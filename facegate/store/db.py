"""Persistent storage (SQLite) plus an in-memory vector index per collection.

SQLite in WAL mode comfortably handles an attendance workload (writes only on
enrolment, reads served from memory). Search is a single matrix-vector product:
for 10,000 enrolled faces x 128 dimensions that is ~1.3M multiply-adds, well
under a millisecond. Swapping in pgvector/FAISS for millions of faces only
touches this module.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from facegate.store.crypto import Cipher

SCHEMA = """
CREATE TABLE IF NOT EXISTS collections (
    collection_id TEXT PRIMARY KEY,
    created_at    REAL NOT NULL,
    model_id      TEXT NOT NULL,
    tags          TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS faces (
    face_id           TEXT PRIMARY KEY,
    collection_id     TEXT NOT NULL REFERENCES collections(collection_id) ON DELETE CASCADE,
    image_id          TEXT NOT NULL,
    external_image_id TEXT,
    user_id           TEXT,
    bbox              TEXT NOT NULL,
    confidence        REAL NOT NULL,
    quality           TEXT NOT NULL,
    liveness          REAL,
    model_id          TEXT NOT NULL,
    embedding         BLOB NOT NULL,
    crop              BLOB,
    created_at        REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS faces_collection ON faces(collection_id, created_at);
CREATE INDEX IF NOT EXISTS faces_external ON faces(collection_id, external_image_id);
CREATE INDEX IF NOT EXISTS faces_user ON faces(collection_id, user_id);
CREATE TABLE IF NOT EXISTS users (
    collection_id TEXT NOT NULL REFERENCES collections(collection_id) ON DELETE CASCADE,
    user_id       TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at    REAL NOT NULL,
    PRIMARY KEY (collection_id, user_id)
);
CREATE TABLE IF NOT EXISTS lookalikes (
    collection_id  TEXT NOT NULL,
    face_id        TEXT NOT NULL,
    other_face_id  TEXT NOT NULL,
    identity       TEXT NOT NULL,
    other_identity TEXT NOT NULL,
    cosine         REAL NOT NULL,
    created_at     REAL NOT NULL,
    PRIMARY KEY (face_id, other_face_id)
);
CREATE TABLE IF NOT EXISTS liveness_sessions (
    session_id   TEXT PRIMARY KEY,
    created_at   REAL NOT NULL,
    expires_at   REAL NOT NULL,
    status       TEXT NOT NULL,
    client_token TEXT,
    settings     TEXT NOT NULL,
    challenge    TEXT NOT NULL,
    confidence   REAL,
    result       TEXT,
    reference    BLOB,
    audit        BLOB
);
CREATE TABLE IF NOT EXISTS audit_log (
    ts            REAL NOT NULL,
    request_id    TEXT NOT NULL,
    operation     TEXT NOT NULL,
    principal     TEXT,
    collection_id TEXT,
    status        TEXT NOT NULL,
    latency_ms    REAL NOT NULL,
    detail        TEXT
);
CREATE INDEX IF NOT EXISTS audit_ts ON audit_log(ts);
"""


@dataclass
class FaceRecord:
    face_id: str
    collection_id: str
    image_id: str
    external_image_id: str | None
    user_id: str | None
    bbox: dict
    confidence: float
    quality: dict
    liveness: float | None
    model_id: str
    created_at: float

    @property
    def identity(self) -> str:
        """Who this face belongs to, for ambiguity / look-alike logic."""
        return self.user_id or self.external_image_id or self.face_id


@dataclass
class _CollectionIndex:
    # (face ids, N x D float32 matrix of L2-normalised templates)
    snapshot: tuple[list[str], np.ndarray | None] = field(default_factory=lambda: ([], None))
    records: dict[str, FaceRecord] = field(default_factory=dict)
    stale: int = 0  # faces embedded with a different model, excluded from search
    dirty: bool = False

    def rebuild(self, vectors: dict[str, np.ndarray]) -> None:
        ids = list(vectors.keys())
        matrix = np.stack([vectors[i] for i in ids]).astype(np.float32) if ids else None
        # Readers take the (ids, matrix) pair in one attribute read, so a
        # concurrent rebuild can never hand them mismatched halves.
        self.snapshot = (ids, matrix)
        self.dirty = False


class _Result:
    def __init__(self, rows: list, rowcount: int):
        self.rows = rows
        self.rowcount = rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list:
        return self.rows

    def __iter__(self):
        return iter(self.rows)


class NotFound(KeyError):
    pass


class AlreadyExists(KeyError):
    pass


class FaceStore:
    def __init__(self, path: Path, cipher: Cipher, model_id: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.cipher = cipher
        self.model_id = model_id
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(SCHEMA)
        self._index: dict[str, _CollectionIndex] = {}
        self._vectors: dict[str, dict[str, np.ndarray]] = {}
        self._load()

    def _x(self, sql: str, args: tuple = ()) -> _Result:
        """Run one statement. The connection is shared between worker
        threads, so every access is serialised by the store lock."""
        with self._lock:
            cur = self._db.execute(sql, args)
            return _Result(cur.fetchall(), cur.rowcount)

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        for row in self._x("SELECT collection_id FROM collections"):
            self._index[row["collection_id"]] = _CollectionIndex()
            self._vectors[row["collection_id"]] = {}
        for row in self._x("SELECT * FROM faces ORDER BY created_at"):
            rec = self._record(row)
            idx = self._index[rec.collection_id]
            idx.records[rec.face_id] = rec
            if rec.model_id != self.model_id:
                idx.stale += 1
                continue
            vec = np.frombuffer(self.cipher.decrypt(row["embedding"], rec.face_id.encode()), dtype=np.float32)
            self._vectors[rec.collection_id][rec.face_id] = vec
        for cid, idx in self._index.items():
            idx.rebuild(self._vectors[cid])

    @staticmethod
    def _record(row: sqlite3.Row) -> FaceRecord:
        return FaceRecord(
            face_id=row["face_id"],
            collection_id=row["collection_id"],
            image_id=row["image_id"],
            external_image_id=row["external_image_id"],
            user_id=row["user_id"],
            bbox=json.loads(row["bbox"]),
            confidence=row["confidence"],
            quality=json.loads(row["quality"]),
            liveness=row["liveness"],
            model_id=row["model_id"],
            created_at=row["created_at"],
        )

    # ----------------------------------------------------------- collections
    def create_collection(self, collection_id: str, tags: dict | None = None) -> None:
        with self._lock:
            if collection_id in self._index:
                raise AlreadyExists(collection_id)
            self._x(
                "INSERT INTO collections VALUES (?,?,?,?)",
                (collection_id, time.time(), self.model_id, json.dumps(tags or {})),
            )
            self._index[collection_id] = _CollectionIndex()
            self._vectors[collection_id] = {}

    def delete_collection(self, collection_id: str) -> None:
        with self._lock:
            self._require(collection_id)
            self._x("DELETE FROM faces WHERE collection_id=?", (collection_id,))
            self._x("DELETE FROM users WHERE collection_id=?", (collection_id,))
            self._x("DELETE FROM lookalikes WHERE collection_id=?", (collection_id,))
            self._x("DELETE FROM collections WHERE collection_id=?", (collection_id,))
            del self._index[collection_id]
            del self._vectors[collection_id]

    def list_collections(self) -> list[str]:
        return sorted(self._index.keys())

    def describe_collection(self, collection_id: str) -> dict:
        self._require(collection_id)
        row = self._x("SELECT * FROM collections WHERE collection_id=?", (collection_id,)).fetchone()
        users = self._x("SELECT COUNT(*) FROM users WHERE collection_id=?", (collection_id,)).fetchone()[0]
        idx = self._index[collection_id]
        return {
            "face_count": len(idx.records),
            "user_count": users,
            "created_at": row["created_at"],
            "stale_faces": idx.stale,
            "tags": json.loads(row["tags"]),
        }

    def _require(self, collection_id: str) -> _CollectionIndex:
        idx = self._index.get(collection_id)
        if idx is None:
            raise NotFound(collection_id)
        return idx

    # ----------------------------------------------------------------- faces
    def add_face(
        self,
        collection_id: str,
        *,
        image_id: str,
        external_image_id: str | None,
        bbox: dict,
        confidence: float,
        quality: dict,
        liveness: float | None,
        embedding: np.ndarray,
        crop_jpeg: bytes | None,
    ) -> FaceRecord:
        with self._lock:
            idx = self._require(collection_id)
            face_id = str(uuid.uuid4())
            now = time.time()
            emb = embedding.astype(np.float32)
            self._x(
                "INSERT INTO faces VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    face_id,
                    collection_id,
                    image_id,
                    external_image_id,
                    None,
                    json.dumps(bbox),
                    confidence,
                    json.dumps(quality),
                    liveness,
                    self.model_id,
                    self.cipher.encrypt(emb.tobytes(), face_id.encode()),
                    self.cipher.encrypt(crop_jpeg, face_id.encode()) if crop_jpeg else None,
                    now,
                ),
            )
            rec = FaceRecord(
                face_id, collection_id, image_id, external_image_id, None, bbox, confidence, quality, liveness, self.model_id, now
            )
            idx.records[face_id] = rec
            self._vectors[collection_id][face_id] = emb
            idx.dirty = True
            return rec

    def delete_faces(self, collection_id: str, face_ids: list[str]) -> tuple[list[str], list[str]]:
        with self._lock:
            idx = self._require(collection_id)
            deleted, missing = [], []
            for fid in face_ids:
                if fid not in idx.records:
                    missing.append(fid)
                    continue
                self._x("DELETE FROM faces WHERE face_id=?", (fid,))
                self._x("DELETE FROM lookalikes WHERE face_id=? OR other_face_id=?", (fid, fid))
                idx.records.pop(fid, None)
                self._vectors[collection_id].pop(fid, None)
                deleted.append(fid)
            idx.dirty = True
            return deleted, missing

    def get_face(self, collection_id: str, face_id: str) -> FaceRecord:
        idx = self._require(collection_id)
        rec = idx.records.get(face_id)
        if rec is None:
            raise NotFound(face_id)
        return rec

    def get_vector(self, collection_id: str, face_id: str) -> np.ndarray:
        self._require(collection_id)
        vec = self._vectors[collection_id].get(face_id)
        if vec is None:
            raise NotFound(face_id)
        return vec

    def list_faces(self, collection_id: str, user_id: str | None = None, face_ids: list[str] | None = None) -> list[FaceRecord]:
        idx = self._require(collection_id)
        recs = sorted(idx.records.values(), key=lambda r: (r.created_at, r.face_id))
        if user_id is not None:
            recs = [r for r in recs if r.user_id == user_id]
        if face_ids:
            wanted = set(face_ids)
            recs = [r for r in recs if r.face_id in wanted]
        return recs

    def faces_for_identity(self, collection_id: str, identity: str) -> list[FaceRecord]:
        idx = self._require(collection_id)
        return [r for r in idx.records.values() if r.identity == identity]

    def search(self, collection_id: str, query: np.ndarray, top_k: int) -> list[tuple[FaceRecord, float]]:
        idx = self._require(collection_id)
        if idx.dirty:
            with self._lock:
                if idx.dirty:
                    idx.rebuild(self._vectors[collection_id])
        ids, matrix = idx.snapshot
        if matrix is None or not ids:
            return []
        scores = matrix @ query.astype(np.float32)
        k = min(top_k, len(ids))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        out = []
        for i in top:
            rec = idx.records.get(ids[i])  # may have been deleted since the snapshot
            if rec is not None:
                out.append((rec, float(scores[i])))
        return out

    def get_crop(self, face_id: str) -> bytes | None:
        row = self._x("SELECT crop FROM faces WHERE face_id=?", (face_id,)).fetchone()
        if row is None or row["crop"] is None:
            return None
        return self.cipher.decrypt(row["crop"], face_id.encode())

    def replace_embedding(self, face_id: str, embedding: np.ndarray) -> None:
        """Used by re-indexing after a model upgrade."""
        with self._lock:
            row = self._x("SELECT collection_id FROM faces WHERE face_id=?", (face_id,)).fetchone()
            if row is None:
                raise NotFound(face_id)
            cid = row["collection_id"]
            emb = embedding.astype(np.float32)
            self._x(
                "UPDATE faces SET embedding=?, model_id=? WHERE face_id=?",
                (self.cipher.encrypt(emb.tobytes(), face_id.encode()), self.model_id, face_id),
            )
            idx = self._index[cid]
            rec = idx.records[face_id]
            if rec.model_id != self.model_id:
                idx.stale = max(0, idx.stale - 1)
                rec.model_id = self.model_id
            self._vectors[cid][face_id] = emb
            idx.dirty = True

    # ----------------------------------------------------------------- users
    def create_user(self, collection_id: str, user_id: str) -> None:
        with self._lock:
            self._require(collection_id)
            try:
                self._x("INSERT INTO users VALUES (?,?,?,?)", (collection_id, user_id, "ACTIVE", time.time()))
            except sqlite3.IntegrityError as exc:
                raise AlreadyExists(user_id) from exc

    def delete_user(self, collection_id: str, user_id: str) -> None:
        with self._lock:
            self._require_user(collection_id, user_id)
            self._x("UPDATE faces SET user_id=NULL WHERE collection_id=? AND user_id=?", (collection_id, user_id))
            self._x("DELETE FROM users WHERE collection_id=? AND user_id=?", (collection_id, user_id))
            for rec in self._index[collection_id].records.values():
                if rec.user_id == user_id:
                    rec.user_id = None

    def list_users(self, collection_id: str) -> list[dict]:
        self._require(collection_id)
        rows = self._x(
            "SELECT user_id, status FROM users WHERE collection_id=? ORDER BY user_id", (collection_id,)
        ).fetchall()
        return [{"UserId": r["user_id"], "UserStatus": r["status"]} for r in rows]

    def _require_user(self, collection_id: str, user_id: str) -> None:
        self._require(collection_id)
        row = self._x(
            "SELECT 1 FROM users WHERE collection_id=? AND user_id=?", (collection_id, user_id)
        ).fetchone()
        if row is None:
            raise NotFound(user_id)

    def user_exists(self, collection_id: str, user_id: str) -> bool:
        try:
            self._require_user(collection_id, user_id)
            return True
        except NotFound:
            return False

    def set_face_user(self, collection_id: str, face_id: str, user_id: str | None) -> None:
        with self._lock:
            self._x("UPDATE faces SET user_id=? WHERE face_id=? AND collection_id=?", (user_id, face_id, collection_id))
            self._index[collection_id].records[face_id].user_id = user_id

    # ------------------------------------------------------------ look-alikes
    def add_lookalike(self, rec: FaceRecord, other: FaceRecord, cosine: float) -> None:
        with self._lock:
            for a, b in ((rec, other), (other, rec)):
                self._x(
                    "INSERT OR REPLACE INTO lookalikes VALUES (?,?,?,?,?,?,?)",
                    (a.collection_id, a.face_id, b.face_id, a.identity, b.identity, cosine, time.time()),
                )

    def lookalike_identities(self, collection_id: str) -> set[str]:
        rows = self._x("SELECT DISTINCT identity FROM lookalikes WHERE collection_id=?", (collection_id,))
        return {r["identity"] for r in rows}

    def list_lookalikes(self, collection_id: str | None = None) -> list[dict]:
        q = "SELECT * FROM lookalikes WHERE identity < other_identity"
        args: tuple = ()
        if collection_id:
            q += " AND collection_id=?"
            args = (collection_id,)
        return [dict(r) for r in self._x(q + " ORDER BY cosine DESC", args)]

    # ------------------------------------------------------ liveness sessions
    def create_session(self, session_id: str, ttl: float, client_token: str | None, settings: dict, challenge: dict) -> None:
        now = time.time()
        with self._lock:
            self._x(
                "INSERT INTO liveness_sessions (session_id, created_at, expires_at, status, client_token, settings, challenge)"
                " VALUES (?,?,?,?,?,?,?)",
                (session_id, now, now + ttl, "CREATED", client_token, json.dumps(settings), json.dumps(challenge)),
            )

    def get_session(self, session_id: str) -> dict:
        row = self._x("SELECT * FROM liveness_sessions WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            raise NotFound(session_id)
        out = dict(row)
        out["settings"] = json.loads(out["settings"])
        out["challenge"] = json.loads(out["challenge"])
        out["result"] = json.loads(out["result"]) if out["result"] else None
        if out["reference"]:
            out["reference"] = json.loads(self.cipher.decrypt(out["reference"], session_id.encode()))
        if out["audit"]:
            out["audit"] = json.loads(self.cipher.decrypt(out["audit"], session_id.encode()))
        return out

    def claim_session(self, session_id: str) -> bool:
        """Atomically move CREATED -> IN_PROGRESS. Each session is single use."""
        with self._lock:
            cur = self._x(
                "UPDATE liveness_sessions SET status='IN_PROGRESS' WHERE session_id=? AND status='CREATED' AND expires_at>?",
                (session_id, time.time()),
            )
            return cur.rowcount == 1

    def finish_session(self, session_id: str, status: str, confidence: float, result: dict, reference: dict | None, audit: list | None) -> None:
        enc = lambda obj: self.cipher.encrypt(json.dumps(obj).encode(), session_id.encode()) if obj else None  # noqa: E731
        with self._lock:
            self._x(
                "UPDATE liveness_sessions SET status=?, confidence=?, result=?, reference=?, audit=? WHERE session_id=?",
                (status, confidence, json.dumps(result), enc(reference), enc(audit), session_id),
            )

    def purge_expired_sessions(self, keep_seconds: float = 3600) -> int:
        with self._lock:
            cur = self._x("DELETE FROM liveness_sessions WHERE expires_at < ?", (time.time() - keep_seconds,))
            return cur.rowcount

    # ------------------------------------------------------------------ audit
    def audit(self, request_id: str, operation: str, principal: str | None, collection_id: str | None, status: str, latency_ms: float, detail: dict | None) -> None:
        try:
            self._x(
                "INSERT INTO audit_log VALUES (?,?,?,?,?,?,?,?)",
                (time.time(), request_id, operation, principal, collection_id, status, latency_ms, json.dumps(detail) if detail else None),
            )
        except sqlite3.Error:
            pass

    def recent_audit(self, limit: int = 100) -> list[dict]:
        rows = self._x("SELECT * FROM audit_log ORDER BY ts DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        return {
            "collections": len(self._index),
            "faces": sum(len(i.records) for i in self._index.values()),
            "stale_faces": sum(i.stale for i in self._index.values()),
        }

    def close(self) -> None:
        self._db.close()

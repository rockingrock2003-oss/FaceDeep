"""Rekognition operations.

Each handler takes the decoded JSON request and returns the JSON response
body, with the same field names, defaults, limits and error types as Amazon
Rekognition. FaceGate-specific signals (liveness score, ambiguity decisions,
timings) are returned as extra ``x-facegate-*`` response headers, which AWS
SDKs ignore, so existing clients see a byte-compatible API.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field

import cv2
import numpy as np

from facegate.api import errors, shapes
from facegate.api.images import load_image
from facegate.config import Settings
from facegate.engine.liveness import CHALLENGE_COLOURS
from facegate.engine.pipeline import AnalyzedFace, Analysis, FaceEngine
from facegate.store.db import AlreadyExists, FaceRecord, FaceStore, NotFound

COLLECTION_RE = re.compile(r"^[a-zA-Z0-9_.\-]{1,255}$")
EXTERNAL_ID_RE = re.compile(r"^[a-zA-Z0-9_.\-:]{1,255}$")
USER_ID_RE = re.compile(r"^[a-zA-Z0-9_.\-:]{1,128}$")
FACE_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SESSION_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
QUALITY_FILTERS = {"NONE", "AUTO", "LOW", "MEDIUM", "HIGH"}
# Rekognition Face Liveness feedback codes (GetFaceLivenessSessionResults).
FEEDBACK_MESSAGES = {
    "FACE_NOT_VISIBLE": "The face was not kept visible throughout the session.",
    "LOW_LIGHTING_DETECTED": "Poor lighting conditions were detected during the liveness check.",
    "HIGH_LIGHTING_DETECTED": "Harsh bright lighting or glare interfered with the check.",
}


@dataclass
class RequestContext:
    request_id: str
    principal: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    collection_id: str | None = None
    detail: dict = field(default_factory=dict)


# ----------------------------------------------------------------- validation
def _validation(field_name: str, value, constraint: str) -> errors.RekognitionError:
    return errors.ValidationException(
        f"1 validation error detected: Value '{value}' at '{field_name}' failed to satisfy constraint: {constraint}"
    )


def _collection_id(req: dict) -> str:
    cid = req.get("CollectionId")
    if not isinstance(cid, str) or not COLLECTION_RE.match(cid):
        raise _validation("collectionId", cid, "Member must satisfy regular expression pattern: [a-zA-Z0-9_.\\-]+")
    return cid


def _optional_str(req: dict, key: str, pattern: re.Pattern, label: str) -> str | None:
    v = req.get(key)
    if v is None:
        return None
    if not isinstance(v, str) or not pattern.match(v):
        raise _validation(label, v, f"Member must satisfy regular expression pattern: {pattern.pattern}")
    return v


def _face_ids(req: dict, key: str = "FaceIds", lo: int = 1, hi: int = 4096) -> list[str]:
    ids = req.get(key)
    if not isinstance(ids, list) or not (lo <= len(ids) <= hi):
        raise _validation(key[0].lower() + key[1:], ids, f"Member must have length between {lo} and {hi}")
    for fid in ids:
        if not isinstance(fid, str) or not FACE_ID_RE.match(fid):
            raise _validation("faceIds", fid, "Member must satisfy regular expression pattern: [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
    return ids


def _number(req: dict, key: str, default: float, lo: float, hi: float) -> float:
    v = req.get(key, default)
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not (lo <= v <= hi):
        raise errors.InvalidParameterException(f"{key} must be between {lo} and {hi}")
    return float(v)


def _int(req: dict, key: str, default: int | None, lo: int, hi: int) -> int | None:
    v = req.get(key, default)
    if v is None:
        return None
    if not isinstance(v, int) or isinstance(v, bool) or not (lo <= v <= hi):
        raise errors.InvalidParameterException(f"{key} must be between {lo} and {hi}")
    return v


def _quality_filter(req: dict, default: str) -> str:
    v = req.get("QualityFilter", default)
    if v not in QUALITY_FILTERS:
        raise _validation("qualityFilter", v, "Member must satisfy enum value set: [NONE, AUTO, LOW, MEDIUM, HIGH]")
    return v


def _encode_token(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"o": offset}).encode()).decode()


def _decode_token(token: str | None) -> int:
    if not token:
        return 0
    try:
        return int(json.loads(base64.urlsafe_b64decode(token.encode()))["o"])
    except Exception as exc:
        raise errors.InvalidPaginationTokenException("Invalid pagination token") from exc


def _page(items: list, req: dict, default_max: int, hard_max: int) -> tuple[list, str | None]:
    start = _decode_token(req.get("NextToken"))
    limit = _int(req, "MaxResults", default_max, 0, hard_max) or default_max
    chunk = items[start : start + limit]
    nxt = _encode_token(start + limit) if start + limit < len(items) else None
    return chunk, nxt


# ------------------------------------------------------------------- service
class RekognitionService:
    def __init__(self, settings: Settings, engine: FaceEngine, store: FaceStore):
        self.s = settings
        self.engine = engine
        self.store = store
        self.handlers = {
            "CreateCollection": self.create_collection,
            "DeleteCollection": self.delete_collection,
            "ListCollections": self.list_collections,
            "DescribeCollection": self.describe_collection,
            "IndexFaces": self.index_faces,
            "ListFaces": self.list_faces,
            "DeleteFaces": self.delete_faces,
            "SearchFacesByImage": self.search_faces_by_image,
            "SearchFaces": self.search_faces,
            "DetectFaces": self.detect_faces,
            "CompareFaces": self.compare_faces,
            "CreateUser": self.create_user,
            "DeleteUser": self.delete_user,
            "ListUsers": self.list_users,
            "AssociateFaces": self.associate_faces,
            "DisassociateFaces": self.disassociate_faces,
            "SearchUsers": self.search_users,
            "SearchUsersByImage": self.search_users_by_image,
            "CreateFaceLivenessSession": self.create_face_liveness_session,
            "GetFaceLivenessSessionResults": self.get_face_liveness_session_results,
        }

    # ------------------------------------------------------------- helpers
    @property
    def model_version(self) -> str:
        return self.s.reported_face_model_version

    def _arn(self, cid: str) -> str:
        return f"aws:rekognition:{self.s.aws_region}:{self.s.aws_account_id}:collection/{cid}"

    def _face_json(self, rec: FaceRecord, include_user: bool = True) -> dict:
        out = {
            "FaceId": rec.face_id,
            "BoundingBox": rec.bbox,
            "ImageId": rec.image_id,
            "Confidence": rec.confidence,
            "IndexFacesModelVersion": self.model_version,
        }
        if rec.external_image_id is not None:
            out["ExternalImageId"] = rec.external_image_id
        if include_user and rec.user_id:
            out["UserId"] = rec.user_id
        return out

    def _require_collection(self, cid: str) -> None:
        try:
            self.store.describe_collection(cid)
        except NotFound as exc:
            raise errors.ResourceNotFoundException(f"The collection id: {cid} does not exist") from exc

    def _analyze(self, ctx: RequestContext, image: dict, *, embed: str, liveness: str = "none", max_faces: int | None = None, field_name: str = "Image", purpose: str = "probe") -> Analysis:
        img, _ = load_image(image, self.s, field_name)
        a = self.engine.analyze(img, embed=embed, liveness=liveness, max_faces=max_faces, purpose=purpose)
        for k, v in a.timings_ms.items():
            ctx.detail[f"t_{k}"] = ctx.detail.get(f"t_{k}", 0) + v
        return a

    def _debug_save(self, ctx: RequestContext, a: Analysis, extra: dict) -> None:
        """Opt-in diagnostics (FACEGATE_DEBUG_PROBE_DIR): probe image + scores."""
        d = self.s.debug_probe_dir
        if d is None:
            return
        try:
            d.mkdir(parents=True, exist_ok=True)
            stem = f"{time.strftime('%Y%m%d-%H%M%S')}-{ctx.request_id[:8]}"
            cv2.imwrite(str(d / f"{stem}.jpg"), a.image, [cv2.IMWRITE_JPEG_QUALITY, 92])
            f = a.faces[0] if a.faces else None
            info = {
                "request_id": ctx.request_id,
                "image": [a.width, a.height],
                "face_box": [round(float(v), 1) for v in f.box] if f is not None else None,
                "quality": {"brightness": f.quality.brightness, "sharpness": f.quality.sharpness, "yaw": f.quality.yaw, "pitch": f.quality.pitch} if f is not None else None,
                "liveness": f.liveness if f is not None else None,
                "liveness_per_model": [float(m.probs(a.image, f.box)[1]) for m in self.engine.liveness.models] if f is not None else None,
                **extra,
                **{k: v for k, v in ctx.detail.items() if not k.startswith("t_")},
            }
            (d / f"{stem}.json").write_text(json.dumps(info, indent=2, default=str))
        except Exception:  # diagnostics must never break a check-in
            pass

    def _liveness_gate(self, ctx: RequestContext, face: AnalyzedFace, mode: str) -> bool:
        """Return True if the probe may proceed."""
        if mode == "off" or face.liveness is None:
            return True
        live = face.liveness >= self.s.passive_liveness_threshold
        ctx.headers["x-facegate-liveness"] = f"score={face.liveness:.4f};live={str(live).lower()};mode={mode}"
        ctx.detail["liveness"] = round(face.liveness, 4)
        return live or mode != "enforce"

    def _ambiguity(self, ctx: RequestContext, cid: str, ranked: list[tuple[FaceRecord, float]], threshold_sim: float) -> bool:
        """Twin / look-alike guard. Returns True if the decision is ambiguous.

        Rekognition simply returns every face above the threshold and leaves the
        choice to the app, which normally takes the first. When two *different*
        people are both close to the probe that choice is a coin toss, so we
        flag it (and by default withhold the match).
        """
        if not ranked:
            return False
        best_rec, best = ranked[0]
        if self.engine.similarity(best) < threshold_sim:
            return False
        rival = next((score for rec, score in ranked[1:] if rec.identity != best_rec.identity), None)
        lookalikes = self.store.lookalike_identities(cid)
        margin_needed = self.s.lookalike_margin if best_rec.identity in lookalikes else self.s.ambiguity_margin
        if rival is None:
            return False
        margin = best - rival
        ctx.detail["margin"] = round(margin, 4)
        if margin < margin_needed:
            ctx.headers["x-facegate-decision"] = f"ambiguous;margin={margin:.4f};required={margin_needed:.2f}"
            return True
        return False

    # --------------------------------------------------------- collections
    def create_collection(self, req: dict, ctx: RequestContext) -> dict:
        cid = _collection_id(req)
        ctx.collection_id = cid
        try:
            self.store.create_collection(cid, req.get("Tags"))
        except AlreadyExists as exc:
            raise errors.ResourceAlreadyExistsException(f"The collection id: {cid} already exists") from exc
        return {"StatusCode": 200, "CollectionArn": self._arn(cid), "FaceModelVersion": self.model_version}

    def delete_collection(self, req: dict, ctx: RequestContext) -> dict:
        cid = _collection_id(req)
        ctx.collection_id = cid
        try:
            self.store.delete_collection(cid)
        except NotFound as exc:
            raise errors.ResourceNotFoundException(f"The collection id: {cid} does not exist") from exc
        return {"StatusCode": 200}

    def list_collections(self, req: dict, ctx: RequestContext) -> dict:
        ids = self.store.list_collections()
        chunk, nxt = _page(ids, req, 1000, 4096)
        out = {"CollectionIds": chunk, "FaceModelVersions": [self.model_version] * len(chunk)}
        if nxt:
            out["NextToken"] = nxt
        return out

    def describe_collection(self, req: dict, ctx: RequestContext) -> dict:
        cid = _collection_id(req)
        ctx.collection_id = cid
        try:
            d = self.store.describe_collection(cid)
        except NotFound as exc:
            raise errors.ResourceNotFoundException(f"The collection id: {cid} does not exist") from exc
        if d["stale_faces"]:
            ctx.headers["x-facegate-stale-faces"] = str(d["stale_faces"])
        return {
            "FaceCount": d["face_count"],
            "FaceModelVersion": self.model_version,
            "CollectionARN": self._arn(cid),
            "CreationTimestamp": d["created_at"],
            "UserCount": d["user_count"],
        }

    # --------------------------------------------------------------- faces
    def index_faces(self, req: dict, ctx: RequestContext) -> dict:
        cid = _collection_id(req)
        ctx.collection_id = cid
        ext = _optional_str(req, "ExternalImageId", EXTERNAL_ID_RE, "externalImageId")
        max_faces = _int(req, "MaxFaces", None, 1, 4096)
        qf = _quality_filter(req, "AUTO")
        self._require_collection(cid)
        liveness_mode = self.s.passive_liveness_on_index
        a = self._analyze(ctx, req.get("Image"), embed="all", liveness="largest" if liveness_mode != "off" else "none", purpose="enrol")
        image_id = str(uuid.uuid4())
        records, unindexed = [], []
        accepted: list[AnalyzedFace] = []
        for face in a.faces:
            reasons = face.reasons(qf)
            if reasons:
                unindexed.append({"Reasons": reasons, "FaceDetail": shapes.face_detail(face, a.width, a.height)})
            else:
                accepted.append(face)
        if max_faces is not None:
            for face in accepted[max_faces:]:
                unindexed.append({"Reasons": ["EXCEEDS_MAX_FACES"], "FaceDetail": shapes.face_detail(face, a.width, a.height)})
            accepted = accepted[:max_faces]

        if accepted and accepted[0] is a.faces[0] and not self._liveness_gate(ctx, accepted[0], liveness_mode):
            unindexed.append({"Reasons": ["LOW_FACE_QUALITY"], "FaceDetail": shapes.face_detail(accepted[0], a.width, a.height)})
            ctx.headers["x-facegate-decision"] = "spoof"
            accepted = accepted[1:]

        for face in accepted:
            bbox = shapes.bounding_box(face.box, a.width, a.height)
            crop = None
            if self.s.store_face_crops:
                ok, buf = cv2.imencode(".jpg", face.aligned, [cv2.IMWRITE_JPEG_QUALITY, 95])
                crop = buf.tobytes() if ok else None
            # Look-alike check against *other* identities before inserting.
            nearest = self.store.search(cid, face.embedding, top_k=20)
            rec = self.store.add_face(
                cid,
                image_id=image_id,
                external_image_id=ext,
                bbox=bbox,
                confidence=shapes.confidence(face),
                quality=shapes.quality(face),
                liveness=face.liveness,
                embedding=face.embedding,
                crop_jpeg=crop,
            )
            for other, score in nearest:
                if other.identity != rec.identity and score >= self.s.lookalike_threshold:
                    self.store.add_lookalike(rec, other, score)
                    ctx.headers["x-facegate-lookalike"] = f"{other.identity};cosine={score:.4f}"
            records.append({"Face": self._face_json(rec, include_user=False), "FaceDetail": shapes.face_detail(face, a.width, a.height)})
        ctx.detail["indexed"] = len(records)
        return {"FaceRecords": records, "FaceModelVersion": self.model_version, "UnindexedFaces": unindexed}

    def list_faces(self, req: dict, ctx: RequestContext) -> dict:
        cid = _collection_id(req)
        ctx.collection_id = cid
        user_id = _optional_str(req, "UserId", USER_ID_RE, "userId")
        face_ids = _face_ids(req, lo=1, hi=4096) if req.get("FaceIds") is not None else None
        try:
            recs = self.store.list_faces(cid, user_id=user_id, face_ids=face_ids)
        except NotFound as exc:
            raise errors.ResourceNotFoundException(f"The collection id: {cid} does not exist") from exc
        chunk, nxt = _page(recs, req, 1000, 4096)
        out = {"Faces": [self._face_json(r) for r in chunk], "FaceModelVersion": self.model_version}
        if nxt:
            out["NextToken"] = nxt
        return out

    def delete_faces(self, req: dict, ctx: RequestContext) -> dict:
        cid = _collection_id(req)
        ctx.collection_id = cid
        ids = _face_ids(req)
        self._require_collection(cid)
        deletable, unsuccessful = [], []
        for fid in ids:
            try:
                rec = self.store.get_face(cid, fid)
            except NotFound:
                continue  # Rekognition silently ignores unknown ids here
            if rec.user_id:
                unsuccessful.append({"FaceId": fid, "UserId": rec.user_id, "Reasons": ["ASSOCIATED_TO_AN_EXISTING_USER"]})
            else:
                deletable.append(fid)
        deleted, _ = self.store.delete_faces(cid, deletable)
        out: dict = {"DeletedFaces": deleted}
        if unsuccessful:
            out["UnsuccessfulFaceDeletions"] = unsuccessful
        return out

    # -------------------------------------------------------------- search
    def _rank(self, cid: str, query: np.ndarray, max_faces: int) -> list[tuple[FaceRecord, float]]:
        # Fetch extra candidates so the ambiguity guard can see rival identities.
        return self.store.search(cid, query, top_k=max(max_faces, 50))

    def search_faces_by_image(self, req: dict, ctx: RequestContext) -> dict:
        cid = _collection_id(req)
        ctx.collection_id = cid
        max_faces = _int(req, "MaxFaces", 80, 1, 4096)
        threshold = _number(req, "FaceMatchThreshold", 80.0, 0.0, 100.0)
        qf = _quality_filter(req, "NONE")
        self._require_collection(cid)
        mode = self.s.passive_liveness_on_search
        a = self._analyze(ctx, req.get("Image"), embed="largest", liveness="largest" if mode != "off" else "none", max_faces=1)
        if not a.faces or a.faces[0].reasons(qf):
            raise errors.InvalidParameterException(errors.NO_FACES_MESSAGE)
        face = a.faces[0]
        out = {
            "SearchedFaceBoundingBox": shapes.bounding_box(face.box, a.width, a.height),
            "SearchedFaceConfidence": shapes.confidence(face),
            "FaceMatches": [],
            "FaceModelVersion": self.model_version,
        }
        if not self._liveness_gate(ctx, face, mode):
            ctx.headers["x-facegate-decision"] = "spoof"
            ctx.detail["decision"] = "spoof"
            self._debug_save(ctx, a, {"operation": "SearchFacesByImage"})
            return out
        t = time.perf_counter()
        ranked = self._rank(cid, face.embedding, max_faces)
        ctx.detail["t_search"] = round((time.perf_counter() - t) * 1000, 3)
        if self._ambiguity(ctx, cid, ranked, threshold) and self.s.ambiguity_policy == "reject":
            ctx.detail["decision"] = "ambiguous"
            return out
        matches = []
        for rec, score in ranked[:max_faces]:
            sim = self.engine.similarity(score)
            if sim >= threshold:
                matches.append({"Similarity": float(round(sim, 6)), "Face": self._face_json(rec)})
        out["FaceMatches"] = matches
        ctx.detail["decision"] = "match" if matches else "no_match"
        if matches:
            ctx.detail["top"] = matches[0]["Face"].get("ExternalImageId") or matches[0]["Face"]["FaceId"]
            ctx.detail["similarity"] = matches[0]["Similarity"]
        ctx.headers.setdefault("x-facegate-decision", ctx.detail["decision"])
        self._debug_save(ctx, a, {"operation": "SearchFacesByImage"})
        return out

    def search_faces(self, req: dict, ctx: RequestContext) -> dict:
        cid = _collection_id(req)
        ctx.collection_id = cid
        fid = req.get("FaceId")
        if not isinstance(fid, str) or not FACE_ID_RE.match(fid):
            raise _validation("faceId", fid, "Member must satisfy regular expression pattern for a FaceId")
        max_faces = _int(req, "MaxFaces", 80, 1, 4096)
        threshold = _number(req, "FaceMatchThreshold", 80.0, 0.0, 100.0)
        self._require_collection(cid)
        try:
            query = self.store.get_vector(cid, fid)
        except NotFound as exc:
            raise errors.InvalidParameterException(f"Face {fid} does not exist in collection {cid}") from exc
        matches = []
        for rec, score in self.store.search(cid, query, top_k=max_faces + 1):
            if rec.face_id == fid:
                continue
            sim = self.engine.similarity(score)
            if sim >= threshold:
                matches.append({"Similarity": float(round(sim, 6)), "Face": self._face_json(rec)})
        return {"SearchedFaceId": fid, "FaceMatches": matches[:max_faces], "FaceModelVersion": self.model_version}

    def detect_faces(self, req: dict, ctx: RequestContext) -> dict:
        attrs = req.get("Attributes") or ["DEFAULT"]
        if not isinstance(attrs, list):
            raise errors.InvalidParameterException("Attributes must be a list")
        a = self._analyze(ctx, req.get("Image"), embed="none", max_faces=100)
        if any(x != "DEFAULT" for x in attrs):
            # Age/emotion/accessory attributes are not part of an attendance
            # flow and are deliberately not implemented.
            ctx.headers["x-facegate-unsupported-attributes"] = ",".join(x for x in attrs if x != "DEFAULT")
        return {"FaceDetails": [shapes.face_detail(f, a.width, a.height) for f in a.faces]}

    def compare_faces(self, req: dict, ctx: RequestContext) -> dict:
        threshold = _number(req, "SimilarityThreshold", 80.0, 0.0, 100.0)
        qf = _quality_filter(req, "NONE")
        src = self._analyze(ctx, req.get("SourceImage"), embed="largest", max_faces=1, field_name="SourceImage")
        if not src.faces or src.faces[0].reasons(qf):
            raise errors.InvalidParameterException(errors.NO_FACES_MESSAGE)
        tgt = self._analyze(ctx, req.get("TargetImage"), embed="all", max_faces=100, field_name="TargetImage")
        if not tgt.faces:
            raise errors.InvalidParameterException(errors.NO_FACES_MESSAGE)
        s = src.faces[0]
        matches, unmatched = [], []
        for f in tgt.faces:
            if f.reasons(qf):
                continue
            sim = self.engine.similarity(float(np.dot(s.embedding, f.embedding)))
            item = shapes.compared_face(f, tgt.width, tgt.height)
            if sim >= threshold:
                matches.append({"Similarity": float(round(sim, 6)), "Face": item})
            else:
                unmatched.append(item)
        matches.sort(key=lambda m: m["Similarity"], reverse=True)
        return {
            "SourceImageFace": {
                "BoundingBox": shapes.bounding_box(s.box, src.width, src.height),
                "Confidence": shapes.confidence(s),
            },
            "FaceMatches": matches,
            "UnmatchedFaces": unmatched,
        }

    # --------------------------------------------------------------- users
    def _user_id(self, req: dict) -> str:
        uid = req.get("UserId")
        if not isinstance(uid, str) or not USER_ID_RE.match(uid):
            raise _validation("userId", uid, "Member must satisfy regular expression pattern: [a-zA-Z0-9_.\\-:]+")
        return uid

    def create_user(self, req: dict, ctx: RequestContext) -> dict:
        cid = _collection_id(req)
        ctx.collection_id = cid
        uid = self._user_id(req)
        self._require_collection(cid)
        try:
            self.store.create_user(cid, uid)
        except AlreadyExists as exc:
            raise errors.ConflictException(f"User {uid} already exists in collection {cid}") from exc
        return {}

    def delete_user(self, req: dict, ctx: RequestContext) -> dict:
        cid = _collection_id(req)
        ctx.collection_id = cid
        uid = self._user_id(req)
        self._require_collection(cid)
        try:
            self.store.delete_user(cid, uid)
        except NotFound as exc:
            raise errors.ResourceNotFoundException(f"User {uid} does not exist") from exc
        return {}

    def list_users(self, req: dict, ctx: RequestContext) -> dict:
        cid = _collection_id(req)
        ctx.collection_id = cid
        self._require_collection(cid)
        users = self.store.list_users(cid)
        chunk, nxt = _page(users, req, 500, 500)
        out: dict = {"Users": chunk}
        if nxt:
            out["NextToken"] = nxt
        return out

    def associate_faces(self, req: dict, ctx: RequestContext) -> dict:
        cid = _collection_id(req)
        ctx.collection_id = cid
        uid = self._user_id(req)
        ids = _face_ids(req, hi=100)
        threshold = _number(req, "UserMatchThreshold", 75.0, 0.0, 100.0)
        self._require_collection(cid)
        if not self.store.user_exists(cid, uid):
            raise errors.ResourceNotFoundException(f"User {uid} does not exist")
        existing = [self.store.get_vector(cid, r.face_id) for r in self.store.list_faces(cid, user_id=uid) if r.model_id == self.store.model_id]
        associated, failed = [], []
        for fid in ids:
            try:
                rec = self.store.get_face(cid, fid)
                vec = self.store.get_vector(cid, fid)
            except NotFound:
                failed.append({"FaceId": fid, "Reasons": ["FACE_NOT_FOUND"]})
                continue
            if rec.user_id and rec.user_id != uid:
                failed.append({"FaceId": fid, "UserId": rec.user_id, "Reasons": ["ASSOCIATED_TO_A_DIFFERENT_USER"]})
                continue
            if existing:
                sim = self.engine.similarity(max(float(np.dot(vec, e)) for e in existing))
                if sim < threshold:
                    failed.append({"FaceId": fid, "UserId": uid, "Confidence": float(round(sim, 4)), "Reasons": ["LOW_MATCH_CONFIDENCE"]})
                    continue
            self.store.set_face_user(cid, fid, uid)
            existing.append(vec)
            associated.append({"FaceId": fid})
        return {"AssociatedFaces": associated, "UnsuccessfulFaceAssociations": failed, "UserStatus": "ACTIVE"}

    def disassociate_faces(self, req: dict, ctx: RequestContext) -> dict:
        cid = _collection_id(req)
        ctx.collection_id = cid
        uid = self._user_id(req)
        ids = _face_ids(req, hi=100)
        self._require_collection(cid)
        if not self.store.user_exists(cid, uid):
            raise errors.ResourceNotFoundException(f"User {uid} does not exist")
        done, failed = [], []
        for fid in ids:
            try:
                rec = self.store.get_face(cid, fid)
            except NotFound:
                failed.append({"FaceId": fid, "UserId": uid, "Reasons": ["FACE_NOT_FOUND"]})
                continue
            if rec.user_id != uid:
                failed.append({"FaceId": fid, "UserId": uid, "Reasons": ["ASSOCIATED_TO_A_DIFFERENT_USER"]})
                continue
            self.store.set_face_user(cid, fid, None)
            done.append({"FaceId": fid})
        return {"DisassociatedFaces": done, "UnsuccessfulFaceDisassociations": failed, "UserStatus": "ACTIVE"}

    def _user_matches(self, cid: str, ranked: list[tuple[FaceRecord, float]], threshold: float, max_users: int, exclude: str | None = None) -> list[dict]:
        best: dict[str, float] = {}
        for rec, score in ranked:
            if rec.user_id and rec.user_id != exclude and score > best.get(rec.user_id, -2.0):
                best[rec.user_id] = score
        out = []
        for uid, score in sorted(best.items(), key=lambda kv: kv[1], reverse=True):
            sim = self.engine.similarity(score)
            if sim >= threshold:
                out.append({"Similarity": float(round(sim, 6)), "User": {"UserId": uid, "UserStatus": "ACTIVE"}})
        return out[:max_users]

    def search_users(self, req: dict, ctx: RequestContext) -> dict:
        cid = _collection_id(req)
        ctx.collection_id = cid
        threshold = _number(req, "UserMatchThreshold", 80.0, 0.0, 100.0)
        max_users = _int(req, "MaxUsers", 50, 1, 500)
        self._require_collection(cid)
        out: dict = {"FaceModelVersion": self.model_version}
        if req.get("FaceId"):
            fid = req["FaceId"]
            try:
                query = self.store.get_vector(cid, fid)
            except NotFound as exc:
                raise errors.InvalidParameterException(f"Face {fid} does not exist") from exc
            exclude = None
            out["SearchedFace"] = {"FaceId": fid}
            ranked = self.store.search(cid, query, top_k=200)
            ranked = [(r, s) for r, s in ranked if r.face_id != fid]
        elif req.get("UserId"):
            uid = self._user_id(req)
            faces = [r for r in self.store.list_faces(cid, user_id=uid) if r.model_id == self.store.model_id]
            if not faces:
                raise errors.ResourceNotFoundException(f"User {uid} does not exist or has no faces")
            query = np.mean([self.store.get_vector(cid, r.face_id) for r in faces], axis=0)
            query = query / np.linalg.norm(query)
            exclude = uid
            out["SearchedUser"] = {"UserId": uid}
            ranked = self.store.search(cid, query, top_k=200)
        else:
            raise errors.InvalidParameterException("Either FaceId or UserId must be specified")
        out["UserMatches"] = self._user_matches(cid, ranked, threshold, max_users, exclude)
        return out

    def search_users_by_image(self, req: dict, ctx: RequestContext) -> dict:
        cid = _collection_id(req)
        ctx.collection_id = cid
        threshold = _number(req, "UserMatchThreshold", 80.0, 0.0, 100.0)
        max_users = _int(req, "MaxUsers", 50, 1, 500)
        qf = _quality_filter(req, "NONE")
        self._require_collection(cid)
        mode = self.s.passive_liveness_on_search
        a = self._analyze(ctx, req.get("Image"), embed="largest", liveness="largest" if mode != "off" else "none", max_faces=100)
        if not a.faces or a.faces[0].reasons(qf):
            raise errors.InvalidParameterException(errors.NO_FACES_MESSAGE)
        face = a.faces[0]
        out = {
            "UserMatches": [],
            "FaceModelVersion": self.model_version,
            "SearchedFace": {"FaceDetail": shapes.face_detail(face, a.width, a.height)},
            "UnsearchedFaces": [
                {"FaceDetails": shapes.face_detail(f, a.width, a.height), "Reasons": ["FACE_NOT_LARGEST"]} for f in a.faces[1:]
            ],
        }
        if not self._liveness_gate(ctx, face, mode):
            ctx.headers["x-facegate-decision"] = "spoof"
            return out
        ranked = self.store.search(cid, face.embedding, top_k=200)
        ranked_users = [(r, s) for r, s in ranked if r.user_id]
        # Ambiguity at the user level: compare best user to best *other* user.
        if self._ambiguity(ctx, cid, ranked_users, threshold) and self.s.ambiguity_policy == "reject":
            return out
        out["UserMatches"] = self._user_matches(cid, ranked, threshold, max_users)
        return out

    # ------------------------------------------------------------ liveness
    def create_face_liveness_session(self, req: dict, ctx: RequestContext) -> dict:
        return self.new_liveness_session(req, mode="flash")

    def new_liveness_session(self, req: dict, mode: str = "flash") -> dict:
        """Create a liveness session. mode="flash" is the colour challenge
        (Rekognition-style); mode="passive" captures plain frames (REST API only)."""
        settings = req.get("Settings") or {}
        audit_limit = _int(settings, "AuditImagesLimit", 0, 0, 4)
        session_id = str(uuid.uuid4())
        rng = secrets.SystemRandom()
        names = [c for c in CHALLENGE_COLOURS if c != "white"]
        # Every third frame is neutral white (passive anti-spoofing and the
        # reference image use those); the others are a random colour sequence
        # in which consecutive colours always differ.
        seq: list[str] = []
        for i in range(self.s.liveness_frames_required):
            if i % 3 == 0:
                seq.append("white")
            else:
                seq.append(rng.choice([c for c in names if c != seq[-1]]))
        challenge = {"type": "FaceMovementAndLightChallenge", "version": "1.0.0", "colours": seq, "flash_ms": 220, "mode": "flash"}
        if mode == "passive":
            # 7 plain frames, one every 250 ms; nothing to follow.
            n = self.s.liveness_frames_required
            challenge = {"type": "PassiveFrames", "version": "1.0.0", "colours": ["none"] * n, "flash_ms": 250, "mode": "passive"}
        self.store.create_session(
            session_id,
            ttl=self.s.liveness_session_ttl_seconds,
            client_token=req.get("ClientRequestToken"),
            settings={"AuditImagesLimit": audit_limit, "OutputConfig": settings.get("OutputConfig")},
            challenge=challenge,
        )
        return {"SessionId": session_id}

    def get_face_liveness_session_results(self, req: dict, ctx: RequestContext) -> dict:
        sid = req.get("SessionId")
        if not isinstance(sid, str) or not SESSION_ID_RE.match(sid):
            raise errors.InvalidParameterException("SessionId is invalid")
        try:
            sess = self.store.get_session(sid)
        except NotFound as exc:
            raise errors.SessionNotFoundException(f"Session {sid} was not found") from exc
        status = sess["status"]
        if status in ("CREATED", "IN_PROGRESS") and sess["expires_at"] < time.time():
            status = "EXPIRED"
        out: dict = {"SessionId": sid, "Status": status, "Challenge": {"Type": "FaceMovementAndLightChallenge", "Version": "1.0.0"}}
        if status in ("SUCCEEDED", "FAILED") and sess["confidence"] is not None:
            out["Confidence"] = float(sess["confidence"])
            ref = sess.get("reference")
            if ref:
                out["ReferenceImage"] = {"Bytes": ref["bytes"], "BoundingBox": ref["box"]}
            if sess.get("audit"):
                out["AuditImages"] = [{"Bytes": a["bytes"], "BoundingBox": a["box"]} for a in sess["audit"]]
            if sess.get("result"):
                ctx.headers["x-facegate-liveness-reasons"] = ",".join(sess["result"].get("reasons", [])) or "none"
                feedback = sess["result"].get("feedback") or []
                if feedback and float(sess["confidence"]) < self.s.liveness_pass_confidence:
                    # Rekognition returns retry guidance for low-confidence sessions
                    # as Feedback: [{Code, Message}] with a fixed set of codes. Our
                    # extra codes (SCREEN_TOO_DIM, MULTIPLE_FACES) go only in the
                    # header so strict clients never see an unknown enum value.
                    standard = [c for c in feedback if c in FEEDBACK_MESSAGES]
                    if standard:
                        out["Feedback"] = [{"Code": c, "Message": FEEDBACK_MESSAGES[c]} for c in standard]
                    ctx.headers["x-facegate-liveness-feedback"] = ",".join(feedback)
        return out

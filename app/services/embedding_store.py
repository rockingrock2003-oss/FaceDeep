from datetime import datetime, timezone

import chromadb
import numpy as np

from app.core.config import settings
from app.services.encryption_service import encryption_service

MAX_EMBEDDINGS_PER_PERSON = 50


class EmbeddingStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
        )

    def _get_collection_name(self, user_id: str) -> str:
        return f"user_{user_id}_faces"

    def get_or_create_collection(self, user_id: str):
        return self.client.get_or_create_collection(
            name=self._get_collection_name(user_id),
            metadata={"hnsw:space": "cosine"},
        )

    def _get_person_embeddings(
        self, user_id: str, person_id: str
    ) -> list[dict]:
        collection = self.get_or_create_collection(user_id)
        results = collection.get(include=["metadatas"])

        embeddings = []
        for i, metadata in enumerate(results["metadatas"]):
            try:
                decrypted = encryption_service.decrypt(metadata["person_id"])
                if decrypted == person_id:
                    embeddings.append(
                        {
                            "face_id": results["ids"][i],
                            "uploaded_time": metadata["uploaded_time"],
                        }
                    )
            except Exception:
                continue
        return embeddings

    def _remove_oldest_embeddings(
        self, user_id: str, person_id: str, count_to_remove: int
    ) -> list[str]:
        embeddings = self._get_person_embeddings(user_id, person_id)
        if not embeddings:
            return []

        embeddings.sort(key=lambda x: x["uploaded_time"])
        to_remove = embeddings[:count_to_remove]
        removed_times = [e["uploaded_time"] for e in to_remove]
        removed_ids = [e["face_id"] for e in to_remove]

        collection = self.get_or_create_collection(user_id)
        collection.delete(ids=removed_ids)
        return removed_times

    def add_embedding(
        self,
        user_id: str,
        face_id: str,
        embedding: np.ndarray,
        person_id: str,
    ) -> dict:
        collection = self.get_or_create_collection(user_id)
        uploaded_time = datetime.now(timezone.utc).isoformat()
        encrypted_person_id = encryption_service.encrypt(person_id)

        existing = self._get_person_embeddings(user_id, person_id)
        removed_times = []

        if len(existing) >= MAX_EMBEDDINGS_PER_PERSON:
            count_to_remove = len(existing) - MAX_EMBEDDINGS_PER_PERSON + 1
            removed_times = self._remove_oldest_embeddings(
                user_id, person_id, count_to_remove
            )

        collection.add(
            embeddings=[embedding.astype(np.float32).tolist()],
            ids=[face_id],
            metadatas=[
                {
                    "person_id": encrypted_person_id,
                    "uploaded_time": uploaded_time,
                }
            ],
        )

        return {
            "face_id": face_id,
            "person_id": person_id,
            "uploaded_time": uploaded_time,
            "removed_count": len(removed_times),
            "removed_uploaded_times": removed_times,
        }

    def search(
        self,
        user_id: str,
        query_embedding: np.ndarray,
        n_results: int = 5,
    ) -> list[dict]:
        collection = self.get_or_create_collection(user_id)
        count = collection.count()
        if count == 0:
            return []

        n_results = min(n_results, count)
        results = collection.query(
            query_embeddings=[query_embedding.astype(np.float32).tolist()],
            n_results=n_results,
            include=["metadatas", "distances"],
        )

        matches = []
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i]
            similarity = 1 - distance
            metadata = results["metadatas"][0][i]
            try:
                original_person_id = encryption_service.decrypt(metadata["person_id"])
            except Exception:
                original_person_id = metadata["person_id"]
            matches.append(
                {
                    "face_id": doc_id,
                    "person_id": original_person_id,
                    "similarity": similarity,
                }
            )
        return matches

    def update_embedding(
        self,
        user_id: str,
        face_id: str,
        embedding: np.ndarray,
        person_id: str,
    ) -> dict:
        collection = self.get_or_create_collection(user_id)
        uploaded_time = datetime.now(timezone.utc).isoformat()
        encrypted_person_id = encryption_service.encrypt(person_id)

        collection.update(
            ids=[face_id],
            embeddings=[embedding.astype(np.float32).tolist()],
            metadatas=[
                {
                    "person_id": encrypted_person_id,
                    "uploaded_time": uploaded_time,
                }
            ],
        )
        return {"face_id": face_id, "person_id": person_id}

    def get_face_ids_by_person_id(self, user_id: str, person_id: str) -> list[str]:
        collection = self.get_or_create_collection(user_id)
        results = collection.get(include=["metadatas"])

        face_ids = []
        for i, metadata in enumerate(results["metadatas"]):
            try:
                decrypted = encryption_service.decrypt(metadata["person_id"])
                if decrypted == person_id:
                    face_ids.append(results["ids"][i])
            except Exception:
                continue
        return face_ids

    def delete_by_person_id(self, user_id: str, person_id: str) -> int:
        collection = self.get_or_create_collection(user_id)
        results = collection.get(include=["metadatas"])

        ids_to_delete = []
        for i, metadata in enumerate(results["metadatas"]):
            try:
                decrypted = encryption_service.decrypt(metadata["person_id"])
                if decrypted == person_id:
                    ids_to_delete.append(results["ids"][i])
            except Exception:
                continue

        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
        return len(ids_to_delete)

    def delete_embedding(self, user_id: str, face_id: str) -> bool:
        collection = self.get_or_create_collection(user_id)
        try:
            collection.delete(ids=[face_id])
            return True
        except Exception:
            return False

    def clear_all_embeddings(self, user_id: str) -> int:
        collection = self.get_or_create_collection(user_id)
        count = collection.count()
        if count > 0:
            results = collection.get()
            collection.delete(ids=results["ids"])
        return count

    def list_persons(self, user_id: str) -> list[dict]:
        collection = self.get_or_create_collection(user_id)
        results = collection.get(include=["metadatas"])

        persons = {}
        for i, metadata in enumerate(results["metadatas"]):
            try:
                pid = encryption_service.decrypt(metadata["person_id"])
                if pid not in persons:
                    persons[pid] = {
                        "person_id": pid,
                        "face_count": 0,
                    }
                persons[pid]["face_count"] += 1
            except Exception:
                continue

        return list(persons.values())

import chromadb
import numpy as np

from app.core.config import settings


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

    def add_embedding(
        self,
        user_id: str,
        face_id: str,
        embedding: np.ndarray,
        person_id: str,
        label: str,
    ) -> dict:
        collection = self.get_or_create_collection(user_id)
        collection.add(
            embeddings=[embedding.tolist()],
            ids=[face_id],
            metadatas=[
                {
                    "person_id": person_id,
                    "label": label,
                }
            ],
        )
        return {"face_id": face_id, "person_id": person_id, "label": label}

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
            query_embeddings=[query_embedding.tolist()],
            n_results=n_results,
            include=["metadatas", "distances"],
        )

        matches = []
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i]
            similarity = 1 - distance
            metadata = results["metadatas"][0][i]
            matches.append(
                {
                    "face_id": doc_id,
                    "person_id": metadata["person_id"],
                    "label": metadata["label"],
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
        label: str,
    ) -> dict:
        collection = self.get_or_create_collection(user_id)
        collection.update(
            ids=[face_id],
            embeddings=[embedding.tolist()],
            metadatas=[
                {
                    "person_id": person_id,
                    "label": label,
                }
            ],
        )
        return {"face_id": face_id, "person_id": person_id, "label": label}

    def get_face_ids_by_person_id(self, user_id: str, person_id: str) -> list[str]:
        collection = self.get_or_create_collection(user_id)
        results = collection.get(include=["metadatas"])

        face_ids = []
        for i, metadata in enumerate(results["metadatas"]):
            if metadata["person_id"] == person_id:
                face_ids.append(results["ids"][i])
        return face_ids

    def delete_by_person_id(self, user_id: str, person_id: str) -> int:
        collection = self.get_or_create_collection(user_id)
        results = collection.get(include=["metadatas"])

        ids_to_delete = []
        for i, metadata in enumerate(results["metadatas"]):
            if metadata["person_id"] == person_id:
                ids_to_delete.append(results["ids"][i])

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

    def list_persons(self, user_id: str) -> list[dict]:
        collection = self.get_or_create_collection(user_id)
        results = collection.get(include=["metadatas"])

        persons = {}
        for i, metadata in enumerate(results["metadatas"]):
            pid = metadata["person_id"]
            if pid not in persons:
                persons[pid] = {
                    "person_id": pid,
                    "label": metadata["label"],
                    "face_count": 0,
                }
            persons[pid]["face_count"] += 1

        return list(persons.values())

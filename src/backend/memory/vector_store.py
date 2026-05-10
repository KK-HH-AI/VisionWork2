import os
import hashlib
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer


class VectorStore:
    def __init__(self, persist_dir: str, model_name: str = "all-MiniLM-L6-v2"):
        self._persist_dir = persist_dir
        self._model_name = model_name
        self._client = None
        self._collection = None
        self._embedder = None

    def _ensure_initialized(self):
        if self._client is not None:
            return

        os.makedirs(self._persist_dir, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=self._persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        self._collection = self._client.get_or_create_collection(
            name="code_analysis_notes",
            metadata={"hnsw:space": "cosine"},
        )

        self._embedder = SentenceTransformer(self._model_name)

    def add_notes(self, notes: List[dict]):
        self._ensure_initialized()

        if not notes:
            return

        ids = []
        documents = []
        metadatas = []

        for note in notes:
            note_id = note.get("id", "")
            if not note_id:
                content = note.get("content", "")
                note_id = hashlib.md5(content.encode()).hexdigest()[:16]

            ids.append(note_id)
            documents.append(note.get("content", ""))
            metadatas.append({
                "filepath": note.get("filepath", ""),
                "filename": note.get("filename", ""),
                "note_path": note.get("note_path", ""),
                "node_id": note.get("node_id", ""),
            })

        embeddings = self._embedder.encode(documents).tolist()

        existing_ids = set()
        try:
            existing = self._collection.get(ids=ids)
            if existing and existing.get("ids"):
                existing_ids = set(existing["ids"])
        except Exception:
            pass

        new_ids = []
        new_documents = []
        new_metadatas = []
        new_embeddings = []

        for i, doc_id in enumerate(ids):
            if doc_id not in existing_ids:
                new_ids.append(doc_id)
                new_documents.append(documents[i])
                new_metadatas.append(metadatas[i])
                new_embeddings.append(embeddings[i])

        if new_ids:
            self._collection.add(
                ids=new_ids,
                documents=new_documents,
                metadatas=new_metadatas,
                embeddings=new_embeddings,
            )

    def search(self, query: str, k: int = 5) -> List[dict]:
        self._ensure_initialized()

        query_embedding = self._embedder.encode([query]).tolist()

        results = self._collection.query(
            query_embeddings=query_embedding,
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )

        output = []
        if results and results.get("ids") and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                doc_id = results["ids"][0][i]
                document = results["documents"][0][i] if results.get("documents") else ""
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                distance = results["distances"][0][i] if results.get("distances") else 0.0

                output.append({
                    "id": doc_id,
                    "content": document[:800] if len(document) > 800 else document,
                    "filepath": metadata.get("filepath", ""),
                    "filename": metadata.get("filename", ""),
                    "note_path": metadata.get("note_path", ""),
                    "node_id": metadata.get("node_id", ""),
                    "score": round(1.0 - distance, 4),
                })

        return output

    def clear(self):
        self._ensure_initialized()
        try:
            self._client.delete_collection("code_analysis_notes")
            self._collection = self._client.get_or_create_collection(
                name="code_analysis_notes",
                metadata={"hnsw:space": "cosine"},
            )
        except Exception:
            pass


_store_instances: Dict[str, VectorStore] = {}


def get_vector_store(persist_dir: str, model_name: str = "all-MiniLM-L6-v2") -> VectorStore:
    key = f"{persist_dir}::{model_name}"
    if key not in _store_instances:
        _store_instances[key] = VectorStore(persist_dir, model_name)
    return _store_instances[key]
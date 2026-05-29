import os
import logging

logger = logging.getLogger(__name__)


def init_vector_store(project_path: str):
    import chromadb
    from chromadb.utils import embedding_functions

    vector_db_path = os.path.join(project_path, "vector_db")
    os.makedirs(vector_db_path, exist_ok=True)

    client = chromadb.PersistentClient(path=vector_db_path)
    embedding_fn = embedding_functions.DefaultEmbeddingFunction()
    collection = client.get_or_create_collection(
        name="memory",
        embedding_function=embedding_fn,
    )

    logger.info(f"[memory_vector_store] Vector store initialized at: {vector_db_path}")
    return collection


def add_notes(collection, notes: list, chunk_size=500):
    ids = []
    documents = []
    metadatas = []

    for note in notes:
        content = note.get("content", "")
        filepath = note.get("filepath", "")
        filename = note.get("filename", "")

        if not content or not content.strip():
            continue

        try:
            existing = collection.get(where={"filepath": filepath})
            if existing and existing.get("ids"):
                collection.delete(ids=existing["ids"])
                logger.debug(f"[memory_vector_store] Deleted existing vectors for: {filepath}")
        except Exception as e:
            logger.debug(f"[memory_vector_store] Could not check/delete existing for {filepath}: {e}")

        words = content.split()
        total_chunks = (len(words) + chunk_size - 1) // chunk_size

        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            chunk_text = " ".join(chunk_words)
            chunk_idx = i // chunk_size
            ids.append(f"note_{filename}_{chunk_idx}")
            documents.append(chunk_text)
            metadatas.append({
                "source_type": "note",
                "filepath": filepath,
                "filename": filename,
                "chunk_index": chunk_idx,
                "total_chunks": total_chunks,
            })

    if ids:
        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        logger.info(f"[memory_vector_store] Added {len(ids)} chunks from {len(notes)} notes")

    return len(ids)


def add_community_summaries(collection, summaries: list):
    ids = []
    documents = []
    metadatas = []

    for summary in summaries:
        content = summary.get("content", "")
        level = summary.get("level", "")
        community_id = summary.get("community_id", summary.get("id", ""))
        summary_path = summary.get("summary_path", "")

        if not content or not content.strip():
            continue

        doc_id = f"community_{level}_{community_id}"
        ids.append(doc_id)
        documents.append(content)
        metadatas.append({
            "source_type": "community",
            "level": level,
            "community_id": community_id,
            "summary_path": summary_path,
        })

    if ids:
        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        logger.info(f"[memory_vector_store] Added {len(ids)} community summaries")

    return len(ids)


def query_vector_store(collection, query: str, k: int, search_type: str) -> list:
    where_filter = None
    if search_type == "note":
        where_filter = {"source_type": "note"}
    elif search_type == "community":
        where_filter = {"source_type": "community"}

    results = collection.query(
        query_texts=[query],
        n_results=k,
        where=where_filter,
    )

    output = []
    if results and results.get("ids") and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            doc_id = results["ids"][0][i]
            document = None
            if results.get("documents") and results["documents"][0]:
                document = results["documents"][0][i]
            metadata = {}
            if results.get("metadatas") and results["metadatas"][0]:
                metadata = results["metadatas"][0][i]
            distance = 0.0
            if results.get("distances") and results["distances"][0]:
                distance = results["distances"][0][i]

            score = 1.0 / (1.0 + distance)

            output.append({
                "id": doc_id,
                "content": document,
                "metadata": metadata,
                "distance": distance,
                "score": round(score, 4),
            })

    return output


def get_collection_count(collection) -> int:
    try:
        return collection.count()
    except Exception:
        return 0
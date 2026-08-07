import os
import numpy as np
import faiss
import pickle


def create_faiss_index(embeddings: list):
    if not embeddings:
        raise ValueError("No embeddings were generated.")

    vectors = np.array(embeddings, dtype="float32")

    print("Embeddings shape:", vectors.shape)

    if vectors.ndim != 2:
        raise ValueError(
            f"Invalid embeddings shape: {vectors.shape}. "
            "Expected a 2D array."
        )

    if vectors.shape[0] == 0:
        raise ValueError("Embedding array is empty.")

    dim = vectors.shape[1]

    index = faiss.IndexFlatL2(dim)
    index.add(vectors)

    return index


def save_faiss_index(index, session_id: str, document_id: str):
    folder = os.path.join(
        "faiss_index",
        session_id,
        document_id
    )

    os.makedirs(folder, exist_ok=True)

    file_path = os.path.join(
        folder,
        "index.faiss"
    )

    faiss.write_index(index, file_path)


def load_faiss_index(session_id: str, document_id: str):
    file_path = os.path.join(
        "faiss_index",
        session_id,
        document_id,
        "index.faiss"
    )

    if not os.path.exists(file_path):
        raise FileNotFoundError(
            "No FAISS index found for this document."
        )

    return faiss.read_index(file_path)


def save_chunks(
    chunks,
    session_id: str,
    document_id: str
):
    folder = os.path.join(
        "faiss_index",
        session_id,
        document_id
    )

    os.makedirs(folder, exist_ok=True)

    file_path = os.path.join(
        folder,
        "chunks.pkl"
    )

    with open(file_path, "wb") as f:
        pickle.dump(chunks, f)


def load_chunks(
    session_id: str,
    document_id: str
):
    file_path = os.path.join(
        "faiss_index",
        session_id,
        document_id,
        "chunks.pkl"
    )

    if not os.path.exists(file_path):
        raise FileNotFoundError(
            "No chunks found for this document."
        )

    with open(file_path, "rb") as f:
        chunks = pickle.load(f)

    return chunks
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


def save_faiss_index(index, file_path="faiss_index/index.faiss"):
    os.makedirs("faiss_index", exist_ok=True)
    faiss.write_index(index, file_path)


def load_faiss_index(path="faiss_index/index.faiss"):
    idx = faiss.read_index(path)
    return idx


def save_chunks(chunks, path="faiss_index/chunks.pkl"):
    with open(path, "wb") as f:
        pickle.dump(chunks, f)


def load_chunks(path="faiss_index/chunks.pkl"):
    with open(path, "rb") as f:
        chunks = pickle.load(f)

    return chunks
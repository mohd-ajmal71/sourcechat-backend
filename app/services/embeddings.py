from sentence_transformers import SentenceTransformer

model = None


def get_model():
    global model

    if model is None:
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    return model


def generate_embeddings(chunks: list) -> list[list[float]]:

    model = get_model()

    embeddings = model.encode(
        chunks,
        convert_to_numpy=True,
        show_progress_bar=False
    )

    return embeddings.tolist()
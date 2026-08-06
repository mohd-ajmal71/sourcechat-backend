from langchain_google_genai import GoogleGenerativeAIEmbeddings

embedding_model = GoogleGenerativeAIEmbeddings(model="models/embedding-001")

def generate_embeddings(chunks: list[str]) -> list[list[float]]:
    embeddings = embedding_model.embed_documents(chunks) 
    return embeddings
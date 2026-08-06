import os
import numpy as np
import faiss
import pickle

def create_faiss_index(embeddings:list[list[float]]):
    vectors=np.array(embeddings).astype("float32")
    dim=vectors.shape[1]
    
    index=faiss.IndexFlatL2(dim)
    index.add(vectors)
    return index


def save_faiss_index(index,file_path="faiss_index/index.faiss"):
    os.makedirs("faiss_index",exist_ok=True)
    faiss.write_index(index,file_path)
    
    
def load_faiss_index(path="faiss_index/index.faiss"):
    idx=faiss.read_index(path)
    return idx

    
    
def save_chunks(chunks,path="faiss_index/chunks.pkl"):
    with open (path,"wb") as f:
        pickle.dump(chunks,f)

    
def load_chunks(path="faiss_index/chunks.pkl"):
    
    with open (path,"rb") as f:
        chunks=pickle.load(f)
    return chunks
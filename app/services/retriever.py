from app.services.embeddings import generate_embeddings
from app.services.vector_store import (load_faiss_index,load_chunks)
import numpy as np



def retrieve_chunks(question,k:int=3)-> list[str]:
    index=load_faiss_index()
    chunks=load_chunks()
    question_embedding=generate_embeddings([question])
    
    question_vector=np.array(question_embedding).astype("float32")
    
    distances , indices=index.search(question_vector,k)
    
    result=[]
    
    for idx in indices[0]:
        if idx != -1:
            doc=chunks[idx]
            result.append({
            "text": doc.page_content,
            "page": doc.metadata["page"],
            "source": doc.metadata["source"]})
    
    return result
import os
import shutil
from typing import Annotated
from fastapi import APIRouter,File, HTTPException,UploadFile
from app.services.pdf_loader import load_pdf
from app.services.chunking import chunk_text
from app.services.embeddings import generate_embeddings
from app.services.vector_store import create_faiss_index,save_faiss_index,save_chunks


router=APIRouter()

@router.post("/upload")
async def upload_file(files: Annotated[list[UploadFile], File(...)]):
    
    # delete all files in uploads
    if os.path.exists("uploads"):
        for file in os.listdir("uploads"):
            file_path = os.path.join("uploads", file)
            if os.path.isfile(file_path):
                os.remove(file_path)
                
                
    # Delete all files in faiss_index/
    if os.path.exists("faiss_index"):
        for file in os.listdir("faiss_index"):
            file_path = os.path.join("faiss_index", file)
            if os.path.isfile(file_path):
                os.remove(file_path)
    
    for file in files:
        if file.content_type !="application/pdf":
            raise HTTPException(
             status_code=400,detail="Onky pdf can be uploaded"
             )
   
        saved_file=f"uploads/{file.filename}"
        os.makedirs("uploads", exist_ok=True)
        with open(saved_file,"wb") as buffer:
            shutil.copyfileobj(file.file,buffer)
            
            
        documents = load_pdf(saved_file)
        chunks = chunk_text(documents)
        texts = [doc.page_content for doc in chunks]
        embeddings = generate_embeddings(texts)
        
        
        index=create_faiss_index(embeddings)
        save_faiss_index(index)
        save_chunks(chunks)
        
    
    return {"message": f"{len(files)} PDFs uploaded successfully"}
   
    
        

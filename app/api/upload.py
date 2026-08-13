import os
import shutil
import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.pdf_loader import load_pdf
from app.services.chunking import chunk_text
from app.services.embeddings import generate_embeddings

from app.services.vector_store import create_faiss_index, save_faiss_index, save_chunks


router = APIRouter()


@router.post("/upload")
async def upload_file(
    session_id: str,
    files: Annotated[list[UploadFile], File(...)]
):

    if not session_id:
        raise HTTPException(
            status_code=400,
            detail="Session ID is required."
        )

    if not files:
        raise HTTPException(
            status_code=400,
            detail="No files uploaded."
        )

    document_ids = []

    print("================================")
    print("SESSION ID:", session_id)
    print("================================")

    for file in files:

        if file.content_type != "application/pdf":
            raise HTTPException(
                status_code=400,
                detail="Only PDF files can be uploaded."
            )

        # Create a unique ID for this uploaded document
        document_id = str(uuid.uuid4())

        print("DOCUMENT ID:", document_id)

        # Create a separate folder for this document
        upload_folder = os.path.join(
            "uploads",
            session_id,
            document_id
        )

        os.makedirs(
            upload_folder,
            exist_ok=True
        )

        saved_file = os.path.join(
            upload_folder,
            file.filename
        )

        with open(saved_file, "wb") as buffer:
            shutil.copyfileobj(
                file.file,
                buffer
            )

        print("Saved file:", saved_file)

        # Load PDF
        documents = load_pdf(saved_file)

        # Split PDF into chunks
        chunks = chunk_text(documents)

        print(
            "Chunks generated:",
            len(chunks)
        )

        # Extract text
        texts = [
            doc.page_content
            for doc in chunks
        ]

        print(
            "Total chunks:",
            len(texts)
        )

        # Generate Gemini embeddings
        embeddings = generate_embeddings(texts)

        print(
            "Total embeddings:",
            len(embeddings)
        )

        # Create FAISS index
        index = create_faiss_index(
            embeddings
        )

        # Save index for THIS session + document
        save_faiss_index(
            index,
            session_id,
            document_id
        )

        # Save chunks for THIS session + document
        save_chunks(
            chunks,
            session_id,
            document_id
        )

        document_ids.append(document_id)

        print("Upload completed successfully.")
        print("Session ID:", session_id)
        print("Document ID:", document_id)

    print("================================")
    print("ALL DOCUMENT IDs:", document_ids)
    print("================================")

    return {
        "message": f"{len(files)} PDFs uploaded successfully",
        "session_id": session_id,
        "document_ids": document_ids,
        "files": [
            file.filename
            for file in files
        ]
    }
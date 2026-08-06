from fastapi import APIRouter
from pydantic import BaseModel
from app.services.retriever import retrieve_chunks
from app.services.llm import generate_answer

router = APIRouter()


class ChatRequest(BaseModel):
    question: str


@router.post("/chat")
async def chat(request: ChatRequest):

    chunks = retrieve_chunks(request.question)

    context = "\n\n".join(
        chunk["text"] for chunk in chunks
    )

    answer = generate_answer(
        question=request.question,
        context=context
    )

    unique_sources = []
    seen = set()

    for chunk in chunks:
        key = (chunk["source"], chunk["page"])
        if key not in seen:
            seen.add(key)
            unique_sources.append(
            {
                "page": chunk["page"],
                "source": chunk["source"]
            }
        )

    return {
    "answer": answer,
    "sources": unique_sources}
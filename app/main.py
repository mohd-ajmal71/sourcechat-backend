from fastapi import FastAPI

from app.api.upload import router as upload_router
from app.api.chat import router as chat_router
from app.api.pdf_verifier import router as pdf_verifier_router
from app.api.image_verifier import router as image_verifier_router


app = FastAPI(openapi_version="3.0.3")

app.include_router(upload_router)
app.include_router(chat_router)
app.include_router(pdf_verifier_router)
app.include_router(image_verifier_router)


@app.get("/")
def home():
    return {"Message": "Backend is running"}
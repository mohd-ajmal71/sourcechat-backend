
import json
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.image_analyzer import (
    MAX_IMAGE_SIZE,
    analyze_image,
    validate_image_bytes
)


router = APIRouter(
    prefix="/image-verifier",
    tags=["Image Verifier"]
)


@router.post("/verify")
async def verify_image(
    file: UploadFile = File(...),
    session_id: str = Form(...)
):
    try:
        session_id = str(UUID(session_id))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid session ID."
        )

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Image filename is missing."
        )

    filename = file.filename.replace("\\", "/").split("/")[-1]
    extension = Path(filename).suffix.lower()

    if extension not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(
            status_code=400,
            detail="Only JPG, JPEG, PNG and WEBP images are supported."
        )

    image_bytes = await file.read(MAX_IMAGE_SIZE + 1)
    await file.close()

    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Image size must not exceed 10 MB."
        )

    try:
        mime_type = validate_image_bytes(
            image_bytes,
            extension
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    document_id = str(uuid4())

    upload_dir = (
        Path("uploads")
        / session_id
        / document_id
    )

    result_dir = (
        Path("verifier_results")
        / session_id
        / document_id
    )

    upload_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    result_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    file_path = upload_dir / filename
    file_path.write_bytes(image_bytes)

    try:
        verification_report = analyze_image(
            str(file_path)
        )

        verification_report["metadata"] = {
            "filename": filename,
            "mime_type": mime_type,
            "file_size_bytes": len(image_bytes)
        }

        result_path = result_dir / "verification.json"

        with open(
            result_path,
            "w",
            encoding="utf-8"
        ) as result_file:
            json.dump(
                verification_report,
                result_file,
                indent=4,
                ensure_ascii=False
            )

        return {
            "message": "Image verification completed successfully",
            "session_id": session_id,
            "document_id": document_id,
            "filename": filename,
            "verification_report": verification_report
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Image verification failed: {str(error)}"
        )

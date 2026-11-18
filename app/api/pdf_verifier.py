
import os
import uuid
import json
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.pdf_analyzer import analyze_pdf
from app.services.pdf_risk_assessor import assess_copyright_risk


router = APIRouter(prefix="/verifier", tags=["Verifier"])


@router.post("/verify")
async def verify_pdf(
    session_id: str = Form(...),
    file: UploadFile = File(...)
):
    try:
        try:
            uuid.UUID(session_id)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid session ID"
            )

        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="Filename is required"
            )

        filename = os.path.basename(
            file.filename.replace("\\", "/")
        )

        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are allowed"
            )

        document_id = str(uuid.uuid4())

        upload_dir = (
            Path("uploads") / session_id / document_id
        )

        result_dir = (
            Path("verifier_results") / session_id / document_id
        )

        upload_dir.mkdir(parents=True, exist_ok=True)
        result_dir.mkdir(parents=True, exist_ok=True)

        file_path = upload_dir / filename

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        with open(file_path, "rb") as pdf_file:
            if b"%PDF-" not in pdf_file.read(1024):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid PDF file"
                )

        analyzer_start = time.perf_counter()

        verification_report = analyze_pdf(str(file_path))

        analyzer_time = time.perf_counter() - analyzer_start

        print(
            f"Copyright analyzer took: {analyzer_time:.2f} seconds"
        )

        gemini_start = time.perf_counter()

        risk_assessment = assess_copyright_risk(
            verification_report
        )

        gemini_time = time.perf_counter() - gemini_start

        print(
            f"Gemini assessment took: {gemini_time:.2f} seconds"
        )

        verification_report["risk_assessment"] = risk_assessment

        result_path = result_dir / "verification.json"

        with open(result_path, "w", encoding="utf-8") as result_file:
            json.dump(
                verification_report,
                result_file,
                indent=4,
                ensure_ascii=False,
                default=str
            )

        return {
            "message": "PDF verification completed successfully",
            "session_id": session_id,
            "document_id": document_id,
            "filename": filename,
            "verification_report": verification_report
        }

    except HTTPException:
        raise

    except Exception as e:
        print(f"Verifier error: {str(e)}")

        raise HTTPException(
            status_code=500,
            detail="PDF verification failed"
        )

    finally:
        await file.close()

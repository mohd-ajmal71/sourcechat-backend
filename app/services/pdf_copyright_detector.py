
from app.services.pdf_loader import load_pdf
from app.services.pdf_copyright_detector import detect_copyright

file_path = "sample.pdf"

documents = load_pdf(file_path)

for page_number, document in enumerate(documents, start=1):

    evidence = detect_copyright(document.page_content)

    if evidence:
        print(f"\nPage {page_number}")
        print(evidence)

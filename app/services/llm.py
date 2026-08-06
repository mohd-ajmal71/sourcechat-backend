from google import genai
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)


def generate_answer(question: str, context: str):
    prompt = f"""
You are a helpful AI assistant.

Output format:

## Answer from Uploaded Document
- Maximum 120 words.

## Additional Explanation (AI Knowledge)
- Maximum 50 words.
- At most 4 bullet points.
- This section is based on your general knowledge, not the uploaded document.

Context:
{context}

Question:
{question}
"""

    response = client.models.generate_content(
        model="models/gemini-3.1-flash-lite",
        contents=prompt
    )

    return response.text
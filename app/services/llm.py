import google.generativeai as genai
from dotenv import load_dotenv
import os

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel("gemini-flash-latest")

def generate_answer(question: str, context: str):
    prompt = f"""
You are a helpful AI assistant.

Output format:

## Answer from Uploaded Document
- Maximum 120 words.

## Additional Explanation (AI Knowledge)
- Maximum 50 words.
- At most 4 bullet points.

Context:
{context}

Question:
{question}
"""

    response = model.generate_content(prompt)

    return response.text

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(
        api_version="v1beta"
    )
)

MODEL_NAME = "gemini-flash-lite-latest"


class GeminiModel:

    def generate_content(self, prompt, generation_config=None):
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=generation_config
        )

        return response


model = GeminiModel()


def generate_answer(question: str, context: str):

    prompt = f"""
You are a helpful AI assistant.

Answer the user's question using the uploaded document context.

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


import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(override=True)

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found")

client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(
        api_version="v1beta"
    )
)

model_name = "gemini-flash-lite-latest"

print(f"Testing Flash Lite model: {model_name}")

start_time = time.perf_counter()

try:
    response = client.models.generate_content(
        model=model_name,
        contents="Reply with exactly one word: OK",
        config={
            "temperature": 0,
            "max_output_tokens": 100
        }
    )

    elapsed_time = time.perf_counter() - start_time

    print("\nGemini response:")
    print(response.text)

    print(f"\nResponse time: {elapsed_time:.2f} seconds")

    if response.usage_metadata:
        print("\nToken usage:")
        print(response.usage_metadata)

except Exception as e:
    elapsed_time = time.perf_counter() - start_time

    print(f"\nGemini request failed: {e}")
    print(f"Time before failure: {elapsed_time:.2f} seconds")

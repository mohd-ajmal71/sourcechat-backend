
import time

from app.services.llm import model


prompt = """
Return only this JSON:
{"status": "ok"}
"""

print("Sending a small test request to Gemini...")

start_time = time.perf_counter()

try:
    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0,
            "max_output_tokens": 20,
            "response_mime_type": "application/json"
        }
    )

    elapsed_time = time.perf_counter() - start_time

    print("\nGemini response:")
    print(response.text)

    print(f"\nGemini response time: {elapsed_time:.2f} seconds")

    if response.usage_metadata:
        print("\nToken usage:")
        print(response.usage_metadata)

except Exception as e:
    elapsed_time = time.perf_counter() - start_time

    print(f"\nGemini request failed: {e}")
    print(f"Time before failure: {elapsed_time:.2f} seconds")

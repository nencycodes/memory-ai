import os
from google import genai

print("API key found:", bool(os.getenv("GEMINI_API_KEY")))

try:
    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents="Say exactly: MEMORY AI CONNECTED"
    )

    print("\nSUCCESS!")
    print(response.text)

except Exception as e:
    print("\nGEMINI ERROR:")
    print(type(e).__name__)
    print(e)
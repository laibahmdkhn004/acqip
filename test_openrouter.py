# test_openrouter.py
import os
from litellm import completion
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('OPENROUTER_API_KEY')
print(f"API Key length: {len(api_key) if api_key else 0}")
print(f"API Key starts with: {api_key[:10] if api_key else 'None'}")

try:
    response = completion(
        model="openrouter/openai/gpt-4o-mini",
        messages=[{"role": "user", "content": "Hello"}],
        api_key=api_key,
        max_tokens=10
    )
    print("API Key is valid!")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"API Key is invalid: {e}")
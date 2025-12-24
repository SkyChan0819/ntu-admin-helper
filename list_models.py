
import google.generativeai as genai
import os
from config import GEMINI_API_KEY

if not GEMINI_API_KEY:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("No API Key found. Please set GEMINI_API_KEY in config.py or environment.")
else:
    genai.configure(api_key=GEMINI_API_KEY)
    print("Available models:")
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(m.name)
    except Exception as e:
        print(f"Error listing models: {e}")

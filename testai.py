import google.generativeai as genai

# Copy the key directly from AI Studio - don't type it manually!
genai.configure(api_key="")

print("--- AVAILABLE MODELS ---")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(m.name)
except Exception as e:
    print(f"Error checking models: {e}")

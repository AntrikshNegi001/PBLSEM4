
import google.generativeai as genai

# ---------------------------------------------------------
# 👇 PASTE YOUR API KEY HERE
API_KEY = "AIzaSyBeIBMSmrP9IoPp6ZwT9gE4CswuMEFdCOw"
# ---------------------------------------------------------

try:
    genai.configure(api_key=API_KEY)
    
    print("Checking for available models...\n")
    print(f"{'Model Name':<30} | {'Description'}")
    print("-" * 60)
    
    # List all models
    for m in genai.list_models():
        # We only care about models that can generate content (text/chat)
        if 'generateContent' in m.supported_generation_methods:
            print(f"{m.name:<30} | {m.display_name}")

except Exception as e:
    print(f"\n❌ Error: {e}")
    print("Check if your API Key is correct and has internet access.")
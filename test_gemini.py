# Example using Python SDK
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# Configure API key (using environment variable is better)
genai.configure(api_key="AIzaSyBg7txhTF786IxZffdr8VEENMT-r5f9kCA")

model = genai.GenerativeModel(model_name='gemini-2.5-flash')

# Text generation
response = model.generate_content("What are the main benefits of the Gemini 3 Flash API?")
print(response.text)

# Chat (multi-turn)
chat = model.start_chat(history=[])
chat.send_message("Hi, tell me a fun fact about space.")
print(chat.last.text)



import os
import shutil
import warnings
import hashlib
from functools import lru_cache
warnings.filterwarnings("ignore")

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel
from PIL import Image
from pdf2docx import Converter
import google.generativeai as genai


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# In-memory cache for chatbot responses
response_cache = {}
MAX_CACHE_SIZE = 100  # Limit cache to 100 entries

active_model = None

try:
    genai.configure(api_key=GEMINI_API_KEY)
    

    print("🔄 Checking available models...")
    available_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            available_models.append(m.name)
    

    target_models = ["models/gemini-1.5-flash", "models/gemini-pro", "models/gemini-1.5-pro"]
    selected_model_name = None


    for target in target_models:
        if target in available_models:
            selected_model_name = target
            break
    

    if not selected_model_name and available_models:
        selected_model_name = available_models[0]

    if selected_model_name:
        print(f"✅ Selected Model: {selected_model_name}")
        active_model = genai.GenerativeModel(selected_model_name)
    else:
        print("🔴 No supported models found for this API Key.")

except Exception as e:
    print(f"🔴 Setup Error: {e}")

app = FastAPI()

# Add compression middleware for faster responses
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("temp_uploads", exist_ok=True)
os.makedirs("temp_outputs", exist_ok=True)



def get_cache_key(message: str) -> str:
    """Generate a cache key from the message"""
    return hashlib.md5(message.lower().strip().encode()).hexdigest()


def get_ai_response(user_message):
    if not active_model:
        return "Server Error: No AI model available."

    # Check cache first
    cache_key = get_cache_key(user_message)
    if cache_key in response_cache:
        print(f"✅ Cache hit for: {user_message[:30]}...")
        return response_cache[cache_key]

    try:
        
        prompt = f"""
        You are the AI assistant for Senal Ridmila's Personal Portfolio.
        Your goal is to answer visitor questions in a friendly, "Singlish" (Sinhala words in English) style.
        
        --- SENAL'S DATA (KNOWLEDGE BASE) ---
        
        1. WHO IS SENAL?
           - Name: Senal Ridmila
           - Role: Undergraduate Student & Full Stack Developer
           - Education: BSc (Hons) in Network and Mobile Computing at Horizon Campus.
           - Passion: Software development, working under pressure, and learning new tech.
           
        2. SKILLS (Mewa gana ahuwoth kiyanna):
           - Languages: Java (OOP), JavaScript, Python, PHP
           - Frameworks: Spring Boot, React.js, Next.js, Node.js, React Native (Expo)
           - Databases: MySQL, MongoDB
           - Tools: Docker, Git, VS Code, Firebase
           
        3. KEY PROJECTS (Wada karapu projects):
           - Ayurveda Wellness App: A mobile app for connecting patients with Ayurvedic doctors (React Native, Firebase).
           - Pet Toy Shop: E-commerce platform built with Spring Boot, React, and MongoDB (Full Stack).
           - Car Rental System: Java Swing and MySQL based system for managing rentals.
           - Virtual Fitting App: A virtual try-on experience using Next.js and Tailwind CSS.
           - SLT Tire Management: Tire request system using React and Java.
           
        4. CONTACT DETAILS:
           - Phone: +94 781304930 , +9477 1304930
           - Email: senalridmila2@gmail.com
           - LinkedIn: linkedin.com/in/senal-ridmila-98b996292
           - GitHub: github.com/SenalRidmila

        --- GUIDELINES FOR ANSWERING ---
        
        1. Tone: Friendly, casual, and helpful. Use Singlish words like "Kohomada", "Ow", "Puluwan", "Thiyenawa", "Hari".
        2. If user says "Hi" or "Hello": Reply "Hi! Kohomada? Senal gana wisthara ona nam ahanna."
        3. If asked about "Skills": Mention his Java, React, and Spring Boot skills mainly.
        4. If asked about "Education": Say he is studying at Horizon Campus.
        5. If asked about "Contact": Give the email and LinkedIn link.
        6. Keep answers short (max 2-3 sentences). Don't write long essays.

        --- CONVERSATION ---
        User: {user_message}
        AI:
        """

        response = active_model.generate_content(prompt)
        
        if response and response.text:
            reply = response.text.strip()
            
            # Cache the response
            if len(response_cache) >= MAX_CACHE_SIZE:
                # Remove oldest entry (simple FIFO)
                response_cache.pop(next(iter(response_cache)))
            response_cache[cache_key] = reply
            print(f"💾 Cached response for: {user_message[:30]}...")
            
            return reply
        else:
            return "Samawenna, mata kiyanna deyak hithaganna ba."

    except Exception as e:
        print(f"🔴 Gemini Error: {e}")
        return "Samawenna, podi aulak. Internet connection eka balanna."




class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    reply = get_ai_response(request.message)
    return {"reply": reply}



@app.post("/tools/img-to-pdf")
async def img_to_pdf(file: UploadFile = File(...)):
    try:
        input_path = f"temp_uploads/{file.filename}"
        output_filename = f"{file.filename.split('.')[0]}.pdf"
        output_path = f"temp_outputs/{output_filename}"
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        image = Image.open(input_path)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        image.save(output_path)
        return FileResponse(output_path, filename=output_filename, media_type='application/pdf')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tools/pdf-to-word")
async def pdf_to_word(file: UploadFile = File(...)):
    try:
        input_path = f"temp_uploads/{file.filename}"
        output_filename = f"{file.filename.split('.')[0]}.docx"
        output_path = f"temp_outputs/{output_filename}"
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        cv = Converter(input_path)
        cv.convert(output_path, start=0, end=None)
        cv.close()
        return FileResponse(output_path, filename=output_filename, media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def home():
    return {"message": "Chatbot Backend is Running!"}
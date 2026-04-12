import os
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import google.generativeai as genai
from PIL import Image

app = Flask(__name__)
CORS(app)

# Secure API setup with validation
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")

# Validate API keys
if not GEMINI_API_KEY:
    print("❌ CRITICAL: GEMINI_API_KEY missing!")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-3-flash-preview")

def get_weather(city="Chennai"):
    """Get current weather data for disease risk assessment"""
    if not WEATHER_API_KEY:
        print("⚠️ Weather API key missing, using defaults")
        return 25, 60  # Default fallback: 25°C, 60% humidity
    
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        res = requests.get(url, timeout=5).json()
        temp = res['main']['temp']
        humidity = res['main']['humidity']
        return temp, humidity
    except Exception as e:
        print(f"⚠️ Weather API error: {e}, using defaults")
        return 25, 60  # Fallback values

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/predict", methods=["POST"])
def predict():
    try:
        print("--- NEW REQUEST RECEIVED ---")
        
        if 'image' not in request.files:
            return jsonify({"error": "No image uploaded"}), 400

        # Get city and language from form
        city = request.form.get("city", "Chennai").strip()
        language = request.form.get("language", "English").strip()
        
        print(f"📍 City: {city}, 🌐 Language: {language}")

        file = request.files["image"]
        img = Image.open(file)

        # Get real-time weather for ANY city
        temp, humidity = get_weather(city)
        weather_context = f"Current conditions in {city}: Temperature {temp}°C, Humidity {humidity}%"

        # Multi-language, weather-aware prompt
        prompt = f"""
Analyze this plant image for disease detection.

WEATHER CONTEXT ({city}):
{weather_context}

Return EXACTLY in this format (Respond in {language}):
Disease Name: [name]
Organic Solution: [solution]  
Chemical Solution: [solution]
Risk Level: [LOW/MEDIUM/HIGH]

Guidelines for Risk Level:
- Humidity >70% + fungal symptoms = HIGH risk
- Temperature >30°C + bacterial spots = MEDIUM risk  
- Optimal conditions = LOW risk

Current insight: {humidity}% humidity and {temp}°C affects disease progression
"""

        response = model.generate_content([prompt, img])
        
        if not response.text:
            return jsonify({
                "disease": "Healthy", 
                "solution": "No issues found.",
                "weather": weather_context,
                "risk": "LOW",
                "insight": "Perfect growing conditions detected",
                "city": city
            })

        # BULLETPROOF parsing (handles ANY AI formatting)
        lines = [line.strip() for line in response.text.strip().split('\n') if line.strip()]
        
        disease_name = "Healthy"
        organic = "N/A"
        chemical = "N/A" 
        risk_level = "LOW"
        
        for line in lines:
            line_lower = line.lower()
            if "disease" in line_lower:
                disease_name = line.split(":", 1)[-1].strip()
            elif "organic" in line_lower:
                organic = line.split(":", 1)[-1].strip()
            elif "chemical" in line_lower or "fungicide" in line_lower:
                chemical = line.split(":", 1)[-1].strip()
            elif "risk" in line_lower:
                risk_level = line.split(":", 1)[-1].strip().upper()

        insight = f"Based on {humidity}% humidity and {temp}°C in {city}, disease risk is {risk_level}"

        return jsonify({
            "disease": disease_name,
            "organic": organic,
            "chemical": chemical,
            "risk": risk_level,
            "weather": weather_context,
            "insight": insight,
            "city": city,
            "solution": f"🌿 ORGANIC: {organic} | 🧪 CHEMICAL: {chemical} | ⚠️ RISK: {risk_level}"
        })

    except Exception as e:
        print(f"❌ DEBUG ERROR: {e}")
        return jsonify({
            "error": "AI Processing Error. Check API Keys.", 
            "weather": "Weather data unavailable"
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)  # 🚫 NO DEBUG=True
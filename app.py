import os
import requests
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
import google.generativeai as genai
from PIL import Image
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import io

app = Flask(__name__)
CORS(app)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-3-flash-preview")

def get_weather(city):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        res = requests.get(url, timeout=5).json()
        return res['main']['temp'], res['main']['humidity']
    except:
        return 25, 60

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/predict", methods=["POST"])
def predict():
    try:
        file = request.files["image"]
        img = Image.open(file)

        city = request.form.get("city", "Chennai")
        language = request.form.get("language", "English")

        temp, humidity = get_weather(city)

        prompt = f"""
Analyze plant disease.

Weather: {temp}°C, {humidity}% humidity in {city}

Respond in {language}:

Disease Name:
Organic Solution:
Chemical Solution:
Risk Level:
"""

        response = model.generate_content([prompt, img])
        text = response.text if response.text else ""

        lines = text.split("\n")

        def extract(key):
            for l in lines:
                if key.lower() in l.lower():
                    return l.split(":",1)[-1].strip()
            return "N/A"

        disease = extract("Disease")
        organic = extract("Organic")
        chemical = extract("Chemical")
        risk = extract("Risk").upper()

        return jsonify({
            "disease": disease,
            "organic": organic,
            "chemical": chemical,
            "risk": risk,
            "weather": f"{temp}°C, {humidity}%",
            "solution": f"🌿 {organic} | 🧪 {chemical} | ⚠️ {risk}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/download-report", methods=["POST"])
def download_report():
    data = request.json

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()

    story = []
    story.append(Paragraph(f"Disease: {data['disease']}", styles['Title']))
    story.append(Spacer(1,10))
    story.append(Paragraph(data['solution'], styles['BodyText']))

    doc.build(story)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name="report.pdf", mimetype='application/pdf')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
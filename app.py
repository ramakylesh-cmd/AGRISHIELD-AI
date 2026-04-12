import os
import requests
import io
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from google import genai
from google.genai import types
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)
CORS(app)

# ✅ API KEYS
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")

if not GEMINI_API_KEY:
    raise Exception("❌ CRITICAL: GEMINI_API_KEY environment variable missing!")

# ✅ GENAI CLIENT (NEW SDK)
client = genai.Client(api_key=GEMINI_API_KEY)

# ✅ WEATHER FUNCTION
def get_weather(city):
    try:
        if not WEATHER_API_KEY:
            return 25, 60
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        res = requests.get(url, timeout=5).json()
        if 'main' not in res:
            return 25, 60
        return res['main']['temp'], res['main']['humidity']
    except Exception as e:
        print(f"⚠️ Weather error: {e}")
        return 25, 60

# ✅ HOME ROUTE
@app.route("/")
def home():
    return render_template("index.html")

# ✅ PREDICT ROUTE
@app.route("/predict", methods=["POST"])
def predict():
    try:
        if 'image' not in request.files:
            return jsonify({"error": "No image uploaded"}), 400

        file = request.files["image"]
        img_bytes = file.read()
        mime_type = file.mimetype or "image/jpeg"

        city = request.form.get("city", "Chennai").strip()
        language = request.form.get("language", "English").strip()

        temp, humidity = get_weather(city)

        prompt = f"""
Analyze this plant image for disease detection.
Weather in {city}: {temp}°C, {humidity}% humidity

Respond in {language} ONLY in this exact format (no extra text):
Disease Name: [name or Healthy]
Organic Solution: [solution]
Chemical Solution: [solution]
Risk Level: [LOW or MEDIUM or HIGH]
"""

        image_part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[prompt, image_part]
        )

        text = response.text if response.text else ""
        lines = text.strip().split("\n")

        def extract(key):
            for line in lines:
                if key.lower() in line.lower():
                    return line.split(":", 1)[-1].strip()
            return "N/A"

        disease = extract("Disease")
        organic = extract("Organic")
        chemical = extract("Chemical")
        risk = extract("Risk").upper()

        if risk not in ["LOW", "MEDIUM", "HIGH"]:
            risk = "MEDIUM"

        insight = f"Based on {humidity}% humidity and {temp}°C in {city}, disease risk is {risk}"

        return jsonify({
            "disease": disease,
            "organic": organic,
            "chemical": chemical,
            "risk": risk,
            "weather": f"{temp}°C, {humidity}%",
            "insight": insight,
            "city": city,
            "solution": f"🌿 {organic} | 🧪 {chemical} | ⚠️ {risk}"
        })

    except Exception as e:
        print(f"🔥 REAL ERROR: {e}")
        return jsonify({"error": str(e)}), 500

# ✅ PDF DOWNLOAD ROUTE
@app.route("/download-report", methods=["POST"])
def download_report():
    try:
        data = request.json
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("AgriShield AI - Crop Health Report", styles['Title']))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"<b>City:</b> {data.get('city', 'N/A')}", styles['BodyText']))
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>Disease:</b> {data.get('disease', 'N/A')}", styles['BodyText']))
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>Risk Level:</b> {data.get('risk', 'N/A')}", styles['BodyText']))
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>Weather:</b> {data.get('weather', 'N/A')}", styles['BodyText']))
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>Insight:</b> {data.get('insight', 'N/A')}", styles['BodyText']))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"<b>Organic Solution:</b> {data.get('organic', 'N/A')}", styles['BodyText']))
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>Chemical Solution:</b> {data.get('chemical', 'N/A')}", styles['BodyText']))

        doc.build(story)
        buffer.seek(0)

        city_name = data.get('city', 'report').replace(' ', '_')
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"AgriShield_{city_name}.pdf",
            mimetype='application/pdf'
        )

    except Exception as e:
        print(f"🔥 PDF Error: {e}")
        return jsonify({"error": str(e)}), 500

# ✅ RENDER SAFE RUN
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
import os
import requests
import io
import base64
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from groq import Groq
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)
CORS(app)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")

if not GROQ_API_KEY:
    raise Exception("❌ CRITICAL: GROQ_API_KEY environment variable missing!")

client = Groq(api_key=GROQ_API_KEY)

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

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/predict", methods=["POST"])
def predict():
    try:
        if 'image' not in request.files:
            return jsonify({"error": "No image uploaded"}), 400

        file = request.files["image"]
        img_bytes = file.read()
        mime_type = file.mimetype or "image/jpeg"
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        image_url = f"data:{mime_type};base64,{img_b64}"

        city = request.form.get("city", "Chennai").strip()
        language = request.form.get("language", "English").strip()

        temp, humidity = get_weather(city)

        prompt = f"""You are an expert plant pathologist AI. Analyze this plant image carefully.
Weather in {city}: {temp}°C, {humidity}% humidity

CRITICAL INSTRUCTION: You MUST respond ENTIRELY in {language} language. Every single word of your response must be in {language}. Do not use English if {language} is not English.

Respond ONLY in this exact format with NO extra text:
Disease Name: [name in {language}]
Organic Solution: [solution in {language}]
Chemical Solution: [solution in {language}]
Risk Level: [LOW or MEDIUM or HIGH]
Confidence: [number between 60 and 99]
Severity: [number between 1 and 10]"""

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": prompt}
                    ]
                }
            ],
            max_tokens=600,
            temperature=0.2
        )

        text = response.choices[0].message.content or ""
        print(f"🤖 Groq response: {text}")
        lines = text.strip().split("\n")

        def extract(key):
            for line in lines:
                if key.lower() in line.lower():
                    return line.split(":", 1)[-1].strip()
            return "N/A"

        disease  = extract("Disease")
        organic  = extract("Organic")
        chemical = extract("Chemical")
        risk     = extract("Risk").upper()
        
        # Parse confidence and severity as numbers
        try:
            confidence = int(''.join(filter(str.isdigit, extract("Confidence"))))
            confidence = max(60, min(99, confidence))
        except:
            confidence = 75
            
        try:
            severity = int(''.join(filter(str.isdigit, extract("Severity"))))
            severity = max(1, min(10, severity))
        except:
            severity = 5

        if risk not in ["LOW", "MEDIUM", "HIGH"]:
            risk = "MEDIUM"

        insight = f"Based on {humidity}% humidity and {temp}°C in {city}, disease risk is {risk}"

        return jsonify({
            "disease": disease,
            "organic": organic,
            "chemical": chemical,
            "risk": risk,
            "confidence": confidence,
            "severity": severity,
            "weather": f"{temp}°C, {humidity}%",
            "insight": insight,
            "city": city,
            "solution": f"🌿 {organic} | 🧪 {chemical} | ⚠️ {risk}"
        })

    except Exception as e:
        print(f"🔥 REAL ERROR: {e}")
        return jsonify({"error": str(e)}), 500

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
        story.append(Paragraph(f"<b>Confidence:</b> {data.get('confidence', 'N/A')}%", styles['BodyText']))
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>Severity:</b> {data.get('severity', 'N/A')}/10", styles['BodyText']))
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
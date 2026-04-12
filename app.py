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

# ✅ API KEYS
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")

if not GROQ_API_KEY:
    raise Exception("❌ CRITICAL: GROQ_API_KEY environment variable missing!")

# ✅ GROQ CLIENT
client = Groq(api_key=GROQ_API_KEY)


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

        # ✅ Convert image to base64 for Groq
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        image_url = f"data:{mime_type};base64,{img_b64}"

        city = request.form.get("city", "Chennai").strip()
        language = request.form.get("language", "English").strip()

        temp, humidity = get_weather(city)

        prompt = f"""You are an expert plant pathologist AI.
Analyze this plant image carefully for any disease or health issues.
Weather context in {city}: Temperature {temp}°C, Humidity {humidity}%

Respond in {language} ONLY in this EXACT format, nothing else:
Disease Name: [name or Healthy]
Organic Solution: [specific organic treatment]
Chemical Solution: [specific chemical treatment]
Risk Level: [LOW or MEDIUM or HIGH]"""

        # ✅ GROQ API CALL WITH IMAGE
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url}
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ],
            max_tokens=500,
            temperature=0.1  # ✅ low temp = more structured output
        )

        text = response.choices[0].message.content or ""
        print(f"🤖 Groq response: {text}")
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

        # ✅ Sanitize risk
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
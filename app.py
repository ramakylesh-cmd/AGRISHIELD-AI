import os
import requests
import base64
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from google import genai
from google.genai import types
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import green, black, red
from reportlab.lib.units import inch
from datetime import datetime
import io

app = Flask(__name__)
CORS(app)

# Secure API setup with validation
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")

if not GEMINI_API_KEY:
    raise Exception("❌ CRITICAL: GEMINI_API_KEY environment variable missing!")

# ✅ NEW SDK - correct client init
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-2.5-flash-preview-04-17"  # ✅ Use this; swap to gemini-3-flash-preview when stable


def get_weather(city="Chennai"):
    """Get current weather data - BULLETPROOF"""
    if not WEATHER_API_KEY:
        print("⚠️ Weather API key missing, using defaults")
        return 25, 60

    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        res = requests.get(url, timeout=5).json()

        if 'main' not in res or 'temp' not in res['main']:
            print("⚠️ Invalid weather response, using defaults")
            return 25, 60

        temp = res['main']['temp']
        humidity = res['main']['humidity']
        return temp, humidity
    except Exception as e:
        print(f"⚠️ Weather API error: {e}, using defaults")
        return 25, 60


def draw_multiline_text(c, text, x, y, max_width=400, line_height=14):
    """Handle long text with word wrapping"""
    words = text.split()
    current_line = ""
    lines = []

    for word in words:
        test_line = current_line + word + " "
        if c.stringWidth(test_line, "Helvetica", 11) < max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line.strip())
            current_line = word + " "

    if current_line:
        lines.append(current_line.strip())

    for i, line in enumerate(lines):
        c.drawString(x, y - (i * line_height), line)


def generate_pdf_report(data):
    """Generate professional PDF report"""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Header
    c.setFillColor(green)
    c.rect(0.75 * inch, height - 1.2 * inch, 7 * inch, 0.8 * inch, fill=1)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(1 * inch, height - 0.9 * inch, "AgriShield AI - CROP HEALTH REPORT")
    c.setFont("Helvetica", 10)
    c.drawString(1 * inch, height - 1.1 * inch, "Powered by Gemini AI + OpenWeatherMap")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
    c.drawString(5.5 * inch, height - 1.1 * inch, f"Report: {timestamp}")

    y_pos = height - 2.5 * inch

    # Disease Detection
    c.setFillColor(green)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(0.75 * inch, y_pos, "DISEASE DETECTION")
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(1 * inch, y_pos - 0.3 * inch, f"Disease: {data['disease']}")

    risk_color = green if data['risk'] == 'LOW' else red if data['risk'] == 'HIGH' else black
    c.setFillColor(risk_color)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(1 * inch, y_pos - 0.7 * inch, f"RISK: {data['risk']}")

    y_pos -= 1.8 * inch

    # Weather Intelligence
    c.setFillColor(green)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(0.75 * inch, y_pos, "WEATHER INTELLIGENCE")
    c.setFillColor(black)
    c.setFont("Helvetica", 12)
    draw_multiline_text(c, data['weather'], 1 * inch, y_pos - 0.3 * inch)
    draw_multiline_text(c, data['insight'], 1 * inch, y_pos - 0.8 * inch)

    y_pos -= 1.8 * inch

    # Treatments
    c.setFillColor(green)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(0.75 * inch, y_pos, "TREATMENT RECOMMENDATIONS")

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, y_pos - 0.3 * inch, "ORGANIC SOLUTION")
    c.setFont("Helvetica", 11)
    draw_multiline_text(c, data['organic'], 1.2 * inch, y_pos - 0.6 * inch)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, y_pos - 1.4 * inch, "CHEMICAL SOLUTION")
    c.setFont("Helvetica", 11)
    draw_multiline_text(c, data['chemical'], 1.2 * inch, y_pos - 1.7 * inch)

    # Footer
    c.setFillColor(green)
    c.rect(0.75 * inch, 0.5 * inch, 7 * inch, 0.6 * inch, fill=1)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(1 * inch, 0.7 * inch, "SAVE YOUR CROPS WITH AGRISHIELD AI")
    c.setFont("Helvetica", 10)
    c.drawString(1 * inch, 0.5 * inch, "Download app | Visit agrishield.ai | Built for farmers")

    c.save()
    buffer.seek(0)
    return buffer


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/predict", methods=["POST"])
def predict():
    try:
        print("--- NEW REQUEST RECEIVED ---")

        if 'image' not in request.files:
            return jsonify({"error": "No image uploaded"}), 400

        city = request.form.get("city", "Chennai").strip()
        language = request.form.get("language", "English").strip()

        file = request.files["image"]
        img_bytes = file.read()

        # ✅ NEW SDK - convert image to base64 Part
        img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
        image_part = types.Part.from_bytes(data=img_bytes, mime_type=file.mimetype or "image/jpeg")

        temp, humidity = get_weather(city)
        weather_context = f"Current conditions in {city}: Temperature {temp}°C, Humidity {humidity}%"

        prompt = f"""
Analyze this plant image for disease detection.

WEATHER CONTEXT ({city}):
{weather_context}

Return EXACTLY in this format (Respond in {language}):
Disease Name: [name]
Organic Solution: [solution]
Chemical Solution: [solution]
Risk Level: [LOW/MEDIUM/HIGH]
"""

        # ✅ NEW SDK - correct API call
        response = client.models.generate_content(
            model=MODEL,
            contents=[prompt, image_part],
        )

        response_text = response.text if response.text else ""

        if not response_text.strip():
            data = {
                "disease": "Healthy",
                "organic": "No treatment needed",
                "chemical": "No treatment needed",
                "risk": "LOW",
                "weather": weather_context,
                "insight": "Perfect growing conditions detected",
                "city": city,
                "solution": "Healthy plant - No action required!"
            }
        else:
            lines = [line.strip() for line in response_text.strip().split('\n') if line.strip()]

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
            data = {
                "disease": disease_name,
                "organic": organic,
                "chemical": chemical,
                "risk": risk_level,
                "weather": weather_context,
                "insight": insight,
                "city": city,
                "solution": f"ORGANIC: {organic} | CHEMICAL: {chemical} | RISK: {risk_level}"
            }

        return jsonify(data)

    except Exception as e:
        print(f"🔥 REAL ERROR: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/download-report", methods=["POST"])
def download_report():
    try:
        data = request.json
        pdf_buffer = generate_pdf_report(data)

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f"agrishield_report_{data['city']}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            mimetype='application/pdf'
        )
    except Exception as e:
        print(f"PDF Error: {e}")
        return jsonify({"error": "PDF generation failed"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
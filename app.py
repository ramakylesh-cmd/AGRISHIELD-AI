import os
import re
import requests
import io
import base64
from flask import Flask, request, jsonify, render_template, send_file, send_from_directory
from flask_cors import CORS
from groq import Groq
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from datetime import datetime

app = Flask(__name__)
CORS(app)

GROQ_API_KEY    = os.environ.get("GROQ_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")

if not GROQ_API_KEY:
    raise Exception("❌ CRITICAL: GROQ_API_KEY environment variable missing!")

client = Groq(api_key=GROQ_API_KEY)


def get_weather(city: str):
    defaults = (28, 65, "Clear", 1012)
    if not WEATHER_API_KEY:
        return defaults
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        res = requests.get(url, timeout=5).json()
        if "main" not in res:
            return defaults
        return (
            round(res["main"]["temp"], 1),
            res["main"]["humidity"],
            res["weather"][0]["main"] if res.get("weather") else "Clear",
            res["main"].get("pressure", 1012)
        )
    except Exception as e:
        print(f"⚠️ Weather error: {e}")
        return defaults


def extract_field(lines, key):
    for line in lines:
        if ":" in line and key.lower() in line.lower().split(":")[0].lower():
            value = line.split(":", 1)[-1].strip()
            if value:
                return value
    return "N/A"


def safe_int(text, lo, hi, default):
    digits = re.sub(r"[^\d]", "", str(text))
    if not digits:
        return default
    return max(lo, min(hi, int(digits[:3])))


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/predict", methods=["POST", "HEAD"])
def predict():
    if request.method == "HEAD":
        return "", 200
    try:
        if "image" not in request.files:
            return jsonify({"error": "No image uploaded"}), 400

        file      = request.files["image"]
        img_bytes = file.read()
        if not img_bytes:
            return jsonify({"error": "Uploaded file is empty"}), 400

        mime_type = file.mimetype or "image/jpeg"
        img_b64   = base64.b64encode(img_bytes).decode("utf-8")
        image_url = f"data:{mime_type};base64,{img_b64}"

        city     = (request.form.get("city", "Chennai") or "Chennai").strip()
        language = (request.form.get("language", "English") or "English").strip()

        temp, humidity, condition, pressure = get_weather(city)

        prompt = f"""You are an expert plant pathologist AI. Analyze this plant image carefully.

Current weather in {city}: {temp}°C, {humidity}% humidity, {condition}, pressure {pressure} hPa.

CRITICAL: Respond ENTIRELY in {language}. Every word must be in {language}.

Reply in EXACTLY this format (no extra lines, no markdown):
Disease Name: [name]
Organic Solution: [2-3 sentence organic treatment]
Chemical Solution: [2-3 sentence chemical treatment]
Risk Level: [LOW or MEDIUM or HIGH]
Confidence: [integer 60-99]
Severity: [integer 1-10]
Crop Tip: [one short actionable farming tip based on the weather]"""

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt}
                ]
            }],
            max_tokens=700,
            temperature=0.2,
        )

        text  = (response.choices[0].message.content or "").strip()
        print(f"🤖 Groq response:\n{text}")
        lines = text.split("\n")

        disease  = extract_field(lines, "Disease Name")
        organic  = extract_field(lines, "Organic Solution")
        chemical = extract_field(lines, "Chemical Solution")
        crop_tip = extract_field(lines, "Crop Tip")

        risk_raw = extract_field(lines, "Risk Level").upper()
        if   "HIGH"   in risk_raw: risk = "HIGH"
        elif "LOW"    in risk_raw: risk = "LOW"
        else:                       risk = "MEDIUM"

        confidence = safe_int(extract_field(lines, "Confidence"), 60, 99, 75)
        severity   = safe_int(extract_field(lines, "Severity"),    1, 10,  5)

        if humidity > 70:
            risk_reason = "high humidity increases fungal spread risk"
        elif humidity < 40:
            risk_reason = "low humidity reduces fungal risk but watch for pests"
        else:
            risk_reason = "conditions are moderate — regular monitoring advised"

        insight = f"Weather in {city}: {humidity}% humidity, {temp}°C — {risk_reason}. Current risk level: {risk}."

        return jsonify({
            "disease":    disease,
            "organic":    organic,
            "chemical":   chemical,
            "risk":       risk,
            "confidence": confidence,
            "severity":   severity,
            "weather":    f"{temp}°C · {humidity}%",
            "condition":  condition,
            "pressure":   pressure,
            "humidity":   humidity,
            "temp":       temp,
            "insight":    insight,
            "crop_tip":   crop_tip,
            "city":       city,
            "timestamp":  datetime.now().strftime("%d %b %Y, %I:%M %p"),
            "solution":   f"🌿 {organic} | 🧪 {chemical}",
        })

    except Exception as e:
        print(f"🔥 ERROR in /predict: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/download-report", methods=["POST"])
def download_report():
    try:
        data   = request.json or {}
        buffer = io.BytesIO()
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle("AgriTitle", parent=styles["Title"],    fontSize=20, spaceAfter=6,  textColor=colors.HexColor("#2d7a08"))
        head_style  = ParagraphStyle("AgriHead",  parent=styles["Heading2"], fontSize=12, spaceBefore=14, spaceAfter=4, textColor=colors.HexColor("#4a8a10"))
        body_style  = ParagraphStyle("AgriBody",  parent=styles["BodyText"], fontSize=11, leading=16,    spaceAfter=4)

        doc   = SimpleDocTemplate(buffer, leftMargin=inch, rightMargin=inch, topMargin=inch, bottomMargin=inch)
        story = []

        story.append(Paragraph("🌱 AgriShield AI — Crop Health Report", title_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#4a8a10")))
        story.append(Spacer(1, 10))

        def row(label, value):
            story.append(Paragraph(f"<b>{label}:</b>  {value or 'N/A'}", body_style))

        row("Date",     data.get("timestamp"))
        row("Location", data.get("city"))
        row("Weather",  data.get("weather"))
        story.append(Spacer(1, 6))

        story.append(Paragraph("Diagnosis", head_style))
        row("Disease",       data.get("disease"))
        row("Risk Level",    data.get("risk"))
        row("AI Confidence", f"{data.get('confidence', 'N/A')}%")
        row("Severity",      f"{data.get('severity', 'N/A')}/10")
        story.append(Spacer(1, 6))

        story.append(Paragraph("Treatment", head_style))
        row("Organic",  data.get("organic"))
        row("Chemical", data.get("chemical"))
        story.append(Spacer(1, 6))

        story.append(Paragraph("Additional Info", head_style))
        row("Weather Insight", data.get("insight"))
        row("Crop Tip",        data.get("crop_tip"))

        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
        story.append(Paragraph(
            "<i>Generated by AgriShield AI — Hackathon 2026</i>",
            ParagraphStyle("Footer", parent=styles["BodyText"], fontSize=9, textColor=colors.grey, alignment=1)
        ))

        doc.build(story)
        buffer.seek(0)
        city_safe = (data.get("city") or "report").replace(" ", "_")
        return send_file(buffer, as_attachment=True,
                         download_name=f"AgriShield_{city_safe}_{datetime.now().strftime('%Y%m%d')}.pdf",
                         mimetype="application/pdf")

    except Exception as e:
        print(f"🔥 PDF Error: {e}")
        return jsonify({"error": str(e)}), 500


# ── PWA: serve manifest.json from static folder ──
@app.route("/static/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")

# ── PWA: serve service worker ──
@app.route("/static/sw.js")
def sw():
    return send_from_directory('static', 'sw.js',
                               mimetype='application/javascript')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
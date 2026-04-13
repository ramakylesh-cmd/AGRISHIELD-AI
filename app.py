import os
import re
import uuid
import json
import sqlite3
import requests
import io
import base64
import hashlib
from flask import Flask, request, jsonify, render_template, send_file, send_from_directory, session, g
from flask_cors import CORS
from groq import Groq
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "agrishield-secret-2026-change-me")
CORS(app, supports_credentials=True)

GROQ_API_KEY    = os.environ.get("GROQ_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")

if not GROQ_API_KEY:
    raise Exception("CRITICAL: GROQ_API_KEY environment variable missing!")

client = Groq(api_key=GROQ_API_KEY)

# ── DATABASE SETUP ──────────────────────────────────────────────────────────

DATABASE = "agrishield.db"

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                plan TEXT DEFAULT 'free'
            );
            CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                disease TEXT,
                organic TEXT,
                chemical TEXT,
                risk TEXT,
                confidence INTEGER,
                severity INTEGER,
                city TEXT,
                weather TEXT,
                condition TEXT,
                humidity INTEGER,
                temp REAL,
                pressure INTEGER,
                insight TEXT,
                crop_tip TEXT,
                language TEXT DEFAULT 'English',
                timestamp TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        db.commit()

init_db()

# ── AUTH HELPERS ─────────────────────────────────────────────────────────────

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

# ── AUTH ROUTES ───────────────────────────────────────────────────────────────

@app.route("/api/register", methods=["POST"])
def register():
    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "Farmer").strip()
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        return jsonify({"error": "Email already registered"}), 409
    user_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (id, email, password_hash, name) VALUES (?, ?, ?, ?)",
        (user_id, email, hash_password(password), name)
    )
    db.commit()
    session["user_id"] = user_id
    return jsonify({"success": True, "user": {"id": user_id, "email": email, "name": name}})

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ? AND password_hash = ?",
                      (email, hash_password(password))).fetchone()
    if not user:
        return jsonify({"error": "Invalid email or password"}), 401
    session["user_id"] = user["id"]
    return jsonify({"success": True, "user": {"id": user["id"], "email": user["email"], "name": user["name"]}})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/me")
def me():
    user = get_current_user()
    if not user:
        return jsonify({"user": None})
    return jsonify({"user": {"id": user["id"], "email": user["email"], "name": user["name"], "plan": user["plan"]}})

# ── WEATHER ──────────────────────────────────────────────────────────────────

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
        print(f"Weather error: {e}")
        return defaults

# ── HELPERS ───────────────────────────────────────────────────────────────────

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

# ── ROUTES ────────────────────────────────────────────────────────────────────

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

        result = {
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
            "language":   language,
            "timestamp":  datetime.now().strftime("%d %b %Y, %I:%M %p"),
            "solution":   f"🌿 {organic} | 🧪 {chemical}",
        }

        # Save to database
        user = get_current_user()
        scan_id = str(uuid.uuid4())
        db = get_db()
        db.execute("""
            INSERT INTO scans (id, user_id, disease, organic, chemical, risk, confidence, severity,
                city, weather, condition, humidity, temp, pressure, insight, crop_tip, language)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (scan_id, user["id"] if user else None, disease, organic, chemical, risk,
              confidence, severity, city, result["weather"], condition, humidity,
              temp, pressure, insight, crop_tip, language))
        db.commit()

        result["scan_id"] = scan_id
        return jsonify(result)

    except Exception as e:
        print(f"ERROR in /predict: {e}")
        return jsonify({"error": str(e)}), 500


# ── SCAN HISTORY (DB-backed) ──────────────────────────────────────────────────

@app.route("/api/history")
def api_history():
    user = get_current_user()
    db = get_db()
    if user:
        rows = db.execute(
            "SELECT * FROM scans WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20",
            (user["id"],)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM scans WHERE user_id IS NULL ORDER BY timestamp DESC LIMIT 10"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


# ── ANALYTICS ────────────────────────────────────────────────────────────────

@app.route("/api/analytics")
def api_analytics():
    user = get_current_user()
    db = get_db()
    where = "WHERE user_id = ?" if user else "WHERE user_id IS NULL"
    params = (user["id"],) if user else ()

    total = db.execute(f"SELECT COUNT(*) as c FROM scans {where}", params).fetchone()["c"]
    high_risk = db.execute(f"SELECT COUNT(*) as c FROM scans {where} AND risk = 'HIGH'", params).fetchone()["c"]
    avg_conf = db.execute(f"SELECT AVG(confidence) as a FROM scans {where}", params).fetchone()["a"] or 0

    diseases = db.execute(
        f"SELECT disease, COUNT(*) as cnt FROM scans {where} GROUP BY disease ORDER BY cnt DESC LIMIT 5",
        params
    ).fetchall()

    weekly = db.execute(
        f"SELECT date(timestamp) as day, COUNT(*) as cnt FROM scans {where} AND timestamp >= date('now','-7 days') GROUP BY day ORDER BY day",
        params
    ).fetchall()

    return jsonify({
        "total_scans":    total,
        "high_risk":      high_risk,
        "avg_confidence": round(avg_conf, 1),
        "top_diseases":   [dict(r) for r in diseases],
        "weekly_trend":   [dict(r) for r in weekly],
    })


# ── PDF REPORT ────────────────────────────────────────────────────────────────

@app.route("/download-report", methods=["POST"])
def download_report():
    try:
        data   = request.json or {}
        buffer = io.BytesIO()
        styles = getSampleStyleSheet()

        title_style  = ParagraphStyle("AgriTitle", parent=styles["Title"],    fontSize=20, spaceAfter=6,   textColor=colors.HexColor("#2d7a08"))
        head_style   = ParagraphStyle("AgriHead",  parent=styles["Heading2"], fontSize=12, spaceBefore=14, spaceAfter=4, textColor=colors.HexColor("#4a8a10"))
        body_style   = ParagraphStyle("AgriBody",  parent=styles["BodyText"], fontSize=11, leading=16,     spaceAfter=4)
        footer_style = ParagraphStyle("Footer",    parent=styles["BodyText"], fontSize=9,  textColor=colors.grey, alignment=1)

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
        row("Language", data.get("language", "English"))
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
            footer_style
        ))

        doc.build(story)
        buffer.seek(0)
        city_safe = (data.get("city") or "report").replace(" ", "_")
        return send_file(buffer, as_attachment=True,
                         download_name=f"AgriShield_{city_safe}_{datetime.now().strftime('%Y%m%d')}.pdf",
                         mimetype="application/pdf")

    except Exception as e:
        print(f"PDF Error: {e}")
        return jsonify({"error": str(e)}), 500


# ── PWA ───────────────────────────────────────────────────────────────────────

@app.route("/static/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")

@app.route("/static/sw.js")
def sw():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
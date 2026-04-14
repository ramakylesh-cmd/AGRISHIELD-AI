import os
import re
import uuid
import json
import sqlite3
import requests
import io
import base64
import hashlib
import time
from collections import defaultdict
from functools import wraps
from flask import Flask, request, jsonify, render_template, send_file, send_from_directory, session, g
from flask_cors import CORS
from groq import Groq
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ── Try bcrypt, fall back to sha256 ──────────────────────────────────────────
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    print("⚠️  bcrypt not installed — using SHA-256. Run: pip install bcrypt")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "agrishield-secret-2026-CHANGE-IN-PROD")

# FIX #13: Restrict CORS to known origins in production
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:10000").split(",")
CORS(app, supports_credentials=True, origins=ALLOWED_ORIGINS)

GROQ_API_KEY      = os.environ.get("GROQ_API_KEY")
WEATHER_API_KEY   = os.environ.get("WEATHER_API_KEY")
# FIX #7: Removed duplicate CLIENT_ID/CLIENT_SECRET at top — use only these:
GOOGLE_CLIENT_ID  = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SEC = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT   = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:10000/auth/google/callback")

if not GROQ_API_KEY:
    raise Exception("CRITICAL: GROQ_API_KEY environment variable missing!")

client = Groq(api_key=GROQ_API_KEY)

# FIX #5: Rate limiter with periodic cleanup to prevent memory leak
_rate_store = defaultdict(list)

def rate_limit(max_calls=10, window=60):
    """Decorator: max_calls per window seconds per IP, with cleanup."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            ip = request.remote_addr or "unknown"
            now = time.time()
            calls = [t for t in _rate_store[ip] if now - t < window]
            if len(calls) >= max_calls:
                return jsonify({"error": f"Rate limit: max {max_calls} requests per {window}s. Slow down."}), 429
            calls.append(now)
            _rate_store[ip] = calls
            # Cleanup: if store grows too large, purge inactive IPs
            if len(_rate_store) > 2000:
                stale = [k for k, v in list(_rate_store.items())
                         if not any(now - t < window for t in v)]
                for k in stale[:1000]:
                    del _rate_store[k]
            return f(*args, **kwargs)
        return wrapped
    return decorator

# ── PASSWORD HELPERS ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    if BCRYPT_AVAILABLE:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(password: str, hashed: str) -> bool:
    if BCRYPT_AVAILABLE:
        try:
            return bcrypt.checkpw(password.encode(), hashed.encode())
        except Exception:
            pass
    return hashlib.sha256(password.encode()).hexdigest() == hashed

# ── DATABASE ──────────────────────────────────────────────────────────────────

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
                id            TEXT PRIMARY KEY,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                name          TEXT,
                avatar        TEXT,
                provider      TEXT DEFAULT 'email',
                created_at    TEXT DEFAULT (datetime('now')),
                plan          TEXT DEFAULT 'free'
            );
            CREATE TABLE IF NOT EXISTS scans (
                id          TEXT PRIMARY KEY,
                user_id     TEXT,
                disease     TEXT,
                organic     TEXT,
                chemical    TEXT,
                risk        TEXT,
                confidence  INTEGER,
                severity    INTEGER,
                city        TEXT,
                weather     TEXT,
                condition   TEXT,
                humidity    INTEGER,
                temp        REAL,
                wind        REAL,
                pressure    INTEGER,
                insight     TEXT,
                crop_tip    TEXT,
                why_disease TEXT,
                language    TEXT DEFAULT 'English',
                source      TEXT DEFAULT 'image',
                timestamp   TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS login_attempts (
                ip          TEXT,
                timestamp   REAL,
                success     INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_scans_user ON scans(user_id);
            CREATE INDEX IF NOT EXISTS idx_scans_ts   ON scans(timestamp);
            CREATE INDEX IF NOT EXISTS idx_login_ip   ON login_attempts(ip, timestamp);
        """)
        db.commit()

init_db()

# ── AUTH HELPERS ──────────────────────────────────────────────────────────────

def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

def record_login_attempt(ip, success):
    db = get_db()
    db.execute("INSERT INTO login_attempts (ip, timestamp, success) VALUES (?, ?, ?)",
               (ip, time.time(), 1 if success else 0))
    # FIX #6: Prune old login attempts (keep only last 24h)
    db.execute("DELETE FROM login_attempts WHERE timestamp < ?", (time.time() - 86400,))
    db.commit()

def is_login_blocked(ip):
    """Block IP after 5 failed attempts in 5 minutes."""
    db = get_db()
    cutoff = time.time() - 300
    fails = db.execute(
        "SELECT COUNT(*) as c FROM login_attempts WHERE ip=? AND timestamp>? AND success=0",
        (ip, cutoff)
    ).fetchone()["c"]
    return fails >= 5

# ── AUTH ROUTES ───────────────────────────────────────────────────────────────

@app.route("/api/register", methods=["POST"])
@rate_limit(max_calls=5, window=60)
def register():
    data     = request.json or {}
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name     = (data.get("name") or "Farmer").strip()[:100]  # length cap
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({"error": "Invalid email address"}), 400
    db = get_db()
    if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
        return jsonify({"error": "Email already registered"}), 409
    uid = str(uuid.uuid4())
    db.execute("INSERT INTO users (id,email,password_hash,name,provider) VALUES (?,?,?,?,'email')",
               (uid, email, hash_password(password), name))
    db.commit()
    session["user_id"] = uid
    return jsonify({"success": True, "user": {"id": uid, "email": email, "name": name}})


@app.route("/api/login", methods=["POST"])
@rate_limit(max_calls=10, window=60)
def login():
    ip = request.remote_addr or "unknown"
    if is_login_blocked(ip):
        return jsonify({"error": "Too many failed attempts. Wait 5 minutes."}), 429
    data     = request.json or {}
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user or not check_password(password, user["password_hash"] or ""):
        record_login_attempt(ip, False)
        return jsonify({"error": "Invalid email or password"}), 401
    record_login_attempt(ip, True)
    session["user_id"] = user["id"]
    return jsonify({"success": True, "user": {
        "id": user["id"], "email": user["email"],
        "name": user["name"], "avatar": user["avatar"]
    }})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/api/me")
def me():
    user = get_current_user()
    if not user:
        return jsonify({"user": None})
    return jsonify({"user": {
        "id": user["id"], "email": user["email"],
        "name": user["name"], "plan": user["plan"],
        "avatar": user["avatar"], "provider": user["provider"]
    }})

# ── GOOGLE OAUTH ──────────────────────────────────────────────────────────────

@app.route("/auth/google")
def google_oauth_start():
    if not GOOGLE_CLIENT_ID:
        return jsonify({"error": "Google OAuth not configured. Set GOOGLE_CLIENT_ID env var."}), 501
    import urllib.parse
    state = str(uuid.uuid4())
    session["oauth_state"] = state
    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  GOOGLE_REDIRECT,
        "response_type": "code",
        "scope":         "openid email profile",
        "state":         state,
        "access_type":   "online",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return jsonify({"redirect_url": url})


@app.route("/auth/google/callback")
def google_oauth_callback():
    error = request.args.get("error")
    if error:
        return f"<script>window.opener.postMessage({{error:'{error}'}}, '*'); window.close();</script>"

    # FIX #8: Re-enable state validation (CSRF protection)
    state          = request.args.get("state")
    expected_state = session.pop("oauth_state", None)
    if not expected_state or state != expected_state:
        return "<script>window.opener.postMessage({error:'state_mismatch'}, '*'); window.close();</script>"

    code = request.args.get("code")
    if not code:
        return "<script>window.opener.postMessage({error:'no_code'}, '*'); window.close();</script>"

    try:
        token_resp = requests.post("https://oauth2.googleapis.com/token", data={
            "code":          code,
            "client_id":     GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SEC,
            "redirect_uri":  GOOGLE_REDIRECT,
            "grant_type":    "authorization_code",
        }, timeout=10).json()

        access_token = token_resp.get("access_token")
        if not access_token:
            raise ValueError("No access token received from Google")

        user_info = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        ).json()

        email  = user_info.get("email", "").lower()
        name   = user_info.get("name", "Farmer")
        avatar = user_info.get("picture", "")

        if not email:
            raise ValueError("No email from Google")

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user:
            uid = user["id"]
            db.execute("UPDATE users SET avatar=?, name=?, provider='google' WHERE id=?",
                       (avatar, name, uid))
        else:
            uid = str(uuid.uuid4())
            db.execute(
                "INSERT INTO users (id,email,name,avatar,provider) VALUES (?,?,?,?,'google')",
                (uid, email, name, avatar)
            )
        db.commit()
        session["user_id"] = uid

        safe_name = name.replace("'", "\\'")
        return f"""<script>
            window.opener.postMessage({{
                success: true,
                user: {{ id: '{uid}', email: '{email}', name: '{safe_name}', avatar: '{avatar}' }}
            }}, '*');
            window.close();
        </script>"""

    except Exception as e:
        print(f"Google OAuth error: {e}")
        return f"<script>window.opener.postMessage({{error:'oauth_failed'}}, '*'); window.close();</script>"

# ── WEATHER ───────────────────────────────────────────────────────────────────

# FIX #2: get_weather now returns wind as 5th element
def get_weather(city: str):
    """Returns (temp, humidity, condition, pressure, wind_speed)"""
    defaults = (28, 65, "Clear", 1012, 2.5)
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
            res["main"].get("pressure", 1012),
            round(res.get("wind", {}).get("speed", 2.5), 1),  # FIX: wind included
        )
    except Exception as e:
        print(f"Weather error: {e}")
        return defaults


@app.route("/api/weather")
def api_weather():
    """Real-time weather by city OR lat/lon."""
    city = request.args.get("city", "").strip()
    lat  = request.args.get("lat", "")
    lon  = request.args.get("lon", "")

    if not WEATHER_API_KEY:
        return jsonify({"error": "WEATHER_API_KEY not set"}), 503

    try:
        if lat and lon:
            url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
        elif city:
            url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        else:
            return jsonify({"error": "Provide city or lat/lon"}), 400

        res = requests.get(url, timeout=5).json()
        if "main" not in res:
            return jsonify({"error": "City not found"}), 404

        detected_city = res.get("name", city)
        return jsonify({
            "city":       detected_city,
            "temp":       round(res["main"]["temp"], 1),
            "humidity":   res["main"]["humidity"],
            "condition":  res["weather"][0]["main"] if res.get("weather") else "Clear",
            "desc":       res["weather"][0]["description"] if res.get("weather") else "",
            "pressure":   res["main"].get("pressure", 1012),
            "wind":       round(res.get("wind", {}).get("speed", 0), 1),
            "feels_like": round(res["main"].get("feels_like", res["main"]["temp"]), 1),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/forecast")
def api_forecast():
    """5-day / 3-hour forecast."""
    city = request.args.get("city", "").strip()
    lat  = request.args.get("lat", "")
    lon  = request.args.get("lon", "")

    if not WEATHER_API_KEY:
        return jsonify({"error": "WEATHER_API_KEY not set"}), 503

    try:
        if lat and lon:
            url = f"http://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&cnt=40"
        elif city:
            url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={WEATHER_API_KEY}&units=metric&cnt=40"
        else:
            return jsonify({"error": "Provide city or lat/lon"}), 400

        res = requests.get(url, timeout=5).json()
        if "list" not in res:
            return jsonify({"error": "Forecast not available"}), 404

        days = {}
        for item in res["list"]:
            day  = item["dt_txt"][:10]
            hour = int(item["dt_txt"][11:13])
            if day not in days or abs(hour - 12) < abs(int(days[day]["dt_txt"][11:13]) - 12):
                days[day] = item

        forecast = []
        for day, item in sorted(days.items())[:5]:
            forecast.append({
                "date":      day,
                "temp_max":  round(item["main"]["temp_max"], 1),
                "temp_min":  round(item["main"]["temp_min"], 1),
                "temp":      round(item["main"]["temp"], 1),
                "humidity":  item["main"]["humidity"],
                "condition": item["weather"][0]["main"] if item.get("weather") else "Clear",
                "desc":      item["weather"][0]["description"] if item.get("weather") else "",
                "wind":      round(item.get("wind", {}).get("speed", 0), 1),
            })

        return jsonify({
            "city":     res.get("city", {}).get("name", city),
            "forecast": forecast
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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

def save_scan(db, user, disease, organic, chemical, risk, confidence, severity,
              city, weather_str, condition, humidity, temp, pressure, wind,
              insight, crop_tip, why, language, source="image"):
    """Shared helper to persist a scan to DB."""
    scan_id = str(uuid.uuid4())
    db.execute("""
        INSERT INTO scans
          (id,user_id,disease,organic,chemical,risk,confidence,severity,
           city,weather,condition,humidity,temp,wind,pressure,
           insight,crop_tip,why_disease,language,source)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (scan_id, user["id"] if user else None,
          disease, organic, chemical, risk, confidence, severity,
          city, weather_str, condition, humidity, temp, wind, pressure,
          insight, crop_tip, why, language, source))
    db.commit()
    return scan_id

# ── IMAGE PREDICT ─────────────────────────────────────────────────────────────

MAX_IMAGE_BYTES = 8 * 1024 * 1024  # FIX #9: 8 MB limit

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/predict", methods=["POST", "HEAD"])
@rate_limit(max_calls=30, window=60)
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

        # FIX #9: Validate image size
        if len(img_bytes) > MAX_IMAGE_BYTES:
            return jsonify({"error": f"Image too large. Max size is 8 MB (got {len(img_bytes)//1024//1024} MB)."}), 413

        mime_type = file.mimetype or "image/jpeg"
        if mime_type not in ("image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic"):
            mime_type = "image/jpeg"

        img_b64   = base64.b64encode(img_bytes).decode("utf-8")
        image_url = f"data:{mime_type};base64,{img_b64}"

        city     = (request.form.get("city", "Chennai") or "Chennai").strip()[:100]
        language = (request.form.get("language", "English") or "English").strip()

        # FIX #2: Unpack 5 values including wind
        temp, humidity, condition, pressure, wind = get_weather(city)

        # FIX #10: Added Why This Disease + Alternatives to prompt
        prompt = f"""You are an expert plant pathologist AI. Analyze this plant image carefully.

Current weather in {city}: {temp}°C, {humidity}% humidity, {condition}, pressure {pressure} hPa, wind {wind} m/s.

CRITICAL: Respond ENTIRELY in {language}. Every word must be in {language}.

Reply in EXACTLY this format (no extra lines, no markdown):
Disease Name: [name in {language}]
Organic Solution: [2-3 sentence organic treatment]
Chemical Solution: [2-3 sentence chemical treatment]
Risk Level: [LOW or MEDIUM or HIGH]
Confidence: [integer 60-99]
Severity: [integer 1-10]
Crop Tip: [one short actionable tip based on the weather in {city}]
Why This Disease: [one sentence explaining the key visual symptoms that led to this diagnosis]
Alternative 1: [second most likely disease — name only]
Alternative 2: [third most likely disease — name only]"""

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt}
                ]
            }],
            max_tokens=800,
            temperature=0.2,
        )

        text  = (response.choices[0].message.content or "").strip()
        lines = text.split("\n")

        disease     = extract_field(lines, "Disease Name")
        organic     = extract_field(lines, "Organic Solution")
        chemical    = extract_field(lines, "Chemical Solution")
        crop_tip    = extract_field(lines, "Crop Tip")
        why         = extract_field(lines, "Why This Disease")
        alt1        = extract_field(lines, "Alternative 1")
        alt2        = extract_field(lines, "Alternative 2")

        risk_raw    = extract_field(lines, "Risk Level").upper()
        risk        = "HIGH" if "HIGH" in risk_raw else "LOW" if "LOW" in risk_raw else "MEDIUM"
        confidence  = safe_int(extract_field(lines, "Confidence"), 60, 99, 75)
        severity    = safe_int(extract_field(lines, "Severity"),    1, 10,  5)

        if humidity > 70:
            risk_reason = "high humidity increases fungal spread risk"
        elif humidity < 40:
            risk_reason = "low humidity reduces fungal risk but watch for pests"
        else:
            risk_reason = "conditions are moderate — regular monitoring advised"

        insight = (
            f"Weather in {city}: {humidity}% humidity, {temp}°C, wind {wind} m/s — "
            f"{risk_reason}. Current risk level: {risk}."
        )

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
            "wind":       wind,          # FIX #2: now included
            "insight":    insight,
            "crop_tip":   crop_tip,
            "why":        why,           # FIX #10: now included
            "alt1":       alt1,
            "alt2":       alt2,
            "city":       city,
            "language":   language,
            "timestamp":  datetime.now().strftime("%d %b %Y, %I:%M %p"),
        }

        user    = get_current_user()
        db      = get_db()
        scan_id = save_scan(db, user, disease, organic, chemical, risk, confidence, severity,
                            city, result["weather"], condition, humidity, temp, pressure, wind,
                            insight, crop_tip, why, language, source="image")
        result["scan_id"] = scan_id
        return jsonify(result)

    except Exception as e:
        print(f"ERROR in /predict: {e}")
        return jsonify({"error": str(e)}), 500


# ── FIX #1: VOICE DIAGNOSE ROUTE — was completely missing ────────────────────

@app.route("/voice-diagnose", methods=["POST"])
@rate_limit(max_calls=20, window=60)
def voice_diagnose():
    """Diagnose plant disease from a farmer's voice query (text)."""
    try:
        data     = request.json or {}
        query    = (data.get("query") or "").strip()
        city     = (data.get("city")  or "Chennai").strip()[:100]
        language = (data.get("language") or "English").strip()

        if not query:
            return jsonify({"error": "No query provided"}), 400
        if len(query) > 2000:
            query = query[:2000]

        temp, humidity, condition, pressure, wind = get_weather(city)

        prompt = f"""You are an expert plant pathologist AI helping a farmer.
The farmer described their crop problem in {language}:

"{query}"

Current weather in {city}: {temp}°C, {humidity}% humidity, {condition}, wind {wind} m/s.

Based ONLY on the verbal description, give the most likely diagnosis.

CRITICAL: Respond ENTIRELY in {language}.

Reply in EXACTLY this format:
Disease Name: [name]
Organic Solution: [2-3 sentence organic treatment]
Chemical Solution: [2-3 sentence chemical treatment]
Risk Level: [LOW or MEDIUM or HIGH]
Confidence: [integer 45-88 — be honest, this is from description not photo]
Severity: [integer 1-10]
Crop Tip: [one short actionable tip]
Why This Disease: [one sentence explaining which symptoms in their description suggest this diagnosis]
Alternative 1: [second most likely disease]
Alternative 2: [third most likely disease]"""

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
            temperature=0.3,
        )

        text  = (response.choices[0].message.content or "").strip()
        lines = text.split("\n")

        disease    = extract_field(lines, "Disease Name")
        organic    = extract_field(lines, "Organic Solution")
        chemical   = extract_field(lines, "Chemical Solution")
        crop_tip   = extract_field(lines, "Crop Tip")
        why        = extract_field(lines, "Why This Disease")
        alt1       = extract_field(lines, "Alternative 1")
        alt2       = extract_field(lines, "Alternative 2")

        risk_raw   = extract_field(lines, "Risk Level").upper()
        risk       = "HIGH" if "HIGH" in risk_raw else "LOW" if "LOW" in risk_raw else "MEDIUM"
        confidence = safe_int(extract_field(lines, "Confidence"), 45, 88, 62)
        severity   = safe_int(extract_field(lines, "Severity"),    1, 10,  5)

        insight = (
            f"Voice diagnosis for {city} ({humidity}% humidity, {temp}°C): "
            f"{why or 'Based on described symptoms.'}"
        )

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
            "wind":       wind,
            "insight":    insight,
            "crop_tip":   crop_tip,
            "why":        why,
            "alt1":       alt1,
            "alt2":       alt2,
            "city":       city,
            "language":   language,
            "timestamp":  datetime.now().strftime("%d %b %Y, %I:%M %p"),
        }

        user    = get_current_user()
        db      = get_db()
        scan_id = save_scan(db, user, disease, organic, chemical, risk, confidence, severity,
                            city, result["weather"], condition, humidity, temp, pressure, wind,
                            insight, crop_tip, why, language, source="voice")
        result["scan_id"] = scan_id
        return jsonify(result)

    except Exception as e:
        print(f"ERROR in /voice-diagnose: {e}")
        return jsonify({"error": str(e)}), 500

# ── HISTORY & ANALYTICS ───────────────────────────────────────────────────────

@app.route("/api/history")
def api_history():
    user = get_current_user()
    db   = get_db()
    if user:
        rows = db.execute(
            "SELECT * FROM scans WHERE user_id=? ORDER BY timestamp DESC LIMIT 20",
            (user["id"],)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM scans WHERE user_id IS NULL ORDER BY timestamp DESC LIMIT 10"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/analytics")
def api_analytics():
    user   = get_current_user()
    db     = get_db()

    # FIX #11: Use explicit parameterized building to avoid accidental SQL breaks
    if user:
        uid_filter = "user_id = ?"
        params     = (user["id"],)
    else:
        uid_filter = "user_id IS NULL"
        params     = ()

    total     = db.execute(f"SELECT COUNT(*) as c FROM scans WHERE {uid_filter}", params).fetchone()["c"]
    high_risk = db.execute(f"SELECT COUNT(*) as c FROM scans WHERE {uid_filter} AND risk='HIGH'", params).fetchone()["c"]
    avg_conf  = db.execute(f"SELECT AVG(confidence) as a FROM scans WHERE {uid_filter}", params).fetchone()["a"] or 0
    diseases  = db.execute(
        f"SELECT disease, COUNT(*) as cnt FROM scans WHERE {uid_filter} GROUP BY disease ORDER BY cnt DESC LIMIT 5",
        params
    ).fetchall()
    weekly    = db.execute(
        f"""SELECT date(timestamp) as day, COUNT(*) as cnt
            FROM scans
            WHERE {uid_filter} AND timestamp >= date('now','-7 days')
            GROUP BY day ORDER BY day""",
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
@rate_limit(max_calls=10, window=60)
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
        row("Wind",     f"{data.get('wind', '--')} m/s")
        row("Language", data.get("language", "English"))
        story.append(Spacer(1, 6))

        story.append(Paragraph("Diagnosis", head_style))
        row("Disease",       data.get("disease"))
        row("Risk Level",    data.get("risk"))
        row("AI Confidence", f"{data.get('confidence', 'N/A')}%")
        row("Severity",      f"{data.get('severity', 'N/A')}/10")
        if data.get("why") and data.get("why") != "N/A":
            row("Why Detected",  data.get("why"))
        if data.get("alt1") and data.get("alt1") != "N/A":
            row("Alternative",   f"{data.get('alt1')} / {data.get('alt2', '')}")
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
        story.append(Paragraph("<i>Generated by AgriShield AI — Hackathon 2026</i>", footer_style))

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
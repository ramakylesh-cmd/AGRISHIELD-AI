import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import google.generativeai as genai
from PIL import Image

app = Flask(__name__)
CORS(app)

# Secure API setup
API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-3-flash-preview")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/predict", methods=["POST"])
def predict():
    try:
        print("--- NEW REQUEST RECEIVED ---")
        if 'image' not in request.files:
            return jsonify({"error": "No image uploaded"}), 400

        file = request.files["image"]
        img = Image.open(file)

        # High-level prompt for the judges
        prompt = (
            "Analyze this plant image. Return exactly in this format:\n"
            "Line 1: Disease Name\n"
            "Line 2: Organic Solution\n"
            "Line 3: Chemical Solution"
        )

        response = model.generate_content([prompt, img])
        
        if not response.text:
            return jsonify({"disease": "Healthy", "solution": "No issues found."})

        # Logic to parse the AI response
        lines = response.text.strip().split('\n')
        disease_name = lines[0].replace("Line 1:", "").strip()
        
        # Safe extraction of solutions
        organic = lines[1].replace("Line 2:", "").strip() if len(lines) > 1 else "N/A"
        chemical = lines[2].replace("Line 3:", "").strip() if len(lines) > 2 else "N/A"
        
        return jsonify({
            "disease": disease_name,
            "solution": f"🌿 ORGANIC: {organic} | 🧪 CHEMICAL: {chemical}"
        })

    except Exception as e:
        print(f"DEBUG ERROR: {e}")
        return jsonify({"error": "AI Processing Error. Check Key/Connection."}), 500

# RENDER PORT FIX
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
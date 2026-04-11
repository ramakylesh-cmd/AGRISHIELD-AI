import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import google.generativeai as genai
from PIL import Image

app = Flask(__name__)
CORS(app)

# Use Environment Variable for Render, fall back to your key for local testing
API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)

# Using the top-tier model from your verified list
model = genai.GenerativeModel("gemini-3-flash-preview")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/predict", methods=["POST"])
def predict():
    try:
        print("REQUEST RECEIVED")

        if 'image' not in request.files:
            print("NO IMAGE")
            return jsonify({"error": "No image uploaded"}), 400

        file = request.files["image"]
        print("FILE:", file.filename)

        img = Image.open(file)
        print("IMAGE LOADED")

        prompt = "Say plant disease"

        response = model.generate_content([prompt, img])
        print("RESPONSE:", response)

        return jsonify({"disease": "ok", "solution": "ok"})

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"error": str(e)}), 500

        # Smart parsing for the new prompt format
        lines = response.text.strip().split('\n')
        disease_name = lines[0].replace("Line 1:", "").strip()
        
        # Combining organic and chemical into a rich solution string
        organic = lines[1].replace("Line 2:", "").strip() if len(lines) > 1 else ""
        chemical = lines[2].replace("Line 3:", "").strip() if len(lines) > 2 else ""
        
        full_solution = f"ORGANIC: {organic} | CHEMICAL: {chemical}"

        return jsonify({
            "disease": disease_name,
            "solution": full_solution
        })
    except Exception as e:
        print(f"DEBUG ERROR: {e}")
        return jsonify({"error": "AI processing failed. Check connection."}), 500

# MANDATORY RENDER FIX: Dynamic Port Selection
if __name__ == "__main__":
    # Render assigns a port dynamically. Local usually defaults to 10000 here.
    port = int(os.environ.get("PORT", 5000))
    # host='0.0.0.0' is required for Render to see your app
    app.run(host='0.0.0.0', port=port)
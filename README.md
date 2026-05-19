<div align="center">

# 🌱 AgriShield AI

### *Detect. Diagnose. Protect Your Harvest.*

**An intelligent crop disease detection & advisory platform combining AI, real-time scanning, and weather intelligence — built for Indian farmers.**

[![Live Demo](https://img.shields.io/badge/🚀_Live_Demo-Visit_App-brightgreen?style=for-the-badge)](YOUR_DEPLOYED_LINK_HERE)
[![GitHub](https://img.shields.io/badge/GitHub-ramakylesh--cmd-black?style=for-the-badge&logo=github)](https://github.com/ramakylesh-cmd/AGRISHIELD-AI)
[![Made with Love](https://img.shields.io/badge/Made_with-❤️_for_Indian_Farmers-orange?style=for-the-badge)](https://github.com/ramakylesh-cmd/AGRISHIELD-AI)

</div>

---

## 📸 Screenshots

| Home & Weather | Disease Detection | AI Results | Farmer Mode (Tamil) |
|---|---|---|---|
| ![Home](screenshot-home.png) | ![Scan](screenshot-scan.png) | ![Result](screenshot-result.png) | ![Tamil](screenshot-tamil.png) |

> *Replace the image filenames above with actual screenshot paths in your repo*

---

## 🧠 What is AgriShield AI?

AgriShield AI is a **full-stack AI-powered web application** that helps farmers detect crop diseases in real time by simply uploading or scanning a plant photo. It combines:

- **On-device ML** for instant offline detection
- **Groq LLM (Llama)** for detailed AI-generated diagnosis and treatment advice
- **Real-time weather data** to give risk-aware, location-specific recommendations
- **Multilingual support** so Indian farmers can use it in their own language

Built as a **Progressive Web App (PWA)** — it works offline, can be installed on a phone, and runs on low-end devices.

---

## ✨ Key Features

### 🔬 Multi-Modal Disease Detection
- 📸 Upload from gallery, take a photo with camera, or use **Live AI Scan**
- 🌐 **Offline detection** using on-device TensorFlow.js (Teachable Machine model)
- 🎙️ **Voice input** — farmers can describe symptoms by speaking

### 🤖 AI-Powered Diagnosis
- Identifies diseases like *Septoria Leaf Spot*, *Early Blight*, *Bacterial Canker*, and more
- **85%+ confidence scoring** with severity rating (out of 10)
- Dual treatment plans: **Organic 🌿** and **Chemical ⚗️**
- Differential diagnosis — shows what else it could be
- **PDF report download** for each scan result

### 🌦️ Weather Intelligence
- Real-time weather from **OpenWeatherMap API** (auto-detects location)
- 5-day forecast integrated into risk assessment
- *"High humidity = high fungal risk"* — weather-aware advice

### 🌍 Farmer Mode (Accessibility First)
- Full UI available in **Tamil, Hindi, Telugu, Kannada, Malayalam, and English**
- Voice-first interface with listen button on results
- High-contrast, large-text layout designed for rural users
- Works on 3G and low-end smartphones

### 📊 Analytics Dashboard
- Track scan history across devices
- Disease trend monitoring
- Crop care calendar (Jan–Dec planting guide)

### 🔐 Authentication
- **Google OAuth 2.0** — one-tap sign in
- Email/password option via **Supabase Auth**
- Scan history synced across devices when signed in

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | HTML5, CSS3 (Glassmorphism UI), JavaScript ES6+ |
| **Backend** | Flask (Python), Serverless Architecture |
| **Database & Auth** | Supabase (PostgreSQL + Auth) |
| **AI/ML — Diagnosis** | Groq API (Llama 3 models) |
| **AI/ML — Detection** | TensorFlow.js + Teachable Machine (on-device) |
| **Weather** | OpenWeatherMap API |
| **Auth** | Google OAuth 2.0 |
| **PWA** | Service Workers, Manifest, Offline Support |
| **Deployment** | Vercel / Serverless |

---

## 🏗️ Architecture Overview

```
User (Mobile/Browser)
        │
        ▼
  Frontend (HTML/CSS/JS)
        │
   ┌────┴────────────────────┐
   │                         │
   ▼                         ▼
TensorFlow.js           Flask Backend (Python)
(On-device ML)               │
   │                    ┌────┴────────────┐
   └──── Offline         │                │
         Detection      Groq API      OpenWeatherMap
                        (Llama LLM)    (Weather Data)
                             │
                        Supabase
                    (DB + Auth + Storage)
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- Node.js (optional, for local dev server)
- Supabase account
- Groq API key
- OpenWeatherMap API key

### Installation

```bash
# Clone the repo
git clone https://github.com/ramakylesh-cmd/AGRISHIELD-AI.git
cd AGRISHIELD-AI

# Install Python dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Fill in your API keys in .env

# Run locally
python app.py
```

### Environment Variables

```env
GROQ_API_KEY=your_groq_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
OPENWEATHER_API_KEY=your_weather_key
```

---

## 🌾 How It Works

1. **Open the app** → Location auto-detected → Live weather loaded
2. **Upload or scan** a plant photo (camera / gallery / live scan)
3. **On-device TensorFlow.js** model runs instantly (works offline)
4. **Groq LLM** generates detailed diagnosis + treatment plan
5. **Weather Intelligence** adjusts risk level based on local conditions
6. **Results displayed** in your language with organic + chemical treatment options
7. **Download PDF** or save to history for future reference

---

## 📱 PWA — Install on Your Phone

AgriShield AI works as a **Progressive Web App**:
- Visit the live link on your mobile browser
- Tap *"Add to Home Screen"*
- It works like a native app — even offline!

---

## 🎯 Impact

AgriShield AI was built with a real problem in mind:

> *Indian farmers lose 15–25% of crops to diseases every year, often due to late or incorrect diagnosis. Most solutions require expensive equipment or internet connectivity.*

AgriShield solves this by:
- Running **offline** on cheap smartphones
- Speaking in **regional Indian languages**
- Giving **actionable treatment advice** instantly
- Being completely **free to use**

---

## 🏆 Project Highlights

- 🌐 Fully deployed and functional
- 📱 PWA — installable on mobile
- 🔌 Works offline with on-device ML
- 🌍 6 Indian languages supported
- 🤖 Dual AI system (fast local + powerful cloud)
- 📊 Analytics + PDF export
- 🔐 Full auth system (Google + Email)

---

## 👨‍💻 Built By

**Akylesh Ram**
2nd Year ECE Student | SRM Institute of Science and Technology

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-blue?style=flat&logo=linkedin)](YOUR_LINKEDIN_URL)
[![GitHub](https://img.shields.io/badge/GitHub-Follow-black?style=flat&logo=github)](https://github.com/ramakylesh-cmd)

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

---

<div align="center">

*Built with ❤️ for Indian Farmers | AgriShield AI — Hackathon 2026*

⭐ **If this project helped you, please give it a star!** ⭐

</div>
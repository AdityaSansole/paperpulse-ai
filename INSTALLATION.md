# Installation & Setup Guide

This guide walks you through setting up both the **FastAPI Backend** and **React TypeScript Frontend** for PaperPulse AI.

---

## Prerequisites

- **Python**: `3.11+`
- **Node.js**: `18.0.0+` (with `npm`)
- **Tesseract OCR** (for offline document scanning)
- **Google Gemini API Key** (for intelligent field extraction)

---

## 1. Setup Backend (FastAPI)

Navigate to the project root directory:

```bash
# 1. Create a virtual environment
python -m venv venv

# 2. Activate the virtual environment
# On Windows (PowerShell):
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt
```

---

## 2. Setup Frontend (React + Vite)

Navigate into the new React frontend directory:

```bash
cd web
npm install
```

---

## 3. Install Tesseract OCR

### Windows
1. Download the installer from [UB-Mannheim Tesseract Wiki](https://github.com/UB-Mannheim/tesseract/wiki).
2. Install it on your system.
3. Add the installation folder path (e.g. `C:\Program Files\Tesseract-OCR`) to your system's Environment Variables **PATH**.

### Linux (Ubuntu/Debian)
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-hin
```

### macOS (via Homebrew)
```bash
brew install tesseract tesseract-lang
```

Verify Tesseract is on your path by running:
```bash
tesseract --version
```

---

## 4. Configure Environment Variables

Create your local `.env` configuration file in the project **root directory** (not in the `web` folder):

```bash
cp .env.example .env
```

Open `.env` and fill in your keys and settings:

```env
AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here (optional)
OCR_ENGINE=tesseract
OCR_LANG=eng+hin
MAX_WORKERS=8
```

---

## 5. Running the Application

For a fully working stack, you should launch **both** the backend FastAPI server and the frontend Vite server.

### Terminal 1: Launch Backend Server (Root directory)
```bash
# Activate venv if needed: venv\Scripts\activate
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
- API will be live on: `http://localhost:8000`
- Interactive API Docs: `http://localhost:8000/docs`

### Terminal 2: Launch Frontend Server (web directory)
```bash
cd web
npm run dev
```
- Frontend portal will be live on: `http://localhost:3000`
- The Vite dev server will proxy backend requests directly to port 8000.

---

## Troubleshooting

- **Proxy Error (`ECONNREFUSED`)**: Ensure you have successfully started the Python backend server on port 8000 first.
- **Python `No module named uvicorn`**: Ensure you have activated your virtual environment and successfully run `pip install -r requirements.txt`.
- **Tesseract Not Found**: Ensure you added Tesseract to your PATH (especially on Windows) or rebooted your terminal after installation.

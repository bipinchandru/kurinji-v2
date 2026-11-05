# KURINJI — Indigenous Bridge System (Quickstart Guide)

KURINJI is an educational bridge system that enables indigenous Badaga & Marwari children to learn Tamil and English through interactive cartoon learning cards, phonetic breakdowns, and voice recognition.

---

## 🚀 Quick Start (Windows — 1 Click)

1. **Prerequisites**: Make sure you have:
   - **Python 3.10+** ([python.org](https://www.python.org/downloads/))
   - **Node.js 18+** ([nodejs.org](https://nodejs.org/))

2. **Setup your Gemini API Key**:
   - Open `.env` (or copy `.env.example` to `.env`)
   - Add your free Google Gemini API key:
     ```env
     GEMINI_API_KEY=your_actual_key_here
     ```

3. **Install Python dependencies (First time only)**:
   Open a terminal/PowerShell in this folder and run:
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch Application**:
   - Double-click **`start_kurinji.bat`**!
   - This automatically starts:
     - Backend API server on `http://127.0.0.1:8000`
     - Frontend learning desk on `http://localhost:5173`
     - Automatically launches your default web browser to the application!

---

## 🎙️ How to Use the Application

1. **Voice Search (Speech Translation)**:
   - Click the green **"Speak Badaga"** button at the top.
   - Speak any of the 58 Badaga words clearly into your microphone:
     - Examples: *"kannu"* (Eye), *"mande"* (Head), *"aavu"* (Cow), *"nei"* (Dog), *"maraa"* (Tree), *"pal"* (Teeth).
   - Click **Done**. The system identifies the word and opens the corresponding learning card instantly!

2. **Text Search**:
   - Type any Badaga romanized word in the search box (e.g., `maraa`, `kannu`, `pal`, `mande`, `aavu`).
   - Press **Enter** to jump directly to the verified card.

3. **Explore Curriculum Cards (Kindergarten to Class 5)**:
   - Filter through categories: **My Body**, **Family & Home**, **Nature & Sky**, **Animals & Birds**, **Numbers (1–10)**, **School & Actions**.
   - Each card features a rich 3D cartoon illustration, Tamil script, English meaning, and spelling breakdown.

4. **Interactive Learning Card Modal**:
   - Click any card to open its detailed lesson modal.
   - Click **"Hear Badaga Voice"** to listen to authentic native pronunciation clips.
   - Click **"Listen Tamil"** to hear the Tamil pronunciation.
   - Study the **Letter Blending** formula (e.g., `ப + சு = பசு`) and sample sentence.

---

## 🛠️ Manual Launch (For Linux / macOS)

If you are not on Windows:

### Terminal 1: Backend
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Terminal 2: Frontend
```bash
cd frontend
npm install
npm run dev
```
Open **`http://localhost:5173`** in your browser.

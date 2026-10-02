# PocketSmart AI: Your Smart Budget & Recommendation Assistant
React + Tailwind (CDN) frontend, FastAPI backend, Google Gemini with a built-in demo mode.

## Start the backend
```
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```
API runs at http://localhost:8000 (docs at /docs).

## Start the frontend
```
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. Set `VITE_API_URL` if the backend is elsewhere.

## Gemini and demo mode
Edit `backend/.env`:
```
GEMINI_API_KEY=your_key
DEMO_MODE=false
```
Demo mode is used when `DEMO_MODE=true`, when no key is set, or when the user clicks "Use Demo Recommendations" after an AI failure. Demo results are budget-scaled sample data labelled "Demo Recommendation". Prices and platforms are never live marketplace data. The key is only read by the backend.

## Endpoints
POST /register, /login, /logout, /generate-home, /generate-party, /generate-jewelry, /recommendations/{id}/save;
GET /health, /session-info, /session-data, /history?type=, /recommendations-details/{id}.
Auth: `Authorization: Bearer <token>` (signed, expiring, revocable on logout). Data is stored in `backend/data/db.json`.

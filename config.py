import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
SECRET = os.getenv("SECRET_KEY", "dev-secret-change-me")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
DB = Path(__file__).parent / "data" / "db.json"

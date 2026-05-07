import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Project Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
BOOK_PATH = ROOT_DIR / "data" / "opening_books" / "40H-PGN-databases" / "human_masters_95years.bin"

# Engine Settings
# Defaulting to your TUXEDO path, but overrideable via .env
STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "/usr/games/stockfish")

# Database
DATABASE_URL = os.getenv("DATABASE_URL")
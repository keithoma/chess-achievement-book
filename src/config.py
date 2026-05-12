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

# Engine Depth
LOW_DEPTH = 1
HIGH_DEPTH = 18

# Grace Period for Checkmate Achievements
MATE_GRACE_THRESHOLD = 2.0  # Centipawn eval threshold to trigger playout (+2.0 or -2.0)
MATE_GRACE_PLIES = 20       # 10 full moves
MATE_GRACE_DEPTH = 20       # Engine search depth for the playout moves
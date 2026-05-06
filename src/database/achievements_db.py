import logging
from .connection import get_connection

logger = logging.getLogger(__name__)

def setup_achievements_db():
    query = """
    -- Tracks every time an achievement happens in a specific game (The Ledger)
    CREATE TABLE IF NOT EXISTS game_achievements (
        game_id TEXT,
        username TEXT,
        achievement_slug TEXT,
        granted_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (game_id, achievement_slug)
    );

    -- NEW/RESTORED: The Global Trophy Cabinet (One row per badge per user)
    CREATE TABLE IF NOT EXISTS user_badges (
        username TEXT,
        achievement_slug TEXT,
        first_achieved_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (username, achievement_slug)
    );

    -- (Keep your mastery_progress and game_mastery_grants tables here too)

    -- NEW: Overall Mastery Progress Tracking
    CREATE TABLE IF NOT EXISTS mastery_progress (
        username TEXT,
        category TEXT,
        slug TEXT,
        name TEXT,
        total_exp REAL DEFAULT 0,
        PRIMARY KEY (username, category, slug)
    );

    -- NEW: Ledger to prevent double-counting EXP for the same game
    CREATE TABLE IF NOT EXISTS game_mastery_grants (
        game_id TEXT,
        username TEXT,
        mastery_slug TEXT,
        exp_granted REAL,
        granted_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (game_id, mastery_slug)
    );
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
        conn.commit()
    logger.debug("Database tables verified (Including Mastery).")
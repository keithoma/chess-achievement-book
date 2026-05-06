import logging
from .connection import get_connection

logger = logging.getLogger(__name__)

def setup_achievements_db():
    query = """
    -- Existing Badges Table
    CREATE TABLE IF NOT EXISTS game_achievements (
        game_id TEXT,
        username TEXT,
        achievement_slug TEXT,
        granted_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (game_id, achievement_slug)
    );

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
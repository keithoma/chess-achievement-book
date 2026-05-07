"""
Achievement Ledger operations.

Provides the interface for the Scanner to safely record progress, 
unlocks, and game history grants into the database.
"""

import logging
from typing import Optional
from src.database.connection import get_connection

logger = logging.getLogger(__name__)

class AchievementLedger:
    def __init__(self, username: str):
        self.username = username

    def is_already_granted(self, game_id: str, def_id: str) -> bool:
        """Checks if a specific game has already triggered a specific achievement."""
        query = """
            SELECT 1 FROM game_grants_ledger 
            WHERE game_id = %s AND username = %s AND def_id = %s
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (game_id, self.username, def_id))
                return cur.fetchone() is not None

    def record_feat(self, game_id: str, def_id: str):
        """Unlocks a one-time feat."""
        if self.is_already_granted(game_id, def_id):
            return

        unlock_query = """
            INSERT INTO user_unlocks (username, def_id, tier)
            VALUES (%s, %s, 'base')
            ON CONFLICT (username, def_id, tier) DO NOTHING;
        """
        
        ledger_query = """
            INSERT INTO game_grants_ledger (game_id, username, def_id)
            VALUES (%s, %s, %s);
        """
        
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(unlock_query, (self.username, def_id))
                cur.execute(ledger_query, (game_id, self.username, def_id))
            conn.commit()
            
        logger.info("🏆 FEAT UNLOCKED: %s in game %s", def_id, game_id)

    def record_progress(self, game_id: str, def_id: str, amount: float, newly_unlocked_tier: Optional[str] = None):
        """Adds progress to a Badge or Mastery and logs the exact amount gained."""
        if self.is_already_granted(game_id, def_id):
            return

        # Upsert the accumulating total
        progress_query = """
            INSERT INTO user_progress (username, def_id, current_value)
            VALUES (%s, %s, %s)
            ON CONFLICT (username, def_id) DO UPDATE SET
                current_value = user_progress.current_value + EXCLUDED.current_value,
                updated_at = NOW();
        """
        
        ledger_query = """
            INSERT INTO game_grants_ledger (game_id, username, def_id, change_amount, tier_unlocked)
            VALUES (%s, %s, %s, %s, %s);
        """

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(progress_query, (self.username, def_id, amount))
                cur.execute(ledger_query, (game_id, self.username, def_id, amount, newly_unlocked_tier))
                
                # If a new tier was reached (e.g., hit 25 wins for Gold), save it to unlocks
                if newly_unlocked_tier:
                    unlock_query = """
                        INSERT INTO user_unlocks (username, def_id, tier)
                        VALUES (%s, %s, %s)
                        ON CONFLICT DO NOTHING;
                    """
                    cur.execute(unlock_query, (self.username, def_id, newly_unlocked_tier))
                    
            conn.commit()

        if newly_unlocked_tier:
            logger.info("🏅 TIER UP! %s reached %s tier!", def_id, newly_unlocked_tier)
        else:
            logger.debug("📈 Progress added: %s to %s", amount, def_id)
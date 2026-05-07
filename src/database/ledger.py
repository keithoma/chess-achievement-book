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
        self._ensure_user_exists()

    def _ensure_user_exists(self):
        """Silently registers the user in the database if they don't exist."""
        query = """
            INSERT INTO users (username) 
            VALUES (%s) 
            ON CONFLICT (username) DO NOTHING;
        """
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (self.username,))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to register user {self.username}: {e}")

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

    def record_progress(self, game_id: str, def_id: str, amount: float):
        """Adds progress and checks for tier-ups internally."""
        if self.is_already_granted(game_id, def_id):
            return

        with get_connection() as conn:
            with conn.cursor() as cur:
                # 1. Update/Insert progress and get the total
                cur.execute("""
                    INSERT INTO user_progress (username, def_id, current_value)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (username, def_id) DO UPDATE SET
                        current_value = user_progress.current_value + EXCLUDED.current_value
                    RETURNING current_value;
                """, (self.username, def_id, amount))
                new_total = cur.fetchone()[0]

                # 2. Check for tier unlock
                cur.execute("SELECT config FROM achievement_definitions WHERE id = %s", (def_id,))
                res = cur.fetchone()
                config = res[0] if res else {}
                
                newly_unlocked_tier = None
                if 'tiers' in config:
                    # Check tiers in descending order (Gold -> Silver -> Bronze)
                    for tier, threshold in sorted(config['tiers'].items(), key=lambda x: x[1], reverse=True):
                        if new_total >= threshold:
                            # Check if already unlocked
                            cur.execute("SELECT 1 FROM user_unlocks WHERE username=%s AND def_id=%s AND tier=%s", 
                                        (self.username, def_id, tier))
                            if not cur.fetchone():
                                newly_unlocked_tier = tier
                                cur.execute("INSERT INTO user_unlocks (username, def_id, tier) VALUES (%s, %s, %s)", 
                                            (self.username, def_id, tier))
                            break

                # 3. Save to Ledger
                cur.execute("""
                    INSERT INTO game_grants_ledger (game_id, username, def_id, change_amount, tier_unlocked)
                    VALUES (%s, %s, %s, %s, %s);
                """, (game_id, self.username, def_id, amount, newly_unlocked_tier))
            conn.commit()

        if newly_unlocked_tier:
            print(f"🎉 ACHIEVEMENT UNLOCKED: {def_id} - {newly_unlocked_tier.upper()}!")
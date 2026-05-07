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
        """Adds progress and checks if a new tier should be unlocked."""
        if self.is_already_granted(game_id, def_id):
            return

        with get_connection() as conn:
            with conn.cursor() as cur:
                # 1. Update progress and get the NEW total in one go
                progress_query = """
                    INSERT INTO user_progress (username, def_id, current_value)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (username, def_id) DO UPDATE SET
                        current_value = user_progress.current_value + EXCLUDED.current_value,
                        updated_at = NOW()
                    RETURNING current_value;
                """
                cur.execute(progress_query, (self.username, def_id, amount))
                new_total = cur.fetchone()[0]

                # 2. Fetch the thresholds for this achievement from the definition
                cur.execute("SELECT type, config FROM achievement_definitions WHERE id = %s", (def_id,))
                ach_type, config = cur.fetchone()
                
                newly_unlocked_tier = None
                
                # 3. Check for Tier-Ups (Badges) or Rank-Ups (Mastery)
                if ach_type == 'badge' and 'tiers' in config:
                    # Sort tiers by value to find the highest one we just passed
                    # e.g., if new_total is 11, and bronze is 10, we unlock bronze
                    sorted_tiers = sorted(config['tiers'].items(), key=lambda x: x[1], reverse=True)
                    for tier_name, threshold in sorted_tiers:
                        if new_total >= threshold:
                            # Check if we already have this tier
                            cur.execute("""
                                SELECT 1 FROM user_unlocks 
                                WHERE username = %s AND def_id = %s AND tier = %s
                            """, (self.username, def_id, tier_name))
                            
                            if not cur.fetchone():
                                newly_unlocked_tier = tier_name
                                # Save the new unlock!
                                cur.execute("""
                                    INSERT INTO user_unlocks (username, def_id, tier)
                                    VALUES (%s, %s, %s)
                                """, (self.username, def_id, tier_name))
                            break # Only unlock the highest possible tier

                # 4. Record the entry in the ledger
                ledger_query = """
                    INSERT INTO game_grants_ledger (game_id, username, def_id, change_amount, tier_unlocked)
                    VALUES (%s, %s, %s, %s, %s);
                """
                cur.execute(ledger_query, (game_id, self.username, def_id, amount, newly_unlocked_tier))
                
            conn.commit()

        if newly_unlocked_tier:
            print(f"🎉 ACHIEVEMENT UNLOCKED: {def_id} - {newly_unlocked_tier.upper()}!")
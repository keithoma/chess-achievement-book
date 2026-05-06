import json
from database.connection import get_connection

def update_badge_progress(badge_slug, game_id):
    """
    Increments the count for a badge and links it to a specific game.
    The UNIQUE constraint on game_badges prevents double-counting.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # 1. Attempt to link the game to the badge
            # If (game_id, badge_slug) already exists, this does nothing.
            cur.execute("""
                INSERT INTO game_badges (game_id, badge_slug)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id;
            """, (game_id, badge_slug))
            
            was_added = cur.fetchone()
            
            # 2. If it was a new link, increment the master count and check tiers
            if was_added:
                cur.execute("""
                    UPDATE user_badges 
                    SET current_count = current_count + 1,
                        last_earned_at = NOW()
                    WHERE badge_slug = %s
                    RETURNING current_count, tier_thresholds;
                """, (badge_slug,))
                
                result = cur.fetchone()
                if result:
                    new_count, thresholds = result
                    # Update the highest tier reached if new_count matches a threshold
                    if new_count in thresholds:
                        cur.execute("""
                            UPDATE user_badges 
                            SET current_tier = %s 
                            WHERE badge_slug = %s;
                        """, (new_count, badge_slug))
        conn.commit()

def process_achievements():
    """Iterates through games and checks which badges are triggered."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Fetch games we haven't processed yet or just process all for now
            cur.execute("SELECT id, score, speed, game_data FROM games;")
            games = cur.fetchall()

    for game_id, score, speed, game_data in games:
        # 1. General 'Played' Badge
        update_badge_progress('played-game', game_id)

        # 2. Specific 'Played' Speed Badge
        speed_slug = f"played-{speed.lower()}"
        update_badge_progress(speed_slug, game_id)

        # 3. Winning Logic
        # We check the 'players' object in game_data to see which side the user was on
        # For this example, let's assume 'noctu2nality' is the player.
        is_white = game_data['players']['white']['id'] == 'noctu2nality'
        is_win = (is_white and score == '1-0') or (not is_white and score == '0-1')

        if is_win:
            update_badge_progress('won-game', game_id)
            update_badge_progress(f"won-{speed.lower()}", game_id)

if __name__ == "__main__":
    print("🏆 Scanning games for badges...")
    process_achievements()
    print("✅ Achievement scan complete!")
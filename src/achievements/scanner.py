import os
import re
from datetime import datetime
import logging
import argparse
from src.database.connection import get_connection
from src.database.achievements_db import setup_achievements_db
from .metrics import GameMetrics
from .engine import AchievementEngine

logger = logging.getLogger(__name__)

def export_annotated_pgn(game_data, username):
    """Saves the annotated PGN to the debug folder with custom naming."""
    # 1. Setup path
    output_dir = "debug/pgn_files"
    os.makedirs(output_dir, exist_ok=True)

    # 2. Check if we actually have the annotated PGN
    annotated_content = game_data.get('annotated_pgn')
    if not annotated_content:
        return # Can't export what hasn't been analyzed!

    # 3. Format Filename Data
    # Get yyyymmdd from the timestamp
    ts = game_data.get('timestamp', 0)
    date_str = datetime.fromtimestamp(ts).strftime("%Y%m%d")

    # Determine color
    is_white = game_data['players']['white']['id'].lower() == username.lower()
    color_str = "white" if is_white else "black"

    # Sanitize Opening Name (remove characters like : / \ ?)
    opening_name = game_data.get('opening', {}).get('name', 'Unknown Opening')
    safe_opening = re.sub(r'[\\/*?:"<>|]', "", opening_name)

    filename = f"{date_str} {color_str} {safe_opening}.pgn"
    file_path = os.path.join(output_dir, filename)

    # 4. Write File
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(annotated_content)
    
    # Optional: logger.debug(f"📄 Exported PGN: {filename}")

def process_achievements(username='noctu2nality', limit=None, show_all=False):
    """Main execution loop to batch process games through the engine."""
    username = username.lower()
    setup_achievements_db()
    
    logger.info(f"🏆 Scanning games for {username}...")
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            engine = AchievementEngine(cur, username, show_all=show_all)

            # Modified to respect the limit and pull the most recent games first
            query = "SELECT id, score, speed, game_data FROM games ORDER BY played_at DESC"
            if limit:
                query += f" LIMIT {int(limit)}"
                
            cur.execute(query)
            games = cur.fetchall()
            logger.debug(f"Loaded {len(games)} games from the database.")

            for game_id, score, speed, game_data in games:
                logger.debug(f"Analyzing game {game_id}...")
                metrics = GameMetrics(game_id, score, speed, game_data, username)
                engine.evaluate(metrics)
                if export_pgn:
                    export_annotated_pgn(game_data, username)
            
            conn.commit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process Lichess games and unlock achievements.")
    parser.add_argument("--debug", action="store_true", help="Enable highly verbose debug logging")
    parser.add_argument("--user", type=str, default="noctu2nality", help="Lichess username to target")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    if args.debug:
        logger.debug("🪲 DEBUG MODE ACTIVATED: Verbose achievement tracing is ON.")

    process_achievements(username=args.user)
    logger.info("✅ Achievement scan complete!")
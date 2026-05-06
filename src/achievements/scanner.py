import logging
import argparse
from src.database.connection import get_connection
from src.database.achievements_db import setup_achievements_db
from .metrics import GameMetrics
from .engine import AchievementEngine

logger = logging.getLogger(__name__)

def process_achievements(username='noctu2nality'):
    """Main execution loop to batch process games through the engine."""
    username = username.lower()
    setup_achievements_db()
    
    logger.info(f"🏆 Scanning games for {username}...")
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            engine = AchievementEngine(cur, username)

            cur.execute("SELECT id, score, speed, game_data FROM games;")
            games = cur.fetchall()
            logger.debug(f"Loaded {len(games)} games from the database.")

            for game_id, score, speed, game_data in games:
                logger.debug(f"Analyzing game {game_id}...")
                metrics = GameMetrics(game_id, score, speed, game_data, username)
                engine.evaluate(metrics)
            
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
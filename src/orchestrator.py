import logging
from tqdm import tqdm

from src.database.achievements_db import setup_achievements_db
from src.database.ingest_games import fetch_and_store_games
from src.achievements.scanner import process_achievements
from src.analysis.engine_runner import analyze_pending_games

logger = logging.getLogger(__name__)

def run_pipeline(args):
    """
    Executes the Chess Achievement Book workflow.
    """
    # 0. Infrastructure
    setup_achievements_db()

    # 1. Ingestion
    if not args.skip_fetch:
        logger.info("📥 Fetching games for %s", args.user)
        fetch_and_store_games(username=args.user, limit=args.limit)
    
    # 2. Engine Analysis
    if not args.skip_analysis:
        # We wrap the logic here if we want a high-level progress bar,
        # but typically we'll put the tqdm inside analyze_pending_games.
        logger.info("🧠 Commencing Stockfish Deep Analysis...")
        analyze_pending_games(limit=args.limit)
    
    # 3. Achievement Scanning
    logger.info("🏆 Scanning for achievements...")
    process_achievements(
        username=args.user,
        limit=args.limit,
        show_all=args.show_achievements,
        export_pgn=args.export_pgn
    )

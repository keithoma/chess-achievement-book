import logging
import argparse

from src.database.ingest_games import fetch_and_store_games
from src.achievements.scanner import process_achievements
from src.analysis.engine_runner import analyze_pending_games
from src.database.achievements_db import setup_achievements_db

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Chess Achievement Tracker")
    parser.add_argument("-l", "--limit", type=int, default=50, 
                        help="Number of recent games to pull from Lichess (Default: 50)")
    parser.add_argument("-u", "--user", type=str, default="noctu2nality", 
                        help="Lichess username to target")
    parser.add_argument("--skip-fetch", action="store_true", 
                        help="Skip pulling from Lichess and only scan the local database")
    parser.add_argument("--skip-analysis", action="store_true", 
                        help="Skip the heavy Stockfish Depth 22 analysis step")
    parser.add_argument("--scan-all", action="store_true", 
                        help="Ignore the limit and scan EVERY game in the database")
    parser.add_argument("--show-achievements", action="store_true", 
                        help="Print all qualified achievements for the game, even if already granted")
    parser.add_argument("--debug", action="store_true", 
                        help="Enable highly verbose debug logging")
    parser.add_argument("--export-pgn", action="store_true", 
                    help="Export annotated PGNs to /debug/pgn_files/")
    
    args = parser.parse_args()

    # Configure global logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    print(f"♟️  Starting Chess Tracker for '{args.user}'")
    
    # Step 1: Ingestion
    if not args.skip_fetch:
        print(f"📥 Fetching the last {args.limit} game(s)...")
        fetch_and_store_games(username=args.user, limit=args.limit)
    else:
        print("⏭️  Skipping Lichess API fetch...")

    # Step 1.5: Deep Engine Analysis
    if not args.skip_analysis:
        print("🧠 Running Stockfish Deep Analysis on pending games...")
        # You will need to create this function to loop through games in your DB 
        # that don't have move_evals yet, run stockfish_analyzer.py, and save the results.
        analyze_pending_games(limit=args.limit)
    else:
        print("⏭️  Skipping heavy Stockfish analysis...")

    # Step 2: Achievement Scanning
    print("🏆 Preparing database and scanning for achievements...")
    
    # 1. Run your setup first!
    setup_achievements_db() 
    
    # 2. Run the scanner
    process_achievements(
        username=args.user, 
        limit=args.limit, 
        show_all=args.show_achievements,
        export_pgn=args.export_pgn
    )
    
    print("✅ All done!")

if __name__ == "__main__":
    main()
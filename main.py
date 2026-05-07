"""
Chess Achievement Book: CLI Entry Point

This module orchestrates the end-to-end workflow of the Chess Achievement Book:
1. Ingestion: Pulls recent games from the Lichess API for a specific user.
2. Analysis: Runs deep Stockfish evaluation to identify brilliancies and novelties.
3. Achievement Scanning: Evaluates games against a ledger of trophies and 
   exports annotated PGNs with professional NAG symbols.

Usage:
```bash
uv run main.py --user <username> --limit 50 --export-pgn
```

Author: Kei Thoma
License: MIT
"""

import logging
import argparse
import sys

from src.orchestrator import run_pipeline
from src.display import show_profile, show_history

def main():
    """
    Parse command-line arguments and initiate the achievement tracking pipeline.
    """
    parser = argparse.ArgumentParser(description="Chess Achievement Tracker")
    parser.add_argument("-l", "--limit", type=int, default=1,
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
                        help=(
                            "Print all qualified achievements for the game, "
                            "even if already granted"
                        ))
    parser.add_argument("--debug", action="store_true",
                        help="Enable highly verbose debug logging")
    parser.add_argument("--export-pgn", action="store_true",
                        help="Export annotated PGNs to /debug/pgn_files/")
    parser.add_argument("--profile", action="store_true", 
                        help="Display the user's unlocked trophies and mastery")
    parser.add_argument("--history", action="store_true", 
                        help="Display the recent game ledger (what was earned per game)")
    
    args = parser.parse_args()
    
    # Check if we are just displaying UI, otherwise run the pipeline
    if args.profile:
        show_profile(args.user)
        sys.exit(0)
        
    if args.history:
        show_history(args.user, limit=5)
        sys.exit(0)

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout
    )

    try:
        run_pipeline(args)
        logging.info("✅ All tasks finished.")
    except KeyboardInterrupt:
        logging.warning("\nInterrupted by user. Exiting...")
        sys.exit(1)
    except Exception as e: # pylint: disable=broad-exception-caught
        logging.error("Pipeline failed: %s", e, exc_info=args.debug)
        sys.exit(1)

if __name__ == "__main__":
    main()

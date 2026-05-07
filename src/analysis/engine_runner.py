import json
import logging
from src.database.connection import get_connection
from stockfish_analyzer import analyze_game_data

logger = logging.getLogger(__name__)

def build_pgn_from_json(game_data):
    """
    python-chess needs a PGN string to read. This quickly rebuilds a 
    minimal PGN from your JSONB data so the engine can parse it.
    """
    headers = [
        f'[Event "{game_data.get("speed", "rapid").title()} game"]',
        f'[Site "https://lichess.org/{game_data["id"]}"]',
        f'[White "{game_data["players"]["white"]["name"]}"]',
        f'[Black "{game_data["players"]["black"]["name"]}"]',
        f'[Result "{game_data["score"]}"]',
        f'[ECO "{game_data["opening"]["eco"]}"]',
        f'[Opening "{game_data["opening"]["name"]}"]'
    ]
    moves = game_data.get('moves', '')
    return "\n".join(headers) + "\n\n" + moves + "\n"

def analyze_pending_games(limit=None):
    """
    Finds games in the database that haven't been analyzed by your custom 
    Stockfish yet, runs them, and updates the JSONB payload.
    """
    # 1. Query for unprocessed games
    query = """
        SELECT id, game_data 
        FROM games 
        WHERE game_data->>'local_analysis_complete' IS NULL
    """
    if limit:
        query += f" LIMIT {limit}"

    pending_games = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                pending_games = cur.fetchall()
    except Exception as e:
        logger.error(f"❌ Failed to fetch pending games: {e}")
        return

    if not pending_games:
        logger.info("✨ No pending games require Stockfish analysis.")
        return

    logger.info(f"⚙️  Found {len(pending_games)} game(s) needing deep analysis. Starting engines...")

    # 2. Process each game
    for game_id, game_data in pending_games:
        logger.info(f"  -> Analyzing {game_id} (This may take a moment)")
        
        # Build the PGN and run it through your custom logic
        pgn_string = build_pgn_from_json(game_data)
        
        # NOTE: low_depth=1, high_depth=22 is currently hardcoded here. 
        # Lower high_depth if it takes too long to test!
        annotated_pgn, local_evals = analyze_game_data(pgn_string, low_depth=1, high_depth=22)

        if annotated_pgn:
            # 3. Update the game_data dictionary
            game_data['move_evals'] = local_evals  # Overwrite Lichess evals with yours
            game_data['annotated_pgn'] = annotated_pgn
            game_data['local_analysis_complete'] = True

            # 4. Save it back to the database
            update_query = """
                UPDATE games 
                SET game_data = %s 
                WHERE id = %s
            """
            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(update_query, (json.dumps(game_data), game_id))
                    conn.commit()
                logger.info(f"  ✅ Saved analysis for {game_id}")
            except Exception as e:
                logger.error(f"  ❌ DB Update failed for {game_id}: {e}")
        else:
            logger.error(f"  ⚠️ Engine failed to analyze {game_id}")

    logger.info("🏁 Stockfish analysis batch complete!")
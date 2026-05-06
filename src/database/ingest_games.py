import json
import requests
import chess
import logging
import argparse
from datetime import datetime, timezone

# Assuming this is your local module
from database.connection import get_connection 

# Define the boundary as a timezone-aware datetime object
# 2026-05-01 00:00:00 UTC
MAY_FIRST_2026 = datetime(2026, 5, 1, tzinfo=timezone.utc)

# Initialize the logger (configuration happens in __main__)
logger = logging.getLogger(__name__)

def extract_game_events(moves_string):
    board = chess.Board()
    moves = moves_string.split() if isinstance(moves_string, str) else moves_string
    events = {"captures": [], "en_passants": []}
    
    for ply, move_str in enumerate(moves):
        try:
            move = board.parse_san(move_str)
        except ValueError as e:
            logger.debug(f"  [!] Invalid SAN move '{move_str}' at ply {ply}: {e}")
            continue

        if board.is_en_passant(move):
            events["en_passants"].append({
                "ply": ply + 1,
                "move": move_str,
                "player": "white" if board.turn == chess.WHITE else "black"
            })

        if board.is_capture(move):
            if board.is_en_passant(move):
                captured_piece = "pawn"
            else:
                piece = board.piece_at(move.to_square)
                captured_piece = chess.piece_name(piece.piece_type) if piece else "unknown"

            events["captures"].append({
                "ply": ply + 1,
                "piece_taken": captured_piece,
                "move": move_str,
                "player": "white" if board.turn == chess.WHITE else "black"
            })

        board.push(move)
        
    return events

def setup_db():
    """Ensures the games table exists before we start ingesting."""
    query = """
    CREATE TABLE IF NOT EXISTS games (
        id TEXT PRIMARY KEY,
        platform TEXT,
        played_at TIMESTAMPTZ,
        rated BOOLEAN,
        speed TEXT,
        score TEXT,
        game_data JSONB
    );
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
        conn.commit()
    logger.debug("Database table 'games' verified.")

def save_game_to_db(game_data: dict):
    """Inserts a single formatted game into the PostgreSQL database."""
    query = """
        INSERT INTO games (id, platform, played_at, rated, speed, score, game_data)
        VALUES (%s, %s, to_timestamp(%s), %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING;
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (
                    game_data['id'],
                    game_data['platform'],
                    game_data['timestamp'],
                    game_data['is_rated'],
                    game_data['speed'],
                    game_data['score'],
                    json.dumps(game_data)
                ))
                # Check if a row was actually inserted or if it was a conflict
                inserted = cur.rowcount > 0
            conn.commit()
            
            if inserted:
                logger.info(f"💾 {game_data['id']}: Saved to Database ({game_data['speed']})")
            else:
                logger.debug(f"⏭️ {game_data['id']}: Skipped DB Insert (Already Exists)")
    except Exception as e:
        logger.error(f"❌ {game_data.get('id', 'unknown')}: Database Error: {e}")

def parse_player(player_data):
    if 'aiLevel' in player_data:
        level = player_data['aiLevel']
        return {
            "id": f"stockfish_level_{level}",
            "name": f"Lichess AI Level {level}",
            "rating": 1500,
            "is_bot": True,
            "patron": False
        }
    
    user_info = player_data.get('user', {})
    return {
        "id": user_info.get('id', 'unknown'),
        "name": user_info.get('name', 'Unknown'),
        "rating": player_data.get('rating', 1500),
        "is_bot": user_info.get('title') == 'BOT',
        "patron": user_info.get('patron', False)
    }

def get_score(winner_flag):
    if winner_flag == 'white': return '1-0'
    if winner_flag == 'black': return '0-1'
    return '1/2-1/2'

def format_game_data(raw_game):
    clock_info = raw_game.get('clock', {})
    
    move_evals = []
    if 'analysis' in raw_game:
        for ply in raw_game['analysis']:
            if 'eval' in ply:
                move_evals.append(ply['eval'])
            elif 'mate' in ply:
                move_evals.append(9999 if ply['mate'] > 0 else -9999)

    raw_moves_string = raw_game.get('moves', '')
    logger.debug(f"  -> Extracting events for {raw_game.get('id')} ({len(raw_moves_string.split())} plies)")
    game_events = extract_game_events(raw_moves_string)

    formatted_game = {
        "id": raw_game.get('id'),
        "platform": "lichess",
        "timestamp": raw_game.get('createdAt', 0) // 1000, 
        "is_rated": raw_game.get('rated', False),
        "is_friend": raw_game.get('source') == 'friend',
        "speed": raw_game.get('speed', 'unknown'),
        "rules": {
            "initial": clock_info.get('initial', 0),
            "increment": clock_info.get('increment', 0)
        },
        "players": {
            "white": parse_player(raw_game.get('players', {}).get('white', {})),
            "black": parse_player(raw_game.get('players', {}).get('black', {}))
        },
        "score": get_score(raw_game.get('winner')),
        "termination": raw_game.get('status', 'unknown'),
        "opening": {
            "eco": raw_game.get('opening', {}).get('eco', ''),
            "name": raw_game.get('opening', {}).get('name', '')
        },
        "moves": raw_moves_string,
        "move_times": raw_game.get('clocks', []),
        "move_evals": move_evals,
        "division": raw_game.get('division', {}),
        "captures": game_events["captures"],
        "en_passants": game_events["en_passants"]
    }
    
    return formatted_game

def fetch_and_store_games(username: str, limit: int = 50):
    setup_db()
    url = f"https://lichess.org/api/games/user/{username}"
    
    params = {
        'max': limit,
        'perfType': 'ultraBullet,bullet,blitz,rapid,classical', 
        'moves': 'true',
        'opening': 'true',
        'clocks': 'true',
        'evals': 'true' 
    }
    headers = {'Accept': 'application/x-ndjson'}

    logger.info(f"📡 Filtering games for {username} (Since May 1st, Limit: {limit})...")
    logger.debug(f"API Request URL: {url}")
    logger.debug(f"API Request Params: {params}")
    
    with requests.get(url, params=params, headers=headers, stream=True) as response:
        if response.status_code != 200:
            logger.error(f"❌ API Error: HTTP {response.status_code}")
            logger.error(f"Response Body: {response.text}")
            return

        count = 0
        total_lines_read = 0

        for line in response.iter_lines():
            if not line: continue
            total_lines_read += 1
            
            raw_game = json.loads(line)
            game_id = raw_game.get('id')
            speed = raw_game.get('speed', 'unknown')
            moves_string = raw_game.get('moves', '')
            num_moves = len(moves_string.split())
            
            logger.debug(f"--- Processing Line {total_lines_read} | Game ID: {game_id} | Speed: {speed} ---")

            # 1. Date Check
            createdAt_ms = raw_game.get('createdAt')
            if not createdAt_ms:
                logger.debug(f"  [!] Skipped {game_id}: Missing 'createdAt' timestamp.")
                continue

            game_time = datetime.fromtimestamp(createdAt_ms / 1000, tz=timezone.utc)
            logger.debug(f"  -> Date: {game_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")

            if game_time < MAY_FIRST_2026:
                logger.info(f"📅 Reached {game_time.strftime('%Y-%m-%d')}. Stopping fetch.")
                break
            
            # 2. Variants Check (Initial FEN usually implies Chess960 or custom start)
            if 'initialFen' in raw_game:
                logger.debug(f"  [!] Skipped {game_id}: Custom Initial FEN (Likely variant).")
                continue
                
            # 3. Game Length Check
            if num_moves < 4:
                logger.debug(f"  [!] Skipped {game_id}: Game too short ({num_moves} plies).")
                continue
            
            # Formatting and Saving
            clean_game = format_game_data(raw_game)
            save_game_to_db(clean_game)
            count += 1

        logger.info(f"🏁 Finished! Read {total_lines_read} lines, ingested {count} games.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Lichess games into the database.")
    parser.add_argument("--debug", action="store_true", help="Enable highly verbose debug logging")
    parser.add_argument("--limit", type=int, default=50, help="Max number of games to request from Lichess")
    parser.add_argument("--user", type=str, default="noctu2nality", help="Lichess username to target")
    args = parser.parse_args()

    # Configure the logger based on the --debug flag
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    if args.debug:
        logger.debug("🪲 DEBUG MODE ACTIVATED")

    fetch_and_store_games(args.user, limit=args.limit)
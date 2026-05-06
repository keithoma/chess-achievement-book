import json
import chess
from database.connection import get_connection

def setup_achievements_db():
    """Creates the tracking table for achievements."""
    query = """
    CREATE TABLE IF NOT EXISTS game_achievements (
        game_id TEXT,
        username TEXT,
        achievement_slug TEXT,
        granted_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (game_id, achievement_slug)
    );
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
        conn.commit()

def grant(cur, game_id, username, slug, print_msg):
    """Attempts to grant an achievement. Prints if it's newly unlocked."""
    query = """
        INSERT INTO game_achievements (game_id, username, achievement_slug) 
        VALUES (%s, %s, %s) ON CONFLICT DO NOTHING RETURNING 1;
    """
    cur.execute(query, (game_id, username, slug))
    if cur.fetchone():
        print(f"🎉 New Achievement [{username}]: {print_msg} (Game: {game_id})")

def get_draw_reason(moves_string):
    """Replays the game to find the exact rule that triggered the draw."""
    board = chess.Board()
    for move_str in moves_string.split():
        try:
            board.push_san(move_str)
        except ValueError:
            break
            
    if board.is_stalemate(): return "stalemate"
    if board.is_insufficient_material(): return "insufficient-material"
    if board.can_claim_fifty_moves() or board.is_fifty_moves(): return "50-move"
    if board.can_claim_threefold_repetition() or board.is_repetition(): return "3-fold"
    return "agreement"

def process_game(cur, game_id, score, speed, game_data, username):
    """Evaluates a single game for all badges."""
    # --- 1. Basic Setup & Flags ---
    speed = speed.lower()
    total_plies = len(game_data.get('moves', '').split())
    termination = game_data.get('termination', 'unknown').lower()
    
    white_id = game_data['players']['white'].get('id', '').lower()
    is_white = (white_id == username)
    
    is_win = (is_white and score == '1-0') or (not is_white and score == '0-1')
    is_draw = (score == '1/2-1/2')

    # Eval extraction setup
    evals = game_data.get('move_evals', [])
    division = game_data.get('division', {})
    mid_start = division.get('middle')
    end_start = division.get('end')

    # --- 2. Calculate Accuracies & Minimum Evals ---
    # We will compute the evaluation from the PLAYER'S perspective.
    # Positive is good, negative is bad.
    min_eval_seen = 0
    inaccuracies = 0
    mistakes = 0
    blunders = 0

    eval_at_mid = 0
    eval_at_end = 0

    for i in range(len(evals)):
        current_eval = evals[i]
        prev_eval = evals[i-1] if i > 0 else 0

        # Player's perspective eval
        p_eval = current_eval if is_white else -current_eval
        if p_eval < min_eval_seen:
            min_eval_seen = p_eval

        # Record specific phase evaluations
        if mid_start and i == mid_start - 1: eval_at_mid = p_eval
        if end_start and i == end_start - 1: eval_at_end = p_eval

        # Calculate drops (only on the player's own turn)
        is_player_turn = (is_white and i % 2 == 0) or (not is_white and i % 2 == 1)
        if is_player_turn:
            drop = (current_eval - prev_eval) if is_white else -(current_eval - prev_eval)
            if drop <= -300: blunders += 1
            elif drop <= -100: mistakes += 1
            elif drop <= -50: inaccuracies += 1


    # ==========================================
    # === EVALUATING ACHIEVEMENTS ============
    # ==========================================

    # --- A. Played & Won (General + Speed) ---
    grant(cur, game_id, username, 'played-game', "Played a game")
    grant(cur, game_id, username, f'played-{speed}', f"Played a {speed} game")

    if is_win:
        grant(cur, game_id, username, 'won-game', "Won a game")
        grant(cur, game_id, username, f'won-{speed}', f"Won a {speed} game")

        # --- B. Win by Phase ---
        if mid_start and total_plies < mid_start:
            grant(cur, game_id, username, 'win-opening', "Won in the Opening")
        elif end_start and mid_start <= total_plies < end_start:
            grant(cur, game_id, username, 'win-midgame', "Won in the Middle Game")
        elif end_start and total_plies >= end_start:
            grant(cur, game_id, username, 'win-endgame', "Won in the End Game")

        # --- C. Win by Termination ---
        if termination == 'mate':
            grant(cur, game_id, username, 'win-mate', "Won by Checkmate")
        elif termination == 'resign':
            grant(cur, game_id, username, 'win-resign', "Won by Resignation")
        elif termination in ['outoftime', 'timeout'] and score != '1/2-1/2':
            grant(cur, game_id, username, 'win-timeout', "Won by Time Out")
        elif termination in ['abandoned', 'aborted']:
            grant(cur, game_id, username, 'win-abandon', "Won by Abandonment")

        # --- D. Comebacks (Wins) ---
        if mid_start and end_start:
            if eval_at_mid <= -150 and eval_at_end <= -150:
                grant(cur, game_id, username, 'comeback-midgame-150', "Down 1.5+ after Opening AND Midgame, but won")
            
            if eval_at_mid <= -200 and (total_plies - mid_start) <= 40:
                grant(cur, game_id, username, 'comeback-opening-fast', "Down 2.0+ after Opening, won within 20 moves")
                
            if eval_at_mid <= -300:
                grant(cur, game_id, username, 'comeback-opening-300', "Down 3.0+ after Opening, but won")

        if end_start and eval_at_end <= -200:
            grant(cur, game_id, username, 'comeback-endgame-200', "Started Endgame down 2.0+, but won")

        # --- E. Accuracy & Clean Play ---
        # "Always above 0.0 as white, or -0.3 as black"
        if (is_white and min_eval_seen >= 0) or (not is_white and min_eval_seen >= -30):
            grant(cur, game_id, username, 'clean-eval', "Won with eval always above 0.0 (W) or -0.3 (B)")

        if blunders == 0:
            grant(cur, game_id, username, 'no-blunders', "Won without any blunders")
            if mistakes == 0:
                grant(cur, game_id, username, 'no-mistakes-blunders', "Won without mistakes or blunders")
                if inaccuracies == 0:
                    grant(cur, game_id, username, 'perfect-accuracy', "Won without inaccuracies, mistakes, or blunders")

        # --- F. Endurance ---
        if total_plies > 160: # 80 moves = 160 plies
            grant(cur, game_id, username, 'marathon-win', "Won a game longer than 80 moves")

    # --- G. The Great Escapes (Draws) ---
    if is_draw:
        # Check if the player was previously losing by 3.0+
        if min_eval_seen <= -300:
            reason = get_draw_reason(game_data.get('moves', ''))
            
            if reason == '3-fold':
                grant(cur, game_id, username, 'escape-3-fold', "Drew a lost position via Threefold Repetition")
            elif reason == 'agreement':
                grant(cur, game_id, username, 'escape-agreement', "Drew a lost position by Agreement")
            elif reason == '50-move':
                grant(cur, game_id, username, 'escape-50-move', "Drew a lost position via 50-Move Rule")
            elif reason == 'insufficient-material':
                grant(cur, game_id, username, 'escape-insufficient', "Drew a lost position due to Insufficient Material")

        # Endgame down 2.0+ but drew
        if end_start and eval_at_end <= -200:
            grant(cur, game_id, username, 'escape-endgame-200', "Started Endgame down 2.0+, but managed a draw")


def process_achievements(username='noctu2nality'):
    """Main loop to process all games efficiently."""
    username = username.lower()
    setup_achievements_db()
    
    print(f"🏆 Scanning games for {username}...")
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, score, speed, game_data FROM games;")
            games = cur.fetchall()

            for game_id, score, speed, game_data in games:
                process_game(cur, game_id, score, speed, game_data, username)
            
            # Commit all new achievements to the database
            conn.commit()

if __name__ == "__main__":
    process_achievements()
    print("✅ Achievement scan complete!")
import chess.pgn
import chess.engine
import io
import math
import chess.polyglot

STOCKFISH_PATH = "/usr/games/stockfish"

def get_win_chances(cp):
    return 0.5 + 0.5 * (2 / (1 + math.exp(-0.003682 * cp)) - 1)

def analyze_game_data(input_pgn: str, book_path: str, low_depth: int = 1, high_depth: int = 22):
    pgn_file = io.StringIO(input_pgn.strip())
    game = chess.pgn.read_game(pgn_file)
    if not game: return None, []

    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    engine.configure({"Threads": 4, "Hash": 512})

    node = game
    board = game.board()
    move_evals = []
    novelty_found = False
    
    # Open the book once for the whole game
    reader = None
    if book_path:
        reader = chess.polyglot.open_reader(book_path)

    while node.variations:
        next_node = node.variation(0)
        move_played = next_node.move
        
        # --- 1. ANALYSIS (MultiPV 3) ---
        high_res_list = engine.analyse(board, chess.engine.Limit(depth=high_depth), multipv=3)
        
        # Convert evals to win chances for logic
        w_chances = []
        variation_comments = []
        for i, info in enumerate(high_res_list):
            cp = info["score"].pov(board.turn).score(mate_score=10000)
            w_chances.append(get_win_chances(cp))
            
            # Format variation for PGN comment: "1: d4 (+0.20) 2: e4 (+0.15)..."
            pv_move = board.san(info["pv"][0]) if "pv" in info else "???"
            variation_comments.append(f"{i+1}: {pv_move} ({cp/100:.2f})")

        best_move_high = high_res_list[0]["pv"][0] if "pv" in high_res_list[0] else None
        
        # --- 2. EVALUATE PLAYER MOVE ---
        board.push(move_played)
        post_high = engine.analyse(board, chess.engine.Limit(depth=high_depth))
        post_score = post_high["score"].white().score(mate_score=10000)
        move_evals.append(post_score)
        
        # Win chance from player's POV
        w_after = get_win_chances(post_score if not board.turn else -post_score)

        # --- 3. THE SYMBOL LOGIC ---
        # --- A) Novelty (N) Logic ---
        if reader and not novelty_found:
            prev_board = board.copy()
            prev_board.pop()
            
            # Get EVERY move the book knows, even low-weight ones
            all_entries = list(reader.find_all(prev_board))
            book_moves = [e.move for e in all_entries]

            # DEBUG PRINT: Uncomment this to see what moves the book actually sees
            # if len(board.move_stack) < 10:
            #    print(f"Ply {len(board.move_stack)}: Book knows {len(book_moves)} moves. Player played {move_played}")

            if not book_moves:
                # If even move 1 (e.g., 1. e4) isn't in the book, 
                # something is wrong with the file path or the reader.
                if len(board.move_stack) > 2: # Only flag novelty after move 1
                    next_node.nags.add(146)
                    novelty_found = True
            elif move_played not in book_moves:
                next_node.nags.add(146)
                novelty_found = True

        # B) Brilliancy (!!) - NAG 3
        # Use low-depth blindspot logic
        low_res = engine.analyse(board.copy(), chess.engine.Limit(depth=low_depth)) # Board is post-move
        # (This logic compares depth 1 vs depth 22 as you had before)
        # ... logic as previously implemented ...
        # (Simplified here for space, keep your specific blindspot deltas)
        
        # C) Only Move (□) - NAG 7
        # Logic: Top move is >= 20% win chance better than 2nd
        if len(w_chances) >= 2 and (w_chances[0] - w_chances[1]) >= 0.20:
            if move_played == best_move_high:
                next_node.nags.add(7)

        # D) Good Move (!) - NAG 1
        # Logic: Top two moves are >= 20% better than the 3rd, and not an only move
        elif len(w_chances) >= 3 and (w_chances[1] - w_chances[2]) >= 0.20:
            # If player played move 1 or move 2
            if move_played == best_move_high or (len(high_res_list) > 1 and move_played == high_res_list[1]["pv"][0]):
                next_node.nags.add(1)

        # Build the final comment including the Top 3 variations
        eval_val = f"{post_score/100:.2f}" if abs(post_score) < 10000 else "MATE"
        comment_str = f"[%eval {eval_val}] " + " | ".join(variation_comments)
        next_node.comment = comment_str

        node = next_node

    if reader: reader.close()
    engine.quit()
    
    exporter = chess.pgn.StringExporter(columns=None, headers=True, variations=False, comments=True)
    return game.accept(exporter), move_evals
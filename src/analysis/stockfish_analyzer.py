import chess.pgn
import chess.engine
import io
import math
import chess.polyglot

STOCKFISH_PATH = "/usr/games/stockfish"

def get_win_chances(cp):
    """Sigmoid conversion: centipawns -> winning probability (0.0 to 1.0)."""
    return 0.5 + 0.5 * (2 / (1 + math.exp(-0.003682 * cp)) - 1)

def analyze_game_data(input_pgn: str, book_path: str, low_depth: int = 8, high_depth: int = 22):
    pgn_file = io.StringIO(input_pgn.strip())
    game = chess.pgn.read_game(pgn_file)
    if not game: 
        return None, []

    # Initialize Engine
    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    engine.configure({"Threads": 4, "Hash": 512})

    node = game
    board = game.board()
    move_evals = []
    novelty_found = False
    
    # Open the Master Book
    reader = None
    if book_path:
        try:
            reader = chess.polyglot.open_reader(book_path)
        except FileNotFoundError:
            print(f"Warning: Opening book not found at {book_path}")

    while node.variations:
        next_node = node.variation(0)
        move_played = next_node.move
        
        # --- 1. PRE-MOVE ANALYSIS (The Baseline) ---
        
        # A) High Depth (The Truth) - MultiPV 3
        high_res_list = engine.analyse(board, chess.engine.Limit(depth=high_depth), multipv=3)
        
        w_chances_high = []
        variation_comments = []
        for i, info in enumerate(high_res_list):
            cp = info["score"].pov(board.turn).score(mate_score=10000)
            w_chances_high.append(get_win_chances(cp))
            
            pv_move = board.san(info["pv"][0]) if "pv" in info else "???"
            variation_comments.append(f"{i+1}: {pv_move} ({cp/100:.2f})")

        best_move_high = high_res_list[0]["pv"][0] if "pv" in high_res_list[0] else None

        # B) Low Depth (The Blindspot)
        low_res_before = engine.analyse(board, chess.engine.Limit(depth=low_depth))
        w_low_best = get_win_chances(low_res_before["score"].pov(board.turn).score(mate_score=10000))

        # --- 2. EXECUTE MOVE & POST-MOVE ANALYSIS ---
        
        # Check Novelty (N) before pushing the move
        if reader and not novelty_found:
            all_entries = list(reader.find_all(board))
            book_moves = [e.move for e in all_entries]

            if not book_moves:
                if len(board.move_stack) > 2:
                    next_node.nags.add(146) # N
                    novelty_found = True
            elif move_played not in book_moves:
                next_node.nags.add(146) # N
                novelty_found = True

        board.push(move_played)
        
        # C) Post-Move High Depth
        post_high = engine.analyse(board, chess.engine.Limit(depth=high_depth))
        post_score_white = post_high["score"].white().score(mate_score=10000)
        move_evals.append(post_score_white)
        
        # Win chance for the person who just moved
        w_after = get_win_chances(post_score_white if not board.turn else -post_score_white)

        # D) Post-Move Low Depth
        post_low = engine.analyse(board, chess.engine.Limit(depth=low_depth))
        # Note: evaluate from POV of player who just moved
        w_low_move = get_win_chances(post_low["score"].pov(not board.turn).score(mate_score=10000))

        # --- 3. SYMBOL LOGIC (NAGS) ---

        # B) Brilliancy (!!) - NAG 3
        low_delta = w_low_best - w_low_move
        real_delta = w_chances_high[0] - w_after

        # Logic: Low depth hated it (drop >= 20%), high depth loved it (drop < 5%)
        if low_delta >= 0.20 and real_delta < 0.05:
            next_node.nags.add(3) # !!

        # C) Only Move (□) - NAG 7
        elif len(w_chances_high) >= 2 and (w_chances_high[0] - w_chances_high[1]) >= 0.20:
            if move_played == best_move_high:
                next_node.nags.add(7) # □

        # D) Good Move (!) - NAG 1
        elif len(w_chances_high) >= 3 and (w_chances_high[1] - w_chances_high[2]) >= 0.20:
            # Played one of the top 2 good moves
            if move_played == best_move_high or (len(high_res_list) > 1 and move_played == high_res_list[1]["pv"][0]):
                next_node.nags.add(1) # !

        # 4. FINALIZE COMMENT
        eval_str = f"{post_score_white / 100:.2f}" if abs(post_score_white) < 10000 else "MATE"
        comment = f"[%eval {eval_str}] " + " | ".join(variation_comments)
        next_node.comment = comment

        node = next_node

    # Cleanup
    if reader: 
        reader.close()
    engine.quit()

    # Export to PGN string
    exporter = chess.pgn.StringExporter(columns=None, headers=True, variations=False, comments=True)
    return game.accept(exporter), move_evals
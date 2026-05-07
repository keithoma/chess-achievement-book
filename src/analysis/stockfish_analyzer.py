import chess.pgn
import chess.engine
import io
import math

STOCKFISH_PATH = "/usr/games/stockfish"

def get_win_chances(cp):
    return 0.5 + 0.5 * (2 / (1 + math.exp(-0.003682 * cp)) - 1)

def get_judgement(delta):
    if delta >= 0.3: return "Blunder", 4   
    if delta >= 0.2: return "Mistake", 2   
    return None, None

def analyze_game_data(input_pgn: str, low_depth: int = 1, high_depth: int = 14):
    """
    Returns a tuple: (annotated_pgn_string, list_of_centipawn_evals)
    """
    pgn_file = io.StringIO(input_pgn.strip())
    game = chess.pgn.read_game(pgn_file)
    if not game: return None, []

    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    engine.configure({"Threads": 4, "Hash": 512})

    node = game
    board = game.board()
    was_previous_error = False
    
    # Array to feed into GameMetrics later
    move_evals = [] 

    while node.variations:
        next_node = node.variation(0)
        move_played = next_node.move
        
        # --- HIGH DEPTH ---
        high_res_list = engine.analyse(board, chess.engine.Limit(depth=high_depth), multipv=3)
        w_chances_high = [get_win_chances(info["score"].pov(board.turn).score(mate_score=10000)) for info in high_res_list]
        
        best_move_high = high_res_list[0]["pv"][0] if "pv" in high_res_list[0] else None
        best_move_san = board.san(best_move_high) if best_move_high else ""
        is_only_move = len(w_chances_high) >= 2 and (w_chances_high[0] - w_chances_high[1]) >= 0.20

        # --- LOW DEPTH ---
        low_res = engine.analyse(board, chess.engine.Limit(depth=low_depth))
        w_low_best = get_win_chances(low_res["score"].pov(board.turn).score(mate_score=10000))

        # --- EXECUTE MOVE ---
        board.push(move_played)
        
        # --- POST MOVE ANALYSIS ---
        post_high = engine.analyse(board, chess.engine.Limit(depth=high_depth))
        post_score_white = post_high["score"].white().score(mate_score=10000)
        
        # Append to our evals array for GameMetrics
        move_evals.append(post_score_white) 

        w_after = get_win_chances(post_score_white if not board.turn else -post_score_white)
        
        post_low = engine.analyse(board, chess.engine.Limit(depth=low_depth))
        w_low_move = get_win_chances(post_low["score"].pov(not board.turn).score(mate_score=10000))

        # --- LOGIC ---
        low_delta = w_low_best - w_low_move
        real_delta = w_chances_high[0] - w_after

        eval_str = f"{post_score_white / 100:.2f}" if abs(post_score_white) < 10000 else "MATE"
        comment = f"[%eval {eval_str}]"

        is_brilliant = (low_delta >= 0.20 and real_delta < 0.05)

        if is_brilliant:
            next_node.nags.add(3) 
            comment += " !! Brilliancy."
        elif move_played == best_move_high:
            if is_only_move:
                next_node.nags.add(3) 
                comment += " Excellent Move."
            elif len(w_chances_high) >= 3 and (w_chances_high[0] - w_chances_high[2]) >= 0.20:
                next_node.nags.add(1) 
                comment += " Good Move."
        else:
            if was_previous_error and is_only_move:
                comment += f" Missed tactic: {best_move_san} was required."
            
            error_name, error_nag = get_judgement(real_delta)
            if error_name:
                next_node.nags.add(error_nag)
                comment += f" {error_name}."

        was_previous_error = (get_judgement(real_delta)[0] is not None)
        next_node.comment = comment
        node = next_node

    engine.quit()
    
    # Export the annotated game
    exporter = chess.pgn.StringExporter(columns=None, headers=True, variations=False, comments=True)
    annotated_pgn = game.accept(exporter)
    
    return annotated_pgn, move_evals
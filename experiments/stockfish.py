import chess.pgn
import chess.engine
import io
import sys
import math

STOCKFISH_PATH = "/usr/games/stockfish"

def get_win_chances(cp):
    """Sigmoid conversion: centipawns -> winning probability (0.0 to 1.0)."""
    return 0.5 + 0.5 * (2 / (1 + math.exp(-0.003682 * cp)) - 1)

def get_judgement(delta):
    """Lichess standard error thresholds (?? and ? only)."""
    if delta >= 0.3: return "Blunder", 4   # ??
    if delta >= 0.2: return "Mistake", 2   # ?
    return None, None

def analyze_to_pgn(input_pgn: str, low_depth: int = 1, high_depth: int = 22):
    pgn_file = io.StringIO(input_pgn.strip())
    game = chess.pgn.read_game(pgn_file)
    if not game: return

    try:
        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        engine.configure({"Threads": 4, "Hash": 512})
    except FileNotFoundError:
        print(f"❌ Stockfish not found", file=sys.stderr)
        return

    node = game
    board = game.board()
    was_previous_error = False

    print(f"; Reviewing: Truth (D{high_depth}) | Brilliancy Blindspot (D{low_depth})", file=sys.stderr)

    while node.variations:
        next_node = node.variation(0)
        move_played = next_node.move
        
        # --- 1. HIGH DEPTH BASELINE (Truth & Sharpness) ---
        # Get the top 3 moves to see if an 'Only Move' exists
        high_res_list = engine.analyse(board, chess.engine.Limit(depth=high_depth), multipv=3)
        
        w_chances_high = []
        for info in high_res_list:
            cp = info["score"].pov(board.turn).score(mate_score=10000)
            w_chances_high.append(get_win_chances(cp))
        
        best_move_high = high_res_list[0]["pv"][0] if "pv" in high_res_list[0] else None
        best_move_san = board.san(best_move_high) if best_move_high else ""

        # Only Move logic: Is the best move 20% better than the 2nd best?
        is_only_move = False
        if len(w_chances_high) >= 2 and (w_chances_high[0] - w_chances_high[1]) >= 0.20:
            is_only_move = True

        # --- 2. LOW DEPTH BLINDSPOT (D1) ---
        low_res = engine.analyse(board, chess.engine.Limit(depth=low_depth))
        low_best_cp = low_res["score"].pov(board.turn).score(mate_score=10000)
        w_low_best = get_win_chances(low_best_cp)

        # Execute Player Move
        board.push(move_played)
        
        # --- 3. EVALUATE RESULT (Truth & Low Depth) ---
        # Post-move high depth (Truth)
        post_high = engine.analyse(board, chess.engine.Limit(depth=high_depth))
        post_score_white = post_high["score"].white().score(mate_score=10000)
        w_after = get_win_chances(post_score_white if not board.turn else -post_score_white)
        
        # Post-move low depth (Did D1 see this coming?)
        post_low = engine.analyse(board, chess.engine.Limit(depth=low_depth))
        low_move_cp = post_low["score"].pov(not board.turn).score(mate_score=10000)
        w_low_move = get_win_chances(low_move_cp)

        # --- 4. THE LOGIC ---
        # Brilliancy: D1 hated it (drop >= 0.2), D22 loved it (drop < 0.05)
        low_delta = w_low_best - w_low_move
        real_delta = w_chances_high[0] - w_after

        eval_str = f"{post_score_white / 100:.2f}" if abs(post_score_white) < 10000 else "MATE"
        comment = f"[%eval {eval_str}]"

        is_brilliant = (low_delta >= 0.20 and real_delta < 0.05)

        if is_brilliant:
            next_node.nags.add(3) # !!
            comment += " !! Brilliancy."
        elif move_played == best_move_high:
            if is_only_move:
                next_node.nags.add(3) # !!
                comment += " Excellent Move."
            elif len(w_chances_high) >= 3 and (w_chances_high[0] - w_chances_high[2]) >= 0.20:
                next_node.nags.add(1) # !
                comment += " Good Move."
        else:
            # Handle misses and errors
            if was_previous_error and is_only_move:
                comment += f" Missed tactic: {best_move_san} was required after the opponent's error."
            
            error_name, error_nag = get_judgement(real_delta)
            if error_name:
                next_node.nags.add(error_nag)
                comment += f" {error_name}."

        was_previous_error = (get_judgement(real_delta)[0] is not None)
        next_node.comment = comment
        node = next_node
        print(".", end="", file=sys.stderr, flush=True)

    engine.quit()
    print("\n", file=sys.stderr)
    exporter = chess.pgn.StringExporter(columns=None, headers=True, variations=False, comments=True)
    print(game.accept(exporter))

if __name__ == "__main__":
    # Example PGN variable - ensure yours is defined
    my_pgn_string = """[Event "rated rapid game"]
[Site "https://lichess.org/mKunkW9L"]
[Date "2026.05.07"]
[Round "-"]
[White "sa6561"]
[Black "noctu2nality"]
[Result "1-0"]
[WhiteElo "1899"]
[BlackElo "1881"]
[TimeControl "600+0"]
[Termination "Time forfeit"]
[GameId "mKunkW9L"]
[Variant "Standard"]
[ECO "A45"]
[Opening "Indian Defense"]
[StudyName "Game study"]
[ChapterName "sa6561 (1899) - noctu2nality (1881)"]
[ChapterURL "https://lichess.org/study/FWsGP3kE/szu1QvHI"]
[Annotator "https://lichess.org/@/noctu2nality"]

1. d4 Nf6 2. e3 g6 3. a3 Bg7 4. Nc3 O-O 5. Bd2 d6 6. h3 Nbd7 7. Nf3 c5 8. Be2 cxd4 9. exd4 b6 10. O-O Bb7 11. Be3 Rc8 12. Na2 Nd5 13. c4 N5f6 14. Nc3 Ne4 15. Rc1 Re8 16. Bd3 Nxc3 17. bxc3 e5 18. Be2 Ba6 19. Qb3 Qc7 20. Nd2 Nf6 21. Rfe1 Bb7 22. Nf3 Ne4 23. Bd3 Qe7 24. Nd2 Nxd2 25. Bxd2 Qh4 26. Be3 exd4 27. cxd4 Bxd4 28. Bxd4 Qxd4 29. Rcd1 Qf4 30. Qa2 Qg5 31. Bf1 Re7 32. Rxe7 Qxe7 33. Qd2 Qh4 34. Qxd6 Ba6 35. Rd4 Qg5 36. Qf4 Qxf4 37. Rxf4 Kg7 38. Bd3 Rc7 39. g3 h5 40. Kg2 Bb7+ 41. f3 Re7 42. Kf2 Rd7 43. Be4 Bxe4 44. Rxe4 Kf6 45. Ke3 Rd1 46. c5 bxc5 47. Rc4 Ra1 48. Rc3 c4 49. Rxc4 Rxa3+ 50. Ke4 a5 51. g4 hxg4 52. hxg4 Ke6 53. f4 f5+ 54. gxf5+ gxf5+ 55. Kd4 Rf3 56. Rc6+ Kd7 57. Ra6 Rxf4+ 58. Ke5 Rf1 59. Rxa5 f4 60. Ra2 Kc6 61. Ke4 Kd6 62. Ra3 f3 63. Ke3 Ke5 64. Ra2 Kf5 65. Ra5+ Kg4 66. Ra2 Kg3 67. Ra8 f2 68. Rg8+ Kh2 69. Rf8 1-0



"""
    
    # Run the analysis
    analyze_to_pgn(my_pgn_string, low_depth=1, high_depth=14)
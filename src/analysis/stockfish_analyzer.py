"""
Core Engine Logic for Chess Achievement Book.
Fixed: POV-Consistency and high-depth played-move evaluation.
"""

import math
import io
import logging
from typing import Optional, List, Tuple, Dict, Any, TypedDict, Union

import chess.pgn
import chess.engine
import chess.polyglot
from src.config import STOCKFISH_PATH, BOOK_PATH

logger = logging.getLogger(__name__)

class EngineAnalysisData(TypedDict):
    high_res_best: chess.engine.InfoDict    # The actual #1 move
    high_res_played: chess.engine.InfoDict  # The user's move at high depth
    high_multipv: List[chess.engine.InfoDict] # For the "Top 3" display
    low_res_best: chess.engine.InfoDict
    low_res_played: chess.engine.InfoDict
    post_high_score: int

class AchievementAnalyzer:
    def __init__(self, low_depth: int = 8, high_depth: int = 15, threads: int = 4) -> None:
        self.low_depth = low_depth
        self.high_depth = high_depth
        self.threads = threads
        self.engine: Optional[chess.engine.SimpleEngine] = None
        self.reader: Optional[chess.polyglot.MemoryMappedReader] = None

    def __enter__(self) -> "AchievementAnalyzer":
        self.engine = chess.engine.SimpleEngine.popen_uci(str(STOCKFISH_PATH))
        self.engine.configure({"Threads": self.threads, "Hash": 512})
        try:
            self.reader = chess.polyglot.open_reader(str(BOOK_PATH))
        except FileNotFoundError:
            logger.warning("Opening book not found. Novelty detection disabled.")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.engine:
            self.engine.quit()
        if self.reader:
            self.reader.close()

    def analyze_game(self, input_pgn: str) -> Tuple[Optional[str], List[int]]:
        game = chess.pgn.read_game(io.StringIO(input_pgn.strip()))
        if not game: return None, []

        board = game.board()
        node = game
        move_evals = []
        novelty_found = False
        
        total_moves = sum(1 for _ in game.mainline())
        move_count = 0

        while node.variations:
            move_count += 1
            next_node = node.variation(0)
            move_played = next_node.move

            eval_data = self._get_move_analysis(board, move_played)
            if not eval_data: break

            if move_count % 10 == 0 or move_count == 1:
                logger.info(f"      ♟️  Analyzing move {move_count}/{total_moves}...")

            self._assign_symbols(next_node, move_played, eval_data, board)

            if self.reader and not novelty_found:
                novelty_found = self._check_for_novelty(board, move_played, next_node)

            move_evals.append(eval_data['post_high_score'])
            next_node.comment = self._format_comment(eval_data, board)

            board.push(move_played)
            node = next_node

        return self._export_pgn(game), move_evals

    def _get_move_analysis(self, board: chess.Board, move: chess.Move) -> Optional[EngineAnalysisData]:
        if board.is_game_over(): return None

        # 1. High Depth: Get Top 3 alternatives
        high_multipv = self.engine.analyse(board, chess.engine.Limit(depth=self.high_depth), multipv=3)
        if not isinstance(high_multipv, list): high_multipv = [high_multipv]

        # 2. High Depth: Specifically evaluate the move played (to compare against Best)
        high_res_played = self.engine.analyse(board, chess.engine.Limit(depth=self.high_depth), root_moves=[move])

        # 3. Low Depth: Best vs Played (for Brilliancy/Blindspot detection)
        low_res_best = self.engine.analyse(board, chess.engine.Limit(depth=self.low_depth))
        low_res_played = self.engine.analyse(board, chess.engine.Limit(depth=self.low_depth), root_moves=[move])

        # 4. Final Score (White POV for the database list)
        score_obj = high_res_played.get("score")
        post_high_score = score_obj.white().score(mate_score=10000) if score_obj else 0

        return {
            'high_res_best': high_multipv[0],
            'high_res_played': high_res_played,
            'high_multipv': high_multipv,
            'low_res_best': low_res_best,
            'low_res_played': low_res_played,
            'post_high_score': post_high_score
        }

    def _assign_symbols(self, node, move, data, board):
        # Everything here is POV of the player whose turn it is
        turn = board.turn 

        def get_win_chance(info):
            score = info.get("score")
            if not score: return 0.5
            cp = score.pov(turn).score(mate_score=10000) or 0
            return self._calculate_win_chances(cp)

        w_best_high = get_win_chance(data['high_res_best'])
        w_played_high = get_win_chance(data['high_res_played'])
        
        w_best_low = get_win_chance(data['low_res_best'])
        w_played_low = get_win_chance(data['low_res_played'])

        # Delta is now POSITIVE (0.0 to 1.0). 0.0 means you played the engine best move.
        delta = w_best_high - w_played_high

        # --- BRILLIANCY (!!) ---
        # If best move at high depth, but low depth thought it was a >15% mistake
        if delta < 0.015 and (w_best_low - w_played_low) > 0.15:
            node.nags.add(3)
            return

        # --- ERRORS (Using standard Lichess-style brackets) ---
        if delta > 0.20:
            node.nags.add(4)  # ?? (Blunder)
        elif delta > 0.10:
            node.nags.add(2)  # ? (Mistake)
        
        # --- POSITIVE ---
        elif delta < 0.01:
            # Check for Only Move (□)
            if len(data['high_multipv']) > 1:
                w_second = get_win_chance(data['high_multipv'][1])
                if (w_best_high - w_second) > 0.15:
                    node.nags.add(7) # □
            
            # Great Move (!)
            # If the position is tough (win chance < 40%) but you found the top move
            if w_best_high < 0.40:
                node.nags.add(1)

    def _format_comment(self, data: EngineAnalysisData, board: chess.Board) -> str:
        score_obj = data['high_res_played'].get("score")
        eval_str = self._format_eval(score_obj.white()) if score_obj else "0.00"
        
        top_moves_list = []
        for i, info in enumerate(data['high_multipv']):
            pv = info.get("pv", [])
            if not pv: continue
            san = board.san(pv[0])
            score = self._format_eval(info.get("score").pov(board.turn))
            top_moves_list.append(f"{i+1}. {san} ({score})")
            
        return f"[%eval {eval_str}] (Top: {', '.join(top_moves_list)})"

    @staticmethod
    def _calculate_win_chances(cp: int) -> float:
        return 0.5 + 0.5 * (2 / (1 + math.exp(-0.003682 * cp)) - 1)

    def _format_eval(self, score: chess.engine.Score) -> str:
        mate = score.mate()
        if mate is not None: return f"#{mate}"
        cp = score.score(mate_score=10000)
        return f"{cp / 100:.2f}" if cp is not None else "0.00"

    def _check_for_novelty(self, board, move, node) -> bool:
        if not self.reader or len(board.move_stack) < 6: return False
        book_moves = [e.move for e in self.reader.find_all(board)]
        if move not in book_moves:
            node.nags.add(146) # N
            return True
        return False

    def _export_pgn(self, game: chess.pgn.Game) -> str:
        exporter = chess.pgn.StringExporter(columns=None, comments=True, variations=False)
        return game.accept(exporter)
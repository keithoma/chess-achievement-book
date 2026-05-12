"""
Core Engine Logic for Chess Achievement Book.
Optimized for dual-depth analysis and Mate Grace Period playouts.
"""

import io
import logging
from typing import Optional, List, Dict, Any, TypedDict

import chess.pgn
import chess.engine
import chess.polyglot
from src.config import (
    STOCKFISH_PATH, BOOK_PATH, LOW_DEPTH, HIGH_DEPTH,
    MATE_GRACE_THRESHOLD, MATE_GRACE_PLIES, MATE_GRACE_DEPTH
)

logger = logging.getLogger(__name__)

class MoveAnalysis(TypedDict):
    ply: int
    move_san: str
    high_depth_eval: float     # The evaluation of the played move @ HIGH_DEPTH
    high_top_moves: List[Dict] # Top 2 engine moves @ HIGH_DEPTH
    low_best_move: Dict        # Best engine move @ LOW_DEPTH
    is_book: bool

class AchievementAnalyzer:
    def __init__(self, threads: int = 4) -> None:
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

    def analyze_game(self, pgn_text: str) -> Tuple[List[MoveAnalysis], str]:
        """
        Processes a game, returns decorated move data, and an optionally amended PGN.
        """
        game = chess.pgn.read_game(io.StringIO(pgn_text.strip()))
        if not game: return [], pgn_text

        board = game.board()
        analysis_results = []
        
        total_plies = sum(1 for _ in game.mainline())
        terminal_node = game
        
        for ply, node in enumerate(game.mainline(), start=1):
            move = node.move
            
            # 1. Analyze position BEFORE the move
            move_data = self._analyze_position(board, move, ply)
            move_data['is_book'] = self._is_book_move(board, move)
            analysis_results.append(move_data)
            
            # 2. Update board and track terminal node
            board.push(move)
            terminal_node = node
            
            if ply % 10 == 0:
                logger.info(f"Analyzed {ply}/{total_plies} plies...")

        # 3. Grace Period Checkmate Playout
        if analysis_results and not board.is_checkmate() and not board.is_game_over(claim_draw=True):
            final_eval = analysis_results[-1]["high_depth_eval"]
            # We use absolute value because an eval of -5.0 is just as "won" as +5.0
            if abs(final_eval) >= MATE_GRACE_THRESHOLD:
                self._run_mate_grace_period(board, terminal_node)

        # We return the analysis data AND the amended PGN so the DB can store the new moves
        exporter = chess.pgn.StringExporter(columns=None, comments=True, variations=True)
        amended_pgn = game.accept(exporter)

        return analysis_results, amended_pgn

    def _analyze_position(self, board: chess.Board, played_move: chess.Move, ply: int) -> MoveAnalysis:
        # High Depth Pass (MultiPV=2)
        high_res = self.engine.analyse(board, chess.engine.Limit(depth=HIGH_DEPTH), multipv=2)
        
        # Played Move Eval
        played_move_info = next((m for m in high_res if m.get("pv") and m["pv"][0] == played_move), None)
        if not played_move_info:
            played_move_info = self.engine.analyse(board, chess.engine.Limit(depth=HIGH_DEPTH), root_moves=[played_move])

        # Low Depth Pass
        low_res = self.engine.analyse(board, chess.engine.Limit(depth=LOW_DEPTH))

        return {
            "ply": ply,
            "move_san": board.san(played_move),
            "high_depth_eval": self._to_cp(played_move_info.get("score"), board.turn),
            "high_top_moves": [
                {"move": board.san(info["pv"][0]), "eval": self._to_cp(info["score"], board.turn)}
                for info in high_res if info.get("pv")
            ],
            "low_best_move": {
                "move": board.san(low_res["pv"][0]) if low_res.get("pv") else None,
                "eval": self._to_cp(low_res.get("score"), board.turn)
            },
            "is_book": False
        }

    def _run_mate_grace_period(self, board: chess.Board, terminal_node: chess.pgn.GameNode) -> None:
        """
        Simulates the game to its conclusion. If a checkmate is found within the ply limit,
        the moves are attached to the original game node as a variation.
        """
        logger.info(f"Threshold met. Running engine playout for up to {MATE_GRACE_PLIES} plies...")
        
        sim_board = board.copy()
        sim_moves = []

        for _ in range(MATE_GRACE_PLIES):
            if sim_board.is_checkmate() or sim_board.is_game_over(claim_draw=True):
                break

            # Let the engine find the fastest path to mate
            result = self.engine.play(sim_board, chess.engine.Limit(depth=MATE_GRACE_DEPTH))
            if not result or not result.move:
                break
            
            sim_moves.append(result.move)
            sim_board.push(result.move)

        # Only amend the game if the simulation actually resulted in a checkmate
        if sim_board.is_checkmate():
            logger.info("Grace period mate found! Amending PGN.")
            curr_node = terminal_node
            for move in sim_moves:
                curr_node = curr_node.add_main_variation(move)
                curr_node.comment = "[Engine Playout]"
        else:
            logger.info("No mate found within grace period limits. Discarding simulation.")

    def _to_cp(self, score_obj: Optional[chess.engine.PovScore], turn: chess.Color) -> float:
        if not score_obj: return 0.0
        score = score_obj.pov(turn)
        if score.is_mate():
            # If it's a forced mate, return an artificially massive evaluation
            # so the grace period triggers easily.
            return 10000.0 if score.mate() > 0 else -10000.0
        return (score.score() or 0) / 100.0

    def _is_book_move(self, board: chess.Board, move: chess.Move) -> bool:
        if not self.reader: return False
        return any(entry.move == move for entry in self.reader.find_all(board))
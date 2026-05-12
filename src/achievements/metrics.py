import math
import chess
from typing import List, Dict, Any

class GameMetrics:
    """
    Consumes raw game data and the structured MoveAnalysis from the Engine Analyzer.
    Pre-calculates accuracies, material swings, and tactical achievements.
    """
    def __init__(self, game_id: str, game_data: Dict[str, Any], analysis_results: List[Dict[str, Any]], username: str):
        self.game_id = game_id
        self.speed = game_data.get('speed', 'unknown').lower()
        self.moves_string = game_data.get('moves', '')
        self.san_moves = self.moves_string.split()
        self.total_plies = len(self.san_moves)
        self.score = game_data.get('score', '*')
        
        # --- OPENING EXTRACTION ---
        raw_api = game_data.get('raw_api_response', {})
        opening_data = raw_api.get('opening', {})
        self.opening_name = opening_data.get('name', 'Unknown')
        self.opening_eco = opening_data.get('eco', 'Unknown')
        
        # --- PLAYER CONTEXT ---
        self.white_id = game_data['players']['white'].get('id', '').lower()
        self.is_white = (self.white_id == username.lower())
        self.my_color = chess.WHITE if self.is_white else chess.BLACK
        self.opp_color = chess.BLACK if self.is_white else chess.WHITE
        
        # --- OUTCOMES ---
        self.is_win = (self.is_white and self.score == '1-0') or (not self.is_white and self.score == '0-1')
        self.is_draw = (self.score == '1/2-1/2')
        self._draw_reason = None

        # --- ANALYTIC COUNTERS ---
        self.inaccuracies = 0
        self.mistakes = 0
        self.blunders = 0
        self.brilliancies = 0 # Can be calculated from analyzer deltas!
        
        self.total_material_points = 0
        self.clean_pawns_won_moves = []
        
        # --- BOOK METRICS ---
        self.my_book_moves = 0
        self.total_book_plies = 0
        self.out_of_book_ply = None

        # --- ACPL (Average Centipawn Loss) ---
        self.total_cpl = 0.0
        self.analyzed_moves_count = 0
        self.acpl = 0.0

        # Execute processing
        self._process_game_and_tactics(analysis_results)

    def _process_game_and_tactics(self, analysis_results: List[Dict[str, Any]]):
        """
        A single, clean pass through the game using chess.Board.
        Extracts captures, evaluates accuracies, and tracks opening book status.
        """
        board = chess.Board()
        piece_values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
        
        for ply, move_san in enumerate(self.san_moves, start=1):
            is_my_turn = (board.turn == self.my_color)
            
            try:
                move = board.parse_san(move_san)
            except ValueError:
                break # Invalid SAN failsafe

            # --- 1. CAPTURE & MATERIAL LOGIC ---
            if board.is_capture(move):
                captured_piece = chess.PAWN if board.is_en_passant(move) else board.piece_at(move.to_square).piece_type
                if is_my_turn and captured_piece:
                    pts = piece_values.get(captured_piece, 0)
                    self.total_material_points += pts
                    
                    # (You can re-implement the "Clean Pawn" logic here using board state 
                    # rather than SAN string parsing, which is much more reliable)

            # --- 2. ENGINE EVALUATIONS & BOOK LOGIC ---
            if ply - 1 < len(analysis_results):
                move_data = analysis_results[ply - 1]
                
                # Book Logic
                if move_data.get('is_book'):
                    self.total_book_plies += 1
                    if is_my_turn:
                        self.my_book_moves += 1
                elif self.out_of_book_ply is None:
                    self.out_of_book_ply = ply

                # Accuracy Logic (Only evaluate our own moves)
                if is_my_turn and move_data.get('high_top_moves'):
                    best_eval = move_data['high_top_moves'][0]['eval']
                    played_eval = move_data['high_depth_eval']
                    
                    # Calculate Centipawn Loss (capped at 1000cp / 10 pawns)
                    cpl = max(0.0, best_eval - played_eval)
                    self.total_cpl += min(cpl * 100, 1000) 
                    self.analyzed_moves_count += 1

                    # Win Chance Drop
                    w_best = self._calculate_win_chances(best_eval)
                    w_played = self._calculate_win_chances(played_eval)
                    delta = w_best - w_played

                    if delta >= 0.25:
                        self.blunders += 1
                    elif delta >= 0.12:
                        self.mistakes += 1
                    elif delta >= 0.06:
                        self.inaccuracies += 1

            # Push move for the next iteration
            board.push(move)

        # Finalize ACPL
        if self.analyzed_moves_count > 0:
            self.acpl = round(self.total_cpl / self.analyzed_moves_count, 1)

        # Finalize Draw Reason
        if self.is_draw:
            if board.is_stalemate(): self._draw_reason = "stalemate"
            elif board.is_insufficient_material(): self._draw_reason = "insufficient-material"
            elif board.can_claim_fifty_moves() or board.is_fifty_moves(): self._draw_reason = "50-move"
            elif board.can_claim_threefold_repetition() or board.is_repetition(): self._draw_reason = "3-fold"
            else: self._draw_reason = "agreement"

    def get_draw_reason(self) -> str:
        return self._draw_reason or "none"

    def _calculate_win_chances(self, cp_eval: float) -> float:
        """Converts an evaluation (in pawns) to a win probability (0.0 to 1.0)."""
        # Note: Stockfish analyzer passes eval in pawns (e.g., 1.5), so we multiply by 100 for the formula
        cp = cp_eval * 100 
        return 0.5 + 0.5 * (2 / (1 + math.exp(-0.003682 * cp)) - 1)
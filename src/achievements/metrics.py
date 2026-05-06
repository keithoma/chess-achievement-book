import chess

class GameMetrics:
    """
    Parses a single game's raw data and pre-calculates all necessary 
    metrics (accuracies, material, punishments) exactly once.
    """
    def __init__(self, game_id, score, speed, game_data, username):
        self.game_id = game_id
        self.speed = speed.lower()
        self.total_plies = len(game_data.get('moves', '').split())
        self.termination = game_data.get('termination', 'unknown').lower()
        self.moves_string = game_data.get('moves', '')
        
        # Player Context
        self.white_id = game_data['players']['white'].get('id', '').lower()
        self.is_white = (self.white_id == username)
        self.my_color = 'white' if self.is_white else 'black'
        self.opp_color = 'black' if self.is_white else 'white'
        
        # Outcomes
        self.is_win = (self.is_white and score == '1-0') or (not self.is_white and score == '0-1')
        self.is_draw = (score == '1/2-1/2')

        # Phases
        division = game_data.get('division', {})
        self.mid_start = division.get('middle')
        self.end_start = division.get('end')

        # Analytic Counters
        self.min_eval_seen = 0
        self.eval_at_mid = 0
        self.eval_at_end = 0
        
        self.inaccuracies = 0
        self.mistakes = 0
        self.blunders = 0
        
        self.mistakes_punished = 0
        self.blunders_punished = 0
        
        self.total_material_points = 0
        self.clean_pawns_won = 0

        # Lazy loaded properties
        self._draw_reason = None

        # Execute crunching algorithms
        self._analyze_evals(game_data.get('move_evals', []))
        self._analyze_material(game_data.get('captures', []), game_data.get('move_evals', []))

    def _analyze_evals(self, evals):
        for i in range(len(evals)):
            current_eval = evals[i]
            prev_eval = evals[i-1] if i > 0 else 0

            p_eval = current_eval if self.is_white else -current_eval
            if p_eval < self.min_eval_seen:
                self.min_eval_seen = p_eval

            if self.mid_start and i == self.mid_start - 1: self.eval_at_mid = p_eval
            if self.end_start and i == self.end_start - 1: self.eval_at_end = p_eval

            is_player_turn = (self.is_white and i % 2 == 0) or (not self.is_white and i % 2 == 1)
            
            if i > 0:
                drop = (current_eval - prev_eval) if self.is_white else -(current_eval - prev_eval)
                
                if is_player_turn:
                    if drop <= -300: self.blunders += 1
                    elif drop <= -100: self.mistakes += 1
                    elif drop <= -50: self.inaccuracies += 1
                else:
                    opp_drop = -drop 
                    if opp_drop <= -100 and (i + 1 < len(evals)):
                        my_response_eval = evals[i+1]
                        my_response_drop = (my_response_eval - current_eval) if self.is_white else -(my_response_eval - current_eval)
                        
                        if my_response_drop > -50:
                            if opp_drop <= -300: self.blunders_punished += 1
                            elif opp_drop <= -100: self.mistakes_punished += 1

    def _analyze_material(self, captures, evals):
        piece_values = {'pawn': 1, 'knight': 3, 'bishop': 3, 'rook': 5, 'queen': 9}
        for cap in captures:
            if cap['player'] == self.my_color:
                self.total_material_points += piece_values.get(cap['piece_taken'], 0)
                if cap['piece_taken'] == 'pawn':
                    c_ply = cap['ply']
                    eval_idx = c_ply - 1 
                    is_clean = True
                    if 0 < eval_idx < len(evals):
                        current_eval = evals[eval_idx]
                        prev_eval = evals[eval_idx - 1]
                        drop = (current_eval - prev_eval) if self.is_white else -(current_eval - prev_eval)
                        if drop <= -100: is_clean = False
                    
                    if is_clean and (self.total_plies >= c_ply + 10):
                        lost_pawn_soon = False
                        for future_cap in captures:
                            if future_cap['player'] == self.opp_color and future_cap['piece_taken'] == 'pawn':
                                if c_ply < future_cap['ply'] <= c_ply + 10:
                                    lost_pawn_soon = True
                                    break
                        if not lost_pawn_soon:
                            self.clean_pawns_won += 1

    def get_draw_reason(self):
        if self._draw_reason is None:
            board = chess.Board()
            for move_str in self.moves_string.split():
                try: board.push_san(move_str)
                except ValueError: break
                    
            if board.is_stalemate(): self._draw_reason = "stalemate"
            elif board.is_insufficient_material(): self._draw_reason = "insufficient-material"
            elif board.can_claim_fifty_moves() or board.is_fifty_moves(): self._draw_reason = "50-move"
            elif board.can_claim_threefold_repetition() or board.is_repetition(): self._draw_reason = "3-fold"
            else: self._draw_reason = "agreement"
        return self._draw_reason
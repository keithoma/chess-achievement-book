import chess
import chess.polyglot
import os

# Adjust this path if your working directory changes.
# Based on your explorer image, this is the path from the project root.
BOOK_PATH = "Solista-ENG 2026E-BIN/Solista-ENG 2026E.bin"

class GameMetrics:
    """
    Parses a single game's raw data and pre-calculates all necessary 
    metrics (accuracies, material, punishments) exactly once.
    """
    def __init__(self, game_id, score, speed, game_data, username):
        self.game_id = game_id
        self.speed = speed.lower()
        self.moves_string = game_data.get('moves', '')
        self.san_moves = self.moves_string.split()
        self.total_plies = len(self.san_moves)
        self.termination = game_data.get('termination', 'unknown').lower()
        
        # Capture Opening Info
        self.opening_name = game_data.get('opening', {}).get('name', 'Unknown')
        self.opening_eco = game_data.get('opening', {}).get('eco', 'Unknown')
        
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
        
        self.mistakes_punished_moves = []
        self.blunders_punished_moves = []
        self.clean_pawns_won_moves = []
        
        self.total_material_points = 0
        self.final_eval = 0
        self.blundered_queen = False

        # --- NEW: Polyglot Book Metrics ---
        self.my_book_moves = 0
        self.total_book_plies = 0
        self.my_book_weights = []
        self.out_of_book_ply = None

        # Lazy loaded properties
        self._draw_reason = None

        # Execute crunching algorithms
        self._analyze_evals(game_data.get('move_evals', []))
        self._analyze_material(game_data.get('captures', []), game_data.get('move_evals', []))
        
        # Run the Opening Book analysis
        self._analyze_opening_book()

    def _format_move(self, ply_index):
        """Converts a 0-based ply index into readable notation (e.g. '17. Qxc5' or '17... Qxc5')"""
        if ply_index >= len(self.san_moves):
            return "Unknown"
        move_num = (ply_index // 2) + 1
        san = self.san_moves[ply_index]
        if ply_index % 2 == 0:
            return f"{move_num}. {san}"
        else:
            return f"{move_num}... {san}"

    def _analyze_opening_book(self):
        """Steps through the game and checks moves against the Solista Polyglot book."""
        if not os.path.exists(BOOK_PATH):
            return # Skip if the book isn't downloaded or path is wrong

        board = chess.Board()
        
        try:
            with chess.polyglot.open_reader(BOOK_PATH) as reader:
                for i, move_str in enumerate(self.san_moves):
                    try:
                        # Find the move the player actually made on the board
                        player_move = board.parse_san(move_str)
                    except ValueError:
                        break # Failsafe for invalid SAN
                    
                    # Fetch all known book moves for the current position
                    entries = reader.find_all(board)
                    book_moves = {e.move: e.weight for e in entries}

                    if player_move in book_moves:
                        self.total_book_plies += 1
                        weight = book_moves[player_move]
                        
                        is_my_turn = (self.is_white and i % 2 == 0) or (not self.is_white and i % 2 == 1)
                        if is_my_turn:
                            self.my_book_moves += 1
                            self.my_book_weights.append(weight)
                            
                        # Advance the board state to check the next move
                        board.push(player_move)
                    else:
                        # The move played is not in Solista. We are out of book.
                        self.out_of_book_ply = i
                        break
        except Exception as e:
            print(f"Error reading polyglot book: {e}")

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
                            # CHANGED: Store the formatted move string of your punishing response
                            punishing_move = self._format_move(i + 1)
                            if opp_drop <= -300: 
                                self.blunders_punished_moves.append(punishing_move)
                            elif opp_drop <= -100: 
                                self.mistakes_punished_moves.append(punishing_move)

    def _analyze_material(self, captures, evals):
        piece_values = {'pawn': 1, 'knight': 3, 'bishop': 3, 'rook': 5, 'queen': 9}
        
        # Helpers to calculate relative balance at any exact moment in the game
        def get_balance_at_ply(target_ply):
            my_pts = sum(piece_values.get(c['piece_taken'], 0) for c in captures if c['player'] == self.my_color and c['ply'] <= target_ply)
            opp_pts = sum(piece_values.get(c['piece_taken'], 0) for c in captures if c['player'] == self.opp_color and c['ply'] <= target_ply)
            return my_pts - opp_pts

        def get_pawn_balance_at_ply(target_ply):
            my_pawns = sum(1 for c in captures if c['player'] == self.my_color and c['piece_taken'] == 'pawn' and c['ply'] <= target_ply)
            opp_pawns = sum(1 for c in captures if c['player'] == self.opp_color and c['piece_taken'] == 'pawn' and c['ply'] <= target_ply)
            return my_pawns - opp_pawns

        for cap in captures:
            if cap['player'] == self.my_color:
                # Always track total material for the "Board Wiper" badges
                self.total_material_points += piece_values.get(cap['piece_taken'], 0)
                
                if cap['piece_taken'] == 'pawn':
                    c_ply = cap['ply']
                    eval_idx = c_ply - 1 
                    
                    # 1. Engine Check: Was it a blunder?
                    is_clean = True
                    if 0 < eval_idx < len(evals):
                        drop = (evals[eval_idx] - evals[eval_idx-1]) if self.is_white else -(evals[eval_idx] - evals[eval_idx-1])
                        if drop <= -100: is_clean = False
                    
                    # 2. Tactical Resolution Check
                    if is_clean:
                        # Record the baseline BEFORE you grabbed the pawn
                        bal_mat_before = get_balance_at_ply(c_ply - 1)
                        bal_pwn_before = get_pawn_balance_at_ply(c_ply - 1)
                        
                        target_ply = c_ply + 3
                        final_ply = c_ply
                        
                        # Loop through the upcoming moves to find when the dust settles
                        # (self.san_moves is 0-indexed, so index `c_ply` is the move immediately AFTER the capture)
                        for p_idx in range(c_ply, self.total_plies):
                            current_ply = p_idx + 1
                            san = self.san_moves[p_idx]
                            
                            # If tactical noise occurs, push the timer back 3 plies
                            if any(char in san for char in ['x', '+', '#', '=']):
                                target_ply = current_ply + 3
                                
                            final_ply = current_ply
                            
                            # 3 quiet plies have passed, the tactical sequence is over
                            if current_ply == target_ply:
                                break
                                
                        # 3. Final Balance Check
                        bal_mat_after = get_balance_at_ply(final_ply)
                        bal_pwn_after = get_pawn_balance_at_ply(final_ply)
                        
                        # Check if the NET change since before the capture is positive
                        if (bal_mat_after - bal_mat_before) >= 1 and (bal_pwn_after - bal_pwn_before) >= 1:
                            self.clean_pawns_won_moves.append(self._format_move(c_ply - 1))

    def get_draw_reason(self):
        if self._draw_reason is None:
            board = chess.Board()
            for move_str in self.san_moves:
                try: board.push_san(move_str)
                except ValueError: break
                    
            if board.is_stalemate(): self._draw_reason = "stalemate"
            elif board.is_insufficient_material(): self._draw_reason = "insufficient-material"
            elif board.can_claim_fifty_moves() or board.is_fifty_moves(): self._draw_reason = "50-move"
            elif board.can_claim_threefold_repetition() or board.is_repetition(): self._draw_reason = "3-fold"
            else: self._draw_reason = "agreement"
        return self._draw_reason
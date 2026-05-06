import logging
from .metrics import GameMetrics

logger = logging.getLogger(__name__)

class AchievementEngine:
    def __init__(self, db_cursor, username, show_all=False):
        self.cur = db_cursor
        self.username = username
        self.show_all = show_all # New flag

    def _grant(self, game_id, slug, print_msg):
        query = """
            INSERT INTO game_achievements (game_id, username, achievement_slug) 
            VALUES (%s, %s, %s) ON CONFLICT DO NOTHING RETURNING 1;
        """
        self.cur.execute(query, (game_id, self.username, slug))
        newly_granted = self.cur.fetchone()

        if self.show_all:
            # Verbose mode: Print everything this game qualifies for
            prefix = "🎉 NEW:" if newly_granted else "🏅 QUALIFIED:"
            logger.info(f"{prefix} [{self.username}] {print_msg} (Game: {game_id})")
        elif newly_granted:
            # Standard mode: Only print brand new achievements
            logger.info(f"🎉 New Achievement [{self.username}]: {print_msg} (Game: {game_id})")
        else:
            logger.debug(f"  - Skipped: '{slug}' already granted for game {game_id}")

    def _grant_mastery(self, game_id, category, slug, name, exp_to_add):
        """Grants EXP and updates the player's total mastery progress safely."""
        # 1. Ledger Check: Did we already grant this EXP for this game?
        check_query = "SELECT 1 FROM game_mastery_grants WHERE game_id = %s AND mastery_slug = %s AND username = %s"
        self.cur.execute(check_query, (game_id, slug, self.username))
        if self.cur.fetchone():
            return # Quietly skip, already processed

        # 2. Record the grant in the ledger
        insert_grant = """
            INSERT INTO game_mastery_grants (game_id, username, mastery_slug, exp_granted)
            VALUES (%s, %s, %s, %s)
        """
        self.cur.execute(insert_grant, (game_id, self.username, slug, exp_to_add))

        # 3. Upsert the total mastery progress
        upsert_progress = """
            INSERT INTO mastery_progress (username, category, slug, name, total_exp)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (username, category, slug) 
            DO UPDATE SET total_exp = mastery_progress.total_exp + EXCLUDED.total_exp
            RETURNING total_exp;
        """
        self.cur.execute(upsert_progress, (self.username, category, slug, name, exp_to_add))
        new_total = self.cur.fetchone()[0]

        # Log it dynamically!
        if self.show_all:
            logger.info(f"📈 QUALIFIED [{self.username}]: {name} +{exp_to_add} EXP (Total: {new_total:.1f}) (Game: {game_id})")
        else:
            logger.info(f"📈 MASTERY UP [{self.username}]: {name} +{exp_to_add} EXP (Total: {new_total:.1f}) (Game: {game_id})")

    def check_mastery(self, m: GameMetrics):
        """Calculates experience points for opening mastery."""
        # Clean the opening name to get the base (e.g., "Caro-Kann Defense: Advance" -> "Caro-Kann Defense")
        base_opening = m.opening_name.split(':')[0].split('|')[0].strip()
        if base_opening == 'Unknown' or not base_opening:
            return

        # Create a clean URL-friendly slug (e.g., "caro-kann-defense")
        import re
        slug = re.sub(r'[^a-z0-9]+', '-', base_opening.lower()).strip('-')

        # Calculate how many plies actually occurred in the opening
        opening_plies = m.mid_start if m.mid_start else m.total_plies
        
        # Calculate how many of those plies YOU played
        my_opening_moves = 0
        for i in range(opening_plies):
            is_my_turn = (m.is_white and i % 2 == 0) or (not m.is_white and i % 2 == 1)
            if is_my_turn:
                my_opening_moves += 1

        # Determine multiplier based on game outcome
        if m.is_win:
            multiplier = 5.0
        elif m.is_draw:
            multiplier = 4.0
        else:
            multiplier = 2.5

        exp_earned = my_opening_moves * multiplier

        if exp_earned > 0:
            self._grant_mastery(m.game_id, 'opening', slug, base_opening, exp_earned)

    def evaluate(self, metrics: GameMetrics):
        """Main entry point to run a game through all achievement rulesets."""
        self.check_participation(metrics)
        if metrics.is_win:
            self.check_wins(metrics)
            self.check_terminations(metrics)
            self.check_comebacks(metrics)
            self.check_accuracy(metrics)
            self.check_endurance(metrics)
        if metrics.is_draw:
            self.check_escapes(metrics)
            
        self.check_material(metrics)
        self.check_punishments(metrics)

        self.check_mastery(metrics)

        self.check_feats(metrics)

    def check_participation(self, m: GameMetrics):
        self._grant(m.game_id, 'played-game', "Played a game")
        self._grant(m.game_id, f'played-{m.speed}', f"Played a {m.speed} game")

    def check_wins(self, m: GameMetrics):
        self._grant(m.game_id, 'won-game', "Won a game")
        self._grant(m.game_id, f'won-{m.speed}', f"Won a {m.speed} game")
        if m.mid_start and m.total_plies < m.mid_start: self._grant(m.game_id, 'win-opening', "Won in the Opening")
        elif m.end_start and m.mid_start <= m.total_plies < m.end_start: self._grant(m.game_id, 'win-midgame', "Won in the Middle Game")
        elif m.end_start and m.total_plies >= m.end_start: self._grant(m.game_id, 'win-endgame', "Won in the End Game")

    def check_terminations(self, m: GameMetrics):
        if m.termination == 'mate': self._grant(m.game_id, 'win-mate', "Won by Checkmate")
        elif m.termination == 'resign': self._grant(m.game_id, 'win-resign', "Won by Resignation")
        elif m.termination in ['outoftime', 'timeout']: self._grant(m.game_id, 'win-timeout', "Won by Time Out")
        elif m.termination in ['abandoned', 'aborted']: self._grant(m.game_id, 'win-abandon', "Won by Abandonment")

    def check_comebacks(self, m: GameMetrics):
        if m.mid_start and m.end_start:
            if m.eval_at_mid <= -150 and m.eval_at_end <= -150: self._grant(m.game_id, 'comeback-midgame-150', "Down 1.5+ after Opening AND Midgame, but won")
            if m.eval_at_mid <= -200 and (m.total_plies - m.mid_start) <= 40: self._grant(m.game_id, 'comeback-opening-fast', "Down 2.0+ after Opening, won within 20 moves")
            if m.eval_at_mid <= -300: self._grant(m.game_id, 'comeback-opening-300', "Down 3.0+ after Opening, but won")
        if m.end_start and m.eval_at_end <= -200:
            self._grant(m.game_id, 'comeback-endgame-200', "Started Endgame down 2.0+, but won")

    def check_accuracy(self, m: GameMetrics):
        if (m.is_white and m.min_eval_seen >= 0) or (not m.is_white and m.min_eval_seen >= -30):
            self._grant(m.game_id, 'clean-eval', "Won with eval always above 0.0 (W) or -0.3 (B)")
        if m.blunders == 0:
            self._grant(m.game_id, 'no-blunders', "Won without any blunders")
            if m.mistakes == 0:
                self._grant(m.game_id, 'no-mistakes-blunders', "Won without mistakes or blunders")
                if m.inaccuracies == 0:
                    self._grant(m.game_id, 'perfect-accuracy', "Won without inaccuracies, mistakes, or blunders")

    def check_endurance(self, m: GameMetrics):
        if m.total_plies > 160: self._grant(m.game_id, 'marathon-win', "Won a game longer than 80 moves")

    def check_escapes(self, m: GameMetrics):
        if m.min_eval_seen <= -300:
            reason = m.get_draw_reason()
            if reason == '3-fold': self._grant(m.game_id, 'escape-3-fold', "Drew a lost position via Threefold")
            elif reason == 'agreement': self._grant(m.game_id, 'escape-agreement', "Drew a lost position by Agreement")
            elif reason == '50-move': self._grant(m.game_id, 'escape-50-move', "Drew a lost position via 50-Move Rule")
            elif reason == 'insufficient-material': self._grant(m.game_id, 'escape-insufficient', "Drew a lost position (Insufficient Material)")
        if m.end_start and m.eval_at_end <= -200:
            self._grant(m.game_id, 'escape-endgame-200', "Started Endgame down 2.0+, but managed a draw")

    def check_material(self, m: GameMetrics):
        pts = m.total_material_points
        if pts >= 20: self._grant(m.game_id, 'captured-20-points', f"Captured 20+ points of material ({pts} total)")
        if pts >= 30: self._grant(m.game_id, 'captured-30-points', f"Captured 30+ points of material ({pts} total)")
        if pts >= 39: self._grant(m.game_id, 'captured-39-points', f"Board Wiper: Captured {pts} points of material")

        pawns = len(m.clean_pawns_won_moves)
        if pawns >= 1: 
            self._grant(m.game_id, 'clean-pawn-1', f"Won a clean pawn and held it for 5+ turns (at {m.clean_pawns_won_moves[0]})")
        if pawns >= 2: 
            self._grant(m.game_id, 'clean-pawn-2', f"Won 2 clean pawns in a single game (2nd at {m.clean_pawns_won_moves[1]})")
        if pawns >= 3: 
            self._grant(m.game_id, 'clean-pawn-3', f"Pawn Grabber: Won 3+ clean pawns in a single game (3rd at {m.clean_pawns_won_moves[2]})")

    def check_punishments(self, m: GameMetrics):
        if len(m.mistakes_punished_moves) >= 1: 
            self._grant(m.game_id, 'punished-mistake-1', f"Punished an opponent's mistake (at {m.mistakes_punished_moves[0]})")
        if len(m.mistakes_punished_moves) >= 3: 
            self._grant(m.game_id, 'punished-mistake-3', f"Opportunist: Punished 3 mistakes in one game (3rd at {m.mistakes_punished_moves[2]})")
            
        if len(m.blunders_punished_moves) >= 1: 
            self._grant(m.game_id, 'punished-blunder-1', f"Punished an opponent's blunder (at {m.blunders_punished_moves[0]})")
        if len(m.blunders_punished_moves) >= 2: 
            self._grant(m.game_id, 'punished-blunder-2', f"Executioner: Punished multiple blunders in one game (2nd at {m.blunders_punished_moves[1]})")

    def check_feats(self, m: GameMetrics):
        """Evaluates rare, difficult, or highly specific feats."""
        # 3. The Botez Gambit
        if m.is_win and m.blundered_queen:
            self._grant(m.game_id, 'feat-botez-gambit', "Botez Gambit: Blundered your Queen and still won the game")
            
        # 4. The Iron Mind (120+ Moves)
        # Note: We don't require a win here. Just surviving 120 moves is a feat.
        if m.total_plies >= 240: 
            self._grant(m.game_id, 'feat-120-moves', "Iron Mind: Survive a grueling game of over 120 moves")
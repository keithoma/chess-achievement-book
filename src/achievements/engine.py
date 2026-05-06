import logging
from .metrics import GameMetrics

logger = logging.getLogger(__name__)

class AchievementEngine:
    """
    Evaluates GameMetrics against achievement rules and triggers database inserts.
    Organized strictly by logical achievement groupings.
    """
    def __init__(self, db_cursor, username):
        self.cur = db_cursor
        self.username = username

    def _grant(self, game_id, slug, print_msg):
        query = """
            INSERT INTO game_achievements (game_id, username, achievement_slug) 
            VALUES (%s, %s, %s) ON CONFLICT DO NOTHING RETURNING 1;
        """
        self.cur.execute(query, (game_id, self.username, slug))
        if self.cur.fetchone():
            logger.info(f"🎉 New Achievement [{self.username}]: {print_msg} (Game: {game_id})")
        else:
            logger.debug(f"  - Skipped: '{slug}' already granted for game {game_id}")

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

        pawns = m.clean_pawns_won
        if pawns >= 1: self._grant(m.game_id, 'clean-pawn-1', "Won a clean pawn and held it for 5+ turns")
        if pawns >= 2: self._grant(m.game_id, 'clean-pawn-2', "Won 2 clean pawns in a single game")
        if pawns >= 3: self._grant(m.game_id, 'clean-pawn-3', "Pawn Grabber: Won 3+ clean pawns in a single game")

    def check_punishments(self, m: GameMetrics):
        if m.mistakes_punished >= 1: self._grant(m.game_id, 'punished-mistake-1', "Punished an opponent's mistake")
        if m.mistakes_punished >= 3: self._grant(m.game_id, 'punished-mistake-3', "Opportunist: Punished 3 mistakes in one game")
        if m.blunders_punished >= 1: self._grant(m.game_id, 'punished-blunder-1', "Punished an opponent's blunder")
        if m.blunders_punished >= 2: self._grant(m.game_id, 'punished-blunder-2', "Executioner: Punished multiple blunders in one game")
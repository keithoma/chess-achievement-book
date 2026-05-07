"""
Achievement Scanner Orchestrator.

Scans analyzed games, calculates metrics, and evaluates them against 
the JSON achievement rules using the AchievementLedger.
"""

import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from src.database.connection import get_connection
from src.database.ledger import AchievementLedger
from src.achievements.metrics import GameMetrics

logger = logging.getLogger(__name__)

class AchievementScanner:
    def __init__(self, username: str, show_all: bool = False):
        self.username = username
        self.show_all = show_all
        self.ledger = AchievementLedger(username)
        self.configs = self._load_configs()

    def _load_configs(self) -> Dict[str, List[Dict[str, Any]]]:
        """Loads the JSON rule dictionaries into memory."""
        configs = {"badge": [], "mastery": [], "feat": [], "story": []}
        data_dir = Path(__file__).resolve().parent.parent.parent / "data" / "achievements"
        
        for filepath in data_dir.glob("*.json"):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        # Group by type (badge, mastery, etc.)
                        configs[item.get("type", "unknown")].append(item)
            except Exception as e:
                logger.error("Failed to load %s: %s", filepath.name, e)
                
        return configs

    def scan_games(self, limit: int = None, export_pgn: bool = False):
        """Fetches eligible games and pushes them through the evaluation pipeline."""
        logger.info("🏆 Scanning games for %s...", self.username)

        # Only select games where engine evaluation is complete (move_evals is populated)
        query = """
            SELECT id, score, speed, game_data 
            FROM games 
            WHERE (game_data->'players'->'white'->>'id' = %s 
               OR game_data->'players'->'black'->>'id' = %s)
              AND jsonb_array_length(game_data->'move_evals') > 0
            ORDER BY played_at DESC
        """
        if limit:
            query += f" LIMIT {limit}"

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (self.username, self.username))
                rows = cur.fetchall()

        if not rows:
            logger.warning("No un-scanned, analyzed games found in database for user: %s", self.username)
            return

        for game_id, score, speed, game_data in rows:
            metrics = GameMetrics(game_id, score, speed, game_data, self.username)
            
            # Run the 3-Stage Scan
            self._evaluate_badges(metrics)
            self._evaluate_mastery(metrics)
            self._evaluate_feats(metrics)
            
            if export_pgn:
                self._export_annotated_pgn(game_data)

    def _evaluate_badges(self, metrics: GameMetrics):
        """Maps Badge IDs to their specific triggering logic."""
        
        # A dictionary mapping the JSON ID to the metric condition that grants +1 progress
        badge_triggers = {
            "badge_played_total": 1,
            "badge_played_blitz": 1 if metrics.speed == "blitz" else 0,
            "badge_played_rapid": 1 if metrics.speed == "rapid" else 0,
            
            "badge_won_total": 1 if metrics.is_win else 0,
            "badge_won_blitz": 1 if metrics.is_win and metrics.speed == "blitz" else 0,
            "badge_won_rapid": 1 if metrics.is_win and metrics.speed == "rapid" else 0,
            
            "badge_no_blunders": 1 if metrics.is_win and metrics.blunders == 0 else 0,
            "badge_clean_pawns": len(metrics.clean_pawns_won_moves),
            "badge_punish_blunders": len(metrics.blunders_punished_moves)
            # Add the rest of your specific logic mapping here!
        }

        for badge in self.configs["badge"]:
            badge_id = badge["id"]
            progress_amount = badge_triggers.get(badge_id, 0)
            
            if progress_amount > 0:
                # Calculate if a new tier was reached (Logic omitted for brevity, 
                # but you would compare current DB progress + amount vs JSON config tiers)
                new_tier = None 
                
                self.ledger.record_progress(
                    game_id=metrics.game_id, 
                    def_id=badge_id, 
                    amount=progress_amount, 
                    newly_unlocked_tier=new_tier
                )

    def _evaluate_mastery(self, metrics: GameMetrics):
        """Matches ECO codes and awards EXP for opening mastery."""
        opening_eco = metrics.opening_eco
        opening_name = metrics.opening_name
        my_color = "white" if metrics.is_white else "black"

        for mastery in self.configs["mastery"]:
            cond = mastery.get("config", {}).get("conditions", {})
            
            if cond.get("color") not in ["any", my_color]:
                continue
                
            matched_eco = any(opening_eco.startswith(p) for p in cond.get("eco_prefixes", []))
            matched_name = any(n in opening_name for n in cond.get("name_includes", []))

            if matched_eco or matched_name:
                # Calculate EXP based on accuracy (Simplified example)
                exp = 50 if metrics.is_win else 10
                if metrics.blunders == 0: exp += 25
                
                self.ledger.record_progress(metrics.game_id, mastery["id"], exp)

    def _evaluate_feats(self, metrics: GameMetrics):
        """Checks for highly specific, one-time geometric/situational occurrences."""
        # e.g., if metrics.total_plies > 240: (120 moves)
        #     self.ledger.record_feat(metrics.game_id, "feat_marathon_120")
        pass

    def _export_annotated_pgn(self, game_data: Dict[str, Any]):
        """Saves the annotated PGN to the debug folder with custom naming."""
        output_dir = Path("debug/pgn_files")
        output_dir.mkdir(parents=True, exist_ok=True)

        annotated_content = game_data.get('annotated_pgn')
        if not annotated_content:
            return 

        ts = game_data.get('timestamp', 0)
        date_str = datetime.fromtimestamp(ts).strftime("%Y%m%d")
        
        is_white = game_data['players']['white']['id'].lower() == self.username.lower()
        color_str = "white" if is_white else "black"

        opening_name = game_data.get('opening', {}).get('name', 'Unknown Opening')
        safe_opening = re.sub(r'[\\/*?:"<>|]', "", opening_name)

        filename = f"{date_str} {color_str} {safe_opening}.pgn"
        file_path = output_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(annotated_content)
        
        logger.info("  📄 Exported Debug PGN: %s", filename)


# --- EXPORTED FUNCTION FOR ORCHESTRATOR ---
def process_achievements(username: str, limit: int = None, show_all: bool = False, export_pgn: bool = False):
    """Entry point for orchestrator.py"""
    scanner = AchievementScanner(username, show_all)
    scanner.scan_games(limit, export_pgn)
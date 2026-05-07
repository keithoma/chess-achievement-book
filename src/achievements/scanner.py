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
        # Fixed pathing to ensure data is found relative to the project root
        data_dir = Path(__file__).resolve().parent.parent.parent / "data" / "achievements"
        
        for filepath in data_dir.glob("*.json"):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        configs[item.get("type", "unknown")].append(item)
            except Exception as e:
                logger.error("Failed to load %s: %s", filepath.name, e)
                
        return configs

    def scan_games(self, limit: int = None, export_pgn: bool = False):
        """Fetches analyzed games and pushes them through the evaluation pipeline."""
        logger.info("🏆 Scanning games for %s...", self.username)

        # We use COALESCE and multiple paths to find the player ID 
        # because Lichess nesting can vary.
        query = """
            SELECT id, score, speed, game_data 
            FROM games 
            WHERE (
                LOWER(COALESCE(
                    game_data#>>'{players,white,user,id}', 
                    game_data#>>'{players,white,id}'
                )) = %s 
                OR 
                LOWER(COALESCE(
                    game_data#>>'{players,black,user,id}', 
                    game_data#>>'{players,black,id}'
                )) = %s
            )
            AND game_data->>'local_analysis_complete' = 'true'
            ORDER BY played_at DESC
        """
        if limit:
            query += f" LIMIT {limit}"

        with get_connection() as conn:
            with conn.cursor() as cur:
                # We pass the username in lowercase to match the DB
                cur.execute(query, (self.username.lower(), self.username.lower()))
                rows = cur.fetchall()

        if not rows:
            logger.warning("No analyzed games found in DB for path-check. Trying fallback search...")
            # Fallback: Just look for the string anywhere in the players JSON
            fallback_query = "SELECT id, score, speed, game_data FROM games WHERE game_data->'players'::text LIKE %s LIMIT 10"
            cur.execute(fallback_query, (f'%{self.username.lower()}%',))
            rows = cur.fetchall()

        if not rows:
            logger.error("❌ Seriously, no games found for %s. Check the table with 'SELECT * FROM games;'", self.username)
            return

        logger.info("🎯 Found %d games to scan!", len(rows))

        for game_id, score, speed, game_data in rows:
            metrics = GameMetrics(game_id, score, speed, game_data, self.username)
            
            self._evaluate_badges(metrics)
            self._evaluate_mastery(metrics)
            self._evaluate_feats(metrics)
            
            if export_pgn:
                self._export_annotated_pgn(game_data)

    def _evaluate_badges(self, metrics: GameMetrics):
        """Maps Badge IDs to their specific triggering logic."""
        is_win = getattr(metrics, 'is_win', False)
        speed = getattr(metrics, 'speed', 'unknown')
        
        badge_triggers = {
            "badge_played_total": 1,
            "badge_played_blitz": 1 if speed == "blitz" else 0,
            "badge_played_rapid": 1 if speed == "rapid" else 0,
            "badge_won_total": 1 if is_win else 0,
            "badge_won_blitz": 1 if is_win and speed == "blitz" else 0,
            "badge_won_rapid": 1 if is_win and speed == "rapid" else 0,
        }

        for badge in self.configs.get("badge", []):
            badge_id = badge["id"]
            progress_amount = badge_triggers.get(badge_id, 0)
            
            if progress_amount > 0:
                # Ledger now handles tier-checking internally
                self.ledger.record_progress(metrics.game_id, badge_id, progress_amount)

    def _evaluate_mastery(self, metrics: GameMetrics):
        """Matches ECO codes and awards EXP for opening mastery."""
        opening_eco = getattr(metrics, 'opening_eco', "")
        opening_name = getattr(metrics, 'opening_name', "")
        my_color = "white" if metrics.is_white else "black"

        for mastery_item in self.configs.get("mastery", []):
            cond = mastery_item.get("config", {}).get("conditions", {})
            
            # Check color requirement (any, white, or black)
            if cond.get("color", "any") not in ["any", my_color]:
                continue
                
            matched_eco = any(opening_eco.startswith(p) for p in cond.get("eco_prefixes", []))
            matched_name = any(n.lower() in opening_name.lower() for n in cond.get("name_includes", []))

            if matched_eco or matched_name:
                exp = 50 if metrics.is_win else 10
                # Bonus for clean games (if metrics supports it)
                if getattr(metrics, 'blunders', 1) == 0: 
                    exp += 25
                
                self.ledger.record_progress(metrics.game_id, mastery_item["id"], exp)

    def _evaluate_feats(self, metrics: GameMetrics):
        """Checks for situational occurrences (Marathons, comebacks, etc)."""
        pass

    def _export_annotated_pgn(self, game_data: Dict[str, Any]):
        """Saves annotated PGN with robust name and opening detection."""
        output_dir = Path("debug/pgn_files")
        output_dir.mkdir(parents=True, exist_ok=True)

        annotated_content = game_data.get('annotated_pgn')
        if not annotated_content:
            return 

        # 1. Date Extraction (Handle seconds or milliseconds)
        ts = game_data.get('timestamp') or (game_data.get('createdAt', 0) / 1000)
        date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        
        # 2. Aggressive Player Name Extraction
        def get_name(color):
            p = game_data.get('players', {}).get(color, {})
            # Tries: user.name -> name -> user.id -> id
            return (p.get('user', {}).get('name') or 
                    p.get('name') or 
                    p.get('user', {}).get('id') or 
                    p.get('id') or "Unknown")

        white = get_name('white')
        black = get_name('black')

        # 3. Aggressive Opening Extraction
        # Look at top level, then fall back to the raw API response
        opening_data = game_data.get('opening')
        if not opening_data:
            opening_data = game_data.get('raw_api_response', {}).get('opening')

        opening_name = "Unknown Opening"
        if isinstance(opening_data, dict):
            opening_name = opening_data.get('name', "Unknown Opening")
        elif isinstance(opening_data, str):
            opening_name = opening_data

        # Strip illegal characters for Windows/Linux/Mac filenames
        safe_opening = re.sub(r'[\\/*?:"<>|]', "", opening_name)

        # 4. Final filename assembly
        filename = f"{date_str} - {white} vs {black} - {safe_opening}.pgn"
        file_path = output_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(annotated_content)
        
        logger.info("  📄 Exported: %s", filename)


def process_achievements(username: str, limit: int = None, show_all: bool = False, export_pgn: bool = False):
    scanner = AchievementScanner(username, show_all)
    scanner.scan_games(limit, export_pgn)
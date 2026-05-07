"""
Quick and Dirty Terminal UI.

Queries the database to display a user's profile (achievements) 
and their recent game history ledger.
"""

import logging
from datetime import datetime
from src.database.connection import get_connection

logger = logging.getLogger(__name__)

def _format_date(date_obj):
    if not date_obj:
        return "Unknown Date"
    if isinstance(date_obj, str):
        return date_obj[:10]
    return date_obj.strftime("%Y-%m-%d")

def show_profile(username: str):
    """Displays unlocked trophies, badge progress, and mastery."""
    print(f"\n{'='*50}")
    print(f"👤 CHESS PROFILE: {username.upper()}")
    print(f"{'='*50}")

    unlocks_query = """
        SELECT ad.type, ad.category, ad.name, uu.tier, uu.unlocked_at
        FROM user_unlocks uu
        JOIN achievement_definitions ad ON uu.def_id = ad.id
        WHERE uu.username = %s
        ORDER BY ad.type, ad.category, uu.unlocked_at DESC;
    """
    
    progress_query = """
        SELECT ad.type, ad.name, up.current_value
        FROM user_progress up
        JOIN achievement_definitions ad ON up.def_id = ad.id
        WHERE up.username = %s
        ORDER BY ad.type, up.current_value DESC;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(unlocks_query, (username,))
            unlocks = cur.fetchall()
            
            cur.execute(progress_query, (username,))
            progress = cur.fetchall()

    if not unlocks and not progress:
        print("\n 🦗 *crickets* ... No data found. Play some games!")
        return

    # --- 1. TROPHY CABINET ---
    print("\n🏆 TROPHY CABINET (Unlocks)")
    print("-" * 50)
    if not unlocks:
        print("  (No trophies earned yet. Keep grinding!)")
    else:
        current_type = ""
        for ach_type, category, name, tier, unlocked_at in unlocks:
            if ach_type != current_type:
                print(f"\n  [{ach_type.upper()}]")
                current_type = ach_type
            date_str = _format_date(unlocked_at)
            tier_str = f"({tier.upper()})" if tier != 'base' else ""
            print(f"  ✨ {name:<25} {tier_str:<10} | {date_str}")

    # --- 2. ACTIVE PROGRESS ---
    print("\n\n📈 ACTIVE GRIND (Progress)")
    print("-" * 50)
    
    badges = [p for p in progress if p[0] == 'badge']
    mastery = [p for p in progress if p[0] == 'mastery']
    
    if badges:
        print("\n  [BADGES]")
        for _, name, val in badges:
            print(f"  📊 {name:<25} | {int(val)}/10 to Bronze")
            
    if mastery:
        print("\n  [MASTERY]")
        for _, name, val in mastery:
            print(f"  📚 {name:<25} | EXP: {val:.1f}")
            
    print(f"\n{'='*50}\n")


def show_history(username: str, limit: int = 10):
    """Displays the ledger of what was earned in recent games."""
    print(f"\n{'='*90}")
    print(f"📜 RECENT GAME HISTORY: {username.upper()}")
    print(f"{'='*90}")

    # JOIN with the 'games' table so we can extract the JSONB data for names and openings
    games_query = """
        SELECT ggl.game_id, MAX(ggl.granted_at) as recent_grant, g.game_data
        FROM game_grants_ledger ggl
        JOIN games g ON ggl.game_id = g.id
        WHERE ggl.username = %s
        GROUP BY ggl.game_id, g.game_data
        ORDER BY recent_grant DESC
        LIMIT %s;
    """

    # Fetch ad.description so we can show how the badge is earned
    ledger_query = """
        SELECT ad.name, ad.description, ad.type, ggl.change_amount, ggl.tier_unlocked
        FROM game_grants_ledger ggl
        JOIN achievement_definitions ad ON ggl.def_id = ad.id
        WHERE ggl.game_id = %s AND ggl.username = %s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(games_query, (username, limit))
            recent_games = cur.fetchall()

            if not recent_games:
                print("\n 🦗 No history found. Run the scanner first!")
                return

            for game_id, recent_grant, game_data_raw in recent_games:
                game_data = game_data_raw if isinstance(game_data_raw, dict) else json.loads(game_data_raw)
                
                # 1. Names
                white = game_data.get("players", {}).get("white", {}).get("user", {}).get("name", "Unknown")
                black = game_data.get("players", {}).get("black", {}).get("user", {}).get("name", "Unknown")
                
                # 2. Openings (Matching your JSON dump exactly)
                opening_obj = game_data.get("opening", {})
                opening = "Unknown Opening"
                if isinstance(opening_obj, dict):
                    opening = opening_obj.get("name", "Unknown Opening")

                date_str = _format_date(recent_grant)
                
                print(f"\n⚔️  {white} vs {black}")
                print(f"   Opening: {opening}")
                print(f"   [ID: {game_id} | Scanned: {date_str}]")
                print("-" * 90)
                        
    print(f"\n{'='*90}\n")
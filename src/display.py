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
    if isinstance(date_obj, str):
        return date_obj[:10]
    return date_obj.strftime("%Y-%m-%d")

def show_profile(username: str):
    """Displays unlocked trophies and mastery progress."""
    print(f"\n{'='*50}")
    print(f"👤 CHESS PROFILE: {username.upper()}")
    print(f"{'='*50}")

    # 1. Fetch Permanent Unlocks (Badges, Feats, Story)
    unlocks_query = """
        SELECT ad.type, ad.category, ad.name, uu.tier, uu.unlocked_at
        FROM user_unlocks uu
        JOIN achievement_definitions ad ON uu.def_id = ad.id
        WHERE uu.username = %s
        ORDER BY ad.type, ad.category, uu.unlocked_at DESC;
    """
    
    # 2. Fetch Mastery Progress
    mastery_query = """
        SELECT ad.category, ad.name, up.current_value
        FROM user_progress up
        JOIN achievement_definitions ad ON up.def_id = ad.id
        WHERE up.username = %s AND ad.type = 'mastery'
        ORDER BY up.current_value DESC;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(unlocks_query, (username,))
            unlocks = cur.fetchall()
            
            cur.execute(mastery_query, (username,))
            mastery = cur.fetchall()

    if not unlocks and not mastery:
        print("\n 🦗 *crickets* ... No achievements earned yet! Go play some games!")
        return

    print("\n🏆 TROPHY CABINET (Unlocks)")
    print("-" * 50)
    current_type = ""
    for ach_type, category, name, tier, unlocked_at in unlocks:
        if ach_type != current_type:
            print(f"\n  [{ach_type.upper()}]")
            current_type = ach_type
            
        date_str = _format_date(unlocked_at)
        tier_str = f"({tier.upper()})" if tier != 'base' else ""
        print(f"  ✨ {name:<30} {tier_str:<10} | {date_str}")

    print("\n\n🧠 MASTERY PROGRESS")
    print("-" * 50)
    for category, name, exp in mastery:
        print(f"  📚 {name:<30} | EXP: {exp:.1f}")
        
    print(f"\n{'='*50}\n")


def show_history(username: str, limit: int = 5):
    """Displays the ledger of what was earned in recent games."""
    print(f"\n{'='*60}")
    print(f"📜 RECENT GAME HISTORY: {username.upper()}")
    print(f"{'='*60}")

    # Fetch the most recent distinct games that have ledger entries
    games_query = """
        SELECT DISTINCT game_id, granted_at
        FROM game_grants_ledger
        WHERE username = %s
        ORDER BY granted_at DESC
        LIMIT %s;
    """

    ledger_query = """
        SELECT ad.name, ad.type, ggl.change_amount, ggl.tier_unlocked
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

            for game_id, granted_at in recent_games:
                date_str = _format_date(granted_at)
                print(f"\n⚔️  GAME ID: {game_id} | Scanned on: {date_str}")
                print("-" * 60)
                
                cur.execute(ledger_query, (game_id, username))
                grants = cur.fetchall()
                
                for name, ach_type, amount, tier in grants:
                    if ach_type == 'feat' or ach_type == 'story':
                        print(f"   🎉 UNLOCKED: {name}")
                    elif ach_type == 'mastery':
                        print(f"   📈 {name:<25} | +{amount} EXP")
                        if tier:
                            print(f"      🌟 RANK UP! Reached {tier} tier!")
                    elif ach_type == 'badge':
                        print(f"   📊 {name:<25} | +{amount} Progress")
                        if tier:
                            print(f"      🏅 BADGE UPGRADED! Reached {tier.upper()} tier!")
                            
    print(f"\n{'='*60}\n")
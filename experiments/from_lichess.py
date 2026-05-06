import requests
import json

def parse_player(player_data):
    """Translates Lichess player objects (human or AI) into our schema."""
    # Handle AI (Lichess doesn't provide user objects for their built-in bot)
    if 'aiLevel' in player_data:
        level = player_data['aiLevel']
        return {
            "id": f"stockfish_level_{level}",
            "name": f"Lichess AI Level {level}",
            "rating": 1500, # Default rating for AI placeholder
            "is_bot": True,
            "patron": False
        }
    
    # Handle Humans and Registered Bots
    user_info = player_data.get('user', {})
    return {
        "id": user_info.get('id', 'unknown'),
        "name": user_info.get('name', 'Unknown'),
        "rating": player_data.get('rating', 1500), # Default if casual/unrated
        "is_bot": user_info.get('title') == 'BOT',
        "patron": user_info.get('patron', False)
    }

def get_score(winner_flag):
    """Converts 'white'/'black'/None into standard chess scores."""
    if winner_flag == 'white': return '1-0'
    if winner_flag == 'black': return '0-1'
    return '1/2-1/2' # Draw or unfinished

def format_game_data(raw_game):
    """Maps the raw Lichess JSON to our future-proof schema."""
    clock_info = raw_game.get('clock', {})
    
    formatted_game = {
        "id": raw_game.get('id'),
        "platform": "lichess",
        # Lichess gives createdAt in milliseconds, convert to seconds
        "timestamp": raw_game.get('createdAt', 0) // 1000, 
        "is_rated": raw_game.get('rated', False),
        "is_friend": raw_game.get('source') == 'friend',
        "speed": raw_game.get('speed', 'unknown'),
        "rules": {
            "initial": clock_info.get('initial', 0),
            "increment": clock_info.get('increment', 0)
        },
        "players": {
            "white": parse_player(raw_game.get('players', {}).get('white', {})),
            "black": parse_player(raw_game.get('players', {}).get('black', {}))
        },
        "score": get_score(raw_game.get('winner')),
        "termination": raw_game.get('status', 'unknown'),
        "opening": {
            "eco": raw_game.get('opening', {}).get('eco', ''),
            "name": raw_game.get('opening', {}).get('name', '')
        },
        "moves": raw_game.get('moves', ''),
        "move_times": raw_game.get('clocks', []),
        "division": raw_game.get('division', {})
    }
    
    # Optional: Save server analysis if Lichess already computed blunders/inaccuracies
    if 'analysis' in raw_game:
        formatted_game['analysis'] = raw_game['analysis']
        
    return formatted_game

def fetch_pure_standard_games(username, limit=10):
    url = f"https://lichess.org/api/games/user/{username}"
    
    params = {
        'max': limit,
        'perfType': 'bullet,blitz,rapid,classical', 
        'moves': 'true',
        'opening': 'true',
        'division': 'true', 
        'clocks': 'true'
    }
    
    headers = {'Accept': 'application/x-ndjson'}
    
    print(f"🔍 Fetching games for {username} (Filtering out position variants)...")
    
    response = requests.get(url, params=params, headers=headers, stream=True)
    
    if response.status_code == 200:
        filename = f"{username}_clean.jsonl"
        with open(filename, "w") as f:
            for line in response.iter_lines():
                if line:
                    raw_game = json.loads(line)
                    
                    # LOGIC: 'initialFen' only exists if the game didn't start 
                    # from the standard board setup.
                    if 'initialFen' in raw_game:
                        print(f"⏩ Skipping Position Variant/Custom Start: {raw_game.get('id')}")
                        continue
                        
                    # Skip games with fewer than 4 plies (2 full moves) to prevent garbage data
                    moves_list = raw_game.get('moves', '').split()
                    if len(moves_list) < 4:
                        print(f"⏩ Skipping aborted/tiny game: {raw_game.get('id')}")
                        continue
                    
                    # Apply our formatting map
                    clean_game = format_game_data(raw_game)
                    
                    f.write(json.dumps(clean_game) + "\n")
                    print(f"✅ Saved Formatted Game: {clean_game.get('id')}")
        print(f"🎉 Done! File saved as {filename}")
    else:
        print(f"Error: {response.status_code}")

# Run the test
fetch_pure_standard_games('thibault', limit=10)
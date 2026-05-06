import requests
import json

def parse_player(player_data):
    """Translates Lichess player objects into our schema."""
    if 'aiLevel' in player_data:
        level = player_data['aiLevel']
        return {
            "id": f"stockfish_level_{level}",
            "name": f"Lichess AI Level {level}",
            "rating": 1500,
            "is_bot": True,
            "patron": False
        }
    
    user_info = player_data.get('user', {})
    return {
        "id": user_info.get('id', 'unknown'),
        "name": user_info.get('name', 'Unknown'),
        "rating": player_data.get('rating', 1500),
        "is_bot": user_info.get('title') == 'BOT',
        "patron": user_info.get('patron', False)
    }

def get_score(winner_flag):
    if winner_flag == 'white': return '1-0'
    if winner_flag == 'black': return '0-1'
    return '1/2-1/2'

def format_game_data(raw_game):
    """Maps the raw Lichess JSON to our schema including evaluations."""
    clock_info = raw_game.get('clock', {})
    
    # We extract move-by-move evals if the game was already analyzed on Lichess
    # Note: 'analysis' is a list where each entry is {'eval': centipawns, ...}
    move_evals = []
    if 'analysis' in raw_game:
        for ply in raw_game['analysis']:
            if 'eval' in ply:
                move_evals.append(ply['eval'])
            elif 'mate' in ply:
                # Store mates as a high number (e.g., 9999 for white mate, -9999 for black)
                move_evals.append(9999 if ply['mate'] > 0 else -9999)

    formatted_game = {
        "id": raw_game.get('id'),
        "platform": "lichess",
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
        "move_evals": move_evals, # New field: Centipawn values per ply
        "division": raw_game.get('division', {})
    }
    
    return formatted_game

def fetch_pure_standard_games(username, limit=10):
    url = f"https://lichess.org/api/games/user/{username}"
    
    params = {
        'max': limit,
        'perfType': 'bullet,blitz,rapid,classical', 
        'moves': 'true',
        'opening': 'true',
        'division': 'true', 
        'clocks': 'true',
        'evals': 'true' # THE KEY PARAMETER: requests move-by-move Stockfish evals
    }
    
    headers = {'Accept': 'application/x-ndjson'}
    
    print(f"🔍 Fetching games for {username} with evaluations...")
    
    response = requests.get(url, params=params, headers=headers, stream=True)
    
    if response.status_code == 200:
        filename = f"{username}_clean_with_evals.jsonl"
        with open(filename, "w") as f:
            for line in response.iter_lines():
                if line:
                    raw_game = json.loads(line)
                    if 'initialFen' in raw_game: continue
                    if len(raw_game.get('moves', '').split()) < 4: continue
                    
                    clean_game = format_game_data(raw_game)
                    f.write(json.dumps(clean_game) + "\n")
                    
                    status = "Eval Found" if clean_game['move_evals'] else "No Eval"
                    print(f"✅ Game {clean_game['id']} ({status})")
    else:
        print(f"Error: {response.status_code}")

fetch_pure_standard_games('thibault', limit=5)
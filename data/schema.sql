-- 1. User Table
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Achievement Definitions
CREATE TABLE IF NOT EXISTS achievement_definitions (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL, 
    category TEXT,
    subcategory TEXT,
    name TEXT NOT NULL,
    description TEXT,
    flavor_text TEXT,
    is_hidden BOOLEAN DEFAULT FALSE,
    config JSONB DEFAULT '{}'
);

-- 3. User Progress
CREATE TABLE IF NOT EXISTS user_progress (
    username TEXT REFERENCES users(username),
    def_id TEXT REFERENCES achievement_definitions(id),
    current_value FLOAT DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (username, def_id)
);

-- 4. User Unlocks
CREATE TABLE IF NOT EXISTS user_unlocks (
    username TEXT REFERENCES users(username),
    def_id TEXT REFERENCES achievement_definitions(id),
    tier TEXT DEFAULT 'base',
    unlocked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (username, def_id, tier)
);

-- 5. Games Table (FIXED WITH PLATFORM AND RATED)
CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    platform TEXT DEFAULT 'lichess',
    played_at TIMESTAMP WITH TIME ZONE,
    rated BOOLEAN,
    speed TEXT,
    score TEXT,
    game_data JSONB
);

-- 6. The Ledger
CREATE TABLE IF NOT EXISTS game_grants_ledger (
    id SERIAL PRIMARY KEY,
    game_id TEXT REFERENCES games(id),
    username TEXT REFERENCES users(username),
    def_id TEXT REFERENCES achievement_definitions(id),
    change_amount FLOAT,
    tier_unlocked TEXT,
    granted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

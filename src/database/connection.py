"""
Database Connection Utility
---------------------------
This module handles the initialization of the PostgreSQL connection using 
environment variables. It serves as the primary entry point for database 
interaction within the chess-achievement-book application.
"""

import os
import sys
from typing import Optional
from dotenv import load_dotenv
from psycopg import Connection, Cursor

load_dotenv()
DB_URI: Optional[str] = os.getenv("DATABASE_URL")

def get_connection() -> Connection:
    """
    Creates and returns a new connection to the PostgreSQL database.
    
    Returns:
        psycopg.Connection: A connection object ready for queries.
        
    Raises:
        psycopg.Error: If the connection could not be established.
        ValueError: If DATABASE_URL is missing from the .env file.
    """
    if not DB_URI:
        raise ValueError("❌ DATABASE_URL not found in .env. Check your configuration.")
    
    return psycopg.connect(DB_URI)

def test_connection() -> None:
    """
    Performs a connection test to ensure the database is reachable.
    Prints status to the console.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                version = cur.fetchone()
                print("✅ Successfully connected to PostgreSQL!")
                print(f"🖥️  Server version: {version[0]}")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_connection()
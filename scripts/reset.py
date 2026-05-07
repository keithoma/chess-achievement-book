from chess_achievement_book.database.connection import get_connection


def main():
    print("🧹 Clearing achievement data...")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                TRUNCATE game_grants_ledger,
                         user_progress,
                         user_unlocks
                CASCADE;
            """)
        conn.commit()

    print("✨ Database cleared. You can now re-scan your games.")


if __name__ == "__main__":
    main()
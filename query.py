import sqlite3

def show_all_tables(db_path='database.db'):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row['name'] for row in cursor.fetchall()]

    print("\n--- DATABASE CONTENTS ---\n")
    for table in tables:
        print(f"--- {table} ---")
        try:
            rows = cursor.execute(f"SELECT * FROM {table}").fetchall()
            for row in rows:
                print(dict(row))
        except Exception as e:
            print(f"Error reading {table}: {e}")
        print()

    conn.close()

if __name__ == '__main__':
    show_all_tables()

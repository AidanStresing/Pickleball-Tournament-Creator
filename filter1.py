import pandas as pd
import sqlite3

def insert_courts_with_coords(csv_path, db_path, start_at_one=True):
    df = pd.read_csv(csv_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS COURT_PARK (
        C_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Name TEXT NOT NULL,
        Address TEXT NOT NULL,
        Open_Time TIME,
        Latitude REAL,
        Longitude REAL
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS INDIVIDUAL_COURTS (
        COURT_NUM INTEGER,
        C_ID INTEGER,
        PRIMARY KEY (COURT_NUM, C_ID),
        FOREIGN KEY (C_ID) REFERENCES COURT_PARK(C_ID)
    )
    ''')

    total_courts_inserted = 0

    for _, row in df.iterrows():
        name = row["Name"]
        address = row["Address"]
        open_time = row["Open_Time"]
        latitude = row["Latitude"]
        longitude = row["Longitude"]
        num_courts = int(row["Num"])

        cursor.execute('''
        INSERT INTO COURT_PARK (Name, Address, Open_Time, Latitude, Longitude)
        VALUES (?, ?, ?, ?, ?)
        ''', (name, address, open_time, latitude, longitude))

        c_id = cursor.lastrowid

        start = 1 if start_at_one else 0
        for court_num in range(start, start + num_courts):
            cursor.execute('''
            INSERT INTO INDIVIDUAL_COURTS (COURT_NUM, C_ID)
            VALUES (?, ?)
            ''', (court_num, c_id))
            total_courts_inserted += 1

    conn.commit()
    conn.close()

    print(f"Successfully inserted {len(df)} parks and {total_courts_inserted} individual courts into '{db_path}'")

if __name__ == "__main__":
    insert_courts_with_coords("court_data_with_coords.csv", "database.db", start_at_one=True)

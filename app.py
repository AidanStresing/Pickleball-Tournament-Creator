from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import sqlite3
import random
from math import radians, sin, cos, sqrt, atan2
from flask import jsonify, request
import os


app = Flask(__name__)
DATABASE = 'database.db'


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  
    return conn

# Calculate distance 
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

@app.route('/get_nearby_parks', methods=['POST'])
def get_nearby_parks():
    import math
    data = request.json
    user_lat = float(data['lat'])
    user_lng = float(data['lng'])

    def haversine(lat1, lon1, lat2, lon2):
        R = 3958.8  
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)
        a = math.sin(d_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda/2)**2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    parks = conn.execute('SELECT C_ID, Name, Address, Open_Time, Latitude, Longitude FROM COURT_PARK').fetchall()
    park_list = []
    for park in parks:
        distance = haversine(user_lat, user_lng, park['Latitude'], park['Longitude'])
        num_courts = conn.execute('SELECT COUNT(*) FROM INDIVIDUAL_COURTS WHERE C_ID = ?', (park['C_ID'],)).fetchone()[0]
        park_list.append({
            'C_ID': park['C_ID'],
            'Name': park['Name'],
            'Address': park['Address'],
            'Open_Time': park['Open_Time'],
            'Num': num_courts,
            'Distance': distance
        })
    park_list.sort(key=lambda x: x['Distance'])
    conn.close()

    return jsonify({'parks': park_list[:10]})


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/')
def index():
    conn = get_db_connection()
    tournaments = conn.execute("SELECT * FROM TOURNAMENT WHERE Status = 'active'").fetchall()
    conn.close()
    return render_template('index.html', tournaments=tournaments)

@app.route('/create', methods=['GET', 'POST'])
def create_tournament():
    if request.method == 'POST':
        date = request.form['date']
        tournament_type = request.form['type']
        prize = request.form['prize']
        location = request.form['location']

        # Get next tournament ID
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT MAX(T_ID) FROM TOURNAMENT')
        row = cursor.fetchone()
        next_tid = 1 if row[0] is None else row[0] + 1

        # Insert tournament
        cursor.execute('INSERT INTO TOURNAMENT (T_ID, Date, Type, Prize, C_ID) VALUES (?, ?, ?, ?, ?)',
                       (next_tid, date, tournament_type, prize, location))

        # Insert players
        names = request.form.getlist('player_name[]')
        ages = request.form.getlist('player_age[]')
        genders = request.form.getlist('player_gender[]')

        # Inside your POST block of /create_tournament
        for name, age, gender in zip(names, ages, genders):
            # Check if player exists
            cursor.execute('SELECT P_ID, T_ID FROM PLAYER WHERE Name = ? AND Age = ? AND Gender = ?', (name, age, gender))
            existing = cursor.fetchone()

            if existing:
                pid = existing['P_ID']
                existing_tid = existing['T_ID']

                if existing_tid:
                    # Check if that tournament is still active
                    cursor.execute("SELECT Status FROM TOURNAMENT WHERE T_ID = ?", (existing_tid,))
                    status_row = cursor.fetchone()
                    if status_row and status_row['Status'] == 'active':
                        # Player is still in an active tournament
                        conn.close()
                        return f"Player {name} is already in an active tournament and cannot be added to this one.", 400

                # If player was in a completed tournament, reassign to new T_ID
                cursor.execute("UPDATE PLAYER SET T_ID = ? WHERE P_ID = ?", (next_tid, pid))
            else:
                # Create a new player
                cursor.execute('SELECT MAX(P_ID) FROM PLAYER')
                row = cursor.fetchone()
                next_pid = 1 if row[0] is None else row[0] + 1

                cursor.execute('INSERT INTO PLAYER (P_ID, Name, Age, Gender, T_ID) VALUES (?, ?, ?, ?, ?)',
                            (next_pid, name, age, gender, next_tid))

        conn.commit()
        conn.close()
        generate_games_for_tournament(next_tid)
        return redirect(url_for('edit_bracket', tournament_id=next_tid))

    return render_template('create.html')

@app.route('/autocomplete')
def autocomplete():
    term = request.args.get('term')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT Name FROM PLAYER WHERE Name LIKE ?", (f"{term}%",))
    results = [row['Name'] for row in cursor.fetchall()]
    conn.close()
    return {"results": results}

def paginate_items(items, page, per_page):
    from math import ceil
    total_items = len(items)
    total_pages = ceil(total_items / per_page)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        'items': items[start:end],
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'total_items': total_items
    }


@app.route('/players')
def manage_players():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))  

    conn = get_db_connection()
    players = conn.execute("SELECT * FROM PLAYER").fetchall()
    conn.close()

    paginated = paginate_items(players, page, per_page)

    return render_template('players.html',
                           players=paginated['items'],
                           page=paginated['page'],
                           total_pages=paginated['total_pages'],
                           per_page=paginated['per_page'])

@app.route('/search_players', methods=['GET'])
def search_players():
    name = request.args.get('name', '')
    gender = request.args.get('gender', '')
    age = request.args.get('age', '')
    tid = request.args.get('tid', '')

    conn = get_db_connection()
    query = "SELECT * FROM PLAYER WHERE 1=1"
    params = []

    if name:
        query += " AND Name LIKE ?"
        params.append(f"%{name}%")
    if gender:
        query += " AND Gender = ?"
        params.append(gender)
    if age:
        query += " AND Age = ?"
        params.append(age)
    if tid:
        query += " AND T_ID = ?"
        params.append(tid)

    players = conn.execute(query, params).fetchall()
    conn.close()

    return render_template('players.html',
                           players=players,
                           page=1,
                           total_pages=1,
                           per_page=10)  


@app.route('/edit_player', methods=['POST'])
def edit_player():
    p_id = request.form['p_id']
    name = request.form['name']
    age = request.form['age']
    gender = request.form['gender']

    conn = get_db_connection()
    conn.execute('UPDATE PLAYER SET Name = ?, Age = ?, Gender = ? WHERE P_ID = ?',
                 (name, age, gender, p_id))
    conn.commit()
    conn.close()
    return redirect(url_for('manage_players'))

@app.route('/delete_player', methods=['POST'])
def delete_player():
    p_id = request.form['p_id']

    conn = get_db_connection()
    conn.execute('DELETE FROM PLAYER WHERE P_ID = ?', (p_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('manage_players'))

@app.route('/add_player', methods=['POST'])
def add_player():
    name = request.form['name'].strip()
    age = request.form['age']
    gender = request.form['gender']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM PLAYER WHERE Name = ? AND Age = ? AND Gender = ?", (name, age, gender))
    if cursor.fetchone():
        conn.close()
        return redirect(url_for('manage_players'))  

    cursor.execute("SELECT MAX(P_ID) FROM PLAYER")
    row = cursor.fetchone()
    next_pid = 1 if row[0] is None else row[0] + 1

    cursor.execute("INSERT INTO PLAYER (P_ID, Name, Age, Gender, T_ID) VALUES (?, ?, ?, ?, NULL)",
                   (next_pid, name, age, gender))

    conn.commit()
    conn.close()
    return redirect(url_for('manage_players'))

@app.route('/update_player', methods=['POST'])
def update_player():
    p_id = request.form['p_id']
    name = request.form['name']
    age = request.form['age']
    gender = request.form['gender']

    conn = get_db_connection()
    conn.execute("""
        UPDATE PLAYER SET Name = ?, Age = ?, Gender = ? WHERE P_ID = ?
    """, (name, age, gender, p_id))

    conn.commit()
    conn.close()
    return redirect(url_for('manage_players'))

@app.route('/bracket/<int:tournament_id>')
def show_bracket(tournament_id):
    conn = get_db_connection()
    players = conn.execute("SELECT * FROM PLAYER WHERE T_ID = ?", (tournament_id,)).fetchall()
    conn.close()

    player_list = [dict(p) for p in players]

    return render_template('edit_bracket.html', players=player_list, tid=tournament_id)

@app.route('/edit_tournament')
def edit_tournaments():
    conn = get_db_connection()

    # Get all active tournaments
    tournaments = conn.execute("SELECT * FROM TOURNAMENT WHERE Status = 'active'").fetchall()

    # Get number of players per tournament using GROUP BY
    player_counts = conn.execute('''
        SELECT T_ID, COUNT(*) as count
        FROM PLAYER
        WHERE T_ID IS NOT NULL
        GROUP BY T_ID
    ''').fetchall()

    # Map T_ID → player count
    count_map = {row['T_ID']: row['count'] for row in player_counts}

    conn.close()

    return render_template('edit_tournament.html', tournaments=tournaments, player_counts=count_map)

@app.route('/update_tournament', methods=['POST'])
def update_tournament():
    t_id = request.form['t_id']
    date = request.form['date']
    prize = request.form['prize']
    location = request.form['location']

    conn = get_db_connection()
    conn.execute('UPDATE TOURNAMENT SET Date = ?, Prize = ?, C_ID = ? WHERE T_ID = ?',
                 (date, prize, location, t_id))
    conn.commit()
    conn.close()
    return redirect(url_for('edit_tournaments'))

@app.route('/delete_tournament', methods=['POST'])
def delete_tournament():
    t_id = request.form['t_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # Set players' T_ID to NULL
    cursor.execute("UPDATE PLAYER SET T_ID = NULL WHERE T_ID = ?", (t_id,))

    # Delete player-game links
    cursor.execute("DELETE FROM PLAYER_GAME WHERE T_ID = ?", (t_id,))
    cursor.execute("DELETE FROM GAME_COURT WHERE T_ID = ?", (t_id,))
    cursor.execute("DELETE FROM GAME WHERE T_ID = ?", (t_id,))

    # Finally delete the tournament
    cursor.execute("DELETE FROM TOURNAMENT WHERE T_ID = ?", (t_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('edit_tournaments'))


@app.route('/edit_bracket_done/<int:tournament_id>')
def edit_bracket_done(tournament_id):
    import math
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get tournament info and address
    tournament = conn.execute("""
        SELECT T.*, C.Address
        FROM TOURNAMENT T
        JOIN COURT_PARK C ON T.C_ID = C.C_ID
        WHERE T.T_ID = ?
    """, (tournament_id,)).fetchone()

    is_doubles = tournament["Type"][-1] == "D"  

    # Pull only players who played in this tournament (via PLAYER_GAME)
    pg_rows = conn.execute("SELECT DISTINCT P_ID FROM PLAYER_GAME WHERE T_ID = ?", (tournament_id,)).fetchall()
    player_ids = [row['P_ID'] for row in pg_rows]

    if player_ids:
        placeholders = ','.join('?' * len(player_ids))
        query = f"SELECT P_ID, Name FROM PLAYER WHERE P_ID IN ({placeholders})"
        player_rows = conn.execute(query, player_ids).fetchall()
        pid_to_name = {row['P_ID']: row['Name'] for row in player_rows}
    else:
        pid_to_name = {}

    # Get all games
    games = conn.execute("SELECT * FROM GAME WHERE T_ID = ?", (tournament_id,)).fetchall()
    game_map = {game['G_ID']: dict(game) for game in games}

    # Get PLAYER_GAME links
    pg_rows = conn.execute("SELECT P_ID, G_ID FROM PLAYER_GAME WHERE T_ID = ?", (tournament_id,)).fetchall()
    player_game = {}
    for row in pg_rows:
        player_game.setdefault(row['G_ID'], []).append(row['P_ID'])

    # Get court info
    gc_rows = conn.execute("SELECT * FROM GAME_COURT WHERE T_ID = ?", (tournament_id,)).fetchall()
    court_map = {row['G_ID']: row['COURT_NUM'] for row in gc_rows}

    # Determine bracket structure
    total_players = len(player_ids)
    row = conn.execute("SELECT MAX(Round) as max_round FROM GAME WHERE T_ID = ?", (tournament_id,)).fetchone()
    num_rounds = row["max_round"] if row and row["max_round"] else 1
    bracket_size = 2 ** num_rounds

    bracket_by_round = {}

    def resolve_name(pid, is_first_round):
        return pid_to_name.get(pid, "BYE" if is_first_round else "TBD")

    for g_id, game in game_map.items():
        round_num = game['Round']
        result_pid = game.get('Result')
        p_ids = player_game.get(g_id, [])

        winner = None

        if is_doubles:
            team1 = [resolve_name(pid, round_num == 1) for pid in p_ids[:2]]
            team2 = [resolve_name(pid, round_num == 1) for pid in p_ids[2:]]
            player1 = " & ".join(team1) if team1 else ("BYE" if round_num == 1 else "TBD")
            player2 = " & ".join(team2) if team2 else ("BYE" if round_num == 1 else "TBD")

            # Check if winner is in team1 or team2
            if result_pid in p_ids[:2]:
                winner = player1
            elif result_pid in p_ids[2:]:
                winner = player2
        else:
            player1 = resolve_name(p_ids[0], round_num == 1) if len(p_ids) > 0 else ("BYE" if round_num == 1 else "TBD")
            player2 = resolve_name(p_ids[1], round_num == 1) if len(p_ids) > 1 else ("BYE" if round_num == 1 else "TBD")
            winner = pid_to_name.get(result_pid)

        bracket_by_round.setdefault(round_num - 1, []).append({
            'player1': player1,
            'player2': player2,
            'time': game['Time'],
            'court': court_map.get(g_id),
            'g_id': g_id,
            'winner': winner
        })

    conn.close()

    return render_template(
        'edit_bracket_done.html',
        tournament=tournament,
        bracket_by_round=bracket_by_round,
        bracket_size=bracket_size,
        num_rounds=num_rounds,
        is_doubles=is_doubles
    )


@app.route('/edit_bracket/<int:tournament_id>')
def edit_bracket(tournament_id):
    import math
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get tournament info and address
    tournament = conn.execute("""
        SELECT T.*, C.Address
        FROM TOURNAMENT T
        JOIN COURT_PARK C ON T.C_ID = C.C_ID
        WHERE T.T_ID = ?
    """, (tournament_id,)).fetchone()

    is_doubles = tournament["Type"][-1] == "D"  

    # Pull only players who played in this tournament (via PLAYER_GAME)
    pg_rows = conn.execute("SELECT DISTINCT P_ID FROM PLAYER_GAME WHERE T_ID = ?", (tournament_id,)).fetchall()
    player_ids = [row['P_ID'] for row in pg_rows]

    if player_ids:
        placeholders = ','.join('?' * len(player_ids))
        query = f"SELECT P_ID, Name FROM PLAYER WHERE P_ID IN ({placeholders})"
        player_rows = conn.execute(query, player_ids).fetchall()
        pid_to_name = {row['P_ID']: row['Name'] for row in player_rows}
    else:
        pid_to_name = {}

    # Get all games
    games = conn.execute("SELECT * FROM GAME WHERE T_ID = ?", (tournament_id,)).fetchall()
    game_map = {game['G_ID']: dict(game) for game in games}

    # Get PLAYER_GAME links
    pg_rows = conn.execute("SELECT P_ID, G_ID FROM PLAYER_GAME WHERE T_ID = ?", (tournament_id,)).fetchall()
    player_game = {}
    for row in pg_rows:
        player_game.setdefault(row['G_ID'], []).append(row['P_ID'])

    # Get court info
    gc_rows = conn.execute("SELECT * FROM GAME_COURT WHERE T_ID = ?", (tournament_id,)).fetchall()
    court_map = {row['G_ID']: row['COURT_NUM'] for row in gc_rows}

    # Determine bracket structure
    total_players = len(player_ids)
    row = conn.execute("SELECT MAX(Round) as max_round FROM GAME WHERE T_ID = ?", (tournament_id,)).fetchone()
    num_rounds = row["max_round"] if row and row["max_round"] else 1
    bracket_size = 2 ** num_rounds

    bracket_by_round = {}

    def resolve_name(pid, is_first_round):
        return pid_to_name.get(pid, "BYE" if is_first_round else "TBD")

    for g_id, game in game_map.items():
        round_num = game['Round']
        result_pid = game.get('Result')
        p_ids = player_game.get(g_id, [])

        winner = None

        if is_doubles:
            team1 = [resolve_name(pid, round_num == 1) for pid in p_ids[:2]]
            team2 = [resolve_name(pid, round_num == 1) for pid in p_ids[2:]]
            player1 = " & ".join(team1) if team1 else ("BYE" if round_num == 1 else "TBD")
            player2 = " & ".join(team2) if team2 else ("BYE" if round_num == 1 else "TBD")

            # Check if winner is in team1 or team2
            if result_pid in p_ids[:2]:
                winner = player1
            elif result_pid in p_ids[2:]:
                winner = player2
        else:
            player1 = resolve_name(p_ids[0], round_num == 1) if len(p_ids) > 0 else ("BYE" if round_num == 1 else "TBD")
            player2 = resolve_name(p_ids[1], round_num == 1) if len(p_ids) > 1 else ("BYE" if round_num == 1 else "TBD")
            winner = pid_to_name.get(result_pid)

        bracket_by_round.setdefault(round_num - 1, []).append({
            'player1': player1,
            'player2': player2,
            'time': game['Time'],
            'court': court_map.get(g_id),
            'g_id': g_id,
            'winner': winner
        })

    conn.close()

    return render_template(
        'edit_bracket.html',
        tournament=tournament,
        bracket_by_round=bracket_by_round,
        bracket_size=bracket_size,
        num_rounds=num_rounds,
        is_doubles=is_doubles
    )



@app.route('/search_past_tournaments', methods=['GET'])
def search_past_tournaments():
    date = request.args.get('date', '')
    prize = request.args.get('prize', '')
    t_type = request.args.get('type', '')
    court_id = request.args.get('court', '')

    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))

    query = "SELECT * FROM TOURNAMENT WHERE Status = 'completed'"
    params = []

    if date:
        query += " AND Date = ?"
        params.append(date)
    if prize:
        query += " AND Prize >= ?"
        params.append(prize)
    if t_type:
        query += " AND Type = ?"
        params.append(t_type)
    if court_id:
        query += " AND C_ID = ?"
        params.append(court_id)

    conn = get_db_connection()
    tournaments = conn.execute(query, tuple(params)).fetchall()
    conn.close()

    paginated = paginate_items(tournaments, page, per_page)

    return render_template(
        'past_tournaments.html',
        tournaments=paginated['items'],
        page=paginated['page'],
        per_page=paginated['per_page'],
        total_pages=paginated['total_pages']
    )

@app.route('/update_bracket/<int:tournament_id>', methods=['POST'])
def update_bracket(tournament_id):
    p1 = request.form['p1']
    p2 = request.form['p2']
    match_index = int(request.form['match_index'])

    print(f"Match {match_index}: {p1} vs {p2} (Tournament {tournament_id})")
    generate_games_for_tournament(next_tid)
    return redirect(url_for('edit_bracket', tournament_id=tournament_id))

def generate_games_for_tournament(t_id):
    import math
    import random

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get tournament type
    t_type = cursor.execute("SELECT Type FROM TOURNAMENT WHERE T_ID = ?", (t_id,)).fetchone()['Type']
    is_doubles = t_type in ("MD", "WD", "MID")  

    # Get players (just for count/bracket size)
    cursor.execute("SELECT P_ID, Name FROM PLAYER WHERE T_ID = ?", (t_id,))
    player_rows = cursor.fetchall()
    players = [{'P_ID': row['P_ID'], 'Name': row['Name']} for row in player_rows]
    random.shuffle(players)

    # Determine how many teams we’ll need
    if is_doubles:
        teams = [players[i:i+2] for i in range(0, len(players), 2)]
        if len(teams[-1]) == 1:
            teams[-1].append({'P_ID': None, 'Name': 'BYE'})  
    else:
        teams = [[p] for p in players]

    total_teams = len(teams)
    if total_teams < 2:
        conn.close()
        return players

    # Bracket math
    bracket_size = 1
    while bracket_size < total_teams:
        bracket_size *= 2
    num_games = bracket_size - 1
    num_rounds = int(math.log2(bracket_size))

    # Get next G_ID
    cursor.execute("SELECT MAX(G_ID) FROM GAME")
    row = cursor.fetchone()
    next_gid = 1 if row[0] is None else row[0] + 1
    game_ids = []

    for i in range(num_games):
        g_id = next_gid + i
        round_num = num_rounds - int(math.floor(math.log2(num_games + 1 - (i + 1))))
        cursor.execute(
            "INSERT INTO GAME (G_ID, T_ID, Round, Result, Time) VALUES (?, ?, ?, NULL, NULL)",
            (g_id, t_id, round_num)
        )
        game_ids.append(g_id)

    # Assign courts for each game
    cursor.execute("SELECT C_ID FROM TOURNAMENT WHERE T_ID = ?", (t_id,))
    c_id = cursor.fetchone()['C_ID']
    cursor.execute("SELECT COURT_NUM FROM INDIVIDUAL_COURTS WHERE C_ID = ? ORDER BY COURT_NUM", (c_id,))
    courts = [row['COURT_NUM'] for row in cursor.fetchall()]

    for i, g_id in enumerate(game_ids):
        court_num = courts[i % len(courts)]
        cursor.execute("INSERT INTO GAME_COURT (T_ID, G_ID, COURT_NUM, C_ID) VALUES (?, ?, ?, ?)",
                       (t_id, g_id, court_num, c_id))

    conn.commit()
    conn.close()
    return players

@app.route('/edit_games/<int:tournament_id>', methods=['GET'])
def edit_games(tournament_id):
    finish_prompt = request.args.get('complete') == '1'
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Tournament Info
    tournament = cursor.execute("""
        SELECT T.Type, T.Prize, T.Date, C.Address
        FROM TOURNAMENT T
        JOIN COURT_PARK C ON T.C_ID = C.C_ID
        WHERE T.T_ID = ?
    """, (tournament_id,)).fetchone()

    if not tournament:
        return "Tournament not found", 404

    is_doubles = tournament['Type'].endswith('D')

    # All players eligible for dropdowns
    all_players = cursor.execute("SELECT P_ID, Name FROM PLAYER WHERE T_ID = ?", (tournament_id,)).fetchall()
    pid_to_name = {p['P_ID']: p['Name'] for p in all_players}

    # Get all games
    games = cursor.execute("SELECT * FROM GAME WHERE T_ID = ? ORDER BY Round, G_ID", (tournament_id,)).fetchall()

    # Map current player assignments per game
    pg_rows = cursor.execute("SELECT P_ID, G_ID FROM PLAYER_GAME WHERE T_ID = ?", (tournament_id,)).fetchall()
    pg_map = {}
    used_pids = set()
    for row in pg_rows:
        pg_map.setdefault(row['G_ID'], []).append(row['P_ID'])
        used_pids.add(row['P_ID'])

    # Build game_players and result options
    game_players = {}
    result_options = {}

    for game in games:
        g_id = game["G_ID"]
        p_ids = pg_map.get(g_id, [])
        names = [pid_to_name.get(pid, "TBD") for pid in p_ids] 
        game_players[g_id] = names

        if is_doubles and len(names) >= 2:
            team1 = " & ".join(sorted(names[:2]))
            team2 = " & ".join(sorted(names[2:4])) if len(names) >= 4 else "BYE"
            result_options[g_id] = [team1, team2]
        else:
            if len(names) == 1:
                result_options[g_id] = [names[0]] 
            elif len(names) == 2:
                result_options[g_id] = names
            else:
                result_options[g_id] = []

    # Build available options for first round games
    available_players = [{'P_ID': p['P_ID'], 'Name': p['Name']} for p in all_players if p['P_ID'] not in used_pids]

    conn.close()

    return render_template(
        'edit_games.html',
        games=games,
        game_players=game_players,
        result_options=result_options,
        tournament_id=tournament_id,
        tournament_prize=tournament['Prize'],
        tournament_address=tournament['Address'],
        tournament_date=tournament['Date'],
        all_players=all_players,
        available_players=available_players,
        is_doubles=is_doubles,
        finish_prompt=finish_prompt
    )

@app.route('/update_game', methods=['POST'])
def update_game():
    t_id = request.form['tournament_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get tournament type
    cursor.execute("SELECT Type FROM TOURNAMENT WHERE T_ID = ?", (t_id,))
    t_type = cursor.fetchone()['Type']
    is_doubles = t_type.endswith('D')

    # Build name -> P_ID map
    players = cursor.execute("SELECT P_ID, Name FROM PLAYER WHERE T_ID = ?", (t_id,)).fetchall()
    name_to_pid = {p['Name']: p['P_ID'] for p in players}

    # Fetch all games
    games = cursor.execute("SELECT * FROM GAME WHERE T_ID = ?", (t_id,)).fetchall()

    for game in games:
        g_id = game['G_ID']
        round_num = game['Round']
        time = request.form.get(f"time_{g_id}")
        result_name = request.form.get(f"result_{g_id}", "").strip()

        # Update game time
        if time:
            cursor.execute("UPDATE GAME SET Time = ? WHERE G_ID = ?", (time, g_id))

        # Only allow editing player assignments in Round 1
        if round_num == 1:
            cursor.execute("DELETE FROM PLAYER_GAME WHERE G_ID = ? AND T_ID = ?", (g_id, t_id))
            slot_count = 4 if is_doubles else 2
            for i in range(slot_count):
                field = request.form.get(f"player_{g_id}_{i}", "").strip()
                if field.upper() == "BYE" or field == "":
                    continue  
                pid = name_to_pid.get(field)
                if pid:
                    cursor.execute("INSERT INTO PLAYER_GAME (P_ID, G_ID, T_ID) VALUES (?, ?, ?)", (pid, g_id, t_id))

        # Process winner
        if result_name:
            if is_doubles:
                team_names = [n.strip() for n in result_name.split('&')]
                winning_pids = [name_to_pid.get(n) for n in team_names if name_to_pid.get(n)]
                if len(winning_pids) == 2:
                    advance_doubles_winner(cursor, g_id, t_id, result_name)
            else:
                winner_pid = name_to_pid.get(result_name)
                if winner_pid:
                    cursor.execute("UPDATE GAME SET Result = ? WHERE G_ID = ?", (winner_pid, g_id))
                    advance_winner(cursor, g_id, t_id, result_name)

    # Final check for completion
    cursor.execute("SELECT COUNT(*) as incomplete FROM GAME WHERE T_ID = ? AND Result IS NULL", (t_id,))
    incomplete = cursor.fetchone()['incomplete']

    if incomplete == 0:
        conn.commit()   
        conn.close()
        return redirect(url_for('edit_games', tournament_id=t_id, complete=1))

    conn.commit() 
    conn.close()
    return redirect(url_for('edit_games', tournament_id=t_id, finish_prompt=1))


@app.route('/update_all_games', methods=['POST'])
def update_all_games():
    t_id = request.form['t_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT Type FROM TOURNAMENT WHERE T_ID = ?", (t_id,))
    t_type = cursor.fetchone()['Type']
    is_doubles = t_type.endswith('D')

    players = cursor.execute("SELECT P_ID, Name FROM PLAYER WHERE T_ID = ?", (t_id,)).fetchall()
    name_to_pid = {p['Name']: p['P_ID'] for p in players}

    games = cursor.execute("SELECT * FROM GAME WHERE T_ID = ?", (t_id,)).fetchall()

    for game in games:
        g_id = game['G_ID']
        round_num = game['Round']
        time = request.form.get(f'time_{g_id}')
        result_name = request.form.get(f'result_{g_id}', '').strip()

        if time:
            cursor.execute("UPDATE GAME SET Time = ? WHERE G_ID = ?", (time, g_id))

        # Only allow reassignment for Round 1
        if round_num == 1:
            cursor.execute("DELETE FROM PLAYER_GAME WHERE G_ID = ? AND T_ID = ?", (g_id, t_id))
            max_slots = 4 if is_doubles else 2
            for i in range(max_slots):
                player_field = request.form.get(f"player_{g_id}_{i}", "").strip()
                if player_field.upper() == "BYE" or player_field == "":
                    continue
                pid = name_to_pid.get(player_field)
                if pid:
                    cursor.execute("INSERT INTO PLAYER_GAME (P_ID, G_ID, T_ID) VALUES (?, ?, ?)", (pid, g_id, t_id))

        # Update result
        if result_name:
            if is_doubles:
                team_names = [n.strip() for n in result_name.split('&')]
                winning_pids = [name_to_pid.get(n) for n in team_names if name_to_pid.get(n)]
                if len(winning_pids) == 2:
                    advance_doubles_winner(cursor, g_id, t_id, result_name)
            else:
                winner_pid = name_to_pid.get(result_name)
                if winner_pid:
                    cursor.execute("UPDATE GAME SET Result = ? WHERE G_ID = ?", (winner_pid, g_id))
                    advance_winner(cursor, g_id, t_id, winner_pid)

    cursor.execute("SELECT COUNT(*) as incomplete FROM GAME WHERE T_ID = ? AND Result IS NULL", (t_id,))
    incomplete = cursor.fetchone()['incomplete']

    conn.commit()
    conn.close()

    if incomplete == 0:
        return redirect(url_for('edit_games', tournament_id=t_id, complete=1))

    return redirect(url_for('edit_games', tournament_id=t_id))


@app.route('/autocomplete_player', methods=['GET'])
def autocomplete_player():
    term = request.args.get('term', '')
    if len(term) < 2:
        return {'players': []}

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Name, Age, Gender
        FROM PLAYER
        WHERE Name LIKE ?
        LIMIT 10
    """, (f"{term}%",))
    matches = cursor.fetchall()
    conn.close()

    players = [{'name': row['Name'], 'age': row['Age'], 'gender': row['Gender']} for row in matches]
    return {'players': players}


@app.route('/past_tournaments')
def past_tournaments():
    date = request.args.get('date')
    prize_min = request.args.get('prize_min')
    t_type = request.args.get('type')
    court_id = request.args.get('court_id')

    # Get pagination params
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))

    query = "SELECT * FROM TOURNAMENT WHERE Status = 'completed'"
    params = []

    if date:
        query += " AND Date = ?"
        params.append(date)
    if prize_min:
        query += " AND Prize >= ?"
        params.append(prize_min)
    if t_type:
        query += " AND Type = ?"
        params.append(t_type)
    if court_id:
        query += " AND C_ID = ?"
        params.append(court_id)

    conn = get_db_connection()
    tournaments = conn.execute(query, tuple(params)).fetchall()
    conn.close()

    # Paginate the result
    paginated = paginate_items(tournaments, page, per_page)

    return render_template(
        'past_tournaments.html',
        tournaments=paginated['items'],
        page=paginated['page'],
        per_page=paginated['per_page'],
        total_pages=paginated['total_pages']
    )


def advance_winner(conn, g_id, t_id, result_name):
    # Check if tournament is doubles
    tournament = conn.execute("SELECT Type FROM TOURNAMENT WHERE T_ID = ?", (t_id,)).fetchone()
    is_doubles = tournament["Type"].endswith("D")

    # Get players in this game
    rows = conn.execute("""
        SELECT P.P_ID, P.Name
        FROM PLAYER_GAME PG
        JOIN PLAYER P ON PG.P_ID = P.P_ID
        WHERE PG.G_ID = ? AND PG.T_ID = ?
        ORDER BY P.P_ID
    """, (g_id, t_id)).fetchall()

    p_ids = [row["P_ID"] for row in rows]
    p_names = [row["Name"] for row in rows]
    pid_to_name = dict(zip(p_ids, p_names))

    winner_ids = []

    if is_doubles:
        # Build teams from first 2 and second 2
        team1_ids = p_ids[:2]
        team2_ids = p_ids[2:]

        team1_names = sorted(pid_to_name.get(pid, "TBD") for pid in team1_ids)
        team2_names = sorted(pid_to_name.get(pid, "TBD") for pid in team2_ids)

        team1_name = " & ".join(team1_names)
        team2_name = " & ".join(team2_names)

        if result_name == team1_name:
            winner_ids = team1_ids
        elif result_name == team2_name:
            winner_ids = team2_ids
    else:
        # Singles: result_name is one of the players
        for pid, name in pid_to_name.items():
            if name == result_name:
                winner_ids = [pid]
                break

    if not winner_ids:
        return  

    # Find the next game
    current_round = conn.execute("SELECT Round FROM GAME WHERE G_ID = ?", (g_id,)).fetchone()["Round"]
    next_round = current_round + 1

    current_games = conn.execute("SELECT G_ID FROM GAME WHERE T_ID = ? AND Round = ? ORDER BY G_ID", (t_id, current_round)).fetchall()
    next_games = conn.execute("SELECT G_ID FROM GAME WHERE T_ID = ? AND Round = ? ORDER BY G_ID", (t_id, next_round)).fetchall()

    if not next_games:
        return

    g_index = [row["G_ID"] for row in current_games].index(g_id)
    next_game_index = g_index // 2

    if next_game_index >= len(next_games):
        return

    next_g_id = next_games[next_game_index]["G_ID"]

    # Insert winners into next game
    for pid in winner_ids:
        exists = conn.execute("SELECT 1 FROM PLAYER_GAME WHERE P_ID = ? AND G_ID = ?", (pid, next_g_id)).fetchone()
        if not exists:
            conn.execute("INSERT INTO PLAYER_GAME (P_ID, G_ID, T_ID) VALUES (?, ?, ?)", (pid, next_g_id, t_id))

def advance_doubles_winner(conn, g_id, t_id, team_name_str):
    current_round = conn.execute("SELECT Round FROM GAME WHERE G_ID = ?", (g_id,)).fetchone()['Round']
    next_round = current_round + 1

    current_games = conn.execute(
        "SELECT G_ID FROM GAME WHERE T_ID = ? AND Round = ? ORDER BY G_ID", (t_id, current_round)).fetchall()
    next_games = conn.execute(
        "SELECT G_ID FROM GAME WHERE T_ID = ? AND Round = ? ORDER BY G_ID", (t_id, next_round)).fetchall()

    current_game_ids = [g['G_ID'] for g in current_games]
    next_game_index = current_game_ids.index(g_id) // 2

    # Get all players in current game
    p_ids = conn.execute(
        "SELECT PLAYER.P_ID, PLAYER.Name FROM PLAYER_GAME JOIN PLAYER ON PLAYER.P_ID = PLAYER_GAME.P_ID WHERE G_ID = ?", 
        (g_id,)).fetchall()
    name_to_pid = {player['Name']: player['P_ID'] for player in p_ids}

    winning_names = [name.strip() for name in team_name_str.split('&')]
    winning_ids = [name_to_pid[name] for name in winning_names if name in name_to_pid]

    # Update GAME.Result with any one winner ID (to mark game complete)
    if winning_ids:
        conn.execute("UPDATE GAME SET Result = ? WHERE G_ID = ?", (winning_ids[0], g_id))

    if next_games:
        next_g_id = next_games[next_game_index]['G_ID']
        # Insert both winning team members into the next round
        for winner_pid in winning_ids:
            exists = conn.execute("SELECT 1 FROM PLAYER_GAME WHERE P_ID = ? AND G_ID = ?", (winner_pid, next_g_id)).fetchone()
            if not exists:
                conn.execute("INSERT INTO PLAYER_GAME (P_ID, G_ID, T_ID) VALUES (?, ?, ?)", (winner_pid, next_g_id, t_id))

def check_and_mark_completed(conn, t_id):
    max_round = conn.execute("SELECT MAX(Round) as max_r FROM GAME WHERE T_ID = ?", (t_id,)).fetchone()['max_r']
    final_results = conn.execute("SELECT Result FROM GAME WHERE T_ID = ? AND Round = ?", (t_id, max_round)).fetchall()
    if all(g['Result'] for g in final_results):
        conn.execute("UPDATE TOURNAMENT SET Status = 'completed' WHERE T_ID = ?", (t_id,))


@app.route('/finalize_tournament', methods=['POST'])
def finalize_tournament():
    t_id = request.form.get('t_id')
    action = request.form.get('confirm')  

    if not t_id or not action:
        return "Bad request", 400

    if action == "yes":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE TOURNAMENT SET Status = 'completed' WHERE T_ID = ?", (t_id,))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))  

    return redirect(url_for('edit_games', tournament_id=t_id))


@app.route('/check_player', methods=['POST'])
def check_player():
    name = request.json.get('name')
    age = request.json.get('age')
    gender = request.json.get('gender')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT PLAYER.P_ID, PLAYER.T_ID, TOURNAMENT.Status
        FROM PLAYER
        JOIN TOURNAMENT ON PLAYER.T_ID = TOURNAMENT.T_ID
        WHERE Name = ? AND Age = ? AND Gender = ? AND TOURNAMENT.Status = 'active'
    """, (name, age, gender))
    row = cursor.fetchone()
    conn.close()

    return {'in_active_tournament': bool(row)}


@app.route('/check_duplicate_player', methods=['POST'])
def check_duplicate_player():
    data = request.json
    name = data.get('name')
    age = data.get('age')
    gender = data.get('gender')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM PLAYER WHERE Name = ? AND Age = ? AND Gender = ?", (name, age, gender))
    exists = cursor.fetchone() is not None
    conn.close()

    return {'exists': exists}

@app.route('/courts')
def manage_courts():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))

    conn = get_db_connection()
    cursor = conn.cursor()

    court_parks = cursor.execute('SELECT * FROM COURT_PARK').fetchall()

    # Add num_courts to each
    courts = []
    for park in court_parks:
        num = cursor.execute(
            "SELECT COUNT(*) FROM INDIVIDUAL_COURTS WHERE C_ID = ?", (park['C_ID'],)
        ).fetchone()[0]

        park_dict = dict(park)
        park_dict['Num_Courts'] = num
        courts.append(park_dict)

    conn.close()

    paginated = paginate_items(courts, page, per_page)

    return render_template('courts.html',
                           courts=paginated['items'],
                           page=paginated['page'],
                           total_pages=paginated['total_pages'],
                           per_page=paginated['per_page'])


@app.route('/add_court', methods=['POST'])
def add_court():
    name = request.form['name']
    address = request.form['address']
    open_time = request.form['open_time']
    latitude = request.form['latitude']
    longitude = request.form['longitude']
    num_courts = int(request.form['num_courts'])

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO COURT_PARK (Name, Address, Open_Time, Latitude, Longitude)
        VALUES (?, ?, ?, ?, ?)""",
        (name, address, open_time, latitude, longitude))

    c_id = cursor.lastrowid

    for num in range(1, num_courts + 1):
        cursor.execute("INSERT INTO INDIVIDUAL_COURTS (COURT_NUM, C_ID) VALUES (?, ?)", (num, c_id))

    conn.commit()
    conn.close()

    return redirect(url_for('manage_courts'))

@app.route('/update_court', methods=['POST'])
def update_court():
    c_id = request.form['c_id']
    name = request.form['name']
    address = request.form['address']
    open_time = request.form['open_time']
    latitude = request.form['latitude']
    longitude = request.form['longitude']

    conn = get_db_connection()
    conn.execute("""
        UPDATE COURT_PARK
        SET Name = ?, Address = ?, Open_Time = ?, Latitude = ?, Longitude = ?
        WHERE C_ID = ?""",
        (name, address, open_time, latitude, longitude, c_id))
    conn.commit()
    conn.close()

    return redirect(url_for('manage_courts'))

@app.route('/delete_court', methods=['POST'])
def delete_court():
    c_id = request.form['c_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM INDIVIDUAL_COURTS WHERE C_ID = ?", (c_id,))
    cursor.execute("DELETE FROM COURT_PARK WHERE C_ID = ?", (c_id,))

    conn.commit()
    conn.close()

    return redirect(url_for('manage_courts'))

@app.route('/search_courts', methods=['GET'])
def search_courts():
    search_term = request.args.get('q', '')
    open_time = request.args.get('open_time', '')

    conn = get_db_connection()
    query = "SELECT * FROM COURT_PARK WHERE 1=1"
    params = []

    if search_term:
        query += " AND (Name LIKE ? OR Address LIKE ?)"
        params.extend([f"%{search_term}%", f"%{search_term}%"])

    if open_time:
        query += " AND Open_Time >= ?"
        params.append(open_time)

    courts = conn.execute(query, params).fetchall()
    conn.close()

    return render_template('courts.html', courts=courts)


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)


from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, join_room, emit
import sqlite3
import json
import random
import os

app = Flask(__name__, static_folder="static")
# app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

db_file = "bingo.sqlite"
def get_db_connection():
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/game")
def serve_game():
    return send_from_directory("static", "game.html")

@app.route("/")
def serve_landing_page():
    return send_from_directory("static", "landing.html")

@app.route("/random_meme")
def random_meme():
    memes_folder = os.path.join(app.static_folder, "memes")
    memes = os.listdir(memes_folder)
    if not memes:
        return jsonify({"error": "No memes found"}), 404
    meme = random.choice(memes)

    return jsonify({"filename": meme})

def init_db():
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                options TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board TEXT NOT NULL,
                name TEXT NOT NULL,
                room TEXT NOT NULL,
                UNIQUE(name, room)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ticked_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room TEXT NOT NULL,
                option TEXT NOT NULL,
                UNIQUE(room, option)
            )
        ''')
        conn.commit()

@app.route("/create_room", methods=["POST"])
def create_room():
    data = request.json
    room_name = data.get("room_name")
    options = data.get("options")  # List of options
    if not room_name or not options:
        return jsonify({"error": "Room name and options are required"}), 400
    
    options_str = ",".join(options)
    try:
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO rooms (name, options) VALUES (?, ?)", (room_name, options_str))
            conn.commit()
        return jsonify({"success": "Room created"})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Room already exists"}), 400

def enter_player_into_room(room_name, player_name):
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO players (board, name, room) VALUES (?, ?, ?)", ('', player_name, room_name))
        
        # Retrieve room options and create a randomized board for the player
        cursor.execute("SELECT options FROM rooms WHERE name = ?", (room_name,))
        row = cursor.fetchone()
        if row:
            options = row[0].split(",")
            random.shuffle(options)
            board = json.dumps(options)
            cursor.execute("UPDATE players SET board = ? WHERE name = ? AND room = ?", (board, player_name, room_name))
        
        conn.commit()

@app.route("/join_room", methods=["POST"])
def join_room_api():
    data = request.json
    room_name = data.get("room_name")
    player_name = data.get("player_name")
    if not room_name or not player_name:
        return jsonify({"error": "Room name and player name are required"}), 400
    
    enter_player_into_room(room_name, player_name)
    return jsonify({"success": "Joined room"})

@app.route("/game_state/<room>", methods=["GET"])
def get_game_state(room):
    player = request.args.get("player")

    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM players WHERE name = ? AND room = ?", (player, room))
        if cursor.fetchone() is None:
            enter_player_into_room(room, player)

    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT options FROM rooms WHERE name = ?", (room,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Room not found"}), 404
        
        all_options = row[0].split(",")
        
        # Retrieve the player's specific board
        cursor.execute("SELECT board FROM players WHERE name = ? AND room = ?", (player, room))
        player_row = cursor.fetchone()
        if player_row:
            player_board = json.loads(player_row[0])
        else:
            player_board = all_options
        
        cursor.execute("SELECT option FROM ticked_options WHERE room = ?", (room,))
        ticked = [r[0] for r in cursor.fetchall()]
    return jsonify({"options": player_board, "ticked": ticked})

@socketio.on("join")
def handle_join(data):
    room = data.get("room")
    player = data.get("player")
    join_room(room)
    emit("player_joined", {"player": player}, room=room)

@socketio.on("tick_option")
def handle_tick(data):
    room = data.get("room")
    option = data.get("option")
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO ticked_options (room, option) VALUES (?, ?)", (room, option))
        conn.commit()
    emit("option_ticked", {"option": option}, room=room)

@socketio.on("untick_option")
def handle_tick(data):
    room = data.get("room")
    option = data.get("option")
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ticked_options WHERE room = ? AND option = ?", (room, option))
        conn.commit()
    emit("option_unticked", {"option": option}, room=room)

@socketio.on("join")
def handle_join(data):
    room = data["room"]
    player = data["player"]
    join_room(room)

    # conn = get_db_connection()
    # cur = conn.cursor()

    # # Retrieve player's board
    # cur.execute("SELECT board FROM players WHERE room = ? AND player = ?", (room, player))
    # row = cur.fetchone()
    # if row and row["board"]:
    #     board = json.loads(row["board"])
    # else:
    #     return

    # # Retrieve ticked options
    # cur.execute("SELECT option FROM ticks WHERE room = ?", (room,))
    # ticked = [r["option"] for r in cur.fetchall()]
    
    # conn.close()

    # Broadcast full game state to all players in the room
    # emit("sync_game", {"room": room, "board": board, "ticked": ticked}, room=room)

@socketio.on("tick_option")
def handle_tick(data):
    room = data["room"]
    option = data["option"]

    conn = get_db_connection()
    cur = conn.cursor()
    
    # Save ticked option in the database
    cur.execute("INSERT INTO ticked_options (room, option) VALUES (?, ?) ON CONFLICT DO NOTHING", (room, option))
    conn.commit()
    conn.close()

    # Broadcast ticked option update
    emit("option_ticked", {"room": room, "option": option}, room=room)

if __name__ == "__main__":
    init_db()
    socketio.run(app, debug=True, port=8000)

from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, join_room, emit
import sqlite3
import json
import random

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

@app.route("/join_room", methods=["POST"])
def join_room_api():
    data = request.json
    room_name = data.get("room_name")
    player_name = data.get("player_name")
    if not room_name or not player_name:
        return jsonify({"error": "Room name and player name are required"}), 400
    
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO players (name, room) VALUES (?, ?)", (player_name, room_name))
        conn.commit()
    return jsonify({"success": "Joined room"})

@app.route("/game_state/<room>", methods=["GET"])
def get_game_state(room):
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT options FROM rooms WHERE name = ?", (room,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Room not found"}), 404
        
        all_options = row[0].split(",")
        cursor.execute("SELECT option FROM ticked_options WHERE room = ?", (room,))
        ticked = [r[0] for r in cursor.fetchall()]
    return jsonify({"options": all_options, "ticked": ticked})

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

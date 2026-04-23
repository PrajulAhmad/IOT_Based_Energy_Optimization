"""
IoT Smart Building Energy Optimizer v4
Flask + SocketIO + SQLite + Auth + ML + Weather + MQTT + Anomaly Detection
"""
import csv, io, sqlite3, os, hashlib, random, json, threading, logging
from datetime import datetime, timedelta
from functools import wraps
import numpy as np
from flask import Flask, request, jsonify, render_template, session, redirect, Response
from flask_cors import CORS
from flask_socketio import SocketIO
import requests as http_req
import paho.mqtt.client as mqtt
from sklearn.ensemble import IsolationForest

app = Flask(__name__)
app.secret_key = "iot-energy-secret-key-2026-v4"
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

logging.basicConfig(filename='alerts.log', level=logging.WARNING, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('werkzeug').setLevel(logging.WARNING)

CONFIG = {
    "power_threshold": 400,
    "temp_threshold": 26.0,
    "overrides": {},
    "weather_api_key": "",
    "weather_city": "London",
    "energy_rate": 0.12,
}

global_weather_temp = 25.0
DB_PATH = "energy.db"
ROOMS = [
    {"id": 1, "name": "Living Room"},
    {"id": 2, "name": "Server Room"},
    {"id": 3, "name": "Office 1"},
    {"id": 4, "name": "Kitchen"},
]

# MQTT Config
MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883
MQTT_TOPIC_PREFIX = "prajul_smart_building/sensors/"

# Anomaly Detection Models Cache
# We will train an IsolationForest per room on the recent power data.
anomaly_models = {}

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'viewer',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER DEFAULT 1,
            timestamp TEXT,
            temp REAL, lux REAL, occupancy INTEGER, power REAL,
            light_status INTEGER, hvac_status INTEGER, alert INTEGER,
            is_anomaly INTEGER DEFAULT 0,
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        );
    """)
    for r in ROOMS:
        conn.execute("INSERT OR IGNORE INTO rooms (id, name) VALUES (?,?)", (r["id"], r["name"]))
    ah = hashlib.sha256("admin123".encode()).hexdigest()
    conn.execute("INSERT OR IGNORE INTO users (username,password_hash,role,created_at) VALUES (?,?,'admin',?)",
                 ("admin", ah, datetime.now().isoformat()))
    vh = hashlib.sha256("viewer123".encode()).hexdigest()
    conn.execute("INSERT OR IGNORE INTO users (username,password_hash,role,created_at) VALUES (?,?,'viewer',?)",
                 ("viewer", vh, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# --- Auth Decorators ---
def login_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect("/login")
        return f(*a, **kw)
    return dec

def admin_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if "user_id" not in session:
            return jsonify({"error": "unauthorized"}), 401
        if session.get("role") != "admin":
            return jsonify({"error": "admin required"}), 403
        return f(*a, **kw)
    return dec

# --- Rule & ML Engine ---
def train_anomaly_model(room_id):
    conn = get_db()
    rows = conn.execute("SELECT power FROM readings WHERE room_id=? ORDER BY id DESC LIMIT 200", (room_id,)).fetchall()
    conn.close()
    if len(rows) > 10:
        data = np.array([r["power"] for r in rows]).reshape(-1, 1)
        model = IsolationForest(contamination=0.05, random_state=42)
        model.fit(data)
        anomaly_models[room_id] = model

def detect_anomaly(room_id, power):
    if room_id not in anomaly_models:
        train_anomaly_model(room_id)
    model = anomaly_models.get(room_id)
    if model:
        prediction = model.predict([[power]])
        # IsolationForest returns -1 for anomaly, 1 for normal
        return 1 if prediction[0] == -1 else 0
    return 0

def apply_rules(room_id, temp, lux, occupancy, power):
    thr = CONFIG["power_threshold"]
    ov = CONFIG["overrides"].get(str(room_id), {})
    ov_light = ov.get("light")
    ov_hvac = ov.get("hvac")
    
    light = 1 if ov_light else (0 if (occupancy == 0 or lux > 700) else 1)
    if ov_light is False: light = 0
    
    hvac = 1 if ov_hvac else (1 if (occupancy == 1 and temp > CONFIG["temp_threshold"]) else 0)
    if ov_hvac is False: hvac = 0
    
    alert = 1 if power > thr else 0
    
    is_anomaly = detect_anomaly(room_id, power)
    if is_anomaly:
        alert = 1 # Force alert if anomalous
        
    return light, hvac, alert, is_anomaly

# --- MQTT Integration ---
def process_mqtt_message(payload_str):
    try:
        d = json.loads(payload_str)
        rid = int(d.get("room_id", 1))
        temp = float(d.get("temp", 0))
        lux = float(d.get("lux", 0))
        occ = int(d.get("occupancy", 0))
        pwr = float(d.get("power", 0))
        
        light, hvac, alert, is_anomaly = apply_rules(rid, temp, lux, occ, pwr)
        ts = datetime.now().isoformat()
        
        if alert and not is_anomaly:
            logging.warning(f"High Power Alert in Room {rid}: {pwr}W")
        if is_anomaly:
            logging.error(f"AI Anomaly Detected in Room {rid}: {pwr}W")
        
        conn = get_db()
        conn.execute("INSERT INTO readings (room_id,timestamp,temp,lux,occupancy,power,light_status,hvac_status,alert,is_anomaly) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (rid, ts, temp, lux, occ, pwr, light, hvac, alert, is_anomaly))
        conn.commit()
        conn.close()
        
        reading = {"room_id": rid, "timestamp": ts, "temp": temp, "lux": lux,
                   "occupancy": occ, "power": pwr, "light_status": light,
                   "hvac_status": hvac, "alert": alert, "is_anomaly": is_anomaly}
        socketio.emit("new_reading", reading)
        
        # Periodically retrain anomaly model
        if random.random() < 0.05:
            train_anomaly_model(rid)
            
    except Exception as e:
        print("MQTT Processing Error:", e)

def on_mqtt_connect(client, userdata, flags, reason_code, properties=None):
    print("MQTT Connected. Subscribing to", f"{MQTT_TOPIC_PREFIX}#")
    client.subscribe(f"{MQTT_TOPIC_PREFIX}#")

def on_mqtt_message(client, userdata, msg):
    with app.app_context():
        process_mqtt_message(msg.payload.decode('utf-8'))

def start_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_mqtt_connect
    client.on_message = on_mqtt_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

# --- HTTP Endpoints ---
@app.route("/login")
def login_page():
    if "user_id" in session: return redirect("/")
    return render_template("login.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    d = request.get_json(force=True)
    h = hashlib.sha256(d.get("password", "").encode()).hexdigest()
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE username=? AND password_hash=?", (d.get("username", ""), h)).fetchone()
    conn.close()
    if not u: return jsonify({"error": "Invalid credentials"}), 401
    session["user_id"] = u["id"]
    session["username"] = u["username"]
    session["role"] = u["role"]
    return jsonify({"ok": True, "username": u["username"], "role": u["role"]})

@app.route("/api/register", methods=["POST"])
def api_register():
    d = request.get_json(force=True)
    un = d.get("username", "").strip()
    pw = d.get("password", "")
    role = d.get("role", "viewer")
    if not un or not pw: return jsonify({"error": "Username and password required"}), 400
    if role not in ("admin", "viewer"): role = "viewer"
    h = hashlib.sha256(pw.encode()).hexdigest()
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)", (un, h, role, datetime.now().isoformat()))
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username exists"}), 409
    finally:
        conn.close()
    return jsonify({"ok": True})

@app.route("/api/logout")
def api_logout():
    session.clear()
    return redirect("/login")

@app.route("/api/me")
@login_required
def api_me():
    return jsonify({"username": session["username"], "role": session["role"]})

@app.route("/")
@login_required
def index():
    return render_template("index.html")

@app.route("/api/rooms")
@login_required
def get_rooms():
    conn = get_db()
    rows = conn.execute("SELECT * FROM rooms ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# Legacy HTTP fallback for data reception
@app.route("/api/data", methods=["POST"])
def receive_data():
    process_mqtt_message(request.data.decode('utf-8'))
    return jsonify({"ok": True})

@app.route("/api/latest")
@login_required
def get_latest():
    rid = request.args.get("room_id", 1, type=int)
    conn = get_db()
    rows = conn.execute("SELECT * FROM readings WHERE room_id=? ORDER BY id DESC LIMIT 30", (rid,)).fetchall()
    conn.close()
    if not rows: return jsonify({"rows": [], "latest": None})
    readings = [dict(r) for r in rows]
    latest = readings[0]
    readings.reverse()
    return jsonify({"rows": readings, "latest": latest, "threshold": CONFIG["power_threshold"],
                    "temp_threshold": CONFIG["temp_threshold"],
                    "overrides": CONFIG["overrides"].get(str(rid), {}), "energy_rate": CONFIG["energy_rate"]})

@app.route("/api/heatmap")
@login_required
def get_heatmap():
    conn = get_db()
    res = {}
    for r in ROOMS:
        row = conn.execute("""
            SELECT COUNT(*) as total, SUM(occupancy) as occ
            FROM readings WHERE room_id=?
        """, (r["id"],)).fetchone()
        pct = (row["occ"] / row["total"] * 100) if row["total"] > 0 else 0
        res[r["id"]] = {"pct": round(pct, 1), "total": row["total"]}
    conn.close()
    return jsonify(res)

@app.route("/api/predict")
@login_required
def predict():
    rid = request.args.get("room_id", 1, type=int)
    conn = get_db()
    rows = conn.execute("SELECT power FROM readings WHERE room_id=? ORDER BY id DESC LIMIT 50", (rid,)).fetchall()
    conn.close()
    if len(rows) < 5: return jsonify({"error": "need more data", "predicted": [], "trend": "unknown"})
    y = np.array([r["power"] for r in reversed(rows)], dtype=float)
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    future_x = np.arange(len(y), len(y) + 10)
    predicted = [round(float(slope * fx + intercept), 1) for fx in future_x]
    trend = "rising" if slope > 1 else ("falling" if slope < -1 else "stable")
    return jsonify({"predicted": predicted, "trend": trend, "slope": round(float(slope), 3), "current_avg": round(float(np.mean(y)), 1)})

@app.route("/api/all_rooms_status")
@login_required
def all_rooms_status():
    conn = get_db()
    res = []
    for r in ROOMS:
        row = conn.execute("SELECT * FROM readings WHERE room_id=? ORDER BY id DESC LIMIT 1", (r["id"],)).fetchone()
        if row:
            res.append({"room_id": r["id"], "name": r["name"], **dict(row)})
        else:
            res.append({"room_id": r["id"], "name": r["name"], "temp": 0, "lux": 0, "power": 0, "occupancy": 0, "light_status": 0, "hvac_status": 0, "alert": 0, "is_anomaly": 0})
    conn.close()
    return jsonify(res)

@app.route("/api/weather")
@login_required
def get_weather():
    global global_weather_temp
    global_weather_temp += random.uniform(-0.1, 0.1)
    global_weather_temp = max(10.0, min(40.0, global_weather_temp))
    return jsonify({"source": "simulated", "temp": round(global_weather_temp, 1), "humidity": random.randint(30, 80),
                    "desc": random.choice(["partly cloudy", "clear sky", "light rain"]), "city": "London",
                    "suggestion": "Open windows" if global_weather_temp < 22 else "Use HVAC"})

@app.route("/api/threshold_temp", methods=["POST"])
@admin_required
def set_temp_threshold():
    d = request.get_json(force=True)
    CONFIG["temp_threshold"] = float(d.get("temp_threshold", 26.0))
    return jsonify({"ok": True})

@app.route("/api/wastage")
@login_required
def get_wastage():
    conn = get_db()
    res = {}
    for r in ROOMS:
        row = conn.execute("SELECT SUM(power) as wasted FROM readings WHERE room_id=? AND occupancy=0", (r["id"],)).fetchone()
        res[r["id"]] = round((row["wasted"] or 0) / 1000.0, 2)
    conn.close()
    return jsonify(res)

@app.route("/api/override", methods=["POST"])
@admin_required
def set_override():
    d = request.get_json(force=True)
    rid = str(d.get("room_id", 1))
    if rid not in CONFIG["overrides"]: CONFIG["overrides"][rid] = {}
    if d.get("device") in ("light", "hvac"): CONFIG["overrides"][rid][d.get("device")] = d.get("state")
    return jsonify({"ok": True})

if __name__ == "__main__":
    init_db()
    print("DB initialized. Starting MQTT listener...")
    start_mqtt()
    print("Starting Flask-SocketIO server on http://localhost:5000")
    socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True, use_reloader=False)

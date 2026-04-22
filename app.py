"""
IoT Smart Building Energy Optimizer v3
Flask + SocketIO + SQLite + Auth + Multi-Room + ML + Weather
"""
import csv, io, sqlite3, os, hashlib, random
from datetime import datetime, timedelta
from functools import wraps
import numpy as np
from flask import Flask, request, jsonify, render_template, session, redirect, Response
from flask_cors import CORS
from flask_socketio import SocketIO
import requests as http_req

app = Flask(__name__)
app.secret_key = "iot-energy-secret-key-2026"
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

CONFIG = {
    "power_threshold": 400,
    "overrides": {},
    "weather_api_key": "",
    "weather_city": "London",
    "energy_rate": 0.12,
}
DB_PATH = "energy.db"
ROOMS = [
    {"id": 1, "name": "Living Room"},
    {"id": 2, "name": "Server Room"},
    {"id": 3, "name": "Office 1"},
    {"id": 4, "name": "Kitchen"},
]

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

# --- Rule Engine ---
def apply_rules(room_id, temp, lux, occupancy, power):
    thr = CONFIG["power_threshold"]
    ov = CONFIG["overrides"].get(str(room_id), {})
    ov_light = ov.get("light")
    ov_hvac = ov.get("hvac")
    if ov_light is not None:
        light = 1 if ov_light else 0
    else:
        light = 0 if (occupancy == 0 or lux > 700) else 1
    if ov_hvac is not None:
        hvac = 1 if ov_hvac else 0
    else:
        hvac = 1 if (occupancy == 1 and temp > 26) else 0
    alert = 1 if power > thr else 0
    return light, hvac, alert

# --- Auth Routes ---
@app.route("/login")
def login_page():
    if "user_id" in session:
        return redirect("/")
    return render_template("login.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    d = request.get_json(force=True)
    h = hashlib.sha256(d.get("password", "").encode()).hexdigest()
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE username=? AND password_hash=?",
                     (d.get("username", ""), h)).fetchone()
    conn.close()
    if not u:
        return jsonify({"error": "Invalid credentials"}), 401
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
    if not un or not pw:
        return jsonify({"error": "Username and password required"}), 400
    if role not in ("admin", "viewer"):
        role = "viewer"
    h = hashlib.sha256(pw.encode()).hexdigest()
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
                     (un, h, role, datetime.now().isoformat()))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Username exists"}), 409
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

# --- Pages ---
@app.route("/")
@login_required
def index():
    return render_template("index.html")

# --- API ---
@app.route("/api/rooms")
@login_required
def get_rooms():
    conn = get_db()
    rows = conn.execute("SELECT * FROM rooms ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/data", methods=["POST"])
def receive_data():
    d = request.get_json(force=True)
    rid = int(d.get("room_id", 1))
    temp = float(d.get("temp", 0))
    lux = float(d.get("lux", 0))
    occ = int(d.get("occupancy", 0))
    pwr = float(d.get("power", 0))
    light, hvac, alert = apply_rules(rid, temp, lux, occ, pwr)
    ts = datetime.now().isoformat()
    conn = get_db()
    conn.execute("INSERT INTO readings (room_id,timestamp,temp,lux,occupancy,power,light_status,hvac_status,alert) VALUES (?,?,?,?,?,?,?,?,?)",
                 (rid, ts, temp, lux, occ, pwr, light, hvac, alert))
    conn.commit()
    conn.close()
    reading = {"room_id": rid, "timestamp": ts, "temp": temp, "lux": lux,
               "occupancy": occ, "power": pwr, "light_status": light,
               "hvac_status": hvac, "alert": alert}
    socketio.emit("new_reading", reading)
    return jsonify({"light_status": light, "hvac_status": hvac, "alert": alert})

@app.route("/api/latest")
@login_required
def get_latest():
    rid = request.args.get("room_id", 1, type=int)
    conn = get_db()
    rows = conn.execute("SELECT * FROM readings WHERE room_id=? ORDER BY id DESC LIMIT 30", (rid,)).fetchall()
    conn.close()
    if not rows:
        return jsonify({"rows": [], "latest": None})
    readings = [dict(r) for r in rows]
    latest = readings[0]
    readings.reverse()
    ov = CONFIG["overrides"].get(str(rid), {})
    return jsonify({"rows": readings, "latest": latest,
                    "threshold": CONFIG["power_threshold"],
                    "overrides": ov, "energy_rate": CONFIG["energy_rate"]})

@app.route("/api/stats")
@login_required
def get_stats():
    rid = request.args.get("room_id", 1, type=int)
    conn = get_db()
    r = conn.execute("""SELECT COUNT(*) AS total, ROUND(AVG(temp),2) AS avg_temp,
        ROUND(MIN(temp),2) AS min_temp, ROUND(MAX(temp),2) AS max_temp,
        ROUND(AVG(power),2) AS avg_power, ROUND(MIN(power),2) AS min_power,
        ROUND(MAX(power),2) AS max_power, SUM(alert) AS total_alerts,
        SUM(light_status) AS light_on, SUM(hvac_status) AS hvac_on
        FROM readings WHERE room_id=?""", (rid,)).fetchone()
    conn.close()
    return jsonify(dict(r))

@app.route("/api/export/csv")
@login_required
def export_csv():
    rid = request.args.get("room_id", 1, type=int)
    conn = get_db()
    rows = conn.execute("SELECT * FROM readings WHERE room_id=? ORDER BY id", (rid,)).fetchall()
    conn.close()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id","room_id","timestamp","temp","lux","occupancy","power","light","hvac","alert"])
    for r in rows:
        w.writerow(list(r))
    out.seek(0)
    fn = f"energy_room{rid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={fn}"})

@app.route("/api/override", methods=["POST"])
@admin_required
def set_override():
    d = request.get_json(force=True)
    dev = d.get("device")
    state = d.get("state")
    rid = str(d.get("room_id", 1))
    if rid not in CONFIG["overrides"]:
        CONFIG["overrides"][rid] = {}
    if dev in ("light", "hvac"):
        CONFIG["overrides"][rid][dev] = state
    return jsonify({"ok": True, "overrides": CONFIG["overrides"].get(rid, {})})

@app.route("/api/threshold", methods=["POST"])
@admin_required
def set_threshold():
    d = request.get_json(force=True)
    try:
        CONFIG["power_threshold"] = float(d["threshold"])
    except (KeyError, ValueError):
        return jsonify({"error": "invalid"}), 400
    return jsonify({"ok": True, "threshold": CONFIG["power_threshold"]})

@app.route("/api/energy_rate", methods=["POST"])
@admin_required
def set_energy_rate():
    d = request.get_json(force=True)
    try:
        CONFIG["energy_rate"] = float(d["rate"])
    except (KeyError, ValueError):
        return jsonify({"error": "invalid"}), 400
    return jsonify({"ok": True, "rate": CONFIG["energy_rate"]})

@app.route("/api/weather")
@login_required
def get_weather():
    key = CONFIG.get("weather_api_key", "")
    city = CONFIG.get("weather_city", "London")
    if key:
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={key}&units=metric"
            r = http_req.get(url, timeout=5).json()
            t = r["main"]["temp"]
            return jsonify({"source": "live", "temp": t, "humidity": r["main"]["humidity"],
                            "desc": r["weather"][0]["description"], "city": city,
                            "suggestion": "Open windows" if t < 22 else "Use HVAC"})
        except Exception:
            pass
    t = round(random.uniform(15, 35), 1)
    return jsonify({"source": "simulated", "temp": t, "humidity": random.randint(30, 80),
                    "desc": random.choice(["partly cloudy", "clear sky", "light rain", "sunny"]),
                    "city": city,
                    "suggestion": "Open windows for fresh air" if t < 22 else "Use HVAC for cooling"})

@app.route("/api/predict")
@login_required
def predict():
    rid = request.args.get("room_id", 1, type=int)
    conn = get_db()
    rows = conn.execute("SELECT power FROM readings WHERE room_id=? ORDER BY id DESC LIMIT 50",
                        (rid,)).fetchall()
    conn.close()
    if len(rows) < 5:
        return jsonify({"error": "need more data", "predicted": [], "trend": "unknown"})
    powers = [r["power"] for r in reversed(rows)]
    x = np.arange(len(powers), dtype=float)
    y = np.array(powers, dtype=float)
    coeffs = np.polyfit(x, y, 1)
    slope, intercept = coeffs
    future_x = np.arange(len(powers), len(powers) + 10)
    predicted = [round(float(slope * fx + intercept), 1) for fx in future_x]
    trend = "rising" if slope > 1 else ("falling" if slope < -1 else "stable")
    avg = round(float(np.mean(y)), 1)
    return jsonify({"predicted": predicted, "trend": trend, "slope": round(float(slope), 3),
                    "current_avg": avg})

@app.route("/api/reports/weekly")
@login_required
def weekly_report():
    rid = request.args.get("room_id", 1, type=int)
    now = datetime.now()
    week_ago = (now - timedelta(days=7)).isoformat()
    two_weeks = (now - timedelta(days=14)).isoformat()
    conn = get_db()
    this_week = conn.execute("""SELECT COUNT(*) AS cnt, ROUND(AVG(power),2) AS avg_pwr,
        ROUND(SUM(power),2) AS total_pwr, SUM(alert) AS alerts
        FROM readings WHERE room_id=? AND timestamp>=?""", (rid, week_ago)).fetchone()
    last_week = conn.execute("""SELECT COUNT(*) AS cnt, ROUND(AVG(power),2) AS avg_pwr,
        ROUND(SUM(power),2) AS total_pwr, SUM(alert) AS alerts
        FROM readings WHERE room_id=? AND timestamp>=? AND timestamp<?""",
        (rid, two_weeks, week_ago)).fetchone()
    conn.close()
    tw = dict(this_week)
    lw = dict(last_week)
    change = 0
    if lw["avg_pwr"] and tw["avg_pwr"]:
        change = round(((tw["avg_pwr"] - lw["avg_pwr"]) / lw["avg_pwr"]) * 100, 1)
    return jsonify({"this_week": tw, "last_week": lw, "pct_change": change})

@app.route("/api/all_rooms_status")
@login_required
def all_rooms_status():
    conn = get_db()
    result = []
    for room in ROOMS:
        row = conn.execute("SELECT * FROM readings WHERE room_id=? ORDER BY id DESC LIMIT 1",
                           (room["id"],)).fetchone()
        if row:
            result.append({"room_id": room["id"], "name": room["name"], **dict(row)})
        else:
            result.append({"room_id": room["id"], "name": room["name"],
                           "temp": 0, "lux": 0, "power": 0, "occupancy": 0,
                           "light_status": 0, "hvac_status": 0, "alert": 0})
    conn.close()
    return jsonify(result)

# --- SocketIO Events ---
@socketio.on("connect")
def handle_connect():
    print(f"Client connected: {request.sid}")

@socketio.on("disconnect")
def handle_disconnect():
    print(f"Client disconnected: {request.sid}")

if __name__ == "__main__":
    init_db()
    print("DB initialized. Rooms:", [r["name"] for r in ROOMS])
    print("Default users: admin/admin123 (admin), viewer/viewer123 (viewer)")
    print("Starting on http://localhost:5000")
    socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True)

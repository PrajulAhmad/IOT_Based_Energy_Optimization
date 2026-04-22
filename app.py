"""
IoT Smart Building Energy Optimizer — Flask Backend (v2)
Features:
  - SQLite DB (single table, inline setup)
  - Rule engine with configurable threshold
  - Manual device override (light / HVAC)
  - REST API: POST /api/data, GET /api/latest, GET /api/stats,
              GET /api/export/csv, POST /api/override, POST /api/threshold
"""

import csv
import io
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------------------------
# Config (mutable at runtime via /api/threshold)
# ---------------------------------------------------------------------------
CONFIG = {
    "power_threshold": 400,      # W  — alert if exceeded
    "light_override": None,       # None = auto, True = force ON, False = force OFF
    "hvac_override": None,        # None = auto, True = force ON, False = force OFF
}

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DB_PATH = "energy.db"


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT,
            temp         REAL,
            lux          REAL,
            occupancy    INTEGER,
            power        REAL,
            light_status INTEGER,
            hvac_status  INTEGER,
            alert        INTEGER
        )
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Rule Engine
# ---------------------------------------------------------------------------
def apply_rules(temp, lux, occupancy, power):
    threshold = CONFIG["power_threshold"]

    # Light
    if CONFIG["light_override"] is not None:
        light_status = 1 if CONFIG["light_override"] else 0
    else:
        light_status = 0 if (occupancy == 0 or lux > 700) else 1

    # HVAC
    if CONFIG["hvac_override"] is not None:
        hvac_status = 1 if CONFIG["hvac_override"] else 0
    else:
        hvac_status = 1 if (occupancy == 1 and temp > 26) else 0

    # Alert
    alert = 1 if power > threshold else 0

    return light_status, hvac_status, alert


# ---------------------------------------------------------------------------
# Routes — Pages
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------
@app.route("/api/data", methods=["POST"])
def receive_data():
    """Accept sensor JSON, apply rules, store, return device states."""
    data = request.get_json(force=True)

    temp      = float(data.get("temp", 0))
    lux       = float(data.get("lux", 0))
    occupancy = int(data.get("occupancy", 0))
    power     = float(data.get("power", 0))

    light_status, hvac_status, alert = apply_rules(temp, lux, occupancy, power)
    timestamp = datetime.now().isoformat()

    conn = get_db()
    conn.execute(
        """INSERT INTO readings
           (timestamp, temp, lux, occupancy, power, light_status, hvac_status, alert)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (timestamp, temp, lux, occupancy, power, light_status, hvac_status, alert),
    )
    conn.commit()
    conn.close()

    return jsonify({
        "light_status": light_status,
        "hvac_status":  hvac_status,
        "alert":        alert,
    })


@app.route("/api/latest", methods=["GET"])
def get_latest():
    """Return last 30 rows (oldest→newest) + latest device states."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM readings ORDER BY id DESC LIMIT 30"
    ).fetchall()
    conn.close()

    if not rows:
        return jsonify({"rows": [], "latest": None})

    readings = [dict(r) for r in rows]
    latest   = readings[0]
    readings.reverse()          # chronological for chart

    return jsonify({
        "rows":      readings,
        "latest":    latest,
        "threshold": CONFIG["power_threshold"],
        "overrides": {
            "light": CONFIG["light_override"],
            "hvac":  CONFIG["hvac_override"],
        },
    })


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Return aggregate statistics across all readings."""
    conn = get_db()
    row = conn.execute("""
        SELECT
            COUNT(*)        AS total,
            ROUND(AVG(temp),  2) AS avg_temp,
            ROUND(MIN(temp),  2) AS min_temp,
            ROUND(MAX(temp),  2) AS max_temp,
            ROUND(AVG(lux),   2) AS avg_lux,
            ROUND(AVG(power), 2) AS avg_power,
            ROUND(MIN(power), 2) AS min_power,
            ROUND(MAX(power), 2) AS max_power,
            SUM(alert)      AS total_alerts,
            SUM(light_status) AS light_on_count,
            SUM(hvac_status)  AS hvac_on_count
        FROM readings
    """).fetchone()
    conn.close()

    return jsonify(dict(row))


@app.route("/api/export/csv", methods=["GET"])
def export_csv():
    """Stream all readings as a CSV file download."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM readings ORDER BY id ASC").fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "timestamp", "temp", "lux", "occupancy",
                     "power", "light_status", "hvac_status", "alert"])
    for r in rows:
        writer.writerow(list(r))

    output.seek(0)
    filename = f"energy_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/api/override", methods=["POST"])
def set_override():
    """
    Manually override a device.
    Body: { "device": "light"|"hvac", "state": true|false|null }
    """
    data   = request.get_json(force=True)
    device = data.get("device")
    state  = data.get("state")          # true / false / null

    if device == "light":
        CONFIG["light_override"] = state
    elif device == "hvac":
        CONFIG["hvac_override"] = state
    else:
        return jsonify({"error": "device must be 'light' or 'hvac'"}), 400

    return jsonify({
        "ok": True,
        "overrides": {
            "light": CONFIG["light_override"],
            "hvac":  CONFIG["hvac_override"],
        },
    })


@app.route("/api/threshold", methods=["POST"])
def set_threshold():
    """
    Update the alert power threshold.
    Body: { "threshold": 350 }
    """
    data = request.get_json(force=True)
    try:
        CONFIG["power_threshold"] = float(data["threshold"])
    except (KeyError, ValueError):
        return jsonify({"error": "threshold must be a number"}), 400

    return jsonify({"ok": True, "threshold": CONFIG["power_threshold"]})


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    print("Database initialized.")
    print("Starting Flask server on http://localhost:5000")
    app.run(debug=True, port=5000)

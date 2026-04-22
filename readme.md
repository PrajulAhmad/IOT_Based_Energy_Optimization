# Project Title : loT-Based Smart Building Energy Optimization 

# Project Objective: To monitor real-time energy consumption using loT sensors and smart meters. To analyze energy usage patterns and identify areas of energy wastage. To automate control of lighting, HVAC, and electrical appliances based on occupancy and environmental conditions. To reduce overall energy consumption and operational costs of buildings. To enhance occupant comfort while ensuring energy efficiency. To support sustainable and eco-friendly smart building solutions.

# IoT Smart Building Energy Optimizer — Working MVP

## Objective
Generate a COMPLETE, WORKING local demo. Code must run without modification after `pip install`. Prioritize working integration over clean architecture. Avoid splitting logic unnecessarily.

## Tech Stack
- Python 3 + Flask
- SQLite (inline setup, single table, check_same_thread=False)
- ONE HTML file with INLINE CSS and INLINE JavaScript
- Chart.js via CDN (no local JS files)
- Vanilla JS only

## The Only Rule Logic
- Light OFF if occupancy == 0 OR lux > 700
- HVAC ON if occupancy == 1 AND temp > 26
- HVAC OFF otherwise
- Alert if power > 400

## File Structure (MAXIMUM 3 FILES)
This is non-negotiable. More files = more ways to fail.

```
project/
├── app.py              # Flask + SQLite setup + API routes + rule logic (ALL IN ONE)
├── simulator.py        # POSTs random data every 2 seconds
└── templates/
    └── index.html      # Dashboard with inline CSS/JS
```

## Database (inside app.py)
ONE table only:
```sql
CREATE TABLE readings (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    temp REAL,
    lux REAL,
    occupancy INTEGER,
    power REAL,
    light_status INTEGER,
    hvac_status INTEGER,
    alert INTEGER
)
```

## API Endpoints
- `POST /api/data` → accepts JSON, applies rules, inserts row, returns `{light_status, hvac_status, alert}`
- `GET /api/latest` → returns last 30 rows + latest device states

## Frontend (inline everything)
- Dark theme CSS in `<style>`
- Chart.js line chart (last 30 power readings) in `<script>`
- Big numbers for latest temp, lux, occupancy, power
- Colored text/divs for Light/HVAC status (green=on, red=off)
- Red banner if latest `alert == 1`
- Auto-fetch `/api/latest` every 3 seconds

## Critical Constraints
- Enable Flask-CORS
- Chart.js from CDN: `https://cdn.jsdelivr.net/npm/chart.js`
- NO separate CSS files
- NO separate JS files  
- NO models.py
- NO engine.py
- NO multi-room logic
- NO alerts table (compute alert as 0/1 in the same row)
- Single room only
- Use `render_template('index.html')` — assume templates folder exists

## Output Order
1. `app.py` — complete, runnable Flask app with DB setup inside
2. `simulator.py` — standalone script, uses `requests`, loops every 2s
3. `index.html` — complete dashboard, inline CSS/JS
4. Run instructions (2 terminals)

## Success Criteria
After `pip install flask flask-cors requests` and running `app.py` + `simulator.py`:
- Browser shows dashboard at `http://localhost:5000`
- Numbers update every 3 seconds
- Chart draws a line
- Light/HVAC status changes color based on rules
- No 500 errors in terminal
```

---


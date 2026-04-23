# IoT-Based Smart Building Energy Optimization

A production-grade IoT energy monitoring and automation platform featuring real-time data streaming, AI-driven anomaly detection, and interactive 3D visualizations.

## 🚀 Objective
*   **Real-time Monitoring:** Track energy consumption using simulated IoT sensors and smart meters.
*   **Wastage Analysis:** Automatically identify and calculate energy wastage in kW.
*   **Automated Control:** Autonomous management of HVAC and lighting based on occupancy and environmental thresholds.
*   **Predictive Insights:** Forecast energy trends using Machine Learning (Linear Regression).
*   **Visual Excellence:** Interactive 3D floorplans and real-time heatmaps for occupancy.

## ✨ Key Features
*   **Real-time Data Pipeline:** Uses **MQTT** for high-frequency sensor data ingestion.
*   **AI Anomaly Detection:** Integrated **Isolation Forest** (Scikit-Learn) to flag unusual power spikes as they happen.
*   **3D Live Floorplan:** Interactive bird's-eye view of the building using **Three.js** with real-time status labels.
*   **Smart Automation Engine:** Rule-based logic that controls devices (ON/OFF/AUTO) based on PIR, Lux, and Temperature sensors.
*   **Dynamic Analytics:**
    *   Energy wastage calculation in **kW**.
    *   Occupancy Heatmaps showing usage percentage and total active time.
    *   Real-time cost calculator based on energy rates.
*   **Admin Controls:** Configurable temperature and power thresholds without requiring a page refresh.
*   **Logging System:** Robust logging of critical alerts (High Power, AI Anomalies) to `alerts.log`.

## 🛠️ Tech Stack
*   **Backend:** Flask, Flask-SocketIO, SQLite
*   **Communication:** Paho-MQTT (Broker: `broker.emqx.io`)
*   **Machine Learning:** Scikit-Learn (Isolation Forest), NumPy (Linear Regression)
*   **Frontend:** HTML5, CSS3 (Vanilla), Three.js (3D), Chart.js (Real-time Graphs)
*   **Simulation:** Python-based multi-room IoT sensor simulator

## 📂 Project Structure
```text
.
├── app.py              # Main Flask Server & MQTT Client
├── simulator.py        # IoT Sensor Data Simulator
├── energy.db           # SQLite Database (Auto-generated)
├── alerts.log          # System Alert History
├── static/             # JS, CSS, and 3D Assets
└── templates/          # HTML Dashboards
```

## ⚙️ Installation & Setup

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/your-username/IOT_Based_Energy_Optimization.git
    cd IOT_Based_Energy_Optimization
    ```

2.  **Create Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## 🏃 Running the Project

You will need **two terminal windows**:

### Terminal 1: Start the Backend
```bash
source venv/bin/activate
python app.py
```

### Terminal 2: Start the IoT Simulator
```bash
source venv/bin/activate
python simulator.py
```

**Access the Dashboard:** [http://localhost:5000](http://localhost:5000)

**Default Credentials:**
*   **Admin:** `admin` / `admin123`
*   **Viewer:** `viewer` / `viewer123`

## 📊 Monitoring & Alerts
*   The system logs all **WARNING** (Power > Threshold) and **ERROR** (AI Anomaly) events to `alerts.log`.
*   Real-time notifications appear on the dashboard toast system.

## 📜 License
Distributed under the MIT License. See `LICENSE` for more information.

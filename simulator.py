"""
IoT Multi-Room Sensor Simulator v3
Simulates 4 rooms with realistic patterns. Posts via HTTP every 2 seconds.
"""
import time, random, requests

API_URL = "http://localhost:5000/api/data"
ROOMS = [
    {"id": 1, "name": "Living Room", "temp": 24.0, "occ": 1, "base_power": 280},
    {"id": 2, "name": "Server Room",  "temp": 28.0, "occ": 1, "base_power": 450},
    {"id": 3, "name": "Office 1",     "temp": 23.0, "occ": 1, "base_power": 200},
    {"id": 4, "name": "Kitchen",      "temp": 25.0, "occ": 0, "base_power": 150},
]

def tick(room):
    room["temp"] += random.uniform(-0.4, 0.4)
    room["temp"] = max(18, min(38, room["temp"]))
    if random.random() < 0.08:
        room["occ"] = 1 - room["occ"]
    base_lux = 800 if room["occ"] == 0 else 350
    lux = round(max(50, min(1100, base_lux + random.uniform(-200, 200))), 1)
    bp = room["base_power"] if room["occ"] else room["base_power"] * 0.4
    if random.random() < 0.04:
        bp += 300
    power = round(max(60, bp + random.uniform(-50, 50)), 1)
    return {"room_id": room["id"], "temp": round(room["temp"], 1),
            "lux": lux, "occupancy": room["occ"], "power": power}

def main():
    print("Multi-Room IoT Simulator v3")
    print(f"Rooms: {[r['name'] for r in ROOMS]}")
    print(f"Posting to: {API_URL}\n")
    n = 0
    while True:
        n += 1
        for room in ROOMS:
            reading = tick(room)
            try:
                r = requests.post(API_URL, json=reading, timeout=5).json()
                print(f"[{n:>4}] {room['name']:>12} | "
                      f"T={reading['temp']:>5.1f} Lux={reading['lux']:>6.1f} "
                      f"Occ={'Y' if reading['occupancy'] else 'N'} "
                      f"P={reading['power']:>6.1f}W | "
                      f"L={'ON ' if r['light_status'] else 'OFF'} "
                      f"H={'ON ' if r['hvac_status'] else 'OFF'} "
                      f"{'!ALERT' if r['alert'] else '  ok  '}")
            except requests.exceptions.ConnectionError:
                print(f"  [ERR] Cannot connect. Is app.py running?")
                break
            except Exception as e:
                print(f"  [ERR] {e}")
        time.sleep(2)

if __name__ == "__main__":
    main()

"""
IoT Sensor Simulator (v2)
Sends randomised but realistic sensor readings every 2 seconds.
Simulates occupancy patterns, gradual temperature drift, and power spikes.
"""

import time
import random
import requests

API_URL = "http://localhost:5000/api/data"

# Simulate a slowly drifting room temperature
_temp = 24.0
_occ  = 1


def next_reading():
    global _temp, _occ

    # Gradual temperature drift
    _temp += random.uniform(-0.5, 0.5)
    _temp  = max(18.0, min(38.0, _temp))

    # Occasional occupancy change (~10 % chance each tick)
    if random.random() < 0.1:
        _occ = 1 - _occ

    # Lux: bright when unoccupied (window), dim when occupied (blinds)
    base_lux = 800 if _occ == 0 else 350
    lux = round(base_lux + random.uniform(-200, 200), 1)
    lux = max(50.0, min(1100.0, lux))

    # Power: higher baseline when occupied; random spike ~5 % of the time
    base_power = 300.0 if _occ == 1 else 150.0
    if random.random() < 0.05:
        base_power += 300          # spike
    power = round(base_power + random.uniform(-60, 60), 1)
    power = max(80.0, power)

    return {
        "temp":      round(_temp, 1),
        "lux":       lux,
        "occupancy": _occ,
        "power":     power,
    }


def main():
    print("IoT Sensor Simulator v2 started")
    print(f"Posting to: {API_URL}")
    print("Press Ctrl+C to stop\n")

    count = 0
    while True:
        count += 1
        reading = next_reading()
        try:
            resp   = requests.post(API_URL, json=reading, timeout=5)
            result = resp.json()
            print(
                f"[{count:>4}] "
                f"Temp={reading['temp']:>5.1f}C  "
                f"Lux={reading['lux']:>6.1f}  "
                f"Occ={'YES' if reading['occupancy'] else 'NO ':>3}  "
                f"Power={reading['power']:>6.1f}W  ->  "
                f"Light={'ON ' if result['light_status'] else 'OFF'}  "
                f"HVAC={'ON ' if result['hvac_status'] else 'OFF'}  "
                f"Alert={'!!! HIGH POWER' if result['alert'] else 'OK'}"
            )
        except requests.exceptions.ConnectionError:
            print("  [ERR] Cannot connect. Is app.py running?")
        except Exception as exc:
            print(f"  [ERR] {exc}")

        time.sleep(2)


if __name__ == "__main__":
    main()

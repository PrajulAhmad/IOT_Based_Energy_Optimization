"""
IoT Multi-Room Sensor Simulator v4 (MQTT Edition)
Simulates 4 rooms with realistic patterns. Publishes via MQTT every 2 seconds.
"""
import time, random, json
import paho.mqtt.client as mqtt

MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883
MQTT_TOPIC_PREFIX = "prajul_smart_building/sensors/"

ROOMS = [
    {"id": 1, "name": "Living Room", "temp": 24.0, "occ": 1, "base_power": 280},
    {"id": 2, "name": "Server Room",  "temp": 28.0, "occ": 1, "base_power": 450},
    {"id": 3, "name": "Office 1",     "temp": 23.0, "occ": 1, "base_power": 200},
    {"id": 4, "name": "Kitchen",      "temp": 25.0, "occ": 0, "base_power": 150},
]

def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"Connected to MQTT broker at {MQTT_BROKER} (Code: {reason_code})")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
print(f"Connecting to {MQTT_BROKER}...")
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

def tick(room):
    room["temp"] += random.uniform(-0.1, 0.1)
    room["temp"] = max(20.0, min(28.0, room["temp"]))
    if random.random() < 0.08:
        room["occ"] = 1 - room["occ"]
    base_lux = 800 if room["occ"] == 0 else 350
    lux = round(max(50, min(1100, base_lux + random.uniform(-200, 200))), 1)
    
    bp = room["base_power"] if room["occ"] else room["base_power"] * 0.4
    
    # Simulate anomalous power spike randomly
    if random.random() < 0.03:
        bp += random.uniform(500, 1000)
        
    if random.random() < 0.04:
        bp += 300
        
    power = round(max(60, bp + random.uniform(-50, 50)), 1)
    return {"room_id": room["id"], "temp": round(room["temp"], 1),
            "lux": lux, "occupancy": room["occ"], "power": power}

def main():
    print("Multi-Room IoT Simulator v4 (MQTT)")
    print(f"Rooms: {[r['name'] for r in ROOMS]}")
    print(f"Publishing to: {MQTT_TOPIC_PREFIX}<room_id>\n")
    n = 0
    try:
        while True:
            n += 1
            for room in ROOMS:
                reading = tick(room)
                topic = f"{MQTT_TOPIC_PREFIX}{room['id']}"
                payload = json.dumps(reading)
                client.publish(topic, payload)
                
                print(f"[{n:>4}] Published to {topic}: {payload}")
            time.sleep(2)
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()

import paho.mqtt.client as mqtt
import sqlite3
import datetime
import os
import time
import collections

MQTT_BROKER = "mosquitto"
MQTT_PORT = 1883
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
DB_PATH = "/data/id3_data.db"
MAX_CACHE_SIZE = 1000

db_conn = None
last_payloads = collections.OrderedDict()


def init_db():
    global db_conn
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    db_conn.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            topic TEXT,
            payload TEXT
        )
    ''')
    db_conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp DESC)
    ''')
    db_conn.commit()


def on_connect(client, userdata, flags, reason_code, properties):
    print(f"Connected with result code {reason_code}")
    client.subscribe("#")


def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload.decode('utf-8')

        if last_payloads.get(topic) == payload:
            return

        if topic in last_payloads:
            last_payloads.move_to_end(topic)
        last_payloads[topic] = payload
        if len(last_payloads) > MAX_CACHE_SIZE:
            last_payloads.popitem(last=False)

        timestamp = datetime.datetime.now().isoformat()
        db_conn.execute(
            "INSERT INTO messages (timestamp, topic, payload) VALUES (?, ?, ?)",
            (timestamp, topic, payload)
        )
        db_conn.commit()
    except Exception as e:
        print(f"Error storing message: {e}")


if __name__ == "__main__":
    init_db()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message

    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            break
        except Exception as e:
            print(f"Waiting for broker... {e}")
            time.sleep(2)

    client.loop_forever()

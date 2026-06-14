import sqlite3
import json

DB_PATH = "/home/admin/docker/myCar/database/id3_data.db"

def inspect_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all unique topics and a sample payload for each
    cursor.execute("SELECT topic, payload FROM messages GROUP BY topic")
    topics = cursor.fetchall()
    
    print(f"Total unique topics: {len(topics)}")
    for topic, payload in topics:
        print(f"Topic: {topic}")
        print(f"Sample Payload: {payload[:100]}")
        print("-" * 40)
    
    conn.close()

if __name__ == "__main__":
    inspect_db()

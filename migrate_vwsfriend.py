#!/usr/bin/env python3
"""
Migration: vwsfriend PostgreSQL → myCar SQLite
Converts historical vwsfriend data into synthetic MQTT messages.
"""
import os
import sqlite3
from datetime import datetime, timezone, timedelta

import psycopg2
import pytz

VIN = "YOUR_VIN_HERE"
BASE = f"carconnectivity/0/garage/{VIN}"
TZ_LOCAL = pytz.timezone("Europe/Vienna")

CHARGING_STATE_MAP = {
    "CHARGING": "charging",
    "NOT_READY_FOR_CHARGING": "off",
    "CHARGE_PURPOSE_REACHED_NOT_CONSERVATION_CHARGING": "off",
    "CHARGE_PURPOSE_REACHED_CONSERVATION": "conservation",
    "ERROR": "invalid",
}


def to_local_iso(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_LOCAL).isoformat()


def migrate():
    pg = psycopg2.connect(
        host=os.environ.get("DB_HOST", "postgresdbbackend"),
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ.get("DB_NAME", "vwsfriend"),
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "secret"),
    )
    sq = sqlite3.connect("/data/id3_data.db")
    messages = []

    cur = pg.cursor()

    # --- 1. Battery: SOC + range ---
    print("Reading battery table...")
    cur.execute("""
        SELECT "carCapturedTimestamp", "currentSOC_pct", "cruisingRangeElectric_km"
        FROM battery ORDER BY "carCapturedTimestamp"
    """)
    last_soc = last_range = None
    for ts, soc, rng in cur.fetchall():
        ts_str = to_local_iso(ts)
        if soc is not None and soc != last_soc:
            messages.append((ts_str, f"{BASE}/drives/primary/level", str(float(soc))))
            last_soc = soc
        if rng is not None and rng != last_range:
            messages.append((ts_str, f"{BASE}/drives/primary/range", str(float(rng))))
            last_range = rng

    # --- 2. Battery temperature (Kelvin → Celsius) ---
    print("Reading battery_temperature table...")
    cur.execute("""
        SELECT "carCapturedTimestamp", "temperatureHvBatteryMin_K", "temperatureHvBatteryMax_K"
        FROM battery_temperature ORDER BY "carCapturedTimestamp"
    """)
    last_tmin = last_tmax = None
    for ts, tmin, tmax in cur.fetchall():
        ts_str = to_local_iso(ts)
        if tmin is not None:
            c_min = round(tmin - 273.15, 1)
            if c_min != last_tmin:
                messages.append((ts_str, f"{BASE}/drives/primary/battery/temperature_min", str(c_min)))
                last_tmin = c_min
        if tmax is not None:
            c_max = round(tmax - 273.15, 1)
            if c_max != last_tmax:
                messages.append((ts_str, f"{BASE}/drives/primary/battery/temperature_max", str(c_max)))
                last_tmax = c_max

    # --- 3. Charges: state + power ---
    print("Reading charges table...")
    cur.execute("""
        SELECT "carCapturedTimestamp", "chargingState", "chargePower_kW"
        FROM charges ORDER BY "carCapturedTimestamp"
    """)
    last_state = last_power = None
    for ts, state, power in cur.fetchall():
        ts_str = to_local_iso(ts)
        mapped = CHARGING_STATE_MAP.get(state, "invalid")
        if mapped != last_state:
            messages.append((ts_str, f"{BASE}/charging/state", mapped))
            last_state = mapped
        if power is not None and round(power, 2) != last_power:
            messages.append((ts_str, f"{BASE}/charging/power", str(round(power, 2))))
            last_power = round(power, 2)

    # --- 4. Charging sessions: type + connector + SoC at start/end ---
    print("Reading charging_sessions table...")
    cur.execute("""
        SELECT connected, started, ended, disconnected, acdc,
               "startSOC_pct", "endSOC_pct", position_latitude, position_longitude
        FROM charging_sessions ORDER BY started
    """)
    for connected, started, ended, disconnected, acdc, start_soc, end_soc, lat, lon in cur.fetchall():
        if connected:
            ts = to_local_iso(connected)
            messages.append((ts, f"{BASE}/charging/connector/connection_state", "connected"))
            if lat is not None:
                messages.append((ts, f"{BASE}/position/latitude", str(lat)))
            if lon is not None:
                messages.append((ts, f"{BASE}/position/longitude", str(lon)))
        if started:
            ts = to_local_iso(started)
            if acdc:
                messages.append((ts, f"{BASE}/charging/type", acdc.lower()))
            if start_soc is not None:
                messages.append((ts, f"{BASE}/drives/primary/level", str(float(start_soc))))
        if ended:
            ts = to_local_iso(ended)
            if end_soc is not None:
                messages.append((ts, f"{BASE}/drives/primary/level", str(float(end_soc))))
        if disconnected:
            ts = to_local_iso(disconnected)
            messages.append((ts, f"{BASE}/charging/connector/connection_state", "disconnected"))

    # --- 5. Trips: state transitions + odometer + position ---
    print("Reading trips table...")
    cur.execute("""
        SELECT t."startDate", t."endDate",
               t."start_mileage_km", t."end_mileage_km",
               t."start_position_latitude",  t."start_position_longitude",
               t."destination_position_latitude", t."destination_position_longitude",
               ls.city, ls.road, ld.city, ld.road
        FROM trips t
        LEFT JOIN locations ls ON t."start_location_id"       = ls.osm_id
        LEFT JOIN locations ld ON t."destination_location_id" = ld.osm_id
        ORDER BY t."startDate"
    """)
    for row in cur.fetchall():
        (start_dt, end_dt,
         start_km, end_km,
         start_lat, start_lon,
         dest_lat, dest_lon,
         start_city, start_road,
         dest_city, dest_road) = row

        # Normalize to UTC-aware
        if start_dt and start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt and end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        # 1 second before departure: set parked + odometer + position
        pre_ts = to_local_iso(start_dt - timedelta(seconds=1)) if start_dt else None
        start_str = to_local_iso(start_dt)
        end_str = to_local_iso(end_dt)

        if pre_ts:
            if start_km is not None:
                messages.append((pre_ts, f"{BASE}/odometer", str(float(start_km))))
            if start_lat is not None:
                messages.append((pre_ts, f"{BASE}/position/latitude", str(start_lat)))
            if start_lon is not None:
                messages.append((pre_ts, f"{BASE}/position/longitude", str(start_lon)))
            if start_city:
                messages.append((pre_ts, f"{BASE}/position/position_location/city", start_city))
            if start_road:
                messages.append((pre_ts, f"{BASE}/position/position_location/road", start_road))
            messages.append((pre_ts, f"{BASE}/state", "parked"))

        if start_str:
            messages.append((start_str, f"{BASE}/state", "driving"))

        if end_str:
            if end_km is not None:
                messages.append((end_str, f"{BASE}/odometer", str(float(end_km))))
            if dest_lat is not None:
                messages.append((end_str, f"{BASE}/position/latitude", str(dest_lat)))
            if dest_lon is not None:
                messages.append((end_str, f"{BASE}/position/longitude", str(dest_lon)))
            if dest_city:
                messages.append((end_str, f"{BASE}/position/position_location/city", dest_city))
            if dest_road:
                messages.append((end_str, f"{BASE}/position/position_location/road", dest_road))
            messages.append((end_str, f"{BASE}/state", "parked"))

    # --- 6. Online states → connection_state ---
    print("Reading onlinestates table...")
    cur.execute('SELECT "onlineTime", "offlineTime" FROM onlinestates ORDER BY "onlineTime"')
    for online_ts, offline_ts in cur.fetchall():
        if online_ts:
            if online_ts.tzinfo is None:
                online_ts = online_ts.replace(tzinfo=timezone.utc)
            messages.append((to_local_iso(online_ts), f"{BASE}/connection_state", "reachable"))
        if offline_ts:
            if offline_ts.tzinfo is None:
                offline_ts = offline_ts.replace(tzinfo=timezone.utc)
            messages.append((to_local_iso(offline_ts), f"{BASE}/connection_state", "unreachable"))

    # --- Insert into SQLite ---
    messages = [(ts, topic, payload) for ts, topic, payload in messages if ts is not None]
    messages.sort(key=lambda x: x[0])

    cur_sq = sq.cursor()
    cur_sq.execute("SELECT MIN(timestamp) FROM messages")
    earliest_existing = cur_sq.fetchone()[0]
    print(f"Earliest existing message in SQLite: {earliest_existing}")
    print(f"Total historical messages to process: {len(messages)}")

    inserted = skipped_overlap = 0
    for ts_str, topic, payload in messages:
        if earliest_existing and ts_str >= earliest_existing:
            skipped_overlap += 1
            continue
        cur_sq.execute(
            "INSERT INTO messages (timestamp, topic, payload) VALUES (?, ?, ?)",
            (ts_str, topic, payload),
        )
        inserted += 1

    sq.commit()
    print(f"\nDone: {inserted} messages inserted, {skipped_overlap} skipped (timestamp overlap with existing data).")

    cur.close()
    pg.close()
    sq.close()


if __name__ == "__main__":
    migrate()

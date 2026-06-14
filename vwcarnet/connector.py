"""VW CarNet → MQTT connector (volkswagencarnet library).

Polls vehicle data every 5 minutes via the unofficial WeConnect API
and publishes to MQTT using the same topic-suffix structure as the
eudata connector — so the dashboard LIKE-queries pick up either source,
always preferring the most-recent row.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

import aiohttp
import paho.mqtt.client as mqtt
from volkswagencarnet.vw_connection import Connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
_LOGGER = logging.getLogger("vwcarnet")

# ── Config ─────────────────────────────────────────────────────────────────────
MQTT_BROKER   = os.environ.get("MQTT_BROKER", "mosquitto")
MQTT_PORT     = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER     = os.environ.get("MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
VW_EMAIL      = os.environ.get("VW_USERNAME", "")
VW_PASSWORD   = os.environ.get("VW_PASSWORD", "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))   # 5 min default
ABRP_TOKEN    = os.environ.get("ABRP_TOKEN", "")

ABRP_API_URL = "https://api.iternio.com/1/tlm/send"

# ── MQTT ───────────────────────────────────────────────────────────────────────

def mqtt_connect() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            client.loop_start()
            _LOGGER.info("Connected to MQTT broker %s:%s", MQTT_BROKER, MQTT_PORT)
            return client
        except Exception as exc:
            _LOGGER.warning("Waiting for MQTT broker... %s", exc)
            time.sleep(5)


def pub(client: mqtt.Client, topic: str, value) -> None:
    if value is None:
        return
    client.publish(topic, str(value), retain=True)


# ── Charging state normalisation ───────────────────────────────────────────────
# volkswagencarnet returns descriptive strings; map to dashboard-compatible values.

_CHARGING_STATE_MAP: dict[str, str] = {
    "charging":  "charging",
    "on":        "charging",
    "off":       "off",
    "ready":     "off",
    "discharging": "off",
    "conservation": "charging",
    "error":     "invalid",
    "unsupported": "invalid",
}

def _norm_charge_state(raw: str | None) -> str:
    if raw is None:
        return "off"
    return _CHARGING_STATE_MAP.get(raw.lower(), raw.lower())


# ── Topic builder ──────────────────────────────────────────────────────────────

def build_topics(vehicle) -> dict[str, str]:
    vin  = vehicle.vin
    base = f"vwcarnet/vehicles/{vin}"
    topics: dict[str, str] = {}

    # ── identity
    topics[f"{base}/name"]  = vehicle.nickname or vin
    topics[f"{base}/model"] = vehicle.model or "VW ID.3"

    # ── battery / range
    if vehicle.battery_level is not None:
        topics[f"{base}/drives/primary/level"] = vehicle.battery_level

    if vehicle.electric_range is not None:
        topics[f"{base}/drives/primary/range"] = vehicle.electric_range

    if vehicle.distance is not None:
        topics[f"{base}/odometer"] = vehicle.distance

    # ── charging
    charge_state_norm = _norm_charge_state(vehicle.charging_state)
    topics[f"{base}/charging/state"] = charge_state_norm

    if vehicle.charging_power is not None:
        topics[f"{base}/charging/power"] = vehicle.charging_power

    if vehicle.battery_target_charge_level is not None:
        topics[f"{base}/charging/settings/target_level"] = vehicle.battery_target_charge_level

    if vehicle.charge_max_ac_ampere is not None:
        topics[f"{base}/charging/settings/maximum_current"] = vehicle.charge_max_ac_ampere

    # derive charge type from power level (>11 kW → DC)
    if vehicle.charging_power is not None:
        try:
            charge_type = "dc" if float(vehicle.charging_power) > 11 else "ac"
            topics[f"{base}/charging/type"]                    = charge_type
            topics[f"{base}/charging/settings/charge_type"]   = charge_type
        except (ValueError, TypeError):
            pass

    # ── position / GPS
    pos = vehicle.position
    if pos and pos.get("lat") not in (None, "?") and pos.get("lng") not in (None, "?"):
        topics[f"{base}/position/lat"] = pos["lat"]
        topics[f"{base}/position/lng"] = pos["lng"]

    # ── vehicle state
    if vehicle.vehicle_moving:
        vstate = "driving"
    elif charge_state_norm == "charging":
        vstate = "charging"
    else:
        vstate = "parked"
    topics[f"{base}/garage/{vin}/state"] = vstate

    # ── climatisation
    if vehicle.climatisation_target_temperature is not None:
        topics[f"{base}/climatization/target_temperature"] = vehicle.climatisation_target_temperature

    topics[f"{base}/climatization/state"] = "on" if vehicle.electric_climatisation else "off"
    topics[f"{base}/climatization/settings/window_heating"] = (
        "True" if vehicle.window_heater else "False"
    )

    # ── windows / doors
    topics[f"{base}/windows/closed"] = str(vehicle.windows_closed)

    # ── connection / timestamp
    topics[f"{base}/garage/{vin}/connection_state"] = "reachable"
    topics["vwcarnet/last_update"] = datetime.now(timezone.utc).isoformat()

    return topics


# ── ABRP push ──────────────────────────────────────────────────────────────────

async def push_abrp(session: aiohttp.ClientSession, vehicle) -> None:
    if not ABRP_TOKEN or vehicle.battery_level is None:
        return

    tlm: dict = {
        "utc":         int(datetime.now(timezone.utc).timestamp()),
        "soc":         float(vehicle.battery_level),
        "is_charging": 1 if vehicle.charging else 0,
    }

    if vehicle.charging_power is not None:
        try:
            tlm["power"] = float(vehicle.charging_power)
        except (ValueError, TypeError):
            pass

    if vehicle.electric_range is not None:
        try:
            tlm["est_battery_range"] = float(vehicle.electric_range)
        except (ValueError, TypeError):
            pass

    pos = vehicle.position
    if pos and pos.get("lat") not in (None, "?") and pos.get("lng") not in (None, "?"):
        tlm["lat"] = pos["lat"]
        tlm["lon"] = pos["lng"]

    try:
        async with session.post(
            ABRP_API_URL,
            params={"token": ABRP_TOKEN},
            json={"tlm": tlm},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.json()
            if body.get("status") == "ok":
                _LOGGER.info(
                    "ABRP: sent SOC=%.0f%% charging=%s gps=%s",
                    tlm["soc"],
                    bool(vehicle.charging),
                    "lat" in tlm,
                )
            else:
                _LOGGER.warning("ABRP: unexpected response: %s", body)
    except Exception as exc:
        _LOGGER.warning("ABRP: push failed: %s", exc)


# ── Main loop ──────────────────────────────────────────────────────────────────

async def fetch_and_publish(
    session: aiohttp.ClientSession,
    mqtt_client: mqtt.Client,
) -> None:
    connection = Connection(session, VW_EMAIL, VW_PASSWORD)

    if not await connection.doLogin():
        _LOGGER.error("Login failed")
        return

    if not await connection.update():
        _LOGGER.error("Vehicle data update failed")
        return

    vehicles = list(connection.vehicles)
    if not vehicles:
        _LOGGER.warning("No vehicles found in account")
        return

    vehicle = vehicles[0]
    _LOGGER.info(
        "Vehicle: %s (%s) — SOC=%s%% range=%s km odo=%s km charging=%s",
        vehicle.nickname or vehicle.vin,
        vehicle.vin,
        vehicle.battery_level,
        vehicle.electric_range,
        vehicle.distance,
        vehicle.charging_state,
    )

    topics = build_topics(vehicle)
    for topic, value in topics.items():
        pub(mqtt_client, topic, value)

    _LOGGER.info("Published %d MQTT topics", len(topics))

    await push_abrp(session, vehicle)


async def main() -> None:
    if not VW_EMAIL or not VW_PASSWORD:
        raise RuntimeError("VW_USERNAME and VW_PASSWORD must be set")

    mqtt_client = mqtt_connect()

    while True:
        try:
            async with aiohttp.ClientSession(
                headers={"Connection": "keep-alive"},
                cookie_jar=aiohttp.CookieJar(),
            ) as session:
                await fetch_and_publish(session, mqtt_client)
        except Exception as exc:
            _LOGGER.exception("Poll cycle failed: %s", exc)

        _LOGGER.info("Sleeping %d s until next poll...", POLL_INTERVAL)
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())

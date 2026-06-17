"""VW EU Data Act → MQTT connector.

Fetches vehicle data from the VW EU Data Act portal every 15 minutes
and publishes it to MQTT using the same topic structure as the old
carconnectivity stack.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import aiohttp
import paho.mqtt.client as mqtt

from api import ApiError, AuthError, EudaApiClient, NO_CONTENT_SUFFIX, get_field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
_LOGGER = logging.getLogger("eudata")

# ── Config ─────────────────────────────────────────────────────────────────────
MQTT_BROKER   = os.environ.get("MQTT_BROKER", "mosquitto")
MQTT_PORT     = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER     = os.environ.get("MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
VW_EMAIL      = os.environ.get("VW_USERNAME", "")
VW_PASSWORD   = os.environ.get("VW_PASSWORD", "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", str(15 * 60)))
ABRP_TOKEN    = os.environ.get("ABRP_TOKEN", "")

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
        except Exception as e:
            _LOGGER.warning("Waiting for MQTT broker... %s", e)
            time.sleep(5)


def pub(client: mqtt.Client, topic: str, value) -> None:
    if value is None:
        return
    client.publish(topic, str(value), retain=True)


# ── Normalization helpers ──────────────────────────────────────────────────────

# EU Data Act enum → dashboard-compatible charging state
_CHARGE_STATE_MAP = {
    "charge_state_charging":                            "charging",
    "charge_state_charging_hv_battery":                 "charging",
    "charge_state_conservation_charging":               "charging",
    "charge_state_conserving":                          "charging",
    "charge_state_ready_for_charging":                  "off",
    "charge_state_not_ready_for_charging":              "off",
    "charge_state_charge_purpose_reached_conservation": "off",
    "charge_state_charge_purpose_reached_not_charging": "off",
    "charge_state_error":                               "invalid",
    "charge_state_unsupported":                         "invalid",
}

def _normalize_charge_state(raw: str) -> str:
    return _CHARGE_STATE_MAP.get(raw.lower(), raw.lower())


# EU Data Act enum → ampere value (ID.3 uses 16 A max / 8 A reduced)
_MAX_CURRENT_MAP = {
    "max_charge_current_ac_maximum": "16",
    "max_charge_current_ac_reduced": "8",
}

def _normalize_max_current(raw: str) -> str | None:
    try:
        float(raw)
        return raw
    except ValueError:
        return _MAX_CURRENT_MAP.get(raw.lower())


# ── ABRP telemetry ────────────────────────────────────────────────────────────

ABRP_API_URL = "https://api.iternio.com/1/tlm/send"

async def push_abrp(session: aiohttp.ClientSession, data_points: list[dict]) -> None:
    if not ABRP_TOKEN:
        return

    soc = get_field(data_points, "battery_state_report.soc")
    if soc is None:
        _LOGGER.debug("ABRP: no SOC available, skipping")
        return

    charge_state_raw = get_field(data_points, "charging_state_report.current_charge_state")
    is_charging = charge_state_raw is not None and "charging" in charge_state_raw.lower()
    charge_power = get_field(data_points, "battery_state_report.charge_power")

    tlm: dict = {
        "utc":         int(datetime.now(timezone.utc).timestamp()),
        "soc":         float(soc),
        "is_charging": 1 if is_charging else 0,
    }
    if charge_power is not None:
        try:
            tlm["power"] = float(charge_power)
        except (ValueError, TypeError):
            pass

    try:
        async with session.post(
            ABRP_API_URL,
            params={"token": ABRP_TOKEN},
            json={"tlm": tlm},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.json()
            if body.get("status") == "ok":
                _LOGGER.info("ABRP: telemetry sent (SOC=%.0f%%, charging=%s)", tlm["soc"], bool(is_charging))
            else:
                _LOGGER.warning("ABRP: unexpected response: %s", body)
    except Exception as e:
        _LOGGER.warning("ABRP: push failed: %s", e)


# ── Topic mapping ──────────────────────────────────────────────────────────────

def build_topics(vin: str, nickname: str, data_points: list[dict]) -> dict[str, str]:
    """Map EU Data Act fields → MQTT topics."""
    base = f"eudata/vehicles/{vin}"

    def field(name: str) -> str | None:
        return get_field(data_points, name)

    topics: dict[str, str] = {}

    # ── identity (published once, static after first fetch)
    topics[f"{base}/name"]  = nickname or vin
    topics[f"{base}/model"] = "VW ID.3"

    # ── battery / range
    soc = field("battery_state_report.soc")
    if soc is not None:
        topics[f"{base}/drives/primary/level"] = soc

    rng = field("range.value")
    if rng is not None:
        topics[f"{base}/drives/primary/range"] = rng

    odometer = field("mileage.value")
    if odometer is not None:
        topics[f"{base}/odometer"] = odometer

    # ── charging
    charge_state_raw = field("charging_state_report.current_charge_state")
    if charge_state_raw is not None:
        topics[f"{base}/charging/state"] = _normalize_charge_state(charge_state_raw)

    charge_power = field("battery_state_report.charge_power")
    if charge_power is not None:
        topics[f"{base}/charging/power"] = charge_power

    target_soc = field("settings.target_soc")
    if target_soc is not None:
        topics[f"{base}/charging/settings/target_level"] = target_soc

    max_current = field("settings.max_charge_current_ac")
    if max_current is not None:
        normalized = _normalize_max_current(max_current)
        if normalized is not None:
            topics[f"{base}/charging/settings/maximum_current"] = normalized

    charge_type = field("charging_state_report.charge_type")
    if charge_type is not None:
        ct = charge_type.lower()
        if ct.startswith("charge_type_"):
            ct = ct[len("charge_type_"):]
        topics[f"{base}/charging/settings/charge_type"] = ct
        topics[f"{base}/charging/type"] = ct

    # Estimated charge completion: remaining minutes → ISO timestamp
    remaining_mins_raw = field("battery_state_report.remaining_charging_time_complete")
    if remaining_mins_raw is not None:
        try:
            remaining_mins = int(float(remaining_mins_raw))
            if remaining_mins > 0:
                est = datetime.now(timezone.utc) + timedelta(minutes=remaining_mins)
                topics[f"{base}/charging/estimated_date_reached"] = est.isoformat()
        except (ValueError, TypeError):
            pass

    # ── vehicle state (derived: charging > parked; driving not detectable at 15 min)
    if charge_state_raw:
        active_states = {"charging", "conserving", "charge_purpose_reached"}
        vs = "charging" if charge_state_raw.lower() in active_states else "parked"
        topics[f"{base}/garage/{vin}/state"] = vs

    # ── climatisation
    window_heat = field("window_heating_state")
    if window_heat is not None:
        wh = window_heat.upper()
        topics[f"{base}/climatization/settings/window_heating"] = (
            "True" if "ON" in wh else "False"
        )

    # prefer target_soc as climate temp source if dedicated field absent
    # actual climate target temp isn't always in the EU Data Act dataset
    for temp_field in ("remaining_climate_time",):
        v = field(temp_field)
        if v is not None:
            topics[f"{base}/climatization/remaining_time"] = v

    # ── connection / last update
    topics[f"{base}/garage/{vin}/connection_state"] = "reachable"
    topics["eudata/last_update"] = datetime.now(timezone.utc).isoformat()

    return topics


# ── Main loop ──────────────────────────────────────────────────────────────────

async def fetch_and_publish(client: EudaApiClient, mqtt_client: mqtt.Client) -> None:
    """One fetch-and-publish cycle."""
    vehicles = await client.async_list_vehicles()
    if not vehicles:
        _LOGGER.warning("No vehicles returned from portal")
        return

    vehicle = vehicles[0]
    vin      = vehicle["vin"]
    nickname = vehicle.get("nickname", vin)
    _LOGGER.info("Vehicle: %s (%s)", nickname, vin)

    meta = await client.async_get_metadata(vin)
    identifier = meta.get("Identifier")
    if not identifier:
        _LOGGER.error("No Identifier in metadata response: %s", meta)
        return

    datasets = await client.async_list_datasets(vin, identifier)
    if not datasets:
        _LOGGER.warning("No datasets available yet")
        return

    # newest first; skip no-content stubs
    dataset_name = next(
        (d["name"] for d in datasets if not d["name"].endswith(NO_CONTENT_SUFFIX)),
        None,
    )
    if dataset_name is None:
        _LOGGER.warning("All available datasets are no-content stubs")
        return

    _LOGGER.info("Downloading dataset: %s", dataset_name)
    payload = await client.async_download_dataset(vin, identifier, dataset_name)
    data_points: list[dict] = payload.get("Data", [])
    _LOGGER.info("Got %d data points", len(data_points))
    _LOGGER.info("Available fields: %s", [d.get("dataFieldName") for d in data_points])

    topics = build_topics(vin, nickname, data_points)
    for topic, value in topics.items():
        pub(mqtt_client, topic, value)
        _LOGGER.debug("  %s = %s", topic, value)

    _LOGGER.info("Published %d MQTT topics", len(topics))
    pub(mqtt_client, "eudata/api_status", "ok")
    await push_abrp(session, data_points)


async def main() -> None:
    if not VW_EMAIL or not VW_PASSWORD:
        raise RuntimeError("VW_USERNAME and VW_PASSWORD environment variables must be set")

    mqtt_client = mqtt_connect()

    while True:
        connector = aiohttp.TCPConnector(ssl=True)
        session = aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(),
            connector=connector,
        )
        client = EudaApiClient(session, VW_EMAIL, VW_PASSWORD)
        try:
            await fetch_and_publish(client, mqtt_client)
        except AuthError as e:
            _LOGGER.error("Authentication failed: %s", e)
            pub(mqtt_client, "eudata/api_status", f"Auth-Fehler")
        except ApiError as e:
            _LOGGER.error("API error: %s", e)
            # extract "HTTP 5xx" from message like "GET … -> HTTP 500"
            import re as _re
            m = _re.search(r"HTTP\s*(\d{3})", str(e))
            code = f"HTTP {m.group(1)}" if m else "API-Fehler"
            pub(mqtt_client, "eudata/api_status", code)
        except Exception as e:
            _LOGGER.exception("Unexpected error: %s", e)
            pub(mqtt_client, "eudata/api_status", "Unbekannter Fehler")
        finally:
            await session.close()

        _LOGGER.info("Sleeping %d seconds until next poll...", POLL_INTERVAL)
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())

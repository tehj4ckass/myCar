# ⚡ myCar.dashboard

> Self-hosted VW ID.3 monitoring stack running on a Raspberry Pi — real-time SOC, charging sessions, trip history, battery health, and ABRP integration.

![Stack](https://img.shields.io/badge/stack-Docker_Compose-2496ED?logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/python-3.11-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/dashboard-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![MQTT](https://img.shields.io/badge/broker-Mosquitto-660066?logo=eclipsemosquitto&logoColor=white)
![SQLite](https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite&logoColor=white)
![Pi](https://img.shields.io/badge/runs_on-Raspberry_Pi-A22846?logo=raspberrypi&logoColor=white)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Raspberry Pi                             │
│                                                                 │
│  ┌──────────────┐     MQTT      ┌──────────────┐               │
│  │   eudata     │ ────────────► │  mosquitto   │               │
│  │  connector   │  (retain=T)   │   broker     │               │
│  │              │               └──────┬───────┘               │
│  │ VW EU Data   │                      │ subscribe             │
│  │ Act Portal   │               ┌──────▼───────┐               │
│  │ (15 min)     │               │   sqlite     │               │
│  └──────────────┘               │   catcher    │               │
│                                 │              │               │
│  ┌──────────────┐               │  id3_data.db │               │
│  │  vwcarnet    │               └──────┬───────┘               │
│  │  connector   │  (disabled –         │ query                 │
│  │  [fallback]  │   VW API broken)     │                       │
│  └──────────────┘               ┌──────▼───────┐               │
│                                 │  Streamlit   │ :8502         │
│                                 │  dashboard   │ ──────► 🌐    │
│                                 └──────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Services

| Service | Container | Description |
|---|---|---|
| `mosquitto` | `id3_mosquitto` | MQTT broker — message bus for all vehicle data |
| `eudata` | `id3_eudata` | VW EU Data Act connector — polls vehicle state every 15 min |
| `vwcarnet` | `id3_vwcarnet` | volkswagencarnet connector — **disabled** (VW broke unofficial API May 2026) |
| `sqlite_catcher` | `id3_sqlite_catcher` | Subscribes to all MQTT topics and persists to SQLite |
| `dashboard` | `id3_dashboard` | Streamlit web dashboard on port 8502 |

---

## Dashboard

Four pages, dark-themed, auto-refresh every 5 minutes:

- **Übersicht** — Live SOC gauge, range, odometer, charging status, monthly statistics (km driven, energy charged, cost estimate, battery SoH trend)
- **Ladevorgänge** — Active charging state, session timeline chart, historical session log with energy/cost/duration
- **Trips** — Trip history detected from vehicle state transitions, map visualization of historical GPS tracks

---

## Data Source: VW EU Data Act Portal

Since VW killed the WeConnect API on **27 May 2026**, this stack uses the free [VW EU Data Act portal](https://eu-data-act.drivesomethinggreater.com) — mandated by EU regulation, no subscription required.

**What's available:**

| Field | Available |
|---|---|
| State of Charge (SOC) | ✅ |
| Estimated range | ✅ |
| Odometer | ✅ |
| Charging state & power | ✅ |
| Target SOC / max current | ✅ |
| GPS position | ❌ |
| Doors / windows | ❌ |
| Climate details | ❌ |
| **Polling frequency** | **15 min** |

> The `vwcarnet/` service provides a ready-to-enable connector based on [volkswagencarnet](https://github.com/robinostlund/volkswagencarnet) (5 min polling, GPS, full telemetry) — re-enable it if/when the upstream library regains working auth against VW's backend.

---

## ABRP Integration

The eudata connector pushes live SOC and charging state to [A Better Route Planner](https://abetterrouteplanner.com) after every successful poll. Set your ABRP user token in `.env` to enable.

---

## Setup

### 1. Prerequisites

- Raspberry Pi (tested on Pi 5, aarch64) with Docker + Docker Compose
- VW ID account (same credentials as the VW app)
- VW EU Data Act portal configured: [eu-data-act.drivesomethinggreater.com](https://eu-data-act.drivesomethinggreater.com)
  - Log in → set up a **continuous data request** for your vehicle

### 2. Clone & configure

```bash
git clone https://github.com/yourusername/myCar.git
cd myCar
cp .env.example .env
```

Edit `.env`:

```env
VW_USERNAME=your@email.com
VW_PASSWORD=yourpassword
MQTT_USER=mqttuser
MQTT_PASSWORD=mqttpassword
ABRP_TOKEN=your-abrp-token          # optional
```

### 3. Start the stack

```bash
docker compose up -d
```

Dashboard is available at `http://<pi-ip>:8502`

---

## Environment Variables

| Variable | Service | Description |
|---|---|---|
| `VW_USERNAME` | eudata, vwcarnet | VW account email |
| `VW_PASSWORD` | eudata, vwcarnet | VW account password |
| `MQTT_USER` | all | MQTT broker username |
| `MQTT_PASSWORD` | all | MQTT broker password |
| `ABRP_TOKEN` | eudata | ABRP user token (optional) |
| `POLL_INTERVAL_SECONDS` | eudata | Poll interval in seconds (default: 900) |

---

## MQTT Topic Structure

All topics use the pattern `<source>/vehicles/<VIN>/<suffix>` — the SQLite catcher stores every message and the dashboard queries with `LIKE '%<suffix>'`, so both `eudata/` and `vwcarnet/` sources work transparently.

```
eudata/vehicles/<VIN>/drives/primary/level       # SOC %
eudata/vehicles/<VIN>/drives/primary/range       # Range km
eudata/vehicles/<VIN>/odometer                   # Odometer km
eudata/vehicles/<VIN>/charging/state             # charging | off | invalid
eudata/vehicles/<VIN>/charging/power             # kW
eudata/vehicles/<VIN>/charging/settings/target_level    # Target SOC %
eudata/vehicles/<VIN>/charging/settings/maximum_current # A
eudata/vehicles/<VIN>/charging/type              # ac | dc
eudata/vehicles/<VIN>/garage/<VIN>/state         # parked | charging | driving
eudata/last_update                               # ISO timestamp
```

---

## Project Structure

```
myCar/
├── docker-compose.yml
├── .env                        # credentials (not committed)
│
├── eudata/                     # VW EU Data Act connector (primary)
│   ├── api.py                  # OIDC auth + portal API client
│   ├── connector.py            # polling loop → MQTT + ABRP push
│   ├── Dockerfile
│   └── requirements.txt
│
├── vwcarnet/                   # volkswagencarnet connector (fallback, disabled)
│   ├── connector.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── catcher/                    # MQTT → SQLite persistence
│   ├── catcher.py
│   └── Dockerfile
│
├── dashboard/                  # Streamlit dashboard
│   ├── app.py                  # navigation shell
│   └── pages/
│       ├── uebersicht.py       # overview
│       ├── laden.py            # charging sessions
│       └── trips.py            # trip history
│
└── mosquitto/                  # MQTT broker config
    └── mosquitto.conf
```

---

## Historical Data

All MQTT messages are stored in `database/id3_data.db` (SQLite). Historical data from the old WeConnect API (pre May 2026) is preserved — monthly statistics, trip charts, and SoH trend go back to when the stack was first deployed.

---

## Battery Health (SoH)

The dashboard estimates State of Health from real charging session data: energy delivered (calculated from charging power × time) divided by the SOC delta, compared against the 58 kWh nominal capacity. Requires sessions with ≥ 20% SOC delta. Displayed as a monthly trend.

---

## License

MIT — do whatever you want with it.

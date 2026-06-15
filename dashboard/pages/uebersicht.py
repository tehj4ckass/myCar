import os
import sqlite3
import statistics
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

DB_PATH = "/data/id3_data.db"
VIN         = os.environ.get("VIN", "YOUR_VIN_HERE")
BATTERY_KWH = 58
COST_AC     = 0.25
COST_DC     = 0.60

MONTHS_DE = {
    1: "Januar", 2: "Februar", 3: "März",     4: "April",
    5: "Mai",    6: "Juni",    7: "Juli",      8: "August",
    9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}

st.markdown("""
<style>
*, body { font-family: system-ui, -apple-system, 'Segoe UI', sans-serif !important; }
.stApp { background: #080d14 !important; color: #e8edf5; }
.block-container { padding-top: 1.25rem !important; padding-bottom: 2rem !important; }
hr { border-color: rgba(255,255,255,0.07) !important; }

.card {
    background: #0e1520;
    border-radius: 13px;
    padding: 22px 24px;
    border: 1px solid rgba(255,255,255,0.04);
    box-shadow: 0 4px 24px rgba(0,0,0,0.25);
    height: 100%;
    display: flex;
    flex-direction: column;
    justify-content: center;
    transition: transform 0.18s ease, border-color 0.18s ease;
}
.card:hover { transform: translateY(-2px); border-color: rgba(255,255,255,0.09); }

.card-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: #9ca3af;
    margin-bottom: 10px;
}
.card-value {
    font-size: 2rem;
    font-weight: 700;
    line-height: 1.15;
    color: #f1f5f9;
}
.card-sub {
    font-size: 12.5px;
    color: rgba(255,255,255,0.32);
    margin-top: 7px;
    line-height: 1.45;
}

.gauge-card {
    background: #0e1520;
    border-radius: 13px;
    padding: 24px;
    border: 1px solid rgba(255,255,255,0.04);
    box-shadow: 0 4px 24px rgba(0,0,0,0.25);
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    transition: transform 0.18s ease, border-color 0.18s ease;
}
.gauge-card:hover { transform: translateY(-2px); border-color: rgba(255,255,255,0.09); }
.gauge-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: #9ca3af;
    margin-bottom: 14px;
    align-self: flex-start;
}
.gauge-sub {
    font-size: 13px;
    color: rgba(255,255,255,0.32);
    margin-top: 10px;
}

.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 13px;
    border-radius: 20px;
    font-size: 12.5px;
    font-weight: 600;
    line-height: 1;
}
.pill-green  { background: rgba(74,222,128,0.1);  color: #4ade80; border: 1px solid rgba(74,222,128,0.2); }
.pill-orange { background: rgba(255,170,0,0.1);   color: #ffaa00; border: 1px solid rgba(255,170,0,0.2); }
.pill-blue   { background: rgba(59,130,246,0.1);  color: #3b82f6; border: 1px solid rgba(59,130,246,0.2); }
.pill-gray   { background: rgba(156,163,175,0.1); color: #9ca3af; border: 1px solid rgba(156,163,175,0.2); }

.section-rule {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 22px 0 14px 0;
}
.section-rule span {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: rgba(255,255,255,0.28);
    white-space: nowrap;
}
.section-rule::after {
    content: '';
    flex: 1;
    height: 1px;
    background: rgba(255,255,255,0.07);
}

/* Tabs styling */
[data-testid="stTabs"] [data-testid="stTab"] {
    background: transparent !important;
    border-radius: 8px 8px 0 0 !important;
    color: #9ca3af !important;
    font-size: 13px !important;
    font-weight: 600 !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: #f1f5f9 !important;
    border-bottom: 2px solid #3b82f6 !important;
}

.stButton > button {
    background: rgba(59,130,246,0.1) !important;
    color: #3b82f6 !important;
    border: 1px solid rgba(59,130,246,0.2) !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    transition: all 0.15s !important;
    padding: 6px 14px !important;
}
.stButton > button:hover {
    background: rgba(59,130,246,0.2) !important;
    border-color: rgba(59,130,246,0.35) !important;
}
.stCaption { color: rgba(255,255,255,0.22) !important; font-size: 11px !important; }
[data-testid="stAlert"] { border-radius: 10px !important; }
</style>
""", unsafe_allow_html=True)

st_autorefresh(interval=300_000, key="auto_refresh")


@st.cache_resource
def get_conn():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)


def latest(topic_suffix: str):
    try:
        row = get_conn().execute(
            "SELECT payload, timestamp FROM messages WHERE topic LIKE ? ORDER BY timestamp DESC LIMIT 1",
            (f"%{topic_suffix}",),
        ).fetchone()
        return (row[0], row[1]) if row else (None, None)
    except Exception:
        return (None, None)


def val(v, fmt=None, fallback="—"):
    if v is None:
        return fallback
    try:
        return fmt(v) if fmt else v
    except Exception:
        return fallback


def card(label, value, sub="", color="#f1f5f9"):
    sub_html = f'<div class="card-sub">{sub}</div>' if sub else ""
    return f"""
    <div class="card">
        <div class="card-label">{label}</div>
        <div class="card-value" style="color:{color};">{value}</div>
        {sub_html}
    </div>"""


def gauge_card(label, pct, sub=""):
    pct = max(0, min(100, float(pct)))
    color = "#4ade80" if pct > 20 else "#ffaa00" if pct > 10 else "#ef4444"

    r = 46
    circ = 2 * 3.14159265 * r
    arc  = circ * 0.75
    gap  = circ - arc
    filled = pct / 100 * arc

    svg = f"""
    <svg viewBox="0 0 120 110" style="width:100%;max-width:190px;height:auto;display:block;margin:0 auto;">
      <circle cx="60" cy="62" r="{r}" fill="none"
        stroke="rgba(255,255,255,0.06)" stroke-width="11" stroke-linecap="round"
        stroke-dasharray="{arc:.2f} {gap:.2f}" transform="rotate(-225 60 62)"/>
      <circle cx="60" cy="62" r="{r}" fill="none"
        stroke="{color}" stroke-width="11" stroke-linecap="round"
        stroke-dasharray="{filled:.2f} {circ - filled:.2f}" transform="rotate(-225 60 62)"/>
      <text x="60" y="57" text-anchor="middle"
        fill="{color}" font-size="26" font-weight="700"
        font-family="system-ui,-apple-system,sans-serif">{int(pct)}%</text>
      <text x="60" y="72" text-anchor="middle"
        fill="rgba(255,255,255,0.28)" font-size="8" font-weight="600"
        font-family="system-ui,-apple-system,sans-serif" letter-spacing="0.12em">AKKU</text>
    </svg>"""

    sub_html = f'<div class="gauge-sub">{sub}</div>' if sub else ""
    return f"""
    <div class="gauge-card">
        <div class="gauge-label">{label}</div>
        {svg}
        {sub_html}
    </div>"""


def format_month(m: str) -> str:
    y, mo = int(m[:4]), int(m[5:7])
    return f"{MONTHS_DE[mo]} {y}"


@st.cache_data(ttl=300)
def monthly_stats(n: int = 6) -> list:
    conn = get_conn()

    # km driven per month: MAX(odometer) – MIN(odometer)
    odo_rows = conn.execute("""
        SELECT strftime('%Y-%m', timestamp) AS month,
               MIN(CAST(payload AS REAL))   AS first_odo,
               MAX(CAST(payload AS REAL))   AS last_odo
        FROM messages
        WHERE topic LIKE '%/odometer' AND CAST(payload AS REAL) > 0
        GROUP BY month ORDER BY month DESC LIMIT ?
    """, (n,)).fetchall()
    km_by_month = {r[0]: max(0.0, (r[2] or 0) - (r[1] or 0)) for r in odo_rows}

    # Trip count + driving energy per month (state transitions + SOC at trip boundaries)
    DRIVING_STATES_LOWER = {"driving", "ignition_on"}
    state_rows = conn.execute("""
        SELECT timestamp, strftime('%Y-%m', timestamp) AS month, payload
        FROM messages WHERE topic LIKE '%' || ? || '/state'
        ORDER BY timestamp ASC
    """, (VIN,)).fetchall()

    def _soc_at(t):
        r = conn.execute(
            "SELECT CAST(payload AS REAL) FROM messages "
            "WHERE topic LIKE '%drives/primary/level' AND payload != '' "
            "AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1", (t,)
        ).fetchone()
        return r[0] if r and r[0] else None

    trips_by_month: dict = {}
    drive_energy_by_month: dict = {}
    prev_state = None
    trip_start_ts = None
    trip_month = None
    for ts_str, month, raw_state in state_rows:
        state = (raw_state or "").lower().strip()
        if not state:
            continue
        if prev_state in (None, "parked", "charging") and state in DRIVING_STATES_LOWER:
            trip_start_ts = ts_str
            trip_month    = month
        elif prev_state in DRIVING_STATES_LOWER and state in ("parked", "charging") and trip_start_ts:
            trips_by_month[month] = trips_by_month.get(month, 0) + 1
            soc_s = _soc_at(trip_start_ts)
            soc_e = _soc_at(ts_str)
            if soc_s and soc_e and soc_s > soc_e:
                m = trip_month or month
                drive_energy_by_month[m] = (
                    drive_energy_by_month.get(m, 0) + (soc_s - soc_e) * BATTERY_KWH / 100
                )
            trip_start_ts = None
        prev_state = state

    # Charging sessions: energy, cost, SoH estimates
    charge_rows = conn.execute("""
        SELECT timestamp, topic, payload FROM messages
        WHERE topic LIKE '%charging/state'
           OR topic LIKE '%charging/power'
           OR topic LIKE '%drives/primary/level'
        ORDER BY timestamp ASC
    """).fetchall()

    ACTIVE = (
        "charging", "charge",
        "charge_state_charging", "charge_state_charging_hv_battery",
        "charge_state_conservation_charging", "charge_state_conserving",
    )
    energy_by_month: dict = {}
    cost_by_month:   dict = {}
    soh_samples:     dict = {}

    session_start     = None
    session_start_soc = None
    last_soc          = None
    power_pts:        list = []
    prev              = None

    for ts_str, topic, payload in charge_rows:
        if "charging/state" in topic:
            state = (payload or "").strip().lower()
            if prev not in ACTIVE and state in ACTIVE:
                session_start     = ts_str
                session_start_soc = last_soc
                power_pts         = []
            elif prev in ACTIVE and state not in ACTIVE and session_start:
                if session_start_soc is not None and last_soc is not None:
                    delta = last_soc - session_start_soc
                    if delta > 0:
                        month  = ts_str[:7]
                        energy = delta * BATTERY_KWH / 100
                        
                        max_p = max((p for _, p in power_pts), default=0)
                        rate  = COST_DC if max_p > 11.0 else COST_AC
                        cost  = energy * rate
                        
                        energy_by_month[month] = energy_by_month.get(month, 0) + energy
                        cost_by_month[month]   = cost_by_month.get(month, 0) + cost

                        # SoH estimate: need ≥3 power readings for reliable energy calc
                        if delta >= 20 and len(power_pts) >= 3:
                            try:
                                s_dt  = pd.to_datetime(session_start, format="ISO8601", utc=True)
                                e_dt  = pd.to_datetime(ts_str, format="ISO8601", utc=True)
                                dur_h = (e_dt - s_dt).total_seconds() / 3600
                                if dur_h > 0:
                                    pts = sorted(power_pts, key=lambda x: x[0])
                                    pts.append((e_dt, 0.0))
                                    energy_kwh = 0.0
                                    for i in range(1, len(pts)):
                                        t0, p0 = pts[i-1]
                                        t1, _  = pts[i]
                                        dt_h = (t1 - t0).total_seconds() / 3600.0
                                        if dt_h > 0:
                                            energy_kwh += p0 * dt_h

                                    max_p = max(p for _, p in power_pts)
                                    eff   = 0.94 if max_p > 11 else 0.88
                                    cap   = energy_kwh * eff / (delta / 100)
                                    # cap must be physically plausible (±15% of nominal)
                                    if BATTERY_KWH * 0.75 < cap < BATTERY_KWH * 1.15:
                                        soh_samples.setdefault(month, []).append(
                                            cap / BATTERY_KWH * 100
                                        )
                            except Exception:
                                pass

                session_start     = None
                session_start_soc = None
                power_pts         = []
            prev = state

        elif "charging/power" in topic and session_start is not None:
            try:
                pwr = float(payload)
                if pwr > 0:
                    power_pts.append((pd.to_datetime(ts_str, format="ISO8601", utc=True), pwr))
            except Exception:
                pass

        elif "drives/primary/level" in topic:
            try:
                last_soc = float(payload)
            except Exception:
                pass

    soh_by_month = {m: sum(v) / len(v) for m, v in soh_samples.items()}

    all_months = sorted(
        set(list(km_by_month) + list(trips_by_month) + list(energy_by_month) + list(drive_energy_by_month)),
        reverse=True,
    )[:n]

    result = []
    for m in all_months:
        km       = km_by_month.get(m, 0)
        kwh      = energy_by_month.get(m, 0)
        drive_kwh = drive_energy_by_month.get(m, 0)
        consumption = (drive_kwh / km * 100) if km > 0 and drive_kwh > 0 else None
        soh = soh_by_month.get(m)
        result.append({
            "month":       m,
            "km":          round(km, 0)          if km  > 0   else None,
            "trips":       trips_by_month.get(m),
            "energy_kwh":  round(kwh, 1)          if kwh > 0   else None,
            "cost":        round(cost_by_month.get(m, 0), 2) if cost_by_month.get(m) else None,
            "consumption": round(consumption, 1)  if consumption else None,
            "soh":         round(soh, 1)          if soh        else None,
        })
    return result


# ── Fetch live data ───────────────────────────────────────────────────────────
name,         _ = latest("/name")
model,        _ = latest("/model")
conn_state,   _ = latest("garage/YOUR_VIN_HERE/connection_state")
last_update,  _ = latest("last_update")
batt_level,   _ = latest("drives/primary/level")
batt_range,   _ = latest("drives/primary/range")
odometer,     _ = latest("/odometer")
vehicle_state,_ = latest("garage/YOUR_VIN_HERE/state")
charge_state, _ = latest("charging/state")
charge_power, _ = latest("charging/power")
target_lvl,   _ = latest("charging/settings/target_level")
max_current,  _ = latest("charging/settings/maximum_current")
est_done,     _ = latest("charging/estimated_date_reached")

lvl        = float(batt_level) if batt_level else 0.0
is_charging = charge_state not in (None, "off", "invalid", "")

# ── Header ────────────────────────────────────────────────────────────────────
h_left, h_right = st.columns([1, 1])
with h_left:
    vehicle_label = name or "VW ID.3"
    if conn_state == "reachable":
        pill = '<span class="status-pill pill-green">● Online</span>'
    elif is_charging:
        pill = '<span class="status-pill pill-orange">⚡ Lädt</span>'
    else:
        pill = '<span class="status-pill pill-gray">○ Offline</span>'
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;padding:4px 0 16px 0;">'
        f'<span style="font-size:1.6rem;font-weight:700;color:#f1f5f9;">⚡ {vehicle_label}</span>'
        f'{pill}</div>',
        unsafe_allow_html=True,
    )
with h_right:
    btn_col, cap_col = st.columns([1, 4])
    with btn_col:
        if st.button("↺ Refresh", help="Daten aktualisieren"):
            st.rerun()
    with cap_col:
        if last_update:
            st.caption(f"Letzte Aktualisierung: {last_update[:19]}")

# ── Row 1: Gauge + Info Cards ─────────────────────────────────────────────────
c_gauge, c_range, c_odo, c_state = st.columns([1.6, 1, 1, 1])

with c_gauge:
    range_sub = val(batt_range, lambda v: f"⬤ {float(v):.0f} km Reichweite")
    st.markdown(gauge_card("🔋 Akkustand", lvl, sub=range_sub), unsafe_allow_html=True)

with c_range:
    st.markdown(
        card("🛣️ Reichweite",
             val(batt_range, lambda v: f"{float(v):.0f} km"),
             color="#3b82f6"),
        unsafe_allow_html=True,
    )

with c_odo:
    st.markdown(
        card("📏 Kilometerstand",
             val(odometer, lambda v: f"{float(v):,.0f} km".replace(",", ".")),
             sub="Gesamte Lebenszeit"),
        unsafe_allow_html=True,
    )

with c_state:
    state_map = {
        "parked":       ("🅿️ Geparkt",    "#9ca3af"),
        "driving":      ("🚗 Unterwegs",  "#4ade80"),
        "charging":     ("⚡ Lädt",        "#ffaa00"),
        "ignition_on":  ("🔑 Zündung an", "#3b82f6"),
    }
    s_val, s_col = state_map.get(vehicle_state or "", (f"○ {vehicle_state or '—'}", "#9ca3af"))
    st.markdown(card("🚦 Status", s_val, color=s_col), unsafe_allow_html=True)

st.write("")

# ── Row 2: Charging ───────────────────────────────────────────────────────────
st.markdown('<div class="section-rule"><span>Aktuell</span></div>', unsafe_allow_html=True)

c_chg, c_empty = st.columns([2, 1])

_CHARGE_LABELS = {
    "charging": "⚡ Lädt", "off": "Inaktiv", "invalid": "—",
    "charge_state_charging": "⚡ Lädt",
    "charge_state_charging_hv_battery": "⚡ Lädt",
    "charge_state_conservation_charging": "⚡ Erhaltung",
    "charge_state_conserving": "⚡ Erhaltung",
    "charge_state_ready_for_charging": "Bereit",
    "charge_state_not_ready_for_charging": "Inaktiv",
    "charge_state_charge_purpose_reached_conservation": "Ziel erreicht",
    "charge_state_charge_purpose_reached_not_charging": "Ziel erreicht",
    "charge_state_error": "Fehler",
}
_CURRENT_MAP_UI = {"max_charge_current_ac_maximum": "16", "max_charge_current_ac_reduced": "8"}
def _resolve_amp(v):
    if v is None: return None
    try: return float(v)
    except (ValueError, TypeError):
        m = _CURRENT_MAP_UI.get((v or "").lower()); return float(m) if m else None

with c_chg:
    pwr     = val(charge_power, lambda v: f"{float(v):.1f} kW")
    tgt     = val(target_lvl,   lambda v: f"Ziel {float(v):.0f}%")
    cs      = _CHARGE_LABELS.get((charge_state or "").lower(), "—")
    _amp    = _resolve_amp(max_current)
    chg_sub = f"{tgt} · Max {_amp:.0f} A" if _amp is not None else tgt
    if est_done and is_charging:
        try:
            done_dt   = datetime.fromisoformat(est_done)
            mins_left = int((done_dt - datetime.now(timezone.utc)).total_seconds() / 60)
            if mins_left > 0:
                label = f"{mins_left//60}h {mins_left%60}min" if mins_left >= 60 else f"{mins_left} min"
                chg_sub += f" · ⏱ fertig in {label}"
        except Exception:
            pass
    chg_color = "#ffaa00" if is_charging else "#9ca3af"
    st.markdown(card("⚡ Laden", f"{cs} · {pwr}", sub=chg_sub, color=chg_color), unsafe_allow_html=True)



st.write("")

# ── Row 3: Monatliche Statistiken ─────────────────────────────────────────────
st.markdown('<div class="section-rule"><span>Monatliche Statistiken</span></div>', unsafe_allow_html=True)

stats = monthly_stats()

if stats:
    stats_asc = list(reversed(stats))
    tab_labels = [format_month(s["month"]) for s in stats_asc]
    tabs = st.tabs(tab_labels)

    for tab, s in zip(tabs, stats_asc):
        with tab:
            c1, c2, c3, c4, c5 = st.columns(5)

            with c1:
                st.markdown(
                    card("🛣️ Gefahren",
                         f"{int(s['km']):,} km".replace(",", ".") if s["km"] else "—",
                         sub="In diesem Monat"),
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    card("🗺️ Trips",
                         str(s["trips"]) if s["trips"] else "—",
                         sub="Fahrten im Monat"),
                    unsafe_allow_html=True,
                )
            with c3:
                st.markdown(
                    card("💶 Ladekosten",
                         f"{s['cost']:.2f} €" if s["cost"] else "—",
                         sub=f"{s['energy_kwh']:.1f} kWh geladen" if s["energy_kwh"] else "",
                         color="#ffaa00" if s["cost"] else "#f1f5f9"),
                    unsafe_allow_html=True,
                )
            with c4:
                sub_v = f"{s['energy_kwh']:.1f} kWh / {int(s['km']):,} km".replace(",", ".") \
                        if s["energy_kwh"] and s["km"] else ""
                st.markdown(
                    card("⚡ Ø Verbrauch",
                         f"{s['consumption']:.1f} kWh/100km" if s["consumption"] else "—",
                         sub=sub_v,
                         color="#3b82f6" if s["consumption"] else "#f1f5f9"),
                    unsafe_allow_html=True,
                )
            with c5:
                soh_color = (
                    "#4ade80" if (s["soh"] or 0) > 90
                    else "#ffaa00" if (s["soh"] or 0) > 80
                    else "#ef4444" if s["soh"]
                    else "#9ca3af"
                )
                st.markdown(
                    card("🏥 Batterie-SoH",
                         f"{s['soh']:.1f} %" if s["soh"] else "—",
                         sub="Zu wenig Ladedaten" if not s["soh"] else "",
                         color=soh_color),
                    unsafe_allow_html=True,
                )

    # ── SoH Trend Chart ───────────────────────────────────────────────────
    soh_history = [s for s in reversed(stats) if s["soh"] is not None]
    if len(soh_history) >= 2:
        st.write("")
        st.markdown('<div class="section-rule"><span>Batterie-Gesundheit Trend (Seit März 2026)</span></div>', unsafe_allow_html=True)
        import plotly.express as px
        df_soh = pd.DataFrame(soh_history)
        df_soh["Month_Label"] = df_soh["month"].apply(format_month)
        
        fig_soh = go.Figure()
        fig_soh.add_trace(go.Bar(
            y=df_soh["Month_Label"],
            x=df_soh["soh"],
            orientation="h",
            marker=dict(
                color="#00cc88",
                opacity=0.85,
                line=dict(color="#0e1520", width=1.5)
            ),
            text=df_soh["soh"].apply(lambda v: f" <b>{v:.1f}%</b>"),
            textposition="outside",
            textfont=dict(color="#00cc88", size=11),
            hovertemplate="<b>%{y}</b><br>SoH: %{x:.1f}%<extra></extra>",
            width=0.4
        ))
        fig_soh.update_layout(
            height=120 + len(df_soh) * 45,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=10, b=10, l=10, r=40), font=dict(color="#9ca3af", size=11),
            xaxis=dict(
                title="SoH (%)",
                range=[70, 100],
                gridcolor="rgba(255,255,255,0.05)",
                zeroline=False
            ),
            yaxis=dict(
                showgrid=False,
                autorange="reversed"
            )
        )
        st.plotly_chart(fig_soh, use_container_width=True)

else:
    st.info("Noch keine Monatsdaten vorhanden.")


# ── Footer ────────────────────────────────────────────────────────────────────
try:
    count = get_conn().execute("SELECT COUNT(*) FROM messages").fetchone()[0]
except Exception:
    count = 0

st.caption(
    f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')} · "
    f"Auto-Refresh alle 5 min · {count:,} Datenpunkte"
)

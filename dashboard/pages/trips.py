import os
import html
import sqlite3
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

DB_PATH = "/data/id3_data.db"
VIN = os.environ.get("VIN", "YOUR_VIN_HERE")
BATTERY_KWH = 58

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
    font-size: 11px; font-weight: 600; letter-spacing: 0.09em;
    text-transform: uppercase; color: #9ca3af; margin-bottom: 10px;
}
.card-value { font-size: 2rem; font-weight: 700; line-height: 1.15; color: #f1f5f9; }
.card-sub { font-size: 12.5px; color: rgba(255,255,255,0.32); margin-top: 7px; line-height: 1.45; }

.section-rule {
    display: flex; align-items: center; gap: 12px;
    margin: 22px 0 14px 0;
}
.section-rule span {
    font-size: 11px; font-weight: 600; letter-spacing: 0.09em;
    text-transform: uppercase; color: rgba(255,255,255,0.28); white-space: nowrap;
}
.section-rule::after { content:''; flex:1; height:1px; background:rgba(255,255,255,0.07); }

.stButton > button {
    background: rgba(59,130,246,0.1) !important; color: #3b82f6 !important;
    border: 1px solid rgba(59,130,246,0.2) !important; border-radius: 8px !important;
    font-weight: 600 !important;
}
.stButton > button:hover { background: rgba(59,130,246,0.2) !important; }
[data-testid="stAlert"] { border-radius: 10px !important; }
.stCaption { color: rgba(255,255,255,0.22) !important; font-size: 11px !important; }
[data-testid="stDataFrame"] { border-radius: 12px !important; overflow: hidden !important; }
</style>
""", unsafe_allow_html=True)

st_autorefresh(interval=300_000, key="trips_refresh")


@st.cache_resource
def get_conn():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)


def latest(suffix):
    row = get_conn().execute(
        "SELECT payload, timestamp FROM messages WHERE topic LIKE ? ORDER BY timestamp DESC LIMIT 1",
        (f"%{suffix}",),
    ).fetchone()
    return (row[0], row[1]) if row else (None, None)


def get_positions() -> pd.DataFrame:
    conn = get_conn()
    lat_rows = conn.execute(
        f"SELECT timestamp, payload FROM messages "
        f"WHERE topic = 'carconnectivity/0/garage/{VIN}/position/latitude' ORDER BY id"
    ).fetchall()
    lon_rows = conn.execute(
        f"SELECT timestamp, payload FROM messages "
        f"WHERE topic = 'carconnectivity/0/garage/{VIN}/position/longitude' ORDER BY id"
    ).fetchall()
    if not lat_rows or not lon_rows:
        return pd.DataFrame()
    records = []
    for (ts, lat), (_, lon) in zip(lat_rows, lon_rows):
        try:
            records.append({"timestamp": ts, "lat": float(lat), "lon": float(lon)})
        except (ValueError, TypeError):
            pass
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", utc=True).dt.tz_convert("Europe/Vienna")
    df["lat_r"] = df["lat"].round(5)
    df["lon_r"] = df["lon"].round(5)
    return df


DRIVING_STATES = {"driving", "ignition_on"}


def _adjust_ts(ts: str, delta_s: int) -> str:
    """Return ISO timestamp string shifted by delta_s seconds."""
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return ts
    from datetime import timedelta
    dt2 = dt + timedelta(seconds=delta_s)
    return dt2.isoformat()


def _ts_diff_seconds(ts_ref: str, ts_other: str) -> float:
    """Return abs(ts_ref - ts_other) in seconds; large number on parse error."""
    try:
        a = datetime.fromisoformat(ts_ref)
        b = datetime.fromisoformat(ts_other)
        if a.tzinfo is None and b.tzinfo is not None:
            b = b.replace(tzinfo=None)
        elif a.tzinfo is not None and b.tzinfo is None:
            a = a.replace(tzinfo=None)
        return abs((a - b).total_seconds())
    except Exception:
        return 99999


def detect_trips():
    rows = get_conn().execute(
        f"SELECT timestamp, payload FROM messages "
        f"WHERE topic LIKE '%{VIN}/state' ORDER BY timestamp"
    ).fetchall()
    trips, trip_start, prev_state = [], None, None

    for ts_str, raw_state in rows:
        state = raw_state.strip()
        if not state:
            continue  # skip empty state updates
        if prev_state in (None, "parked", "charging") and state in DRIVING_STATES:
            trip_start = ts_str
        elif prev_state in DRIVING_STATES and state in ("parked", "charging") and trip_start:
            conn = get_conn()

            def odo_at(t, _conn=conn):
                # Try to find a reading within 2 seconds of t first (simultaneous poll),
                # then fall back to last-before-t. If that value is >5 min stale, use
                # first-after-t instead (avoids inheriting end-of-previous-trip odometer).
                near = _conn.execute(
                    f"SELECT payload, timestamp FROM messages WHERE topic LIKE '%{VIN}/odometer' "
                    f"AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp ASC LIMIT 1",
                    (_adjust_ts(t, -2), _adjust_ts(t, 2)),
                ).fetchone()
                if near:
                    return float(near[0])
                before = _conn.execute(
                    f"SELECT payload, timestamp FROM messages WHERE topic LIKE '%{VIN}/odometer' "
                    f"AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1", (t,)
                ).fetchone()
                if before:
                    age_s = _ts_diff_seconds(t, before[1])
                    if age_s < 300:  # fresh enough (<5 min)
                        return float(before[0])
                # Stale before-reading: use first reading after t
                after = _conn.execute(
                    f"SELECT payload FROM messages WHERE topic LIKE '%{VIN}/odometer' "
                    f"AND timestamp > ? ORDER BY timestamp ASC LIMIT 1", (t,)
                ).fetchone()
                return float(after[0]) if after else (float(before[0]) if before else None)

            def soc_at(t, _conn=conn):
                r = _conn.execute(
                    "SELECT payload FROM messages WHERE topic LIKE '%drives/primary/level' "
                    "AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1", (t,)
                ).fetchone()
                return float(r[0]) if r and r[0] else None

            def pos_at(t):
                lat = conn.execute(
                    f"SELECT payload FROM messages WHERE topic = 'carconnectivity/0/garage/{VIN}/position/latitude' "
                    f"AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1", (t,)
                ).fetchone()
                lon = conn.execute(
                    f"SELECT payload FROM messages WHERE topic = 'carconnectivity/0/garage/{VIN}/position/longitude' "
                    f"AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1", (t,)
                ).fetchone()
                try:
                    return (float(lat[0]), float(lon[0])) if lat and lon and lat[0] and lon[0] else (None, None)
                except (ValueError, TypeError):
                    return (None, None)

            def city_at(t):
                r = conn.execute(
                    "SELECT payload FROM messages WHERE topic LIKE '%position_location/city' "
                    "AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1", (t,)
                ).fetchone()
                return r[0] if r else None

            def _parse_ts(ts):
                dt = datetime.fromisoformat(ts)
                return dt.replace(tzinfo=None) if dt.tzinfo else dt

            start_dt  = _parse_ts(trip_start)
            end_dt    = _parse_ts(ts_str)
            duration  = end_dt - start_dt
            odo_start = odo_at(trip_start)
            odo_end   = odo_at(ts_str)
            distance  = round(odo_end - odo_start, 1) if odo_start and odo_end else None
            soc_start = soc_at(trip_start)
            soc_end   = soc_at(ts_str)
            energy    = round((soc_start - soc_end) * BATTERY_KWH / 100, 2) if soc_start and soc_end else None
            efficiency = round(energy / distance * 100, 1) if energy and distance and distance > 0 else None
            lat_s, lon_s = pos_at(trip_start)
            lat_e, lon_e = pos_at(ts_str)

            trips.append({
                "start": start_dt, "end": end_dt, "duration": duration,
                "distance_km": distance, "energy_kwh": energy, "efficiency": efficiency,
                "soc_start": soc_start, "soc_end": soc_end,
                "lat_start": lat_s, "lon_start": lon_s,
                "lat_end": lat_e, "lon_end": lon_e,
                "city_start": city_at(trip_start),
                "city_end":   city_at(ts_str),
            })
            trip_start = None
        prev_state = state
    return trips


def card(label, value, sub="", color="#f1f5f9"):
    label = html.escape(str(label)) if label is not None else ""
    value = html.escape(str(value)) if value is not None else ""
    sub = html.escape(str(sub)) if sub is not None else ""
    sub_html = f'<div class="card-sub">{sub}</div>' if sub else ""
    return f"""
    <div class="card">
        <div class="card-label">{label}</div>
        <div class="card-value" style="color:{color};">{value}</div>
        {sub_html}
    </div>"""


# ── Header ────────────────────────────────────────────────────────────────────
h1, h2 = st.columns([9, 1])
with h1:
    st.markdown(
        '<h1 style="font-size:1.6rem;font-weight:700;color:#f1f5f9;padding:4px 0 16px 0;">🗺️ Trips</h1>',
        unsafe_allow_html=True,
    )
with h2:
    st.write("")
    if st.button("↺"):
        st.rerun()

# ── Data ──────────────────────────────────────────────────────────────────────
vehicle_state, _ = latest(f"{VIN}/state")
odometer,      _ = latest("/odometer")
trips            = detect_trips()
positions        = get_positions()

# Status banner
state_banners = {
    "driving":      ("🚗 Fahrzeug ist gerade unterwegs", "success"),
    "parked":       ("🅿️ Fahrzeug geparkt", "info"),
    "charging":     ("⚡ Fahrzeug lädt", "info"),
    "ignition_on":  ("🔑 Zündung an", "info"),
}
msg, kind = state_banners.get(vehicle_state or "", (f"○ Status: {vehicle_state or 'unbekannt'}", "info"))
getattr(st, kind)(msg)

# ── Quick Stats ───────────────────────────────────────────────────────────────
st.markdown('<div class="section-rule"><span>Statistik</span></div>', unsafe_allow_html=True)

q1, q2, q3, q4 = st.columns(4)
total_dist = sum(t["distance_km"] or 0 for t in trips)
total_kwh  = sum(t["energy_kwh"] or 0 for t in trips)

with q1:
    odo_val = f"{float(odometer)/1000:.1f} Tkm" if odometer else "—"
    st.markdown(card("📏 Gesamtkilometer", odo_val, sub="Gesamte Lebenszeit"), unsafe_allow_html=True)
with q2:
    st.markdown(card("🗺️ Trips erkannt", str(len(trips)), sub="Seit März 2026", color="#3b82f6"), unsafe_allow_html=True)
with q3:
    st.markdown(card("📐 Gefahren gesamt", f"{total_dist:.0f} km" if trips else "—", sub="Seit März 2026"), unsafe_allow_html=True)
with q4:
    st.markdown(card("⚡ Verbrauch gesamt", f"{total_kwh:.1f} kWh" if trips else "—", sub="Seit März 2026", color="#ffaa00"), unsafe_allow_html=True)

# ── Karte ─────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-rule"><span>Standort-Karte</span></div>', unsafe_allow_html=True)

if not positions.empty:
    stops   = positions.drop_duplicates(subset=["lat_r", "lon_r"]).copy()
    lat_c   = positions["lat"].mean()
    lon_c   = positions["lon"].mean()
    zoom    = 11 if (positions["lat"].max() - positions["lat"].min()) > 0.05 else 13

    fig_map = go.Figure()

    if len(positions) > 1:
        fig_map.add_trace(go.Scattermap(
            lat=positions["lat"].tolist(), lon=positions["lon"].tolist(),
            mode="lines", line=dict(width=2, color="rgba(68,136,255,0.35)"),
            hoverinfo="skip", name="Pfad", showlegend=False,
        ))

    fig_map.add_trace(go.Scattermap(
        lat=stops["lat"].tolist(), lon=stops["lon"].tolist(),
        mode="markers",
        marker=dict(size=7, color="#4488ff", opacity=0.65),
        text=stops["timestamp"].dt.strftime("%d.%m.%Y %H:%M").tolist(),
        hovertemplate="<b>%{text}</b><br>%{lat:.5f}, %{lon:.5f}<extra></extra>",
        name="Positionen",
    ))

    latest_pos = positions.sort_values("timestamp").iloc[-1]
    fig_map.add_trace(go.Scattermap(
        lat=[latest_pos["lat"]], lon=[latest_pos["lon"]],
        mode="markers+text",
        marker=dict(size=15, color="#00cc88"),
        text=["🚗 Aktuell"], textposition="top right",
        textfont=dict(size=13, color="#00cc88"),
        hovertemplate=f"<b>Aktuell</b><br>{latest_pos['timestamp'].strftime('%d.%m. %H:%M')}<extra></extra>",
        name="Aktueller Standort",
    ))

    for i, trip in enumerate(trips):
        if trip["lat_start"] and trip["lat_end"]:
            fig_map.add_trace(go.Scattermap(
                lat=[trip["lat_start"], trip["lat_end"]],
                lon=[trip["lon_start"], trip["lon_end"]],
                mode="markers",
                marker=dict(size=11, color=["#ffaa00", "#ff4444"]),
                text=[f"Start Trip {i+1}", f"Ende Trip {i+1}"],
                hovertemplate="%{text}<extra></extra>",
                name=f"Trip {i+1}",
                showlegend=len(trips) <= 5,
            ))

    fig_map.update_layout(
        map=dict(style="open-street-map", center=dict(lat=lat_c, lon=lon_c), zoom=zoom),
        height=480, margin=dict(t=0, b=0, l=0, r=0),
        legend=dict(bgcolor="rgba(14,21,32,0.85)", bordercolor="rgba(255,255,255,0.08)",
                    borderwidth=1, font=dict(color="#9ca3af")),
    )
    st.plotly_chart(fig_map, use_container_width=True)

    city, _     = latest("position_location/city")
    road, _     = latest("position_location/road")
    house, _    = latest("position_location/house_number")
    postcode, _ = latest("position_location/postcode")
    if city:
        addr = f"{road} {house}, {postcode} {city}" if road else f"{postcode} {city}"
        st.caption(f"📌 Aktueller Standort: {addr} · {len(stops)} einzigartige Positionen")
else:
    st.info("Noch keine GPS-Daten vorhanden.")

# ── Trip-Liste ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-rule"><span>Gefahrene Trips (Seit März 2026)</span></div>', unsafe_allow_html=True)

if trips:
    trip_rows = []
    for t in reversed(trips):
        dur_m   = int(t["duration"].total_seconds() / 60)
        dur_str = f"{dur_m//60}h {dur_m%60:02d}min" if dur_m >= 60 else f"{dur_m} min"
        trip_rows.append({
            "Datum":     t["start"].strftime("%d.%m.%Y"),
            "Start":     t["start"].strftime("%H:%M"),
            "Ende":      t["end"].strftime("%H:%M"),
            "Dauer":     dur_str,
            "Distanz":   f"{t['distance_km']:.1f} km"       if t["distance_km"] else "—",
            "Verbrauch": f"{t['energy_kwh']:.1f} kWh"       if t["energy_kwh"]  else "—",
            "Effizienz": f"{t['efficiency']:.1f} kWh/100km" if t["efficiency"]  else "—",
            "Von":       t["city_start"] or "—",
            "Nach":      t["city_end"]   or "—",
        })
    st.dataframe(pd.DataFrame(trip_rows), use_container_width=True, hide_index=True)

    if len(trips) >= 2:
        df_trips = pd.DataFrame(trips)
        df_trips["Date_raw"] = df_trips["start"].dt.date
        
        # Distanz & Verbrauch kombiniert
        dist_day = df_trips.groupby("Date_raw")["distance_km"].sum().reset_index()
        kwh_day  = df_trips.groupby("Date_raw")["energy_kwh"].sum().reset_index()
        combined = dist_day.merge(kwh_day, on="Date_raw", how="left")
        combined = combined.sort_values("Date_raw")
        combined["Date"] = combined["Date_raw"].apply(lambda x: x.strftime("%d.%m."))

        if not combined.empty:
            fig_c = go.Figure()
            fig_c.add_trace(go.Bar(
                x=combined["Date"], y=combined["distance_km"],
                name="Distanz (km)",
                marker=dict(color="#4488ff", opacity=0.8),
                yaxis="y1",
                text=combined["distance_km"].apply(lambda v: f"{v:.0f}"),
                textposition="outside",
                textfont=dict(color="#4488ff", size=10),
                hovertemplate="<b>%{x}</b><br>%{y:.0f} km<extra></extra>",
            ))
            fig_c.add_trace(go.Scatter(
                x=combined["Date"], y=combined["energy_kwh"],
                name="Verbrauch (kWh)",
                mode="lines+markers+text",
                line=dict(color="#00cc88", width=2.5),
                marker=dict(size=7, color="#00cc88", line=dict(color="#0e1520", width=1.5)),
                text=combined["energy_kwh"].apply(lambda v: f"{v:.1f}" if pd.notnull(v) else ""),
                textposition="top center",
                textfont=dict(color="#00cc88", size=10),
                yaxis="y2",
                hovertemplate="<b>%{x}</b><br>%{y:.1f} kWh<extra></extra>",
            ))
            fig_c.update_layout(
                height=320,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=10, b=0, l=0, r=0),
                font=dict(color="#9ca3af", size=11),
                xaxis=dict(
                    type="category",
                    categoryorder="array",
                    categoryarray=combined["Date"].tolist(),
                    showgrid=False
                ),
                yaxis=dict(title="km", gridcolor="rgba(255,255,255,0.05)", zeroline=False, side="left"),
                yaxis2=dict(title="kWh", overlaying="y", side="right", showgrid=False, zeroline=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                            font=dict(color="#9ca3af", size=11)),
                barmode="group",
            )
            st.markdown('<div style="color:#9ca3af; font-size:0.8rem; margin-top:20px; margin-bottom:4px;">Distanz pro Tag &amp; Verbrauch je Tag (Seit März 2026)</div>', unsafe_allow_html=True)
            st.plotly_chart(fig_c, use_container_width=True)



        # ── Usage Profile & Weekday Analysis ──────────────────────────────────
        st.write("")
        st.markdown('<div class="section-rule"><span>Nutzungsprofil (Seit März 2026)</span></div>', unsafe_allow_html=True)
        
        weekday_data = pd.DataFrame([
            {"Weekday": t["start"].strftime("%A"), "KM": t["distance_km"] or 0}
            for t in trips
        ])
        if not weekday_data.empty:
            order    = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            de_order = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
            weekday_data["Wochentag"] = weekday_data["Weekday"].map(dict(zip(order, de_order)))
            dist_wd = weekday_data.groupby("Wochentag")["KM"].sum().reindex(de_order).fillna(0)
            fig_wd = go.Figure(go.Bar(
                x=dist_wd.index, y=dist_wd.values,
                marker=dict(color="#3b82f6", opacity=0.8),
                text=[f"{v:.0f}" if v > 0 else "" for v in dist_wd.values],
                textposition="outside",
                textfont=dict(color="#3b82f6", size=10),
                hovertemplate="<b>%{x}</b><br>%{y:.0f} km gesamt<extra></extra>"
            ))
            fig_wd.update_layout(
                height=240, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=8, b=0), font=dict(color="#9ca3af", size=11),
                yaxis=dict(title="km", gridcolor="rgba(255,255,255,0.05)"),
                xaxis=dict(
                    type="category",
                    categoryorder="array",
                    categoryarray=de_order,
                    showgrid=False
                ),
            )
            st.caption("Kilometer nach Wochentag (Seit März 2026)")
            st.plotly_chart(fig_wd, use_container_width=True)

else:
    st.info("Noch keine Trips erkannt. Sobald das Fahrzeug fährt und wieder parkt, erscheinen die Trips hier.")


st.caption(f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')} · Auto-Refresh alle 5 min")

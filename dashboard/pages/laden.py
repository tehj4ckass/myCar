import os
import sqlite3
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from streamlit_autorefresh import st_autorefresh

DB_PATH = "/data/id3_data.db"
VIN = os.environ.get("VIN", "YOUR_VIN_HERE")
BATTERY_KWH = 58
COST_AC = 0.25
COST_DC = 0.60

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

[data-testid="metric-container"] {
    background: #0e1520 !important;
    border-radius: 12px !important;
    padding: 16px 20px !important;
    border: 1px solid rgba(255,255,255,0.04) !important;
}
[data-testid="metric-container"] > label {
    color: #9ca3af !important; font-size: 11px !important;
    font-weight: 600 !important; text-transform: uppercase !important;
    letter-spacing: 0.09em !important;
}
[data-testid="stMetricValue"] > div {
    font-size: 1.65rem !important; font-weight: 700 !important; color: #f1f5f9 !important;
}

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

st_autorefresh(interval=300_000, key="laden_refresh")


@st.cache_resource
def get_conn():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)


@st.cache_data(ttl=2)
def latest(suffix):
    """
    Fetch the latest payload and timestamp for a given topic suffix.
    Cached for 2 seconds to debounce rapid Streamlit UI interactions and prevent DB query spikes.
    """
    row = get_conn().execute(
        "SELECT payload, timestamp FROM messages WHERE topic LIKE ? ORDER BY timestamp DESC LIMIT 1",
        (f"%{suffix}",),
    ).fetchone()
    return (row[0], row[1]) if row else (None, None)


@st.cache_data(ttl=2)
def history(suffix, limit=2000):
    """
    Fetch historical data for a given topic suffix.
    Cached for 2 seconds to debounce rapid Streamlit UI interactions.
    """
    rows = get_conn().execute(
        "SELECT timestamp, payload FROM messages WHERE topic LIKE ? ORDER BY id ASC LIMIT ?",
        (f"%{suffix}", limit),
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "value"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", utc=True).dt.tz_convert("Europe/Vienna")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["value"])


_CHARGING_STATE_VALUES = {
    "charging", "charge",
    "charge_state_charging", "charge_state_charging_hv_battery",
    "charge_state_conservation_charging", "charge_state_conserving",
}

def _is_active(state: str) -> bool:
    return state.strip().lower() in _CHARGING_STATE_VALUES


def _build_session(conn, session_start: str, ts_str: str) -> dict | None:
    def soc_at(t):
        r = conn.execute(
            "SELECT payload FROM messages WHERE topic LIKE '%drives/primary/level' "
            "AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1", (t,),
        ).fetchone()
        return float(r[0]) if r else None

    def _parse_ts(ts):
        dt = datetime.fromisoformat(ts)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt

    start_dt = _parse_ts(session_start)
    end_dt   = _parse_ts(ts_str)
    duration = end_dt - start_dt
    if duration.total_seconds() < 60:
        return None

    s_soc = soc_at(session_start)
    e_soc = soc_at(ts_str)
    energy = round((e_soc - s_soc) * BATTERY_KWH / 100, 2) if s_soc and e_soc else None

    pwr_rows = conn.execute(
        f"SELECT payload FROM messages WHERE topic LIKE '%{VIN}/charging/power' "
        f"AND timestamp BETWEEN ? AND ?", (session_start, ts_str),
    ).fetchall()
    avg_pwr = (
        sum(float(r[0]) for r in pwr_rows if r[0]) / len(pwr_rows)
        if pwr_rows else None
    )

    type_rows = conn.execute(
        f"SELECT payload FROM messages WHERE topic LIKE '%{VIN}/charging/type' "
        f"AND timestamp BETWEEN ? AND ?", (session_start, ts_str),
    ).fetchall()
    def _norm_type(v):
        v = v.strip().lower()
        if v.startswith("charge_type_"):
            v = v[len("charge_type_"):]
        return v
    types = [_norm_type(r[0]) for r in type_rows if r[0].strip() not in ("invalid", "")]
    charge_type = max(set(types), key=types.count) if types else "ac"
    rate = COST_DC if "dc" in charge_type else COST_AC
    cost = round(energy * rate, 2) if energy else None

    return {
        "start": start_dt, "end": end_dt, "duration": duration,
        "start_soc": s_soc, "end_soc": e_soc,
        "energy_kwh": energy, "avg_power": round(avg_pwr, 1) if avg_pwr else None,
        "charge_type": charge_type, "cost": cost,
    }


@st.cache_data(ttl=2)
def detect_sessions():
    """
    Detect charging sessions from database messages.
    Cached for 2 seconds to debounce rapid Streamlit UI interactions and prevent DB query spikes.
    """
    conn = get_conn()

    # ── Primary: state-transition based detection ──────────────────────────────
    state_rows = conn.execute(
        f"SELECT timestamp, payload FROM messages WHERE topic LIKE '%{VIN}/charging/state' ORDER BY timestamp"
    ).fetchall()

    sessions = []
    session_start, prev = None, None
    state_intervals = []   # track covered time windows for power-fallback dedup

    for ts_str, raw_state in state_rows:
        active = _is_active(raw_state)
        if not _is_active(prev or "") and active:
            session_start = ts_str
        elif _is_active(prev or "") and not active and session_start:
            s = _build_session(conn, session_start, ts_str)
            if s:
                sessions.append(s)
                state_intervals.append((session_start, ts_str))
            session_start = None
        prev = raw_state

    # ── Fallback: power-based detection for sessions with no state entries ──────
    pwr_rows = conn.execute(
        f"SELECT timestamp, CAST(payload AS REAL) FROM messages "
        f"WHERE topic LIKE '%{VIN}/charging/power' ORDER BY timestamp"
    ).fetchall()

    pwr_start = None
    for i, (ts_str, pwr) in enumerate(pwr_rows):
        in_state_session = any(a <= ts_str <= b for a, b in state_intervals)
        if pwr and pwr > 0 and pwr_start is None and not in_state_session:
            pwr_start = ts_str
        elif (pwr is None or pwr == 0) and pwr_start is not None:
            if not any(a <= pwr_start <= b for a, b in state_intervals):
                s = _build_session(conn, pwr_start, ts_str)
                if s:
                    sessions.append(s)
            pwr_start = None

    sessions.sort(key=lambda s: s["start"])
    return sessions


def card(label, value, sub="", color="#f1f5f9"):
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
        '<h1 style="font-size:1.6rem;font-weight:700;color:#f1f5f9;padding:4px 0 16px 0;">🔌 Ladevorgänge</h1>',
        unsafe_allow_html=True,
    )
with h2:
    st.write("")
    if st.button("↺"):
        st.rerun()

# ── Fetch current state ───────────────────────────────────────────────────────
charge_state, _ = latest("charging/state")
charge_power, _ = latest("charging/power")
charge_type,  _ = latest("charging/type")
est_done,     _ = latest("charging/estimated_date_reached")
batt_level,   _ = latest("drives/primary/level")
batt_range,   _ = latest("drives/primary/range")
target_lvl,   _ = latest("charging/settings/target_level")
max_current,  _ = latest("charging/settings/maximum_current")

lvl         = float(batt_level) if batt_level else 0.0
is_charging = charge_state not in (None, "off", "invalid", "")

# Status banner
if is_charging:
    pwr = float(charge_power) if charge_power else 0
    st.success(f"⚡ Fahrzeug lädt · **{pwr:.1f} kW**")
else:
    st.info("🅿️ Fahrzeug lädt gerade nicht")

# ── Aktueller Zustand ─────────────────────────────────────────────────────────
st.markdown('<div class="section-rule"><span>Aktueller Zustand</span></div>', unsafe_allow_html=True)

c1, c2, c3, c4, c5, c6 = st.columns(6)

state_labels = {
    "off": "Inaktiv", "charging": "⚡ Lädt", "invalid": "—",
    "conservation": "🔒 Erhaltung", "readyForCharging": "🟡 Bereit",
    "charge_state_charging": "⚡ Lädt",
    "charge_state_charging_hv_battery": "⚡ Lädt",
    "charge_state_conservation_charging": "⚡ Erhaltung",
    "charge_state_conserving": "⚡ Erhaltung",
    "charge_state_ready_for_charging": "🟡 Bereit",
    "charge_state_not_ready_for_charging": "Inaktiv",
    "charge_state_charge_purpose_reached_conservation": "Ziel erreicht",
    "charge_state_charge_purpose_reached_not_charging": "Ziel erreicht",
    "charge_state_error": "Fehler",
}
with c1:
    lc = "#4ade80" if lvl > 20 else "#ffaa00" if lvl > 10 else "#ef4444"
    st.markdown(card("🔋 Ladestand", f"{lvl:.0f} %", color=lc), unsafe_allow_html=True)
with c2:
    st.markdown(card("Status", state_labels.get((charge_state or "").lower(), charge_state or "—")), unsafe_allow_html=True)
with c3:
    pwr_val = f"{float(charge_power):.1f} kW" if charge_power else "—"
    st.markdown(card("⚡ Leistung", pwr_val, color="#ffaa00" if is_charging else "#f1f5f9"), unsafe_allow_html=True)
with c4:
    st.markdown(card("🛣️ Reichweite", f"{float(batt_range):.0f} km" if batt_range else "—", color="#3b82f6"), unsafe_allow_html=True)
with c5:
    if est_done:
        try:
            done_dt   = datetime.fromisoformat(est_done)
            mins_left = int((done_dt - datetime.now(timezone.utc)).total_seconds() / 60)
            if mins_left > 0:
                eta = f"{mins_left//60}h {mins_left%60}min" if mins_left >= 60 else f"{mins_left} min"
                st.markdown(card("⏱ Fertig in", eta), unsafe_allow_html=True)
            else:
                st.markdown(card("⏱ Letzte Ladung", done_dt.strftime("%d.%m. %H:%M")), unsafe_allow_html=True)
        except Exception:
            st.markdown(card("⏱ ETA", est_done[:16]), unsafe_allow_html=True)
    else:
        st.markdown(card("⏱ ETA", "—"), unsafe_allow_html=True)
with c6:
    if target_lvl:
        tgt_f = float(target_lvl)
        remaining = max(tgt_f - lvl, 0) * BATTERY_KWH / 100
        st.markdown(card("⚡ Noch bis Ziel", f"{remaining:.1f} kWh", sub=f"Bis {tgt_f:.0f}%"), unsafe_allow_html=True)
    else:
        st.markdown(card("⚡ Noch bis Ziel", "—"), unsafe_allow_html=True)

if is_charging and target_lvl:
    tgt = float(target_lvl)
    st.progress(min(lvl / tgt, 1.0))

# ── Ladeeinstellungen ─────────────────────────────────────────────────────────
st.markdown('<div class="section-rule"><span>Ladeeinstellungen</span></div>', unsafe_allow_html=True)

s1, s2, s3 = st.columns(3)
with s1:
    st.markdown(card("🎯 Ziel-SoC", f"{float(target_lvl):.0f} %" if target_lvl else "—"), unsafe_allow_html=True)
_CURRENT_MAP = {"max_charge_current_ac_maximum": "16", "max_charge_current_ac_reduced": "8"}
def _resolve_current(v):
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        mapped = _CURRENT_MAP.get(v.lower())
        return float(mapped) if mapped else None

_amp = _resolve_current(max_current)
with s2:
    st.markdown(card("⚡ Max. Strom", f"{_amp:.0f} A" if _amp is not None else "—"), unsafe_allow_html=True)
with s3:
    if _amp is not None:
        st.markdown(card("🔌 Max. AC", f"{1.732 * 230 * _amp / 1000:.1f} kW"), unsafe_allow_html=True)
    else:
        st.markdown(card("🔌 Max. AC", "—"), unsafe_allow_html=True)

# ── Timeline Chart ────────────────────────────────────────────────────────────
st.markdown('<div class="section-rule"><span>Akku-Verlauf &amp; Ladeleistung</span></div>', unsafe_allow_html=True)

batt_df  = history("drives/primary/level")
power_df = history("charging/power")
sessions = detect_sessions()

if not batt_df.empty:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=batt_df["timestamp"], y=batt_df["value"], name="Ladestand (%)",
        fill="tozeroy", line=dict(color="#00cc88", width=2),
        fillcolor="rgba(0,204,136,0.10)",
        hovertemplate="%{y:.0f}%<extra>Ladestand</extra>",
    ), secondary_y=False)
    if target_lvl:
        fig.add_hline(y=float(target_lvl), line_dash="dash",
                      line_color="rgba(100,149,255,0.6)", line_width=1.5,
                      annotation_text=f"Ziel {float(target_lvl):.0f}%",
                      annotation_font_color="rgba(100,149,255,0.9)",
                      secondary_y=False)
    if not power_df.empty and power_df["value"].max() > 0:
        fig.add_trace(go.Scatter(
            x=power_df["timestamp"], y=power_df["value"], name="Ladeleistung (kW)",
            line=dict(color="#ffaa00", width=2, dash="dot"),
            hovertemplate="%{y:.1f} kW<extra>Leistung</extra>",
        ), secondary_y=True)
    for s in sessions:
        fig.add_vrect(x0=s["start"], x1=s["end"],
                      fillcolor="rgba(255,170,0,0.07)", layer="below",
                      line_width=0.5, line_color="rgba(255,170,0,0.25)")
    fig.update_layout(
        height=380, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified", margin=dict(t=10, b=0),
        font=dict(color="#9ca3af", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    bgcolor="rgba(14,21,32,0.8)", bordercolor="rgba(255,255,255,0.07)", borderwidth=1),
    )
    fig.update_yaxes(title_text="Ladestand (%)", range=[0, 105],
                     gridcolor="rgba(255,255,255,0.05)", zeroline=False, secondary_y=False)
    fig.update_yaxes(title_text="Leistung (kW)", rangemode="tozero",
                     gridcolor="rgba(255,255,255,0.03)", secondary_y=True)
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.04)")
    st.plotly_chart(fig, use_container_width=True)
    
    # ── Charging Curve (Power vs SoC) ─────────────────────────────────────────
    if not power_df.empty and not batt_df.empty:
        # Merge power and battery level data to correlate them
        # We use merge_asof to match the closest power reading for each SOC reading
        df_curve = pd.merge_asof(
            batt_df.sort_values("timestamp"),
            power_df.sort_values("timestamp"),
            on="timestamp",
            direction="backward",
            suffixes=("_soc", "_pwr")
        )
        df_curve = df_curve[df_curve["value_pwr"] > 0] # Only show points where charging was active
        
        if not df_curve.empty:
            st.markdown('<div class="section-rule"><span>Ladekurve (Leistung vs. SOC)</span></div>', unsafe_allow_html=True)
            fig_curve = go.Figure()
            fig_curve.add_trace(go.Scatter(
                x=df_curve["value_soc"], y=df_curve["value_pwr"],
                mode="markers",
                marker=dict(
                    size=8,
                    color=df_curve["value_pwr"],
                    colorscale="Viridis",
                    showscale=True,
                    colorbar=dict(title="kW", thickness=15, len=0.8)
                ),
                hovertemplate="SOC: %{x}%<br>Leistung: %{y:.1f} kW<extra></extra>"
            ))
            fig_curve.update_layout(
                height=350, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=10, b=0), font=dict(color="#9ca3af", size=11),
                xaxis=dict(title="Ladestand (%)", range=[0, 100], gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(title="Leistung (kW)", rangemode="tozero", gridcolor="rgba(255,255,255,0.05)"),
            )
            st.plotly_chart(fig_curve, use_container_width=True)
else:
    st.info("Noch keine Akkudaten in der Datenbank.")


# ── Ladesitzungen ─────────────────────────────────────────────────────────────
st.markdown('<div class="section-rule"><span>Erkannte Ladevorgänge (Seit März 2026)</span></div>', unsafe_allow_html=True)

if sessions:
    rows_disp = []
    for s in reversed(sessions):
        dur_m = int(s["duration"].total_seconds() / 60)
        rows_disp.append({
            "Start":           s["start"].strftime("%d.%m.%Y %H:%M"),
            "Ende":            s["end"].strftime("%d.%m.%Y %H:%M"),
            "Dauer":           f"{dur_m//60}h {dur_m%60:02d}min" if dur_m >= 60 else f"{dur_m} min",
            "Start-SoC":       f"{s['start_soc']:.0f} %" if s["start_soc"] else "—",
            "End-SoC":         f"{s['end_soc']:.0f} %"   if s["end_soc"]   else "—",
            "Geladen (kWh)":   f"{s['energy_kwh']:.1f}"  if s["energy_kwh"] else "—",
            "Ø Leistung":      f"{s['avg_power']:.1f} kW" if s["avg_power"] else "—",
            "Typ":             (s.get("charge_type") or "ac").upper(),
            "Kosten (ca.)":    f"{s['cost']:.2f} €" if s.get("cost") else "—",
        })
    st.dataframe(pd.DataFrame(rows_disp), use_container_width=True, hide_index=True)

    total_energy = sum(s["energy_kwh"] or 0 for s in sessions)
    avg_dur      = sum(s["duration"].total_seconds() for s in sessions) / len(sessions) / 60

    st.write("")
    m1, m2, m3, m4 = st.columns(4)
    with m1: st.markdown(card("📋 Ladevorgänge", str(len(sessions)), sub="Seit März 2026"), unsafe_allow_html=True)
    with m2: st.markdown(card("⚡ Gesamt geladen", f"{total_energy:.1f} kWh", sub="Seit März 2026", color="#4ade80"), unsafe_allow_html=True)
    with m3: st.markdown(card("⏱ Ø Ladedauer", f"{avg_dur:.0f} min", sub="Seit März 2026"), unsafe_allow_html=True)
    with m4: st.markdown(card("📊 Ø pro Vorgang", f"{total_energy/len(sessions):.1f} kWh", sub="Seit März 2026"), unsafe_allow_html=True)

    if len(sessions) >= 2:
        chart_data = pd.DataFrame([
            {
                "Date_raw": s["start"].date(),
                "kWh":   s["energy_kwh"] or 0,
                "Kosten": s["cost"] or 0,
            }
            for s in sessions if s["energy_kwh"]
        ])
        if not chart_data.empty:
            # Aggregate by Date_raw
            chart_day = chart_data.groupby("Date_raw").agg({"kWh": "sum", "Kosten": "sum"}).reset_index()
            chart_day = chart_day.sort_values("Date_raw")
            chart_day["Datum"] = chart_day["Date_raw"].apply(lambda x: x.strftime("%d.%m."))

            fig2 = make_subplots(specs=[[{"secondary_y": True}]])
            fig2.add_trace(go.Bar(
                x=chart_day["Datum"], y=chart_day["kWh"],
                name="Geladen (kWh)",
                marker=dict(color="#00cc88", opacity=0.85),
                text=chart_day["kWh"].apply(lambda v: f"{v:.1f}"),
                textposition="outside", textfont=dict(color="#9ca3af", size=10),
            ), secondary_y=False)
            fig2.add_trace(go.Scatter(
                x=chart_day["Datum"], y=chart_day["Kosten"],
                name="Kosten (€)",
                mode="lines+markers+text",
                line=dict(color="#ffaa00", width=2),
                marker=dict(size=7, color="#ffaa00"),
                text=chart_day["Kosten"].apply(lambda v: f"{v:.2f}€"),
                textposition="top center",
                textfont=dict(color="#ffaa00", size=10),
                hovertemplate="%{y:.2f} €<extra>Kosten</extra>",
            ), secondary_y=True)
            fig2.update_layout(
                height=280, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=16, b=0), font=dict(color="#9ca3af", size=11),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                            bgcolor="rgba(14,21,32,0.8)", bordercolor="rgba(255,255,255,0.07)", borderwidth=1),
                xaxis=dict(
                    type="category",
                    categoryorder="array",
                    categoryarray=chart_day["Datum"].tolist(),
                    showgrid=False
                ),
                barmode="group",
            )
            fig2.update_yaxes(title_text="kWh", gridcolor="rgba(255,255,255,0.05)",
                              zeroline=False, secondary_y=False)
            fig2.update_yaxes(title_text="€", gridcolor="rgba(255,255,255,0.03)",
                              zeroline=False, secondary_y=True)
            st.plotly_chart(fig2, use_container_width=True)

        # ── Charging Type Distribution ────────────────────────────────────────
        type_counts = pd.DataFrame([s["charge_type"].upper() for s in sessions if s.get("charge_type")], columns=["Typ"])
        if not type_counts.empty:
            st.write("")
            st.markdown('<div class="section-rule"><span>Verteilung Ladetyp (Seit März 2026)</span></div>', unsafe_allow_html=True)
            dist = type_counts["Typ"].value_counts()
            fig3 = go.Figure(go.Pie(
                labels=dist.index, values=dist.values,
                hole=0.45,
                marker=dict(colors=["#00cc88", "#3b82f6", "#ffaa00"]),
                textinfo="label+percent",
                hovertemplate="<b>%{label}</b><br>%{value} Ladevorgänge<extra></extra>"
            ))
            fig3.update_layout(
                height=260, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=0, b=0, l=0, r=0),
                legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5,
                            font=dict(color="#9ca3af", size=11)),
            )
            st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("Noch keine abgeschlossenen Ladevorgänge erkannt.")


st.caption(f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')} · Auto-Refresh alle 5 min · Akku: {BATTERY_KWH} kWh")


## 2024-06-25 - Debouncing high-frequency DB queries during Streamlit UI interactions
**Learning:** Streamlit re-runs the script top-to-bottom on every user interaction (e.g., clicking, toggling, interacting with charts). This can lead to N+1 query problems and high CPU/DB load if data retrieval functions (like `latest` or `detect_sessions`) fetch data directly from SQLite without caching.
**Action:** Use `@st.cache_data(ttl=2)` on data retrieval functions. A very short TTL (like 2 seconds) debounces frequent queries during rapid UI interactions while maintaining a near-real-time feel for telemetry dashboards.

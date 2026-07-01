## 2024-05-24 - Debouncing Streamlit DB Polling

**Learning:** Streamlit apps utilizing auto-refresh or high-frequency UI interactions can quickly generate excessive DB load via N+1 queries. We observed this in the telemetry dashboard. Using a standard, long cache duration (`ttl=300`) might cause data to go stale, while not using cache crushes the database.

**Action:** For near-real-time Streamlit data fetching where autorefresh (e.g. `streamlit_autorefresh`) is used, debounce the database calls by wrapping data-fetch functions in `@st.cache_data(ttl=2)`. This provides a 2-second buffer that perfectly handles bursts of rapid UI interactions and autorefreshes, collapsing concurrent renders into single DB hits while maintaining the realtime feel.

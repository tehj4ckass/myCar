## 2024-05-18 - Missing Caching on Data Functions
**Learning:** In a Streamlit dashboard built on top of a SQLite database containing high-frequency MQTT messages, functions like `latest()` and `history()` run multiple expensive queries on every app re-render (which happens very frequently on auto-refresh or user interaction) leading to massive query overhead.
**Action:** Use `@st.cache_data(ttl=2)` on all data retrieval functions to maintain real-time feel while dramatically reducing SQLite load.

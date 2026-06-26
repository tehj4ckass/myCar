## 2024-05-15 - Streamlit @st.cache_data Debouncing
**Learning:** In a Streamlit dashboard with high-frequency auto-refresh or data polling, rapid database queries can bottleneck performance and hit the SQLite DB unnecessarily.
**Action:** Adding `@st.cache_data(ttl=2)` to data retrieval functions acts as a simple debounce, significantly reducing redundant SQLite queries within short time windows (e.g. 2 seconds) without sacrificing the perception of real-time telemetry.

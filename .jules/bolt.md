## 2026-06-30 - Streamlit Autorefresh & Debouncing Queries
**Learning:** Streamlit `st_autorefresh` and rapid UI interactions cause N+1 and redundant database polling issues, which severely impacts performance when not cached, even when using local SQLite.
**Action:** Use a short TTL cache like `@st.cache_data(ttl=2)` on data retrieval functions to debounce these rapid, redundant database calls without sacrificing the real-time feel of the dashboard.

## 2024-05-18 - Streamlit N+1 query anti-pattern during re-renders
**Learning:** Because Streamlit executes the entire script top-to-bottom on every interaction or auto-refresh cycle, failing to cache expensive database retrieval or processing functions leads to severe N+1 query problems and redundant computations.
**Action:** Always wrap heavy data-fetching and processing functions in Streamlit dashboards with `@st.cache_data` (e.g., `ttl=300` to align with the auto-refresh interval) to prevent repeated SQLite queries and ensure UI responsiveness.

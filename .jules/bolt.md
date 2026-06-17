## 2026-06-17 - Streamlit N+1 Query Bottleneck
**Learning:** Streamlit's "re-run on interaction" model combined with N+1 DB query functions (like trip or charging session detection which fetches extra data points per event) causes severe UI bottlenecks because expensive SQLite logic runs synchronously on every render.
**Action:** Always wrap expensive, repetitive data processing and DB queries in Streamlit dashboards with `@st.cache_data` (e.g. `@st.cache_data(ttl=300)`) to memoize the results between renders and prevent redundant database hits.

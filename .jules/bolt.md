## 2024-06-22 - Missing Streamlit DB Caching
**Learning:** Found N+1 database queries inside Streamlit views that run synchronously on every render.
**Action:** Always use `@st.cache_data(ttl=300)` on expensive DB queries in Streamlit to avoid blocking the main thread during component interactions.

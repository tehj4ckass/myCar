## YYYY-MM-DD - Streamlit Database Query Debouncing
**Learning:** Using `@st.cache_data(ttl=2)` acts as an effective debounce mechanism for Streamlit apps, preventing redundant SQLite database hits during rapid UI interactions or autorefresh cycles while maintaining near-real-time performance.
**Action:** Always consider short TTL caching for data retrieval functions in Streamlit apps that poll a database frequently, ensuring the functions establish their own internal database connection as Streamlit cannot cache connection objects.

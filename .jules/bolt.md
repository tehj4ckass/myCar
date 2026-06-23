## 2023-10-27 - Streamlit Caching

**Learning:** Streamlit executes the entire script from top to bottom on every user interaction (e.g., clicking a button, typing in an input). This leads to severe performance degradation if expensive operations like database queries or data processing are not cached, as they will be re-run on every interaction, causing significant UI lag and database load.

**Action:** Always wrap expensive data fetching and processing functions in Streamlit with `@st.cache_data(ttl=X)` to memoize the results and prevent redundant executions during re-renders. Choose a TTL that balances performance with data freshness requirements.

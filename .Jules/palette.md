## 2024-06-24 - Tooltips in Streamlit
**Learning:** In Streamlit, icon-only buttons lack native accessibility context, making them difficult for screen reader users and confusing visually.
**Action:** Always use the `help` parameter when creating `st.button` instances with icons (e.g., `st.button("↺", help="Daten aktualisieren")`) to automatically generate tooltips and provide accessible labels.

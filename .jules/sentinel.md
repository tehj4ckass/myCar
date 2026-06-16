## 2025-05-18 - XSS in Streamlit Custom HTML

**Vulnerability:** The Streamlit dashboard uses `st.markdown(html, unsafe_allow_html=True)` to render custom UI components (like `card` and `gauge_card`). Dynamic data (e.g. vehicle name, battery percentage) retrieved from the MQTT-fed SQLite database was being interpolated directly into these HTML strings without sanitization, leading to a Stored Cross-Site Scripting (XSS) vulnerability.

**Learning:** When using Streamlit's `unsafe_allow_html=True`, the framework disables its default sanitization. Therefore, any dynamic variables injected into the HTML string must be manually escaped, even if they originate from an internal database.

**Prevention:** Always use `html.escape(str(variable))` for any dynamic data being interpolated into HTML strings that will be rendered with `unsafe_allow_html=True`. Cast to string first to prevent `TypeError`s on non-string data.

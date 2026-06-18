
## 2024-05-18 - Fix Cross-Site Scripting (XSS) in Streamlit Custom Components
**Vulnerability:** The application is built using Streamlit and frequently utilizes `unsafe_allow_html=True` to render custom UI components like `card` and `gauge_card`. Data incorporated into these HTML strings (like text values or vehicle labels) wasn't being sanitized, presenting a direct Cross-Site Scripting (XSS) vulnerability.
**Learning:** `unsafe_allow_html=True` acts as a bypass to standard Streamlit sanitization. Any dynamic string interpolation inside HTML contexts requires manual sanitation to prevent malicious payload execution when untrusted data sources (e.g. MQTT feeds) are rendered.
**Prevention:** Always use `html.escape()` around variables before interpolating them into HTML strings in Streamlit when `unsafe_allow_html=True` is utilized. Ensure the sanitization happens correctly handling `None` values (e.g., `html.escape(str(val)) if val is not None else ""`).

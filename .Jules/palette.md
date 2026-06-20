## 2026-06-20 - Accessible tooltips for icon-only buttons
**Learning:** Adding accessible labels to icon-only buttons like '↺' is required for proper accessibility. Streamlit's `st.button()` allows doing this efficiently via the `help` parameter.
**Action:** When adding icon-only buttons using Streamlit, always include a descriptive `help` argument to ensure tooltips and ARIA-equivalent labeling exist.

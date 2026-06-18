## 2024-06-18 - Tooltips for Icon-Only Buttons in Streamlit
**Learning:** Icon-only buttons without tooltips are a common accessibility anti-pattern in Streamlit applications. Streamlit's `st.button` provides a built-in `help` parameter specifically for this purpose, which adds both visual tooltips on hover and accessible names for screen readers.
**Action:** When implementing or reviewing `st.button` components that only use an icon (like '↺'), always ensure a descriptive `help` text is provided in the local language to clarify the button's action.

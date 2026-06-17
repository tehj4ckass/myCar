## YYYY-MM-DD - Icon-only Buttons Accessibility
**Learning:** In Streamlit, icon-only buttons (`st.button("↺")`) lack context for screen readers and tooltips for sighted users.
**Action:** Always add a `help` argument to `st.button()` when it contains only an icon to provide accessible tooltips and context.

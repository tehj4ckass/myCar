
## 2024-05-23 - Icon-Only Buttons Need Tooltips
**Learning:** Streamlit `st.button()` with only an icon lacks context, making it inaccessible to screen readers and potentially confusing to users who aren't familiar with standard icon meanings.
**Action:** Always include the `help` argument with a descriptive, localized text when creating icon-only buttons to add native tooltips.

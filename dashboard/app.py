import base64
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="VW ID.3 Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

with open("/app/vw_id3_Mangangrau_Metallic_Schwarz.webp", "rb") as _f:
    _img_b64 = base64.b64encode(_f.read()).decode()

# Global sidebar styling injected once here
st.markdown("""
<style>
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] {
    visibility: visible !important;
    opacity: 1 !important;
}

[data-testid="stSidebar"] {
    background: #0e1520 !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}
[data-testid="stSidebarContent"] {
    display: flex !important;
    flex-direction: column !important;
    padding-top: 0.25rem !important;
}
[data-testid="stSidebarNav"] { order: 3; }
.car-img-wrap { order: 2; padding: 0.5rem 0.75rem 1rem 0.75rem; }
.app-title { order: 1; padding: 0rem 1rem 0rem 1rem; margin-top: -0.5rem; }
.app-title .mycar {
    font-size: 1.4rem;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.02em;
    transition: color 0.18s ease;
}
.app-title .dash {
    font-size: 1.4rem;
    font-weight: 300;
    color: #8bb4f7; /* Leichtes blau für den Akzent */
}
.car-img-wrap img {
    width: 100%;
    height: auto;
    object-fit: contain;
    display: block;
    filter: drop-shadow(0px 8px 16px rgba(0,0,0,0.4));
    transition: transform 0.18s ease;
}
.sidebar-header-link {
    text-decoration: none !important;
    color: inherit !important;
    display: block;
    cursor: pointer;
}
.sidebar-header-link:hover .mycar {
    color: #8bb4f7 !important;
}
.sidebar-header-link:hover img {
    transform: scale(1.025);
}
/* remove streamlit's default block margin around the image element */
[data-testid="stSidebarContent"] [data-testid="stMarkdownContainer"]:has(.car-img-wrap) {
    margin: 0 !important;
    padding: 0 !important;
}
[data-testid="stSidebarContent"] > div:first-child {
    margin-top: 0 !important;
    padding-top: 0 !important;
}
[data-testid="stSidebarNav"] a {
    border-radius: 9px !important;
    margin: 2px 6px !important;
    padding: 8px 12px !important;
    transition: background 0.15s !important;
}
[data-testid="stSidebarNav"] a:hover {
    background: rgba(59,130,246,0.1) !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"] {
    background: rgba(59,130,246,0.12) !important;
    border-right: 3px solid #3b82f6 !important;
    color: #3b82f6 !important;
}

/* Custom EV themed loading indicator replacing the sports running man */
[data-testid="stStatusWidget"] {
    visibility: hidden;
}
[data-testid="stStatusWidget"]::before {
    content: "⚡";
    visibility: visible;
    display: inline-block;
    font-size: 1.25rem;
    animation: rotate-spark 1.5s linear infinite;
    cursor: default;
}
@keyframes rotate-spark {
    0% { transform: rotate(0deg) scale(0.9); opacity: 0.6; }
    50% { transform: rotate(180deg) scale(1.1); opacity: 1; }
    100% { transform: rotate(360deg) scale(0.9); opacity: 0.6; }
}
</style>
""", unsafe_allow_html=True)

# Fix Material Symbols icons: the bundled font has no ligature table,
# so icon names render as plain text. Replace them with the correct Unicode
# Private Use Area codepoints via MutationObserver.
components.html("""
<script>
(function() {
  const ICON_MAP = {
    'keyboard_double_arrow_left':  '❮',
    'keyboard_double_arrow_right': '❯',
    'keyboard_double_arrow_up':    '',
    'keyboard_double_arrow_down':  '',
    'chevron_left':                '❮',
    'chevron_right':               '❯',
    'close':                       '✖',
    'menu':                        '☰',
    'expand_more':                 '',
    'info':                        '',
    'contrast':                    '',
    'light_mode':                  '',
    'dark_mode':                   '',
  };

  function fixIcons(root) {
    root.querySelectorAll('[data-testid="stIconMaterial"]').forEach(el => {
      const text = el.textContent.trim();
      if (ICON_MAP[text]) {
        el.textContent = ICON_MAP[text];
        if (['❮', '❯', '✖', '☰'].includes(ICON_MAP[text])) {
             el.style.fontFamily = "sans-serif";
             el.style.fontWeight = "bold";
             el.style.fontSize = "1.2rem";
        }
      }
    });
  }

  // Fix icons already in DOM
  fixIcons(window.parent.document);

  // Watch for new icons added by React
  const observer = new MutationObserver(() => fixIcons(window.parent.document));
  observer.observe(window.parent.document.body, { childList: true, subtree: true });
})();
</script>
""", height=0)

st.sidebar.markdown(
    f'<a href="/" target="_self" class="sidebar-header-link">'
    f'<div class="app-title"><span class="mycar">myCar</span><span class="dash">.dashboard</span></div>'
    f'</a>',
    unsafe_allow_html=True,
)
st.sidebar.markdown(
    f'<a href="/" target="_self" class="sidebar-header-link" aria-label="Zur Startseite">'
    f'<div class="car-img-wrap"><img src="data:image/webp;base64,{_img_b64}" alt="VW ID.3"></div>'
    f'</a>',
    unsafe_allow_html=True,
)

pg = st.navigation([
    st.Page("pages/uebersicht.py",  title="Übersicht",     icon="🏠", default=True),
    st.Page("pages/laden.py",       title="Ladevorgänge",  icon="🔌"),
    st.Page("pages/trips.py",       title="Trips",         icon="🗺️"),
])
pg.run()

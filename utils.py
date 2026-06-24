"""Shared helpers and styles for all pages."""
import io
import os
import requests
import streamlit as st

try:
    from colorthief import ColorThief
    _COLORTHIEF = True
except ImportError:
    _COLORTHIEF = False

NOISE = (
    "data:image/svg+xml,%3Csvg viewBox='0 0 512 512' xmlns='http://www.w3.org/2000/svg'%3E"
    "%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.72' "
    "numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E"
    "%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E"
)

def get_secret(key):
    return st.secrets.get(key) or os.getenv(key)

def search_unsplash(query, n=9):
    key = get_secret("UNSPLASH_ACCESS_KEY")
    if not key:
        return []
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": n, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {key}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        return [
            {"thumb": p["urls"]["small"], "link": p["links"]["html"],
             "author": p["user"]["name"], "source": "unsplash"}
            for p in resp.json().get("results", [])
        ]
    except Exception:
        return []

def search_pexels(query, n=9):
    key = get_secret("PEXELS_API_KEY")
    if not key:
        return []
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": n, "orientation": "landscape"},
            headers={"Authorization": key},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        return [
            {"thumb": p["src"]["medium"], "link": p["url"],
             "author": p["photographer"], "source": "pexels"}
            for p in resp.json().get("photos", [])
        ]
    except Exception:
        return []

@st.cache_data(show_spinner=False)
def get_color_palette(image_url, num_colors=5):
    if not _COLORTHIEF:
        return []
    try:
        resp = requests.get(image_url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        ct = ColorThief(io.BytesIO(resp.content))
        palette = ct.get_palette(color_count=num_colors, quality=10)
        return [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in palette]
    except Exception:
        return []

def image_card_html(img_url, link, author, source):
    palette = get_color_palette(img_url)
    badge_class = "badge-unsplash" if source == "unsplash" else "badge-pexels"
    badge_label = "Unsplash" if source == "unsplash" else "Pexels"
    swatches = "".join(
        f'<div class="swatch" style="background:{c};" title="{c}"></div>'
        for c in palette
    ) if palette else ""
    palette_row = f'<div class="palette-row">{swatches}</div>' if swatches else ""
    return f"""
    <div class="img-card">
        <a href="{link}" target="_blank" rel="noopener">
            <img src="{img_url}" style="width:100%;border-radius:10px;display:block;object-fit:cover;height:160px;">
        </a>
        {palette_row}
        <div style="margin-top:5px;">
            <span class="badge {badge_class}">{badge_label}</span>
            <a href="{link}" target="_blank"
               style="font-size:0.72rem;color:#5A5A6E;text-decoration:none;margin-left:4px;">{author}</a>
        </div>
    </div>"""

def strip_with_palettes(previews):
    """Build preview strip + palette bars for query cards."""
    imgs = "".join(
        f'<a href="{p["link"]}" target="_blank" rel="noopener">'
        f'<img src="{p["thumb"]}" alt="{p["author"]}"></a>'
        for p in previews[:3]
    )
    pal_cols = ""
    for p in previews[:3]:
        pal = get_color_palette(p["thumb"])
        swatches = "".join(
            f'<div class="swatch" style="background:{c};width:100%;height:8px;'
            f'border-radius:2px;border:none;box-shadow:none;"></div>'
            for c in pal
        ) if pal else ""
        pal_cols += f'<div class="strip-palette">{swatches}</div>'
    return f'<div class="preview-strip">{imgs}</div><div class="strip-palettes">{pal_cols}</div>'

SHARED_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600&family=Space+Mono:wght@400;700&display=swap');

html, body, [class*="css"] {{ font-family: 'Space Grotesk', sans-serif; }}
.stApp {{ background-color: #EAEAED; }}

/* Left panel: clean white */
[data-testid="stSidebar"] {{
    background: #F4F4F7 !important;
    border-right: 1px solid rgba(200,200,215,0.55) !important;
}}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3, [data-testid="stSidebar"] label,
[data-testid="stSidebar"] p {{ color: #0C0C12 !important; }}
[data-testid="stSidebarNav"] {{ display: none !important; }}

/* Right area: gradient blob */
[data-testid="stMain"], section.main {{
    background:
        radial-gradient(ellipse at 80% 62%, #1533E8 0%, rgba(21,51,232,0.72) 18%, rgba(21,51,232,0.13) 46%, transparent 62%),
        radial-gradient(ellipse at 96% 16%, rgba(21,51,232,0.26) 0%, transparent 40%),
        radial-gradient(ellipse at 55% 94%, rgba(21,51,232,0.16) 0%, transparent 36%),
        #EAEAED !important;
    background-attachment: fixed !important;
}}
[data-testid="stMain"]::before, section.main::before {{
    content: '';
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background-image: url("{NOISE}");
    opacity: 0.07; pointer-events: none; z-index: 0;
}}
.block-container, [data-testid="stMainBlockContainer"] {{
    background: transparent !important; position: relative; z-index: 1;
}}

/* Sidebar nav bubbles */
[data-testid="stSidebar"] .stButton > button {{
    border-radius: 50px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 0.78rem !important; font-weight: 500 !important;
    letter-spacing: 0.04em !important; text-align: left !important;
    padding: 0.45rem 1rem !important; transition: all 0.15s !important;
    width: 100% !important;
}}
[data-testid="stSidebar"] .stButton > button[kind="secondary"] {{
    background: rgba(21,51,232,0.06) !important;
    border: 1px solid rgba(21,51,232,0.18) !important;
    color: #0C0C12 !important;
}}
[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {{
    background: rgba(21,51,232,0.12) !important;
    border-color: rgba(21,51,232,0.3) !important;
}}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {{
    background: #1533E8 !important;
    border: none !important; color: #fff !important;
}}

h1 {{
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 1.9rem !important; color: #0C0C12 !important;
    letter-spacing: -0.03em; font-weight: 600 !important;
    text-transform: uppercase;
}}
h2, h3 {{
    font-family: 'Space Grotesk', sans-serif !important;
    color: #0C0C12 !important; font-weight: 500 !important; letter-spacing: -0.01em;
}}

/* Glass cards */
.glass-card {{
    background: rgba(255,255,255,0.58);
    backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.78);
    border-radius: 18px; padding: 1.3rem 1.4rem; margin-bottom: 1rem;
}}

/* Query cards */
.query-card {{
    background: rgba(255,255,255,0.58);
    backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.78);
    border-radius: 18px; overflow: hidden; margin-bottom: 1rem;
}}
.query-card-inner {{ padding: 1.2rem 1.3rem 1.1rem; }}
.card-label {{
    font-size: 0.58rem; color: #1533E8; font-weight: 700;
    letter-spacing: 0.2em; text-transform: uppercase;
    font-family: 'Space Mono', monospace; margin-bottom: 0.35rem;
}}
.card-query-text {{
    font-size: 0.95rem; color: #0C0C12; font-weight: 500;
    font-style: italic; margin-bottom: 0.9rem; line-height: 1.4;
}}

/* Preview strip */
.preview-strip {{ display: flex; gap: 0.5rem; margin-bottom: 0.4rem; }}
.preview-strip img {{
    width: calc(33.33% - 0.34rem); height: 88px;
    object-fit: cover; border-radius: 8px; border: 1px solid rgba(255,255,255,0.6);
}}
.preview-placeholder {{
    width: calc(33.33% - 0.34rem); height: 88px;
    background: rgba(255,255,255,0.28); border-radius: 8px;
    border: 1px solid rgba(255,255,255,0.5);
}}
.strip-palettes {{ display: flex; gap: 0.5rem; margin-bottom: 0.75rem; }}
.strip-palette {{ width: calc(33.33% - 0.34rem); display: flex; gap: 2px; }}

/* Image cards */
.img-card {{ margin-bottom: 0.5rem; }}
.palette-row {{ display: flex; gap: 4px; margin-top: 6px; align-items: center; }}
.swatch {{
    width: 20px; height: 20px; border-radius: 50%;
    border: 1.5px solid rgba(255,255,255,0.7); flex-shrink: 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.15);
}}

.btn-row {{ display: flex; flex-wrap: wrap; gap: 0.3rem; }}
.ref-btn {{
    display: inline-flex; align-items: center;
    padding: 0.36rem 0.9rem; border-radius: 50px;
    text-decoration: none !important; font-size: 0.67rem; font-weight: 500;
    font-family: 'Space Grotesk', sans-serif; letter-spacing: 0.07em;
    text-transform: uppercase; transition: opacity 0.2s; border: 1px solid transparent;
}}
.ref-btn:hover {{ opacity: 0.68; }}
.btn-pinterest {{ background: #1533E8; color: #fff !important; }}
.btn-behance   {{ background: #0C0C12; color: #EAEAED !important; }}
.btn-google    {{ background: rgba(255,255,255,0.72); color: #0C0C12 !important; border: 1px solid rgba(0,0,0,0.1); }}
.btn-archinect {{ background: rgba(255,255,255,0.42); color: #0C0C12 !important; border: 1px solid rgba(0,0,0,0.08); }}
.btn-arena     {{ background: rgba(21,51,232,0.1); color: #1533E8 !important; border: 1px solid rgba(21,51,232,0.2); }}

/* Inputs */
input[type="text"], textarea {{
    background-color: rgba(255,255,255,0.88) !important;
    border: 1px solid rgba(200,200,215,0.7) !important;
    border-radius: 50px !important; color: #0C0C12 !important;
    font-family: 'Space Grotesk', sans-serif !important;
}}
textarea {{ border-radius: 14px !important; }}
input[type="text"]:focus, textarea:focus {{
    border-color: #1533E8 !important;
    box-shadow: 0 0 0 2px rgba(21,51,232,0.12) !important;
}}
[data-testid="stSelectbox"] > div > div {{
    background-color: rgba(255,255,255,0.88) !important;
    border: 1px solid rgba(200,200,215,0.7) !important;
    border-radius: 50px !important; color: #0C0C12 !important;
}}

/* Main action buttons */
.stButton > button[kind="primary"] {{
    background-color: #1533E8 !important; color: #fff !important;
    border: none !important; border-radius: 50px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 500 !important; letter-spacing: 0.07em;
    text-transform: uppercase; font-size: 0.74rem !important;
}}
.stButton > button[kind="primary"]:hover {{ background-color: #0F25C4 !important; }}
.stButton > button[kind="secondary"] {{
    background-color: rgba(255,255,255,0.6) !important; color: #0C0C12 !important;
    border: 1px solid rgba(0,0,0,0.14) !important; border-radius: 50px !important;
    font-family: 'Space Grotesk', sans-serif !important; font-weight: 500 !important;
    letter-spacing: 0.07em; text-transform: uppercase; font-size: 0.74rem !important;
}}
.stButton > button[kind="secondary"]:hover {{ background-color: rgba(255,255,255,0.88) !important; }}
.stDownloadButton > button {{
    background-color: #0C0C12 !important; color: #EAEAED !important;
    border: none !important; border-radius: 50px !important;
    font-family: 'Space Grotesk', sans-serif !important; font-weight: 500 !important;
    letter-spacing: 0.07em; text-transform: uppercase; font-size: 0.74rem !important;
}}
.stDownloadButton > button:hover {{ background-color: #1533E8 !important; }}

/* Filter pills */
[data-testid="stPillsInput"] button {{
    border-radius: 50px !important; font-family: 'Space Grotesk', sans-serif !important;
    font-size: 0.72rem !important; font-weight: 500 !important; letter-spacing: 0.05em !important;
    background: rgba(255,255,255,0.55) !important;
    border: 1px solid rgba(200,200,215,0.65) !important;
    color: #0C0C12 !important; transition: all 0.15s !important;
}}
[data-testid="stPillsInput"] button[aria-pressed="true"] {{
    background: #1533E8 !important; border-color: #1533E8 !important; color: #fff !important;
}}
[data-testid="stPillsInput"] button:hover {{
    background: rgba(21,51,232,0.1) !important; border-color: rgba(21,51,232,0.3) !important;
}}

/* Alerts */
[data-testid="stAlert"] {{
    border-radius: 12px !important; backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    font-family: 'Space Grotesk', sans-serif !important;
}}
.stSuccess {{ background: rgba(230,235,255,0.72) !important; color: #0A1A8A !important; border-left: 3px solid #1533E8 !important; }}
.stInfo    {{ background: rgba(255,255,255,0.52) !important; color: #0C0C12 !important; border-left: 3px solid rgba(100,100,140,0.5) !important; }}
.stWarning {{ background: rgba(255,244,230,0.72) !important; color: #5A3000 !important; border-left: 3px solid #E88015 !important; }}

hr {{ border-color: rgba(0,0,0,0.08) !important; }}
.stSpinner > div {{ border-top-color: #1533E8 !important; }}
.badge {{
    display: inline-block; padding: 0.1rem 0.5rem; border-radius: 50px;
    font-size: 0.6rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
}}
.badge-unsplash {{ background: #0C0C12; color: #EAEAED; }}
.badge-pexels   {{ background: #1533E8; color: #fff; }}
.section-tag {{
    font-size: 0.6rem; letter-spacing: 0.2em; text-transform: uppercase;
    color: #1533E8; font-weight: 700; margin-bottom: 0.2rem;
    font-family: 'Space Mono', monospace;
}}

/* Home page bubble navigation (right column) */
.home-bubble-nav .stButton > button {{
    background: rgba(255,255,255,0.16) !important;
    border: 1px solid rgba(255,255,255,0.45) !important;
    border-radius: 50px !important; color: #0C0C12 !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 500 !important; font-size: 0.88rem !important;
    letter-spacing: 0.03em !important; padding: 0.65rem 1.4rem !important;
    backdrop-filter: blur(8px) !important; -webkit-backdrop-filter: blur(8px) !important;
    text-align: left !important; transition: all 0.2s !important;
    width: 100% !important;
}}
.home-bubble-nav .stButton > button:hover {{
    background: rgba(255,255,255,0.28) !important;
    border-color: rgba(255,255,255,0.7) !important;
    transform: translateX(4px) !important;
}}

/* Brief extracted chips */
.brief-chip {{
    display: inline-flex; align-items: center; gap: 0.3rem;
    background: rgba(21,51,232,0.08); border: 1px solid rgba(21,51,232,0.2);
    border-radius: 50px; padding: 0.28rem 0.85rem;
    font-size: 0.7rem; font-weight: 500; color: #1533E8;
}}
.brief-chip-label {{
    font-size: 0.58rem; font-weight: 700; letter-spacing: 0.12em;
    text-transform: uppercase; opacity: 0.6; margin-right: 2px;
    font-family: 'Space Mono', monospace;
}}
</style>
"""

# Pages definition: (key, label, description)
PAGES = [
    ("brief",  "Assignment Brief",   "Paste a project brief — Claude extracts themes and finds images"),
    ("search", "AI Reference Search","Generate targeted queries from a quick brief"),
    ("filter", "Filter & Browse",    "Pick tags to browse images without prompts"),
    ("browse", "Browse Images",      "Pull photos directly from Unsplash & Pexels"),
    ("score",  "Score Image URLs",   "Paste URLs and Claude rates them for render-readiness"),
]

def sidebar_nav(current_page):
    """Render sidebar with app logo + bubble navigation."""
    with st.sidebar:
        st.markdown("""
        <div style="padding:0.2rem 0 1rem;">
            <div style="font-size:0.58rem;letter-spacing:0.2em;text-transform:uppercase;
                        color:#1533E8;font-weight:700;font-family:'Space Mono',monospace;
                        margin-bottom:0.3rem;">Tool</div>
            <div style="font-size:1.3rem;font-weight:600;letter-spacing:-0.03em;color:#0C0C12;">
                Render Finder</div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Home", key="nav_home",
                     type="primary" if current_page == "home" else "secondary",
                     use_container_width=True):
            st.session_state.page = "home"
            st.rerun()

        for key, label, _ in PAGES:
            btn_type = "primary" if current_page == key else "secondary"
            if st.button(label, key=f"nav_{key}", type=btn_type, use_container_width=True):
                st.session_state.page = key
                st.rerun()

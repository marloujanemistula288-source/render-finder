import streamlit as st
import anthropic
import urllib.parse
import os, csv, io, re, requests
from PIL import Image
from colorthief import ColorThief
from dotenv import load_dotenv
from collections import Counter

load_dotenv()

st.set_page_config(page_title="Render Finder", layout="wide", initial_sidebar_state="collapsed")

# ── Session state ──────────────────────────────────────────────────────────────
_defaults = {
    "history": [], "selected_images": [], "comparison_images": [],
    "browse_results": [], "filter_results": [], "generated_queries": [],
    "brief_space": "", "brief_style": "Dreamy",
    "brief_mood": "", "brief_background": "White/Isolated",
    "template_selector": "— Choose a template —",
    "page": "Brief",
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

PAGES = ["Brief", "Search", "Browse", "Palette", "Board", "Prompt"]
STYLE_OPTIONS = ["Dreamy", "Dark Moody", "Minimal", "Maximalist", "Realistic CGI"]
BG_OPTIONS    = ["White/Isolated", "Scene", "Any"]
FILTER_SPACES = ["Living Room","Bedroom","Kitchen","Office","Courtyard","Exterior","Dining Room","Studio","Bathroom"]
FILTER_STYLES = ["Dreamy","Minimal","Dark Moody","Maximalist","Brutalist","Japandi","Bohemian","Industrial","Coastal"]
FILTER_MOODS  = ["Warm","Cool","Cozy","Editorial","Raw","Airy","Dramatic","Serene","Earthy","Luxe"]
FILTER_LIGHTS = ["Natural Light","Golden Hour","Night Scene","Overcast","Candlelight","Diffused","Artificial"]
TEMPLATES = {
    "— Choose a template —": None,
    "Warm Scandinavian Interior": {"space":"living room","style":"Minimal","mood":"warm, hygge, soft diffused light","background":"Scene"},
    "Dark Industrial Loft":       {"space":"loft apartment","style":"Dark Moody","mood":"raw, editorial, exposed concrete","background":"Scene"},
    "Dreamy Exterior Courtyard":  {"space":"outdoor courtyard","style":"Dreamy","mood":"hazy, atmospheric, lush greenery","background":"Scene"},
    "Maximalist Living Room":     {"space":"living room","style":"Maximalist","mood":"layered, eclectic, rich jewel tones","background":"Scene"},
    "Clean White Kitchen":        {"space":"kitchen","style":"Minimal","mood":"bright, airy, clinical precision","background":"White/Isolated"},
    "Warm Terracotta Bedroom":    {"space":"bedroom","style":"Dreamy","mood":"earthy, cozy, Mediterranean warmth","background":"Scene"},
    "Brutalist Office Lobby":     {"space":"office lobby","style":"Realistic CGI","mood":"monumental, raw concrete, dramatic","background":"Scene"},
}
STOP_WORDS = {"a","an","the","and","or","for","with","in","on","at","to","of","from","by","as","is","are","that","this","be","was","were","it","its","interior","design","photography","photo","image","render","photoshop","reference","style","space","mood","background","high","end","modern","contemporary","architectural","architecture"}

def get_secret(k):
    return st.secrets.get(k) or os.getenv(k)

client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

# ── Navigation (session state only — never HTML links) ─────────────────────────
page = st.session_state.page

def go_to(p):
    st.session_state.page = p
    st.rerun()

# ── Helpers ────────────────────────────────────────────────────────────────────
def search_unsplash(query, n=9):
    key = get_secret("UNSPLASH_ACCESS_KEY")
    if not key: return []
    try:
        r = requests.get("https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": n, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {key}"}, timeout=10)
        if r.status_code != 200: return []
        return [{"thumb": p["urls"]["small"], "full": p["urls"]["regular"],
                 "link": p["links"]["html"], "author": p["user"]["name"], "source": "unsplash"}
                for p in r.json().get("results", [])]
    except: return []

def search_pexels(query, n=9):
    key = get_secret("PEXELS_API_KEY")
    if not key: return []
    try:
        r = requests.get("https://api.pexels.com/v1/search",
            params={"query": query, "per_page": n, "orientation": "landscape"},
            headers={"Authorization": key}, timeout=10)
        if r.status_code != 200: return []
        return [{"thumb": p["src"]["medium"], "full": p["src"]["large"],
                 "link": p["url"], "author": p["photographer"], "source": "pexels"}
                for p in r.json().get("photos", [])]
    except: return []

def extract_palette(url, n=6):
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        ct = ColorThief(io.BytesIO(r.content))
        return [f"#{rv:02x}{g:02x}{b:02x}" for rv, g, b in ct.get_palette(color_count=n, quality=1)]
    except: return []

def create_moodboard(images, cols=3, tw=400, th=280, gap=10):
    imgs = []
    for d in images:
        try:
            r = requests.get(d.get("full", d["thumb"]), timeout=10)
            img = Image.open(io.BytesIO(r.content)).convert("RGB").resize((tw, th), Image.LANCZOS)
            imgs.append(img)
        except: pass
    if not imgs: return None
    rows = (len(imgs) + cols - 1) // cols
    board = Image.new("RGB", (cols*(tw+gap)+gap, rows*(th+gap)+gap), (240,243,255))
    for i, img in enumerate(imgs):
        r2, c = divmod(i, cols)
        board.paste(img, (c*(tw+gap)+gap, r2*(th+gap)+gap))
    buf = io.BytesIO(); board.save(buf, "PNG"); return buf.getvalue()

def extract_keywords(texts):
    words = [w for t in texts for w in re.findall(r'\b[a-zA-Z]{4,}\b', t.lower())]
    return [w for w, _ in Counter(w for w in words if w not in STOP_WORDS).most_common(14)]

def on_template_change():
    c = st.session_state.template_selector
    if c != "— Choose a template —" and TEMPLATES.get(c):
        t = TEMPLATES[c]
        st.session_state.brief_space      = t["space"]
        st.session_state.brief_style      = t["style"]
        st.session_state.brief_mood       = t["mood"]
        st.session_state.brief_background = t["background"]
        st.session_state.template_selector = "— Choose a template —"

def render_image_grid(images, key_prefix="img"):
    cols3 = st.columns(3)
    for i, img in enumerate(images):
        bc = "badge-unsplash" if img["source"] == "unsplash" else "badge-pexels"
        bl = "Unsplash"       if img["source"] == "unsplash" else "Pexels"
        on_board   = any(x["thumb"] == img["thumb"] for x in st.session_state.selected_images)
        on_compare = any(x["thumb"] == img["thumb"] for x in st.session_state.comparison_images)
        with cols3[i % 3]:
            st.image(img["thumb"], use_container_width=True)
            st.markdown(f'<span class="badge {bc}">{bl}</span> '
                        f'<a href="{img["link"]}" target="_blank" '
                        f'style="font-size:0.74rem;color:#3D5299;text-decoration:none;">'
                        f'{img["author"]}</a>', unsafe_allow_html=True)
            ca, cb = st.columns(2)
            with ca:
                if st.button("✓ Board" if on_board else "+ Board",
                             key=f"{key_prefix}_b_{i}", use_container_width=True):
                    if not on_board: st.session_state.selected_images.append(img)
                    else: st.session_state.selected_images = [x for x in st.session_state.selected_images if x["thumb"] != img["thumb"]]
                    st.rerun()
            with cb:
                if st.button("✓ Cmp" if on_compare else "Compare",
                             key=f"{key_prefix}_c_{i}", use_container_width=True):
                    if on_compare: st.session_state.comparison_images = [x for x in st.session_state.comparison_images if x["thumb"] != img["thumb"]]
                    elif len(st.session_state.comparison_images) < 2: st.session_state.comparison_images.append(img)
                    else: st.session_state.comparison_images = [st.session_state.comparison_images[1], img]
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,300;1,400&display=swap');
*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

header[data-testid="stHeader"], [data-testid="stSidebar"],
[data-testid="collapsedControl"], footer, #MainMenu { display: none !important; }

/* App background */
.stApp { background-color: #F2F3F9; min-height: 100vh; }

/* Blue blob */
.zn-blob {
    position: fixed; top: -8%; right: -6%;
    width: 62vw; height: 115vh;
    background: radial-gradient(ellipse at 48% 42%,
        #0A1FCC 0%, #1330CC 12%, #1A3AE0 24%,
        rgba(22,53,220,0.72) 38%, rgba(18,44,200,0.38) 55%,
        rgba(15,35,170,0.12) 70%, transparent 82%);
    border-radius: 58% 42% 52% 48% / 44% 56% 44% 56%;
    pointer-events: none; z-index: 1;
}
.zn-blob::after {
    content: ''; position: absolute; inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 300 300' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
    background-size: 250px 250px; opacity: 0.07; mix-blend-mode: overlay;
    border-radius: inherit; pointer-events: none;
}
.zn-bottom-fade {
    position: fixed; bottom: 0; left: 0; right: 0; height: 38vh;
    background: linear-gradient(to top, rgba(14,30,160,0.42) 0%, transparent 100%);
    pointer-events: none; z-index: 1;
}

/* Topbar row — styled via CSS, scrolls with page (no JS needed) */
.zn-topbar-wrap {
    background: rgba(242,243,249,0.94);
    backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
    border-bottom: 1px solid rgba(22,53,204,0.07);
    margin: -1.5rem -3.5rem 1.5rem -3.5rem;
    padding: 0 3.5rem;
    min-height: 62px;
    display: flex; align-items: center;
    position: relative; z-index: 100;
}

/* Main container */
.main .block-container {
    padding-top: 1.5rem !important; padding-left: 3.5rem !important;
    padding-right: 3.5rem !important; padding-bottom: 4rem !important;
    max-width: 100% !important; position: relative; z-index: 10;
}

/* ── Nav link buttons (marker-div targeting) ──
   Usage: render <div class="znav [active]"></div> immediately before st.button()
   The CSS adjacent-sibling selector styles that specific button.              */
div.znav + [data-testid="stButton"] > button {
    background: transparent !important; border: none !important;
    box-shadow: none !important; color: #8892C0 !important;
    font-size: 0.74rem !important; font-weight: 500 !important;
    letter-spacing: 0.07em !important; text-transform: uppercase !important;
    padding: 0 0.3rem !important; height: 62px !important;
    border-radius: 0 !important; width: 100% !important;
    border-bottom: 2px solid transparent !important;
    transition: color 0.18s !important;
}
div.znav + [data-testid="stButton"] > button:hover {
    color: #0D1F8A !important; background: transparent !important;
}
div.znav.active + [data-testid="stButton"] > button {
    color: #0D1F8A !important; border-bottom-color: #0D1F8A !important;
}

/* Logo area */
.zn-logo-area {
    display: flex; align-items: center; gap: 9px;
    font-size: 0.82rem; font-weight: 700; letter-spacing: 0.1em;
    color: #0D1F8A; padding: 0; line-height: 62px;
    white-space: nowrap;
}

/* Connect / BRIEF button in topbar */
div.znav-connect + [data-testid="stButton"] > button {
    background: #0D1F8A !important; color: #fff !important;
    border: none !important; border-radius: 50px !important;
    font-size: 0.74rem !important; font-weight: 600 !important;
    letter-spacing: 0.07em !important; text-transform: uppercase !important;
    padding: 0.38rem 1.1rem !important; height: auto !important;
    min-height: 36px !important;
    box-shadow: 0 3px 14px rgba(13,31,138,0.28) !important;
    transition: background 0.18s !important;
}
div.znav-connect + [data-testid="stButton"] > button:hover {
    background: #1635CC !important;
}

/* ── Floating pill buttons (right column on Brief page) ──
   Usage: render <div class="znfp [active]"></div> before st.button()          */
div.znfp + [data-testid="stButton"] > button {
    background: rgba(255,255,255,0.72) !important;
    border: 1px solid rgba(255,255,255,0.88) !important;
    border-radius: 50px !important; color: #0D1F8A !important;
    font-size: 0.86rem !important; font-weight: 500 !important;
    padding: 0.7rem 1.5rem !important; min-height: 50px !important;
    backdrop-filter: blur(16px) !important;
    box-shadow: 0 4px 22px rgba(0,0,0,0.09) !important;
    justify-content: flex-start !important; text-align: left !important;
    margin-bottom: 0 !important; width: 100% !important;
    transition: all 0.2s !important;
}
div.znfp + [data-testid="stButton"] > button:hover {
    background: rgba(255,255,255,0.92) !important;
    box-shadow: 0 6px 28px rgba(0,0,0,0.13) !important;
    transform: translateX(-3px) !important;
}
div.znfp.active + [data-testid="stButton"] > button {
    background: #0D1F8A !important; color: white !important;
    border-color: #0D1F8A !important;
    box-shadow: 0 6px 28px rgba(13,31,138,0.42) !important;
}

/* ── Primary / secondary CTA buttons ── */
.stButton > button[kind="primary"] {
    background: #0D1F8A !important; color: #fff !important;
    border: none !important; border-radius: 50px !important;
    font-family: 'Inter', sans-serif !important; font-weight: 600 !important;
    font-size: 0.76rem !important; letter-spacing: 0.07em !important;
    text-transform: uppercase !important; padding: 0.55rem 1.6rem !important;
    box-shadow: 0 4px 18px rgba(13,31,138,0.30) !important; transition: all 0.18s !important;
}
.stButton > button[kind="primary"]:hover {
    background: #1635CC !important;
    box-shadow: 0 6px 22px rgba(13,31,138,0.42) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"] {
    background: rgba(255,255,255,0.78) !important; color: #0D1F8A !important;
    border: 1.5px solid rgba(13,31,138,0.28) !important; border-radius: 50px !important;
    font-family: 'Inter', sans-serif !important; font-weight: 500 !important;
    font-size: 0.76rem !important; letter-spacing: 0.07em !important;
    text-transform: uppercase !important; backdrop-filter: blur(8px) !important;
}
.stButton > button[kind="secondary"]:hover {
    background: rgba(13,31,138,0.06) !important; border-color: #0D1F8A !important;
}
.stDownloadButton > button {
    background: rgba(255,255,255,0.82) !important; color: #0D1F8A !important;
    border: 1.5px solid rgba(13,31,138,0.25) !important; border-radius: 50px !important;
    font-family: 'Inter', sans-serif !important; font-size: 0.76rem !important;
}

/* ── Inputs ── */
input, textarea, [data-testid="stTextInput"] input {
    background: rgba(255,255,255,0.88) !important;
    border: 1.5px solid rgba(13,31,138,0.16) !important;
    border-radius: 12px !important; color: #0D1F8A !important;
    font-family: 'Inter', sans-serif !important;
}
input:focus, textarea:focus {
    border-color: #0D1F8A !important;
    box-shadow: 0 0 0 3px rgba(13,31,138,0.1) !important;
}
[data-testid="stSelectbox"] > div > div {
    background: rgba(255,255,255,0.88) !important;
    border: 1.5px solid rgba(13,31,138,0.16) !important;
    border-radius: 12px !important; color: #0D1F8A !important;
}
label { color: #3D5299 !important; font-size: 0.8rem !important; }

/* ── Glass cards ── */
.zn-card {
    background: rgba(255,255,255,0.48);
    backdrop-filter: blur(22px); -webkit-backdrop-filter: blur(22px);
    border: 1px solid rgba(255,255,255,0.82);
    border-radius: 24px; padding: 1.7rem 2rem;
    box-shadow: 0 4px 32px rgba(13,31,138,0.07);
    position: relative; z-index: 10;
}
.zn-card-label {
    font-size: 0.67rem; letter-spacing: 0.14em; text-transform: uppercase;
    color: #1635CC; font-weight: 700; margin-bottom: 1.1rem;
    font-family: 'Inter', sans-serif;
}

/* ── Hero ── */
.zn-hero { padding: 1rem 0 1.8rem; position: relative; z-index: 10; }
.zn-badge-pill {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 0.38rem 1.05rem;
    background: rgba(255,255,255,0.75); backdrop-filter: blur(10px);
    border: 1px solid rgba(22,53,204,0.14); border-radius: 50px;
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.11em;
    color: #0D1F8A; margin-bottom: 1.5rem; font-family: 'Inter', sans-serif;
}
.zn-headline {
    font-size: 3.4rem !important; font-weight: 800 !important;
    color: #0D1F8A !important; letter-spacing: -0.03em;
    line-height: 1.07 !important; margin-bottom: 1.3rem !important;
    font-family: 'Inter', sans-serif !important;
}
.zn-headline em { font-weight: 300 !important; font-style: italic; }
.zn-hero-body {
    font-size: 0.88rem; line-height: 1.72; color: #3D5299;
    max-width: 310px; margin-bottom: 2rem; font-family: 'Inter', sans-serif;
}

/* ── Stats grid ── */
.zn-stats-grid { display: flex; gap: 1.5rem; margin-bottom: 1rem; }
.zn-stat { text-align: center; flex: 1; }
.zn-stat-val { font-size: 1.9rem; font-weight: 700; color: #0D1F8A; font-family: 'Inter', sans-serif; line-height: 1; }
.zn-stat-lbl { font-size: 0.7rem; color: #8892C0; margin-top: 0.3rem; font-family: 'Inter', sans-serif; }

/* ── Page header for sub-pages ── */
.zn-page-header { margin-bottom: 2rem; position: relative; z-index: 10; }
.zn-page-title {
    font-size: 2.2rem !important; font-weight: 700 !important;
    color: #0D1F8A !important; letter-spacing: -0.02em;
    margin: 0.4rem 0 0.2rem !important; font-family: 'Inter', sans-serif !important;
}
.zn-badge-small {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 0.28rem 0.85rem;
    background: rgba(255,255,255,0.7); border: 1px solid rgba(13,31,138,0.14);
    border-radius: 50px; font-size: 0.67rem; font-weight: 600;
    letter-spacing: 0.12em; color: #1635CC; font-family: 'Inter', sans-serif;
    margin-bottom: 0.6rem;
}

/* ── Query cards ── */
.qcard {
    background: rgba(255,255,255,0.62); backdrop-filter: blur(16px);
    border: 1px solid rgba(255,255,255,0.85); border-radius: 20px;
    padding: 1.2rem 1.4rem 1rem; margin-bottom: 0.9rem;
    box-shadow: 0 2px 16px rgba(13,31,138,0.06);
}
.qcard-num  { font-size:0.67rem; color:#1635CC; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; }
.qcard-text { font-size:0.94rem; color:#0D1F8A; font-style:italic; margin:0.3rem 0 0.8rem; }
.preview-strip { display:flex; gap:0.45rem; margin-bottom:0.8rem; }
.preview-strip a  { flex:1; display:block; }
.preview-strip img{ width:100%; height:90px; object-fit:cover; border-radius:10px;
                    border:1px solid rgba(13,31,138,0.1); display:block; }
.preview-ph { flex:1; height:90px; background:rgba(13,31,138,0.04);
              border-radius:10px; border:1px solid rgba(13,31,138,0.08); }
.btn-row { display:flex; flex-wrap:wrap; gap:0.3rem; }
.ref-btn { display:inline-flex; align-items:center; padding:0.3rem 0.82rem;
           border-radius:50px; text-decoration:none !important;
           font-size:0.75rem; font-weight:500; font-family:'Inter',sans-serif;
           transition:all 0.18s; border:1px solid transparent; }
.ref-btn:hover { opacity:0.82; transform:translateY(-1px); }
.btn-p  { background:rgba(230,0,35,0.09);  color:#cc0020 !important; border-color:rgba(230,0,35,0.2); }
.btn-b  { background:rgba(23,105,255,0.09); color:#1769FF !important; border-color:rgba(23,105,255,0.2); }
.btn-g  { background:rgba(255,255,255,0.8); color:#0D1F8A !important; border-color:rgba(13,31,138,0.18); }
.btn-a  { background:rgba(13,31,138,0.07); color:#0D1F8A !important; border-color:rgba(13,31,138,0.18); }
.btn-r  { background:rgba(22,53,204,0.09); color:#1635CC !important; border-color:rgba(22,53,204,0.2); }

/* ── Misc ── */
.kw-tag { display:inline-block; padding:0.2rem 0.76rem; margin:0.14rem;
          background:rgba(13,31,138,0.07); border:1px solid rgba(13,31,138,0.16);
          border-radius:50px; font-size:0.77rem; color:#1635CC;
          font-family:'Inter',sans-serif; font-weight:500; }
.badge  { display:inline-block; padding:0.1rem 0.46rem; border-radius:20px;
          font-size:0.64rem; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; }
.badge-unsplash { background:rgba(13,31,138,0.09); color:#0D1F8A; }
.badge-pexels   { background:rgba(22,53,204,0.12); color:#1635CC; }
.filter-lbl { font-size:0.68rem; letter-spacing:0.12em; text-transform:uppercase;
              color:#3D5299; font-weight:600; margin:0.9rem 0 0.3rem; }
.swatch-row { display:flex; gap:0.85rem; flex-wrap:wrap; margin:1rem 0; }
.swatch { width:68px; text-align:center; }
.swatch-block { width:68px; height:60px; border-radius:14px;
                border:1px solid rgba(0,0,0,0.06); margin-bottom:0.32rem;
                box-shadow:0 2px 10px rgba(0,0,0,0.1); }
.swatch-hex { font-size:0.66rem; color:#3D5299; font-family:monospace; }
.prompt-box { background:rgba(255,255,255,0.82); border:1.5px solid rgba(13,31,138,0.15);
              border-radius:16px; padding:1.3rem 1.5rem; font-size:0.86rem; color:#0D1F8A;
              font-family:monospace; line-height:1.72; white-space:pre-wrap; }
.stSuccess { background:rgba(13,31,138,0.06) !important; color:#0D1F8A !important;
             border-left:4px solid #1635CC !important; border-radius:12px !important; }
.stInfo    { background:rgba(255,255,255,0.6) !important; color:#3D5299 !important;
             border-left:4px solid rgba(13,31,138,0.3) !important; border-radius:12px !important; }
.stWarning { background:rgba(255,195,0,0.1) !important; border-radius:12px !important; }
hr { border-color:rgba(13,31,138,0.09) !important; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# Background
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="zn-blob" aria-hidden="true"></div>'
            '<div class="zn-bottom-fade" aria-hidden="true"></div>',
            unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# Topbar  — Streamlit buttons styled as nav links via the marker-div trick
# JS makes the first stHorizontalBlock fixed via .zn-topnav class
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="zn-topbar-wrap">', unsafe_allow_html=True)
c_logo, c1, c2, c3, c4, c5, c6, c_conn = st.columns([2, 0.9, 0.9, 0.95, 0.95, 0.85, 0.85, 1.7])

with c_logo:
    st.markdown("""
    <div class="zn-logo-area">
      <svg width="17" height="17" viewBox="0 0 18 18" fill="none">
        <circle cx="9" cy="9" r="1.9" fill="#0D1F8A"/>
        <line x1="9" y1="1" x2="9" y2="4.5" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
        <line x1="9" y1="13.5" x2="9" y2="17" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
        <line x1="1" y1="9" x2="4.5" y2="9" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
        <line x1="13.5" y1="9" x2="17" y2="9" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
        <line x1="3.22" y1="3.22" x2="5.64" y2="5.64" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
        <line x1="12.36" y1="12.36" x2="14.78" y2="14.78" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
        <line x1="14.78" y1="3.22" x2="12.36" y2="5.64" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
        <line x1="5.64" y1="12.36" x2="3.22" y2="14.78" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
      </svg>
      RENDER FINDER
    </div>""", unsafe_allow_html=True)

nav_items = [("HOME","Brief"),("SEARCH","Search"),("BROWSE","Browse"),
             ("PALETTE","Palette"),("BOARD","Board"),("PROMPT","Prompt")]
for col, (label, p) in zip([c1,c2,c3,c4,c5,c6], nav_items):
    with col:
        active_cls = "znav active" if page == p else "znav"
        st.markdown(f'<div class="{active_cls}"></div>', unsafe_allow_html=True)
        if st.button(label, key=f"nav_{p}", use_container_width=True):
            go_to(p)

with c_conn:
    brief_lbl = (st.session_state.brief_space[:10]+"…"
                 if len(st.session_state.brief_space) > 10
                 else st.session_state.brief_space) if st.session_state.brief_space else "BRIEF"
    st.markdown('<div class="znav-connect"></div>', unsafe_allow_html=True)
    if st.button(f"{brief_lbl} ●", key="nav_connect", use_container_width=True):
        go_to("Brief")

st.markdown('</div>', unsafe_allow_html=True)  # close zn-topbar-wrap

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Brief  (Zeronode hero layout)
# ══════════════════════════════════════════════════════════════════════════════
if page == "Brief":
    hero_col, gap_col, pills_col = st.columns([4.5, 1, 2.5])

    with hero_col:
        st.markdown("""
        <div class="zn-hero">
          <div class="zn-badge-pill">● WHERE RENDERS BEGIN</div>
          <h1 class="zn-headline">Where every reference<br>finds its <em>render.</em></h1>
          <p class="zn-hero-body">
            Render Finder curates architectural and interior references from
            Pinterest, Behance, Unsplash, Pexels, and more — powered by Claude
            AI to match your exact brief.
          </p>
        </div>
        """, unsafe_allow_html=True)

        b1, b2, _ = st.columns([2.4, 2, 2])
        with b1:
            if st.button("FIND REFERENCES →", type="primary", key="cta_find", use_container_width=True):
                if not st.session_state.brief_space or not st.session_state.brief_mood:
                    st.warning("Fill in Space and Mood in the brief below first.")
                else:
                    brief = {k: st.session_state[f"brief_{k}"] for k in ["space","style","mood","background"]}
                    if not st.session_state.history or st.session_state.history[0] != brief:
                        st.session_state.history.insert(0, brief)
                        st.session_state.history = st.session_state.history[:5]
                    go_to("Search")
        with b2:
            if st.button("BROWSE IMAGES", key="cta_browse", use_container_width=True):
                go_to("Browse")

    # Three floating right pills (Transparency / Regeneration / Intelligence equivalent)
    with pills_col:
        st.markdown("<div style='padding-top:4rem'>", unsafe_allow_html=True)
        fp_items = [
            ("⊕  Search Refs",   "Search"),
            ("⊟  Browse Images", "Browse"),
            ("✦  AI Prompt",     "Prompt"),
        ]
        for label, p in fp_items:
            active_cls = "znfp active" if page == p else "znfp"
            st.markdown(f'<div class="{active_cls}"></div>', unsafe_allow_html=True)
            if st.button(label, key=f"fp_{p}", use_container_width=True):
                go_to(p)
        st.markdown("</div>", unsafe_allow_html=True)

    # Bottom glass cards
    st.markdown("<div style='height:3rem'></div>", unsafe_allow_html=True)
    card_l, _, card_r = st.columns([4.5, 0.4, 2.6])

    with card_l:
        st.markdown('<div class="zn-card">', unsafe_allow_html=True)
        st.markdown('<div class="zn-card-label">YOUR BRIEF</div>', unsafe_allow_html=True)
        st.selectbox("template", list(TEMPLATES.keys()), key="template_selector",
                     on_change=on_template_change, label_visibility="collapsed")
        ci1, ci2 = st.columns(2)
        with ci1:
            st.text_input("Space", placeholder="e.g. living room", key="brief_space")
        with ci2:
            st.selectbox("Style", STYLE_OPTIONS, key="brief_style")
        st.text_input("Mood", placeholder="e.g. warm, earthy, editorial", key="brief_mood")
        st.markdown("</div>", unsafe_allow_html=True)

    with card_r:
        st.markdown('<div class="zn-card">', unsafe_allow_html=True)
        st.markdown('<div class="zn-card-label">SESSION</div>', unsafe_allow_html=True)
        n_b = len(st.session_state.selected_images)
        n_h = len(st.session_state.history)
        n_q = len(st.session_state.generated_queries)
        st.markdown(f"""
        <div class="zn-stats-grid">
          <div class="zn-stat"><div class="zn-stat-val">{n_b}</div><div class="zn-stat-lbl">Board</div></div>
          <div class="zn-stat"><div class="zn-stat-val">{n_h}</div><div class="zn-stat-lbl">Briefs</div></div>
          <div class="zn-stat"><div class="zn-stat-val">{n_q}</div><div class="zn-stat-lbl">Queries</div></div>
        </div>""", unsafe_allow_html=True)
        if st.session_state.history:
            last = st.session_state.history[0]
            st.markdown(f"<div style='font-size:0.77rem;color:#3D5299;margin-top:0.4rem'>"
                        f"Last: {last['space']} · {last['style']}</div>", unsafe_allow_html=True)
        if n_b:
            if st.button("Open Mood Board →", use_container_width=True):
                go_to("Board")
        st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Search
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Search":
    st.markdown('<div class="zn-page-header"><div class="zn-badge-small">● AI-GENERATED</div>'
                '<h2 class="zn-page-title">Reference Queries</h2></div>', unsafe_allow_html=True)

    if st.button("Generate Queries", type="primary"):
        sp = st.session_state.brief_space; mo = st.session_state.brief_mood
        if not sp or not mo:
            st.warning("Go to **Home** and fill in Space and Mood first.")
        else:
            sty = st.session_state.brief_style; bg = st.session_state.brief_background
            brief = {"space":sp,"style":sty,"mood":mo,"background":bg}
            if not st.session_state.history or st.session_state.history[0] != brief:
                st.session_state.history.insert(0,brief); st.session_state.history = st.session_state.history[:5]
            prompt = (f"Generate 5 targeted search queries for a designer finding Photoshop render references. "
                      f"Brief — Space: {sp}, Style: {sty}, Mood: {mo}, Background: {bg}. "
                      f"Use designer vocabulary. Return numbered list only, no extra text.")
            with st.spinner("Generating queries..."):
                resp = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=512,
                    messages=[{"role":"user","content":prompt}])
            st.session_state.generated_queries = [l.strip() for l in resp.content[0].text.strip().splitlines() if l.strip()]

    if st.session_state.generated_queries:
        lines = st.session_state.generated_queries
        has_keys = bool(get_secret("UNSPLASH_ACCESS_KEY") or get_secret("PEXELS_API_KEY"))
        kws = extract_keywords([l.lstrip("0123456789. ").strip('"') for l in lines])
        if kws:
            st.markdown("<div style='margin-bottom:1.4rem'>" +
                        "".join(f"<span class='kw-tag'>{w}</span>" for w in kws) +
                        "</div>", unsafe_allow_html=True)
        for i, line in enumerate(lines, 1):
            qt  = line.lstrip("0123456789. ").strip('"')
            enc = urllib.parse.quote_plus(qt)
            previews = []
            if has_keys:
                previews = search_unsplash(qt, n=3)
                if len(previews) < 3: previews += search_pexels(qt, n=3-len(previews))
            strip = ""
            if previews:
                strip = '<div class="preview-strip">' + "".join(
                    f'<a href="{p["link"]}" target="_blank"><img src="{p["thumb"]}" alt=""></a>'
                    for p in previews[:3]) + "</div>"
            elif has_keys:
                strip = '<div class="preview-strip">' + '<div class="preview-ph"></div>'*3 + "</div>"
            st.markdown(f"""
            <div class="qcard">
              <div class="qcard-num">Query {i}</div>
              <div class="qcard-text">{qt}</div>
              {strip}
              <div class="btn-row">
                <a class="ref-btn btn-p" href="https://www.pinterest.com/search/pins/?q={enc}" target="_blank">Pinterest</a>
                <a class="ref-btn btn-b" href="https://www.behance.net/search/projects?search={enc}" target="_blank">Behance</a>
                <a class="ref-btn btn-g" href="https://www.google.com/search?tbm=isch&q={enc}" target="_blank">Google Images</a>
                <a class="ref-btn btn-a" href="https://archinect.com/search#/?q={enc}&type=photos" target="_blank">Archinect</a>
                <a class="ref-btn btn-r" href="https://www.are.na/search/{enc}" target="_blank">Are.na</a>
              </div>
            </div>""", unsafe_allow_html=True)
        if not has_keys:
            st.info("Add **UNSPLASH_ACCESS_KEY** or **PEXELS_API_KEY** to secrets for image previews.")
        st.success(f"{len(lines)} queries generated.")
    else:
        st.info("Click **Generate Queries** to create AI-powered search queries from your brief.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Browse
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Browse":
    st.markdown('<div class="zn-page-header"><div class="zn-badge-small">● NO AI NEEDED</div>'
                '<h2 class="zn-page-title">Browse & Filter</h2></div>', unsafe_allow_html=True)

    st.markdown("<div class='filter-lbl'>Space</div>", unsafe_allow_html=True)
    sel_spaces = st.pills("spaces", FILTER_SPACES, selection_mode="multi", label_visibility="collapsed")
    st.markdown("<div class='filter-lbl'>Style</div>", unsafe_allow_html=True)
    sel_styles = st.pills("styles", FILTER_STYLES, selection_mode="multi", label_visibility="collapsed")
    st.markdown("<div class='filter-lbl'>Mood</div>", unsafe_allow_html=True)
    sel_moods  = st.pills("moods",  FILTER_MOODS,  selection_mode="multi", label_visibility="collapsed")
    st.markdown("<div class='filter-lbl'>Lighting</div>", unsafe_allow_html=True)
    sel_lights = st.pills("lights", FILTER_LIGHTS, selection_mode="multi", label_visibility="collapsed")

    st.markdown("<br>", unsafe_allow_html=True)
    fa, fb = st.columns([2, 5])
    with fa:
        filter_btn = st.button("Browse Images", type="primary", use_container_width=True)
    with fb:
        tags = list(sel_spaces or []) + list(sel_styles or []) + list(sel_moods or []) + list(sel_lights or [])
        if tags:
            st.markdown(f"<div style='padding-top:0.55rem;color:#1635CC;font-size:0.82rem;'>"
                        f"Query: <em>{', '.join(tags)}</em></div>", unsafe_allow_html=True)

    if filter_btn:
        tags = list(sel_spaces or []) + list(sel_styles or []) + list(sel_moods or []) + list(sel_lights or [])
        if not tags:
            st.warning("Select at least one filter.")
        elif not get_secret("UNSPLASH_ACCESS_KEY") and not get_secret("PEXELS_API_KEY"):
            st.warning("Add image API keys to Streamlit secrets.")
        else:
            q = " ".join(tags) + " interior architecture"
            with st.spinner("Fetching images..."):
                st.session_state.filter_results = search_unsplash(q, n=9) + search_pexels(q, n=9)

    fa2, _ = st.columns([2, 5])
    with fa2:
        if st.button("Browse from Brief", use_container_width=True):
            sp = st.session_state.brief_space; mo = st.session_state.brief_mood
            if not sp or not mo: st.warning("Set a brief on the Home page first.")
            elif not get_secret("UNSPLASH_ACCESS_KEY") and not get_secret("PEXELS_API_KEY"):
                st.warning("Add image API keys to Streamlit secrets.")
            else:
                q = f"{st.session_state.brief_style} {sp} {mo} interior architecture"
                with st.spinner("Fetching images..."):
                    st.session_state.browse_results = search_unsplash(q, n=9) + search_pexels(q, n=9)

    results = st.session_state.filter_results or st.session_state.browse_results
    if results:
        st.markdown(f"<p style='color:#3D5299;font-size:0.82rem;margin:1rem 0'>"
                    f"Showing {len(results)} images</p>", unsafe_allow_html=True)
        render_image_grid(results, key_prefix="br")
        if len(st.session_state.comparison_images) == 2:
            st.divider()
            st.markdown('<div class="zn-badge-small">● COMPARISON</div>', unsafe_allow_html=True)
            ca, cb = st.columns(2)
            for col, img in zip([ca, cb], st.session_state.comparison_images):
                with col:
                    st.caption(f"{img['source'].upper()} — {img['author']}")
                    st.image(img["full"], use_container_width=True)
            if st.button("Clear comparison"):
                st.session_state.comparison_images = []; st.rerun()
    else:
        st.info("Select filters and click **Browse Images**, or use **Browse from Brief**.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Palette
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Palette":
    st.markdown('<div class="zn-page-header"><div class="zn-badge-small">● COLOR EXTRACTION</div>'
                '<h2 class="zn-page-title">Palette Extractor</h2></div>', unsafe_allow_html=True)
    st.markdown('<div class="zn-card">', unsafe_allow_html=True)
    palette_url = st.text_input("Image URL", placeholder="https://images.unsplash.com/photo-...")
    n_colors = st.slider("Number of colors", 3, 10, 6)
    if st.button("Extract Palette", type="primary"):
        if not palette_url.strip():
            st.warning("Paste an image URL first.")
        else:
            with st.spinner("Extracting..."):
                hexes = extract_palette(palette_url.strip(), n=n_colors)
            if not hexes:
                st.warning("Could not extract palette — try a direct image URL (.jpg/.png).")
            else:
                st.markdown(
                    "<div class='swatch-row'>" +
                    "".join(f"<div class='swatch'><div class='swatch-block' style='background:{h}'></div>"
                             f"<div class='swatch-hex'>{h}</div></div>" for h in hexes) +
                    "</div>", unsafe_allow_html=True)
                dl_col, _ = st.columns([1,3])
                with dl_col:
                    st.download_button("Download CSV", ",".join(hexes).encode(), "palette.csv", "text/csv")
                st.success(f"Extracted {len(hexes)} colors.")
    st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Board
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Board":
    st.markdown('<div class="zn-page-header"><div class="zn-badge-small">● EXPORT</div>'
                '<h2 class="zn-page-title">Mood Board</h2></div>', unsafe_allow_html=True)
    if not st.session_state.selected_images:
        st.info("Browse images on **Browse** and click **+ Board** to add them here.")
    else:
        imgs = st.session_state.selected_images
        st.markdown(f"<p style='color:#3D5299;font-size:0.88rem'>{len(imgs)} image(s) selected</p>",
                    unsafe_allow_html=True)
        prev_cols = st.columns(min(len(imgs), 4))
        for i, img in enumerate(imgs):
            with prev_cols[i % 4]:
                st.image(img["thumb"], use_container_width=True)
                if st.button("Remove", key=f"rm_{i}", use_container_width=True):
                    st.session_state.selected_images.pop(i); st.rerun()
        st.divider()
        gc1, gc2, gc3 = st.columns([1.2, 1.5, 2])
        with gc1:
            mb_cols = st.selectbox("Grid columns", [2,3,4], index=1)
        with gc2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Generate Mood Board", type="primary", use_container_width=True):
                with st.spinner("Compositing..."):
                    png = create_moodboard(imgs, cols=mb_cols)
                if png:
                    st.image(png)
                    st.download_button("Download PNG", png, "moodboard.png", "image/png", use_container_width=True)
                    st.success("Mood board ready.")
                else:
                    st.warning("Could not load images.")
        with gc3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Clear All", use_container_width=True):
                st.session_state.selected_images = []; st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Prompt
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Prompt":
    st.markdown('<div class="zn-page-header"><div class="zn-badge-small">● AI GENERATION</div>'
                '<h2 class="zn-page-title">Prompt Generator</h2></div>', unsafe_allow_html=True)
    platform = st.radio("Platform", ["Midjourney", "Stable Diffusion", "Both"], horizontal=True)

    p_space = st.session_state.brief_space or ""
    p_style = st.session_state.brief_style
    p_mood  = st.session_state.brief_mood  or ""
    p_bg    = st.session_state.brief_background

    with st.expander("Override brief for this prompt"):
        oc1, oc2 = st.columns(2)
        with oc1:
            p_space = st.text_input("Space",  value=p_space, key="ps")
            p_style = st.selectbox("Style",   STYLE_OPTIONS,
                                   index=STYLE_OPTIONS.index(p_style) if p_style in STYLE_OPTIONS else 0, key="pst")
        with oc2:
            p_mood  = st.text_input("Mood",   value=p_mood,  key="pm")
            p_bg    = st.selectbox("Background", BG_OPTIONS,
                                   index=BG_OPTIONS.index(p_bg) if p_bg in BG_OPTIONS else 0, key="pb")

    if st.button("Generate Prompt", type="primary"):
        if not p_space or not p_mood:
            st.warning("Fill in Space and Mood (in Home brief or override above).")
        else:
            if platform == "Midjourney":
                instr = "Generate a detailed Midjourney prompt only. End with --ar 16:9 --v 6.1 --style raw"
            elif platform == "Stable Diffusion":
                instr = ("Generate a Stable Diffusion prompt with positive comma-separated tags, "
                         "then a blank line, then 'Negative prompt:' with negative tags.")
            else:
                instr = ("Generate both:\n1) Midjourney prompt (end with --ar 16:9 --v 6.1 --style raw)\n"
                         "2) Stable Diffusion prompt with positive tags and Negative prompt: line.")
            full = (f"{instr}\nBrief: Space: {p_space}, Style: {p_style}, Mood: {p_mood}, Background: {p_bg}.\n"
                    f"Include camera angle, lighting quality, material palette, atmosphere, color grading.")
            with st.spinner("Crafting prompt..."):
                resp = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=600,
                    messages=[{"role":"user","content":full}])
            result = resp.content[0].text.strip()
            st.markdown(f"<div class='prompt-box'>{result}</div>", unsafe_allow_html=True)
            dl_col, _ = st.columns([1,3])
            with dl_col:
                st.download_button("Download .txt", result.encode(), "prompt.txt", "text/plain")
            st.success("Prompt ready.")
    else:
        st.info("Set your brief on the **Home** page then click **Generate Prompt**.")

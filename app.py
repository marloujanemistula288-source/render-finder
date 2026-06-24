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
    "nav_pills": "Brief",
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Constants ──────────────────────────────────────────────────────────────────
STYLE_OPTIONS  = ["Dreamy", "Dark Moody", "Minimal", "Maximalist", "Realistic CGI"]
BG_OPTIONS     = ["White/Isolated", "Scene", "Any"]
FILTER_SPACES  = ["Living Room","Bedroom","Kitchen","Office","Courtyard","Exterior","Dining Room","Studio","Bathroom","Hallway"]
FILTER_STYLES  = ["Dreamy","Minimal","Dark Moody","Maximalist","Brutalist","Japandi","Bohemian","Industrial","Coastal","Rustic"]
FILTER_MOODS   = ["Warm","Cool","Cozy","Editorial","Raw","Airy","Dramatic","Serene","Earthy","Luxe"]
FILTER_LIGHTS  = ["Natural Light","Golden Hour","Night Scene","Overcast","Candlelight","Diffused","Artificial"]
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
STOP_WORDS = {
    "a","an","the","and","or","for","with","in","on","at","to","of","from","by","as","is",
    "are","that","this","be","was","were","it","its","interior","design","photography",
    "photo","image","render","photoshop","reference","style","space","mood","background",
    "high","end","modern","contemporary","architectural","architecture","inspired","using",
}

def get_secret(k):
    return st.secrets.get(k) or os.getenv(k)

client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

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
    choice = st.session_state.template_selector
    if choice != "— Choose a template —" and TEMPLATES.get(choice):
        t = TEMPLATES[choice]
        st.session_state.brief_space      = t["space"]
        st.session_state.brief_style      = t["style"]
        st.session_state.brief_mood       = t["mood"]
        st.session_state.brief_background = t["background"]
        st.session_state.template_selector = "— Choose a template —"

def go_to(page):
    st.session_state.nav_pills = page
    st.rerun()

def render_image_grid(images, key_prefix="img"):
    cols3 = st.columns(3)
    for i, img in enumerate(images):
        badge_cls = "badge-unsplash" if img["source"] == "unsplash" else "badge-pexels"
        badge_lbl = "Unsplash"       if img["source"] == "unsplash" else "Pexels"
        already_board   = any(x["thumb"] == img["thumb"] for x in st.session_state.selected_images)
        already_compare = any(x["thumb"] == img["thumb"] for x in st.session_state.comparison_images)
        with cols3[i % 3]:
            st.image(img["thumb"], use_container_width=True)
            st.markdown(
                f'<span class="badge {badge_cls}">{badge_lbl}</span> '
                f'<a href="{img["link"]}" target="_blank" '
                f'style="font-size:0.75rem;color:#3D5299;text-decoration:none;">'
                f'{img["author"]}</a>', unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✓ Board" if already_board else "+ Board",
                             key=f"{key_prefix}_board_{i}", use_container_width=True):
                    if not already_board:
                        st.session_state.selected_images.append(img)
                    else:
                        st.session_state.selected_images = [
                            x for x in st.session_state.selected_images if x["thumb"] != img["thumb"]]
                    st.rerun()
            with c2:
                if st.button("✓ Cmp" if already_compare else "Compare",
                             key=f"{key_prefix}_cmp_{i}", use_container_width=True):
                    if already_compare:
                        st.session_state.comparison_images = [
                            x for x in st.session_state.comparison_images if x["thumb"] != img["thumb"]]
                    elif len(st.session_state.comparison_images) < 2:
                        st.session_state.comparison_images.append(img)
                    else:
                        st.session_state.comparison_images = [st.session_state.comparison_images[1], img]
                    st.rerun()

# ── CSS — Zeronode-inspired ────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* Hide sidebar */
[data-testid="stSidebar"],
[data-testid="stSidebarNav"],
[data-testid="collapsedControl"] { display: none !important; }

/* Background with blue gradient blob */
.stApp {
    background-color: #EEF1FF;
    background-image:
        radial-gradient(ellipse at 88% 12%, rgba(22,53,204,0.70) 0%,
                        rgba(22,53,204,0.35) 28%, rgba(22,53,204,0.08) 55%, transparent 70%);
    background-attachment: fixed;
    background-size: 100% 100%;
}

/* Main container */
.main .block-container {
    max-width: 1160px;
    padding: 2.5rem 3rem 4rem !important;
    position: relative; z-index: 1;
}

/* Typography */
h1 { font-family: 'Inter', sans-serif !important; font-size: 2.8rem !important;
     font-weight: 700 !important; color: #0B1D8A !important;
     letter-spacing: -0.03em; line-height: 1.1 !important; }
h2 { font-family: 'Inter', sans-serif !important; font-weight: 600 !important;
     color: #0B1D8A !important; letter-spacing: -0.02em; }
h3 { font-family: 'Inter', sans-serif !important; font-weight: 500 !important; color: #0B1D8A !important; }
label, p, li { color: #2C3E7A; }

/* Pills navigation */
[data-testid="stPills"] { margin: 1.5rem 0 2rem 0; }
[data-testid="stPillsButton"] {
    background: rgba(255,255,255,0.75) !important;
    border: 1.5px solid rgba(22,53,204,0.22) !important;
    border-radius: 50px !important; color: #1635CC !important;
    font-family: 'Inter', sans-serif !important; font-size: 0.82rem !important;
    font-weight: 500 !important; letter-spacing: 0.03em !important;
    padding: 0.45rem 1.4rem !important; transition: all 0.2s !important;
    backdrop-filter: blur(8px) !important;
}
[data-testid="stPillsButton"][aria-selected="true"] {
    background: #1635CC !important; color: #fff !important;
    border-color: #1635CC !important;
    box-shadow: 0 4px 18px rgba(22,53,204,0.38) !important;
}
[data-testid="stPillsButton"]:hover {
    background: rgba(22,53,204,0.08) !important;
    border-color: #1635CC !important;
}

/* Buttons */
.stButton > button[kind="primary"] {
    background: #1635CC !important; color: #fff !important;
    border: none !important; border-radius: 50px !important;
    font-family: 'Inter', sans-serif !important; font-weight: 600 !important;
    letter-spacing: 0.03em !important; padding: 0.55rem 1.8rem !important;
    box-shadow: 0 4px 18px rgba(22,53,204,0.32) !important; transition: all 0.18s !important;
}
.stButton > button[kind="primary"]:hover {
    background: #0D25B3 !important;
    box-shadow: 0 6px 22px rgba(22,53,204,0.45) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"] {
    background: rgba(255,255,255,0.78) !important; color: #1635CC !important;
    border: 1.5px solid rgba(22,53,204,0.28) !important; border-radius: 50px !important;
    font-family: 'Inter', sans-serif !important; font-weight: 500 !important;
    backdrop-filter: blur(8px) !important;
}
.stButton > button[kind="secondary"]:hover { background: rgba(22,53,204,0.07) !important; }
.stDownloadButton > button {
    background: rgba(255,255,255,0.8) !important; color: #1635CC !important;
    border: 1.5px solid rgba(22,53,204,0.28) !important; border-radius: 50px !important;
    font-family: 'Inter', sans-serif !important;
}

/* Inputs */
input, textarea,
[data-testid="stTextInput"] input {
    background: rgba(255,255,255,0.88) !important;
    border: 1.5px solid rgba(22,53,204,0.18) !important;
    border-radius: 12px !important; color: #0B1D8A !important;
    font-family: 'Inter', sans-serif !important;
}
input:focus, textarea:focus {
    border-color: #1635CC !important;
    box-shadow: 0 0 0 3px rgba(22,53,204,0.12) !important;
}
[data-testid="stSelectbox"] > div > div {
    background: rgba(255,255,255,0.88) !important;
    border: 1.5px solid rgba(22,53,204,0.18) !important;
    border-radius: 12px !important; color: #0B1D8A !important;
}

/* Alerts */
.stSuccess { background: rgba(22,53,204,0.07) !important; color: #0B1D8A !important;
             border: 1px solid rgba(22,53,204,0.18) !important; border-radius: 12px !important;
             border-left: 4px solid #1635CC !important; }
.stInfo    { background: rgba(255,255,255,0.68) !important; color: #2C3E7A !important;
             border: 1px solid rgba(22,53,204,0.14) !important; border-radius: 12px !important;
             border-left: 4px solid rgba(22,53,204,0.35) !important; }
.stWarning { background: rgba(255,200,50,0.1) !important; border-radius: 12px !important; }

hr { border-color: rgba(22,53,204,0.1) !important; }

/* Glass card (via wrapping div) */
.glass {
    background: rgba(255,255,255,0.72);
    backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
    border: 1px solid rgba(255,255,255,0.9);
    border-radius: 22px; padding: 1.6rem 1.8rem;
    box-shadow: 0 4px 28px rgba(22,53,204,0.07);
    margin-bottom: 1rem;
}

/* Brief context bar */
.brief-bar {
    display: inline-flex; align-items: center; gap: 0.55rem;
    background: rgba(255,255,255,0.72); backdrop-filter: blur(12px);
    border: 1px solid rgba(22,53,204,0.16); border-radius: 50px;
    padding: 0.45rem 1.4rem; font-size: 0.82rem; color: #2C3E7A;
    margin-bottom: 1.8rem;
}
.brief-dot { width:7px; height:7px; background:#1635CC; border-radius:50%; display:inline-block; }

/* Section label */
.section-tag {
    display: inline-flex; align-items: center; gap: 0.4rem;
    font-size: 0.68rem; letter-spacing: 0.14em; text-transform: uppercase;
    color: #1635CC; font-weight: 600; margin-bottom: 0.25rem;
}
.section-tag::before { content: '•'; font-size: 1.1rem; color: #1635CC; }

/* Subtitle */
.subtitle { font-size: 1rem; color: #3D5299; margin-top: -0.5rem;
            margin-bottom: 2rem; font-weight: 400; line-height: 1.55; }

/* Query cards */
.query-card {
    background: rgba(255,255,255,0.72); backdrop-filter: blur(16px);
    border: 1px solid rgba(255,255,255,0.88); border-radius: 20px;
    padding: 1.2rem 1.4rem 1rem; margin-bottom: 1rem;
    box-shadow: 0 2px 18px rgba(22,53,204,0.06);
}
.query-header { display:flex; align-items:baseline; gap:0.6rem; margin-bottom:0.75rem; }
.query-num  { font-size:0.68rem; color:#1635CC; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; }
.query-text { font-size:0.95rem; color:#0B1D8A; font-style:italic; }

/* Preview strip */
.preview-strip { display:flex; gap:0.5rem; margin-bottom:0.8rem; }
.preview-strip a { width:calc(33.33% - 0.34rem); display:block; }
.preview-strip img { width:100%; height:92px; object-fit:cover; border-radius:10px;
                     border:1px solid rgba(22,53,204,0.1); display:block; }
.preview-placeholder { width:calc(33.33% - 0.34rem); height:92px;
                        background:rgba(22,53,204,0.05); border-radius:10px;
                        border:1px solid rgba(22,53,204,0.1); }

/* Platform buttons */
.btn-row { display:flex; flex-wrap:wrap; gap:0.3rem; }
.ref-btn { display:inline-flex; align-items:center; padding:0.32rem 0.85rem;
           border-radius:50px; text-decoration:none !important;
           font-size:0.76rem; font-weight:500; font-family:'Inter',sans-serif;
           transition:all 0.18s; border:1px solid transparent; }
.ref-btn:hover { opacity:0.82; transform:translateY(-1px); }
.btn-pinterest { background:rgba(230,0,35,0.09); color:#cc0020 !important; border-color:rgba(230,0,35,0.2); }
.btn-behance   { background:rgba(23,105,255,0.09); color:#1769FF !important; border-color:rgba(23,105,255,0.2); }
.btn-google    { background:rgba(255,255,255,0.8); color:#0B1D8A !important; border-color:rgba(22,53,204,0.18); }
.btn-archinect { background:rgba(11,29,138,0.07); color:#0B1D8A !important; border-color:rgba(11,29,138,0.18); }
.btn-arena     { background:rgba(22,53,204,0.09); color:#1635CC !important; border-color:rgba(22,53,204,0.2); }

/* Keyword tags */
.kw-tag { display:inline-block; padding:0.2rem 0.78rem; margin:0.15rem;
          background:rgba(22,53,204,0.07); border:1px solid rgba(22,53,204,0.18);
          border-radius:50px; font-size:0.78rem; color:#1635CC;
          font-family:'Inter',sans-serif; font-weight:500; }

/* Image badges */
.badge { display:inline-block; padding:0.1rem 0.48rem; border-radius:20px;
         font-size:0.64rem; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; }
.badge-unsplash { background:rgba(11,29,138,0.09); color:#0B1D8A; }
.badge-pexels   { background:rgba(22,53,204,0.12); color:#1635CC; }

/* Color swatches */
.swatch-row { display:flex; gap:0.9rem; flex-wrap:wrap; margin:1rem 0; }
.swatch { width:72px; text-align:center; }
.swatch-block { width:72px; height:64px; border-radius:14px;
                border:1px solid rgba(0,0,0,0.06); margin-bottom:0.35rem;
                box-shadow:0 2px 10px rgba(0,0,0,0.1); }
.swatch-hex { font-size:0.68rem; color:#3D5299; font-family:monospace; }

/* Prompt box */
.prompt-box { background:rgba(255,255,255,0.85); backdrop-filter:blur(12px);
              border:1.5px solid rgba(22,53,204,0.16); border-radius:16px;
              padding:1.4rem 1.6rem; font-size:0.87rem; color:#0B1D8A;
              font-family:monospace; line-height:1.7; white-space:pre-wrap; }

/* Compare */
.compare-label { font-size:0.68rem; letter-spacing:0.1em; text-transform:uppercase;
                 color:#3D5299; margin-bottom:0.3rem; }

/* Filter heading */
.filter-heading { font-size:0.7rem; letter-spacing:0.11em; text-transform:uppercase;
                  color:#3D5299; font-weight:600; margin:1.1rem 0 0.35rem 0; }

/* History item */
.hist-item { font-size:0.78rem; color:#3D5299; padding:0.2rem 0; }
</style>
""", unsafe_allow_html=True)

# ── Global header ──────────────────────────────────────────────────────────────
st.markdown("<div class='section-tag'>AI TOOL</div>", unsafe_allow_html=True)
st.title("Render Finder")
st.markdown(
    "<div class='subtitle'>AI-powered image curation for Photoshop renders</div>",
    unsafe_allow_html=True)

# ── Bubble navigation ──────────────────────────────────────────────────────────
page = st.pills(
    "nav", ["Brief", "Search", "Browse", "Palette", "Board", "Prompt"],
    key="nav_pills", label_visibility="collapsed")
if page is None:
    page = "Brief"

# Convenience aliases (always fresh from session state)
space      = st.session_state.brief_space
style      = st.session_state.brief_style
mood       = st.session_state.brief_mood
background = st.session_state.brief_background

# Brief context bar on non-Brief pages
if page != "Brief" and space and mood:
    st.markdown(
        f"<div class='brief-bar'><span class='brief-dot'></span>"
        f"<strong>{space}</strong> · {style} · {mood}</div>",
        unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Brief
# ══════════════════════════════════════════════════════════════════════════════
if page == "Brief":
    st.markdown("<div class='section-tag'>Start here</div>", unsafe_allow_html=True)
    st.header("Define Your Brief")
    st.markdown(
        "<p style='color:#3D5299;margin-top:-0.4rem;margin-bottom:1.8rem;'>"
        "Describe the space, style, and mood you're rendering. "
        "Use a template to get started instantly.</p>", unsafe_allow_html=True)

    col_form, col_hist = st.columns([3, 1])

    with col_form:
        st.markdown("<div class='glass'>", unsafe_allow_html=True)

        st.markdown("<div class='filter-heading'>Load a template</div>", unsafe_allow_html=True)
        st.selectbox("template", list(TEMPLATES.keys()), key="template_selector",
                     on_change=on_template_change, label_visibility="collapsed")

        st.markdown("<div class='filter-heading' style='margin-top:1.2rem'>Space</div>",
                    unsafe_allow_html=True)
        st.text_input("space_input", placeholder="e.g. living room, outdoor courtyard",
                      key="brief_space", label_visibility="collapsed")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("<div class='filter-heading'>Style</div>", unsafe_allow_html=True)
            st.selectbox("style_sel", STYLE_OPTIONS, key="brief_style", label_visibility="collapsed")
        with c2:
            st.markdown("<div class='filter-heading'>Background</div>", unsafe_allow_html=True)
            st.selectbox("bg_sel", BG_OPTIONS, key="brief_background", label_visibility="collapsed")

        st.markdown("<div class='filter-heading'>Mood</div>", unsafe_allow_html=True)
        st.text_input("mood_input", placeholder="e.g. warm and earthy, editorial, hazy",
                      key="brief_mood", label_visibility="collapsed")

        st.markdown("</div>", unsafe_allow_html=True)

        bc1, bc2, bc3 = st.columns([2, 2, 1])
        with bc1:
            if st.button("Find References →", type="primary", use_container_width=True):
                if not space or not mood:
                    st.warning("Fill in Space and Mood first.")
                else:
                    brief = {"space": space, "style": style, "mood": mood, "background": background}
                    if not st.session_state.history or st.session_state.history[0] != brief:
                        st.session_state.history.insert(0, brief)
                        st.session_state.history = st.session_state.history[:5]
                    go_to("Search")
        with bc2:
            if st.button("Browse Images →", use_container_width=True):
                go_to("Browse")

    with col_hist:
        if st.session_state.history:
            st.markdown("<div class='filter-heading'>Recent briefs</div>", unsafe_allow_html=True)
            for j, h in enumerate(st.session_state.history):
                st.markdown(f"<div class='hist-item'>{h['space']} · {h['style']}</div>",
                            unsafe_allow_html=True)
                if st.button("↩ Load", key=f"hist_{j}", use_container_width=True):
                    for fk in ["space","style","mood","background"]:
                        st.session_state[f"brief_{fk}"] = h[fk]
                    st.rerun()
        if st.session_state.selected_images:
            n_b = len(st.session_state.selected_images)
            st.markdown("<div class='filter-heading' style='margin-top:1.5rem'>Mood Board</div>",
                        unsafe_allow_html=True)
            st.markdown(f"<div class='hist-item'>{n_b} image{'s' if n_b!=1 else ''} selected</div>",
                        unsafe_allow_html=True)
            if st.button("Open Board →", use_container_width=True):
                go_to("Board")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Search
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Search":
    st.markdown("<div class='section-tag'>AI-generated</div>", unsafe_allow_html=True)
    st.header("Reference Queries")

    find_btn = st.button("Generate Queries", type="primary")

    if find_btn:
        if not space or not mood:
            st.warning("Go to **Brief** and fill in Space and Mood first.")
        else:
            brief = {"space": space, "style": style, "mood": mood, "background": background}
            if not st.session_state.history or st.session_state.history[0] != brief:
                st.session_state.history.insert(0, brief)
                st.session_state.history = st.session_state.history[:5]
            prompt = (
                f"Generate 5 targeted search queries for a designer finding Photoshop render references. "
                f"Brief — Space: {space}, Style: {style}, Mood: {mood}, Background: {background}. "
                f"Use designer vocabulary. Return numbered list only, no extra text.")
            with st.spinner("Generating queries..."):
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001", max_tokens=512,
                    messages=[{"role": "user", "content": prompt}])
            raw = response.content[0].text.strip()
            st.session_state.generated_queries = [l.strip() for l in raw.splitlines() if l.strip()]

    if st.session_state.generated_queries:
        lines    = st.session_state.generated_queries
        has_keys = bool(get_secret("UNSPLASH_ACCESS_KEY") or get_secret("PEXELS_API_KEY"))

        keywords = extract_keywords([l.lstrip("0123456789. ").strip('"') for l in lines])
        if keywords:
            st.markdown(
                "<div style='margin-bottom:1.4rem'>" +
                "".join(f"<span class='kw-tag'>{w}</span>" for w in keywords) +
                "</div>", unsafe_allow_html=True)

        for i, line in enumerate(lines, 1):
            qt  = line.lstrip("0123456789. ").strip('"')
            enc = urllib.parse.quote_plus(qt)
            previews = []
            if has_keys:
                previews = search_unsplash(qt, n=3)
                if len(previews) < 3:
                    previews += search_pexels(qt, n=3 - len(previews))

            strip = ""
            if previews:
                strip = '<div class="preview-strip">' + "".join(
                    f'<a href="{p["link"]}" target="_blank" rel="noopener">'
                    f'<img src="{p["thumb"]}" alt="{p["author"]}"></a>'
                    for p in previews[:3]) + "</div>"
            elif has_keys:
                strip = '<div class="preview-strip">' + \
                        '<div class="preview-placeholder"></div>' * 3 + "</div>"

            st.markdown(f"""
            <div class="query-card">
                <div class="query-header">
                    <span class="query-num">Query {i}</span>
                    <span class="query-text">{qt}</span>
                </div>
                {strip}
                <div class="btn-row">
                    <a class="ref-btn btn-pinterest" href="https://www.pinterest.com/search/pins/?q={enc}"       target="_blank">Pinterest</a>
                    <a class="ref-btn btn-behance"   href="https://www.behance.net/search/projects?search={enc}" target="_blank">Behance</a>
                    <a class="ref-btn btn-google"    href="https://www.google.com/search?tbm=isch&q={enc}"       target="_blank">Google Images</a>
                    <a class="ref-btn btn-archinect" href="https://archinect.com/search#/?q={enc}&type=photos"   target="_blank">Archinect</a>
                    <a class="ref-btn btn-arena"     href="https://www.are.na/search/{enc}"                      target="_blank">Are.na</a>
                </div>
            </div>""", unsafe_allow_html=True)

        if not has_keys:
            st.info("Add **UNSPLASH_ACCESS_KEY** or **PEXELS_API_KEY** to secrets to see image previews.")
        st.success(f"{len(lines)} queries generated. Click any image or platform button to explore.")
    else:
        st.info("Click **Generate Queries** to create AI-powered search queries from your brief.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Browse  (filter chips — no AI needed)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Browse":
    st.markdown("<div class='section-tag'>No AI needed</div>", unsafe_allow_html=True)
    st.header("Browse & Filter")
    st.markdown(
        "<p style='color:#3D5299;margin-top:-0.4rem;margin-bottom:1.4rem;'>"
        "Select filters to browse images directly — no prompts required.</p>",
        unsafe_allow_html=True)

    st.markdown("<div class='filter-heading'>Space</div>", unsafe_allow_html=True)
    sel_spaces = st.pills("spaces", FILTER_SPACES, selection_mode="multi",
                          label_visibility="collapsed")

    st.markdown("<div class='filter-heading'>Style</div>", unsafe_allow_html=True)
    sel_styles = st.pills("styles", FILTER_STYLES, selection_mode="multi",
                          label_visibility="collapsed")

    st.markdown("<div class='filter-heading'>Mood</div>", unsafe_allow_html=True)
    sel_moods = st.pills("moods", FILTER_MOODS, selection_mode="multi",
                         label_visibility="collapsed")

    st.markdown("<div class='filter-heading'>Lighting</div>", unsafe_allow_html=True)
    sel_lights = st.pills("lights", FILTER_LIGHTS, selection_mode="multi",
                          label_visibility="collapsed")

    st.markdown("<br>", unsafe_allow_html=True)
    fa, fb = st.columns([2, 4])
    with fa:
        filter_btn = st.button("Browse Images", type="primary", use_container_width=True)
    with fb:
        all_tags = list(sel_spaces or []) + list(sel_styles or []) + \
                   list(sel_moods or []) + list(sel_lights or [])
        if all_tags:
            st.markdown(
                f"<div style='padding-top:0.55rem;color:#1635CC;font-size:0.82rem;'>"
                f"Query: <em>{', '.join(all_tags)}</em></div>",
                unsafe_allow_html=True)

    if filter_btn:
        all_tags = list(sel_spaces or []) + list(sel_styles or []) + \
                   list(sel_moods or []) + list(sel_lights or [])
        if not all_tags:
            st.warning("Select at least one filter to browse.")
        elif not get_secret("UNSPLASH_ACCESS_KEY") and not get_secret("PEXELS_API_KEY"):
            st.warning("Add **UNSPLASH_ACCESS_KEY** or **PEXELS_API_KEY** to Streamlit secrets.")
        else:
            q = " ".join(all_tags) + " interior architecture"
            with st.spinner("Fetching images..."):
                st.session_state.filter_results = \
                    search_unsplash(q, n=9) + search_pexels(q, n=9)

    # Also allow browsing from brief
    st.divider()
    browse_brief_btn = st.button("Browse from Brief", use_container_width=False)
    if browse_brief_btn:
        if not space or not mood:
            st.warning("Set a brief first.")
        elif not get_secret("UNSPLASH_ACCESS_KEY") and not get_secret("PEXELS_API_KEY"):
            st.warning("Add image API keys to Streamlit secrets.")
        else:
            q = f"{style} {space} {mood} interior architecture"
            with st.spinner("Fetching images..."):
                st.session_state.browse_results = \
                    search_unsplash(q, n=9) + search_pexels(q, n=9)

    results = (st.session_state.filter_results or st.session_state.browse_results)
    if results:
        st.markdown(f"<p style='color:#3D5299;font-size:0.85rem;margin:1rem 0'>"
                    f"Showing {len(results)} images</p>", unsafe_allow_html=True)
        render_image_grid(results, key_prefix="browse")

        if len(st.session_state.comparison_images) == 2:
            st.divider()
            st.markdown("<div class='section-tag'>Comparison</div>", unsafe_allow_html=True)
            ca, cb = st.columns(2)
            for col, img in zip([ca, cb], st.session_state.comparison_images):
                with col:
                    st.markdown(f"<div class='compare-label'>{img['source'].upper()} — {img['author']}</div>",
                                unsafe_allow_html=True)
                    st.image(img["full"], use_container_width=True)
                    st.markdown(f"[Open original ↗]({img['link']})")
            if st.button("Clear comparison"):
                st.session_state.comparison_images = []
                st.rerun()
        st.success(f"{len(results)} images loaded — click **+ Board** to add to your mood board.")
    else:
        st.info("Select filters above and click **Browse Images**, or use **Browse from Brief** to use your current brief.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Palette
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Palette":
    st.markdown("<div class='section-tag'>Color extraction</div>", unsafe_allow_html=True)
    st.header("Color Palette Extractor")
    st.markdown(
        "<p style='color:#3D5299;margin-top:-0.4rem;margin-bottom:1.8rem;'>"
        "Paste any image URL to extract its dominant color palette as hex swatches.</p>",
        unsafe_allow_html=True)

    palette_url = st.text_input("Image URL",
        placeholder="https://images.unsplash.com/photo-...",
        label_visibility="collapsed")
    n_colors = st.slider("Number of colors", 3, 10, 6)
    palette_btn = st.button("Extract Palette", type="primary")

    if palette_btn:
        if not palette_url.strip():
            st.warning("Paste an image URL first.")
        else:
            with st.spinner("Extracting palette..."):
                hexes = extract_palette(palette_url.strip(), n=n_colors)
            if not hexes:
                st.warning("Could not extract palette — try a direct image URL (jpg/png).")
            else:
                swatches_html = "".join(
                    f"<div class='swatch'>"
                    f"<div class='swatch-block' style='background:{h}'></div>"
                    f"<div class='swatch-hex'>{h}</div></div>"
                    for h in hexes)
                st.markdown(f"<div class='swatch-row'>{swatches_html}</div>",
                            unsafe_allow_html=True)

                col_dl, _ = st.columns([1, 3])
                with col_dl:
                    st.download_button("Download palette CSV",
                                       ",".join(hexes).encode(),
                                       "palette.csv", "text/csv")
                st.success(f"Extracted {len(hexes)} colors.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Board
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Board":
    st.markdown("<div class='section-tag'>Export</div>", unsafe_allow_html=True)
    st.header("Mood Board")

    if not st.session_state.selected_images:
        st.info("Browse images on the **Browse** page and click **+ Board** to start building your mood board here.")
    else:
        imgs  = st.session_state.selected_images
        n_sel = len(imgs)
        st.markdown(
            f"<p style='color:#3D5299;font-size:0.9rem;'>{n_sel} image{'s' if n_sel!=1 else ''} selected</p>",
            unsafe_allow_html=True)

        preview_cols = st.columns(min(n_sel, 4))
        for i, img in enumerate(imgs):
            with preview_cols[i % 4]:
                st.image(img["thumb"], use_container_width=True)
                if st.button("Remove", key=f"rm_{i}", use_container_width=True):
                    st.session_state.selected_images.pop(i)
                    st.rerun()

        st.markdown("---")
        gc1, gc2, gc3 = st.columns([1, 1, 2])
        with gc1:
            mb_cols = st.selectbox("Grid columns", [2, 3, 4], index=1)
        with gc2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Generate Mood Board", type="primary", use_container_width=True):
                with st.spinner("Compositing..."):
                    png = create_moodboard(imgs, cols=mb_cols)
                if png:
                    st.image(png)
                    st.download_button("Download PNG", png, "moodboard.png",
                                       "image/png", use_container_width=True)
                    st.success("Mood board ready.")
                else:
                    st.warning("Could not load images — check URLs are accessible.")
        with gc3:
            if st.button("Clear Board", use_container_width=True):
                st.session_state.selected_images = []
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Prompt
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Prompt":
    st.markdown("<div class='section-tag'>AI generation</div>", unsafe_allow_html=True)
    st.header("AI Prompt Generator")
    st.markdown(
        "<p style='color:#3D5299;margin-top:-0.4rem;margin-bottom:1.8rem;'>"
        "Generate a ready-to-paste Midjourney or Stable Diffusion prompt from your brief.</p>",
        unsafe_allow_html=True)

    platform = st.radio("Platform", ["Midjourney", "Stable Diffusion", "Both"],
                        horizontal=True, label_visibility="collapsed")

    # Allow overriding the brief inline (widgets always render; expander just collapses them)
    p_space, p_style, p_mood, p_bg = space, style, mood, background
    with st.expander("Override brief for this prompt"):
        oc1, oc2 = st.columns(2)
        with oc1:
            p_space = st.text_input("Space", value=space or "", key="p_space")
            p_style = st.selectbox("Style", STYLE_OPTIONS,
                                   index=STYLE_OPTIONS.index(style) if style in STYLE_OPTIONS else 0,
                                   key="p_style")
        with oc2:
            p_mood  = st.text_input("Mood", value=mood or "", key="p_mood")
            p_bg    = st.selectbox("Background", BG_OPTIONS,
                                   index=BG_OPTIONS.index(background) if background in BG_OPTIONS else 0,
                                   key="p_bg")

    prompt_btn = st.button("Generate Prompt", type="primary")

    if prompt_btn:
        if not p_space or not p_mood:
            st.warning("Fill in Space and Mood (in Brief or the override above).")
        else:
            if platform == "Midjourney":
                instr = "Generate a detailed Midjourney prompt only. End with --ar 16:9 --v 6.1 --style raw"
            elif platform == "Stable Diffusion":
                instr = ("Generate a Stable Diffusion prompt. Include positive prompt tags (comma-separated), "
                         "then a blank line, then 'Negative prompt:' with negative tags.")
            else:
                instr = ("Generate both:\n"
                         "1) Midjourney prompt (end with --ar 16:9 --v 6.1 --style raw)\n"
                         "2) Stable Diffusion prompt with positive tags and Negative prompt: line.")

            full_prompt = (
                f"{instr}\n"
                f"Brief: Space: {p_space}, Style: {p_style}, Mood: {p_mood}, Background: {p_bg}.\n"
                f"Include: camera angle, lighting quality, material palette, atmosphere, color grading. "
                f"Make it specific and evocative for architectural/interior visualization.")

            with st.spinner("Crafting prompt..."):
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001", max_tokens=600,
                    messages=[{"role": "user", "content": full_prompt}])
            result = response.content[0].text.strip()

            st.markdown(f"<div class='prompt-box'>{result}</div>", unsafe_allow_html=True)
            dl1, _ = st.columns([1, 3])
            with dl1:
                st.download_button("Download as .txt", result.encode(),
                                   "render_prompt.txt", "text/plain")
            st.success("Prompt ready — paste directly into Midjourney or your SD interface.")
    else:
        st.info("Set your brief then click **Generate Prompt**.")

    # Filter-based scoring section on Prompt page
    st.divider()
    st.markdown("<div class='section-tag'>Score existing images</div>", unsafe_allow_html=True)
    st.subheader("Filter & Score Images")
    st.markdown(
        "<p style='color:#3D5299;font-size:0.9rem;'>Paste image URLs to score render-readiness — "
        "no prompts needed for browsing, but Claude scores them here.</p>", unsafe_allow_html=True)

    url_input = st.text_area("Image URLs (one per line)", height=120,
        placeholder="https://i.pinimg.com/...\nhttps://images.unsplash.com/...",
        label_visibility="collapsed")
    check_btn = st.button("Check Render-Readiness", type="primary")

    if check_btn:
        urls = [u.strip() for u in url_input.splitlines() if u.strip()]
        if not urls:
            st.warning("Paste at least one image URL.")
        else:
            score_prompt = (
                f"Rate each image URL for Photoshop render use 1-10. "
                f"Criteria: clean/white background, matches {p_style} {p_mood} brief, good composition. "
                f"Return a markdown table: URL | Score | Reason. Show only scores 6+.\n"
                + "\n".join(urls))
            with st.spinner("Scoring images..."):
                resp = client.messages.create(
                    model="claude-haiku-4-5-20251001", max_tokens=1024,
                    messages=[{"role": "user", "content": score_prompt}])
            result = resp.content[0].text.strip()
            st.markdown(result)

            rows = []
            for line in result.splitlines():
                if "|" in line and not re.match(r"^[\s|:-]+$", line):
                    cells = [c.strip() for c in line.strip().strip("|").split("|")]
                    if cells and cells[0].lower() not in ("url", ""):
                        rows.append(cells)
            if rows:
                buf = io.StringIO()
                csv.writer(buf).writerow(["URL","Score","Reason"])
                csv.writer(buf).writerows(rows)
                _, dl_col = st.columns([3, 1])
                with dl_col:
                    st.download_button("Download CSV", buf.getvalue().encode(),
                                       "scored_images.csv", "text/csv",
                                       use_container_width=True)
            passed, total = len(rows), len(urls)
            if passed:
                st.success(f"{passed} of {total} images scored 6+ — ready to download.")
            else:
                st.info(f"None of the {total} images scored 6+ for this brief.")

import streamlit as st
import anthropic
import urllib.parse
import os, csv, io, re, requests
from PIL import Image
from colorthief import ColorThief
from dotenv import load_dotenv
from collections import Counter

load_dotenv()

st.set_page_config(page_title="Render Finder", layout="wide", initial_sidebar_state="expanded")

# ── Session state ──────────────────────────────────────────────────────────────
_defaults = {
    "history": [], "selected_images": [], "comparison_images": [],
    "browse_results": [], "generated_queries": [],
    "brief_space": "", "brief_style": "Dreamy",
    "brief_mood": "", "brief_background": "White/Isolated",
    "template_selector": "— Choose a template —",
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Constants ──────────────────────────────────────────────────────────────────
STYLE_OPTIONS = ["Dreamy", "Dark Moody", "Minimal", "Maximalist", "Realistic CGI"]
BG_OPTIONS    = ["White/Isolated", "Scene", "Any"]
TEMPLATES = {
    "— Choose a template —": None,
    "Warm Scandinavian Interior":  {"space": "living room",       "style": "Minimal",       "mood": "warm, hygge, soft diffused light",      "background": "Scene"},
    "Dark Industrial Loft":        {"space": "loft apartment",    "style": "Dark Moody",    "mood": "raw, editorial, exposed concrete",       "background": "Scene"},
    "Dreamy Exterior Courtyard":   {"space": "outdoor courtyard", "style": "Dreamy",        "mood": "hazy, atmospheric, lush greenery",       "background": "Scene"},
    "Maximalist Living Room":      {"space": "living room",       "style": "Maximalist",    "mood": "layered, eclectic, rich jewel tones",    "background": "Scene"},
    "Clean White Kitchen":         {"space": "kitchen",           "style": "Minimal",       "mood": "bright, airy, clinical precision",       "background": "White/Isolated"},
    "Warm Terracotta Bedroom":     {"space": "bedroom",           "style": "Dreamy",        "mood": "earthy, cozy, Mediterranean warmth",     "background": "Scene"},
    "Brutalist Office Lobby":      {"space": "office lobby",      "style": "Realistic CGI", "mood": "monumental, raw concrete, dramatic",     "background": "Scene"},
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
    board = Image.new("RGB", (cols*(tw+gap)+gap, rows*(th+gap)+gap), (240, 234, 225))
    for i, img in enumerate(imgs):
        r, c = divmod(i, cols)
        board.paste(img, (c*(tw+gap)+gap, r*(th+gap)+gap))
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

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500&family=DM+Serif+Display&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.stApp { background-color: #EDE8E1; color: #2C2520; }

[data-testid="stSidebar"] { background-color: #E0D8CF !important; border-right: 1px solid #C8BFB5; }
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3, [data-testid="stSidebar"] label,
[data-testid="stSidebar"] p { color: #2C2520 !important; }

h1 { font-family: 'DM Serif Display', serif !important; font-size: 2.6rem !important;
     color: #2C2520 !important; letter-spacing: -0.02em; font-weight: 400 !important; }
h2, h3 { font-family: 'DM Serif Display', serif !important; color: #2C2520 !important;
         font-weight: 400 !important; letter-spacing: -0.01em; }

input[type="text"], textarea {
    background-color: #F5F0EA !important; border: 1px solid #C8BFB5 !important;
    border-radius: 6px !important; color: #2C2520 !important; font-family: 'DM Sans', sans-serif !important; }
input[type="text"]:focus, textarea:focus {
    border-color: #B5634A !important; box-shadow: 0 0 0 2px rgba(181,99,74,0.15) !important; }

[data-testid="stSelectbox"] > div > div {
    background-color: #F5F0EA !important; border: 1px solid #C8BFB5 !important;
    border-radius: 6px !important; color: #2C2520 !important; }

.stButton > button[kind="primary"] {
    background-color: #B5634A !important; color: #F5F0EA !important;
    border: none !important; border-radius: 6px !important;
    font-family: 'DM Sans', sans-serif !important; font-weight: 500 !important; }
.stButton > button[kind="primary"]:hover { background-color: #9A5038 !important; }
.stButton > button[kind="secondary"] {
    background-color: transparent !important; color: #2C2520 !important;
    border: 1px solid #B5634A !important; border-radius: 6px !important;
    font-family: 'DM Sans', sans-serif !important; font-weight: 500 !important; }
.stButton > button[kind="secondary"]:hover { background-color: #B5634A22 !important; }
.stDownloadButton > button {
    background-color: #7D9178 !important; color: #fff !important;
    border: none !important; border-radius: 6px !important; }
.stDownloadButton > button:hover { background-color: #667A62 !important; }

[data-testid="stAlert"] { border-radius: 8px !important; }
.stSuccess { background-color: #D8E5D5 !important; color: #2C3D28 !important; border-left: 4px solid #7D9178 !important; }
.stInfo    { background-color: #E8E4DE !important; color: #2C2520 !important; border-left: 4px solid #A09489 !important; }
.stWarning { background-color: #F0E4D8 !important; color: #3D2515 !important; border-left: 4px solid #B5634A !important; }
hr { border-color: #C8BFB5 !important; }

/* Platform buttons */
.ref-btn {
    display: inline-flex; align-items: center; padding: 0.4rem 0.9rem;
    margin: 0.18rem 0.2rem 0.18rem 0; border-radius: 6px;
    text-decoration: none !important; font-size: 0.8rem; font-weight: 500;
    font-family: 'DM Sans', sans-serif; transition: opacity 0.2s; }
.ref-btn:hover { opacity: 0.82; }
.btn-pinterest { background-color: #B5634A; color: #fff !important; }
.btn-behance   { background-color: #1769FF; color: #fff !important; }
.btn-google    { background-color: #F5F0EA; color: #2C2520 !important; border: 1px solid #C8BFB5; }
.btn-archinect { background-color: #2C2520; color: #EDE8E1 !important; }
.btn-arena     { background-color: #7D9178; color: #fff !important; }

/* Query card */
.query-card {
    background: #F5F0EA; border: 1px solid #D5CCC5; border-radius: 10px;
    padding: 1rem 1.1rem 0.85rem; margin-bottom: 1rem; }
.query-header { display: flex; align-items: baseline; gap: 0.5rem; margin-bottom: 0.7rem; }
.query-label { font-size: 0.72rem; color: #B5634A; font-weight: 600;
               letter-spacing: 0.09em; text-transform: uppercase; }
.query-text  { font-size: 0.95rem; color: #2C2520; font-style: italic; }
.preview-strip { display: flex; gap: 0.5rem; margin-bottom: 0.75rem; }
.preview-strip a { width: calc(33.33% - 0.34rem); display: block; }
.preview-strip img { width: 100%; height: 100px; object-fit: cover;
                     border-radius: 6px; border: 1px solid #C8BFB5; display: block; }
.preview-placeholder { width: calc(33.33% - 0.34rem); height: 100px;
                        background: #E0D8CF; border-radius: 6px; border: 1px solid #C8BFB5; }
.btn-row { display: flex; flex-wrap: wrap; gap: 0.3rem; }

/* Keyword tags */
.kw-tag {
    display: inline-block; padding: 0.22rem 0.7rem; margin: 0.15rem;
    background: #E0D8CF; border: 1px solid #C8BFB5; border-radius: 20px;
    font-size: 0.78rem; color: #2C2520; font-family: 'DM Sans', sans-serif; }

/* Image badge */
.badge { display: inline-block; padding: 0.12rem 0.5rem; border-radius: 4px;
         font-size: 0.68rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; }
.badge-unsplash { background: #2C2520; color: #EDE8E1; }
.badge-pexels   { background: #7D9178; color: #fff; }

/* Color swatch */
.swatch-row { display: flex; gap: 0.6rem; flex-wrap: wrap; margin: 0.8rem 0; }
.swatch {
    width: 70px; text-align: center; }
.swatch-block {
    width: 70px; height: 60px; border-radius: 8px;
    border: 1px solid rgba(0,0,0,0.08); margin-bottom: 0.3rem; }
.swatch-hex { font-size: 0.7rem; color: #7A6E68; font-family: monospace; }

/* Comparison */
.compare-label { font-size: 0.7rem; letter-spacing: 0.09em; text-transform: uppercase;
                 color: #7A6E68; margin-bottom: 0.3rem; }

/* Mood board thumb */
.board-img { position: relative; margin-bottom: 0.5rem; }
.board-img img { width: 100%; border-radius: 6px; border: 1px solid #C8BFB5; }
.board-remove { font-size: 0.7rem; color: #B5634A; cursor: pointer; }

/* Prompt box */
.prompt-box {
    background: #F5F0EA; border: 1px solid #C8BFB5; border-radius: 8px;
    padding: 1rem 1.1rem; font-size: 0.85rem; color: #2C2520;
    font-family: monospace; line-height: 1.6; white-space: pre-wrap; }

/* Typography helpers */
.section-tag { font-size: 0.7rem; letter-spacing: 0.12em; text-transform: uppercase;
               color: #B5634A; font-weight: 500; margin-bottom: 0.2rem; }
.subtitle { font-size: 1rem; color: #7A6E68; margin-top: -0.8rem;
            margin-bottom: 1.5rem; font-weight: 300; letter-spacing: 0.01em; }
</style>
""", unsafe_allow_html=True)

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("<div class='section-tag'>Tool</div>", unsafe_allow_html=True)
st.title("Render Finder")
st.markdown("<div class='subtitle'>AI-powered image curation for Photoshop renders</div>",
            unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div class='section-tag'>Templates</div>", unsafe_allow_html=True)
    st.selectbox("template", list(TEMPLATES.keys()), key="template_selector",
                 on_change=on_template_change, label_visibility="collapsed")

    st.markdown("<div class='section-tag' style='margin-top:1.2rem'>Project Brief</div>",
                unsafe_allow_html=True)
    st.text_input("Space", placeholder="e.g. living room, courtyard", key="brief_space")
    st.selectbox("Style", STYLE_OPTIONS, key="brief_style")
    st.text_input("Mood", placeholder="e.g. warm and earthy, serene", key="brief_mood")
    st.selectbox("Background", BG_OPTIONS, key="brief_background")

    st.markdown("---")
    find_btn   = st.button("Find References", use_container_width=True, type="primary")
    browse_btn = st.button("Browse Images",   use_container_width=True)

    if st.session_state.selected_images:
        n_board = len(st.session_state.selected_images)
        st.markdown(
            f"<div style='text-align:center;color:#B5634A;font-size:0.82rem;margin:0.6rem 0'>"
            f"Mood Board — {n_board} image{'s' if n_board!=1 else ''}</div>",
            unsafe_allow_html=True)
        if st.button("Clear Board", use_container_width=True):
            st.session_state.selected_images = []
            st.rerun()

    if st.session_state.history:
        st.markdown("---")
        st.markdown("<div class='section-tag'>Recent Briefs</div>", unsafe_allow_html=True)
        for j, h in enumerate(st.session_state.history):
            ca, cb = st.columns([4, 1])
            with ca:
                st.markdown(
                    f"<div style='font-size:0.77rem;color:#7A6E68;padding:0.15rem 0'>"
                    f"{h['space']} · {h['style']}</div>", unsafe_allow_html=True)
            with cb:
                if st.button("↩", key=f"hist_{j}", help=h["mood"]):
                    for fk, fv in h.items():
                        st.session_state[f"brief_{fk}"] = fv
                    st.rerun()

# Convenience aliases
space      = st.session_state.brief_space
style      = st.session_state.brief_style
mood       = st.session_state.brief_mood
background = st.session_state.brief_background

# ── 01 — Reference Queries ─────────────────────────────────────────────────────
st.markdown("<div class='section-tag'>01 — Search</div>", unsafe_allow_html=True)
st.header("Reference Queries")

if find_btn:
    if not space or not mood:
        st.warning("Please fill in **Space** and **Mood** before searching.")
    else:
        brief = {"space": space, "style": style, "mood": mood, "background": background}
        if not st.session_state.history or st.session_state.history[0] != brief:
            st.session_state.history.insert(0, brief)
            st.session_state.history = st.session_state.history[:5]

        prompt = (
            f"Generate 5 targeted search queries for a designer finding Photoshop render references. "
            f"Brief — Space: {space}, Style: {style}, Mood: {mood}, Background: {background}. "
            f"Use designer vocabulary. Return numbered list only, no extra text."
        )
        with st.spinner("Generating queries..."):
            response = client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=512,
                messages=[{"role": "user", "content": prompt}])

        raw = response.content[0].text.strip()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        st.session_state.generated_queries = lines

if st.session_state.generated_queries:
    lines = st.session_state.generated_queries
    has_keys = bool(get_secret("UNSPLASH_ACCESS_KEY") or get_secret("PEXELS_API_KEY"))

    # Keyword tags
    keywords = extract_keywords([l.lstrip("0123456789. ").strip('"') for l in lines])
    if keywords:
        tags_html = "<div style='margin-bottom:1.2rem'>" + "".join(
            f"<span class='kw-tag'>{w}</span>" for w in keywords) + "</div>"
        st.markdown(tags_html, unsafe_allow_html=True)

    for i, line in enumerate(lines, 1):
        qt  = line.lstrip("0123456789. ").strip('"')
        enc = urllib.parse.quote_plus(qt)

        previews = []
        if has_keys:
            previews = search_unsplash(qt, n=3)
            if len(previews) < 3:
                previews += search_pexels(qt, n=3 - len(previews))

        if previews:
            strip = '<div class="preview-strip">' + "".join(
                f'<a href="{p["link"]}" target="_blank" rel="noopener">'
                f'<img src="{p["thumb"]}" alt="{p["author"]}"></a>'
                for p in previews[:3]) + "</div>"
        elif has_keys:
            strip = '<div class="preview-strip">' + \
                    '<div class="preview-placeholder"></div>' * 3 + "</div>"
        else:
            strip = ""

        st.markdown(f"""
        <div class="query-card">
            <div class="query-header">
                <span class="query-label">Query {i}</span>
                <span class="query-text">{qt}</span>
            </div>
            {strip}
            <div class="btn-row">
                <a class="ref-btn btn-pinterest" href="https://www.pinterest.com/search/pins/?q={enc}"       target="_blank" rel="noopener">Pinterest</a>
                <a class="ref-btn btn-behance"   href="https://www.behance.net/search/projects?search={enc}" target="_blank" rel="noopener">Behance</a>
                <a class="ref-btn btn-google"    href="https://www.google.com/search?tbm=isch&q={enc}"       target="_blank" rel="noopener">Google Images</a>
                <a class="ref-btn btn-archinect" href="https://archinect.com/search#/?q={enc}&type=photos"   target="_blank" rel="noopener">Archinect</a>
                <a class="ref-btn btn-arena"     href="https://www.are.na/search/{enc}"                      target="_blank" rel="noopener">Are.na</a>
            </div>
        </div>""", unsafe_allow_html=True)

    if not has_keys:
        st.info("Add **UNSPLASH_ACCESS_KEY** or **PEXELS_API_KEY** to secrets to see image previews.")
    st.success(f"{len(lines)} queries generated — click any image or platform to explore.")
else:
    st.info("Fill in the brief and click **Find References**.")

st.divider()

# ── 02 — Browse Images ─────────────────────────────────────────────────────────
st.markdown("<div class='section-tag'>02 — Browse</div>", unsafe_allow_html=True)
st.header("Browse Reference Images")

if browse_btn:
    if not space or not mood:
        st.warning("Please fill in **Space** and **Mood** before browsing.")
    elif not get_secret("UNSPLASH_ACCESS_KEY") and not get_secret("PEXELS_API_KEY"):
        st.warning("Add **UNSPLASH_ACCESS_KEY** and/or **PEXELS_API_KEY** to secrets.")
    else:
        q = f"{style} {space} {mood} interior architecture"
        with st.spinner("Fetching images..."):
            st.session_state.browse_results = (
                search_unsplash(q, n=9) + search_pexels(q, n=9))

if st.session_state.browse_results:
    images = st.session_state.browse_results
    cols3  = st.columns(3)
    for i, img in enumerate(images):
        badge_cls  = "badge-unsplash" if img["source"] == "unsplash" else "badge-pexels"
        badge_lbl  = "Unsplash"       if img["source"] == "unsplash" else "Pexels"
        img_id     = f"img_{i}"
        already_board   = any(x["thumb"] == img["thumb"] for x in st.session_state.selected_images)
        already_compare = any(x["thumb"] == img["thumb"] for x in st.session_state.comparison_images)

        with cols3[i % 3]:
            st.image(img["thumb"], use_container_width=True)
            st.markdown(
                f'<span class="badge {badge_cls}">{badge_lbl}</span> '
                f'<a href="{img["link"]}" target="_blank" '
                f'style="font-size:0.78rem;color:#7A6E68;text-decoration:none;">'
                f'{img["author"]}</a>', unsafe_allow_html=True)

            c1, c2 = st.columns(2)
            with c1:
                board_label = "✓ Board" if already_board else "+ Board"
                if st.button(board_label, key=f"board_{img_id}", use_container_width=True):
                    if not already_board:
                        st.session_state.selected_images.append(img)
                    else:
                        st.session_state.selected_images = [
                            x for x in st.session_state.selected_images if x["thumb"] != img["thumb"]]
                    st.rerun()
            with c2:
                cmp_label = "✓ Compare" if already_compare else "Compare"
                if st.button(cmp_label, key=f"cmp_{img_id}", use_container_width=True):
                    if already_compare:
                        st.session_state.comparison_images = [
                            x for x in st.session_state.comparison_images if x["thumb"] != img["thumb"]]
                    elif len(st.session_state.comparison_images) < 2:
                        st.session_state.comparison_images.append(img)
                    else:
                        st.session_state.comparison_images = [st.session_state.comparison_images[1], img]
                    st.rerun()
    st.success(f"Showing {len(images)} images — click **+ Board** to add to mood board.")
else:
    st.info("Click **Browse Images** in the sidebar to pull real photos.")

# Comparison view
if len(st.session_state.comparison_images) == 2:
    st.markdown("---")
    st.markdown("<div class='section-tag'>Side-by-Side Comparison</div>", unsafe_allow_html=True)
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

st.divider()

# ── 03 — Color Palette Extractor ──────────────────────────────────────────────
st.markdown("<div class='section-tag'>03 — Palette</div>", unsafe_allow_html=True)
st.header("Color Palette Extractor")
st.markdown(
    "<p style='color:#7A6E68;font-size:0.9rem;margin-top:-0.5rem;'>"
    "Paste any image URL to extract its dominant color palette.</p>",
    unsafe_allow_html=True)

palette_url = st.text_input("Image URL", placeholder="https://images.unsplash.com/...",
                             label_visibility="collapsed")
palette_btn = st.button("Extract Palette", type="primary")

if palette_btn:
    if not palette_url.strip():
        st.warning("Paste an image URL first.")
    else:
        with st.spinner("Extracting palette..."):
            hexes = extract_palette(palette_url.strip(), n=6)
        if not hexes:
            st.warning("Could not extract palette — check the URL or try a direct image link.")
        else:
            swatches = "".join(
                f"<div class='swatch'>"
                f"<div class='swatch-block' style='background:{h}'></div>"
                f"<div class='swatch-hex'>{h}</div></div>"
                for h in hexes)
            st.markdown(f"<div class='swatch-row'>{swatches}</div>", unsafe_allow_html=True)

            hex_csv = ",".join(hexes)
            st.download_button("Download palette as CSV", hex_csv.encode(),
                               "palette.csv", "text/csv")
            st.success(f"Extracted {len(hexes)} colors.")

st.divider()

# ── 04 — Filter Images ────────────────────────────────────────────────────────
st.markdown("<div class='section-tag'>04 — Filter</div>", unsafe_allow_html=True)
st.header("Filter Images")
st.markdown(
    "<p style='color:#7A6E68;font-size:0.9rem;margin-top:-0.5rem;'>"
    "Paste image URLs (one per line) — Claude scores each for render-readiness.</p>",
    unsafe_allow_html=True)

url_input = st.text_area("URLs", height=140,
    placeholder="https://i.pinimg.com/...\nhttps://images.unsplash.com/...",
    label_visibility="collapsed")
check_btn = st.button("Check Render-Readiness", type="primary")

if check_btn:
    urls = [u.strip() for u in url_input.splitlines() if u.strip()]
    if not urls:
        st.warning("Paste at least one image URL.")
    else:
        prompt = (
            f"Rate each image URL for Photoshop render use 1-10. "
            f"Criteria: clean/white background, matches {style} {mood} brief, good composition. "
            f"Return a markdown table: URL | Score | Reason. Show only scores 6+.\n"
            + "\n".join(urls))
        with st.spinner("Scoring images..."):
            response = client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=1024,
                messages=[{"role": "user", "content": prompt}])
        result = response.content[0].text.strip()
        st.markdown(result)

        rows = []
        for line in result.splitlines():
            if "|" in line and not re.match(r"^[\s|:-]+$", line):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if cells and cells[0].lower() not in ("url", ""):
                    rows.append(cells)

        if rows:
            buf = io.StringIO()
            csv.writer(buf).writerow(["URL", "Score", "Reason"])
            csv.writer(buf).writerows(rows)
            _, dl_col = st.columns([3, 1])
            with dl_col:
                st.download_button("Download CSV", buf.getvalue().encode(),
                                   "render_references.csv", "text/csv",
                                   use_container_width=True)

        passed, total = len(rows), len(urls)
        if passed:
            st.success(f"{passed} of {total} image{'s' if total!=1 else ''} scored 6+ — ready to download.")
        else:
            st.info(f"None of the {total} images scored 6 or above for this brief.")

st.divider()

# ── 05 — Mood Board ───────────────────────────────────────────────────────────
st.markdown("<div class='section-tag'>05 — Mood Board</div>", unsafe_allow_html=True)
st.header("Mood Board")

if not st.session_state.selected_images:
    st.info("Browse images and click **+ Board** on any image to start building your mood board.")
else:
    imgs = st.session_state.selected_images
    st.markdown(f"<p style='color:#7A6E68;font-size:0.9rem;'>{len(imgs)} image{'s' if len(imgs)!=1 else ''} selected</p>",
                unsafe_allow_html=True)

    mb_cols = st.columns(min(len(imgs), 4))
    for i, img in enumerate(imgs):
        with mb_cols[i % 4]:
            st.image(img["thumb"], use_container_width=True)
            if st.button("Remove", key=f"rm_{i}", use_container_width=True):
                st.session_state.selected_images.pop(i)
                st.rerun()

    st.markdown("---")
    col_a, col_b = st.columns([1, 1])
    with col_a:
        mb_cols_n = st.selectbox("Grid columns", [2, 3, 4], index=1)
    with col_b:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Generate Mood Board PNG", type="primary", use_container_width=True):
            with st.spinner("Compositing mood board..."):
                png = create_moodboard(imgs, cols=mb_cols_n)
            if png:
                st.image(png)
                st.download_button("Download Mood Board", png, "moodboard.png",
                                   "image/png", use_container_width=True)
                st.success("Mood board ready — click Download to save.")
            else:
                st.warning("Could not load images — check that URLs are accessible.")

st.divider()

# ── 06 — Prompt Generator ─────────────────────────────────────────────────────
st.markdown("<div class='section-tag'>06 — Prompt</div>", unsafe_allow_html=True)
st.header("AI Prompt Generator")
st.markdown(
    "<p style='color:#7A6E68;font-size:0.9rem;margin-top:-0.5rem;'>"
    "Generate a ready-to-paste Midjourney or Stable Diffusion prompt from your brief.</p>",
    unsafe_allow_html=True)

prompt_type = st.radio("Platform", ["Midjourney", "Stable Diffusion", "Both"],
                       horizontal=True, label_visibility="collapsed")
prompt_btn  = st.button("Generate Prompt", type="primary")

if prompt_btn:
    if not space or not mood:
        st.warning("Fill in **Space** and **Mood** in the brief first.")
    else:
        if prompt_type == "Midjourney":
            instr = "Generate a detailed Midjourney prompt only. End with --ar 16:9 --v 6.1 --style raw"
        elif prompt_type == "Stable Diffusion":
            instr = "Generate a detailed Stable Diffusion prompt only, including positive prompt tags separated by commas, then a Negative prompt: line."
        else:
            instr = "Generate both: 1) Midjourney prompt (end with --ar 16:9 --v 6.1 --style raw) and 2) Stable Diffusion prompt with positive tags and Negative prompt: line."

        full_prompt = (
            f"{instr}\n"
            f"Brief: Space: {space}, Style: {style}, Mood: {mood}, Background: {background}.\n"
            f"Include: camera angle, lighting quality, material palette, atmosphere, color grading. "
            f"Make it specific and evocative for architectural/interior visualization."
        )
        with st.spinner("Crafting prompt..."):
            response = client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=512,
                messages=[{"role": "user", "content": full_prompt}])
        result = response.content[0].text.strip()
        st.markdown(f"<div class='prompt-box'>{result}</div>", unsafe_allow_html=True)

        st.download_button("Copy as .txt", result.encode(), "render_prompt.txt", "text/plain")
        st.success("Prompt ready — paste directly into Midjourney or your SD interface.")
else:
    st.info("Set your brief, choose a platform, then click **Generate Prompt**.")

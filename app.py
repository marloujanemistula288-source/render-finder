import streamlit as st
import anthropic
import urllib.parse
import os
import csv
import io
import re
import requests
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Render Finder", layout="wide", initial_sidebar_state="expanded")

def get_secret(key):
    return st.secrets.get(key) or os.getenv(key)

client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

# ── Image search helpers ───────────────────────────────────────────────────────
def search_unsplash(query, n=9):
    key = get_secret("UNSPLASH_ACCESS_KEY")
    if not key:
        return []
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

def search_pexels(query, n=9):
    key = get_secret("PEXELS_API_KEY")
    if not key:
        return []
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

NOISE = "data:image/svg+xml,%3Csvg viewBox='0 0 512 512' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E"

# ── Theme: Zeronode-inspired cobalt + cool grey ────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600&family=Space+Mono:wght@400;700&display=swap');

/* ── Global ── */
html, body, [class*="css"] {{ font-family: 'Space Grotesk', sans-serif; }}
.stApp {{ background-color: #E4E4EA; color: #0C0C12; }}

/* ── Sidebar ── */
[data-testid="stSidebar"] {{
    background-color: #DADAE2 !important;
    border-right: 1px solid #BEBECE;
}}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p {{ color: #0C0C12 !important; }}
[data-testid="stSidebarNav"] {{ display: none; }}

/* ── Streamlit default headers (keep minimal) ── */
h1 {{
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 2rem !important;
    color: #0C0C12 !important;
    letter-spacing: -0.03em;
    font-weight: 600 !important;
    text-transform: uppercase;
}}
h2, h3 {{
    font-family: 'Space Grotesk', sans-serif !important;
    color: #0C0C12 !important;
    font-weight: 500 !important;
    letter-spacing: -0.01em;
}}

/* ── Hero card ── */
.hero-card {{
    position: relative;
    border-radius: 20px;
    overflow: hidden;
    margin-bottom: 2rem;
    padding: 2.8rem 2.2rem 2.2rem;
    min-height: 210px;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
}}
.hero-blob {{
    position: absolute;
    inset: 0;
    background:
        radial-gradient(ellipse at 28% 58%, #1533E8 0%, rgba(21,51,232,0.78) 18%, rgba(21,51,232,0.15) 45%, transparent 65%),
        radial-gradient(ellipse at 76% 22%, rgba(21,51,232,0.3) 0%, transparent 52%),
        #EEEEF8;
}}
.hero-noise {{
    position: absolute;
    inset: 0;
    background-image: url("{NOISE}");
    opacity: 0.09;
    pointer-events: none;
}}
.hero-content {{ position: relative; z-index: 1; }}
.hero-pill {{
    display: inline-block;
    background: rgba(255,255,255,0.16);
    border: 1px solid rgba(255,255,255,0.48);
    border-radius: 50px;
    padding: 0.55rem 1.6rem;
    color: white;
    font-size: 1rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    margin-bottom: 0.55rem;
}}
.hero-tagline {{
    font-size: 0.66rem;
    color: rgba(255,255,255,0.58);
    letter-spacing: 0.18em;
    text-transform: uppercase;
    font-family: 'Space Mono', monospace;
}}

/* ── Inputs ── */
input[type="text"], textarea {{
    background-color: #FFFFFF !important;
    border: 1px solid #BEBECE !important;
    border-radius: 50px !important;
    color: #0C0C12 !important;
    font-family: 'Space Grotesk', sans-serif !important;
}}
textarea {{ border-radius: 14px !important; }}
input[type="text"]:focus, textarea:focus {{
    border-color: #1533E8 !important;
    box-shadow: 0 0 0 2px rgba(21,51,232,0.12) !important;
}}

/* ── Select ── */
[data-testid="stSelectbox"] > div > div {{
    background-color: #FFFFFF !important;
    border: 1px solid #BEBECE !important;
    border-radius: 50px !important;
    color: #0C0C12 !important;
}}

/* ── Primary buttons ── */
.stButton > button[kind="primary"] {{
    background-color: #1533E8 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 50px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 500 !important;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    font-size: 0.75rem !important;
    transition: background-color 0.2s;
}}
.stButton > button[kind="primary"]:hover {{ background-color: #0F25C4 !important; }}

/* ── Secondary buttons ── */
.stButton > button[kind="secondary"] {{
    background-color: transparent !important;
    color: #0C0C12 !important;
    border: 1px solid #1533E8 !important;
    border-radius: 50px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 500 !important;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    font-size: 0.75rem !important;
}}
.stButton > button[kind="secondary"]:hover {{ background-color: rgba(21,51,232,0.06) !important; }}

/* ── Download button ── */
.stDownloadButton > button {{
    background-color: #0C0C12 !important;
    color: #E4E4EA !important;
    border: none !important;
    border-radius: 50px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 500 !important;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    font-size: 0.75rem !important;
}}
.stDownloadButton > button:hover {{ background-color: #1533E8 !important; }}

/* ── Alerts ── */
[data-testid="stAlert"] {{ border-radius: 12px !important; font-family: 'Space Grotesk', sans-serif !important; }}
.stSuccess {{ background-color: #E6EBFF !important; color: #0A1A8A !important; border-left: 3px solid #1533E8 !important; }}
.stInfo    {{ background-color: #EEEEF5 !important; color: #0C0C12 !important; border-left: 3px solid #8888AA !important; }}
.stWarning {{ background-color: #FFF4E6 !important; color: #5A3000 !important; border-left: 3px solid #E88015 !important; }}

/* ── Divider ── */
hr {{ border-color: #BEBECE !important; }}

/* ── Spinner ── */
.stSpinner > div {{ border-top-color: #1533E8 !important; }}

/* ── Query card (gradient blob panel) ── */
.query-card {{
    position: relative;
    border: 1px solid #CCCCDA;
    border-radius: 18px;
    overflow: hidden;
    margin-bottom: 1.2rem;
}}
.card-blob-area {{
    position: relative;
    min-height: 148px;
    padding: 1.3rem 1.3rem 1.2rem;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    background:
        radial-gradient(ellipse at 35% 62%, #1533E8 0%, rgba(21,51,232,0.72) 20%, rgba(21,51,232,0.12) 52%, transparent 68%),
        radial-gradient(ellipse at 80% 18%, rgba(21,51,232,0.26) 0%, transparent 50%),
        #EDEDF6;
}}
.card-noise {{
    position: absolute;
    inset: 0;
    background-image: url("{NOISE}");
    opacity: 0.09;
    pointer-events: none;
}}
.card-label {{
    position: relative;
    z-index: 1;
    font-size: 0.58rem;
    color: rgba(255,255,255,0.62);
    font-weight: 600;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    font-family: 'Space Mono', monospace;
    margin-bottom: 0.45rem;
}}
.card-query-pill {{
    position: relative;
    z-index: 1;
    display: inline-block;
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.4);
    border-radius: 50px;
    padding: 0.45rem 1.2rem;
    color: white;
    font-size: 0.88rem;
    font-weight: 500;
    font-style: italic;
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
    max-width: 100%;
    word-break: break-word;
}}
.card-content-area {{
    padding: 0.9rem 1.1rem 1rem;
    background: white;
}}

/* ── Preview strip ── */
.preview-strip {{
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.8rem;
}}
.preview-strip img {{
    width: calc(33.33% - 0.34rem);
    height: 90px;
    object-fit: cover;
    border-radius: 8px;
    border: 1px solid #CCCCDA;
}}
.preview-placeholder {{
    width: calc(33.33% - 0.34rem);
    height: 90px;
    background: #EEEEF5;
    border-radius: 8px;
    border: 1px solid #CCCCDA;
}}
.btn-row {{ display: flex; flex-wrap: wrap; gap: 0.3rem; }}

/* ── Platform ref buttons ── */
.ref-btn {{
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.38rem 0.95rem;
    margin: 0.15rem 0.2rem 0.15rem 0;
    border-radius: 50px;
    text-decoration: none !important;
    font-size: 0.68rem;
    font-weight: 500;
    font-family: 'Space Grotesk', sans-serif;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    transition: opacity 0.2s;
    border: 1px solid transparent;
}}
.ref-btn:hover {{ opacity: 0.68; }}
.btn-pinterest {{ background-color: #1533E8; color: #fff !important; }}
.btn-behance   {{ background-color: #0C0C12; color: #E4E4EA !important; }}
.btn-google    {{ background-color: #F0F0F8; color: #0C0C12 !important; border: 1px solid #BEBECE; }}
.btn-archinect {{ background-color: #E4E4EA; color: #0C0C12 !important; border: 1px solid #BEBECE; }}
.btn-arena     {{ background-color: rgba(21,51,232,0.1); color: #1533E8 !important; border: 1px solid rgba(21,51,232,0.22); }}

/* ── Image badge ── */
.badge {{
    display: inline-block;
    padding: 0.1rem 0.5rem;
    border-radius: 50px;
    font-size: 0.6rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}}
.badge-unsplash {{ background: #0C0C12; color: #E4E4EA; }}
.badge-pexels   {{ background: #1533E8; color: #fff; }}

/* ── Section label ── */
.section-tag {{
    font-size: 0.6rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: #1533E8;
    font-weight: 700;
    margin-bottom: 0.2rem;
    font-family: 'Space Mono', monospace;
}}
</style>
""", unsafe_allow_html=True)

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="hero-card">
    <div class="hero-blob"></div>
    <div class="hero-noise"></div>
    <div class="hero-content">
        <div class="hero-pill">Render Finder</div>
        <div class="hero-tagline">AI-powered image curation for Photoshop renders</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div class='section-tag'>Project Brief</div>", unsafe_allow_html=True)
    st.markdown("### Brief")

    space = st.text_input("Space", placeholder="e.g. living room, courtyard, office")
    style = st.selectbox("Style", ["Dreamy", "Dark Moody", "Minimal", "Maximalist", "Realistic CGI"])
    mood = st.text_input("Mood", placeholder="e.g. warm and earthy, editorial, serene")
    background = st.selectbox("Background", ["White/Isolated", "Scene", "Any"])

    st.markdown("---")
    find_btn   = st.button("Find References", use_container_width=True, type="primary")
    browse_btn = st.button("Browse Images",   use_container_width=True)

# ── Section 1: Reference Queries ───────────────────────────────────────────────
st.markdown("<div class='section-tag'>01 — Search</div>", unsafe_allow_html=True)
st.header("Reference Queries")

if find_btn:
    if not space or not mood:
        st.warning("Please fill in **Space** and **Mood** before searching.")
    else:
        prompt = (
            f"Generate 5 targeted search queries for a designer finding Photoshop render references. "
            f"Brief — Space: {space}, Style: {style}, Mood: {mood}, Background: {background}. "
            f"Use designer vocabulary. Return numbered list only, no extra text."
        )
        with st.spinner("Generating queries..."):
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
        raw = response.content[0].text.strip()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]

        has_preview_keys = bool(get_secret("UNSPLASH_ACCESS_KEY") or get_secret("PEXELS_API_KEY"))

        for i, line in enumerate(lines, 1):
            query_text = line.lstrip("0123456789. ").strip('"')
            enc = urllib.parse.quote_plus(query_text)

            pinterest_url = f"https://www.pinterest.com/search/pins/?q={enc}"
            behance_url   = f"https://www.behance.net/search/projects?search={enc}"
            google_url    = f"https://www.google.com/search?tbm=isch&q={enc}"
            archinect_url = f"https://archinect.com/search#/?q={enc}&type=photos"
            arena_url     = f"https://www.are.na/search/{enc}"

            previews = []
            if has_preview_keys:
                previews = search_unsplash(query_text, n=3)
                if len(previews) < 3:
                    previews += search_pexels(query_text, n=3 - len(previews))

            if previews:
                strip_html = '<div class="preview-strip">' + "".join(
                    f'<a href="{p["link"]}" target="_blank" rel="noopener">'
                    f'<img src="{p["thumb"]}" alt="{p["author"]}"></a>'
                    for p in previews[:3]
                ) + "</div>"
            elif has_preview_keys:
                strip_html = '<div class="preview-strip">' + ''.join(
                    '<div class="preview-placeholder"></div>' for _ in range(3)
                ) + "</div>"
            else:
                strip_html = ""

            card_html = f"""
            <div class="query-card">
                <div class="card-blob-area">
                    <div class="card-noise"></div>
                    <div class="card-label">Query {i}</div>
                    <div class="card-query-pill">{query_text}</div>
                </div>
                <div class="card-content-area">
                    {strip_html}
                    <div class="btn-row">
                        <a class="ref-btn btn-pinterest" href="{pinterest_url}" target="_blank" rel="noopener">Pinterest</a>
                        <a class="ref-btn btn-behance"   href="{behance_url}"   target="_blank" rel="noopener">Behance</a>
                        <a class="ref-btn btn-google"    href="{google_url}"    target="_blank" rel="noopener">Google Images</a>
                        <a class="ref-btn btn-archinect" href="{archinect_url}" target="_blank" rel="noopener">Archinect</a>
                        <a class="ref-btn btn-arena"     href="{arena_url}"     target="_blank" rel="noopener">Are.na</a>
                    </div>
                </div>
            </div>"""
            st.markdown(card_html, unsafe_allow_html=True)

        if not has_preview_keys:
            st.info("Add **UNSPLASH_ACCESS_KEY** or **PEXELS_API_KEY** to your secrets to see image previews.")
        st.success(f"{len(lines)} queries generated — click any image or platform button to explore.")
else:
    st.info("Fill in the brief and click **Find References** to generate search queries.")

st.divider()

# ── Section 2: Browse Images ───────────────────────────────────────────────────
st.markdown("<div class='section-tag'>02 — Browse</div>", unsafe_allow_html=True)
st.header("Browse Reference Images")

if browse_btn:
    if not space or not mood:
        st.warning("Please fill in **Space** and **Mood** before browsing.")
    else:
        query = f"{style} {space} {mood} interior architecture"
        if not get_secret("UNSPLASH_ACCESS_KEY") and not get_secret("PEXELS_API_KEY"):
            st.warning("Add **UNSPLASH_ACCESS_KEY** and/or **PEXELS_API_KEY** to your Streamlit secrets.")
        else:
            with st.spinner("Fetching images..."):
                images = search_unsplash(query, n=9) + search_pexels(query, n=9)
            if not images:
                st.info("No images found — try adjusting the brief.")
            else:
                cols = st.columns(3)
                for i, img in enumerate(images):
                    badge_class = "badge-unsplash" if img["source"] == "unsplash" else "badge-pexels"
                    badge_label = "Unsplash" if img["source"] == "unsplash" else "Pexels"
                    with cols[i % 3]:
                        st.image(img["thumb"], use_container_width=True)
                        st.markdown(
                            f'<span class="badge {badge_class}">{badge_label}</span> '
                            f'<a href="{img["link"]}" target="_blank" '
                            f'style="font-size:0.78rem;color:#6B6B80;text-decoration:none;">'
                            f'{img["author"]}</a>',
                            unsafe_allow_html=True,
                        )
                st.success(f"Showing {len(images)} images for '{query}'")
else:
    st.info("Click **Browse Images** in the sidebar to pull real photos from Unsplash & Pexels.")

st.divider()

# ── Section 3: Filter Images ───────────────────────────────────────────────────
st.markdown("<div class='section-tag'>03 — Filter</div>", unsafe_allow_html=True)
st.header("Filter Images")
st.markdown(
    "<p style='color:#6B6B80; font-size:0.88rem; margin-top:-0.5rem; letter-spacing:0.01em;'>"
    "Paste image URLs (one per line) — Claude will score each for render-readiness.</p>",
    unsafe_allow_html=True,
)

url_input = st.text_area(
    "Image URLs",
    height=160,
    placeholder="https://i.pinimg.com/...\nhttps://images.unsplash.com/...",
    label_visibility="collapsed",
)
check_btn = st.button("Check Render-Readiness", type="primary")

if check_btn:
    urls = [u.strip() for u in url_input.splitlines() if u.strip()]
    if not urls:
        st.warning("Paste at least one image URL before checking.")
    else:
        prompt = (
            f"Rate each image URL for Photoshop render use 1-10. "
            f"Criteria: clean/white background, matches {style} {mood} brief, good composition. "
            f"Return a markdown table with columns: URL | Score | Reason. "
            f"Show only images with scores 6 or higher. "
            f"URLs:\n" + "\n".join(urls)
        )
        with st.spinner("Scoring images..."):
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
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
            writer = csv.writer(buf)
            writer.writerow(["URL", "Score", "Reason"])
            writer.writerows(rows)
            col1, col2 = st.columns([3, 1])
            with col2:
                st.download_button(
                    label="Download CSV",
                    data=buf.getvalue().encode(),
                    file_name="render_references.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        passed, total = len(rows), len(urls)
        if passed:
            st.success(f"{passed} of {total} image{'s' if total != 1 else ''} scored 6+ — ready to download.")
        else:
            st.info(f"None of the {total} images scored 6 or above for this brief.")

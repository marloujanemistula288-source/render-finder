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

NOISE = "data:image/svg+xml,%3Csvg viewBox='0 0 512 512' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.72' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600&family=Space+Mono:wght@400;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Space Grotesk', sans-serif;
}}

/* ── Page base ── */
.stApp {{
    background-color: #EAEAED;
}}

/* ── LEFT PANEL: clean white sidebar ── */
[data-testid="stSidebar"] {{
    background: #F4F4F7 !important;
    border-right: 1px solid rgba(200,200,215,0.55) !important;
    backdrop-filter: none !important;
}}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p {{ color: #0C0C12 !important; }}
[data-testid="stSidebarNav"] {{ display: none; }}

/* ── RIGHT AREA: gradient blob on main content ── */
[data-testid="stMain"],
section.main {{
    background:
        radial-gradient(ellipse at 80% 64%, #1533E8 0%, rgba(21,51,232,0.72) 19%, rgba(21,51,232,0.14) 46%, transparent 63%),
        radial-gradient(ellipse at 95% 18%, rgba(21,51,232,0.28) 0%, transparent 40%),
        radial-gradient(ellipse at 55% 92%, rgba(21,51,232,0.18) 0%, transparent 36%),
        #EAEAED !important;
    background-attachment: fixed !important;
}}

/* Grain texture over main area */
[data-testid="stMain"]::before,
section.main::before {{
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background-image: url("{NOISE}");
    opacity: 0.07;
    pointer-events: none;
    z-index: 0;
}}

/* Transparent block containers so gradient shows */
.block-container,
[data-testid="stMainBlockContainer"] {{
    background: transparent !important;
    position: relative;
    z-index: 1;
}}

/* ── Headers ── */
h1 {{
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 1.9rem !important;
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

/* ── Hero section ── */
.hero-section {{
    padding: 2.6rem 0 2rem;
    max-width: 520px;
}}
.hero-tag {{
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background: rgba(255,255,255,0.55);
    border: 1px solid rgba(255,255,255,0.78);
    border-radius: 50px;
    padding: 0.32rem 1rem;
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #1533E8;
    font-family: 'Space Mono', monospace;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    margin-bottom: 1.3rem;
}}
.tag-dot {{
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #1533E8;
    flex-shrink: 0;
}}
.hero-title {{
    font-size: 3rem;
    font-weight: 600;
    color: #0C0C12;
    letter-spacing: -0.04em;
    line-height: 1.06;
    margin-bottom: 1rem;
    font-family: 'Space Grotesk', sans-serif;
}}
.hero-title em {{
    font-style: italic;
    font-weight: 300;
    color: #1533E8;
}}
.hero-body {{
    font-size: 0.92rem;
    color: #5A5A6E;
    line-height: 1.65;
    font-weight: 400;
    max-width: 400px;
}}

/* ── Frosted glass query cards ── */
.query-card {{
    background: rgba(255,255,255,0.58);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.78);
    border-radius: 18px;
    overflow: hidden;
    margin-bottom: 1rem;
}}
.query-card-inner {{
    padding: 1.2rem 1.3rem 1.1rem;
}}
.card-label {{
    font-size: 0.58rem;
    color: #1533E8;
    font-weight: 700;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    font-family: 'Space Mono', monospace;
    margin-bottom: 0.35rem;
}}
.card-query-text {{
    font-size: 0.95rem;
    color: #0C0C12;
    font-weight: 500;
    font-style: italic;
    margin-bottom: 0.9rem;
    line-height: 1.4;
}}

/* ── Preview strip ── */
.preview-strip {{
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.85rem;
}}
.preview-strip img {{
    width: calc(33.33% - 0.34rem);
    height: 88px;
    object-fit: cover;
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.6);
}}
.preview-placeholder {{
    width: calc(33.33% - 0.34rem);
    height: 88px;
    background: rgba(255,255,255,0.28);
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.5);
}}
.btn-row {{ display: flex; flex-wrap: wrap; gap: 0.3rem; }}

/* ── Platform buttons ── */
.ref-btn {{
    display: inline-flex;
    align-items: center;
    padding: 0.36rem 0.9rem;
    border-radius: 50px;
    text-decoration: none !important;
    font-size: 0.67rem;
    font-weight: 500;
    font-family: 'Space Grotesk', sans-serif;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    transition: opacity 0.2s;
    border: 1px solid transparent;
}}
.ref-btn:hover {{ opacity: 0.68; }}
.btn-pinterest {{ background: #1533E8; color: #fff !important; }}
.btn-behance   {{ background: #0C0C12; color: #EAEAED !important; }}
.btn-google    {{ background: rgba(255,255,255,0.72); color: #0C0C12 !important; border: 1px solid rgba(0,0,0,0.1); }}
.btn-archinect {{ background: rgba(255,255,255,0.42); color: #0C0C12 !important; border: 1px solid rgba(0,0,0,0.08); }}
.btn-arena     {{ background: rgba(21,51,232,0.1); color: #1533E8 !important; border: 1px solid rgba(21,51,232,0.2); }}

/* ── Inputs ── */
input[type="text"], textarea {{
    background-color: rgba(255,255,255,0.88) !important;
    border: 1px solid rgba(200,200,215,0.7) !important;
    border-radius: 50px !important;
    color: #0C0C12 !important;
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
    border-radius: 50px !important;
    color: #0C0C12 !important;
}}

/* ── Streamlit buttons ── */
.stButton > button[kind="primary"] {{
    background-color: #1533E8 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 50px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 500 !important;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    font-size: 0.74rem !important;
}}
.stButton > button[kind="primary"]:hover {{ background-color: #0F25C4 !important; }}
.stButton > button[kind="secondary"] {{
    background-color: rgba(255,255,255,0.6) !important;
    color: #0C0C12 !important;
    border: 1px solid rgba(0,0,0,0.14) !important;
    border-radius: 50px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 500 !important;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    font-size: 0.74rem !important;
}}
.stButton > button[kind="secondary"]:hover {{ background-color: rgba(255,255,255,0.88) !important; }}
.stDownloadButton > button {{
    background-color: #0C0C12 !important;
    color: #EAEAED !important;
    border: none !important;
    border-radius: 50px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 500 !important;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    font-size: 0.74rem !important;
}}
.stDownloadButton > button:hover {{ background-color: #1533E8 !important; }}

/* ── Alerts: frosted ── */
[data-testid="stAlert"] {{
    border-radius: 12px !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    font-family: 'Space Grotesk', sans-serif !important;
}}
.stSuccess {{ background: rgba(230,235,255,0.72) !important; color: #0A1A8A !important; border-left: 3px solid #1533E8 !important; }}
.stInfo    {{ background: rgba(255,255,255,0.52) !important; color: #0C0C12 !important; border-left: 3px solid rgba(100,100,140,0.5) !important; }}
.stWarning {{ background: rgba(255,244,230,0.72) !important; color: #5A3000 !important; border-left: 3px solid #E88015 !important; }}

/* ── Filter pills (st.pills) ── */
[data-testid="stPillsInput"] button {{
    border-radius: 50px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 0.72rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.05em !important;
    background: rgba(255,255,255,0.55) !important;
    border: 1px solid rgba(200,200,215,0.65) !important;
    color: #0C0C12 !important;
    transition: all 0.15s !important;
}}
[data-testid="stPillsInput"] button[aria-pressed="true"] {{
    background: #1533E8 !important;
    border-color: #1533E8 !important;
    color: #fff !important;
}}
[data-testid="stPillsInput"] button:hover {{
    background: rgba(21,51,232,0.1) !important;
    border-color: rgba(21,51,232,0.3) !important;
}}

/* ── Misc ── */
hr {{ border-color: rgba(0,0,0,0.08) !important; }}
.stSpinner > div {{ border-top-color: #1533E8 !important; }}
.badge {{
    display: inline-block;
    padding: 0.1rem 0.5rem;
    border-radius: 50px;
    font-size: 0.6rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}}
.badge-unsplash {{ background: #0C0C12; color: #EAEAED; }}
.badge-pexels   {{ background: #1533E8; color: #fff; }}
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

# ── Hero ───────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-section">
    <div class="hero-tag"><span class="tag-dot"></span>AI-Powered Image Curation</div>
    <div class="hero-title">Find the right<br>references,<br><em>every time.</em></div>
    <div class="hero-body">Generate targeted search queries for your Photoshop renders — curated by AI for architecture and interior design.</div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar: clean white left panel ───────────────────────────────────────────
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
                <div class="query-card-inner">
                    <div class="card-label">Query {i}</div>
                    <div class="card-query-text">{query_text}</div>
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

# ── Section 2: Filter & Browse ─────────────────────────────────────────────────
st.markdown("<div class='section-tag'>02 — Filter</div>", unsafe_allow_html=True)
st.header("Filter & Browse")
st.markdown(
    "<p style='color:#5A5A6E;font-size:0.88rem;margin-top:-0.5rem;margin-bottom:1.2rem;'>"
    "Select tags to browse images directly — no prompts needed.</p>",
    unsafe_allow_html=True,
)

fc1, fc2 = st.columns(2)
with fc1:
    filter_spaces = st.pills(
        "Space type",
        ["Living Room", "Bedroom", "Kitchen", "Office", "Courtyard",
         "Rooftop", "Restaurant", "Hotel Lobby", "Retail"],
        selection_mode="multi", key="filter_spaces",
    )
    filter_styles = st.pills(
        "Style",
        ["Dreamy", "Dark Moody", "Minimal", "Maximalist", "Rustic",
         "Industrial", "Scandinavian", "Japanese", "Mediterranean"],
        selection_mode="multi", key="filter_styles",
    )
with fc2:
    filter_moods = st.pills(
        "Mood",
        ["Warm & Earthy", "Cool & Fresh", "Dramatic", "Serene",
         "Editorial", "Cozy", "Luxurious", "Raw & Textured"],
        selection_mode="multi", key="filter_moods",
    )
    filter_light = st.pills(
        "Lighting",
        ["Natural Light", "Golden Hour", "Moody Low Light", "Overcast", "Artificial"],
        selection_mode="multi", key="filter_light",
    )

filter_btn = st.button("Browse Filtered Images", type="primary", key="filter_browse")

if filter_btn:
    all_tags = (list(filter_spaces or []) + list(filter_styles or []) +
                list(filter_moods or []) + list(filter_light or []))
    if not all_tags:
        st.warning("Select at least one filter tag to browse images.")
    elif not get_secret("UNSPLASH_ACCESS_KEY") and not get_secret("PEXELS_API_KEY"):
        st.warning("Add **UNSPLASH_ACCESS_KEY** and/or **PEXELS_API_KEY** to your secrets to see images.")
    else:
        filter_query = " ".join(all_tags) + " interior architecture"
        with st.spinner("Fetching images..."):
            images = search_unsplash(filter_query, n=9) + search_pexels(filter_query, n=9)
        if not images:
            st.info("No images found — try different filter tags.")
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
                        f'style="font-size:0.78rem;color:#5A5A6E;text-decoration:none;">'
                        f'{img["author"]}</a>',
                        unsafe_allow_html=True,
                    )
            st.success(f"Showing {len(images)} images for: {', '.join(all_tags)}")
else:
    st.info("Select filter tags above and click **Browse Filtered Images**.")

st.divider()

# ── Section 3: Browse Images ───────────────────────────────────────────────────
st.markdown("<div class='section-tag'>03 — Browse</div>", unsafe_allow_html=True)
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
                            f'style="font-size:0.78rem;color:#5A5A6E;text-decoration:none;">'
                            f'{img["author"]}</a>',
                            unsafe_allow_html=True,
                        )
                st.success(f"Showing {len(images)} images for '{query}'")
else:
    st.info("Click **Browse Images** in the sidebar to pull real photos from Unsplash & Pexels.")

st.divider()

# ── Section 4: Score URLs ──────────────────────────────────────────────────────
st.markdown("<div class='section-tag'>04 — Score</div>", unsafe_allow_html=True)
st.header("Filter Images")
st.markdown(
    "<p style='color:#5A5A6E;font-size:0.88rem;margin-top:-0.5rem;'>"
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

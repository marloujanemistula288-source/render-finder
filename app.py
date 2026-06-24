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

# ── Theme: warm concrete + terracotta palette ──────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600&family=Space+Mono:wght@400;700&display=swap');

/* ── Global ── */
html, body, [class*="css"] {
    font-family: 'Space Grotesk', sans-serif;
}
.stApp {
    background-color: #E8E8ED;
    color: #0C0C12;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: #DDDDE6 !important;
    border-right: 1px solid #C4C4D0;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p {
    color: #0C0C12 !important;
}
[data-testid="stSidebarNav"] { display: none; }

/* ── Headers ── */
h1 {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 2.6rem !important;
    color: #0C0C12 !important;
    letter-spacing: -0.03em;
    font-weight: 600 !important;
    text-transform: uppercase;
}
h2, h3 {
    font-family: 'Space Grotesk', sans-serif !important;
    color: #0C0C12 !important;
    font-weight: 500 !important;
    letter-spacing: -0.01em;
}

/* ── Inputs ── */
input[type="text"], textarea {
    background-color: #FFFFFF !important;
    border: 1px solid #C4C4D0 !important;
    border-radius: 50px !important;
    color: #0C0C12 !important;
    font-family: 'Space Grotesk', sans-serif !important;
}
input[type="text"]:focus, textarea:focus {
    border-color: #1533E8 !important;
    box-shadow: 0 0 0 2px rgba(21,51,232,0.12) !important;
}

/* ── Select / Dropdown ── */
[data-testid="stSelectbox"] > div > div {
    background-color: #FFFFFF !important;
    border: 1px solid #C4C4D0 !important;
    border-radius: 50px !important;
    color: #0C0C12 !important;
}

/* ── Primary buttons ── */
.stButton > button[kind="primary"] {
    background-color: #1533E8 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 50px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 500 !important;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    font-size: 0.78rem !important;
    transition: background-color 0.2s;
}
.stButton > button[kind="primary"]:hover {
    background-color: #0F25C4 !important;
}

/* ── Secondary buttons ── */
.stButton > button[kind="secondary"] {
    background-color: transparent !important;
    color: #0C0C12 !important;
    border: 1px solid #1533E8 !important;
    border-radius: 50px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 500 !important;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    font-size: 0.78rem !important;
}
.stButton > button[kind="secondary"]:hover {
    background-color: rgba(21,51,232,0.06) !important;
}

/* ── Download button ── */
.stDownloadButton > button {
    background-color: #0C0C12 !important;
    color: #E8E8ED !important;
    border: none !important;
    border-radius: 50px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 500 !important;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    font-size: 0.78rem !important;
}
.stDownloadButton > button:hover {
    background-color: #1533E8 !important;
}

/* ── Alert boxes ── */
[data-testid="stAlert"] {
    border-radius: 12px !important;
    font-family: 'Space Grotesk', sans-serif !important;
}
.stSuccess { background-color: #E6EBFF !important; color: #0A1A8A !important; border-left: 3px solid #1533E8 !important; }
.stInfo    { background-color: #F0F0F5 !important; color: #0C0C12 !important; border-left: 3px solid #8888AA !important; }
.stWarning { background-color: #FFF4E6 !important; color: #5A3000 !important; border-left: 3px solid #E88015 !important; }

/* ── Divider ── */
hr { border-color: #C4C4D0 !important; }

/* ── Spinner ── */
.stSpinner > div { border-top-color: #1533E8 !important; }

/* ── Reference link buttons ── */
.ref-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 1rem;
    margin: 0.2rem 0.3rem 0.2rem 0;
    border-radius: 50px;
    text-decoration: none !important;
    font-size: 0.72rem;
    font-weight: 500;
    font-family: 'Space Grotesk', sans-serif;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    transition: opacity 0.2s;
    border: 1px solid transparent;
}
.ref-btn:hover { opacity: 0.72; }
.btn-pinterest  { background-color: #1533E8; color: #fff !important; }
.btn-behance    { background-color: #0C0C12; color: #E8E8ED !important; }
.btn-google     { background-color: #FFFFFF; color: #0C0C12 !important; border: 1px solid #C4C4D0; }
.btn-archinect  { background-color: #E8E8ED; color: #0C0C12 !important; border: 1px solid #C4C4D0; }
.btn-arena      { background-color: #1533E8; color: #fff !important; opacity: 0.75; }

/* ── Query card ── */
.query-card {
    background: #FFFFFF;
    border: 1px solid #D4D4DF;
    border-radius: 16px;
    padding: 1rem 1.1rem 0.8rem;
    margin-bottom: 1rem;
}
.query-header {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    margin-bottom: 0.7rem;
}
.query-label {
    font-size: 0.68rem;
    color: #1533E8;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    font-family: 'Space Mono', monospace;
}
.query-text {
    font-size: 0.95rem;
    color: #0C0C12;
    font-style: italic;
}
.preview-strip {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
}
.preview-strip img {
    width: calc(33.33% - 0.34rem);
    height: 100px;
    object-fit: cover;
    border-radius: 10px;
    border: 1px solid #D4D4DF;
}
.preview-placeholder {
    width: calc(33.33% - 0.34rem);
    height: 100px;
    background: #E8E8ED;
    border-radius: 10px;
    border: 1px solid #D4D4DF;
}
.btn-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
}

/* ── Image badge ── */
.badge {
    display: inline-block;
    padding: 0.12rem 0.55rem;
    border-radius: 50px;
    font-size: 0.62rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.badge-unsplash { background: #0C0C12; color: #E8E8ED; }
.badge-pexels   { background: #1533E8; color: #fff; }

/* ── Subtitle ── */
.subtitle {
    font-size: 0.8rem;
    color: #6B6B80;
    margin-top: -0.8rem;
    margin-bottom: 1.5rem;
    font-weight: 400;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

/* ── Section label ── */
.section-tag {
    font-size: 0.65rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #1533E8;
    font-weight: 700;
    margin-bottom: 0.2rem;
    font-family: 'Space Mono', monospace;
}
</style>
""", unsafe_allow_html=True)

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("<div class='section-tag'>Tool</div>", unsafe_allow_html=True)
st.title("Render Finder")
st.markdown("<div class='subtitle'>AI-powered image curation for Photoshop renders</div>", unsafe_allow_html=True)

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

            # Fetch 3 preview images from Unsplash then Pexels
            previews = []
            if has_preview_keys:
                previews = search_unsplash(query_text, n=3)
                if len(previews) < 3:
                    previews += search_pexels(query_text, n=3 - len(previews))

            # Build preview strip HTML
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
                <div class="query-header">
                    <span class="query-label">Query {i}</span>
                    <span class="query-text">{query_text}</span>
                </div>
                {strip_html}
                <div class="btn-row">
                    <a class="ref-btn btn-pinterest" href="{pinterest_url}" target="_blank" rel="noopener">Pinterest</a>
                    <a class="ref-btn btn-behance"   href="{behance_url}"   target="_blank" rel="noopener">Behance</a>
                    <a class="ref-btn btn-google"    href="{google_url}"    target="_blank" rel="noopener">Google Images</a>
                    <a class="ref-btn btn-archinect" href="{archinect_url}" target="_blank" rel="noopener">Archinect</a>
                    <a class="ref-btn btn-arena"     href="{arena_url}"     target="_blank" rel="noopener">Are.na</a>
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
                            f'style="font-size:0.78rem;color:#7A6E68;text-decoration:none;">'
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
    "<p style='color:#7A6E68; font-size:0.9rem; margin-top:-0.5rem;'>"
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

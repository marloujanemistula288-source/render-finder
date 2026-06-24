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

# ── Theme: warm concrete + terracotta palette ──────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500&family=DM+Serif+Display&display=swap');

/* ── Global ── */
html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}
.stApp {
    background-color: #EDE8E1;
    color: #2C2520;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: #E0D8CF !important;
    border-right: 1px solid #C8BFB5;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p {
    color: #2C2520 !important;
}
[data-testid="stSidebarNav"] { display: none; }

/* ── Headers ── */
h1 {
    font-family: 'DM Serif Display', serif !important;
    font-size: 2.6rem !important;
    color: #2C2520 !important;
    letter-spacing: -0.02em;
    font-weight: 400 !important;
}
h2, h3 {
    font-family: 'DM Serif Display', serif !important;
    color: #2C2520 !important;
    font-weight: 400 !important;
    letter-spacing: -0.01em;
}

/* ── Inputs ── */
input[type="text"], textarea {
    background-color: #F5F0EA !important;
    border: 1px solid #C8BFB5 !important;
    border-radius: 6px !important;
    color: #2C2520 !important;
    font-family: 'DM Sans', sans-serif !important;
}
input[type="text"]:focus, textarea:focus {
    border-color: #B5634A !important;
    box-shadow: 0 0 0 2px rgba(181,99,74,0.15) !important;
}

/* ── Select / Dropdown ── */
[data-testid="stSelectbox"] > div > div {
    background-color: #F5F0EA !important;
    border: 1px solid #C8BFB5 !important;
    border-radius: 6px !important;
    color: #2C2520 !important;
}

/* ── Primary buttons ── */
.stButton > button[kind="primary"] {
    background-color: #B5634A !important;
    color: #F5F0EA !important;
    border: none !important;
    border-radius: 6px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em;
    transition: background-color 0.2s;
}
.stButton > button[kind="primary"]:hover {
    background-color: #9A5038 !important;
}

/* ── Secondary buttons ── */
.stButton > button[kind="secondary"] {
    background-color: transparent !important;
    color: #2C2520 !important;
    border: 1px solid #B5634A !important;
    border-radius: 6px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
}
.stButton > button[kind="secondary"]:hover {
    background-color: #B5634A22 !important;
}

/* ── Download button ── */
.stDownloadButton > button {
    background-color: #7D9178 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 6px !important;
    font-family: 'DM Sans', sans-serif !important;
}
.stDownloadButton > button:hover {
    background-color: #667A62 !important;
}

/* ── Alert boxes ── */
[data-testid="stAlert"] {
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
}
.stSuccess { background-color: #D8E5D5 !important; color: #2C3D28 !important; border-left: 4px solid #7D9178 !important; }
.stInfo    { background-color: #E8E4DE !important; color: #2C2520 !important; border-left: 4px solid #A09489 !important; }
.stWarning { background-color: #F0E4D8 !important; color: #3D2515 !important; border-left: 4px solid #B5634A !important; }

/* ── Divider ── */
hr { border-color: #C8BFB5 !important; }

/* ── Spinner ── */
.stSpinner > div { border-top-color: #B5634A !important; }

/* ── Reference link buttons ── */
.ref-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.5rem 1.1rem;
    margin: 0.2rem 0.3rem 0.2rem 0;
    border-radius: 6px;
    text-decoration: none !important;
    font-size: 0.82rem;
    font-weight: 500;
    font-family: 'DM Sans', sans-serif;
    letter-spacing: 0.02em;
    transition: opacity 0.2s;
}
.ref-btn:hover { opacity: 0.82; }
.btn-pinterest  { background-color: #B5634A; color: #fff !important; }
.btn-behance    { background-color: #1769FF; color: #fff !important; }
.btn-google     { background-color: #F5F0EA; color: #2C2520 !important; border: 1px solid #C8BFB5; }
.btn-archinect  { background-color: #2C2520; color: #EDE8E1 !important; }
.btn-arena      { background-color: #7D9178; color: #fff !important; }

/* ── Query row ── */
.query-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.25rem;
    padding: 0.6rem 0;
    border-bottom: 1px solid #D5CCC5;
}
.query-label {
    font-size: 0.85rem;
    color: #7A6E68;
    min-width: 1.4rem;
    font-weight: 300;
}
.query-text {
    font-size: 0.92rem;
    color: #2C2520;
    flex: 1;
    min-width: 160px;
    font-style: italic;
}

/* ── Image badge ── */
.badge {
    display: inline-block;
    padding: 0.12rem 0.5rem;
    border-radius: 4px;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.badge-unsplash { background: #2C2520; color: #EDE8E1; }
.badge-pexels   { background: #7D9178; color: #fff; }

/* ── Subtitle ── */
.subtitle {
    font-size: 1rem;
    color: #7A6E68;
    margin-top: -0.8rem;
    margin-bottom: 1.5rem;
    font-weight: 300;
    letter-spacing: 0.01em;
}

/* ── Section label ── */
.section-tag {
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #B5634A;
    font-weight: 500;
    margin-bottom: 0.2rem;
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

        rows_html = ""
        for i, line in enumerate(lines, 1):
            query_text = line.lstrip("0123456789. ").strip('"')
            enc = urllib.parse.quote_plus(query_text)

            pinterest_url  = f"https://www.pinterest.com/search/pins/?q={enc}"
            behance_url    = f"https://www.behance.net/search/projects?search={enc}"
            google_url     = f"https://www.google.com/search?tbm=isch&q={enc}"
            archinect_url  = f"https://archinect.com/search#/?q={enc}&type=photos"
            arena_url      = f"https://www.are.na/search/{enc}"

            rows_html += f"""
            <div class="query-row">
                <span class="query-label">{i}.</span>
                <span class="query-text">{query_text}</span>
                <a class="ref-btn btn-pinterest"  href="{pinterest_url}"  target="_blank" rel="noopener">Pinterest</a>
                <a class="ref-btn btn-behance"    href="{behance_url}"    target="_blank" rel="noopener">Behance</a>
                <a class="ref-btn btn-google"     href="{google_url}"     target="_blank" rel="noopener">Google Images</a>
                <a class="ref-btn btn-archinect"  href="{archinect_url}"  target="_blank" rel="noopener">Archinect</a>
                <a class="ref-btn btn-arena"      href="{arena_url}"      target="_blank" rel="noopener">Are.na</a>
            </div>"""

        st.markdown(rows_html, unsafe_allow_html=True)
        st.success(f"{len(lines)} queries generated — open on any platform.")
else:
    st.info("Fill in the brief and click **Find References** to generate search queries.")

st.divider()

# ── Section 2: Browse Images ───────────────────────────────────────────────────
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

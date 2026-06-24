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

st.set_page_config(page_title="Render Finder", layout="wide")

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("Render Finder")
st.markdown(
    "<p style='font-size:1.1rem; color:gray; margin-top:-0.5rem;'>"
    "AI-powered image curation for Photoshop renders</p>",
    unsafe_allow_html=True,
)

def get_secret(key):
    return st.secrets.get(key) or os.getenv(key)

client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

# ── Sidebar: Brief Form ────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Brief")

    space = st.text_input("Space", placeholder="e.g. living room, bedroom, office")
    style = st.selectbox("Style", ["Dreamy", "Dark Moody", "Minimal", "Maximalist", "Realistic CGI"])
    mood = st.text_input("Mood", placeholder="e.g. warm and cozy, editorial, serene")
    background = st.selectbox("Background", ["White/Isolated", "Scene", "Any"])

    find_btn = st.button("Find References", use_container_width=True, type="primary")
    browse_btn = st.button("Browse Images", use_container_width=True)

# ── Styles ─────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .pinterest-btn {
        display: inline-block;
        padding: 0.45rem 1rem;
        margin: 0.25rem 0;
        background-color: #E60023;
        color: #fff !important;
        border-radius: 6px;
        text-decoration: none !important;
        font-size: 0.875rem;
        font-weight: 500;
        transition: background-color 0.2s;
    }
    .pinterest-btn:hover { background-color: #ad081b; }
    .pinterest-btn::before { content: "⊞  "; }

    .img-card { position: relative; border-radius: 10px; overflow: hidden; }
    .badge {
        display: inline-block;
        padding: 0.15rem 0.55rem;
        border-radius: 4px;
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }
    .badge-unsplash { background:#111; color:#fff; }
    .badge-pexels   { background:#05A081; color:#fff; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Section 1: Pinterest Queries ───────────────────────────────────────────────
st.header("Pinterest Search Queries")

if find_btn:
    if not space or not mood:
        st.warning("Please fill in **Space** and **Mood** before searching.")
    else:
        prompt = (
            f"Generate 5 targeted Pinterest search queries for a designer finding Photoshop render references. "
            f"Brief — Space: {space}, Style: {style}, Mood: {mood}, Background: {background}. "
            f"Use designer vocabulary. Return numbered list only."
        )
        with st.spinner("Generating search queries..."):
            response = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
        raw = response.content[0].text.strip()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]

        buttons_html = ""
        for line in lines:
            query_text = line.lstrip("0123456789. ").strip('"')
            encoded = urllib.parse.quote_plus(query_text)
            url = f"https://www.pinterest.com/search/pins/?q={encoded}"
            buttons_html += (
                f'<a class="pinterest-btn" href="{url}" target="_blank" rel="noopener noreferrer">'
                f"{query_text}</a><br>"
            )

        st.markdown(buttons_html, unsafe_allow_html=True)
        st.success(f"Generated {len(lines)} Pinterest queries — click any button to open in a new tab.")
else:
    st.info("Fill in the brief on the left and click **Find References**.")

st.divider()

# ── Section 2: Browse Reference Images ────────────────────────────────────────
st.header("Browse Reference Images")

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
        {
            "thumb": p["urls"]["small"],
            "full": p["urls"]["regular"],
            "link": p["links"]["html"],
            "author": p["user"]["name"],
            "source": "unsplash",
        }
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
        {
            "thumb": p["src"]["medium"],
            "full": p["src"]["large"],
            "link": p["url"],
            "author": p["photographer"],
            "source": "pexels",
        }
        for p in resp.json().get("photos", [])
    ]

if browse_btn:
    if not space or not mood:
        st.warning("Please fill in **Space** and **Mood** before browsing.")
    else:
        query = f"{style} {space} {mood} interior"
        unsplash_key = get_secret("UNSPLASH_ACCESS_KEY")
        pexels_key = get_secret("PEXELS_API_KEY")

        if not unsplash_key and not pexels_key:
            st.warning(
                "Add **UNSPLASH_ACCESS_KEY** and/or **PEXELS_API_KEY** to your secrets to browse images. "
                "Get free keys at unsplash.com/developers and pexels.com/api."
            )
        else:
            with st.spinner("Fetching images from Unsplash & Pexels..."):
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
                            f'<a href="{img["link"]}" target="_blank" style="font-size:0.8rem;">'
                            f'{img["author"]}</a>',
                            unsafe_allow_html=True,
                        )
                st.success(f"Showing {len(images)} images for '{query}'")
else:
    st.info("Click **Browse Images** in the sidebar to pull real photos from Unsplash & Pexels.")

st.divider()

# ── Section 3: Filter Images ───────────────────────────────────────────────────
st.header("Filter Images")
st.markdown("Paste image URLs below (one per line) to check how render-ready they are.")

url_input = st.text_area(
    "Image URLs",
    height=160,
    placeholder="https://i.pinimg.com/...\nhttps://i.pinimg.com/...",
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
        with st.spinner("Checking render-readiness..."):
            response = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
        result = response.content[0].text.strip()
        st.markdown(result)

        # ── Parse table → CSV download ─────────────────────────────────────
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
            csv_bytes = buf.getvalue().encode()

            col1, col2 = st.columns([3, 1])
            with col2:
                st.download_button(
                    label="Download CSV",
                    data=csv_bytes,
                    file_name="render_references.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        passed = len(rows)
        total = len(urls)
        if passed:
            st.success(
                f"{passed} of {total} image{'s' if total != 1 else ''} scored 6 or above — ready to download."
            )
        else:
            st.info(f"None of the {total} images scored 6 or above for this brief.")

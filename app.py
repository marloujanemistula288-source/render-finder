import streamlit as st
import anthropic
import urllib.parse
import os
import csv
import io
import re
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

api_key = st.secrets.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
client = anthropic.Anthropic(api_key=api_key)

# ── Sidebar: Brief Form ────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Brief")

    space = st.text_input("Space", placeholder="e.g. living room, bedroom, office")
    style = st.selectbox("Style", ["Dreamy", "Dark Moody", "Minimal", "Maximalist", "Realistic CGI"])
    mood = st.text_input("Mood", placeholder="e.g. warm and cozy, editorial, serene")
    background = st.selectbox("Background", ["White/Isolated", "Scene", "Any"])

    find_btn = st.button("Find References", use_container_width=True, type="primary")

# ── Button style injection ─────────────────────────────────────────────────────
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

# ── Section 2: Filter Images ───────────────────────────────────────────────────
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
            # Match pipe-delimited table rows that aren't the separator line
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

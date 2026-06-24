import re
import csv
import io
import streamlit as st
import anthropic
from utils import get_secret

def render():
    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    st.markdown("<div class='section-tag'>04 — Score</div>", unsafe_allow_html=True)
    st.header("Score Image URLs")
    st.markdown(
        "<p style='color:#5A5A6E;font-size:0.88rem;margin-top:-0.5rem;margin-bottom:1.2rem;'>"
        "Paste image URLs (one per line) — Claude rates each for render-readiness.</p>",
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("---")
        st.markdown("<div class='section-tag'>Scoring Brief</div>", unsafe_allow_html=True)
        style = st.selectbox("Style", ["Dreamy","Dark Moody","Minimal","Maximalist","Realistic CGI"])
        mood  = st.text_input("Mood", placeholder="e.g. warm and earthy")

    url_input = st.text_area(
        "URLs", height=160,
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
                f"Return a markdown table: URL | Score | Reason. Show only scores 6+.\nURLs:\n"
                + "\n".join(urls)
            )
            with st.spinner("Scoring images..."):
                resp = client.messages.create(
                    model="claude-haiku-4-5-20251001", max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )
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
                w = csv.writer(buf)
                w.writerow(["URL","Score","Reason"])
                w.writerows(rows)
                _, col2 = st.columns([3, 1])
                with col2:
                    st.download_button("Download CSV", buf.getvalue().encode(),
                                       "render_references.csv", "text/csv",
                                       use_container_width=True)

            passed, total = len(rows), len(urls)
            if passed:
                st.success(f"{passed} of {total} image{'s' if total != 1 else ''} scored 6+ — ready to download.")
            else:
                st.info(f"None of the {total} images scored 6 or above.")
    else:
        st.info("Paste image URLs above and click **Check Render-Readiness**.")

import urllib.parse
import streamlit as st
import anthropic
from utils import get_secret, search_unsplash, search_pexels, strip_with_palettes

def render():
    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    st.markdown("<div class='section-tag'>01 — Search</div>", unsafe_allow_html=True)
    st.header("AI Reference Search")
    st.markdown(
        "<p style='color:#5A5A6E;font-size:0.88rem;margin-top:-0.5rem;margin-bottom:1.2rem;'>"
        "Fill in your brief — Claude generates 5 targeted search queries with image previews.</p>",
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("---")
        st.markdown("<div class='section-tag'>Project Brief</div>", unsafe_allow_html=True)
        space      = st.text_input("Space",      placeholder="e.g. living room, courtyard")
        style      = st.selectbox("Style",       ["Dreamy","Dark Moody","Minimal","Maximalist","Realistic CGI"])
        mood       = st.text_input("Mood",       placeholder="e.g. warm and earthy, editorial")
        background = st.selectbox("Background",  ["White/Isolated","Scene","Any"])
        find_btn   = st.button("Find References", use_container_width=True, type="primary")

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
                    model="claude-haiku-4-5-20251001", max_tokens=512,
                    messages=[{"role": "user", "content": prompt}],
                )
            lines = [l.strip() for l in response.content[0].text.strip().splitlines() if l.strip()]
            has_keys = bool(get_secret("UNSPLASH_ACCESS_KEY") or get_secret("PEXELS_API_KEY"))

            for i, line in enumerate(lines, 1):
                q   = line.lstrip("0123456789. ").strip('"')
                enc = urllib.parse.quote_plus(q)
                previews = []
                if has_keys:
                    previews = search_unsplash(q, n=3)
                    if len(previews) < 3:
                        previews += search_pexels(q, n=3 - len(previews))

                strip_html = strip_with_palettes(previews) if previews else (
                    '<div class="preview-strip">' + ''.join('<div class="preview-placeholder"></div>' for _ in range(3)) + "</div>"
                    if has_keys else ""
                )

                st.markdown(f"""
                <div class="query-card"><div class="query-card-inner">
                    <div class="card-label">Query {i}</div>
                    <div class="card-query-text">{q}</div>
                    {strip_html}
                    <div class="btn-row">
                        <a class="ref-btn btn-pinterest" href="https://www.pinterest.com/search/pins/?q={enc}" target="_blank" rel="noopener">Pinterest</a>
                        <a class="ref-btn btn-behance"   href="https://www.behance.net/search/projects?search={enc}" target="_blank" rel="noopener">Behance</a>
                        <a class="ref-btn btn-google"    href="https://www.google.com/search?tbm=isch&q={enc}" target="_blank" rel="noopener">Google Images</a>
                        <a class="ref-btn btn-archinect" href="https://archinect.com/search#/?q={enc}&type=photos" target="_blank" rel="noopener">Archinect</a>
                        <a class="ref-btn btn-arena"     href="https://www.are.na/search/{enc}" target="_blank" rel="noopener">Are.na</a>
                    </div>
                </div></div>""", unsafe_allow_html=True)

            if not has_keys:
                st.info("Add **UNSPLASH_ACCESS_KEY** or **PEXELS_API_KEY** to see image previews.")
            st.success(f"{len(lines)} queries generated.")
    else:
        st.info("Fill in the sidebar brief and click **Find References**.")

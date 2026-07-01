import re
import html
import json
import urllib.parse
import streamlit as st
import anthropic
from utils import get_secret, search_unsplash, search_pexels, get_color_palette, strip_with_palettes

def render():
    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    st.markdown("<div class='section-tag'>00 — Brief</div>", unsafe_allow_html=True)
    st.header("Assignment Brief")
    st.markdown(
        "<p style='color:#5A5A6E;font-size:0.88rem;margin-top:-0.5rem;margin-bottom:1.2rem;'>"
        "Paste your project brief — Claude extracts themes and finds reference images.</p>",
        unsafe_allow_html=True,
    )

    brief_text = st.text_area(
        "Brief", height=160,
        placeholder=(
            "e.g. Design a residential living space for a young professional couple in Singapore. "
            "The aesthetic should feel warm yet contemporary, drawing from Japanese minimalism "
            "and tropical materials. The space must balance openness with intimacy, using "
            "natural light and organic textures..."
        ),
        label_visibility="collapsed",
    )
    parse_btn = st.button("Parse Brief & Find Images", type="primary")

    if parse_btn:
        if not brief_text.strip():
            st.warning("Paste your assignment brief first.")
        else:
            with st.spinner("Reading your brief..."):
                resp = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=512,
                    messages=[{"role": "user", "content": (
                        "You are helping a design student find Photoshop render references. "
                        "Parse this assignment brief and extract key information.\n\n"
                        f"Brief:\n{brief_text}\n\n"
                        "Return a JSON object with exactly these fields:\n"
                        '{"project_name":"short name","space":"primary space type",'
                        '"style":"visual style","mood":"mood/atmosphere",'
                        '"themes":["theme1","theme2","theme3"],'
                        '"queries":["query1","query2","query3","query4","query5"]}\n'
                        "Return valid JSON only, no other text."
                    )}],
                )
            try:
                raw = re.sub(r"^```(?:json)?|```$", "", resp.content[0].text.strip(), flags=re.MULTILINE).strip()
                parsed = json.loads(raw)
            except Exception:
                st.error("Couldn't parse the brief — try simplifying it.")
                return

            chips = ""
            if parsed.get("space"):
                chips += f'<div class="brief-chip"><span class="brief-chip-label">Space</span>{html.escape(parsed["space"])}</div>'
            if parsed.get("style"):
                chips += f'<div class="brief-chip"><span class="brief-chip-label">Style</span>{html.escape(parsed["style"])}</div>'
            if parsed.get("mood"):
                chips += f'<div class="brief-chip"><span class="brief-chip-label">Mood</span>{html.escape(parsed["mood"])}</div>'
            for t in (parsed.get("themes") or []):
                chips += f'<div class="brief-chip">{html.escape(str(t))}</div>'

            st.markdown(f"""
            <div class="glass-card">
                <div style="font-size:0.58rem;color:#1533E8;font-weight:700;letter-spacing:0.2em;
                            text-transform:uppercase;font-family:'Space Mono',monospace;margin-bottom:0.5rem;">
                    Extracted from brief</div>
                <div style="font-size:1rem;font-weight:600;color:#0C0C12;margin-bottom:0.6rem;">
                    {html.escape(parsed.get("project_name",""))}</div>
                <div style="display:flex;flex-wrap:wrap;gap:0.4rem;">{chips}</div>
            </div>
            """, unsafe_allow_html=True)

            has_keys = bool(get_secret("UNSPLASH_ACCESS_KEY") or get_secret("PEXELS_API_KEY"))

            for i, q in enumerate(parsed.get("queries", []), 1):
                enc = urllib.parse.quote_plus(q)
                previews = []
                if has_keys:
                    previews = search_unsplash(q, n=3)
                    if len(previews) < 3:
                        previews += search_pexels(q, n=3 - len(previews))

                if previews:
                    strip_html = strip_with_palettes(previews)
                elif has_keys:
                    strip_html = '<div class="preview-strip">' + ''.join('<div class="preview-placeholder"></div>' for _ in range(3)) + "</div>"
                else:
                    strip_html = ""

                st.markdown(f"""
                <div class="query-card"><div class="query-card-inner">
                    <div class="card-label">Query {i}</div>
                    <div class="card-query-text">{html.escape(q)}</div>
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
            st.success(f"{len(parsed.get('queries', []))} queries extracted from brief.")
    else:
        st.info("Paste your assignment brief above and click **Parse Brief & Find Images**.")

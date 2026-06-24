import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Render Finder", layout="wide", initial_sidebar_state="expanded")

from utils import SHARED_CSS, PAGES, sidebar_nav

if "page" not in st.session_state:
    st.session_state.page = "home"

st.markdown(SHARED_CSS, unsafe_allow_html=True)
sidebar_nav(st.session_state.page)

# ── Route to page ──────────────────────────────────────────────────────────────
page = st.session_state.page

if page == "home":

    # Hero (left) + Bubble nav (right)
    left, right = st.columns([55, 45])

    with left:
        st.markdown("""
        <div style="padding: 3rem 0 2.5rem;">
            <div style="display:inline-flex;align-items:center;gap:0.5rem;
                        background:rgba(255,255,255,0.55);border:1px solid rgba(255,255,255,0.78);
                        border-radius:50px;padding:0.32rem 1rem;font-size:0.62rem;font-weight:700;
                        letter-spacing:0.15em;text-transform:uppercase;color:#1533E8;
                        font-family:'Space Mono',monospace;backdrop-filter:blur(8px);
                        margin-bottom:1.4rem;">
                <span style="width:6px;height:6px;border-radius:50%;background:#1533E8;
                             display:inline-block;flex-shrink:0;"></span>
                AI-Powered Image Curation
            </div>
            <div style="font-size:3.2rem;font-weight:600;color:#0C0C12;letter-spacing:-0.04em;
                        line-height:1.06;margin-bottom:1rem;font-family:'Space Grotesk',sans-serif;">
                Find the right<br>references,<br>
                <em style="font-style:italic;font-weight:300;color:#1533E8;">every time.</em>
            </div>
            <div style="font-size:0.95rem;color:#5A5A6E;line-height:1.65;max-width:400px;
                        margin-bottom:2rem;">
                Generate targeted search queries for your Photoshop renders —
                curated by AI for architecture and interior design.
            </div>
        </div>
        """, unsafe_allow_html=True)

    with right:
        st.markdown("""
        <div style="padding:3rem 0 1rem;">
            <div style="font-size:0.6rem;letter-spacing:0.2em;text-transform:uppercase;
                        color:rgba(255,255,255,0.6);font-weight:700;margin-bottom:1.2rem;
                        font-family:'Space Mono',monospace;">Where would you like to start?</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="home-bubble-nav">', unsafe_allow_html=True)
        for key, label, description in PAGES:
            if st.button(label, key=f"home_{key}", use_container_width=True):
                st.session_state.page = key
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.divider()

    # Feature overview cards
    st.markdown("""
    <div style="font-size:0.6rem;letter-spacing:0.2em;text-transform:uppercase;
                color:#1533E8;font-weight:700;font-family:'Space Mono',monospace;
                margin-bottom:0.4rem;">What's inside</div>
    """, unsafe_allow_html=True)
    st.header("Features")

    c1, c2, c3 = st.columns(3)
    cards = [
        ("Assignment Brief",   "Paste any project brief — Claude reads it and extracts space, style, mood, and themes. Instantly generates 5 targeted queries with image previews."),
        ("AI Reference Search","Give a quick brief via the sidebar. Claude generates precise search vocabulary a designer would use, with platform links and image previews per query."),
        ("Filter & Browse",    "No prompt needed. Pick tags for space type, style, mood, and lighting — the app builds the query and pulls matching photos instantly."),
        ("Browse Images",      "Direct photo search using your sidebar brief. Pulls images from Unsplash and Pexels with colour palette swatches on every result."),
        ("Score Image URLs",   "Found images elsewhere? Paste URLs and Claude rates each one 1–10 for render-readiness based on your brief. Export the shortlist as CSV."),
        ("Colour Palettes",    "Every image shown in the app displays its dominant colour palette as swatches — great for mood-boarding and material selection."),
    ]
    for i, (title, desc) in enumerate(cards):
        col = [c1, c2, c3][i % 3]
        with col:
            st.markdown(f"""
            <div class="glass-card">
                <div style="font-size:0.58rem;color:#1533E8;font-weight:700;letter-spacing:0.2em;
                            text-transform:uppercase;font-family:'Space Mono',monospace;
                            margin-bottom:0.5rem;">{str(i+1).zfill(2)}</div>
                <div style="font-size:1rem;font-weight:600;color:#0C0C12;
                            margin-bottom:0.5rem;letter-spacing:-0.02em;">{title}</div>
                <div style="font-size:0.82rem;color:#5A5A6E;line-height:1.6;">{desc}</div>
            </div>
            """, unsafe_allow_html=True)

else:
    # Route to inner pages
    if page == "brief":
        import pages.brief as p
    elif page == "search":
        import pages.search as p
    elif page == "filter":
        import pages.filter as p
    elif page == "browse":
        import pages.browse as p
    elif page == "score":
        import pages.score as p
    p.render()

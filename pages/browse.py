import streamlit as st
from utils import get_secret, search_unsplash, search_pexels, image_card_html

def render():
    st.markdown("<div class='section-tag'>03 — Browse</div>", unsafe_allow_html=True)
    st.header("Browse Reference Images")
    st.markdown(
        "<p style='color:#5A5A6E;font-size:0.88rem;margin-top:-0.5rem;margin-bottom:1.2rem;'>"
        "Pull photos directly from Unsplash & Pexels using your brief.</p>",
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("---")
        st.markdown("<div class='section-tag'>Project Brief</div>", unsafe_allow_html=True)
        space  = st.text_input("Space",  placeholder="e.g. living room, courtyard")
        style  = st.selectbox("Style",  ["Dreamy","Dark Moody","Minimal","Maximalist","Realistic CGI"])
        mood   = st.text_input("Mood",  placeholder="e.g. warm and earthy, editorial")
        browse_btn = st.button("Browse Images", use_container_width=True, type="primary")

    if browse_btn:
        if not space or not mood:
            st.warning("Please fill in **Space** and **Mood**.")
        elif not get_secret("UNSPLASH_ACCESS_KEY") and not get_secret("PEXELS_API_KEY"):
            st.warning("Add **UNSPLASH_ACCESS_KEY** and/or **PEXELS_API_KEY** to your secrets.")
        else:
            q = f"{style} {space} {mood} interior architecture"
            with st.spinner("Fetching images..."):
                images = search_unsplash(q, n=9) + search_pexels(q, n=9)
            if not images:
                st.info("No images found — try adjusting the brief.")
            else:
                cols = st.columns(3)
                for i, img in enumerate(images):
                    with cols[i % 3]:
                        st.markdown(image_card_html(img["thumb"], img["link"], img["author"], img["source"]),
                                    unsafe_allow_html=True)
                st.success(f"Showing {len(images)} images for '{q}'")
    else:
        st.info("Fill in the sidebar brief and click **Browse Images**.")

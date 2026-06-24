import streamlit as st
from utils import get_secret, search_unsplash, search_pexels, image_card_html

def render():
    st.markdown("<div class='section-tag'>02 — Filter</div>", unsafe_allow_html=True)
    st.header("Filter & Browse")
    st.markdown(
        "<p style='color:#5A5A6E;font-size:0.88rem;margin-top:-0.5rem;margin-bottom:1.2rem;'>"
        "Select tags to browse images — no prompts needed.</p>",
        unsafe_allow_html=True,
    )

    fc1, fc2 = st.columns(2)
    with fc1:
        filter_spaces = st.pills("Space type",
            ["Living Room","Bedroom","Kitchen","Office","Courtyard",
             "Rooftop","Restaurant","Hotel Lobby","Retail"],
            selection_mode="multi", key="filter_spaces")
        filter_styles = st.pills("Style",
            ["Dreamy","Dark Moody","Minimal","Maximalist","Rustic",
             "Industrial","Scandinavian","Japanese","Mediterranean"],
            selection_mode="multi", key="filter_styles")
    with fc2:
        filter_moods = st.pills("Mood",
            ["Warm & Earthy","Cool & Fresh","Dramatic","Serene",
             "Editorial","Cozy","Luxurious","Raw & Textured"],
            selection_mode="multi", key="filter_moods")
        filter_light = st.pills("Lighting",
            ["Natural Light","Golden Hour","Moody Low Light","Overcast","Artificial"],
            selection_mode="multi", key="filter_light")

    if st.button("Browse Filtered Images", type="primary", key="filter_browse"):
        all_tags = (list(filter_spaces or []) + list(filter_styles or []) +
                    list(filter_moods or []) + list(filter_light or []))
        if not all_tags:
            st.warning("Select at least one tag.")
        elif not get_secret("UNSPLASH_ACCESS_KEY") and not get_secret("PEXELS_API_KEY"):
            st.warning("Add **UNSPLASH_ACCESS_KEY** and/or **PEXELS_API_KEY** to your secrets.")
        else:
            q = " ".join(all_tags) + " interior architecture"
            with st.spinner("Fetching images..."):
                images = search_unsplash(q, n=9) + search_pexels(q, n=9)
            if not images:
                st.info("No images found — try different tags.")
            else:
                cols = st.columns(3)
                for i, img in enumerate(images):
                    with cols[i % 3]:
                        st.markdown(image_card_html(img["thumb"], img["link"], img["author"], img["source"]),
                                    unsafe_allow_html=True)
                st.success(f"Showing {len(images)} images for: {', '.join(all_tags)}")
    else:
        st.info("Select filter tags above and click **Browse Filtered Images**.")

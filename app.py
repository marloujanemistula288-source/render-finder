import streamlit as st
import anthropic
import urllib.parse
import os, csv, io, re, requests, base64, json, html, ipaddress, socket
from datetime import datetime
from email.utils import parseaddr
from urllib.parse import urlparse
from PIL import Image
from colorthief import ColorThief
from dotenv import load_dotenv
from collections import Counter
from streamlit_javascript import st_javascript

load_dotenv()

def _is_safe_url(url):
    """Block SSRF to private/internal IP ranges before fetching user-supplied URLs."""
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname
        if not host:
            return False
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            ip = ipaddress.ip_address(socket.gethostbyname(host))
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)
    except Exception:
        return False

def _is_valid_email(addr):
    """Reject addresses that contain header-injection characters."""
    _, parsed = parseaddr(addr)
    return bool(parsed) and "@" in parsed and "\n" not in addr and "\r" not in addr

_LS_KEY = "rf_sessions"  # localStorage key — private per browser/user

def _ls_write(sessions):
    """Stage sessions for localStorage write; bump version so st_javascript re-executes."""
    st.session_state["_ls_pending_write"] = sessions
    st.session_state["_ls_write_ver"] = st.session_state.get("_ls_write_ver", 0) + 1

def _build_session_record(name):
    return {
        "name": name,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "brief_space": st.session_state.get("brief_space", ""),
        "brief_style": st.session_state.get("brief_style", "Dreamy"),
        "brief_mood": st.session_state.get("brief_mood", ""),
        "brief_background": st.session_state.get("brief_background", "White/Isolated"),
        "selected_images": st.session_state.get("selected_images", []),
        "saved_palettes": st.session_state.get("saved_palettes", []),
        "generated_queries": st.session_state.get("generated_queries", []),
    }

def _restore_session(s):
    # Stage under a temp key; the pre-widget block at top applies it after rerun.
    st.session_state["_session_restore"] = s

st.set_page_config(page_title="Visionpull", layout="wide", initial_sidebar_state="collapsed")

# ── Session state ──────────────────────────────────────────────────────────────
_defaults = {
    "history": [], "selected_images": [], "comparison_images": [],
    "browse_results": [], "filter_results": [], "generated_queries": [],
    "saved_palettes": [],
    "brief_space": "", "brief_style": "Dreamy",
    "brief_mood": "", "brief_background": "White/Isolated",
    "template_selector": "— Choose a template —",
    "page": "Brief",
    "main_nav": "Home",
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

PAGES = ["Brief", "Search", "Browse", "Palette", "Board", "Prompt"]
PAGE_TO_NAV = {"Brief":"Home","Search":"Search","Browse":"Browse","Palette":"Palette","Board":"Board","Prompt":"Prompt"}
NAV_TO_PAGE = {"Home":"Brief","Search":"Search","Browse":"Browse","Palette":"Palette","Board":"Board","Prompt":"Prompt"}
STYLE_OPTIONS = ["Dreamy", "Dark Moody", "Minimal", "Maximalist", "Realistic CGI"]
BG_OPTIONS    = ["White/Isolated", "Scene", "Any"]

# Streamlit 1.58 forbids setting widget-bound session keys after the widget renders.
# The extract-brief flow stores results here, reruns, then this block pre-populates
# the keys before any widget is instantiated.
if "_brief_extracted" in st.session_state:
    _ext = st.session_state.pop("_brief_extracted")
    if _ext.get("space"):
        st.session_state["brief_space"] = _ext["space"]
    if _ext.get("style") and _ext["style"] in STYLE_OPTIONS:
        st.session_state["brief_style"] = _ext["style"]
    if _ext.get("mood"):
        st.session_state["brief_mood"] = _ext["mood"]
    if _ext.get("background") and _ext["background"] in BG_OPTIONS:
        st.session_state["brief_background"] = _ext["background"]

if "_session_restore" in st.session_state:
    _sr = st.session_state.pop("_session_restore")
    st.session_state["brief_space"]       = _sr.get("brief_space", "")
    st.session_state["brief_style"]       = _sr.get("brief_style", "Dreamy")
    st.session_state["brief_mood"]        = _sr.get("brief_mood", "")
    st.session_state["brief_background"]  = _sr.get("brief_background", "White/Isolated")
    st.session_state["selected_images"]   = _sr.get("selected_images", [])
    st.session_state["saved_palettes"]    = _sr.get("saved_palettes", [])
    st.session_state["generated_queries"] = _sr.get("generated_queries", [])
FILTER_SPACES = ["Living Room","Bedroom","Kitchen","Office","Courtyard","Exterior","Dining Room","Studio","Bathroom"]
FILTER_STYLES = ["Dreamy","Minimal","Dark Moody","Maximalist","Brutalist","Japandi","Bohemian","Industrial","Coastal"]
FILTER_MOODS  = ["Warm","Cool","Cozy","Editorial","Raw","Airy","Dramatic","Serene","Earthy","Luxe"]
FILTER_LIGHTS = ["Natural Light","Golden Hour","Night Scene","Overcast","Candlelight","Diffused","Artificial"]
TEMPLATES = {
    "— Choose a template —": None,
    "Warm Scandinavian Interior": {"space":"living room","style":"Minimal","mood":"warm, hygge, soft diffused light","background":"Scene"},
    "Dark Industrial Loft":       {"space":"loft apartment","style":"Dark Moody","mood":"raw, editorial, exposed concrete","background":"Scene"},
    "Dreamy Exterior Courtyard":  {"space":"outdoor courtyard","style":"Dreamy","mood":"hazy, atmospheric, lush greenery","background":"Scene"},
    "Maximalist Living Room":     {"space":"living room","style":"Maximalist","mood":"layered, eclectic, rich jewel tones","background":"Scene"},
    "Clean White Kitchen":        {"space":"kitchen","style":"Minimal","mood":"bright, airy, clinical precision","background":"White/Isolated"},
    "Warm Terracotta Bedroom":    {"space":"bedroom","style":"Dreamy","mood":"earthy, cozy, Mediterranean warmth","background":"Scene"},
    "Brutalist Office Lobby":     {"space":"office lobby","style":"Realistic CGI","mood":"monumental, raw concrete, dramatic","background":"Scene"},
}
STOP_WORDS = {"a","an","the","and","or","for","with","in","on","at","to","of","from","by","as","is","are","that","this","be","was","were","it","its","interior","design","photography","photo","image","render","photoshop","reference","style","space","mood","background","high","end","modern","contemporary","architectural","architecture"}

def get_secret(k):
    try:
        return st.secrets.get(k) or os.getenv(k)
    except Exception:
        return os.getenv(k)

client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

# ── Navigation (session state only — never HTML links) ─────────────────────────
# Apply any pending nav override BEFORE the segmented_control widget renders
if "_nav_override" in st.session_state:
    st.session_state.main_nav = st.session_state.pop("_nav_override")

# Sync page ↔ main_nav (segmented control uses main_nav key)
if "main_nav" in st.session_state and st.session_state.main_nav:
    st.session_state.page = NAV_TO_PAGE.get(st.session_state.main_nav, st.session_state.page)
page = st.session_state.page

def go_to(p):
    # Snapshot brief values now (before rerun can reset widget-tied keys)
    st.session_state._brief_snapshot = {
        "space": st.session_state.get("brief_space", ""),
        "style": st.session_state.get("brief_style", "Dreamy"),
        "mood": st.session_state.get("brief_mood", ""),
        "background": st.session_state.get("brief_background", "White/Isolated"),
    }
    st.session_state.page = p
    st.session_state._nav_override = PAGE_TO_NAV.get(p, "Home")
    st.rerun()

# ── Helpers ────────────────────────────────────────────────────────────────────
def search_unsplash(query, n=9):
    key = get_secret("UNSPLASH_ACCESS_KEY")
    if not key: return []
    try:
        r = requests.get("https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": n, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {key}"}, timeout=10)
        if r.status_code != 200: return []
        return [{"thumb": p["urls"]["small"], "full": p["urls"]["regular"],
                 "link": p["links"]["html"], "author": p["user"]["name"], "source": "unsplash"}
                for p in r.json().get("results", [])]
    except: return []

def search_pexels(query, n=9):
    key = get_secret("PEXELS_API_KEY")
    if not key: return []
    try:
        r = requests.get("https://api.pexels.com/v1/search",
            params={"query": query, "per_page": n, "orientation": "landscape"},
            headers={"Authorization": key}, timeout=10)
        if r.status_code != 200: return []
        return [{"thumb": p["src"]["medium"], "full": p["src"]["large"],
                 "link": p["url"], "author": p["photographer"], "source": "pexels"}
                for p in r.json().get("photos", [])]
    except: return []

def extract_palette(url, n=6):
    if not _is_safe_url(url):
        return []
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        ct = ColorThief(io.BytesIO(r.content))
        return [f"#{rv:02x}{g:02x}{b:02x}" for rv, g, b in ct.get_palette(color_count=n, quality=1)]
    except: return []

def create_collage_moodboard(images, palette_colors=None):
    from PIL import ImageDraw, ImageFilter
    W, H = 1600, 2000
    BG = (248, 244, 238)
    canvas = Image.new("RGB", (W, H), BG)

    # Staggered editorial placements: (x, y, w, h)
    # Designed for up to 9 images — each cluster of 3 fills a horizontal band
    _all_placements = [
        (55,  50,  700, 500),   # 0 hero top-left
        (710, 120, 460, 340),   # 1 med top-right
        (940, 420, 580, 420),   # 2 large right-mid
        (60,  540, 480, 360),   # 3 med mid-left
        (520, 540, 360, 260),   # 4 small mid-centre
        (60,  900, 700, 500),   # 5 hero bottom-left
        (730, 860, 380, 280),   # 6 small bottom-centre
        (700, 1130, 560, 400),  # 7 large bottom-right
        (60,  1390, 440, 320),  # 8 accent bottom
    ]

    loaded = []
    for d in images[:9]:
        try:
            r = requests.get(d.get("full", d["thumb"]), timeout=12)
            loaded.append(Image.open(io.BytesIO(r.content)).convert("RGB"))
        except:
            loaded.append(None)

    shadow_layer = Image.new("RGB", (W, H), BG)
    shadow_draw  = ImageDraw.Draw(shadow_layer)

    for i, img in enumerate(loaded):
        if img is None or i >= len(_all_placements): continue
        x, y, w, h = _all_placements[i]
        # Soft shadow rectangle
        shadow_draw.rectangle([x+8, y+8, x+w+8, y+h+8], fill=(200, 196, 190))
    # Blur the shadow layer and composite onto canvas
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(12))
    canvas = Image.blend(canvas, shadow_layer, alpha=0.45)

    for i, img in enumerate(loaded):
        if img is None or i >= len(_all_placements): continue
        x, y, w, h = _all_placements[i]
        canvas.paste(img.resize((w, h), Image.LANCZOS), (x, y))

    # Palette swatches — right column, stacked bars (like editorial reference)
    if palette_colors:
        colors = [c for c in palette_colors if c and len(c) == 7]
        if colors:
            # Scale bar size so all colours fit without overlapping images
            sw_h = max(28, min(52, (H - 120) // len(colors) - 10))
            sw_gap = max(6, sw_h // 5)
            total_pal_h = len(colors) * (sw_h + sw_gap)
            # Extend canvas if palette strip would push below bottom
            needed_h = total_pal_h + 120
            if needed_h > H:
                H = needed_h + 40
                new_canvas = Image.new("RGB", (W, H), BG)
                new_canvas.paste(canvas, (0, 0))
                canvas = new_canvas
            draw = ImageDraw.Draw(canvas)
            sw_w_base = 220
            sw_x = W - sw_w_base - 60
            sw_y = H - total_pal_h - 80
            for idx, hex_c in enumerate(colors):
                try:
                    rv = int(hex_c[1:3], 16); gv = int(hex_c[3:5], 16); bv = int(hex_c[5:7], 16)
                    bar_w = sw_w_base - (idx % 3) * 30
                    draw.rectangle([sw_x, sw_y, sw_x + bar_w, sw_y + sw_h], fill=(rv, gv, bv))
                    sw_y += sw_h + sw_gap
                except: pass

    buf = io.BytesIO(); canvas.save(buf, "PNG"); return buf.getvalue()


def create_moodboard(images, cols=3, tw=400, th=280, gap=10, palette_colors=None):
    imgs = []
    for d in images:
        try:
            r = requests.get(d.get("full", d["thumb"]), timeout=10)
            img = Image.open(io.BytesIO(r.content)).convert("RGB").resize((tw, th), Image.LANCZOS)
            imgs.append(img)
        except: pass
    if not imgs: return None
    rows = (len(imgs) + cols - 1) // cols
    grid_w = cols*(tw+gap)+gap
    grid_h = rows*(th+gap)+gap
    # Reserve space for palette strip if needed
    colors = [c for c in (palette_colors or []) if c and len(c) == 7]
    sw_h = 60; sw_gap = gap
    # Fit all swatches into rows of up to 12 per row
    swatch_cols = 12
    pal_rows = ((len(colors) + swatch_cols - 1) // swatch_cols) if colors else 0
    pal_h = pal_rows * (sw_h + sw_gap) if colors else 0
    board = Image.new("RGB", (grid_w, grid_h + pal_h), (240, 243, 255))
    for i, img in enumerate(imgs):
        r2, c = divmod(i, cols)
        board.paste(img, (c*(tw+gap)+gap, r2*(th+gap)+gap))
    # Multi-row palette strip below grid
    if colors:
        from PIL import ImageDraw as _ID
        draw = _ID.Draw(board)
        sw_w = max(40, (grid_w - gap*(swatch_cols+1)) // swatch_cols)
        for idx, hex_c in enumerate(colors):
            try:
                row_i, col_i = divmod(idx, swatch_cols)
                sw_x = gap + col_i * (sw_w + gap)
                sw_y = grid_h + sw_gap + row_i * (sw_h + sw_gap)
                rv = int(hex_c[1:3],16); gv = int(hex_c[3:5],16); bv = int(hex_c[5:7],16)
                draw.rectangle([sw_x, sw_y, sw_x+sw_w, sw_y+sw_h], fill=(rv,gv,bv))
            except: pass
    buf = io.BytesIO(); board.save(buf, "PNG"); return buf.getvalue()

def extract_keywords(texts):
    words = [w for t in texts for w in re.findall(r'\b[a-zA-Z]{4,}\b', t.lower())]
    return [w for w, _ in Counter(w for w in words if w not in STOP_WORDS).most_common(14)]

def extract_brief_from_file(file_bytes, mime_type):
    """Use Claude Vision to extract brief info from an uploaded PDF/image."""
    b64 = base64.standard_b64encode(file_bytes).decode()
    prompt = (
        "You are analysing a design assignment brief or mood-board image. "
        "Extract the following and return ONLY a JSON object with these exact keys: "
        '{"space": "...", "style": "...", "mood": "...", "background": "..."}. '
        "space = the room/space type (e.g. living room, bedroom, office). "
        "style = the visual style (choose one: Dreamy, Dark Moody, Minimal, Maximalist, Realistic CGI). "
        "mood = 3-5 descriptive mood words (e.g. warm, earthy, cozy). "
        "background = White/Isolated or Scene. "
        "If unsure, make a reasonable guess. Return ONLY the JSON, no explanation."
    )
    try:
        if mime_type == "application/pdf":
            content_block = {"type":"document","source":{"type":"base64","media_type":"application/pdf","data":b64}}
        else:
            media = mime_type if mime_type in ("image/png","image/jpeg","image/webp","image/gif") else "image/jpeg"
            content_block = {"type":"image","source":{"type":"base64","media_type":media,"data":b64}}
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=256,
            messages=[{"role":"user","content":[
                content_block,
                {"type":"text","text":prompt}
            ]}]
        )
        import json
        text = resp.content[0].text.strip()
        start = text.find("{"); end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except:
        return None

def extract_palette_from_bytes(file_bytes, n=6):
    try:
        # Resize large images before extraction to prevent memory crash
        img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        max_dim = 800
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        ct = ColorThief(buf)
        return [f"#{rv:02x}{g:02x}{b:02x}" for rv, g, b in ct.get_palette(color_count=n, quality=1)]
    except:
        return []

def fetch_pinterest_image(url):
    """Extract image from a Pinterest pin URL, pinimg.com CDN URL, or any direct image URL."""
    url = url.strip()
    if not _is_safe_url(url):
        return None
    if re.search(r'\.(jpg|jpeg|png|webp)(\?[^#]*)?$', url, re.I) or 'pinimg.com' in url:
        return {"thumb": url, "full": url, "link": url, "author": "Pinterest", "source": "pinterest"}
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        r = requests.get(url, timeout=12, headers=headers)
        match = (re.search(r'property="og:image"\s+content="([^"]+)"', r.text) or
                 re.search(r'content="([^"]+)"\s+property="og:image"', r.text))
        if match:
            img = match.group(1)
            return {"thumb": img, "full": img, "link": url, "author": "Pinterest", "source": "pinterest"}
    except:
        pass
    return None

def send_board_email(to_email, images):
    smtp_host = get_secret("SMTP_HOST")
    smtp_user = get_secret("SMTP_USER")
    smtp_pass = get_secret("SMTP_PASS")
    smtp_from = get_secret("SMTP_FROM") or smtp_user
    if not (smtp_host and smtp_user and smtp_pass):
        return False, "no_smtp"
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    img_html = "".join(
        f'<a href="{img["link"]}" style="display:inline-block;margin:6px">'
        f'<img src="{img["thumb"]}" width="180" height="120" '
        f'style="object-fit:cover;border-radius:10px;display:block"></a>'
        for img in images
    )
    body = (
        f"<div style='font-family:sans-serif;max-width:640px;margin:auto'>"
        f"<h2 style='color:#0D1F8A'>Your Visionpull Board</h2>"
        f"<p style='color:#3D5299'>{len(images)} reference image(s) curated for you.</p>"
        f"<div style='display:flex;flex-wrap:wrap;gap:8px;margin-top:16px'>{img_html}</div>"
        f"<p style='color:#8892C0;font-size:12px;margin-top:24px'>Sent from Visionpull</p>"
        f"</div>"
    )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your Visionpull Board"
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg.attach(MIMEText(body, "html"))
    try:
        port = int(get_secret("SMTP_PORT") or 465)
        if port == 587:
            with smtplib.SMTP(smtp_host, port) as s:
                s.starttls(); s.login(smtp_user, smtp_pass)
                s.sendmail(smtp_from, [to_email], msg.as_string())
        else:
            with smtplib.SMTP_SSL(smtp_host, port) as s:
                s.login(smtp_user, smtp_pass)
                s.sendmail(smtp_from, [to_email], msg.as_string())
        return True, "sent"
    except Exception as e:
        return False, str(e)

def on_template_change():
    c = st.session_state.template_selector
    if c != "— Choose a template —" and TEMPLATES.get(c):
        t = TEMPLATES[c]
        st.session_state.brief_space      = t["space"]
        st.session_state.brief_style      = t["style"]
        st.session_state.brief_mood       = t["mood"]
        st.session_state.brief_background = t["background"]

def render_image_grid(images, key_prefix="img"):
    cols3 = st.columns(3)
    for i, img in enumerate(images):
        bc = "badge-unsplash" if img["source"] == "unsplash" else "badge-pexels"
        bl = "Unsplash"       if img["source"] == "unsplash" else "Pexels"
        on_board   = any(x["thumb"] == img["thumb"] for x in st.session_state.selected_images)
        on_compare = any(x["thumb"] == img["thumb"] for x in st.session_state.comparison_images)
        with cols3[i % 3]:
            st.image(img["thumb"], width="stretch")
            st.markdown(f'<span class="badge {bc}">{bl}</span> '
                        f'<a href="{img["link"]}" target="_blank" '
                        f'style="font-size:0.74rem;color:#3D5299;text-decoration:none;">'
                        f'{img["author"]}</a>', unsafe_allow_html=True)
            ca, cb = st.columns(2)
            with ca:
                if st.button("✓ Board" if on_board else "+ Board",
                             key=f"{key_prefix}_b_{i}", use_container_width=True):
                    if not on_board: st.session_state.selected_images.append(img)
                    else: st.session_state.selected_images = [x for x in st.session_state.selected_images if x["thumb"] != img["thumb"]]
                    st.rerun()
            with cb:
                if st.button("✓ Cmp" if on_compare else "Compare",
                             key=f"{key_prefix}_c_{i}", use_container_width=True):
                    if on_compare: st.session_state.comparison_images = [x for x in st.session_state.comparison_images if x["thumb"] != img["thumb"]]
                    elif len(st.session_state.comparison_images) < 2: st.session_state.comparison_images.append(img)
                    else: st.session_state.comparison_images = [st.session_state.comparison_images[1], img]
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,300;1,400&display=swap');
*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

header[data-testid="stHeader"], [data-testid="stSidebar"],
[data-testid="collapsedControl"], footer, #MainMenu { display: none !important; }

/* App background */
.stApp { background-color: #F4F5FA; min-height: 100vh; }

/* Blue blob — narrowed so its left edge clears the nav items (~x>56% of vp).
   The native header (z=10, white bg) covers the topbar row. Only the far-right
   column (BRIEF button) sits on the blue, matching the reference CONNECT style. */
.zn-blob {
    position: fixed; top: -12%; right: -10%;
    width: 54vw; height: 120vh;
    background:
        radial-gradient(ellipse 55% 62% at 60% 18%, #0B1DCC 0%, #1325DD 16%, transparent 60%),
        radial-gradient(ellipse 62% 78% at 66% 54%, #0E20D8 0%, #0B1DCC 24%, transparent 70%),
        radial-gradient(ellipse 46% 52% at 74% 80%, #0916B8 0%, transparent 58%),
        radial-gradient(ellipse 88% 96% at 64% 46%, rgba(10,24,200,0.42) 0%, transparent 72%);
    border-radius: 42% 58% 50% 50% / 48% 44% 60% 52%;
    filter: blur(72px);
    pointer-events: none; z-index: 0;
}
.zn-blob::before {
    content: ''; position: absolute; inset: -5%;
    background:
        radial-gradient(ellipse 48% 40% at 30% 16%, rgba(255,255,255,0.24) 0%, transparent 58%),
        radial-gradient(ellipse 26% 22% at 74% 58%, rgba(255,255,255,0.10) 0%, transparent 52%);
    border-radius: inherit; pointer-events: none;
}
/* Grain overlay — separate fixed div so it's NOT blurred with the blob */
.zn-grain {
    position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 280 280' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.70' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
    background-size: 160px 160px; opacity: 0.30; mix-blend-mode: overlay;
    pointer-events: none; z-index: 0;
}
.zn-bottom-fade {
    position: fixed; bottom: 0; right: 0; width: 65vw; height: 28vh;
    background: radial-gradient(ellipse 80% 100% at 62% 112%, rgba(10,22,200,0.48) 0%, transparent 65%);
    filter: blur(40px);
    pointer-events: none; z-index: 0;
}

/* Main container */
.main .block-container {
    padding-top: 1.2rem !important; padding-left: 3.8rem !important;
    padding-right: 3.8rem !important; padding-bottom: 4rem !important;
    max-width: 100% !important; position: relative; z-index: 10;
}

/* ── Three-layer z-index hierarchy ─────────────────────────────────────────
   Layer 1 (z-0):  .zn-blob / .zn-grain / .zn-bottom-fade  (background)
   Layer 2 (z-10): left column  — hero text, CTA buttons, brief form
   Layer 3 (z-20): right column — badge pill, external pills, session, email
   ─────────────────────────────────────────────────────────────────────── */
[data-testid="stColumn"]:has(.zn-hero)     { position: relative; z-index: 10; }
[data-testid="stColumn"]:has(.fp-container){ position: relative; z-index: 20; }

/* Logo area */
.zn-logo-area {
    display: flex; align-items: center; gap: 9px;
    font-size: 0.82rem; font-weight: 700; letter-spacing: 0.12em;
    color: #0D1F8A; padding: 0; line-height: 56px;
    white-space: nowrap;
}

/* Topbar connect button override — always solid navy pill like Zeronode CONNECT */
[data-testid="column"]:last-child .stButton > button {
    background: #0D1F8A !important;
    color: #fff !important;
    border: none !important;
    border-radius: 50px !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    padding: 0.42rem 1.3rem !important;
    box-shadow: 0 4px 18px rgba(13,31,138,0.28) !important;
    white-space: nowrap;
}

/* ── Segmented control → plain text nav links (Zeronode style) ── */
[data-testid="stSegmentedControl"],
[data-testid="stSegmentedControl"] > div,
[data-testid="stSegmentedControl"] > div > div,
[data-testid="stSegmentedControl"] [role="group"],
[data-testid="stSegmentedControl"] [role="radiogroup"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    gap: 0px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
[data-testid="stSegmentedControl"] button {
    border-radius: 0 !important;
    background: transparent !important;
    border: none !important;
    color: #7A89BB !important;
    font-size: 0.74rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.13em !important;
    text-transform: uppercase !important;
    padding: 0.5rem 1.6rem !important;
    height: auto !important;
    min-height: 40px !important;
    box-shadow: none !important;
    margin: 0 !important;
    transition: color 0.18s !important;
}
[data-testid="stSegmentedControl"] button:hover {
    background: transparent !important;
    color: #0D1F8A !important;
    box-shadow: none !important;
}
[data-testid="stSegmentedControl"] button[aria-checked="true"],
[data-testid="stSegmentedControl"] button[data-checked="true"],
[data-testid="stSegmentedControl"] button[aria-pressed="true"],
[data-testid="stSegmentedControl"] button[aria-selected="true"] {
    background: transparent !important;
    color: #0D1F8A !important;
    font-weight: 700 !important;
    box-shadow: none !important;
    border: none !important;
}
/* Streamlit puts data-testid ON the button element itself for segmented control */
button[data-testid^="stBaseButton-segmented_control"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: #8892C0 !important;
}
button[data-testid="stBaseButton-segmented_controlActive"] {
    background: transparent !important;
    color: #0D1F8A !important;
    font-weight: 700 !important;
    border: none !important;
    box-shadow: none !important;
}

/* ── Primary / secondary CTA buttons ── */
.stButton > button[kind="primary"] {
    background: #0D1F8A !important; color: #fff !important;
    border: none !important; border-radius: 50px !important;
    font-family: 'Inter', sans-serif !important; font-weight: 600 !important;
    font-size: 0.76rem !important; letter-spacing: 0.07em !important;
    text-transform: uppercase !important; padding: 0.55rem 1.6rem !important;
    box-shadow: 0 4px 18px rgba(13,31,138,0.30) !important; transition: all 0.18s !important;
}
.stButton > button[kind="primary"]:hover {
    background: #1635CC !important;
    box-shadow: 0 6px 22px rgba(13,31,138,0.42) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"] {
    background: rgba(255,255,255,0.9) !important; color: #0D1F8A !important;
    border: 1.5px solid rgba(13,31,138,0.22) !important; border-radius: 50px !important;
    font-family: 'Inter', sans-serif !important; font-weight: 500 !important;
    font-size: 0.76rem !important; letter-spacing: 0.07em !important;
    text-transform: uppercase !important;
}
.stButton > button[kind="secondary"]:hover {
    background: rgba(13,31,138,0.06) !important; border-color: #0D1F8A !important;
}
.stDownloadButton > button {
    background: rgba(255,255,255,0.82) !important; color: #0D1F8A !important;
    border: 1.5px solid rgba(13,31,138,0.25) !important; border-radius: 50px !important;
    font-family: 'Inter', sans-serif !important; font-size: 0.76rem !important;
}

/* ── Floating pills — data-testid is ON the button itself; comes after secondary rule ── */
[data-testid="stColumn"]:has(.fp-container) button[data-testid^="stBaseButton"] {
    background: rgba(255,255,255,0.12) !important;
    backdrop-filter: blur(18px) brightness(0.40) saturate(0.75) !important;
    -webkit-backdrop-filter: blur(18px) brightness(0.40) saturate(0.75) !important;
    border: 1.5px solid rgba(255,255,255,0.50) !important;
    border-radius: 50px !important;
    color: #FFFFFF !important;
    font-size: 0.92rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em !important;
    text-transform: none !important;
    padding: 0.85rem 1.6rem !important;
    box-shadow: 0 4px 32px rgba(0,0,40,0.28), inset 0 1px 0 rgba(255,255,255,0.25) !important;
    width: 100% !important;
    transition: all 0.2s !important;
}
[data-testid="stColumn"]:has(.fp-container) button[data-testid^="stBaseButton"]:hover {
    background: rgba(255,255,255,0.22) !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 12px 44px rgba(0,0,40,0.32), inset 0 1px 0 rgba(255,255,255,0.45) !important;
}

/* ── External link pills (Pinterest / Arch Daily / Dezeen) ── */
.fp-container {
    display: flex; flex-direction: column; gap: 0.65rem;
}
.fp-pill {
    display: block; text-align: center; position: relative; z-index: 20;
    background: rgba(255, 255, 255, 0.15);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.3);
    border-radius: 50px;
    color: #FFFFFF !important;
    font-family: inherit; font-size: 0.92rem; font-weight: 500;
    letter-spacing: 0.04em; text-decoration: none;
    padding: 0.85rem 1.6rem;
    box-shadow: 0 4px 32px rgba(0,0,40,0.28), inset 0 1px 0 rgba(255,255,255,0.25);
    transition: all 0.2s; cursor: pointer;
}
.fp-pill:hover {
    background: rgba(255, 255, 255, 0.25);
    transform: translateY(-2px);
    box-shadow: 0 12px 44px rgba(0,0,40,0.32), inset 0 1px 0 rgba(255,255,255,0.45);
    color: #FFFFFF !important; text-decoration: none;
}

/* ── Inputs ── */
input, textarea,
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    background: #ffffff !important;
    border: 1.5px solid rgba(100, 120, 220, 0.3) !important;
    border-radius: 8px !important;
    color: #1a1a6e !important;
    padding: 10px 14px !important;
    font-family: 'Inter', sans-serif !important;
}
input::placeholder, textarea::placeholder,
[data-testid="stTextInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder {
    color: rgba(100, 120, 220, 0.5) !important;
    opacity: 1 !important;
}
input:focus, textarea:focus {
    border-color: rgba(100, 120, 220, 0.3) !important;
    box-shadow: 0 0 0 3px rgba(100, 120, 220, 0.08) !important;
}
[data-testid="stSelectbox"] > div > div,
[data-testid="stSelectbox"] [data-baseweb="select"] > div {
    background: #ffffff !important;
    border: 1.5px solid rgba(100, 120, 220, 0.3) !important;
    border-radius: 8px !important;
    color: #1a1a6e !important;
    position: relative !important;
}
/* Chevron arrow indicator via ::after on the outer control box */
[data-testid="stSelectbox"] [data-baseweb="select"] > div::after {
    content: '▾';
    position: absolute;
    right: 12px;
    top: 50%;
    transform: translateY(-50%);
    color: rgba(100, 120, 220, 0.6);
    font-size: 1.1rem;
    pointer-events: none;
    line-height: 1;
}
/* Inner children: no border (prevents border-left divider) */
[data-testid="stSelectbox"] [data-baseweb="select"] > div > div {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
}
/* Hide the BaseWeb icons container (35px with SVG arrow) */
[data-testid="stSelectbox"] [data-baseweb="select"] > div > div:last-child {
    display: none !important;
}
/* Neutralise the hidden combobox input that renders as a grey square */
[data-testid="stSelectbox"] input[role="combobox"] {
    -webkit-appearance: none !important;
    appearance: none !important;
    background: transparent !important;
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
    color: transparent !important;
    width: 1px !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] span {
    color: #1a1a6e !important;
}
/* ── Selectbox dropdown portal (BaseWeb popover rendered at body level) ── */
[data-baseweb="popover"],
[data-baseweb="popover"] > div,
[data-baseweb="popover"] ul {
    background: #0D1F8A !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: 8px !important;
    box-shadow: 0 8px 32px rgba(0,0,40,0.4) !important;
}
[data-baseweb="popover"] [role="option"] {
    background: transparent !important;
    color: rgba(255,255,255,0.9) !important;
}
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="popover"] [role="option"][aria-selected="true"] {
    background: rgba(255,255,255,0.1) !important;
    color: #ffffff !important;
}
/* ── File uploader drop zone ── */
[data-testid="stFileUploaderDropzone"] {
    background: rgba(20, 30, 120, 0.6) !important;
    border: 1.5px dashed rgba(255,255,255,0.35) !important;
    border-radius: 12px !important;
}
[data-testid="stFileUploaderDropzone"] span,
[data-testid="stFileUploaderDropzone"] small,
[data-testid="stFileUploaderDropzone"] p {
    color: rgba(255,255,255,0.85) !important;
}
[data-testid="stFileUploaderDropzone"] button {
    color: rgba(255,255,255,0.85) !important;
    border-color: rgba(255,255,255,0.4) !important;
    background: rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
}
label { color: #3D5299 !important; font-size: 0.8rem !important; }

/* ── Glass cards ── */
.zn-card {
    background: rgba(255,255,255,0.88);
    border: 1px solid rgba(13,31,138,0.10);
    border-radius: 24px; padding: 1.7rem 2rem;
    box-shadow: 0 4px 32px rgba(13,31,138,0.07);
}
.zn-card-label {
    font-size: 0.67rem; letter-spacing: 0.14em; text-transform: uppercase;
    color: #1635CC; font-weight: 700; margin-bottom: 1.1rem;
    font-family: 'Inter', sans-serif;
}

/* ── Hero ── */
.zn-hero { padding: 1rem 0 1.8rem; position: relative; z-index: 10; }
.zn-badge-pill {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 0.38rem 1.05rem;
    background: rgba(255,255,255,0.88);
    border: 1px solid rgba(22,53,204,0.14); border-radius: 50px;
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.11em;
    color: #0D1F8A; margin-bottom: 1.5rem; font-family: 'Inter', sans-serif;
    position: relative; z-index: 20;
}
.zn-headline {
    font-size: 3.4rem !important; font-weight: 800 !important;
    color: #0D1F8A !important; letter-spacing: -0.03em;
    line-height: 1.07 !important; margin-bottom: 1.3rem !important;
    font-family: 'Inter', sans-serif !important;
}
.zn-headline em { font-weight: 300 !important; font-style: italic; }
.zn-hero-body {
    font-size: 0.88rem; line-height: 1.72; color: #3D5299;
    max-width: 310px; margin-bottom: 2rem; font-family: 'Inter', sans-serif;
}

/* ── Saved sessions ── */
.sv-label { font-size: 0.67rem; letter-spacing: 0.14em; text-transform: uppercase;
    color: #1635CC; font-weight: 700; margin-bottom: 0.5rem; font-family: 'Inter', sans-serif; }
.sv-item { display: flex; justify-content: space-between; align-items: center;
    padding: 0.45rem 0; border-bottom: 1px solid rgba(13,31,138,0.08); }
.sv-item:last-child { border-bottom: none; }
.sv-name { font-size: 0.78rem; font-weight: 600; color: #0D1F8A; font-family: 'Inter', sans-serif;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 140px; }
.sv-time { font-size: 0.68rem; color: #8892C0; font-family: 'Inter', sans-serif; }
.sv-empty { font-size: 0.75rem; color: #8892C0; font-family: 'Inter', sans-serif; font-style: italic; }
/* Delete session ✕ button — subtle red tint */
.sv-del [data-testid="stButton"] button {
    background: rgba(220,60,60,0.08) !important;
    border-color: rgba(220,60,60,0.25) !important;
    color: #CC2222 !important;
}
.sv-del [data-testid="stButton"] button:hover {
    background: rgba(220,60,60,0.2) !important;
}

/* ── Stats grid ── */
.zn-stats-grid { display: flex; gap: 1.5rem; margin-bottom: 1rem; }
.zn-stat { text-align: center; flex: 1; }
.zn-stat-val { font-size: 1.9rem; font-weight: 700; color: #0D1F8A; font-family: 'Inter', sans-serif; line-height: 1; }
.zn-stat-lbl { font-size: 0.75rem; color: #ffffff; margin-top: 0.3rem; font-family: 'Inter', sans-serif; letter-spacing: 0.03em; }

/* ── Page header for sub-pages ── */
.zn-page-header { margin-bottom: 2rem; position: relative; z-index: 10; }
.zn-page-title {
    font-size: 2.2rem !important; font-weight: 700 !important;
    color: #0D1F8A !important; letter-spacing: -0.02em;
    margin: 0.4rem 0 0.2rem !important; font-family: 'Inter', sans-serif !important;
}
.zn-badge-small {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 0.28rem 0.85rem;
    background: rgba(255,255,255,0.7); border: 1px solid rgba(13,31,138,0.14);
    border-radius: 50px; font-size: 0.67rem; font-weight: 600;
    letter-spacing: 0.12em; color: #1635CC; font-family: 'Inter', sans-serif;
    margin-bottom: 0.6rem;
}

/* ── Query cards ── */
.qcard {
    background: rgba(255,255,255,0.88);
    border: 1px solid rgba(13,31,138,0.08); border-radius: 20px;
    padding: 1.2rem 1.4rem 1rem; margin-bottom: 0.9rem;
    box-shadow: 0 2px 16px rgba(13,31,138,0.06);
}
.qcard-num  { font-size:0.67rem; color:#1635CC; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; }
.qcard-text { font-size:0.94rem; color:#0D1F8A; font-style:italic; margin:0.3rem 0 0.8rem; }
.preview-strip { display:flex; gap:0.45rem; margin-bottom:0.8rem; }
.preview-strip a  { flex:1; display:block; }
.preview-strip img{ width:100%; height:90px; object-fit:cover; border-radius:10px;
                    border:1px solid rgba(13,31,138,0.1); display:block; }
.preview-ph { flex:1; height:90px; background:rgba(13,31,138,0.04);
              border-radius:10px; border:1px solid rgba(13,31,138,0.08); }
.btn-row { display:flex; flex-wrap:wrap; gap:0.3rem; }
.ref-btn { display:inline-flex; align-items:center; padding:0.3rem 0.82rem;
           border-radius:50px; text-decoration:none !important;
           font-size:0.75rem; font-weight:500; font-family:'Inter',sans-serif;
           transition:all 0.18s; border:1px solid transparent; }
.ref-btn:hover { opacity:0.82; transform:translateY(-1px); }
.btn-p  { background:rgba(230,0,35,0.09);  color:#cc0020 !important; border-color:rgba(230,0,35,0.2); }
.btn-b  { background:rgba(23,105,255,0.09); color:#1769FF !important; border-color:rgba(23,105,255,0.2); }
.btn-g  { background:rgba(255,255,255,0.8); color:#0D1F8A !important; border-color:rgba(13,31,138,0.18); }
.btn-a  { background:rgba(13,31,138,0.07); color:#0D1F8A !important; border-color:rgba(13,31,138,0.18); }
.btn-r  { background:rgba(22,53,204,0.09); color:#1635CC !important; border-color:rgba(22,53,204,0.2); }
.btn-f  { background:rgba(255,50,0,0.08);  color:#e63000 !important; border-color:rgba(255,50,0,0.2); }
.btn-t  { background:rgba(0,168,120,0.08); color:#00956a !important; border-color:rgba(0,168,120,0.2); }

/* ── Misc ── */
.kw-tag { display:inline-block; padding:0.2rem 0.76rem; margin:0.14rem;
          background:rgba(13,31,138,0.07); border:1px solid rgba(13,31,138,0.16);
          border-radius:50px; font-size:0.77rem; color:#1635CC;
          font-family:'Inter',sans-serif; font-weight:500; }
.badge  { display:inline-block; padding:0.1rem 0.46rem; border-radius:20px;
          font-size:0.64rem; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; }
.badge-unsplash  { background:rgba(13,31,138,0.09); color:#0D1F8A; }
.badge-pexels    { background:rgba(22,53,204,0.12); color:#1635CC; }
.badge-pinterest { background:rgba(230,0,35,0.09);  color:#cc0020; }
.filter-lbl { font-size:0.68rem; letter-spacing:0.12em; text-transform:uppercase;
              color:#3D5299; font-weight:600; margin:0.9rem 0 0.3rem; }
.swatch-row { display:flex; gap:0.85rem; flex-wrap:wrap; margin:1rem 0; }
.swatch { width:68px; text-align:center; }
.swatch-block { width:68px; height:60px; border-radius:14px;
                border:1px solid rgba(0,0,0,0.06); margin-bottom:0.32rem;
                box-shadow:0 2px 10px rgba(0,0,0,0.1); }
.swatch-hex { font-size:0.66rem; color:#3D5299; font-family:monospace; }
.prompt-box { background:rgba(255,255,255,0.82); border:1.5px solid rgba(13,31,138,0.15);
              border-radius:16px; padding:1.3rem 1.5rem; font-size:0.86rem; color:#0D1F8A;
              font-family:monospace; line-height:1.72; white-space:pre-wrap; }
.stSuccess { background:rgba(13,31,138,0.06) !important; color:#0D1F8A !important;
             border-left:4px solid #1635CC !important; border-radius:12px !important; }
.stInfo    { background:rgba(255,255,255,0.6) !important; color:#9099c4 !important;
             border-left:4px solid rgba(13,31,138,0.3) !important; border-radius:12px !important; }
.stInfo p, .stInfo [data-testid="stMarkdownContainer"] p { color:#9099c4 !important; }
.stWarning { background:rgba(100,120,220,0.1) !important;
             border:1px solid rgba(100,120,220,0.2) !important; border-radius:12px !important; }
.stWarning p, .stWarning [data-testid="stMarkdownContainer"] p { color:#9099c4 !important; }
hr { border-color:rgba(13,31,138,0.09) !important; }

/* ── Stay Connected card ── */
.sc-title {
    font-size: 0.67rem; letter-spacing: 0.14em; text-transform: uppercase;
    color: #1635CC; font-weight: 700; margin-bottom: 0.35rem; font-family: 'Inter', sans-serif;
}
.sc-body {
    font-size: 0.78rem; color: #ffffff; line-height: 1.5; margin-bottom: 0.85rem;
    font-family: 'Inter', sans-serif;
}

/* ── Browse filter pills ── */
button[data-testid="stBaseButton-pills"] {
    background: #ffffff !important;
    border: 1.5px solid rgba(100, 120, 220, 0.35) !important;
    color: #1a1a6e !important;
    border-radius: 9999px !important;
    transition: all 0.15s !important;
}
button[data-testid="stBaseButton-pills"]:hover {
    background: rgba(100, 120, 220, 0.08) !important;
    border-color: rgba(100, 120, 220, 0.6) !important;
    color: #1a1a6e !important;
}
button[data-testid="stBaseButton-pillsActive"] {
    background: #1a1a6e !important;
    border: 1.5px solid #1a1a6e !important;
    color: #ffffff !important;
    border-radius: 9999px !important;
    transition: all 0.15s !important;
}
button[data-testid="stBaseButton-pillsActive"]:hover {
    background: #2a2a8e !important;
    border-color: #2a2a8e !important;
    color: #ffffff !important;
}

/* ── Tabs (Palette page) ── */
button[data-testid="stTab"] {
    color: #9099c4 !important;
}
button[data-testid="stTab"] p {
    color: #9099c4 !important;
}
button[data-testid="stTab"]:hover {
    color: #e8541a !important;
}
button[data-testid="stTab"]:hover p {
    color: #e8541a !important;
}
button[data-testid="stTab"][aria-selected="true"] {
    color: #1a1a6e !important;
}
button[data-testid="stTab"][aria-selected="true"] p {
    color: #1a1a6e !important;
}
/* Active tab underline (sliding indicator div inside tablist) */
[role="tablist"] > [role="presentation"] {
    background-color: #1a1a6e !important;
}
/* Tab bar separator line */
[data-testid="stTabs"] [role="presentation"]:not([role="tablist"] > [role="presentation"]) {
    background-color: rgba(100, 120, 220, 0.2) !important;
}

/* ── Checkbox labels ── */
[data-testid="stCheckbox"] label p,
[data-testid="stCheckbox"] label span {
    color: #9099c4 !important;
}
[data-testid="stCheckbox"] label:has(input:checked) p,
[data-testid="stCheckbox"] label:has(input:checked) span {
    color: #1a1a6e !important;
}

/* ── Expander header ── */
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary span {
    color: #9099c4 !important;
}
[data-testid="stExpander"] summary:hover,
[data-testid="stExpander"] summary:hover p,
[data-testid="stExpander"] summary:hover span {
    color: #1a1a6e !important;
}

/* ── Radio buttons (Prompt page) ── */
[data-testid="stRadio"] > label,
[data-testid="stRadio"] > div > label {
    color: #9099c4 !important;
}
[data-testid="stRadio"] [role="radiogroup"] label > div:last-child,
[data-testid="stRadio"] [role="radiogroup"] label [data-testid="stMarkdownContainer"] p {
    color: #9099c4 !important;
}
[data-testid="stRadio"] [role="radiogroup"] label:hover > div:last-child,
[data-testid="stRadio"] [role="radiogroup"] label:hover [data-testid="stMarkdownContainer"] p {
    color: #e8541a !important;
}
[data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) > div:last-child,
[data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) [data-testid="stMarkdownContainer"] p {
    color: #1a1a6e !important;
}
/* Radio indicator — unselected: white fill, blue border */
[data-testid="stRadio"] [role="radiogroup"] label > div:first-child {
    background-color: #ffffff !important;
    border: 2px solid rgba(100, 120, 220, 0.5) !important;
}
/* Radio indicator inner dot — hidden when unselected */
[data-testid="stRadio"] [role="radiogroup"] label > div:first-child > div {
    background-color: transparent !important;
}
/* Radio indicator — selected: white fill, navy border */
[data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) > div:first-child {
    background-color: #ffffff !important;
    border-color: #1a1a6e !important;
}
/* Radio indicator inner dot — navy when selected */
[data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) > div:first-child > div {
    background-color: #1a1a6e !important;
}
/* Checkbox indicator — white fill, blue border */
[data-testid="stCheckbox"] label > span:first-child {
    background-color: #ffffff !important;
    border: 2px solid rgba(100, 120, 220, 0.5) !important;
    border-radius: 4px !important;
}
/* Checkbox checked — orange fill, orange border, white tick */
[data-testid="stCheckbox"] label:has(input:checked) > span:first-child {
    background-color: #FF6B2B !important;
    border-color: #FF6B2B !important;
}
[data-testid="stCheckbox"] label:has(input:checked) > span:first-child svg {
    fill: #ffffff !important;
    color: #ffffff !important;
    opacity: 1 !important;
}
/* Checkbox label text — orange when checked */
[data-testid="stCheckbox"] label:has(input:checked) p,
[data-testid="stCheckbox"] label:has(input:checked) span:not(:first-child) {
    color: #FF6B2B !important;
    font-weight: 600 !important;
}

/* ── Info & Warning alerts — tangerine theme ── */
[data-testid="stAlert"],
[data-testid="stAlertContainer"] {
    background-color: #FFE5CC !important;
    border: 1px solid #FF8C42 !important;
    border-radius: 10px !important;
}
[data-testid="stAlertContainer"] p,
[data-testid="stAlertContainer"] [data-testid="stMarkdownContainer"] p,
[data-testid="stAlert"] p {
    color: #C04A0A !important;
}
[data-testid="stAlertContainer"] svg,
[data-testid="stAlert"] svg {
    fill: #FF8C42 !important;
    color: #FF8C42 !important;
}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# Background
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="zn-blob" aria-hidden="true"></div>'
            '<div class="zn-grain" aria-hidden="true"></div>'
            '<div class="zn-bottom-fade" aria-hidden="true"></div>',
            unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# Topbar  — logo | segmented-control nav | brief button
# ══════════════════════════════════════════════════════════════════════════════
c_logo, c_nav, c_conn = st.columns([2.2, 6.8, 1.8])

with c_logo:
    st.markdown("""
    <div class="zn-logo-area">
      <svg width="17" height="17" viewBox="0 0 18 18" fill="none">
        <circle cx="9" cy="9" r="1.9" fill="#0D1F8A"/>
        <line x1="9" y1="1" x2="9" y2="4.5" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
        <line x1="9" y1="13.5" x2="9" y2="17" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
        <line x1="1" y1="9" x2="4.5" y2="9" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
        <line x1="13.5" y1="9" x2="17" y2="9" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
        <line x1="3.22" y1="3.22" x2="5.64" y2="5.64" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
        <line x1="12.36" y1="12.36" x2="14.78" y2="14.78" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
        <line x1="14.78" y1="3.22" x2="12.36" y2="5.64" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
        <line x1="5.64" y1="12.36" x2="3.22" y2="14.78" stroke="#0D1F8A" stroke-width="1.4" stroke-linecap="round"/>
      </svg>
      VISIONPULL
    </div>""", unsafe_allow_html=True)

with c_nav:
    st.segmented_control(
        "nav",
        options=["Home", "Search", "Browse", "Palette", "Board", "Prompt"],
        key="main_nav",
        label_visibility="collapsed",
    )

with c_conn:
    with open("render-image-finder.skill", "rb") as _f:
        _skill_bytes = _f.read()
    st.download_button(
        label="DOWNLOAD SKILL ●",
        data=_skill_bytes,
        file_name="render-image-finder.skill",
        mime="application/zip",
        key="nav_connect",
        type="primary",
        use_container_width=True,
    )

st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Brief  (Zeronode hero layout)
# ══════════════════════════════════════════════════════════════════════════════
if page == "Brief":
    # ── Layer 2 (left, z-10) │ Layer 3 (right, z-20 — single container) ─────
    left_col, _gap, right_col = st.columns([4.5, 0.4, 2.6])

    # ── Layer 2: hero heading + CTA buttons + brief form ─────────────────────
    with left_col:
        st.markdown("""
        <div class="zn-hero">
          <div class="zn-badge-pill">● WHERE RENDERS BEGIN</div>
          <h1 class="zn-headline">Where every reference<br>finds its <em>render.</em></h1>
          <p class="zn-hero-body">
            Visionpull curates architectural and interior references from
            Pinterest, Behance, Unsplash, Pexels, and more — powered by Claude
            AI to match your exact brief.
          </p>
        </div>
        """, unsafe_allow_html=True)

        b1, b2, _ = st.columns([2.4, 2, 2])
        with b1:
            if st.button("FIND REFERENCES →", type="primary", key="cta_find", use_container_width=True):
                if not st.session_state.brief_space or not st.session_state.brief_mood:
                    st.warning("Fill in Space and Mood in the brief below first.")
                else:
                    brief = {k: st.session_state[f"brief_{k}"] for k in ["space","style","mood","background"]}
                    if not st.session_state.history or st.session_state.history[0] != brief:
                        st.session_state.history.insert(0, brief)
                        st.session_state.history = st.session_state.history[:5]
                    go_to("Search")
        with b2:
            if st.button("BROWSE IMAGES", key="cta_browse", use_container_width=True):
                st.session_state.filter_results = []
                st.session_state.browse_results = []
                st.session_state["_auto_browse"] = True
                go_to("Browse")

        st.markdown("<div style='height:3rem'></div>", unsafe_allow_html=True)
        st.markdown('<div class="zn-card-label">YOUR BRIEF</div>', unsafe_allow_html=True)
        st.selectbox("template", list(TEMPLATES.keys()), key="template_selector",
                     on_change=on_template_change, label_visibility="collapsed")
        ci1, ci2 = st.columns(2)
        with ci1:
            st.text_input("Space", placeholder="e.g. living room", key="brief_space")
        with ci2:
            st.selectbox("Style", STYLE_OPTIONS, key="brief_style")
        st.text_input("Mood", placeholder="e.g. warm, earthy, editorial", key="brief_mood")

        st.markdown("<div style='margin-top:1rem;margin-bottom:0.3rem'>"
                    "<span style='font-size:0.68rem;letter-spacing:0.12em;text-transform:uppercase;"
                    "color:#3D5299;font-weight:600;'>OR UPLOAD ASSIGNMENT BRIEF</span></div>",
                    unsafe_allow_html=True)
        brief_file = st.file_uploader("Upload brief (PDF or image)", type=["png","jpg","jpeg","pdf","webp"],
                                       label_visibility="collapsed", key="brief_upload")
        if brief_file is not None:
            if st.button("Extract Brief from File", type="primary", key="extract_brief_btn"):
                file_bytes = brief_file.read()
                mime = brief_file.type or "image/jpeg"
                with st.spinner("Reading brief with Claude AI..."):
                    extracted = extract_brief_from_file(file_bytes, mime)
                if extracted:
                    st.session_state["_brief_extracted"] = extracted
                    st.rerun()
                else:
                    st.warning("Could not extract brief — try a clearer image or PDF.")

    # ── Layer 3: single right-side container — always above the gradient ──────
    with right_col:
        st.markdown("<div style='padding-top:3.5rem'></div>", unsafe_allow_html=True)
        st.markdown('''
<div class="fp-container">
  <a href="https://pinterest.com" target="_blank" rel="noopener noreferrer" class="fp-pill">
    ⊕&nbsp;&nbsp;Pinterest
  </a>
  <a href="https://www.archdaily.com" target="_blank" rel="noopener noreferrer" class="fp-pill">
    ⊙&nbsp;&nbsp;Arch Daily
  </a>
  <a href="https://www.dezeen.com" target="_blank" rel="noopener noreferrer" class="fp-pill">
    ◈&nbsp;&nbsp;Dezeen
  </a>
</div>
''', unsafe_allow_html=True)

        st.markdown("<div style='height:3rem'></div>", unsafe_allow_html=True)
        st.markdown('<div class="zn-card-label">SESSION</div>', unsafe_allow_html=True)
        n_b = len(st.session_state.selected_images)
        n_h = len(st.session_state.history)
        n_q = len(st.session_state.generated_queries)
        n_p = len(st.session_state.saved_palettes)
        st.markdown(f"""
        <div class="zn-stats-grid">
          <div class="zn-stat"><div class="zn-stat-val">{n_b}</div><div class="zn-stat-lbl">Board</div></div>
          <div class="zn-stat"><div class="zn-stat-val">{n_p}</div><div class="zn-stat-lbl">Palettes</div></div>
          <div class="zn-stat"><div class="zn-stat-val">{n_h}</div><div class="zn-stat-lbl">Briefs</div></div>
          <div class="zn-stat"><div class="zn-stat-val">{n_q}</div><div class="zn-stat-lbl">Queries</div></div>
        </div>""", unsafe_allow_html=True)
        if st.session_state.history:
            last = st.session_state.history[0]
            st.markdown(f"<div style='font-size:0.77rem;color:#3D5299;margin-top:0.4rem'>"
                        f"Last: {last['space']} · {last['style']}</div>", unsafe_allow_html=True)
        if n_b:
            if st.button("Open Mood Board →", use_container_width=True):
                go_to("Board")

        st.markdown('<hr style="border-color:rgba(13,31,138,0.08);margin:1rem 0">', unsafe_allow_html=True)

        # ── Saved Sessions (per-user browser localStorage) ────────────────────
        st.markdown('<div class="sv-label">SAVED SESSIONS</div>', unsafe_allow_html=True)

        # Pending write? Fold it into the same JS call as the read so it's atomic.
        # Version counter in the key forces st_javascript to re-instantiate (fresh
        # JS execution) instead of returning a cached value.
        _ls_ver = st.session_state.get("_ls_write_ver", 0)
        _pending_write = st.session_state.pop("_ls_pending_write", None)
        if _pending_write is not None:
            _payload_js = json.dumps(json.dumps(_pending_write))
            _js_expr = (
                f"(localStorage.setItem('{_LS_KEY}',{_payload_js}),"
                f"localStorage.getItem('{_LS_KEY}')||'[]')"
            )
        else:
            _js_expr = f"localStorage.getItem('{_LS_KEY}')||'[]'"

        _ls_raw = st_javascript(_js_expr, key=f"ls_sessions_rw_{_ls_ver}")

        # Only populate _cached_sessions from localStorage on a fresh page load.
        if "_cached_sessions" not in st.session_state:
            if isinstance(_ls_raw, str) and _ls_raw not in ("0", "", "[]"):
                try:
                    _parsed = json.loads(_ls_raw)
                    if isinstance(_parsed, list):
                        st.session_state["_cached_sessions"] = _parsed
                except Exception:
                    pass

        _all_sessions = st.session_state.get("_cached_sessions", [])

        if _all_sessions:
            for _i, _s in enumerate(_all_sessions[:4]):
                _col_name, _col_btns = st.columns([3, 2])
                with _col_name:
                    _sv_name = html.escape(_s['name'] or _s.get('brief_space') or 'Untitled')
                    _sv_time = html.escape(_s['timestamp'])
                    st.markdown(
                        f"<div class='sv-item'>"
                        f"<div><div class='sv-name'>{_sv_name}</div>"
                        f"<div class='sv-time'>{_sv_time}</div></div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                with _col_btns:
                    _b_load, _b_del = st.columns([2, 1])
                    with _b_load:
                        if st.button("Load", key=f"restore_{_i}", use_container_width=True):
                            _restore_session(_s)
                            st.rerun()
                    with _b_del:
                        if st.button("✕", key=f"del_session_{_i}", use_container_width=True,
                                     help="Delete this session"):
                            _remaining = [s for j, s in enumerate(_all_sessions) if j != _i]
                            st.session_state["_cached_sessions"] = _remaining
                            _ls_write(_remaining)
                            st.rerun()
        else:
            st.markdown("<div class='sv-empty'>No saved sessions yet.</div>", unsafe_allow_html=True)

        _save_name = st.text_input("Session name", placeholder="e.g. Nordic Living Room",
                                   label_visibility="collapsed", key="save_session_name")
        if st.button("Save Current Session", use_container_width=True, key="save_session_btn"):
            _name = _save_name.strip() or (st.session_state.get("brief_space") or "Untitled")
            _new_s = _build_session_record(_name)
            _updated = ([_new_s] + _all_sessions)[:10]
            st.session_state["_cached_sessions"] = _updated
            _ls_write(_updated)
            st.success("Session saved!")
            st.rerun()

        if st.button("＋ New Session", use_container_width=True, key="new_session_btn"):
            # Clear all work state via the restore-staging pattern so widget
            # keys are reset before widgets render on next rerun.
            st.session_state["_session_restore"] = {
                "brief_space": "", "brief_style": "Dreamy",
                "brief_mood": "", "brief_background": "White/Isolated",
                "selected_images": [], "saved_palettes": [], "generated_queries": [],
            }
            st.rerun()

        st.markdown('<hr style="border-color:rgba(13,31,138,0.08);margin:1rem 0">', unsafe_allow_html=True)
        st.markdown("""
        <div class="sc-title">STAY CONNECTED</div>
        <div class="sc-body">Forward your curated board references straight to your inbox.</div>
        """, unsafe_allow_html=True)
        board_email = st.text_input("Email", placeholder="you@studio.com",
                                    key="board_email_input", label_visibility="collapsed")
        if st.button("Send Board →", key="send_board_btn", type="primary", use_container_width=True):
            _email = st.session_state.get("board_email_input", "").strip()
            _imgs  = st.session_state.get("selected_images", [])
            if not _email or not _is_valid_email(_email):
                st.session_state["_send_result"] = ("warn", "Enter a valid email address.")
            elif not _imgs:
                st.session_state["_send_result"] = ("warn", "Add images to your Board first.")
            else:
                sent, msg = send_board_email(_email, _imgs)
                if sent:
                    st.session_state["_send_result"] = ("ok", f"Board sent to {_email}!")
                else:
                    st.session_state["_send_result"] = ("err", msg)
            st.rerun()
        # ── Send board feedback (rendered outside column so it always shows) ──
if "_send_result" in st.session_state:
    _kind, _txt = st.session_state.pop("_send_result")
    if _kind == "ok":
        st.success(_txt)
    elif _kind == "warn":
        st.warning(_txt)
    else:
        # SMTP error — show links fallback
        st.warning(f"Email error: {_txt}")
        links = "\n".join(img["link"] for img in st.session_state.get("selected_images", []))
        if links:
            st.text_area("Copy these links instead:", links, height=90, key="board_links_out")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Search
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Search":
    st.markdown('<div class="zn-page-header"><div class="zn-badge-small">● AI-GENERATED</div>'
                '<h2 class="zn-page-title">Reference Queries</h2></div>', unsafe_allow_html=True)

    white_bg_only = st.checkbox("White / isolated backgrounds only (for Photoshop cutouts)", key="search_white_bg")

    render_elem = st.checkbox("Render Elements mode — find plant, tree, people & furniture cutouts for compositing", key="search_render_elem")
    elem_type = None
    if render_elem:
        elem_type = st.selectbox("Element type",
            ["Plants & Vegetation", "Trees & Shrubs", "Wildflowers & Meadow Grasses",
             "People / Scale Figures", "Furniture & Objects", "Vehicles & Bikes"],
            key="search_elem_type", label_visibility="collapsed")

    if st.button("Generate Queries", type="primary"):
        _snap = st.session_state.get("_brief_snapshot", {})
        sp = st.session_state.brief_space or _snap.get("space", "")
        mo = st.session_state.brief_mood or _snap.get("mood", "")
        if not render_elem and (not sp or not mo):
            st.warning("Go to **Home** and fill in Space and Mood first.")
        else:
            sty = st.session_state.brief_style or _snap.get("style", "Dreamy")
            bg = st.session_state.brief_background or _snap.get("background", "White/Isolated")
            brief = {"space":sp,"style":sty,"mood":mo,"background":bg}
            if not st.session_state.history or st.session_state.history[0] != brief:
                st.session_state.history.insert(0,brief); st.session_state.history = st.session_state.history[:5]
            if render_elem and elem_type:
                prompt = (
                    f"Generate 5 highly specific search queries to find isolated Photoshop render entourage elements — "
                    f"cutouts on white or transparent backgrounds for architectural compositing. "
                    f"Element type: {elem_type}. Style context: {sty}, Mood: {mo}. "
                    f"Each query MUST include at least one term from this list: "
                    f"'PNG transparent background', 'isolated cutout', 'white background photoshop', "
                    f"'architectural entourage', 'render element', 'cutout transparent', 'isolated on white'. "
                    f"Use specific botanical, material, or design vocabulary (e.g. pampas grass, ornamental grass, "
                    f"prairie wildflowers, mixed shrubbery, tall grasses). "
                    f"Return numbered list only, no extra text."
                )
            else:
                bg_note = (" Prioritise queries that surface white-background or isolated-object shots suitable for Photoshop compositing."
                           if white_bg_only else "")
                prompt = (f"Generate 5 targeted search queries for a designer finding Photoshop render references. "
                          f"Brief — Space: {sp}, Style: {sty}, Mood: {mo}, Background: {bg}.{bg_note} "
                          f"Use designer vocabulary. Return numbered list only, no extra text.")
            with st.spinner("Generating queries..."):
                resp = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=512,
                    messages=[{"role":"user","content":prompt}])
            st.session_state.generated_queries = [l.strip() for l in resp.content[0].text.strip().splitlines() if l.strip()]

    if st.session_state.generated_queries:
        lines = st.session_state.generated_queries
        has_keys = bool(get_secret("UNSPLASH_ACCESS_KEY") or get_secret("PEXELS_API_KEY"))
        kws = extract_keywords([l.lstrip("0123456789. ").strip('"') for l in lines])
        if kws:
            st.markdown("<div style='margin-bottom:1.4rem'>" +
                        "".join(f"<span class='kw-tag'>{w}</span>" for w in kws) +
                        "</div>", unsafe_allow_html=True)
        for i, line in enumerate(lines, 1):
            qt  = line.lstrip("0123456789. ").strip('"')
            enc = urllib.parse.quote_plus(qt)
            previews = []
            if has_keys:
                wb = " white background isolated" if st.session_state.get("search_white_bg") else ""
                previews = search_unsplash(qt + wb, n=3)
                if len(previews) < 3: previews += search_pexels(qt + wb, n=3-len(previews))
            strip = ""
            if previews:
                strip = '<div class="preview-strip">' + "".join(
                    f'<a href="{p["link"]}" target="_blank"><img src="{p["thumb"]}" alt=""></a>'
                    for p in previews[:3]) + "</div>"
            elif has_keys:
                strip = '<div class="preview-strip">' + '<div class="preview-ph"></div>'*3 + "</div>"
            if st.session_state.get("search_render_elem"):
                src_buttons = (
                    f'<a class="ref-btn btn-p" href="https://www.pinterest.com/search/pins/?q={enc}" target="_blank">Pinterest</a>'
                    f'<a class="ref-btn btn-g" href="https://www.google.com/search?tbm=isch&q={enc}" target="_blank">Google Images</a>'
                    f'<a class="ref-btn btn-f" href="https://www.freepik.com/search?query={enc}" target="_blank">Freepik</a>'
                    f'<a class="ref-btn btn-t" href="https://pngtree.com/search?q={enc}" target="_blank">PNGTree</a>'
                    f'<a class="ref-btn btn-b" href="https://www.behance.net/search/projects?search={enc}" target="_blank">Behance</a>'
                )
            else:
                src_buttons = (
                    f'<a class="ref-btn btn-p" href="https://www.pinterest.com/search/pins/?q={enc}" target="_blank">Pinterest</a>'
                    f'<a class="ref-btn btn-b" href="https://www.behance.net/search/projects?search={enc}" target="_blank">Behance</a>'
                    f'<a class="ref-btn btn-g" href="https://www.google.com/search?tbm=isch&q={enc}" target="_blank">Google Images</a>'
                    f'<a class="ref-btn btn-a" href="https://archinect.com/search#/?q={enc}&type=photos" target="_blank">Archinect</a>'
                    f'<a class="ref-btn btn-r" href="https://www.are.na/search/{enc}" target="_blank">Are.na</a>'
                )
            st.markdown(f"""
            <div class="qcard">
              <div class="qcard-num">Query {i}</div>
              <div class="qcard-text">{html.escape(qt)}</div>
              {strip}
              <div class="btn-row">{src_buttons}</div>
            </div>""", unsafe_allow_html=True)
        if not has_keys:
            st.info("Add **UNSPLASH_ACCESS_KEY** or **PEXELS_API_KEY** to secrets for image previews.")
        st.success(f"{len(lines)} queries generated.")
    else:
        st.info("Click **Generate Queries** to create AI-powered search queries from your brief.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Browse
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Browse":
    st.markdown('<div class="zn-page-header"><div class="zn-badge-small">● NO AI NEEDED</div>'
                '<h2 class="zn-page-title">Browse & Filter</h2></div>', unsafe_allow_html=True)

    st.markdown("<div class='filter-lbl'>Space</div>", unsafe_allow_html=True)
    sel_spaces = st.pills("spaces", FILTER_SPACES, selection_mode="multi", label_visibility="collapsed")
    st.markdown("<div class='filter-lbl'>Style</div>", unsafe_allow_html=True)
    sel_styles = st.pills("styles", FILTER_STYLES, selection_mode="multi", label_visibility="collapsed")
    st.markdown("<div class='filter-lbl'>Mood</div>", unsafe_allow_html=True)
    sel_moods  = st.pills("moods",  FILTER_MOODS,  selection_mode="multi", label_visibility="collapsed")
    st.markdown("<div class='filter-lbl'>Lighting</div>", unsafe_allow_html=True)
    sel_lights = st.pills("lights", FILTER_LIGHTS, selection_mode="multi", label_visibility="collapsed")
    st.markdown("<div class='filter-lbl'>Background</div>", unsafe_allow_html=True)
    sel_bg = st.pills("background", ["White/Isolated"], selection_mode="single", label_visibility="collapsed")

    st.markdown("<br>", unsafe_allow_html=True)
    bg_suffix = " white background isolated product photography" if sel_bg == "White/Isolated" else ""
    fa, fb = st.columns([2, 5])
    with fa:
        filter_btn = st.button("Browse Images", type="primary", use_container_width=True)
    with fb:
        tags = list(sel_spaces or []) + list(sel_styles or []) + list(sel_moods or []) + list(sel_lights or [])
        display_tags = tags + (["White/Isolated"] if sel_bg == "White/Isolated" else [])
        if display_tags:
            st.markdown(f"<div style='padding-top:0.55rem;color:#1635CC;font-size:0.82rem;'>"
                        f"Query: <em>{', '.join(display_tags)}</em></div>", unsafe_allow_html=True)

    if filter_btn:
        tags = list(sel_spaces or []) + list(sel_styles or []) + list(sel_moods or []) + list(sel_lights or [])
        if not tags and not sel_bg:
            st.warning("Select at least one filter.")
        elif not get_secret("UNSPLASH_ACCESS_KEY") and not get_secret("PEXELS_API_KEY"):
            st.warning("Add image API keys to Streamlit secrets.")
        else:
            q = " ".join(tags) + bg_suffix + " interior architecture"
            with st.spinner("Fetching images..."):
                st.session_state.filter_results = search_unsplash(q, n=9) + search_pexels(q, n=9)

    def _run_browse_from_brief():
        _snap = st.session_state.get("_brief_snapshot", {})
        sp = st.session_state.brief_space or _snap.get("space", "")
        mo = st.session_state.brief_mood or _snap.get("mood", "")
        if not sp or not mo:
            st.warning("Set a brief on the Home page first.")
            return
        if not get_secret("UNSPLASH_ACCESS_KEY") and not get_secret("PEXELS_API_KEY"):
            st.warning("Add image API keys to Streamlit secrets.")
            return
        brief_bg_suffix = " white background isolated product photography" if st.session_state.brief_background == "White/Isolated" else ""
        sty = st.session_state.brief_style or _snap.get("style", "Dreamy")
        q = f"{sty} {sp} {mo}{brief_bg_suffix} interior architecture"
        with st.spinner("Fetching images..."):
            st.session_state.browse_results = search_unsplash(q, n=9) + search_pexels(q, n=9)

    if st.session_state.pop("_auto_browse", False):
        _run_browse_from_brief()

    fa2, _ = st.columns([2, 5])
    with fa2:
        if st.button("Browse from Brief", use_container_width=True):
            _run_browse_from_brief()

    results = st.session_state.filter_results or st.session_state.browse_results
    if results:
        st.markdown(f"<p style='color:#3D5299;font-size:0.82rem;margin:1rem 0'>"
                    f"Showing {len(results)} images</p>", unsafe_allow_html=True)
        render_image_grid(results, key_prefix="br")
        if len(st.session_state.comparison_images) == 2:
            st.divider()
            st.markdown('<div class="zn-badge-small">● COMPARISON</div>', unsafe_allow_html=True)
            ca, cb = st.columns(2)
            for col, img in zip([ca, cb], st.session_state.comparison_images):
                with col:
                    st.caption(f"{img['source'].upper()} — {img['author']}")
                    st.image(img["full"], width="stretch")
            if st.button("Clear comparison"):
                st.session_state.comparison_images = []; st.rerun()
    else:
        st.info("Select filters and click **Browse Images**, or use **Browse from Brief**.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Palette
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Palette":
    st.markdown('<div class="zn-page-header"><div class="zn-badge-small">● COLOR EXTRACTION</div>'
                '<h2 class="zn-page-title">Palette Extractor</h2></div>', unsafe_allow_html=True)

    n_colors = st.slider("Number of colors", 3, 10, 6)

    pal_tab1, pal_tab2, pal_tab3 = st.tabs(["Upload Image", "From URL", "From Board"])

    def _show_palette(hexes, source_label="", key_suffix=""):
        if not hexes:
            st.warning("Could not extract palette — try a clearer image.")
            return
        if source_label:
            st.markdown(f"<div style='font-size:0.75rem;color:#3D5299;margin-bottom:0.6rem'>"
                        f"Source: <strong>{html.escape(source_label)}</strong></div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='swatch-row'>" +
            "".join(f"<div class='swatch'><div class='swatch-block' style='background:{h}'></div>"
                     f"<div class='swatch-hex'>{h}</div></div>" for h in hexes) +
            "</div>", unsafe_allow_html=True)
        c1, c2, c3, _ = st.columns([1, 1, 1.3, 0.7])
        with c1:
            st.download_button("Download CSV", ",".join(hexes).encode(), "palette.csv", "text/csv",
                               key=f"dl_pal_csv{key_suffix}")
        with c2:
            aco = "\n".join(f"{h}" for h in hexes)
            st.download_button("Download TXT", aco.encode(), "palette.txt", "text/plain",
                               key=f"dl_pal_txt{key_suffix}")
        with c3:
            already = any(p["hexes"] == hexes for p in st.session_state.saved_palettes)
            if st.button("✓ Saved" if already else "+ Save Palette",
                         key=f"save_pal{key_suffix}", type="primary", use_container_width=True):
                if not already:
                    st.session_state.saved_palettes.append({
                        "hexes": hexes,
                        "label": source_label or "Custom palette",
                    })
                    st.rerun()
        st.success(f"Extracted {len(hexes)} colors.")

    with pal_tab1:
        pal_file = st.file_uploader("Upload image (JPG, PNG, WEBP)", type=["jpg","jpeg","png","webp"],
                                     label_visibility="collapsed", key="pal_upload")
        if pal_file:
            try:
                file_bytes = pal_file.read()
                st.session_state["_pal_bytes"] = file_bytes
                st.session_state["_pal_name"] = pal_file.name
                col_img, _ = st.columns([2, 3])
                with col_img:
                    st.image(file_bytes, caption=pal_file.name, width="stretch")
            except Exception as e:
                st.warning(f"Could not preview image: {e}")

        if st.button("Extract Palette from Upload", type="primary", key="pal_upload_btn"):
            fb = st.session_state.get("_pal_bytes")
            fn = st.session_state.get("_pal_name", "uploaded image")
            if not fb:
                st.warning("Upload an image first.")
            else:
                with st.spinner("Extracting..."):
                    hexes = extract_palette_from_bytes(fb, n=n_colors)
                st.session_state["_pal_upload_result"] = {"hexes": hexes, "label": fn}
        if st.session_state.get("_pal_upload_result"):
            r = st.session_state["_pal_upload_result"]
            _show_palette(r["hexes"], source_label=r["label"], key_suffix="_upload")

    with pal_tab2:
        palette_url = st.text_input("Paste a direct image URL (.jpg / .png)",
                                     placeholder="https://images.unsplash.com/photo-...",
                                     key="pal_url_input")
        if st.button("Extract Palette from URL", type="primary", key="pal_url_btn"):
            if not palette_url.strip():
                st.warning("Paste an image URL first.")
            else:
                with st.spinner("Downloading & extracting..."):
                    hexes = extract_palette(palette_url.strip(), n=n_colors)
                st.session_state["_pal_url_result"] = {"hexes": hexes, "label": palette_url.strip()[:60]+"…"}
        if st.session_state.get("_pal_url_result"):
            r = st.session_state["_pal_url_result"]
            _show_palette(r["hexes"], source_label=r["label"], key_suffix="_url")

    with pal_tab3:
        board_imgs = st.session_state.selected_images
        if not board_imgs:
            st.info("Add images to your Board first, then extract palettes from them here.")
        else:
            st.markdown(f"<p style='color:#3D5299;font-size:0.82rem'>{len(board_imgs)} image(s) on board</p>",
                        unsafe_allow_html=True)
            for i, img in enumerate(board_imgs):
                c_img, c_btn = st.columns([2, 3])
                with c_img:
                    st.image(img["thumb"], width="stretch")
                    st.caption(f"{img['source'].upper()} — {img['author']}")
                with c_btn:
                    if st.button(f"Extract from image {i+1}", key=f"pal_board_{i}"):
                        with st.spinner("Extracting..."):
                            hexes = extract_palette(img["full"], n=n_colors)
                        st.session_state[f"_pal_board_result_{i}"] = {
                            "hexes": hexes,
                            "label": f"{img['source']} by {img['author']}",
                        }
                    if st.session_state.get(f"_pal_board_result_{i}"):
                        r = st.session_state[f"_pal_board_result_{i}"]
                        _show_palette(r["hexes"], source_label=r["label"], key_suffix=f"_b{i}")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Board
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Board":
    st.markdown('<div class="zn-page-header"><div class="zn-badge-small">● EXPORT</div>'
                '<h2 class="zn-page-title">Mood Board</h2></div>', unsafe_allow_html=True)
    if not st.session_state.selected_images:
        st.info("Browse images on **Browse** and click **+ Board** to add them here.")
    else:
        imgs = st.session_state.selected_images

        # ── Image selection ───────────────────────────────────────────────────
        st.markdown("<div style='font-size:0.72rem;letter-spacing:0.12em;text-transform:uppercase;"
                    "color:#1635CC;font-weight:700;margin-bottom:0.5rem'>IMAGES</div>",
                    unsafe_allow_html=True)
        st.caption("Tick images to include in the moodboard. Untick to exclude without removing.")
        prev_cols = st.columns(min(len(imgs), 4))
        _mb_img_flags = []
        for i, img in enumerate(imgs):
            with prev_cols[i % 4]:
                st.image(img["thumb"], width="stretch")
                _included = st.checkbox("Include", value=True, key=f"mb_img_{i}")
                _mb_img_flags.append(_included)
                if st.button("Remove", key=f"rm_{i}", use_container_width=True):
                    st.session_state.selected_images.pop(i); st.rerun()

        # ── Palette selection ─────────────────────────────────────────────────
        _saved_pals = st.session_state.get("saved_palettes", [])
        _mb_pal_flags = []
        if _saved_pals:
            st.divider()
            st.markdown("<div style='font-size:0.72rem;letter-spacing:0.12em;text-transform:uppercase;"
                        "color:#1635CC;font-weight:700;margin-bottom:0.5rem'>PALETTES</div>",
                        unsafe_allow_html=True)
            st.caption("Tick palettes to embed their swatches in the moodboard.")
            pal_cols = st.columns(min(len(_saved_pals), 3))
            for j, _pal in enumerate(_saved_pals):
                with pal_cols[j % 3]:
                    _swatches_html = "".join(
                        f"<div style='display:inline-block;width:28px;height:28px;"
                        f"background:{h};border-radius:3px;margin:2px'></div>"
                        for h in _pal.get("hexes", [])[:8]
                    )
                    st.markdown(
                        f"<div style='margin-bottom:4px'>{_swatches_html}</div>"
                        f"<div style='font-size:0.72rem;color:#3D5299;margin-bottom:6px'>"
                        f"{_pal.get('label','Palette')}</div>",
                        unsafe_allow_html=True,
                    )
                    _pal_inc = st.checkbox("Include", value=True, key=f"mb_pal_{j}")
                    _mb_pal_flags.append(_pal_inc)

        st.divider()
        gc1, gc2, gc3, gc4, gc5 = st.columns([1.2, 1.2, 1.2, 1.5, 1.5])
        with gc1:
            mb_layout = st.selectbox("Layout", ["Grid", "Collage"], index=0)
        with gc2:
            mb_cols = st.selectbox("Grid columns", [2, 3, 4], index=1,
                                   disabled=(mb_layout == "Collage"))
        with gc3:
            export_fmt = st.selectbox("Format", ["PNG", "JPEG", "PDF"], index=0)
        with gc4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Generate Mood Board", type="primary", use_container_width=True):
                _sel_imgs = [img for img, flag in zip(imgs, _mb_img_flags) if flag]
                _pal_colors = []
                for j, _pal in enumerate(_saved_pals):
                    if j < len(_mb_pal_flags) and _mb_pal_flags[j]:
                        _pal_colors.extend(_pal.get("hexes", []))
                if not _sel_imgs:
                    st.warning("Select at least one image to include.")
                else:
                    with st.spinner("Compositing..."):
                        if mb_layout == "Collage":
                            png = create_collage_moodboard(_sel_imgs,
                                                           palette_colors=_pal_colors or None)
                        else:
                            png = create_moodboard(_sel_imgs, cols=mb_cols,
                                                   palette_colors=_pal_colors or None)
                    if png:
                        st.session_state["_mb_png"] = png
                        st.session_state["_mb_fmt"] = export_fmt
                    else:
                        st.warning("Could not load images.")
        with gc5:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Clear All", use_container_width=True):
                st.session_state.selected_images = []
                st.session_state.pop("_mb_png", None)
                st.rerun()

        if "_mb_png" in st.session_state:
            _raw_png = st.session_state["_mb_png"]
            _fmt = st.session_state.get("_mb_fmt", "PNG")
            st.image(_raw_png)
            if _fmt == "PNG":
                st.download_button("⬇ Download PNG", _raw_png, "moodboard.png", "image/png",
                                   type="primary", use_container_width=True)
            elif _fmt == "JPEG":
                _jbuf = io.BytesIO()
                Image.open(io.BytesIO(_raw_png)).convert("RGB").save(_jbuf, "JPEG", quality=92)
                st.download_button("⬇ Download JPEG", _jbuf.getvalue(), "moodboard.jpg", "image/jpeg",
                                   type="primary", use_container_width=True)
            elif _fmt == "PDF":
                _pbuf = io.BytesIO()
                Image.open(io.BytesIO(_raw_png)).save(_pbuf, "PDF")
                st.download_button("⬇ Download PDF", _pbuf.getvalue(), "moodboard.pdf", "application/pdf",
                                   type="primary", use_container_width=True)

    st.divider()
    st.markdown('<div class="zn-card-label">SAVED PALETTES</div>', unsafe_allow_html=True)
    saved_pals = st.session_state.saved_palettes
    if not saved_pals:
        st.info("Extract a palette on the **Palette** page and click **+ Save Palette** to collect it here.")
    else:
        st.markdown(f"<p style='color:#3D5299;font-size:0.82rem;margin-bottom:1rem'>"
                    f"{len(saved_pals)} palette(s) saved</p>", unsafe_allow_html=True)
        for pi, pal in enumerate(saved_pals):
            with st.container():
                pc1, pc2 = st.columns([6, 1])
                with pc1:
                    if pal.get("label"):
                        st.markdown(f"<div style='font-size:0.72rem;color:#3D5299;margin-bottom:0.35rem'>"
                                    f"{pal['label']}</div>", unsafe_allow_html=True)
                    st.markdown(
                        "<div class='swatch-row' style='margin:0 0 0.6rem'>" +
                        "".join(
                            f"<div class='swatch'>"
                            f"<div class='swatch-block' style='background:{h}'></div>"
                            f"<div class='swatch-hex'>{h}</div></div>"
                            for h in pal["hexes"]
                        ) + "</div>", unsafe_allow_html=True)
                    st.download_button(
                        "Download CSV",
                        ",".join(pal["hexes"]).encode(),
                        f"palette_{pi+1}.csv", "text/csv",
                        key=f"dl_saved_pal_{pi}",
                    )
                with pc2:
                    st.markdown("<br><br>", unsafe_allow_html=True)
                    if st.button("Remove", key=f"rm_pal_{pi}", use_container_width=True):
                        st.session_state.saved_palettes.pop(pi); st.rerun()
            st.markdown("<hr style='border-color:rgba(13,31,138,0.07);margin:0.6rem 0'>",
                        unsafe_allow_html=True)
        if st.button("Clear All Palettes", key="clear_all_pals"):
            st.session_state.saved_palettes = []; st.rerun()

    st.divider()
    st.markdown('<div class="zn-card-label">PIN FROM PINTEREST</div>', unsafe_allow_html=True)
    st.markdown("<p style='font-size:0.8rem;color:#9099c4;margin-bottom:0.8rem'>"
                "Paste a Pinterest pin URL or copy the image URL directly from Pinterest to add it to your board.</p>",
                unsafe_allow_html=True)
    pa, pb = st.columns([5, 1.4])
    with pa:
        pin_input = st.text_input("Pinterest URL",
                                   placeholder="https://www.pinterest.com/pin/… or paste image URL",
                                   key="pin_url_input", label_visibility="collapsed")
    with pb:
        pin_btn = st.button("Add to Board", type="primary", key="pin_add_btn", use_container_width=True)
    if pin_btn:
        if not pin_input.strip():
            st.warning("Paste a Pinterest pin URL or image URL first.")
        else:
            with st.spinner("Fetching pin..."):
                pin_data = fetch_pinterest_image(pin_input.strip())
            if pin_data:
                if any(x.get("link") == pin_data["link"] for x in st.session_state.selected_images):
                    st.info("This pin is already on your board.")
                else:
                    st.session_state.selected_images.append(pin_data)
                    st.success("Pin added to board!")
                    st.rerun()
            else:
                st.warning("Could not fetch image. On Pinterest, right-click the image → Copy image address, then paste that URL here.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Prompt
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Prompt":
    st.markdown('<div class="zn-page-header"><div class="zn-badge-small">● AI GENERATION</div>'
                '<h2 class="zn-page-title">Prompt Generator</h2></div>', unsafe_allow_html=True)
    platform = st.radio("Platform", ["Midjourney", "Stable Diffusion", "Both"], horizontal=True)

    p_space = st.session_state.brief_space or ""
    p_style = st.session_state.brief_style
    p_mood  = st.session_state.brief_mood  or ""
    p_bg    = st.session_state.brief_background

    brief_parts = [x for x in [p_space, p_style, p_mood] if x]
    if brief_parts:
        st.markdown(f"<p style='font-size:0.8rem;color:#9099c4;margin:0.3rem 0 0.8rem'>"
                    f"Brief: {' · '.join(brief_parts)}</p>", unsafe_allow_html=True)

    with st.expander("Override brief for this prompt"):
        oc1, oc2 = st.columns(2)
        with oc1:
            p_space = st.text_input("Space",  value=p_space, key="ps")
            p_style = st.selectbox("Style",   STYLE_OPTIONS,
                                   index=STYLE_OPTIONS.index(p_style) if p_style in STYLE_OPTIONS else 0, key="pst")
        with oc2:
            p_mood  = st.text_input("Mood",   value=p_mood,  key="pm")
            p_bg    = st.selectbox("Background", BG_OPTIONS,
                                   index=BG_OPTIONS.index(p_bg) if p_bg in BG_OPTIONS else 0, key="pb")

    if st.button("Generate Prompt", type="primary"):
        if not p_space or not p_mood:
            st.warning("Fill in Space and Mood (in Home brief or override above).")
        else:
            if platform == "Midjourney":
                instr = "Generate a detailed Midjourney prompt only. End with --ar 16:9 --v 6.1 --style raw"
            elif platform == "Stable Diffusion":
                instr = ("Generate a Stable Diffusion prompt with positive comma-separated tags, "
                         "then a blank line, then 'Negative prompt:' with negative tags.")
            else:
                instr = ("Generate both:\n1) Midjourney prompt (end with --ar 16:9 --v 6.1 --style raw)\n"
                         "2) Stable Diffusion prompt with positive tags and Negative prompt: line.")
            full = (f"{instr}\nBrief: Space: {p_space}, Style: {p_style}, Mood: {p_mood}, Background: {p_bg}.\n"
                    f"Include camera angle, lighting quality, material palette, atmosphere, color grading.")
            with st.spinner("Crafting prompt..."):
                resp = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=600,
                    messages=[{"role":"user","content":full}])
            result = resp.content[0].text.strip()
            st.markdown(f"<div class='prompt-box'>{html.escape(result).replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
            dl_col, _ = st.columns([1,3])
            with dl_col:
                st.download_button("Download .txt", result.encode(), "prompt.txt", "text/plain")
            st.success("Prompt ready.")
    else:
        st.info("Set your brief on the **Home** page then click **Generate Prompt**.")

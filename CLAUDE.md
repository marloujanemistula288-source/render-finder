# Render Finder — Claude instructions

## Branch & PR workflow

Always work on a feature branch, never commit directly to `main`.

1. At the start of each session, create a branch: `session/YYYY-MM-DD` (use today's date).
   - If a `session/YYYY-MM-DD` branch already exists for today, reuse it.
2. Commit changes to that branch as work progresses.
3. At the end of the session (or when asked to create a PR), push the branch and open a PR into `main` using `gh pr create`.
4. Write a PR title and body that explains what changed and why — include a short test plan.

## Project context

- **Stack**: Streamlit + Python (`app.py`), deployed on Render.
- **Design reference**: Zeronode-style layout — soft white canvas, electric cobalt blue blob, glassmorphism cards, Inter + Cormorant Garamond typography.
- **CSS approach**: all styles are injected via `st.markdown()` at the top of `app.py`. Keep the three-layer z-index hierarchy intact:
  - Layer 1 (z-0): background — `.zn-blob`, `.zn-grain`, `.zn-bottom-fade`
  - Layer 2 (z-10): left column — hero text, CTA buttons, brief form
  - Layer 3 (z-20): right column — badge pill, external pills, session, email

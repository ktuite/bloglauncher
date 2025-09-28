# Blog Launcher — fetch a single Mastodon toot

This small helper fetches a single public Mastodon status (a "toot") using the instance's public API.


Prerequisites
- Python 3.8+
- Install dependencies: pip install -r requirements.txt

Running scripts in this project

This project convention uses `uv` to run Python scripts because `uv` automatically activates a discovered `.venv` for you.

Examples (using uv):

-- Fetch and write a Markdown file with assets (no output-dir required):
  uv run fetch_toot_thread.py https://mastodon.social/@user/115260608425298248

Or, if you prefer to use a virtualenv manually:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python fetch_toot_thread.py https://mastodon.social/@user/115260608425298248
```

Notes
- This script only works for public toots (the instance must return the status via its unauthenticated API).
- `fetch_toot_thread.py` downloads media into an `assets/<status_id>/` folder next to the generated Markdown file and rewrites links accordingly.

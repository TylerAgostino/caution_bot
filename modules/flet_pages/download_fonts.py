"""
download_fonts.py
=================
Downloads the Saira font variants used by the OBS overlays into the
local ``fonts/`` directory so the overlays can serve them without
requiring an internet connection.

Run once from the project root (or from this directory):

    python modules/flet_pages/download_fonts.py

The overlay HTTP server already falls back to the Google Fonts CDN
automatically when the local files are absent, so this script is only
needed for fully-offline setups.
"""

import urllib.request
from pathlib import Path

FONTS_DIR = Path(__file__).parent / "fonts"

# Saira v23 – sourced from Google Fonts CDN (fonts.gstatic.com).
# If these URLs ever become stale, visit:
#   https://fonts.googleapis.com/css2?family=Saira:ital,wght@0,400;0,700;0,900;1,700&display=swap
# and copy the updated src URLs.
FONT_FILES = {
    "Saira-Black.ttf": (
        "https://fonts.gstatic.com/s/saira/v23/"
        "memWYa2wxmKQyPMrZX79wwYZQMhsyuShhKMjjbU9uXuA7_PFosg.ttf"
    ),
    "Saira-Bold.ttf": (
        "https://fonts.gstatic.com/s/saira/v23/"
        "memWYa2wxmKQyPMrZX79wwYZQMhsyuShhKMjjbU9uXuA773Fosg.ttf"
    ),
    "Saira-Regular.ttf": (
        "https://fonts.gstatic.com/s/saira/v23/"
        "memWYa2wxmKQyPMrZX79wwYZQMhsyuShhKMjjbU9uXuA71rCosg.ttf"
    ),
    "Saira-BoldItalic.ttf": (
        "https://fonts.gstatic.com/s/saira/v23/"
        "memUYa2wxmKQyNkiV50dulWP7s95AqZTzZHcVdxWI9WH-pKBrYwxkw.ttf"
    ),
}


def main() -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in FONT_FILES.items():
        dest = FONTS_DIR / filename
        if dest.exists():
            print(f"  [skip]  {filename} (already present)")
            continue
        print(f"  [fetch] {filename} ...", end=" ", flush=True)
        urllib.request.urlretrieve(url, dest)
        print(f"done ({dest.stat().st_size // 1024} KB)")
    print("\nAll fonts ready in:", FONTS_DIR)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build user guide PDF from HTML via headless Chrome (macOS)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

DOCS = Path(__file__).resolve().parent
HTML = DOCS / "Spread-System-v3-rukovodstvo.html"
PDF = DOCS / "Spread-System-v3-rukovodstvo.pdf"
DESKTOP = Path.home() / "Desktop" / "Spread-System-v3-rukovodstvo.pdf"

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def find_browser() -> str | None:
    for path in CHROME_CANDIDATES:
        if Path(path).is_file():
            return path
    return shutil.which("google-chrome") or shutil.which("chromium")


def main() -> None:
    if not HTML.is_file():
        raise SystemExit(f"Missing {HTML}")
    browser = find_browser()
    if not browser:
        raise SystemExit("Install Google Chrome or Edge to generate PDF.")
    subprocess.run(
        [
            browser,
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={PDF}",
            HTML.as_uri(),
        ],
        check=True,
    )
    shutil.copy2(PDF, DESKTOP)
    print(f"Wrote {PDF}")
    print(f"Copied to {DESKTOP}")


if __name__ == "__main__":
    main()

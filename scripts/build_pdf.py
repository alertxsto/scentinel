"""Generate the Scentinel project overview PDF from HTML.

Usage:
    .venv/bin/python scripts/build_pdf.py

Outputs docs/Scentinel_Project_Overview_V1.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

from weasyprint import HTML

ROOT = Path(__file__).resolve().parent.parent
HTML_SOURCE = ROOT / "docs" / "scentinel-overview.html"
PDF_TARGET = ROOT / "docs" / "Scentinel_Project_Overview_V1.pdf"


def main() -> int:
    if not HTML_SOURCE.exists():
        print(f"ERROR: {HTML_SOURCE} not found", file=sys.stderr)
        return 1
    HTML(str(HTML_SOURCE)).write_pdf(str(PDF_TARGET))
    print(f"[saved] {PDF_TARGET} ({PDF_TARGET.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

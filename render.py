"""Render each single-page PDF in config.PAGES_DIR to a PNG.

Usage: python render.py [--dpi 200]

The PNG name includes the DPI. A PNG that exists and is newer than its PDF is
not rendered again.
"""

import argparse
from pathlib import Path

import pymupdf

import config


def png_path(page_id: str, dpi: int) -> Path:
    return config.RENDER_DIR / f"{page_id}_{dpi}dpi.png"


def render_page(pdf_path: Path, dpi: int) -> Path:
    """Render the first page of pdf_path. Return the PNG path."""
    out = png_path(pdf_path.stem, dpi)
    if out.exists() and out.stat().st_mtime >= pdf_path.stat().st_mtime:
        return out
    config.RENDER_DIR.mkdir(exist_ok=True)
    with pymupdf.open(pdf_path) as doc:
        if doc.page_count != 1:
            print(f"WARNING: {pdf_path.name} has {doc.page_count} pages. Only page 1 is used.")
        doc[0].get_pixmap(dpi=dpi).save(out)
    return out


def render_all(dpi: int) -> list[Path]:
    return [render_page(pdf, dpi) for pdf in sorted(config.PAGES_DIR.glob("*.pdf"))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dpi", type=int, default=config.DEFAULT_DPI)
    args = parser.parse_args()
    paths = render_all(args.dpi)
    print(f"{len(paths)} PNG files in {config.RENDER_DIR}")


if __name__ == "__main__":
    main()

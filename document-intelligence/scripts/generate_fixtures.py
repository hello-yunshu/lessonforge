from __future__ import annotations

import json
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def native_text_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((60, 70), "Structured Document Baseline", fontsize=22)
    page.insert_text(
        (60, 115),
        "This page contains native text, a formula, a list, and a ruled table.",
        fontsize=11,
    )
    page.insert_text((60, 145), "Formula: E = mc^2", fontsize=12)
    page.insert_text((60, 175), "1. First item\n2. Second item\n3. Third item", fontsize=11)
    x0, y0, cell_w, cell_h = 60, 250, 140, 35
    for row in range(4):
        page.draw_line((x0, y0 + row * cell_h), (x0 + 3 * cell_w, y0 + row * cell_h))
    for col in range(4):
        page.draw_line((x0 + col * cell_w, y0), (x0 + col * cell_w, y0 + 3 * cell_h))
    values = [["Name", "Count", "Status"], ["Alpha", "12", "Ready"], ["Beta", "7", "Review"]]
    for row, cells in enumerate(values):
        for col, value in enumerate(cells):
            page.insert_text((x0 + col * cell_w + 8, y0 + row * cell_h + 22), value, fontsize=10)
    document.set_metadata({"title": "Native Text Fixture", "author": "document-intelligence"})
    document.save(path, garbage=4, deflate=True)
    document.close()


def scanned_image_pdf(path: Path, image_path: Path) -> None:
    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 80, 1120, 1520), outline="black", width=4)
    draw.text((140, 160), "SCANNED IMAGE DOCUMENT", fill="black")
    draw.text((140, 260), "There is no native PDF text layer on this page.", fill="black")
    draw.text((140, 360), "Invoice total: 125.00", fill="black")
    image.save(image_path)
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    page.insert_image(page.rect, filename=str(image_path))
    document.save(path, garbage=4, deflate=True)
    document.close()


def mixed_layout_pdf(path: Path, image_path: Path) -> None:
    image = Image.new("RGB", (320, 220), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((30, 25, 290, 195), outline="black", width=5)
    draw.line((55, 170, 265, 50), fill="black", width=4)
    draw.text((100, 95), "FIGURE", fill="black")
    image.save(image_path)
    document = fitz.open()
    page1 = document.new_page(width=595, height=842)
    page1.insert_text((55, 65), "Mixed Layout Report", fontsize=20)
    page1.insert_text((55, 110), "The figure below is embedded as an image asset.", fontsize=11)
    page1.insert_image(fitz.Rect(80, 160, 400, 380), filename=str(image_path))
    page1.insert_text((55, 430), "Figure 1. Synthetic geometry illustration.", fontsize=10)
    page2 = document.new_page(width=595, height=842)
    page2.insert_text((55, 65), "Continuation", fontsize=18)
    page2.insert_text((55, 110), "This second page verifies stable page ordering.", fontsize=11)
    document.save(path, garbage=4, deflate=True)
    document.close()


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    native_text_pdf(FIXTURES / "native_text.pdf")
    scanned_image_pdf(FIXTURES / "scanned_image.pdf", FIXTURES / "scanned_source.png")
    mixed_layout_pdf(FIXTURES / "mixed_layout.pdf", FIXTURES / "mixed_figure.png")
    manifest = {
        "version": 1,
        "fixtures": [
            {
                "file": "native_text.pdf",
                "family": "native-text-report",
                "expected_pages": 1,
                "expected_min_text_elements": 4,
            },
            {
                "file": "scanned_image.pdf",
                "family": "image-only-scan",
                "expected_pages": 1,
                "expected_warning": "EMPTY_NATIVE_TEXT",
            },
            {
                "file": "mixed_layout.pdf",
                "family": "mixed-text-image",
                "expected_pages": 2,
                "expected_min_images": 1,
            },
        ],
    }
    (FIXTURES / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()

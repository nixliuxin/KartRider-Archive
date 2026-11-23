#!/usr/bin/env python3
"""Build an accessible, reflowable EPUB 3 photo album from a JSON manifest."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree


LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
IMAGE_TYPES = {
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
}
XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"
DC_NS = "http://purl.org/dc/elements/1.1/"


class ManifestError(ValueError):
    """A user-facing validation error in a manifest or its images."""


@dataclass(frozen=True)
class AlbumEntry:
    title: str
    image_path: Path
    image_href: str
    alt: str
    caption: str
    source_url: str | None
    anchor: str


@dataclass(frozen=True)
class AlbumChapter:
    title: str
    entries: tuple[AlbumEntry, ...]
    filename: str
    anchor: str


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ManifestError(f"{field} must be a string")
    return value.strip()


def _local_image(root: Path, value: Any, field: str) -> tuple[Path, str]:
    relative = _required_text(value, field)
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ManifestError(f"{field} must stay inside the manifest folder: {relative}") from exc

    if not candidate.is_file():
        raise ManifestError(f"{field} does not exist or is not a file: {relative}")
    image_type = IMAGE_TYPES.get(candidate.suffix.lower())
    if image_type is None:
        raise ManifestError(f"{field} must be a JPEG or PNG image: {relative}")
    mime_type, signature = image_type
    try:
        with candidate.open("rb") as image_file:
            header = image_file.read(len(signature))
    except OSError as exc:
        raise ManifestError(f"Cannot read {field}: {relative}: {exc}") from exc
    if not header.startswith(signature):
        raise ManifestError(f"{field} extension does not match a valid {mime_type} image: {relative}")
    return candidate, mime_type


def _source_url(value: Any, field: str) -> str | None:
    if value is None or value == "":
        return None
    url = _required_text(value, field)
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ManifestError(f"{field} must be an http(s) URL")
    return url


def _read_manifest(
    path: Path,
) -> tuple[dict[str, Any], Path, list[AlbumChapter], tuple[Path, str], dict[Path, tuple[str, str]]]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"Cannot read JSON manifest {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ManifestError("The manifest root must be a JSON object")

    title = _required_text(manifest.get("title"), "title")
    language = _required_text(manifest.get("language"), "language")
    if not LANGUAGE_RE.fullmatch(language):
        raise ManifestError("language must be a BCP 47 language tag, such as en, zh-TW, or ko")
    root = path.resolve().parent
    raw_chapters = manifest.get("chapters")
    if raw_chapters is None and isinstance(manifest.get("items"), list):
        raw_chapters = [{"title": "Album", "items": manifest["items"]}]
    if not isinstance(raw_chapters, list) or not raw_chapters:
        raise ManifestError("chapters must be a non-empty array (or provide a non-empty items array)")

    chapters: list[AlbumChapter] = []
    image_paths: dict[Path, tuple[str, str]] = {}
    entry_number = 0
    for chapter_index, raw_chapter in enumerate(raw_chapters, start=1):
        if not isinstance(raw_chapter, dict):
            raise ManifestError(f"chapters[{chapter_index - 1}] must be an object")
        chapter_title = _required_text(raw_chapter.get("title"), f"chapters[{chapter_index - 1}].title")
        raw_entries = raw_chapter.get("items")
        if not isinstance(raw_entries, list) or not raw_entries:
            raise ManifestError(f"Chapter {chapter_title!r} must have a non-empty items array")
        entries: list[AlbumEntry] = []
        for item_index, raw_entry in enumerate(raw_entries, start=1):
            if not isinstance(raw_entry, dict):
                raise ManifestError(f"{chapter_title}: item {item_index} must be an object")
            item_title = _required_text(raw_entry.get("title"), f"{chapter_title}: item {item_index} title")
            image_path, mime_type = _local_image(
                root, raw_entry.get("image"), f"{chapter_title}: item {item_index} image"
            )
            if image_path not in image_paths:
                image_number = len(image_paths) + 1
                extension = ".jpg" if mime_type == "image/jpeg" else ".png"
                image_href = f"images/image-{image_number:04d}{extension}"
                image_paths[image_path] = (image_href, mime_type)
            alt = _required_text(raw_entry.get("alt"), f"{chapter_title}: item {item_index} alt")
            caption = _optional_text(raw_entry.get("caption"), f"{chapter_title}: item {item_index} caption")
            source_url = _source_url(
                raw_entry.get("source_url"), f"{chapter_title}: item {item_index} source_url"
            )
            entry_number += 1
            entries.append(
                AlbumEntry(
                    title=item_title,
                    image_path=image_path,
                    image_href=image_paths[image_path][0],
                    alt=alt,
                    caption=caption,
                    source_url=source_url,
                    anchor=f"item-{entry_number:04d}",
                )
            )
        chapters.append(
            AlbumChapter(
                title=chapter_title,
                entries=tuple(entries),
                filename=f"chapter-{chapter_index:03d}.xhtml",
                anchor=f"chapter-{chapter_index:03d}",
            )
        )

    raw_cover = manifest.get("cover")
    if raw_cover:
        cover = _local_image(root, raw_cover, "cover")
    else:
        first_entry = chapters[0].entries[0]
        cover = (first_entry.image_path, IMAGE_TYPES[first_entry.image_path.suffix.lower()][0])
    if cover[0] not in image_paths:
        image_number = len(image_paths) + 1
        extension = ".jpg" if cover[1] == "image/jpeg" else ".png"
        image_paths[cover[0]] = (f"images/image-{image_number:04d}{extension}", cover[1])
    normalized = {
        "title": title,
        "language": language,
        "creator": _optional_text(manifest.get("creator"), "creator"),
        "description": _optional_text(manifest.get("description"), "description"),
        "cover_alt": _optional_text(manifest.get("cover_alt"), "cover_alt"),
    }
    return normalized, root, chapters, cover, image_paths


def _language_label(language: str) -> str:
    if language.lower().startswith("zh-tw"):
        return "開啟原始卡片"
    if language.lower().startswith("zh"):
        return "查看原卡片"
    if language.lower().startswith("ko"):
        return "원본 카드 보기"
    return "View source card"


def _xhtml(title: str, language: str, body: str, *, stylesheet: str = "styles/book.css") -> str:
    lang = html.escape(language, quote=True)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<html xmlns="{XHTML_NS}" xmlns:epub="{EPUB_NS}" lang="{lang}" xml:lang="{lang}">\n'
        "<head>\n"
        '  <meta charset="utf-8"/>\n'
        f"  <title>{html.escape(title)}</title>\n"
        f'  <link rel="stylesheet" type="text/css" href="{stylesheet}"/>\n'
        "</head>\n"
        f"<body>\n{body}\n</body>\n</html>\n"
    )


def _cover_page(metadata: dict[str, str], cover_href: str) -> str:
    alt = html.escape(metadata["cover_alt"], quote=True)
    body = (
        '<section epub:type="cover" class="cover">\n'
        f'  <img class="cover-image" src="../{html.escape(cover_href, quote=True)}" alt="{alt}"/>\n'
        f'  <h1>{html.escape(metadata["title"])}</h1>\n'
        + (f'  <p class="creator">{html.escape(metadata["creator"])}</p>\n' if metadata["creator"] else "")
        + (f'  <p>{html.escape(metadata["description"])}</p>\n' if metadata["description"] else "")
        + "</section>"
    )
    return _xhtml(metadata["title"], metadata["language"], body)


def _nav_page(metadata: dict[str, str], chapters: list[AlbumChapter]) -> str:
    entries = []
    for chapter in chapters:
        items = "".join(
            f'<li><a href="{chapter.filename}#{entry.anchor}">{html.escape(entry.title)}</a></li>'
            for entry in chapter.entries
        )
        entries.append(
            f'<li><a href="{chapter.filename}#{chapter.anchor}">{html.escape(chapter.title)}</a>'
            f"<ol>{items}</ol></li>"
        )
    body = '<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>' + "".join(entries) + "</ol></nav>"
    return _xhtml("Contents", metadata["language"], body)


def _chapter_page(metadata: dict[str, str], chapter: AlbumChapter) -> str:
    section = [
        f'<section epub:type="chapter" id="{chapter.anchor}">',
        f"  <h1>{html.escape(chapter.title)}</h1>",
    ]
    link_label = _language_label(metadata["language"])
    for entry in chapter.entries:
        section.extend(
            [
                f'  <section class="entry" id="{entry.anchor}">',
                f"    <h2>{html.escape(entry.title)}</h2>",
                "    <figure>",
                f'      <img src="../{html.escape(entry.image_href, quote=True)}" alt="{html.escape(entry.alt, quote=True)}"/>',
                "      <figcaption>",
                f"        <p>{html.escape(entry.caption or entry.title)}</p>",
                (
                    f'        <p class="source"><a href="{html.escape(entry.source_url, quote=True)}">'
                    f"{link_label}</a></p>"
                    if entry.source_url
                    else ""
                ),
                "      </figcaption>",
                "    </figure>",
                "  </section>",
            ]
        )
    section.append("</section>")
    return _xhtml(chapter.title, metadata["language"], "\n".join(section))


def _package_opf(
    metadata: dict[str, str], chapters: list[AlbumChapter], cover_href: str, image_paths: dict[Path, tuple[str, str]]
) -> str:
    stable = json.dumps(metadata, ensure_ascii=False, sort_keys=True).encode("utf-8")
    identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, hashlib.sha256(stable).hexdigest()))
    title = html.escape(metadata["title"])
    language = html.escape(metadata["language"])
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cover_id = next(image_id for image_id, (href, _mime) in enumerate(image_paths.values(), 1) if href == cover_href)

    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="styles" href="styles/book.css" media-type="text/css"/>',
        '<item id="cover-page" href="cover.xhtml" media-type="application/xhtml+xml"/>',
    ]
    manifest.extend(
        f'<item id="{image_id}" href="{html.escape(href, quote=True)}" media-type="{mime}"'
        + (' properties="cover-image"' if image_id == f"image-{cover_id:04d}" else "")
        + "/>"
        for image_id, (href, mime) in (
            (f"image-{index:04d}", item) for index, item in enumerate(image_paths.values(), 1)
        )
    )
    manifest.extend(
        f'<item id="chapter-{index:03d}" href="{chapter.filename}" media-type="application/xhtml+xml"/>'
        for index, chapter in enumerate(chapters, start=1)
    )
    spine = ['<itemref idref="cover-page"/>', '<itemref idref="nav"/>'] + [
        f'<itemref idref="chapter-{index:03d}"/>' for index in range(1, len(chapters) + 1)
    ]
    creator = f"<dc:creator>{html.escape(metadata['creator'])}</dc:creator>" if metadata["creator"] else ""
    description = (
        f"<dc:description>{html.escape(metadata['description'])}</dc:description>" if metadata["description"] else ""
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id" '
        'prefix="rendition: http://www.idpf.org/vocab/rendition/#">\n'
        "  <metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\">\n"
        f"    <dc:identifier id=\"pub-id\">urn:uuid:{identifier}</dc:identifier>\n"
        f"    <dc:title>{title}</dc:title>\n"
        f"    <dc:language>{language}</dc:language>\n"
        f"    {creator}\n"
        f"    {description}\n"
        f"    <meta property=\"dcterms:modified\">{modified}</meta>\n"
        "    <meta property=\"rendition:layout\">reflowable</meta>\n"
        "  </metadata>\n"
        "  <manifest>\n    "
        + "\n    ".join(manifest)
        + "\n  </manifest>\n  <spine page-progression-direction=\"ltr\">\n    "
        + "\n    ".join(spine)
        + "\n  </spine>\n</package>\n"
    )


def _css() -> str:
    return """/* Reflowable layout: readers control text size, margins, and color mode. */
body { font-family: serif; line-height: 1.55; margin: 0; padding: 0 0.4em; }
h1, h2 { line-height: 1.25; }
figure { margin: 1.25em 0; text-align: center; }
figure img { display: block; height: auto; margin: 0 auto; max-height: 82vh; max-width: 100%; object-fit: contain; }
figcaption { margin: 0.75em auto; max-width: 42em; text-align: start; }
.entry { break-before: page; page-break-before: always; }
.entry:first-of-type { break-before: auto; page-break-before: auto; }
.source { font-size: 0.9em; }
.cover { display: flex; flex-direction: column; justify-content: center; min-height: 80vh; text-align: center; }
.cover-image { height: auto; max-height: 65vh; max-width: 100%; object-fit: contain; }
.creator { font-style: italic; }
"""


def build_epub(manifest_path: Path, output_path: Path) -> Path:
    """Validate a manifest, then write an EPUB 3 file at ``output_path``."""
    metadata, _root, chapters, cover, image_paths = _read_manifest(manifest_path)
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(output_path.name + ".tmp")
    try:
        with zipfile.ZipFile(temporary_path, "w") as book:
            # EPUB readers require this exact, uncompressed entry to be first.
            book.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            book.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
                '<rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/>'
                "</rootfiles></container>",
                compress_type=zipfile.ZIP_DEFLATED,
            )
            book.writestr("OEBPS/styles/book.css", _css(), compress_type=zipfile.ZIP_DEFLATED)
            cover_href, _cover_mime = image_paths[cover[0]]
            book.writestr(
                "OEBPS/cover.xhtml",
                _cover_page(metadata, cover_href),
                compress_type=zipfile.ZIP_DEFLATED,
            )
            book.writestr(
                "OEBPS/nav.xhtml", _nav_page(metadata, chapters), compress_type=zipfile.ZIP_DEFLATED
            )
            for chapter in chapters:
                book.writestr(
                    f"OEBPS/{chapter.filename}",
                    _chapter_page(metadata, chapter),
                    compress_type=zipfile.ZIP_DEFLATED,
                )
            for image_index, (image_path, (image_href, _mime)) in enumerate(image_paths.items(), start=1):
                book.write(image_path, f"OEBPS/{image_href}", compress_type=zipfile.ZIP_DEFLATED)
            book.writestr(
                "OEBPS/package.opf",
                _package_opf(metadata, chapters, cover_href, image_paths),
                compress_type=zipfile.ZIP_DEFLATED,
            )
        # Basic package integrity and XML well-formedness checks before publishing the file.
        with zipfile.ZipFile(temporary_path) as book:
            names = book.namelist()
            if not names or names[0] != "mimetype" or book.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
                raise ManifestError("Internal error: invalid EPUB mimetype entry")
            for xml_name in ["META-INF/container.xml", "OEBPS/package.opf", "OEBPS/cover.xhtml", "OEBPS/nav.xhtml"]:
                ElementTree.fromstring(book.read(xml_name))
            for chapter in chapters:
                ElementTree.fromstring(book.read(f"OEBPS/{chapter.filename}"))
        os.replace(temporary_path, output_path)
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create an accessible, reflowable EPUB 3 photo album.")
    parser.add_argument("manifest", type=Path, help="Path to the JSON album manifest")
    parser.add_argument("-o", "--output", required=True, type=Path, help="Output .epub file")
    arguments = parser.parse_args(argv)
    try:
        result = build_epub(arguments.manifest, arguments.output)
    except (ManifestError, OSError, zipfile.BadZipFile) as exc:
        print(f"EPUB export failed: {exc}", file=sys.stderr)
        return 1
    print(f"Created {result} ({result.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

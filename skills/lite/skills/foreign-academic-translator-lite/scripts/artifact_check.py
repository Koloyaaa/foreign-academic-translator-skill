#!/usr/bin/env python3
"""Check that selected translation outputs exist and are minimally readable.

This is a file/container check only. It does not assess translation fidelity,
coverage, correctness, or visual quality.
"""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
import sys
import zipfile
import xml.etree.ElementTree as ET


class BasicHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.seen_document_root = False
        self.seen_body = False
        self.seen_text = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "html":
            self.seen_document_root = True
        elif tag.lower() == "body":
            self.seen_body = True

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.seen_text = True


def check_markdown(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ValueError("Markdown contains no readable text")
    return "UTF-8 text is readable and non-empty"


def check_html(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    parser = BasicHTMLParser()
    parser.feed(text)
    parser.close()
    if not parser.seen_document_root or not parser.seen_body:
        raise ValueError("expected an HTML document with html and body elements")
    if not parser.seen_text:
        raise ValueError("HTML body contains no readable text")
    return "UTF-8 HTML parsed and contains readable text"


def check_docx(path: Path) -> str:
    if not zipfile.is_zipfile(path):
        raise ValueError("DOCX is not a readable ZIP package")
    with zipfile.ZipFile(path) as archive:
        corrupt_member = archive.testzip()
        if corrupt_member is not None:
            raise ValueError(f"corrupt DOCX package member: {corrupt_member}")
        required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
        missing = required.difference(archive.namelist())
        if missing:
            raise ValueError("DOCX package is missing " + ", ".join(sorted(missing)))
        content_types = None
        relationships = None
        for member in sorted(required):
            root = ET.fromstring(archive.read(member))
            local_name = root.tag.rsplit("}", 1)[-1]
            if member == "[Content_Types].xml":
                if local_name != "Types":
                    raise ValueError("[Content_Types].xml has no Types root element")
                content_types = root
            elif member == "_rels/.rels":
                if local_name != "Relationships":
                    raise ValueError("_rels/.rels has no Relationships root element")
                relationships = root
            elif member == "word/document.xml":
                if local_name != "document":
                    raise ValueError("word/document.xml has no document root element")
                body = next((item for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "body"), None)
                if body is None:
                    raise ValueError("word/document.xml has no body element")
        main_content_type = any(
            element.tag.rsplit("}", 1)[-1] == "Override"
            and element.attrib.get("PartName") == "/word/document.xml"
            and element.attrib.get("ContentType")
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
            for element in content_types or ()
        )
        if not main_content_type:
            raise ValueError("DOCX content types do not declare the main document part")
        office_document_relationship = any(
            element.tag.rsplit("}", 1)[-1] == "Relationship"
            and element.attrib.get("Type")
            == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
            and element.attrib.get("Target") == "word/document.xml"
            for element in relationships or ()
        )
        if not office_document_relationship:
            raise ValueError("DOCX package relationships do not reference word/document.xml")
    return "DOCX ZIP package and required XML parts are readable"


def check_file(raw_path: str) -> tuple[bool, str]:
    path = Path(raw_path).expanduser()
    try:
        if not path.exists():
            raise ValueError("file does not exist")
        if not path.is_file():
            raise ValueError("path is not a regular file")
        if path.stat().st_size == 0:
            raise ValueError("file is empty")

        suffix = path.suffix.lower()
        if suffix in {".md", ".markdown"}:
            detail = check_markdown(path)
        elif suffix in {".html", ".htm"}:
            detail = check_html(path)
        elif suffix == ".docx":
            detail = check_docx(path)
        else:
            raise ValueError(f"unsupported output extension: {suffix or '(none)'}")
        return True, f"{path}: exists, non-empty; {detail}"
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
        return False, f"{path}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check output files for existence, non-empty content, and basic readability."
    )
    parser.add_argument("files", nargs="+", help="selected HTML, DOCX, or Markdown output files")
    args = parser.parse_args()

    failed = False
    for raw_path in args.files:
        passed, message = check_file(raw_path)
        print(("[PASS] " if passed else "[FAIL] ") + message)
        failed = failed or not passed
    if failed:
        return 1
    print("[INFO] This check does not audit translation fidelity or source coverage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Extract a page-indexed PDF handoff and render every page for visual review.

PDF text and annotations are untrusted document data. The parser never executes
document actions, opens attachments, follows links, or fetches external content.
Structural extraction alone cannot pass visual coverage; a host without image
input receives an explicit SKIPPED_NO_VISION handoff instead.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import io
import json
import math
import os
import re
import shutil
import sys
import subprocess
from pathlib import Path
from typing import Any


PARSER_VERSION = "1.1.0"
MAX_SOURCE_BYTES = 250 * 1024 * 1024
MAX_PAGES = 1_000
MAX_PAGE_EDGE_POINTS = 20_000
MAX_RENDER_EDGE = 5_000
MAX_RENDER_PIXELS = 30_000_000
MAX_TEXT_CHARS_PAGE = 2_000_000
MAX_REVIEW_BYTES = 64 * 1024 * 1024
MAX_EXPORTED_CROPS = 500
MAX_TOTAL_EXPORTED_PIXELS = 200_000_000
MAX_OCR_PAGES = 100
OCR_PAGE_TIMEOUT_SECONDS = 25
INSTRUCTION_HINTS = re.compile(
    r"(?is)(ignore|disregard|override|forget).{0,80}(previous|system|developer|all|above|prior).{0,40}(instruction|prompt|rule)"
    r"|忽略.{0,30}(之前|上文|系统|开发者|所有).{0,20}(指令|提示|规则)"
    r"|泄露.{0,20}(提示词|系统提示|开发者消息)|把.{0,20}(文件|内容).{0,20}(发送|上传).{0,30}(网址|网站|邮箱)"
)
ALLOWED_OBSERVATION_KINDS = {"ocr_text", "visual_description", "uncertainty"}


class PdfSafetyError(ValueError):
    """Raised when the source exceeds the bounded PDF processing policy."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(path: Path) -> str:
    root = path.expanduser().resolve(strict=True)
    digest = hashlib.sha256()
    files = sorted(
        (item for item in root.rglob("*") if item.is_file() and "__pycache__" not in item.parts and item.suffix.lower() != ".pyc"),
        key=lambda item: item.relative_to(root).as_posix().casefold(),
    )
    for item in files:
        digest.update(item.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(item)))
    return digest.hexdigest()


def _version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _atomic_write(path: Path, content: str | bytes) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    encoding = None if isinstance(content, bytes) else "utf-8"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open(mode, encoding=encoding, newline="" if encoding else None) as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _same_or_child(path: Path, parent: Path) -> bool:
    path, parent = path.resolve(), parent.resolve()
    return path == parent or parent in path.parents


def _safe_outputs(source: Path, outputs: list[Path], visual_root: Path, image_dir: Path | None) -> None:
    normalized = [item.expanduser().resolve() for item in outputs]
    if source in normalized or len({os.path.normcase(str(item)) for item in normalized}) != len(normalized):
        raise ValueError("PDF outputs must be distinct and cannot overwrite the source")
    if any(_same_or_child(item, visual_root) for item in normalized):
        raise ValueError("Manifest and text outputs must be outside the temporary visual-assets directory")
    if _same_or_child(source, visual_root) or visual_root == source.parent:
        raise ValueError("Temporary visual-assets directory must be separate from the source tree")
    if image_dir is not None:
        image_dir = image_dir.expanduser().resolve()
        if image_dir == source.parent or _same_or_child(source, image_dir):
            raise ValueError("Formal image directory cannot contain the source PDF")
        if image_dir == visual_root or _same_or_child(image_dir, visual_root) or _same_or_child(visual_root, image_dir):
            raise ValueError("Formal image directory and temporary visual-assets directory must be separate")
        if any(_same_or_child(item, image_dir) for item in normalized):
            raise ValueError("Manifest and text outputs must be outside the formal image directory")


def _text_lines(page: Any) -> tuple[list[dict[str, Any]], str | None]:
    """Get stable coordinate-bearing text lines, with a fallback for older pdfplumber."""
    try:
        raw_lines = page.extract_text_lines(layout=False, strip=True)
        lines = []
        for line in raw_lines:
            text = str(line.get("text", "")).strip()
            if text:
                lines.append({
                    "text": text,
                    "x0": float(line.get("x0", 0) or 0),
                    "top": float(line.get("top", 0) or 0),
                    "x1": float(line.get("x1", 0) or 0),
                    "bottom": float(line.get("bottom", line.get("top", 0)) or 0),
                })
        return lines, None
    except Exception as exc:
        try:
            fallback = page.extract_text() or ""
            lines = [{"text": line.strip(), "x0": None, "top": None, "x1": None, "bottom": None}
                     for line in fallback.splitlines() if line.strip()]
            return lines, f"Coordinate-aware text extraction failed; used line fallback: {type(exc).__name__}"
        except Exception as fallback_exc:
            return [], f"Text extraction failed: {type(fallback_exc).__name__}"


def _table_records(page: Any, page_number: int, width: float, height: float) -> tuple[list[dict[str, Any]], list[tuple[float, float, float, float]]]:
    """Extract clearly detected tables while keeping their source coordinates."""
    records: list[dict[str, Any]] = []
    boxes: list[tuple[float, float, float, float]] = []
    try:
        tables = page.find_tables()
    except Exception:
        return records, boxes
    for index, table in enumerate(tables, start=1):
        try:
            x0, top, x1, bottom = (float(value) for value in table.bbox)
            rows = table.extract()
            normalized = [[str(cell or "").strip().replace("\n", "<br>") for cell in row] for row in rows]
            normalized = [row for row in normalized if any(row)]
            if not normalized:
                continue
            columns = max(len(row) for row in normalized)
            area_fraction = max(0.0, x1 - x0) * max(0.0, bottom - top) / max(1.0, width * height)
            # A page border is commonly misread as a one-column table. Keep the
            # source text lines unless there is a compact, multi-column table.
            if columns < 2 or area_fraction >= 0.80:
                continue
            normalized = [row + [""] * (columns - len(row)) for row in normalized]
            escape = lambda value: value.replace("|", "\\|")
            table_text = "| " + " | ".join(escape(value) for value in normalized[0]) + " |\n"
            table_text += "| " + " | ".join("---" for _ in range(columns)) + " |\n"
            table_text += "\n".join("| " + " | ".join(escape(value) for value in row) + " |" for row in normalized[1:])
            clipped = _clip_box(x0, top, x1, bottom, width, height)
            records.append({
                "object_id": f"PDF_PAGE:{page_number}:TABLE:{index:03d}", "kind": "table", "source": "pdf_table",
                "text": table_text, "rows": normalized, "confidence": None,
                "instruction_like_content": bool(INSTRUCTION_HINTS.search(table_text)), "uncertainty": None,
                "bounds": clipped,
            })
            boxes.append((x0, top, x1, bottom))
        except Exception:
            continue
    return records, boxes


def _clip_box(x0: float, top: float, x1: float, bottom: float, width: float, height: float) -> dict[str, float]:
    cx0, ctop = min(max(x0, 0.0), width), min(max(top, 0.0), height)
    cx1, cbottom = min(max(x1, 0.0), width), min(max(bottom, 0.0), height)
    return {"x0": round(cx0, 3), "top": round(ctop, 3), "x1": round(max(cx0, cx1), 3), "bottom": round(max(ctop, cbottom), 3)}


def _page_actions(reader: Any, page: Any) -> dict[str, Any]:
    """Record active-content metadata without following or executing targets."""
    result: dict[str, Any] = {"annotation_count": 0, "action_types": [], "target_hashes": [], "instruction_like_annotation": False}
    try:
        for annotation_ref in page.get("/Annots", []):
            result["annotation_count"] += 1
            annotation = annotation_ref.get_object() if hasattr(annotation_ref, "get_object") else annotation_ref
            action = annotation.get("/A")
            if action is not None:
                action = action.get_object() if hasattr(action, "get_object") else action
                action_type = str(action.get("/S", "unknown"))
                result["action_types"].append(action_type)
                for key in ("/URI", "/F", "/JS", "/T"):
                    value = action.get(key)
                    if value is not None:
                        encoded = str(value).encode("utf-8", "replace")
                        result["target_hashes"].append(hashlib.sha256(encoded).hexdigest())
                annotation_text = " ".join(str(annotation.get(key, "")) for key in ("/Contents", "/T", "/Subj"))
                if INSTRUCTION_HINTS.search(annotation_text):
                    result["instruction_like_annotation"] = True
    except Exception as exc:
        result["inspection_error"] = type(exc).__name__
    result["action_types"] = sorted(set(result["action_types"]))
    result["target_hashes"] = sorted(set(result["target_hashes"]))
    return result


def _ocr_engine(language: str) -> tuple[str | None, dict[str, Any]]:
    executable = shutil.which("tesseract")
    info: dict[str, Any] = {"engine": "tesseract", "status": "unavailable", "language": language,
                            "version": None, "pages_attempted": 0, "pages_with_text": 0}
    if executable is None:
        return None, info
    try:
        version_result = subprocess.run([executable, "--version"], capture_output=True, text=True,
                                        timeout=10, check=False)
        info["version"] = (version_result.stdout or version_result.stderr).splitlines()[0][:200]
        languages_result = subprocess.run([executable, "--list-langs"], capture_output=True,
                                          text=True, timeout=10, check=False)
        available = {line.strip() for line in languages_result.stdout.splitlines()[1:] if line.strip()}
        requested = [value.strip() for value in language.split("+") if value.strip()]
        if languages_result.returncode != 0 or not requested or not set(requested) <= available:
            info["status"] = "language_unavailable"
            info["available_languages"] = sorted(available)
            return None, info
        tessdata_result = subprocess.run([executable, "--print-tessdata-dir"], capture_output=True,
                                         text=True, timeout=10, check=False)
        tessdata_value = tessdata_result.stdout.strip()
        tessdata_dir = Path(tessdata_value).expanduser() if tessdata_result.returncode == 0 and tessdata_value else None
        info["language_data_sha256"] = {
            language_code: sha256_file(tessdata_dir / f"{language_code}.traineddata")
            if tessdata_dir and (tessdata_dir / f"{language_code}.traineddata").is_file() else None
            for language_code in requested
        }
        info["tessdata_dir_available"] = bool(tessdata_dir and tessdata_dir.is_dir())
        info["status"] = "ready"
        info["available_languages"] = sorted(available)
        return executable, info
    except (OSError, IndexError, subprocess.TimeoutExpired) as exc:
        info["status"] = "inspection_failed"
        info["error"] = type(exc).__name__
        return None, info


def _ocr_page(executable: str, image_path: Path, language: str) -> tuple[str, float | None, str | None]:
    """Return OCR text as untrusted review data; never treat it as verified source."""
    import subprocess

    try:
        result = subprocess.run([executable, str(image_path), "stdout", "-l", language, "--psm", "6", "tsv"],
                                capture_output=True, text=True, timeout=OCR_PAGE_TIMEOUT_SECONDS, check=False)
        if result.returncode != 0:
            return "", None, "tesseract_failed"
        reader = csv.DictReader(io.StringIO(result.stdout), delimiter="\t")
        words: list[str] = []
        confidences: list[float] = []
        for row in reader:
            if row.get("level") != "5":
                continue
            word = str(row.get("text", "")).strip()
            if not word:
                continue
            words.append(word)
            try:
                confidence = float(row.get("conf", ""))
                if confidence >= 0:
                    confidences.append(confidence / 100.0)
            except (TypeError, ValueError):
                pass
        text = " ".join(words).strip()
        confidence = sum(confidences) / len(confidences) if confidences else None
        return text, confidence, None
    except subprocess.TimeoutExpired:
        return "", None, "tesseract_timeout"
    except OSError as exc:
        return "", None, f"tesseract_error:{type(exc).__name__}"


def _document_actions(reader: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"open_action_present": False, "additional_actions_present": False,
                              "javascript_names_present": False, "embedded_files_present": False,
                              "actions_executed": False, "attachments_opened": False, "links_followed": False}
    try:
        root = reader.trailer["/Root"].get_object()
        result["open_action_present"] = root.get("/OpenAction") is not None
        result["additional_actions_present"] = root.get("/AA") is not None
        names = root.get("/Names")
        if names is not None:
            names = names.get_object() if hasattr(names, "get_object") else names
            result["javascript_names_present"] = names.get("/JavaScript") is not None
            result["embedded_files_present"] = names.get("/EmbeddedFiles") is not None
    except Exception as exc:
        result["inspection_error"] = type(exc).__name__
    return result


def _render_page(pdfium_page: Any, target: Path) -> dict[str, Any]:
    from PIL import Image

    width, height = float(pdfium_page.get_width()), float(pdfium_page.get_height())
    if width <= 0 or height <= 0 or max(width, height) > MAX_PAGE_EDGE_POINTS:
        raise PdfSafetyError("PDF page has invalid or excessive dimensions")
    scale = min(2.0, MAX_RENDER_EDGE / max(width, height), math.sqrt(MAX_RENDER_PIXELS / (width * height)))
    scale = max(0.25, scale)
    bitmap = pdfium_page.render(scale=scale)
    image = bitmap.to_pil()
    if not isinstance(image, Image.Image):
        raise RuntimeError("PDFium did not return a valid page image")
    if image.width * image.height > MAX_RENDER_PIXELS or max(image.size) > MAX_RENDER_EDGE:
        raise PdfSafetyError("Rendered PDF page exceeds the pixel bounds")
    target.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(target, format="PNG", optimize=True)
    return {"path": str(target.resolve()), "width_px": image.width, "height_px": image.height,
            "scale": round(scale, 4), "status": "rendered"}


def _image_records(page: Any, page_number: int, width: float, height: float) -> list[dict[str, Any]]:
    records = []
    for index, image in enumerate(page.images, start=1):
        try:
            x0, top = float(image.get("x0", 0)), float(image.get("top", 0))
            x1, bottom = float(image.get("x1", x0)), float(image.get("bottom", top))
            if not all(math.isfinite(value) for value in (x0, top, x1, bottom)):
                continue
            original_area = max(0.0, x1 - x0) * max(0.0, bottom - top)
            clipped = _clip_box(x0, top, x1, bottom, width, height)
            clipped_area = max(0.0, clipped["x1"] - clipped["x0"]) * max(0.0, clipped["bottom"] - clipped["top"])
            page_area = max(1.0, width * height)
            stream = image.get("stream")
            soft_mask = bool(stream and stream.get("SMask"))
            image_mask = bool(image.get("imagemask"))
            full_page = clipped_area / page_area >= 0.80
            outside = original_area > 0 and clipped_area / original_area < 0.80
            object_id = f"PDF_PAGE:{page_number}:IMAGE:{index:03d}"
            records.append({
                "object_id": object_id, "kind": "image_placement", "source": "pdf_image_xobject",
                "text": "", "confidence": None, "instruction_like_content": False, "uncertainty": None,
                "bounds": clipped,
                "original_bounds": {"x0": round(x0, 3), "top": round(top, 3), "x1": round(x1, 3), "bottom": round(bottom, 3)},
                "area_fraction": round(clipped_area / page_area, 6), "soft_mask": soft_mask, "image_mask": image_mask,
                "background_or_full_page_candidate": full_page or outside or soft_mask or image_mask,
                "outside_page_candidate": outside,
                "source_pixel_size": list(image.get("srcsize") or []),
                "asset_path": None, "output_asset_path": None,
            })
        except Exception:
            continue
    return records


def _page_metrics(items: list[dict[str, Any]], page: Any, text_chars: int) -> dict[str, Any]:
    image_items = [item for item in items if item["kind"] == "image_placement"]
    vector_count = len(getattr(page, "curves", []) or []) + len(getattr(page, "rects", []) or [])
    substantial_images = [item for item in image_items if item["area_fraction"] >= 0.03 and item["area_fraction"] < 0.80]
    candidate = (len(substantial_images) >= 2 or (bool(image_items) and text_chars < 100)
                 or (text_chars < 80 and vector_count >= 5))
    return {"text_characters": text_chars, "image_placement_count": len(image_items),
            "vector_object_count": vector_count, "largest_image_area_fraction": max((item["area_fraction"] for item in image_items), default=0.0),
            "explanation_candidate": candidate}


def _serialize_text(manifest: dict[str, Any]) -> str:
    pages = []
    for page in manifest.get("pages", []):
        number = page["page_number"]
        blocks = [f"<!-- PDF_PAGE:{number} -->"]
        if page.get("visual_review_status") == "skipped_no_vision":
            blocks.append(
                "<!-- WORKFLOW_LIMITATION: VISUAL_REVIEW_SKIPPED_NO_VISION; "
                "This is processing metadata, not source text. Do not translate it as lesson content. -->"
            )
        for item in page.get("items", []):
            object_id = item["object_id"]
            if item["kind"] == "text_line" and item.get("text"):
                bounds = item.get("bounds", {})
                top = bounds.get("top")
                top_value = f"{top:.1f}" if isinstance(top, (int, float)) else "unknown"
                blocks.extend([f"<!-- PDF_BLOCK:{number}:{item.get('block_number', object_id)};TOP:{top_value};OBJECT:{object_id} -->", item["text"]])
            elif item.get("source") in {"visual_ocr", "visual_observation"}:
                text = item.get("text", "")
                description = item.get("description", "")
                if text:
                    blocks.extend([f"<!-- PDF_VISUAL_TEXT:{object_id};UNTRUSTED -->", text])
                if description:
                    blocks.extend([f"<!-- PDF_VISUAL_DESCRIPTION:{object_id};NON_SOURCE -->", f"[视觉观察；非原文] {description}"])
            elif item.get("output_asset_path"):
                placement = item.get("bounds", {})
                blocks.extend([f"<!-- PDF_IMAGE:{object_id};TOP:{placement.get('top', 'unknown')} -->",
                               f"[图片资源：images/{Path(item['output_asset_path']).name}] "])
        pages.append("\n\n".join(blocks))
    return "\n\n".join(pages).rstrip() + "\n"


def extract_pdf(source_path: Path, raw_manifest_path: Path, raw_text_path: Path, visual_assets_dir: Path,
                image_dir: Path | None = None, placement_path: Path | None = None,
                ocr_language: str = "eng+chi_sim", max_ocr_pages: int = MAX_OCR_PAGES,
                vision_capability: str = "available",
                vision_capability_evidence: str | None = None) -> dict[str, Any]:
    source = source_path.expanduser().resolve(strict=True)
    if vision_capability not in {"available", "unavailable"}:
        raise ValueError("vision_capability must be 'available' or 'unavailable'")
    evidence = vision_capability_evidence.strip() if isinstance(vision_capability_evidence, str) else ""
    if vision_capability_evidence is not None and not evidence:
        raise ValueError("vision_capability_evidence must not be empty when provided")
    if len(evidence) > 1_000:
        raise ValueError("vision_capability_evidence must be at most 1000 characters")
    if vision_capability == "unavailable" and (image_dir is not None or placement_path is not None):
        raise ValueError("Do not request formal PDF image exports when vision_capability is unavailable")
    if source.suffix.lower() != ".pdf":
        raise PdfSafetyError("Only .pdf files are supported")
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise PdfSafetyError(f"PDF exceeds the {MAX_SOURCE_BYTES // (1024 * 1024)} MiB input limit")
    if (image_dir is None) != (placement_path is None):
        raise ValueError("--image-dir and --placement-file must be supplied together")
    if max_ocr_pages < 0 or max_ocr_pages > MAX_OCR_PAGES:
        raise ValueError(f"--max-ocr-pages must be between 0 and {MAX_OCR_PAGES}")
    raw_manifest_path, raw_text_path = raw_manifest_path.expanduser().resolve(), raw_text_path.expanduser().resolve()
    visual_root = visual_assets_dir.expanduser().resolve()
    outputs = [raw_manifest_path, raw_text_path, *([placement_path.expanduser().resolve()] if placement_path else [])]
    _safe_outputs(source, outputs, visual_root, image_dir)

    try:
        import pdfplumber
        import pypdf
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError("PDF Reader requires pypdf, pdfplumber, pypdfium2, and Pillow") from exc

    source_hash = sha256_file(source)
    reader = pypdf.PdfReader(str(source), strict=False)
    if reader.is_encrypted:
        raise PdfSafetyError("Encrypted PDFs are not processed; provide a readable copy")
    page_count = len(reader.pages)
    if page_count < 1 or page_count > MAX_PAGES:
        raise PdfSafetyError(f"PDF page count must be between 1 and {MAX_PAGES}")
    root_action_info = _document_actions(reader)
    ocr_executable, ocr_info = _ocr_engine(ocr_language) if max_ocr_pages else (None, {
        "engine": "tesseract", "status": "disabled", "language": ocr_language,
        "version": None, "pages_attempted": 0, "pages_with_text": 0,
    })

    visual_root.mkdir(parents=True, exist_ok=True)
    renderer = pdfium.PdfDocument(str(source))
    pages: list[dict[str, Any]] = []
    render_status = "rendered"
    try:
        with pdfplumber.open(str(source)) as pdf:
            if len(pdf.pages) != page_count:
                raise RuntimeError("PDF parser libraries disagree on the page count")
            total_chars = 0
            for page_number, (page, pdfium_page) in enumerate(zip(pdf.pages, renderer), start=1):
                width, height = float(page.width), float(page.height)
                if width <= 0 or height <= 0 or max(width, height) > MAX_PAGE_EDGE_POINTS:
                    raise PdfSafetyError(f"PDF page {page_number} has invalid or excessive dimensions")
                unresolved: list[str] = []
                lines, extraction_issue = _text_lines(page)
                if extraction_issue:
                    unresolved.append(extraction_issue)
                items: list[dict[str, Any]] = []
                table_records, _table_boxes = _table_records(page, page_number, width, height)
                char_count = 0
                for block_number, line in enumerate(lines, start=1):
                    text = str(line["text"])
                    char_count += len(text)
                    if char_count > MAX_TEXT_CHARS_PAGE:
                        raise PdfSafetyError(f"PDF page {page_number} text exceeds the character limit")
                    bounds = {key: round(value, 3) for key, value in line.items() if key in {"x0", "top", "x1", "bottom"} and isinstance(value, (float, int))}
                    items.append({
                        "object_id": f"PDF_PAGE:{page_number}:BLOCK:{block_number:04d}",
                        "kind": "text_line", "source": "pdf_text", "text": text, "confidence": None,
                        "instruction_like_content": bool(INSTRUCTION_HINTS.search(text)), "uncertainty": None,
                        "bounds": bounds, "block_number": block_number,
                    })
                items.extend(table_records)
                total_chars += char_count
                images = _image_records(page, page_number, width, height)
                items.extend(images)
                visual_id = f"PDF_PAGE:{page_number}:VISUAL"
                items.append({"object_id": visual_id, "kind": "page_visual", "source": "rendered_page", "text": "",
                              "confidence": None, "instruction_like_content": False, "uncertainty": None})
                render_path = visual_root / "pages" / f"page-{page_number:04d}.png"
                try:
                    render = _render_page(pdfium_page, render_path)
                except Exception as exc:
                    render = {"path": None, "status": "failed", "error": type(exc).__name__}
                    render_status = "partial"
                    unresolved.append(f"Page render failed: {type(exc).__name__}")
                if ocr_executable and char_count < 80 and ocr_info["pages_attempted"] < max_ocr_pages and render.get("path"):
                    ocr_info["pages_attempted"] += 1
                    ocr_text, ocr_confidence, ocr_error = _ocr_page(ocr_executable, Path(render["path"]), ocr_language)
                    if ocr_text:
                        ocr_info["pages_with_text"] += 1
                        items.append({
                            "object_id": f"PDF_PAGE:{page_number}:OCR:001", "kind": "ocr_text", "source": "pdf_ocr",
                            "text": ocr_text, "confidence": ocr_confidence,
                            "instruction_like_content": bool(INSTRUCTION_HINTS.search(ocr_text)), "uncertainty": None,
                            "bounds": {"x0": 0.0, "top": 0.0, "x1": round(width, 3), "bottom": round(height, 3)},
                            "verification_required": True,
                        })
                    if ocr_error:
                        ocr_info.setdefault("page_errors", []).append({"page_number": page_number, "error": ocr_error})
                if ocr_executable and char_count < 80 and not render.get("path"):
                    ocr_info.setdefault("page_errors", []).append({"page_number": page_number, "error": "render_unavailable"})
                pages.append({
                    "page_number": page_number,
                    "pdf_page_label": str(reader.page_labels[page_number - 1]) if getattr(reader, "page_labels", None) else str(page_number),
                    "printed_page_label": None,
                    "rotation_degrees": int(page.rotation or 0),
                    "width_points": round(width, 3), "height_points": round(height, 3),
                    "render_path": render["path"], "render_size_px": {"width": render.get("width_px"), "height": render.get("height_px")},
                    "status": "structure_pending_visual_review" if render.get("path") else "render_failed",
                    "items": items, "required_review_object_ids": [item["object_id"] for item in items],
                    "visual_metrics": _page_metrics(items, page, char_count),
                    "uncovered_objects": [], "unresolved_items": unresolved,
                    "page_actions": _page_actions(reader, reader.pages[page_number - 1]),
                })
            if total_chars > 100_000_000:
                raise PdfSafetyError("PDF extracted text exceeds the total character limit")
    finally:
        renderer.close()

    if sha256_file(source) != source_hash:
        raise RuntimeError("Source PDF changed during extraction")
    candidate_pages = [page["page_number"] for page in pages if page["visual_metrics"]["explanation_candidate"]]
    manifest: dict[str, Any] = {
        "schema_version": 1, "parser_version": PARSER_VERSION,
        "vision_capability": vision_capability,
        "vision_capability_evidence": evidence or None,
        "reader_skill_sha256": sha256_tree(Path(__file__).resolve().parent.parent),
        "source": {"path": str(source), "sha256": source_hash, "size_bytes": source.stat().st_size, "page_count": page_count},
        "tools": {"parser": f"pdf_extractor.py {PARSER_VERSION}", "pypdf": _version("pypdf"),
                  "pdfplumber": _version("pdfplumber"), "pypdfium2": _version("pypdfium2"),
                  "renderer": {"name": "PDFium", "status": render_status}, "ocr": ocr_info},
        "document_actions": root_action_info,
        "visual_assets_dir": str(visual_root), "include_images": image_dir is not None,
        "image_dir": str(image_dir.expanduser().resolve()) if image_dir else None,
        "placement_file": str(placement_path.expanduser().resolve()) if placement_path else None,
        "pages": pages,
        "coverage": {"pages_processed": len(pages), "pages_total": page_count,
                     "text_line_count": sum(sum(item["kind"] == "text_line" for item in page["items"]) for page in pages),
                     "image_placement_count": sum(page["visual_metrics"]["image_placement_count"] for page in pages),
                     "pages_without_extractable_text": [page["page_number"] for page in pages if not page["visual_metrics"]["text_characters"]],
                     "visual_explanation_candidate_pages": candidate_pages,
                     "uncovered_page_numbers": [page["page_number"] for page in pages]},
        "visual_review": {"status": "pending", "reviewer": None}, "gate": "PARTIAL",
        "gate_reason": "Structural extraction is complete; every page still requires direct visual review",
    }
    _atomic_write(raw_manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(raw_text_path, _serialize_text(manifest))
    return manifest


def _export_selected_crops(result: dict[str, Any], review_pages: dict[int, dict[str, Any]], image_dir: Path | None,
                           placement_path: Path | None) -> list[dict[str, Any]]:
    if image_dir is None or placement_path is None:
        if any(item.get("export_object_ids") for item in review_pages.values()):
            raise ValueError("Review selected image exports, but formal image output is disabled")
        return []
    from PIL import Image

    image_dir.mkdir(parents=True, exist_ok=True)
    placements: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    exported_pixels = 0
    for page in result["pages"]:
        number = page["page_number"]
        review = review_pages[number]
        selected = review.get("export_object_ids", [])
        if not isinstance(selected, list) or not all(isinstance(value, str) for value in selected):
            raise ValueError(f"export_object_ids must be a string array on PDF page {number}")
        expected_images = {item["object_id"] for item in page["items"] if item["kind"] == "image_placement"}
        if not set(selected) <= expected_images:
            raise ValueError(f"Review selected an unknown/non-image object for PDF page {number}")
        render_path = page.get("render_path")
        if selected and (not render_path or not Path(render_path).is_file()):
            raise ValueError(f"Cannot export page {number} crops without its rendered page")
        for object_id in selected:
            if len(selected_ids) >= MAX_EXPORTED_CROPS:
                raise ValueError(f"PDF image export exceeds the limit of {MAX_EXPORTED_CROPS} crops")
            if object_id in selected_ids:
                raise ValueError(f"Duplicate image export selection: {object_id}")
            selected_ids.add(object_id)
            item = next(item for item in page["items"] if item["object_id"] == object_id)
            bounds = item["bounds"]
            with Image.open(render_path) as source_image:
                sx, sy = source_image.width / page["width_points"], source_image.height / page["height_points"]
                box = (max(0, int(bounds["x0"] * sx)), max(0, int(bounds["top"] * sy)),
                       min(source_image.width, int(math.ceil(bounds["x1"] * sx))),
                       min(source_image.height, int(math.ceil(bounds["bottom"] * sy))))
                if box[2] - box[0] < 2 or box[3] - box[1] < 2:
                    raise ValueError(f"Selected PDF image crop is empty: {object_id}")
                exported_pixels += (box[2] - box[0]) * (box[3] - box[1])
                if exported_pixels > MAX_TOTAL_EXPORTED_PIXELS:
                    raise ValueError(f"PDF image export exceeds the {MAX_TOTAL_EXPORTED_PIXELS:,}-pixel total limit")
                crop = source_image.crop(box).convert("RGB")
                crop_bytes = __import__("io").BytesIO()
                crop.save(crop_bytes, format="PNG", optimize=True)
            digest = hashlib.sha256(crop_bytes.getvalue()).hexdigest()
            filename = f"pdf-p{number:04d}-{object_id.rsplit(':', 1)[-1].lower()}-{digest[:10]}.png"
            target = image_dir / filename
            _atomic_write(target, crop_bytes.getvalue())
            item["output_asset_path"] = str(target.resolve())
            item["output_asset_sha256"] = digest
            placements.append({"seq": len(placements) + 1, "page": number,
                               "object_id": object_id, "x0": bounds["x0"], "top": bounds["top"],
                               "x1": bounds["x1"], "bottom": bounds["bottom"],
                               "w": round(bounds["x1"] - bounds["x0"], 3),
                               "h": round(bounds["bottom"] - bounds["top"], 3),
                               "file": f"images/{filename}", "crop_source": "rendered_page"})
    _atomic_write(placement_path, json.dumps(placements, ensure_ascii=False, indent=2) + "\n")
    return placements


def finalize_visual_review(raw_manifest_path: Path, visual_review_path: Path | None, final_manifest_path: Path,
                           final_text_path: Path, vision_capability: str = "available",
                           vision_capability_evidence: str | None = None) -> dict[str, Any]:
    raw_path = raw_manifest_path.expanduser().resolve(strict=True)
    if vision_capability not in {"available", "unavailable"}:
        raise ValueError("vision_capability must be 'available' or 'unavailable'")
    if vision_capability == "available" and visual_review_path is None:
        raise ValueError("Visual review is required when vision_capability is available")
    if vision_capability == "unavailable" and visual_review_path is not None:
        raise ValueError("Do not provide a visual-review file when vision_capability is unavailable")
    evidence = vision_capability_evidence.strip() if isinstance(vision_capability_evidence, str) else ""
    if vision_capability_evidence is not None and not evidence:
        raise ValueError("vision_capability_evidence must not be empty when provided")
    if len(evidence) > 1_000:
        raise ValueError("vision_capability_evidence must be at most 1000 characters")
    review_path = visual_review_path.expanduser().resolve(strict=True) if visual_review_path is not None else None
    final_manifest_path, final_text_path = final_manifest_path.expanduser().resolve(), final_text_path.expanduser().resolve()
    if review_path is not None and review_path.stat().st_size > MAX_REVIEW_BYTES:
        raise ValueError("Visual-review JSON exceeds the size limit")
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise ValueError("Unsupported PDF manifest schema")
    raw_capability = raw.get("vision_capability")
    if raw_capability is not None and raw_capability != vision_capability:
        raise ValueError("vision_capability changed after PDF extraction; rerun extract with the current host setting")
    raw_evidence = raw.get("vision_capability_evidence")
    if evidence and raw_evidence and evidence != raw_evidence:
        raise ValueError("vision_capability_evidence changed after PDF extraction; rerun extract")
    review: dict[str, Any] | None = None
    reviewer: str | None = None
    review_pages_raw: list[Any] = []
    if review_path is not None:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        if review.get("schema_version") != 1:
            raise ValueError("Unsupported PDF visual-review schema")
        reviewer_value, review_pages_value = review.get("reviewer"), review.get("pages")
        if not isinstance(reviewer_value, str) or not reviewer_value.strip() or not isinstance(review_pages_value, list):
            raise ValueError("Visual-review JSON requires a reviewer and pages array")
        reviewer, review_pages_raw = reviewer_value, review_pages_value
    source = Path(raw.get("source", {}).get("path", "")).expanduser().resolve()
    if not source.is_file() or sha256_file(source) != raw.get("source", {}).get("sha256"):
        raise ValueError("Source PDF is missing or changed since structural extraction")
    input_paths = {raw_path, source, *([review_path] if review_path is not None else [])}
    if final_manifest_path == final_text_path or final_manifest_path in input_paths or final_text_path in input_paths:
        raise ValueError("Final outputs must be distinct from inputs and from each other")
    pages = raw.get("pages", [])
    visual_root = Path(raw.get("visual_assets_dir", "")).expanduser().resolve()
    image_dir = Path(raw["image_dir"]).expanduser().resolve() if raw.get("image_dir") else None
    placement_input = Path(raw["placement_file"]).expanduser().resolve() if raw.get("placement_file") else None
    _safe_outputs(source, [raw_path, *([review_path] if review_path is not None else []), final_manifest_path, final_text_path,
                           *([placement_input] if placement_input else [])], visual_root, image_dir)

    if vision_capability == "unavailable":
        result = json.loads(json.dumps(raw))
        page_numbers = [page["page_number"] for page in result.get("pages", [])]
        for page in result.get("pages", []):
            page["structural_status"] = page.get("status")
            page["status"] = "skipped_no_vision"
            page["visual_review_status"] = "skipped_no_vision"
            page["unreviewed_object_ids"] = list(page.get("required_review_object_ids", []))
            page["uncovered_objects"] = list(page["unreviewed_object_ids"])
        candidate_pages = list(result.get("coverage", {}).get("visual_explanation_candidate_pages", []))
        result["vision_capability"] = "unavailable"
        result["vision_capability_evidence"] = evidence or None
        result["visual_review"] = {
            "status": "skipped_no_vision", "reviewer": None, "visual_observation_count": 0,
            "reviewed_page_numbers": [], "skipped_page_numbers": page_numbers,
            "capability_evidence": evidence or None,
        }
        result["coverage"]["uncovered_page_numbers"] = page_numbers
        result["coverage"]["unreviewed_due_to_no_vision_page_numbers"] = page_numbers
        result["coverage"]["unassessed_visual_explanation_candidate_pages"] = candidate_pages
        result["coverage"]["visual_explanation_candidate_pages"] = []
        result["coverage"]["images_exported"] = 0
        result["gate"] = "SKIPPED_NO_VISION"
        result["gate_reason"] = (
            "The host does not provide image input; extracted text is available, but visual page content was not reviewed"
        )
        if placement_input is not None:
            _atomic_write(placement_input, "[]\n")
        source_text = _serialize_text(result)
        asset_records: list[dict[str, str]] = []
        for page in result.get("pages", []):
            for path_value in [page.get("render_path"), *(item.get("output_asset_path") for item in page.get("items", []))]:
                if path_value:
                    path = Path(path_value).resolve()
                    if path.is_file():
                        asset_records.append({"path": str(path), "sha256": sha256_file(path)})
        if placement_input is not None and placement_input.is_file():
            asset_records.append({"path": str(placement_input), "sha256": sha256_file(placement_input)})
        result["processing_fingerprint"] = hashlib.sha256(json.dumps({
            "manifest": result,
            "source_text_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            "assets": asset_records,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        _atomic_write(final_manifest_path, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        _atomic_write(final_text_path, source_text)
        return result

    if review_path is None or review is None or reviewer is None:
        raise ValueError("Visual-review inputs are missing")
    review_by_number: dict[int, dict[str, Any]] = {}
    for entry in review_pages_raw:
        if not isinstance(entry, dict) or not isinstance(entry.get("page_number"), int):
            raise ValueError("Each review page needs an integer page_number")
        number = entry["page_number"]
        if number in review_by_number:
            raise ValueError(f"Duplicate visual review for PDF page {number}")
        review_by_number[number] = entry
    expected_pages = {page["page_number"] for page in pages}
    if set(review_by_number) != expected_pages:
        raise ValueError(f"Visual review must include every PDF page; missing={sorted(expected_pages-set(review_by_number))}, extra={sorted(set(review_by_number)-expected_pages)}")

    result = json.loads(json.dumps(raw))
    result["vision_capability"] = "available"
    result["vision_capability_evidence"] = evidence or None
    incomplete: list[int] = []
    failed: list[int] = []
    unresolved_all: list[dict[str, Any]] = []
    explanation_candidates: set[int] = set()
    observations_count = 0
    for page in result["pages"]:
        number = page["page_number"]
        review_page = review_by_number[number]
        if not page.get("render_path") or not Path(page["render_path"]).is_file():
            page["status"] = "render_failed"
            page["uncovered_objects"] = ["rendered_page"]
            failed.append(number)
            continue
        expected = set(page.get("required_review_object_ids", []))
        checked_raw = review_page.get("checked_object_ids", [])
        checked = set(checked_raw) if isinstance(checked_raw, list) and all(isinstance(value, str) for value in checked_raw) else set()
        missing, extra = expected - checked, checked - expected
        declared = review_page.get("uncovered_objects", [])
        if not isinstance(declared, list):
            raise ValueError(f"uncovered_objects must be an array on page {number}")
        page["uncovered_objects"] = sorted({*missing, *(str(value) for value in declared), *(f"unknown_review_object:{value}" for value in extra)})
        requires_explanation = review_page.get("requires_explanation")
        if not isinstance(requires_explanation, bool):
            page["uncovered_objects"].append("explanation_routing_not_recorded")
        explanation_reason = review_page.get("explanation_reason", "")
        if not isinstance(explanation_reason, str) or len(explanation_reason) > 2_000:
            raise ValueError(f"explanation_reason must be a string up to 2000 characters on page {number}")
        if requires_explanation and not explanation_reason.strip():
            page["uncovered_objects"].append("explanation_reason_missing")
        page["visual_review_requires_explanation"] = requires_explanation is True
        page["visual_review_explanation_reason"] = explanation_reason.strip() if requires_explanation else None
        printed_label = review_page.get("printed_page_label")
        if printed_label is not None and (not isinstance(printed_label, str) or len(printed_label) > 80):
            raise ValueError(f"printed_page_label must be a short string or null on page {number}")
        page["printed_page_label"] = printed_label
        if review_page.get("status") != "complete" and not page["uncovered_objects"]:
            page["uncovered_objects"].append("visual_review_not_complete")
        if page["uncovered_objects"] or review_page.get("status") != "complete":
            page["status"] = "partial"
            incomplete.append(number)
        else:
            page["status"] = "complete"
        observations = review_page.get("observations", [])
        if not isinstance(observations, list):
            raise ValueError(f"observations must be an array on page {number}")
        for index, observation in enumerate(observations, start=1):
            if not isinstance(observation, dict) or observation.get("object_id") not in expected:
                raise ValueError(f"Observation {index} on page {number} must cite a known object")
            kind = observation.get("kind")
            if kind not in ALLOWED_OBSERVATION_KINDS:
                raise ValueError(f"Invalid observation kind on page {number}: {kind}")
            text, description, uncertainty = observation.get("text", ""), observation.get("description", ""), observation.get("uncertainty")
            confidence = observation.get("confidence")
            if not isinstance(text, str) or not isinstance(description, str) or max(len(text), len(description)) > 20_000:
                raise ValueError("Observation text/description must be bounded strings")
            if confidence is not None and (not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
                raise ValueError("Observation confidence must be between 0 and 1")
            if uncertainty is not None and not isinstance(uncertainty, str):
                raise ValueError("Observation uncertainty must be a string or null")
            item = {"object_id": f"{observation['object_id']}-visual-{index}",
                    "kind": kind, "source": "visual_ocr" if kind == "ocr_text" else "visual_observation",
                    "text": text, "description": description, "confidence": confidence,
                    "instruction_like_content": bool(observation.get("instruction_like_content", False)),
                    "uncertainty": uncertainty, "observed_object_id": observation["object_id"]}
            page["items"].append(item)
            observations_count += 1
            if kind == "uncertainty" or uncertainty or (confidence is not None and confidence < 0.55):
                unresolved_all.append({"page_number": number, "item": uncertainty or description or text or f"Low-confidence {kind}"})
        ocr_object_ids = {item["object_id"] for item in page.get("items", [])
                          if item.get("kind") == "ocr_text" and item.get("verification_required") is True}
        verified_ocr_ids = {observation.get("object_id") for observation in observations
                            if isinstance(observation, dict) and observation.get("kind") == "ocr_text"
                            and isinstance(observation.get("text"), str) and observation["text"].strip()}
        unverified_ocr = sorted(ocr_object_ids - verified_ocr_ids)
        if unverified_ocr:
            page["uncovered_objects"] = sorted({*page["uncovered_objects"],
                                                 *(f"unverified_ocr_text:{object_id}" for object_id in unverified_ocr)})
            page["status"] = "partial"
            if number not in incomplete:
                incomplete.append(number)
        unresolved = review_page.get("unresolved_items", [])
        if not isinstance(unresolved, list) or not all(isinstance(value, str) for value in unresolved):
            raise ValueError(f"unresolved_items must be a string array on page {number}")
        page["unresolved_items"] = [*page.get("unresolved_items", []), *unresolved]
        unresolved_all.extend({"page_number": number, "item": value} for value in unresolved)
        if page["visual_metrics"]["explanation_candidate"] or requires_explanation:
            explanation_candidates.add(number)

    placement_path = placement_input
    placements = _export_selected_crops(result, review_by_number, image_dir, placement_path)
    if sha256_file(source) != raw.get("source", {}).get("sha256"):
        raise ValueError("Source PDF changed during visual review")
    gate = "PASS"
    if failed:
        gate = "FAIL"
    elif incomplete or unresolved_all or any(page.get("unresolved_items") for page in result["pages"]):
        gate = "PARTIAL"
    result["visual_review"] = {"status": "complete" if gate == "PASS" else "partial" if gate == "PARTIAL" else "failed",
                               "reviewer": reviewer.strip()[:200], "visual_observation_count": observations_count,
                               "reviewed_page_numbers": sorted(page["page_number"] for page in result["pages"] if page["status"] == "complete"),
                               "capability_evidence": evidence or None}
    result["coverage"]["uncovered_page_numbers"] = sorted(set(incomplete + failed))
    result["coverage"]["unresolved_items"] = unresolved_all
    result["coverage"]["visual_explanation_candidate_pages"] = sorted(explanation_candidates)
    result["coverage"]["images_exported"] = len(placements)
    result["gate"] = gate
    result["gate_reason"] = ("Every PDF page and extracted object has a complete visual review" if gate == "PASS"
                              else "One or more page images could not be rendered" if gate == "FAIL"
                              else "One or more pages or objects remain unreviewed or unresolved")
    source_text = _serialize_text(result)
    asset_records: list[dict[str, str]] = []
    for page in result["pages"]:
        for path_value in [page.get("render_path"), *(item.get("output_asset_path") for item in page["items"])]:
            if path_value:
                path = Path(path_value).resolve()
                if not path.is_file():
                    raise ValueError(f"Referenced PDF visual asset is missing: {path}")
                asset_records.append({"path": str(path), "sha256": sha256_file(path)})
    if placement_path:
        asset_records.append({"path": str(placement_path.resolve()), "sha256": sha256_file(placement_path.resolve())})
    result["processing_fingerprint"] = hashlib.sha256(json.dumps({
        "manifest": result,
        "source_text_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "assets": asset_records,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    _atomic_write(final_manifest_path, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(final_text_path, source_text)
    return result


def build_context_fingerprint(manifest_path: Path, explanation_path: Path | None = None) -> dict[str, Any]:
    manifest = json.loads(manifest_path.expanduser().resolve(strict=True).read_text(encoding="utf-8"))
    base = manifest.get("processing_fingerprint")
    if not isinstance(base, str) or not re.fullmatch(r"[0-9a-f]{64}", base):
        raise ValueError("Final PDF manifest has no valid processing_fingerprint")
    explanation_hash = sha256_file(explanation_path.expanduser().resolve(strict=True)) if explanation_path else None
    payload = {"base_processing_fingerprint": base, "visual_explanations_sha256": explanation_hash}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"pdf_processing_fingerprint": digest, **payload}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    extract = subparsers.add_parser("extract", help="Extract text, page visuals, and image placements")
    extract.add_argument("source", type=Path)
    extract.add_argument("--raw-manifest", required=True, type=Path)
    extract.add_argument("--raw-text", required=True, type=Path)
    extract.add_argument("--visual-assets-dir", required=True, type=Path)
    extract.add_argument("--image-dir", type=Path)
    extract.add_argument("--placement-file", type=Path)
    extract.add_argument("--vision-capability", required=True, choices=("available", "unavailable"))
    extract.add_argument("--vision-capability-evidence", required=True, help="Short evidence from the current host image-input path")
    extract.add_argument("--ocr-language", default="eng+chi_sim", help="Tesseract languages for low-text pages, when installed")
    extract.add_argument("--max-ocr-pages", type=int, default=MAX_OCR_PAGES, help="Maximum low-text pages to OCR; use 0 to disable")
    finalize = subparsers.add_parser("finalize", help="Validate page review and export only selected image crops")
    finalize.add_argument("--raw-manifest", required=True, type=Path)
    finalize.add_argument("--visual-review", type=Path)
    finalize.add_argument("--vision-capability", required=True, choices=("available", "unavailable"))
    finalize.add_argument("--vision-capability-evidence", required=True, help="Short evidence from the current host image-input path")
    finalize.add_argument("--manifest", required=True, type=Path)
    finalize.add_argument("--source-text", required=True, type=Path)
    fingerprint = subparsers.add_parser("fingerprint", help="Hash reviewed PDF context for downstream stage signatures")
    fingerprint.add_argument("--manifest", required=True, type=Path)
    fingerprint.add_argument("--visual-explanations", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "extract":
            manifest = extract_pdf(args.source, args.raw_manifest, args.raw_text, args.visual_assets_dir,
                                   args.image_dir, args.placement_file, args.ocr_language, args.max_ocr_pages,
                                   args.vision_capability, args.vision_capability_evidence)
            print(json.dumps({"gate": manifest["gate"], "page_count": manifest["source"]["page_count"],
                              "render_status": manifest["tools"]["renderer"]["status"],
                              "pages_without_extractable_text": manifest["coverage"]["pages_without_extractable_text"],
                              "image_placement_count": manifest["coverage"]["image_placement_count"],
                              "visual_explanation_candidate_pages": manifest["coverage"]["visual_explanation_candidate_pages"],
                              "raw_manifest": str(args.raw_manifest.resolve()), "raw_text": str(args.raw_text.resolve()),
                              "visual_assets_dir": str(args.visual_assets_dir.resolve())}, ensure_ascii=False))
            return 0
        if args.command == "fingerprint":
            print(json.dumps(build_context_fingerprint(args.manifest, args.visual_explanations), ensure_ascii=False))
            return 0
        manifest = finalize_visual_review(
            args.raw_manifest, args.visual_review, args.manifest, args.source_text,
            args.vision_capability, args.vision_capability_evidence,
        )
        print(json.dumps({"gate": manifest["gate"], "page_count": manifest["source"]["page_count"],
                          "reviewed_page_count": len(manifest["visual_review"]["reviewed_page_numbers"]),
                          "skipped_page_numbers": manifest["visual_review"].get("skipped_page_numbers", []),
                          "uncovered_page_numbers": manifest["coverage"]["uncovered_page_numbers"],
                          "manifest": str(args.manifest.resolve()), "source_text": str(args.source_text.resolve())}, ensure_ascii=False))
        return 0 if manifest["gate"] in {"PASS", "SKIPPED_NO_VISION"} else 3 if manifest["gate"] == "PARTIAL" else 2
    except (OSError, ValueError, RuntimeError, PdfSafetyError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

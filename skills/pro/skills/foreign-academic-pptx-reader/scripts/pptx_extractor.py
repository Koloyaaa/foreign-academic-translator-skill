#!/usr/bin/env python3
"""Extract a bounded, page-indexed PPTX handoff and render slides for visual review.

This script does not execute macros, open embedded files, or follow external links.
When host image input is available, every rendered visible slide requires a visual
review JSON before the gate can pass. A text-only host receives an explicit
SKIPPED_NO_VISION handoff; that status is not a visual pass.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree


PARSER_VERSION = "1.1.0"
MAX_SOURCE_BYTES = 250 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20_000
MAX_MEMBER_BYTES = 100 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 300
MAX_XML_BYTES = 32 * 1024 * 1024
MAX_REVIEW_BYTES = 32 * 1024 * 1024
MAX_RENDER_EDGE = 5_000
MAX_RENDER_PIXELS = 30_000_000

INSTRUCTION_HINTS = re.compile(
    r"(?is)(ignore|disregard|override|forget).{0,80}(previous|system|developer|all|above|prior).{0,40}(instruction|prompt|rule)"
    r"|忽略.{0,30}(之前|上文|系统|开发者|所有).{0,20}(指令|提示|规则)"
    r"|泄露.{0,20}(提示词|系统提示|开发者消息)|把.{0,20}(文件|内容).{0,20}(发送|上传).{0,30}(网址|网站|邮箱)",
)
SAFE_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff", "svg", "emf", "wmf"}
ALLOWED_OBSERVATION_KINDS = {"ocr_text", "visual_description", "uncertainty"}


class PackageSafetyError(ValueError):
    """Raised when the input archive exceeds bounds or has unsafe package paths."""


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
        relative = item.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(item)))
    return digest.hexdigest()


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _safe_xml(data: bytes, part_name: str) -> ElementTree.Element:
    upper = data[: min(len(data), MAX_XML_BYTES)].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise PackageSafetyError(f"XML declaration/entity is not allowed in {part_name}")
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise PackageSafetyError(f"Invalid XML in {part_name}: {exc}") from exc


def _safe_member_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", normalized)
        or any(part in {"..", ""} for part in path.parts if part != ".")
    ):
        raise PackageSafetyError(f"Unsafe archive member path: {name!r}")
    return normalized


def inspect_package(path: Path) -> dict[str, Any]:
    """Validate PPTX ZIP bounds without extracting members to disk."""
    path = path.expanduser().resolve(strict=True)
    if path.suffix.lower() != ".pptx":
        raise PackageSafetyError("Only .pptx files are supported; macro-enabled formats are not accepted")
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise PackageSafetyError(f"PPTX exceeds the {MAX_SOURCE_BYTES // (1024 * 1024)} MiB input limit")
    if not zipfile.is_zipfile(path):
        raise PackageSafetyError("The source is not a valid PPTX ZIP package")

    seen: set[str] = set()
    total_size = 0
    names: set[str] = set()
    external_relationships: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_MEMBERS:
                raise PackageSafetyError("PPTX contains too many archive members")
            for info in infos:
                name = _safe_member_name(info.filename)
                key = name.casefold()
                if key in seen:
                    raise PackageSafetyError(f"Duplicate archive member path: {name}")
                seen.add(key)
                names.add(name)
                if info.flag_bits & 0x1:
                    raise PackageSafetyError(f"Encrypted archive member is not supported: {name}")
                mode = (info.external_attr >> 16) & 0xFFFF
                if (mode & 0o170000) == 0o120000:
                    raise PackageSafetyError(f"Symbolic-link archive member is not supported: {name}")
                if info.file_size > MAX_MEMBER_BYTES:
                    raise PackageSafetyError(f"PPTX member exceeds the per-file limit: {name}")
                total_size += info.file_size
                if total_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise PackageSafetyError("PPTX exceeds the total uncompressed-size limit")
                if info.file_size and info.compress_size == 0:
                    raise PackageSafetyError(f"Invalid compressed size for {name}")
                if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                    raise PackageSafetyError(f"PPTX member exceeds the compression-ratio limit: {name}")
                if name.lower().endswith((".xml", ".rels")):
                    if info.file_size > MAX_XML_BYTES:
                        raise PackageSafetyError(f"XML package member is too large: {name}")
                    data = archive.read(info)
                    root = _safe_xml(data, name)
                    if name.lower().endswith(".rels"):
                        for relation in root:
                            if relation.attrib.get("TargetMode", "").casefold() == "external":
                                rel_type = relation.attrib.get("Type", "").rsplit("/", 1)[-1]
                                target = relation.attrib.get("Target", "")
                                external_relationships.append({
                                    "relationship_part": name,
                                    "type": rel_type,
                                    "target_sha256": hashlib.sha256(target.encode("utf-8", "replace")).hexdigest(),
                                    "render_blocking": rel_type.casefold() != "hyperlink",
                                })
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, PackageSafetyError):
            raise
        raise PackageSafetyError(f"Cannot inspect PPTX package: {exc}") from exc

    required = {"[Content_Types].xml", "ppt/presentation.xml"}
    missing = required - names
    if missing:
        raise PackageSafetyError(f"PPTX package is missing required parts: {', '.join(sorted(missing))}")
    if any(name.casefold().endswith("/vbaproject.bin") for name in names):
        raise PackageSafetyError("PPTX contains a VBA project and cannot be processed")
    return {
        "archive_member_count": len(names),
        "uncompressed_size_bytes": total_size,
        "external_relationships": external_relationships,
    }


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text_from_element(element: Any) -> str:
    parts = [node.text or "" for node in element.iter() if _local_name(node.tag) == "t"]
    return "".join(parts).strip()


def _shape_type_name(shape: Any) -> str:
    try:
        value = shape.shape_type
        return getattr(value, "name", str(value))
    except Exception:
        return "unknown"


def _shape_bounds(shape: Any, slide_width: int, slide_height: int) -> dict[str, float | int]:
    left = int(getattr(shape, "left", 0) or 0)
    top = int(getattr(shape, "top", 0) or 0)
    width = int(getattr(shape, "width", 0) or 0)
    height = int(getattr(shape, "height", 0) or 0)
    return {
        "x": round(left / slide_width, 6) if slide_width else 0.0,
        "y": round(top / slide_height, 6) if slide_height else 0.0,
        "width": round(width / slide_width, 6) if slide_width else 0.0,
        "height": round(height / slide_height, 6) if slide_height else 0.0,
        "x_emu": left,
        "y_emu": top,
        "width_emu": width,
        "height_emu": height,
    }


def _make_item(
    object_id: str,
    kind: str,
    source: str,
    text: str = "",
    **extra: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "object_id": object_id,
        "kind": kind,
        "source": source,
        "text": text,
        "confidence": 1.0 if source in {"pptx_text", "pptx_table", "chart_cache", "pptx_notes"} else None,
        "instruction_like_content": bool(INSTRUCTION_HINTS.search(text)) if text else False,
        "uncertainty": None,
    }
    item.update(extra)
    return item


def _chart_content(chart: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"title": "", "plots": []}
    try:
        if chart.has_title:
            result["title"] = chart.chart_title.text_frame.text.strip()
    except Exception:
        pass
    try:
        plots = chart.plots
    except Exception:
        plots = []
    for plot_index, plot in enumerate(plots, start=1):
        categories: list[str] = []
        try:
            categories = [str(category.label) for category in plot.categories]
        except Exception:
            pass
        series_data: list[dict[str, Any]] = []
        try:
            series = plot.series
        except Exception:
            series = []
        for series_index, item in enumerate(series, start=1):
            try:
                values = list(item.values)
            except Exception:
                values = []
            clean_values: list[int | float | str | None] = []
            for value in values:
                if value is None:
                    clean_values.append(None)
                elif isinstance(value, (int, float)):
                    clean_values.append(value)
                else:
                    clean_values.append(str(value))
            try:
                name = item.name
            except Exception:
                name = None
            series_data.append({"name": str(name) if name is not None else f"series-{series_index}", "values": clean_values})
        result["plots"].append({"plot": plot_index, "categories": categories, "series": series_data})
    return result


def _write_image_blob(data: bytes, ext: str, object_id: str, visual_root: Path) -> tuple[str, str]:
    ext = ext.lower().lstrip(".")
    if ext not in SAFE_IMAGE_EXTENSIONS:
        ext = "bin"
    digest = hashlib.sha256(data).hexdigest()
    relative = Path("objects") / f"{object_id}.{digest[:12]}.{ext}"
    target = visual_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return str(target.resolve()), digest


def _image_relationships(element: Any) -> list[tuple[str | None, bool]]:
    relationships: list[tuple[str | None, bool]] = []
    for node in element.iter():
        if _local_name(node.tag) != "blip":
            continue
        embedded = next((value for key, value in node.attrib.items() if key.endswith("}embed")), None)
        linked = next((value for key, value in node.attrib.items() if key.endswith("}link")), None)
        if embedded:
            relationships.append((str(embedded), False))
        elif linked:
            relationships.append((str(linked), True))
    return relationships


def _attach_image_asset(
    item: dict[str, Any],
    data: bytes,
    ext: str,
    slide_number: int,
    bounds: dict[str, float | int],
    visual_root: Path,
    export_image_dir: Path | None,
    placement: list[dict[str, Any]],
) -> None:
    object_id = str(item["object_id"])
    visual_path, image_hash = _write_image_blob(data, ext, object_id, visual_root)
    normalized_ext = str(ext).lower().lstrip(".")
    item["asset_path"] = visual_path
    item["asset_sha256"] = image_hash
    item["asset_format"] = normalized_ext
    if export_image_dir is None:
        return
    if normalized_ext not in {"png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff", "svg"}:
        item["uncertainty"] = f"Image format {normalized_ext or 'unknown'} cannot be exported to the selected lesson formats"
        item["confidence"] = 0.0
        return
    file_name = f"pptx_s{slide_number:04d}_o{re.sub(r'[^A-Za-z0-9_-]', '_', object_id)}_{image_hash[:10]}.{normalized_ext}"
    exported_path = export_image_dir / file_name
    exported_path.parent.mkdir(parents=True, exist_ok=True)
    exported_path.write_bytes(data)
    item["output_asset_path"] = str(exported_path.resolve())
    width = int(bounds.get("width_emu", 0))
    height = int(bounds.get("height_emu", 0))
    aspect = (width / height) if height else None
    placement.append({
        "file": f"images/{file_name}",
        "aspect_w_h": round(aspect, 4) if aspect else None,
        "page": slide_number,
        "object_id": object_id,
        "x": bounds.get("x", 0),
        "y": bounds.get("y", 0),
        "width": bounds.get("width", 0),
        "height": bounds.get("height", 0),
    })


def _extract_related_image(
    part: Any,
    element: Any,
    object_id: str,
    kind: str,
    source: str,
    slide_number: int,
    bounds: dict[str, float | int],
    visual_root: Path,
    export_image_dir: Path | None,
    placement: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for image_index, (relationship_id, external) in enumerate(_image_relationships(element), start=1):
        image_id = object_id if image_index == 1 else f"{object_id}-image-{image_index}"
        if external or not relationship_id:
            items.append(_make_item(
                image_id,
                kind,
                source,
                confidence=0.0,
                uncertainty="Image is externally linked and was not fetched",
                bounds=bounds,
            ))
            continue
        try:
            image_part = part.related_part(relationship_id)
            blob = image_part.blob
            try:
                ext = image_part.image.ext
            except Exception:
                content_type = str(getattr(image_part, "content_type", ""))
                ext = content_type.split("/", 1)[-1].replace("svg+xml", "svg")
            item = _make_item(image_id, kind, source, bounds=bounds)
            _attach_image_asset(item, blob, str(ext), slide_number, bounds, visual_root, export_image_dir, placement)
            items.append(item)
        except Exception as exc:
            items.append(_make_item(
                image_id,
                kind,
                source,
                confidence=0.0,
                uncertainty=f"Embedded image relationship could not be read: {exc}",
                bounds=bounds,
            ))
    return items


def _extract_shape_items(
    shapes: Any,
    slide_number: int,
    slide_width: int,
    slide_height: int,
    visual_root: Path,
    export_image_dir: Path | None,
    placement: list[dict[str, Any]],
    object_counter: list[int],
    parent_id: str | None = None,
) -> list[dict[str, Any]]:
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    items: list[dict[str, Any]] = []
    for shape in shapes:
        object_counter[0] += 1
        shape_id = int(getattr(shape, "shape_id", object_counter[0]))
        object_id = f"slide-{slide_number:04d}-shape-{shape_id}"
        shape_name = str(getattr(shape, "name", ""))
        type_name = _shape_type_name(shape)
        try:
            raw_tag_names = {_local_name(node.tag) for node in shape.element.iter()}
        except Exception:
            raw_tag_names = set()
        has_omml = "oMath" in raw_tag_names or "oMathPara" in raw_tag_names
        graphic_uri = ""
        try:
            for node in shape.element.iter():
                if _local_name(node.tag) == "graphicData":
                    graphic_uri = str(node.attrib.get("uri", ""))
                    break
        except Exception:
            pass

        bounds = _shape_bounds(shape, slide_width, slide_height)
        common = {
            "bounds": bounds,
            "shape_id": shape_id,
            "shape_name": shape_name,
            "shape_type": type_name,
            "parent_object_id": parent_id,
            "display_order": object_counter[0],
        }

        if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.GROUP:
            item = _make_item(object_id, "group", "pptx_shape", **common)
            items.append(item)
            try:
                items.extend(_extract_shape_items(
                    shape.shapes,
                    slide_number,
                    slide_width,
                    slide_height,
                    visual_root,
                    export_image_dir,
                    placement,
                    object_counter,
                    object_id,
                ))
            except Exception as exc:
                item["uncertainty"] = f"Group contents could not be enumerated: {exc}"
            continue

        text = ""
        try:
            if shape.has_text_frame:
                text = shape.text_frame.text.strip()
        except Exception:
            pass
        if has_omml:
            math_text = _text_from_element(shape.element)
            text = "\n".join(part for part in (text, math_text) if part)

        if getattr(shape, "has_table", False):
            rows: list[list[str]] = []
            try:
                rows = [[cell.text.strip() for cell in row.cells] for row in shape.table.rows]
            except Exception:
                pass
            table_text = "\n".join("\t".join(row) for row in rows)
            item = _make_item(object_id, "table", "pptx_table", table_text, rows=rows, **common)
        elif getattr(shape, "has_chart", False):
            chart_data: dict[str, Any] = {}
            chart_error = None
            try:
                chart_data = _chart_content(shape.chart)
            except Exception as exc:
                chart_error = str(exc)
                chart_data = {"error": str(exc), "plots": []}
            chart_text_parts = [chart_data.get("title", "")]
            for plot in chart_data.get("plots", []):
                chart_text_parts.extend(plot.get("categories", []))
                for series in plot.get("series", []):
                    chart_text_parts.append(series.get("name", ""))
                    chart_text_parts.extend("" if value is None else str(value) for value in series.get("values", []))
            item = _make_item(
                object_id,
                "chart",
                "chart_cache",
                "\n".join(p for p in chart_text_parts if p),
                chart=chart_data,
                confidence=0.0 if chart_error else 1.0,
                uncertainty=f"Chart data could not be extracted: {chart_error}" if chart_error else None,
                **common,
            )
        elif "OLE_OBJECT" in type_name.upper() or "EMBEDDED_OBJECT" in type_name.upper():
            item = _make_item(
                object_id,
                "embedded_object",
                "pptx_shape",
                text,
                confidence=0.0,
                uncertainty="Embedded or linked object content is not opened or executed; only its visible preview can be reviewed",
                **common,
            )
        elif has_omml:
            item = _make_item(object_id, "equation", "pptx_text", text, **common)
        elif "diagram" in graphic_uri.casefold():
            item = _make_item(object_id, "diagram", "diagram_xml", text or _text_from_element(shape.element), graphic_uri=graphic_uri, **common)
        elif getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.PICTURE:
            item = _make_item(object_id, "image", "pptx_image", text, **common)
            try:
                image = shape.image
                image_bytes = image.blob
                ext = str(image.ext or "bin").lower()
                _attach_image_asset(item, image_bytes, ext, slide_number, bounds, visual_root, export_image_dir, placement)
            except Exception as exc:
                item["uncertainty"] = f"Embedded image could not be extracted: {exc}"
                item["confidence"] = 0.0
        elif "media" in type_name.casefold() or "movie" in type_name.casefold() or "audio" in type_name.casefold():
            item = _make_item(object_id, "media", "pptx_shape", text, **common)
            item["uncertainty"] = "Audio/video playback is not transcribed by the structural extractor"
            item["confidence"] = 0.0
        elif text:
            item = _make_item(object_id, "text", "pptx_text", text, **common)
        else:
            item = _make_item(object_id, "shape", "pptx_shape", **common)
            if type_name == "unknown":
                item["uncertainty"] = "Shape type was not recognized by the parser"
                item["confidence"] = 0.0

        if item.get("uncertainty"):
            item["instruction_like_content"] = bool(INSTRUCTION_HINTS.search(text)) if text else False
        items.append(item)
        if getattr(shape, "shape_type", None) != MSO_SHAPE_TYPE.PICTURE:
            try:
                items.extend(_extract_related_image(
                    shape.part,
                    shape.element,
                    f"{object_id}-picture-fill",
                    "image",
                    "pptx_picture_fill",
                    slide_number,
                    bounds,
                    visual_root,
                    export_image_dir,
                    placement,
                ))
            except Exception as exc:
                fill_item = _make_item(
                    f"{object_id}-picture-fill",
                    "image",
                    "pptx_picture_fill",
                    confidence=0.0,
                    uncertainty=f"Picture fill could not be read: {exc}",
                    bounds=bounds,
                )
                items.append(fill_item)
    return items


def _extract_speaker_notes(slide: Any, slide_number: int) -> tuple[bool, dict[str, Any] | None]:
    try:
        has_notes = bool(slide.has_notes_slide)
    except Exception:
        has_notes = False
    if not has_notes:
        return False, None
    try:
        notes = slide.notes_slide.notes_text_frame.text.strip()
    except Exception:
        return True, _make_item(f"slide-{slide_number:04d}-notes", "speaker_notes", "pptx_notes", "", confidence=0.0, uncertainty="Notes exist but could not be read")
    if not notes:
        return True, None
    return True, _make_item(f"slide-{slide_number:04d}-notes", "speaker_notes", "pptx_notes", notes)


def _render_slides(
    source: Path,
    slides: list[dict[str, Any]],
    render_dir: Path,
    external_relationships: list[dict[str, Any]],
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    visible_numbers = [slide["slide_number"] for slide in slides if slide["visibility"] == "visible"]
    renderer = shutil.which("soffice") or shutil.which("libreoffice")
    if not renderer:
        return {"status": "unavailable", "renderer": None, "error": "LibreOffice (soffice) was not found"}
    blockers = [item for item in external_relationships if item.get("render_blocking")]
    if blockers:
        return {
            "status": "blocked",
            "renderer": Path(renderer).name,
            "error": f"Rendering skipped because {len(blockers)} external non-hyperlink relationships could cause external content to load",
        }
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return {"status": "unavailable", "renderer": Path(renderer).name, "error": "pypdfium2 is required to rasterize the rendered PDF"}

    render_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pptx-render-") as temp_name:
        temp_dir = Path(temp_name).resolve()
        profile_dir = temp_dir / "lo-profile"
        pdf_dir = temp_dir / "pdf"
        profile_dir.mkdir()
        pdf_dir.mkdir()
        command = [
            renderer,
            f"-env:UserInstallation={profile_dir.as_uri()}",
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--convert-to",
            "pdf",
            "--outdir",
            str(pdf_dir),
            str(source.resolve()),
        ]
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired:
            return {"status": "failed", "renderer": Path(renderer).name, "error": f"Slide rendering timed out after {timeout_seconds}s"}
        if process.returncode != 0:
            detail = (process.stderr or process.stdout or f"exit code {process.returncode}").strip()[-2000:]
            return {"status": "failed", "renderer": Path(renderer).name, "error": detail}
        pdf_path = pdf_dir / f"{source.stem}.pdf"
        if not pdf_path.is_file():
            pdf_files = list(pdf_dir.glob("*.pdf"))
            if len(pdf_files) != 1:
                return {"status": "failed", "renderer": Path(renderer).name, "error": "Renderer did not produce one identifiable PDF"}
            pdf_path = pdf_files[0]
        try:
            pdf = pdfium.PdfDocument(str(pdf_path))
        except Exception as exc:
            return {"status": "failed", "renderer": Path(renderer).name, "error": f"Rendered PDF could not be opened: {exc}"}
        try:
            page_count = len(pdf)
            total_slide_count = len(slides)
            if page_count == total_slide_count:
                mapping = [(index, slide) for index, slide in enumerate(slides) if slide["visibility"] == "visible"]
            elif page_count == len(visible_numbers):
                mapping = list(zip(range(page_count), [slide for slide in slides if slide["visibility"] == "visible"]))
            else:
                return {
                    "status": "failed",
                    "renderer": Path(renderer).name,
                    "error": f"Rendered page count ({page_count}) does not match PPTX slide count ({total_slide_count}) or visible count ({len(visible_numbers)})",
                }
            rendered: list[int] = []
            for pdf_index, slide in mapping:
                page = pdf[pdf_index]
                width, height = page.get_size()
                if width <= 0 or height <= 0:
                    return {"status": "failed", "renderer": Path(renderer).name, "error": f"Invalid rendered page size for slide {slide['slide_number']}"}
                scale = min(2.0, MAX_RENDER_EDGE / max(width, height))
                pixel_width = max(1, int(width * scale))
                pixel_height = max(1, int(height * scale))
                if pixel_width * pixel_height > MAX_RENDER_PIXELS:
                    scale *= (MAX_RENDER_PIXELS / (pixel_width * pixel_height)) ** 0.5
                bitmap = page.render(scale=scale)
                image = bitmap.to_pil()
                destination = render_dir / f"slide-{slide['slide_number']:04d}.png"
                image.save(destination, format="PNG", optimize=True)
                slide["render_path"] = str(destination.resolve())
                slide["render_size_px"] = {"width": image.width, "height": image.height}
                rendered.append(slide["slide_number"])
            return {
                "status": "complete" if set(rendered) == set(visible_numbers) else "partial",
                "renderer": Path(renderer).name,
                "renderer_version": _renderer_version(renderer),
                "rasterizer": "pypdfium2",
                "rasterizer_version": _distribution_version("pypdfium2"),
                "rendered_visible_slides": rendered,
                "visible_slides_total": len(visible_numbers),
            }
        finally:
            pdf.close()


def _renderer_version(path: str) -> str | None:
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10, check=False)
        text = (result.stdout or result.stderr).strip()
        return text[:300] if text else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _ocr_slides(slides: list[dict[str, Any]], language: str) -> dict[str, Any]:
    executable = shutil.which("tesseract")
    if not executable:
        return {"status": "unavailable", "engine": None, "language": language}
    version = None
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10, check=False)
        version = (result.stdout or result.stderr).splitlines()[0][:200]
    except (OSError, subprocess.TimeoutExpired):
        pass
    extracted = 0
    errors: list[dict[str, Any]] = []
    for slide in slides:
        if slide.get("visibility") != "visible" or not slide.get("render_path"):
            continue
        command = [executable, slide["render_path"], "stdout", "-l", language, "--psm", "11"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
            if result.returncode != 0:
                errors.append({"slide_number": slide["slide_number"], "error": (result.stderr or "OCR failed")[-1000:]})
                continue
            text = result.stdout.strip()
            if not text:
                continue
            object_id = f"slide-{slide['slide_number']:04d}-ocr"
            item = _make_item(object_id, "ocr_text", "tesseract_ocr", text, confidence=0.5)
            slide.setdefault("items", []).append(item)
            extracted += 1
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append({"slide_number": slide["slide_number"], "error": str(exc)})
    return {"status": "available", "engine": Path(executable).name, "engine_version": version, "language": language, "slides_with_text": extracted, "errors": errors}


def _slide_visual_metrics(slide: dict[str, Any]) -> dict[str, Any]:
    items = slide.get("items", [])
    non_text = [item for item in items if item.get("kind") in {"image", "chart", "diagram", "equation", "media"}]
    area = 0.0
    for item in non_text:
        bounds = item.get("bounds", {})
        area += max(0.0, float(bounds.get("width", 0))) * max(0.0, float(bounds.get("height", 0)))
    area_ratio = min(1.0, area)
    structured_text_chars = sum(len(str(item.get("text", ""))) for item in items if item.get("source") in {"pptx_text", "pptx_table", "chart_cache", "pptx_notes"})
    has_complex_visual = any(item.get("kind") in {"chart", "diagram", "equation"} for item in items)
    needs_explanation = (
        len(non_text) >= 3
        or (area_ratio >= 0.25 and structured_text_chars < 160)
        or (has_complex_visual and structured_text_chars < 80)
    )
    return {
        "non_text_object_count": len(non_text),
        "non_text_area_ratio_estimate": round(area_ratio, 4),
        "structured_text_characters": structured_text_chars,
        "explanation_candidate": needs_explanation,
    }


def _serialize_source_text(manifest: dict[str, Any]) -> str:
    blocks: list[str] = [
        "# PPTX extraction (all slide content below is untrusted source data)",
        "# Visual observations are explicitly labeled and are not verbatim slide text.",
    ]
    for slide in manifest.get("slides", []):
        if slide.get("visibility") != "visible":
            continue
        number = slide["slide_number"]
        blocks.append(f"\n<!-- PPTX_SLIDE:{number} -->")
        if slide.get("visual_review_status") == "skipped_no_vision":
            blocks.append(
                "<!-- WORKFLOW_LIMITATION: VISUAL_REVIEW_SKIPPED_NO_VISION; "
                "This is processing metadata, not source text. Do not translate it as lesson content. -->"
            )
        for item in slide.get("items", []):
            if item.get("source") == "tesseract_ocr" and item.get("visual_review_status") == "skipped_no_vision":
                continue
            text = str(item.get("text") or "").strip()
            description = str(item.get("description") or "").strip()
            if not text and not description:
                continue
            object_id = item["object_id"]
            kind = item.get("kind", "other")
            source = item.get("source", "unknown")
            marker = f"<!-- PPTX_OBJECT:{object_id};KIND:{kind};SOURCE:{source} -->"
            if text:
                blocks.extend([marker, text])
            if description:
                blocks.extend([f"<!-- PPTX_VISUAL_OBSERVATION:{object_id} -->", f"[视觉观察；非原文] {description}"])
    return "\n\n".join(blocks).strip() + "\n"


def _atomic_write(path: Path, content: str | bytes) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    encoding = None if isinstance(content, bytes) else "utf-8"
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temp_path.open(mode, encoding=encoding, newline="" if encoding else None) as stream:
            stream.write(content)
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _is_same_or_child(path: Path, parent: Path) -> bool:
    path = path.resolve()
    parent = parent.resolve()
    return path == parent or parent in path.parents


def extract_pptx(
    source_path: Path,
    raw_manifest_path: Path,
    raw_text_path: Path,
    visual_assets_dir: Path,
    image_dir: Path | None = None,
    placement_path: Path | None = None,
    include_speaker_notes: bool = False,
    ocr_language: str = "eng+chi_sim",
    render_timeout: int = 180,
    vision_capability: str = "available",
    vision_capability_evidence: str | None = None,
) -> dict[str, Any]:
    if vision_capability not in {"available", "unavailable"}:
        raise ValueError("vision_capability must be 'available' or 'unavailable'")
    evidence = vision_capability_evidence.strip() if isinstance(vision_capability_evidence, str) else ""
    if vision_capability_evidence is not None and not evidence:
        raise ValueError("vision_capability_evidence must not be empty when provided")
    if len(evidence) > 1_000:
        raise ValueError("vision_capability_evidence must be at most 1000 characters")
    if vision_capability == "unavailable" and (image_dir is not None or placement_path is not None):
        raise ValueError("Do not request formal PPTX image exports when vision_capability is unavailable")
    source = source_path.expanduser().resolve(strict=True)
    raw_manifest_path = raw_manifest_path.expanduser().resolve()
    raw_text_path = raw_text_path.expanduser().resolve()
    placement_resolved = placement_path.expanduser().resolve() if placement_path is not None else None
    output_files = [raw_manifest_path, raw_text_path, *([placement_resolved] if placement_resolved else [])]
    if source in output_files:
        raise ValueError("PPTX output path cannot overwrite the source file")
    if len({str(path).casefold() for path in output_files}) != len(output_files):
        raise ValueError("PPTX manifest, source text, and placement paths must be distinct")
    if image_dir is not None and placement_path is None:
        raise ValueError("--image-dir requires --placement-file")
    if image_dir is None and placement_path is not None:
        raise ValueError("--placement-file requires --image-dir")
    if source.suffix.lower() != ".pptx":
        raise PackageSafetyError("Only .pptx files are supported; macro-enabled formats are not accepted")
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise PackageSafetyError(f"PPTX exceeds the {MAX_SOURCE_BYTES // (1024 * 1024)} MiB input limit")
    initial_hash = sha256_file(source)
    package_info = inspect_package(source)
    if sha256_file(source) != initial_hash:
        raise RuntimeError("The source PPTX changed during package safety inspection")
    visual_root = visual_assets_dir.expanduser().resolve()
    visual_root.mkdir(parents=True, exist_ok=True)
    export_dir = image_dir.expanduser().resolve() if image_dir is not None else None
    for output_file in output_files:
        if _is_same_or_child(output_file, visual_root):
            raise ValueError("Manifest, source text, and placement files must be outside the visual-assets directory")
    if export_dir is not None and export_dir == source.parent:
        raise ValueError("Image export directory cannot be the source file's parent directory")
    if export_dir is not None:
        if export_dir == visual_root or _is_same_or_child(export_dir, visual_root) or _is_same_or_child(visual_root, export_dir):
            raise ValueError("Image export and temporary visual-assets directories must be separate")
        if any(_is_same_or_child(output_file, export_dir) for output_file in output_files):
            raise ValueError("Manifest, source text, and placement files must be outside the image export directory")
        export_dir.mkdir(parents=True, exist_ok=True)

    try:
        from pptx import Presentation
    except ImportError as exc:
        raise RuntimeError("python-pptx is required; install the pinned suite requirements") from exc

    try:
        presentation = Presentation(str(source))
    except Exception as exc:
        raise RuntimeError(f"python-pptx could not read the presentation: {exc}") from exc
    if not presentation.slides:
        raise RuntimeError("PPTX contains no slides")
    slide_width = int(presentation.slide_width)
    slide_height = int(presentation.slide_height)
    slides: list[dict[str, Any]] = []
    placement: list[dict[str, Any]] = []
    for slide_number, slide in enumerate(presentation.slides, start=1):
        hidden = str(getattr(slide._element, "get", lambda *_: None)("show") or "1").casefold() in {"0", "false", "no"}
        slide_record: dict[str, Any] = {
            "slide_number": slide_number,
            "visibility": "hidden" if hidden else "visible",
            "status": "not_processed_hidden" if hidden else "structure_pending_visual_review",
            "render_path": None,
            "render_size_px": None,
            "notes_present": False,
            "items": [],
            "uncovered_objects": [],
            "unresolved_items": [],
        }
        if hidden:
            slides.append(slide_record)
            continue

        background_id = f"slide-{slide_number:04d}-background"
        background_bounds: dict[str, float | int] = {
            "x": 0.0,
            "y": 0.0,
            "width": 1.0,
            "height": 1.0,
            "x_emu": 0,
            "y_emu": 0,
            "width_emu": slide_width,
            "height_emu": slide_height,
        }
        slide_record["items"].append(_make_item(background_id, "background", "pptx_background", confidence=None, bounds=background_bounds))
        background_nodes = [node for node in slide._element.iter() if _local_name(node.tag) == "bg"]
        for background_index, background_node in enumerate(background_nodes, start=1):
            slide_record["items"].extend(_extract_related_image(
                slide.part,
                background_node,
                f"{background_id}-image-{background_index}",
                "image",
                "pptx_background_image",
                slide_number,
                background_bounds,
                visual_root,
                export_dir,
                placement,
            ))
        try:
            slide_record["items"].extend(_extract_shape_items(
                slide.shapes,
                slide_number,
                slide_width,
                slide_height,
                visual_root,
                export_dir,
                placement,
                [0],
            ))
        except Exception as exc:
            slide_record["status"] = "structure_partial"
            slide_record["unresolved_items"].append(f"Slide structure extraction failed: {exc}")
        notes_present, notes_item = _extract_speaker_notes(slide, slide_number)
        slide_record["notes_present"] = notes_present
        if include_speaker_notes and notes_item is not None:
            slide_record["items"].append(notes_item)
        slide_record["visual_metrics"] = _slide_visual_metrics(slide_record)
        slides.append(slide_record)

    render_info = _render_slides(
        source,
        slides,
        visual_root / "slides",
        package_info["external_relationships"],
        timeout_seconds=render_timeout,
    )
    ocr_info = _ocr_slides(slides, ocr_language)
    for slide in slides:
        if slide["visibility"] == "visible":
            slide["required_review_object_ids"] = [item["object_id"] for item in slide["items"]]

    final_hash = sha256_file(source)
    if initial_hash != final_hash:
        raise RuntimeError("The source PPTX changed while it was being read; no result can be trusted")

    visible_slides = [slide for slide in slides if slide["visibility"] == "visible"]
    extracted_objects = sum(len(slide.get("items", [])) for slide in visible_slides)
    candidate_slides = [slide["slide_number"] for slide in visible_slides if slide.get("visual_metrics", {}).get("explanation_candidate")]
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "parser_version": PARSER_VERSION,
        "reader_skill_sha256": sha256_tree(Path(__file__).resolve().parent.parent),
        "vision_capability": vision_capability,
        "vision_capability_evidence": evidence or None,
        "source": {
            "path": str(source),
            "sha256": initial_hash,
            "size_bytes": source.stat().st_size,
            "slide_count": len(slides),
            "visible_slide_count": len(visible_slides),
            "hidden_slide_numbers": [slide["slide_number"] for slide in slides if slide["visibility"] == "hidden"],
        },
        "slide_size_emu": {"width": slide_width, "height": slide_height},
        "tools": {
            "parser": f"pptx_extractor.py {PARSER_VERSION}",
            "python_pptx": _distribution_version("python-pptx"),
            "pypdfium2": _distribution_version("pypdfium2"),
            "renderer": render_info,
            "ocr": ocr_info,
        },
        "package_safety": {
            "archive_member_count": package_info["archive_member_count"],
            "uncompressed_size_bytes": package_info["uncompressed_size_bytes"],
            "external_relationship_count": len(package_info["external_relationships"]),
            "external_relationships": package_info["external_relationships"],
            "macros_executed": False,
            "embedded_files_opened": False,
            "external_links_followed": False,
        },
        "visual_assets_dir": str(visual_root),
        "images_exported": export_dir is not None,
        "placement_file": str(placement_path.expanduser().resolve()) if placement_path is not None and export_dir is not None else None,
        "slides": slides,
        "coverage": {
            "visible_slides_processed": len(visible_slides),
            "visible_slides_total": len(visible_slides),
            "structural_objects_extracted": extracted_objects,
            "uncovered_slide_numbers": [slide["slide_number"] for slide in visible_slides],
            "visual_explanation_candidate_slides": candidate_slides,
        },
        "visual_review": {"status": "pending", "reviewer": None},
        "gate": "PARTIAL",
        "gate_reason": "Structural extraction completed; every visible slide still requires direct visual review",
    }
    if export_dir is not None and placement_path is not None:
        placement_path = placement_path.expanduser().resolve()
        _atomic_write(placement_path, json.dumps(placement, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(raw_manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(raw_text_path, _serialize_source_text(manifest))
    return manifest


def finalize_visual_review(
    raw_manifest_path: Path,
    visual_review_path: Path | None,
    final_manifest_path: Path,
    final_text_path: Path,
    vision_capability: str = "available",
    vision_capability_evidence: str | None = None,
) -> dict[str, Any]:
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
    final_manifest = final_manifest_path.expanduser().resolve()
    final_text = final_text_path.expanduser().resolve()
    if review_path is not None and review_path.stat().st_size > MAX_REVIEW_BYTES:
        raise ValueError("Visual-review JSON exceeds the size limit")
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("Unsupported raw PPTX manifest schema")
    raw_capability = raw.get("vision_capability")
    if raw_capability is not None and raw_capability != vision_capability:
        raise ValueError("vision_capability changed after PPTX extraction; rerun extract with the current host setting")
    raw_evidence = raw.get("vision_capability_evidence")
    if evidence and raw_evidence and evidence != raw_evidence:
        raise ValueError("vision_capability_evidence changed after PPTX extraction; rerun extract")
    reviewer: str | None = None
    review_slides: list[Any] = []
    if review_path is not None:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        if not isinstance(review, dict) or review.get("schema_version") != 1:
            raise ValueError("Visual-review JSON must use schema_version 1")
        reviewer_value = review.get("reviewer")
        review_slides_value = review.get("slides")
        if not isinstance(reviewer_value, str) or not reviewer_value.strip() or not isinstance(review_slides_value, list):
            raise ValueError("Visual-review JSON requires a reviewer and slides array")
        reviewer, review_slides = reviewer_value, review_slides_value
    by_number: dict[int, dict[str, Any]] = {}
    for item in review_slides:
        if not isinstance(item, dict) or not isinstance(item.get("slide_number"), int):
            raise ValueError("Each visual-review slide needs an integer slide_number")
        number = item["slide_number"]
        if number in by_number:
            raise ValueError(f"Duplicate visual review for slide {number}")
        by_number[number] = item

    result = json.loads(json.dumps(raw))
    source_path = Path(result.get("source", {}).get("path", "")).expanduser().resolve()
    if not source_path.is_file() or sha256_file(source_path) != result.get("source", {}).get("sha256"):
        raise ValueError("Source PPTX is missing or changed since structural extraction")
    input_paths = {raw_path, source_path, *([review_path] if review_path is not None else [])}
    if final_manifest == final_text or final_manifest in input_paths or final_text in input_paths:
        raise ValueError("Final manifest and source-text outputs must be distinct from each other and all inputs")
    visible = [slide for slide in result.get("slides", []) if slide.get("visibility") == "visible"]
    visible_numbers = {slide["slide_number"] for slide in visible}
    if vision_capability == "unavailable":
        slide_numbers = sorted(visible_numbers)
        for slide in visible:
            slide["structural_status"] = slide.get("status")
            slide["status"] = "skipped_no_vision"
            slide["visual_review_status"] = "skipped_no_vision"
            slide["unreviewed_object_ids"] = list(slide.get("required_review_object_ids", []))
            slide["uncovered_objects"] = list(slide["unreviewed_object_ids"])
            for item in slide.get("items", []):
                if item.get("source") == "tesseract_ocr":
                    item["visual_review_status"] = "skipped_no_vision"
        candidate_slides = list(result.get("coverage", {}).get("visual_explanation_candidate_slides", []))
        result["vision_capability"] = "unavailable"
        result["vision_capability_evidence"] = evidence or None
        result["visual_review"] = {
            "status": "skipped_no_vision", "reviewer": None, "visual_observation_count": 0,
            "reviewed_slide_numbers": [], "skipped_slide_numbers": slide_numbers,
            "capability_evidence": evidence or None,
        }
        result["coverage"]["uncovered_slide_numbers"] = slide_numbers
        result["coverage"]["unreviewed_due_to_no_vision_slide_numbers"] = slide_numbers
        result["coverage"]["unassessed_visual_explanation_candidate_slides"] = candidate_slides
        result["coverage"]["visual_explanation_candidate_slides"] = []
        result["images_exported"] = False
        result["gate"] = "SKIPPED_NO_VISION"
        result["gate_reason"] = (
            "The host does not provide image input; extracted text is available, but visual slide content was not reviewed"
        )
        placement_value = result.get("placement_file")
        if isinstance(placement_value, str) and placement_value:
            placement_path = Path(placement_value).expanduser().resolve()
            if placement_path in input_paths or placement_path in {final_manifest, final_text}:
                raise ValueError("Placement output must be distinct from source, manifests, and source text")
            visual_root = Path(result.get("visual_assets_dir", "")).expanduser().resolve()
            if _is_same_or_child(placement_path, visual_root):
                raise ValueError("Placement output must be outside the temporary visual-assets directory")
            _atomic_write(placement_path, "[]\n")
        source_text = _serialize_source_text(result)
        asset_records: list[dict[str, str]] = []
        for slide in result.get("slides", []):
            if slide.get("visibility") != "visible":
                continue
            for path_value in [slide.get("render_path"), *(item.get("asset_path") for item in slide.get("items", []))]:
                if path_value:
                    asset = Path(path_value).resolve()
                    if asset.is_file():
                        asset_records.append({"path": str(asset), "sha256": sha256_file(asset)})
        if isinstance(placement_value, str) and Path(placement_value).is_file():
            placement_path = Path(placement_value).resolve()
            asset_records.append({"path": str(placement_path), "sha256": sha256_file(placement_path)})
        result["processing_fingerprint"] = hashlib.sha256(json.dumps({
            "manifest": result,
            "source_text_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            "assets": asset_records,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        _atomic_write(final_manifest, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        _atomic_write(final_text, source_text)
        return result

    if review_path is None or reviewer is None:
        raise ValueError("Visual-review inputs are missing")
    result["vision_capability"] = "available"
    result["vision_capability_evidence"] = evidence or None
    if set(by_number) != visible_numbers:
        missing = sorted(visible_numbers - set(by_number))
        extra = sorted(set(by_number) - visible_numbers)
        raise ValueError(f"Visual review must include every visible slide; missing={missing}, extra={extra}")

    uncovered_slides: list[int] = []
    unresolved_items: list[dict[str, Any]] = []
    failed_slides: list[int] = []
    visual_observation_count = 0
    for slide in visible:
        number = slide["slide_number"]
        review_slide = by_number[number]
        render_path = slide.get("render_path")
        if not render_path or not Path(render_path).is_file():
            failed_slides.append(number)
            slide["status"] = "failed_render_missing"
            slide["uncovered_objects"] = ["rendered_slide"]
            continue
        expected_ids = set(slide.get("required_review_object_ids", []))
        checked_ids = review_slide.get("checked_object_ids")
        checked = set(checked_ids) if isinstance(checked_ids, list) and all(isinstance(value, str) for value in checked_ids) else set()
        missing_ids = sorted(expected_ids - checked)
        extra_ids = sorted(checked - expected_ids)
        declared_uncovered = review_slide.get("uncovered_objects", [])
        if not isinstance(declared_uncovered, list):
            raise ValueError(f"uncovered_objects must be an array for slide {number}")
        slide["uncovered_objects"] = sorted(set(missing_ids + [str(value) for value in declared_uncovered]))
        if extra_ids:
            slide["uncovered_objects"].extend(f"unrecognized_review_object:{value}" for value in extra_ids)
        requires_explanation = review_slide.get("requires_explanation")
        if not isinstance(requires_explanation, bool):
            slide["uncovered_objects"].append("explanation_routing_not_recorded")
        explanation_reason = review_slide.get("explanation_reason", "")
        if not isinstance(explanation_reason, str) or len(explanation_reason) > 2_000:
            raise ValueError(f"explanation_reason must be a string of at most 2000 characters for slide {number}")
        if requires_explanation and not explanation_reason.strip():
            slide["uncovered_objects"].append("explanation_reason_missing")
        slide["visual_review_requires_explanation"] = requires_explanation is True
        slide["visual_review_explanation_reason"] = explanation_reason.strip() if requires_explanation else None

        if review_slide.get("status") != "complete" or slide["uncovered_objects"]:
            if review_slide.get("status") != "complete" and not slide["uncovered_objects"]:
                slide["uncovered_objects"].append("visual_review_not_complete")
            slide["status"] = "partial"
            if slide["uncovered_objects"]:
                uncovered_slides.append(number)
        else:
            slide["status"] = "complete"

        observations = review_slide.get("observations", [])
        if not isinstance(observations, list):
            raise ValueError(f"observations must be an array for slide {number}")
        for observation_index, observation in enumerate(observations, start=1):
            if not isinstance(observation, dict):
                raise ValueError(f"Observation {observation_index} on slide {number} must be an object")
            object_id = observation.get("object_id")
            kind = observation.get("kind")
            if not isinstance(object_id, str) or object_id not in expected_ids:
                raise ValueError(f"Visual observation on slide {number} must cite a known object_id")
            if kind not in ALLOWED_OBSERVATION_KINDS:
                raise ValueError(f"Invalid visual observation kind on slide {number}: {kind}")
            text = observation.get("text", "")
            description = observation.get("description", "")
            uncertainty = observation.get("uncertainty")
            if not all(isinstance(value, str) for value in (text, description)):
                raise ValueError("Visual observation text and description must be strings")
            if max(len(text), len(description)) > 20_000:
                raise ValueError("Visual observation text is too long")
            confidence = observation.get("confidence")
            if confidence is not None and (not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
                raise ValueError("Visual observation confidence must be between 0 and 1")
            if uncertainty is not None and not isinstance(uncertainty, str):
                raise ValueError("Visual observation uncertainty must be a string or null")
            item = _make_item(
                object_id=f"{object_id}-visual-{observation_index}",
                kind=kind,
                source="visual_ocr" if kind == "ocr_text" else "visual_observation",
                text=text,
                description=description,
                confidence=confidence,
                instruction_like_content=bool(observation.get("instruction_like_content", False)),
                uncertainty=uncertainty,
                observed_object_id=object_id,
            )
            slide.setdefault("items", []).append(item)
            visual_observation_count += 1
            if kind == "uncertainty" or uncertainty or (confidence is not None and confidence < 0.55):
                unresolved_items.append({
                    "slide_number": number,
                    "item": uncertainty or description or text or f"Low-confidence {kind} observation for {object_id}",
                })

        slide_unresolved = review_slide.get("unresolved_items", [])
        if not isinstance(slide_unresolved, list) or not all(isinstance(value, str) for value in slide_unresolved):
            raise ValueError(f"unresolved_items must be an array of strings for slide {number}")
        if slide_unresolved:
            slide["unresolved_items"] = slide_unresolved
            unresolved_items.extend({"slide_number": number, "item": value} for value in slide_unresolved)
        for structural_unresolved in slide.get("unresolved_items", []):
            if structural_unresolved not in slide_unresolved:
                unresolved_items.append({"slide_number": number, "item": str(structural_unresolved)})

        for item in slide.get("items", []):
            if item.get("source") in {"visual_ocr", "visual_observation"}:
                continue
            if item.get("uncertainty") or (item.get("confidence") is not None and item["confidence"] <= 0):
                unresolved_items.append({
                    "slide_number": number,
                    "item": item.get("uncertainty") or f"Uncertain {item.get('kind')} object {item.get('object_id')}",
                })
        if any(item["slide_number"] == number for item in unresolved_items):
            slide["status"] = "partial"
            if number not in uncovered_slides:
                uncovered_slides.append(number)

    gate = "PASS"
    reasons: list[str] = []
    if failed_slides:
        gate = "FAIL"
        reasons.append("Rendered images are missing for one or more visible slides")
    elif uncovered_slides:
        gate = "PARTIAL"
        reasons.append("One or more visible slides or objects were not visually checked")
    elif unresolved_items:
        gate = "PARTIAL"
        reasons.append("Visual review contains unresolved items")
    result["visual_review"] = {
        "status": "complete" if gate == "PASS" else "partial" if gate == "PARTIAL" else "failed",
        "reviewer": reviewer.strip()[:200],
        "visual_observation_count": visual_observation_count,
        "reviewed_slide_numbers": sorted(slide["slide_number"] for slide in visible if slide.get("status") == "complete"),
        "capability_evidence": evidence or None,
    }
    result["coverage"]["uncovered_slide_numbers"] = sorted(set(uncovered_slides + failed_slides))
    result["coverage"]["unresolved_items"] = unresolved_items
    explanation_candidates = {
        slide["slide_number"]
        for slide in visible
        if slide.get("visual_metrics", {}).get("explanation_candidate")
        or slide.get("visual_review_requires_explanation")
    }
    result["coverage"]["visual_explanation_candidate_slides"] = sorted(explanation_candidates)
    result["gate"] = gate
    result["gate_reason"] = "; ".join(reasons) if reasons else "Every visible slide and extracted object has a complete visual review"
    source_text = _serialize_source_text(result)
    asset_records: list[dict[str, str]] = []
    assets_to_hash: set[Path] = set()
    for slide in result.get("slides", []):
        if slide.get("render_path"):
            assets_to_hash.add(Path(slide["render_path"]).resolve())
        for item in slide.get("items", []):
            for key in ("asset_path", "output_asset_path"):
                value = item.get(key)
                if isinstance(value, str) and value:
                    assets_to_hash.add(Path(value).resolve())
    placement_value = result.get("placement_file")
    if isinstance(placement_value, str) and placement_value:
        assets_to_hash.add(Path(placement_value).resolve())
    for asset in sorted(assets_to_hash, key=lambda value: str(value).casefold()):
        if not asset.is_file():
            raise ValueError(f"Referenced PPTX asset is missing: {asset}")
        asset_records.append({"path": str(asset), "sha256": sha256_file(asset)})
    fingerprint_payload = {
        "manifest": result,
        "source_text_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "assets": asset_records,
    }
    result["processing_fingerprint"] = hashlib.sha256(
        json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    _atomic_write(final_manifest, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(final_text, source_text)
    return result


def build_context_fingerprint(manifest_path: Path, explanation_path: Path | None = None) -> dict[str, Any]:
    manifest = json.loads(manifest_path.expanduser().resolve(strict=True).read_text(encoding="utf-8"))
    base = manifest.get("processing_fingerprint")
    if not isinstance(base, str) or not re.fullmatch(r"[0-9a-f]{64}", base):
        raise ValueError("Final PPTX manifest has no valid processing_fingerprint")
    explanation_hash = None
    if explanation_path is not None:
        explanation = explanation_path.expanduser().resolve(strict=True)
        explanation_hash = sha256_file(explanation)
    payload = {"base_processing_fingerprint": base, "visual_explanations_sha256": explanation_hash}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"pptx_processing_fingerprint": digest, **payload}


def _add_extract_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", type=Path, help="Input .pptx file")
    parser.add_argument("--raw-manifest", required=True, type=Path, help="Output path for structural manifest JSON")
    parser.add_argument("--raw-text", required=True, type=Path, help="Output path for structural source text")
    parser.add_argument("--visual-assets-dir", required=True, type=Path, help="Output directory for slide renders and extracted image objects")
    parser.add_argument("--image-dir", type=Path, help="Optional final output directory for embedded pictures when include_images is enabled")
    parser.add_argument("--placement-file", type=Path, help="Optional final image-placement JSON path")
    parser.add_argument("--vision-capability", required=True, choices=("available", "unavailable"))
    parser.add_argument("--vision-capability-evidence", required=True, help="Short evidence from the current host image-input path")
    parser.add_argument("--include-speaker-notes", action="store_true", help="Extract notes as untrusted source data")
    parser.add_argument("--ocr-language", default="eng+chi_sim", help="Tesseract languages, when Tesseract is installed")
    parser.add_argument("--render-timeout", type=int, default=180, help="LibreOffice rendering timeout in seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    extract_parser = subparsers.add_parser("extract", help="Safely extract structures and render visible slides")
    _add_extract_arguments(extract_parser)
    finalize_parser = subparsers.add_parser("finalize", help="Validate visual-review coverage and write the final handoff")
    finalize_parser.add_argument("--raw-manifest", required=True, type=Path)
    finalize_parser.add_argument("--visual-review", type=Path)
    finalize_parser.add_argument("--vision-capability", required=True, choices=("available", "unavailable"))
    finalize_parser.add_argument("--vision-capability-evidence", required=True, help="Short evidence from the current host image-input path")
    finalize_parser.add_argument("--manifest", required=True, type=Path)
    finalize_parser.add_argument("--source-text", required=True, type=Path)
    fingerprint_parser = subparsers.add_parser("fingerprint", help="Hash the reviewed PPTX context without storing its content in cache state")
    fingerprint_parser.add_argument("--manifest", required=True, type=Path)
    fingerprint_parser.add_argument("--visual-explanations", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "extract":
            manifest = extract_pptx(
                args.source,
                args.raw_manifest,
                args.raw_text,
                args.visual_assets_dir,
                image_dir=args.image_dir,
                placement_path=args.placement_file,
                include_speaker_notes=args.include_speaker_notes,
                ocr_language=args.ocr_language,
                render_timeout=args.render_timeout,
                vision_capability=args.vision_capability,
                vision_capability_evidence=args.vision_capability_evidence,
            )
            print(json.dumps({
                "gate": manifest["gate"],
                "slide_count": manifest["source"]["slide_count"],
                "visible_slide_count": manifest["source"]["visible_slide_count"],
                "render_status": manifest["tools"]["renderer"]["status"],
                "visual_explanation_candidate_slides": manifest["coverage"]["visual_explanation_candidate_slides"],
                "raw_manifest": str(args.raw_manifest.resolve()),
                "raw_text": str(args.raw_text.resolve()),
                "visual_assets_dir": str(args.visual_assets_dir.resolve()),
            }, ensure_ascii=False))
            return 0
        if args.command == "fingerprint":
            print(json.dumps(build_context_fingerprint(args.manifest, args.visual_explanations), ensure_ascii=False))
            return 0
        manifest = finalize_visual_review(
            args.raw_manifest, args.visual_review, args.manifest, args.source_text,
            args.vision_capability, args.vision_capability_evidence,
        )
        print(json.dumps({
            "gate": manifest["gate"],
            "visible_slide_count": manifest["source"]["visible_slide_count"],
            "reviewed_slide_count": len(manifest["visual_review"]["reviewed_slide_numbers"]),
            "skipped_slide_numbers": manifest["visual_review"].get("skipped_slide_numbers", []),
            "uncovered_slide_numbers": manifest["coverage"]["uncovered_slide_numbers"],
            "unresolved_items": manifest["coverage"].get("unresolved_items", []),
            "manifest": str(args.manifest.resolve()),
            "source_text": str(args.source_text.resolve()),
        }, ensure_ascii=False))
        return 0 if manifest["gate"] in {"PASS", "SKIPPED_NO_VISION"} else 3 if manifest["gate"] == "PARTIAL" else 2
    except (OSError, ValueError, RuntimeError, PackageSafetyError, zipfile.BadZipFile) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

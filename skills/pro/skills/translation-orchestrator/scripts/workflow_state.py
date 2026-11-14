#!/usr/bin/env python3
"""Track workflow checkpoints by hashing inputs and produced artifacts.

The state file stores selected settings, paths, hashes, sizes, timestamps, and
optional host-reported usage only; it never copies source or translated text.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
CHUNK_SIZE = 1024 * 1024
PRO_TIER = "pro"
PRO_QUALITY_PROFILE = "pro-full-content-audit-v1"
DECISION_LOG_PREFIX = ".pro-decisions-"
GATE_VALUES = {"NONE", "PASS", "FAIL", "PARTIAL", "SKIPPED_NO_VISION"}

STAGE_ORDER = (
    "parse_pdf", "review_pdf", "explain_pdf",
    "parse_pptx", "review_pptx", "explain_pptx",
    "translate", "quiz", "audit_translation", "audit_quiz",
    "publish_html", "publish_docx", "publish_md",
)
NON_SKILL_STAGE_ACTORS = {"publish_md": "shared-markdown-builder"}

STAGE_SKILLS = {
    "parse_pdf": ("foreign-academic-pdf-reader",),
    "review_pdf": ("foreign-academic-pdf-reader",),
    "explain_pdf": ("foreign-academic-visual-explainer",),
    "parse_pptx": ("foreign-academic-pptx-reader",),
    "review_pptx": ("foreign-academic-pptx-reader",),
    "explain_pptx": ("foreign-academic-visual-explainer",),
    "translate": ("foreign-academic-lesson-translator",),
    "quiz": ("foreign-academic-quiz-generator", "foreign-academic-solution-explainer"),
    "audit_translation": ("foreign-academic-quality-auditor",),
    "audit_quiz": ("foreign-academic-quality-auditor",),
    "publish_html": ("foreign-academic-html-publisher",),
    "publish_docx": ("foreign-academic-docx-publisher",),
}


def stage_skill_names(stage: str, task: dict[str, Any]) -> tuple[str, ...]:
    """Return only the Skill selected for a routed translation stage."""
    if stage == "translate" and task.get("translation_route") == "quick":
        return ("foreign-academic-quick-translator",)
    return STAGE_SKILLS.get(stage, ())


def validate_pro_metadata(task: dict[str, Any]) -> None:
    """Reject task/cache metadata from another tier before checking any stage."""
    if task.get("workflow_tier") != PRO_TIER:
        raise ValueError("Pro tasks must set workflow_tier to 'pro'; another tier's manifest cannot be reused")
    if task.get("quality_profile") != PRO_QUALITY_PROFILE:
        raise ValueError(f"Pro tasks must set quality_profile to {PRO_QUALITY_PROFILE!r}")
    output_dir = task.get("output_dir")
    if not isinstance(output_dir, str) or not output_dir.strip():
        raise ValueError("Pro tasks require an absolute output_dir")
    if not Path(output_dir).is_absolute():
        raise ValueError("Pro output_dir must be absolute")
    output_path = Path(output_dir).expanduser().resolve()
    runtime_value = task.get("shared_runtime")
    expected_runtime = Path(__file__).resolve().parent.parent
    if not isinstance(runtime_value, str) or Path(runtime_value).expanduser().resolve() != expected_runtime:
        raise ValueError(f"shared_runtime must resolve to this Pro bundle: {expected_runtime}")
    formats = task.get("output_formats")
    if not isinstance(formats, list) or not formats:
        raise ValueError("Pro tasks require at least one selected output format")
    expected = {
        "state_file": output_path / ".translation-state-pro.json",
        "cache_dir": output_path / ".translator-cache-pro",
        "cache_state_file": output_path / ".translator-cache-pro" / "workflow-state.json",
    }
    for field, path in expected.items():
        value = task.get(field)
        if not isinstance(value, str) or Path(value).expanduser().resolve() != path:
            raise ValueError(f"{field} must point to the Pro-only path {path}")
    decision_log = task.get("decision_log_file")
    run_id = task.get("workflow_run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        raise ValueError("Pro tasks require a safe workflow_run_id")
    expected_log = output_path / f"{DECISION_LOG_PREFIX}{run_id}.jsonl"
    if not isinstance(decision_log, str) or Path(decision_log).expanduser().resolve() != expected_log:
        raise ValueError(f"decision_log_file must point to this run's Pro-only log: {expected_log}")
    for field in ("cache_core_markdown", "cache_coverage_index_file", "cache_quiz_file"):
        value = task.get(field)
        if isinstance(value, str) and value.strip():
            try:
                Path(value).expanduser().resolve().relative_to(expected["cache_dir"])
            except ValueError as exc:
                raise ValueError(f"{field} must stay inside .translator-cache-pro") from exc
    source_kind = str(task.get("source_kind", "")).lower()
    if source_kind in {"pdf", "pptx"}:
        if task.get("vision_capability") not in {"available", "unavailable"}:
            raise ValueError("PDF/PPTX Pro tasks require the current host's vision_capability")
        evidence = task.get("vision_capability_evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("PDF/PPTX Pro tasks require concise vision_capability_evidence")
        if task.get("vision_capability") == "unavailable":
            for field in ("pdf_visual_explanations_file", "pptx_visual_explanations_file"):
                if isinstance(task.get(field), str) and task[field].strip():
                    raise ValueError("Visual explanations cannot be configured when vision_capability is unavailable")


def validate_pro_invocation(task_path: Path, state_path: Path, task: dict[str, Any]) -> None:
    validate_pro_metadata(task)
    output_dir = Path(task["output_dir"]).expanduser().resolve()
    if task_path.expanduser().resolve() != output_dir / ".translation-task-pro.json":
        raise ValueError("Pro task manifest must be output_dir/.translation-task-pro.json")
    if state_path.expanduser().resolve() != output_dir / ".translation-state-pro.json":
        raise ValueError("Pro run state must be output_dir/.translation-state-pro.json")


def validate_cache_state_path(cache_state_path: Path, task: dict[str, Any]) -> None:
    expected = Path(task["cache_state_file"]).expanduser().resolve()
    if cache_state_path.expanduser().resolve() != expected:
        raise ValueError(f"Persistent Pro cache state must be {expected}")


CONTENT_RUNTIME_FILES = (
    "scripts/text_extractor.py",
    "scripts/utils.py",
    "requirements.txt",
)

BUILDER_RUNTIME_PATHS = (
    "scripts/builder.py",
    "scripts/builders",
    "templates",
    "requirements.txt",
)

OFFICE_MATH_XSL_CANDIDATES = (
    r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL",
    r"C:\Program Files (x86)\Microsoft Office\root\Office16\MML2OMML.XSL",
    r"C:\Program Files\Microsoft Office\root\Office15\MML2OMML.XSL",
    r"C:\Program Files (x86)\Microsoft Office\root\Office15\MML2OMML.XSL",
    r"C:\Program Files\Microsoft Office\root\Office14\MML2OMML.XSL",
    r"C:\Program Files\Microsoft Office\Office16\MML2OMML.XSL",
    r"C:\Program Files\Microsoft Office\Office15\MML2OMML.XSL",
)


def digest_path(path: Path) -> dict[str, Any]:
    """Hash one file or a directory tree without loading it all into memory."""
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")

    hasher = hashlib.sha256()
    total_bytes = 0
    if path.is_file():
        with path.open("rb") as stream:
            while chunk := stream.read(CHUNK_SIZE):
                total_bytes += len(chunk)
                hasher.update(chunk)
        return {"path": str(path), "kind": "file", "sha256": hasher.hexdigest(), "size_bytes": total_bytes}

    for child in sorted(
        item
        for item in path.rglob("*")
        if item.is_file() and "__pycache__" not in item.parts and item.suffix.lower() != ".pyc"
    ):
        relative = child.relative_to(path).as_posix().encode("utf-8")
        child_hash = hashlib.sha256()
        child_bytes = 0
        with child.open("rb") as stream:
            while chunk := stream.read(CHUNK_SIZE):
                child_bytes += len(chunk)
                child_hash.update(chunk)
        hasher.update(relative)
        hasher.update(b"\0")
        hasher.update(child_hash.digest())
        total_bytes += child_bytes
    return {"path": str(path), "kind": "directory", "sha256": hasher.hexdigest(), "size_bytes": total_bytes}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def parse_keys(raw: str) -> list[str]:
    return [key.strip() for key in raw.split(",") if key.strip()]


def get_config_value(task: dict[str, Any], key: str) -> Any:
    """Read a top-level or dotted nested key from the task manifest."""
    value: Any = task
    for part in key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def resolve_config(task: dict[str, Any], config_keys: list[str], fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve configured values, hydrating only missing values from a matching checkpoint."""
    fallback = fallback or {}
    resolved: dict[str, Any] = {}
    for key in sorted(set(config_keys)):
        value = get_config_value(task, key)
        if value is None and key in fallback:
            value = fallback[key]
        encoded_value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if len(encoded_value.encode("utf-8")) > 4096:
            raise ValueError(f"Config value is too large to store safely: {key}")
        resolved[key] = value
    return resolved


def build_signature(stage: str, stage_version: str, config: dict[str, Any], inputs: list[dict[str, Any]]) -> str:
    payload = {
        "stage": stage,
        "stage_version": stage_version,
        "config": config,
        "inputs": inputs,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def is_enabled(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"})


def resolve_task_path(task: dict[str, Any], key: str) -> Path | None:
    """Resolve a task path relative to project_root, as specified by the task contract."""
    value = task.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value).expanduser()
    project_root = task.get("project_root")
    if not path.is_absolute() and isinstance(project_root, str) and project_root.strip():
        path = Path(project_root).expanduser() / path
    return path.resolve()


def _source_suffix(task: dict[str, Any]) -> str:
    source = task.get("source_file")
    return Path(source).suffix.lower() if isinstance(source, str) and source.strip() else ""


def _stage_distributions(stage: str, task: dict[str, Any], config: dict[str, Any]) -> list[str]:
    """Return installed packages whose behavior can affect this stage."""
    packages: list[str] = []
    suffix = _source_suffix(task)
    if stage in {"translate", "quiz", "audit_translation", "audit_quiz"}:
        packages.append("chardet")
        packages.extend({".pdf": ["pdfplumber", "pypdf"], ".docx": ["python-docx"], ".txt": ["chardet"]}.get(suffix, []))
    if stage == "translate" and str(config.get("glossary_mode", "")).strip().lower() == "system_glossary":
        packages.append("chardet")
    if stage == "translate" and is_enabled(config.get("include_images")) and suffix == ".pdf":
        packages.extend(("pdfplumber", "pypdf", "Pillow"))
    if stage == "parse_pptx":
        packages.extend(("python-pptx", "lxml", "Pillow", "pypdfium2"))
    if stage == "parse_pdf":
        packages.extend(("pypdf", "pdfplumber", "pypdfium2", "Pillow"))
    if stage == "publish_html":
        packages.append("markdown")
    elif stage == "publish_docx":
        packages.extend(("python-docx", "markdown", "lxml", "Pillow", "matplotlib", "latex2mathml"))
    return sorted(set(packages), key=str.casefold)


def runtime_fingerprint(stage: str, task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Fingerprint interpreter, relevant installed libraries, and optional Office formula backend."""
    packages: dict[str, str | None] = {}
    for package in _stage_distributions(stage, task, config):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None

    formula_xslt: list[dict[str, Any]] = []
    if stage == "publish_docx":
        for candidate in OFFICE_MATH_XSL_CANDIDATES:
            path = Path(candidate)
            if path.is_file():
                formula_xslt.append(digest_path(path))

    external_tools: dict[str, Any] = {}
    if stage in {"parse_pptx", "parse_pdf"}:
        tool_names = ("soffice", "libreoffice", "tesseract") if stage == "parse_pptx" else ("tesseract",)
        for name in tool_names:
            executable = shutil.which(name)
            if executable is None:
                continue
            details: dict[str, Any] = {"version": None}
            try:
                result = subprocess.run(
                    [executable, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                version = (result.stdout or result.stderr).strip()
                details["version"] = version[:500] if version else None
            except (OSError, subprocess.TimeoutExpired):
                details["version_error"] = True
            if name == "tesseract":
                try:
                    languages_result = subprocess.run(
                        [executable, "--list-langs"], capture_output=True, text=True, timeout=10, check=False,
                    )
                    available_languages = sorted({line.strip() for line in languages_result.stdout.splitlines()
                                                  if line.strip() and not line.lstrip().startswith("List of available languages")})
                    details["available_languages"] = available_languages if languages_result.returncode == 0 else None
                except (OSError, subprocess.TimeoutExpired):
                    details["available_languages"] = None
                try:
                    tessdata_result = subprocess.run(
                        [executable, "--print-tessdata-dir"], capture_output=True, text=True, timeout=10, check=False,
                    )
                    tessdata_value = tessdata_result.stdout.strip()
                    tessdata_dir = Path(tessdata_value).expanduser() if tessdata_result.returncode == 0 and tessdata_value else None
                    requested_languages = str(config.get("ocr_language") or "eng+chi_sim").split("+")
                    details["traineddata"] = {
                        language.strip(): digest_path(tessdata_dir / f"{language.strip()}.traineddata")
                        if language.strip() and tessdata_dir and (tessdata_dir / f"{language.strip()}.traineddata").is_file()
                        else None
                        for language in requested_languages if language.strip()
                    }
                except (OSError, subprocess.TimeoutExpired):
                    details["traineddata"] = None
            external_tools[name] = details

    payload = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": packages,
        "office_math_xslt": formula_xslt,
        "external_tools": external_tools,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "path": f"runtime://{stage}",
        "kind": "runtime",
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "size_bytes": len(encoded),
    }


def html_output_inventory_fingerprint(task: dict[str, Any]) -> dict[str, Any] | None:
    """Fingerprint the other HTML paths shown in the HTML reader's output file tree."""
    output_dir = resolve_task_path(task, "output_dir")
    if output_dir is None:
        return None
    base_name = task.get("base_name")
    if not isinstance(base_name, str) or not base_name.strip():
        base_name = "translated_doc"
    current_output = (output_dir / f"{base_name}.html").resolve()
    output_root = next((parent for parent in current_output.parents if parent.name.casefold() == "output"), None)
    html_paths: list[str] = []
    if output_root is not None and output_root.is_dir():
        for path in output_root.rglob("*.html"):
            if not path.is_file() or path.resolve() == current_output:
                continue
            try:
                html_paths.append(path.resolve().relative_to(output_root.resolve()).as_posix())
            except (ValueError, OSError):
                continue
    payload = {
        "current_output": str(current_output),
        "output_root": str(output_root.resolve()) if output_root is not None else None,
        "other_html_paths": sorted(html_paths, key=str.casefold),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "path": "runtime://html-output-inventory",
        "kind": "runtime",
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "size_bytes": len(encoded),
    }


def stage_dependency_paths(task: dict[str, Any], stage: str, config: dict[str, Any]) -> list[Path]:
    """Return project files whose contents can change this stage's result."""
    runtime_value = task.get("shared_runtime")
    runtime = Path(runtime_value).expanduser() if isinstance(runtime_value, str) and runtime_value.strip() else Path(__file__).resolve().parent.parent
    runtime = runtime.resolve()
    sibling_root = runtime.parent

    dependencies: list[Path] = []
    if stage in STAGE_SKILLS or stage == "publish_md":
        dependencies.append(runtime / "scripts" / "workflow_state.py")
    if stage in {"translate", "quiz", "audit_translation", "audit_quiz"}:
        dependencies.extend(runtime / relative for relative in CONTENT_RUNTIME_FILES)

    source_kind = _source_suffix(task)
    if source_kind == ".pptx" and stage == "review_pptx":
        for key in ("pptx_raw_manifest_file", "visual_assets_dir"):
            path = resolve_task_path(task, key)
            if path is not None:
                dependencies.append(path)
    if source_kind == ".pdf" and stage == "review_pdf":
        for key in ("pdf_raw_manifest_file", "visual_assets_dir"):
            path = resolve_task_path(task, key)
            if path is not None:
                dependencies.append(path)
    if source_kind == ".pptx" and stage == "explain_pptx":
        for key in ("pptx_manifest_file", "visual_assets_dir"):
            path = resolve_task_path(task, key)
            if path is not None:
                dependencies.append(path)
    if source_kind == ".pdf" and stage == "explain_pdf":
        for key in ("pdf_manifest_file", "visual_assets_dir"):
            path = resolve_task_path(task, key)
            if path is not None:
                dependencies.append(path)
    if stage in STAGE_SKILLS or stage == "publish_md":
        # The orchestrator contract and handoff rules affect every routed stage.
        dependencies.extend((runtime / "SKILL.md", runtime / "references" / "task-handoff.md"))
        # Hash each selected Skill directory so references, examples, and future support files
        # cannot silently change behavior while a cached result is reused.
        dependencies.extend(sibling_root / skill for skill in stage_skill_names(stage, task))

    if stage == "translate":
        if str(config.get("glossary_mode", "")).strip().lower() == "system_glossary":
            dependencies.extend((runtime / "scripts" / "term_catcher.py", runtime / "scripts" / "glossary_loader.py"))
            discipline = config.get("discipline")
            if discipline:
                dependencies.append(runtime / "glossaries" / str(discipline))
    if stage == "translate" and is_enabled(config.get("include_images")):
        for key in ("image_dir", "placement_file"):
            asset_path = resolve_task_path(task, key)
            if asset_path is not None:
                dependencies.append(asset_path)

    if stage in {"publish_html", "publish_docx"}:
        for key in ("image_dir", "placement_file"):
            asset_path = resolve_task_path(task, key)
            if asset_path is not None:
                dependencies.append(asset_path)

    if stage in {"publish_html", "publish_docx", "publish_md"}:
        dependencies.extend(runtime / relative for relative in BUILDER_RUNTIME_PATHS)

    # Stable de-duplication avoids hashing a file twice when a caller also passed it via --inputs.
    unique: list[Path] = []
    seen: set[str] = set()
    for dependency in dependencies:
        resolved = dependency.resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return unique


def combine_inputs(inputs: list[Path], dependencies: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in [*inputs, *dependencies]:
        resolved = path.expanduser().resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return unique


def stage_context(state: dict[str, Any], stage: str, task: dict[str, Any], config_keys: list[str], inputs: list[Path]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validate_pro_metadata(task)
    capability_stages = {"parse_pdf", "parse_pptx", "review_pdf", "review_pptx", "explain_pdf", "explain_pptx"}
    model_stages = {"review_pdf", "review_pptx", "explain_pdf", "explain_pptx"}
    if stage in capability_stages:
        capability = task.get("vision_capability")
        evidence = task.get("vision_capability_evidence")
        if capability not in {"available", "unavailable"}:
            raise ValueError("PDF/PPTX visual stages require an explicit vision_capability of available or unavailable")
        if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 1_000:
            raise ValueError("PDF/PPTX visual stages require concise vision_capability_evidence from the current host")
        required_config = ["vision_capability", "vision_capability_evidence"]
        if stage in model_stages:
            required_config.append("vision_model_id")
        config_keys = sorted(set([*config_keys, *required_config]))
    base_inputs = combine_inputs(inputs, [])
    base_fingerprints = [digest_path(path) for path in base_inputs]
    previous = state["stages"].get(stage, {})
    fallback: dict[str, Any] = {}
    saved_inputs = previous.get("inputs", []) if isinstance(previous, dict) else []
    if isinstance(saved_inputs, list) and saved_inputs[: len(base_fingerprints)] == base_fingerprints:
        saved_config = previous.get("config")
        if isinstance(saved_config, dict):
            fallback = saved_config
    if stage in capability_stages:
        non_hydratable = ["vision_capability", "vision_capability_evidence"]
        if stage in model_stages:
            non_hydratable.append("vision_model_id")
        for key in non_hydratable:
            fallback.pop(key, None)
    config_keys = sorted(set([*config_keys, "workflow_tier", "quality_profile", "cache_dir"]))
    config = resolve_config(task, config_keys, fallback)
    all_inputs = combine_inputs(base_inputs, stage_dependency_paths(task, stage, config))
    input_fingerprints = [digest_path(path) for path in all_inputs]
    input_fingerprints.append(runtime_fingerprint(stage, task, config))
    if stage == "publish_html":
        inventory = html_output_inventory_fingerprint(task)
        if inventory is not None:
            input_fingerprints.append(inventory)
    return input_fingerprints, config


def validate_gate(task: dict[str, Any], stage: str, gate: str) -> None:
    if gate not in GATE_VALUES:
        raise ValueError(f"Unknown gate status for {stage}: {gate}")
    if stage in {"audit_translation", "audit_quiz", "publish_html", "publish_docx", "publish_md"} and gate != "PASS":
        raise ValueError(f"{stage} can be marked only after its independent audit or format gate is PASS")
    if stage in {"review_pdf", "review_pptx"}:
        capability = task.get("vision_capability")
        if capability == "available" and gate != "PASS":
            raise ValueError(f"{stage} requires a completed page-by-page visual gate with PASS")
        if capability == "unavailable" and gate != "SKIPPED_NO_VISION":
            raise ValueError(f"{stage} must record SKIPPED_NO_VISION when the current host cannot receive page pixels")
    elif gate in {"FAIL", "PARTIAL", "SKIPPED_NO_VISION"}:
        raise ValueError(f"{stage} cannot be marked complete with gate {gate}")


def is_stage_complete(state: dict[str, Any], stage: str, task: dict[str, Any]) -> bool:
    record = state.get("stages", {}).get(stage)
    if not isinstance(record, dict):
        return False
    try:
        validate_gate(task, stage, str(record.get("gate", "NONE")))
    except ValueError:
        return False
    outputs = record.get("outputs")
    return isinstance(outputs, list) and bool(outputs)


def quiz_selected(task: dict[str, Any]) -> bool:
    levels = task.get("quiz_levels")
    return bool(task.get("quiz_enabled") is True or (isinstance(levels, list) and levels))


def source_reader_stages(task: dict[str, Any]) -> list[str]:
    source_kind = str(task.get("source_kind", "")).lower()
    if source_kind == "pdf":
        stages = ["parse_pdf", "review_pdf"]
        if task.get("vision_capability") == "available" and isinstance(task.get("pdf_visual_explanations_file"), str) and task["pdf_visual_explanations_file"].strip():
            stages.append("explain_pdf")
        return stages
    if source_kind == "pptx":
        stages = ["parse_pptx", "review_pptx"]
        if task.get("vision_capability") == "available" and isinstance(task.get("pptx_visual_explanations_file"), str) and task["pptx_visual_explanations_file"].strip():
            stages.append("explain_pptx")
        return stages
    return []


def required_stages(task: dict[str, Any]) -> list[str]:
    stages = source_reader_stages(task)
    stages.append("translate")
    if quiz_selected(task):
        stages.append("quiz")
    stages.append("audit_translation")
    if quiz_selected(task):
        stages.append("audit_quiz")
    formats = task.get("output_formats", ["md"])
    if not isinstance(formats, list) or not formats:
        raise ValueError("output_formats must be a non-empty list containing only selected formats")
    format_stages = {"html": "publish_html", "docx": "publish_docx", "md": "publish_md"}
    for output_format in formats:
        if output_format not in format_stages:
            raise ValueError(f"Unsupported Pro output format: {output_format}")
        stages.append(format_stages[output_format])
    return stages


def stage_dependencies(stage: str, task: dict[str, Any]) -> list[str]:
    reader_stages = source_reader_stages(task)
    if stage == "review_pdf":
        return ["parse_pdf"]
    if stage == "explain_pdf":
        return ["review_pdf"]
    if stage == "review_pptx":
        return ["parse_pptx"]
    if stage == "explain_pptx":
        return ["review_pptx"]
    if stage in {"translate", "quiz"}:
        return reader_stages
    if stage == "audit_translation":
        return ["translate"]
    if stage == "audit_quiz":
        return ["quiz"]
    if stage.startswith("publish_"):
        dependencies = ["audit_translation"]
        if quiz_selected(task):
            dependencies.append("audit_quiz")
        return dependencies
    return []


def eligible_next_stages(state: dict[str, Any], task: dict[str, Any]) -> list[str]:
    required = required_stages(task)
    return [
        stage for stage in STAGE_ORDER
        if stage in required
        and not is_stage_complete(state, stage, task)
        and all(is_stage_complete(state, dependency, task) for dependency in stage_dependencies(stage, task))
    ]


def unresolved_dependencies(state: dict[str, Any], task: dict[str, Any]) -> dict[str, list[str]]:
    pending: dict[str, list[str]] = {}
    for stage in required_stages(task):
        if is_stage_complete(state, stage, task):
            continue
        missing = [dependency for dependency in stage_dependencies(stage, task) if not is_stage_complete(state, dependency, task)]
        if missing:
            pending[stage] = missing
    return pending


def authorize_stage_action(state: dict[str, Any], task: dict[str, Any], stage: str, action: str) -> None:
    """Require the previous redecision to authorize each new stage or cached mark."""
    decisions = state.get("decisions", [])
    if not decisions:
        if state.get("stages") or state.get("runs"):
            raise ValueError(f"Record a Pro redecision before starting or marking {stage}")
        eligible = eligible_next_stages(state, task)
        if stage not in eligible:
            raise ValueError(f"{stage} is not an eligible first Pro stage; eligible stages are {eligible}")
        return
    previous = decisions[-1]
    decision = previous.get("decision", {})
    if decision.get("action") == "start_stage" and decision.get("next_stage") == stage:
        return
    if decision.get("action") == "continue_stage" and decision.get("stage") == stage:
        return
    if action == "retry" and decision.get("action") == "stop_for_repair" and previous.get("completed_stage") == stage:
        return
    raise ValueError(f"{action} for {stage} is not authorized by the latest Pro redecision")


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "workflow_tier": PRO_TIER, "stages": {}, "runs": {}, "decisions": []}
    try:
        state = load_json(path)
    except ValueError:
        return {"schema_version": SCHEMA_VERSION, "stages": {}, "runs": {}}
    if state.get("schema_version") != SCHEMA_VERSION or not isinstance(state.get("stages"), dict):
        return {"schema_version": SCHEMA_VERSION, "workflow_tier": PRO_TIER, "stages": {}, "runs": {}, "decisions": []}
    if state.get("workflow_tier") not in (None, PRO_TIER):
        raise ValueError("Cross-tier workflow state rejected; Pro will not read another tier's state")
    if state.get("workflow_tier") is None:
        # A pre-Pro state file at the Pro path is never a valid source of checkpoints.
        return {"schema_version": SCHEMA_VERSION, "workflow_tier": PRO_TIER, "stages": {}, "runs": {}, "decisions": []}
    if not isinstance(state.get("runs"), dict):
        state["runs"] = {}
    if not isinstance(state.get("decisions"), list):
        state["decisions"] = []
    return state


def write_state(path: Path, state: dict[str, Any]) -> None:
    state["workflow_tier"] = PRO_TIER
    state.setdefault("decisions", [])
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", required=True, type=Path, help="Workflow state JSON path")
    parser.add_argument("--task", required=True, type=Path, help="Current task manifest JSON path")
    parser.add_argument("--stage", required=True, help="Stage key, such as translate or publish_html")
    parser.add_argument("--inputs", required=True, nargs="+", type=Path, help="Files or folders this stage depends on")
    parser.add_argument("--config-keys", default="", help="Comma-separated task keys that affect this stage")
    parser.add_argument("--stage-version", default="1", help="Increment when this stage behavior changes")


def command_check(args: argparse.Namespace) -> int:
    task = load_json(args.task)
    validate_pro_invocation(args.task, args.state, task)
    candidates = [
        ("run_state", read_state(args.state)),
        ("cache_state", read_state(Path(task["cache_state_file"]))),
    ]
    result: dict[str, Any] = {"stage": args.stage, "reusable": False, "reason": "no_checkpoint"}
    last_reason = "no_checkpoint"
    for source, state in candidates:
        record = state["stages"].get(args.stage)
        if not isinstance(record, dict):
            continue
        try:
            input_fingerprints, config = stage_context(
                state, args.stage, task, parse_keys(args.config_keys), args.inputs
            )
        except FileNotFoundError as exc:
            last_reason = "input_missing"
            result.update({"missing_input": str(exc)})
            continue
        signature = build_signature(args.stage, args.stage_version, config, input_fingerprints)
        result["resolved_config"] = config
        if record.get("signature") != signature:
            last_reason = "inputs_or_settings_changed"
            continue
        saved_outputs = record.get("outputs")
        if not isinstance(saved_outputs, list) or not saved_outputs:
            last_reason = "no_recorded_outputs"
            continue
        try:
            current_outputs = [digest_path(Path(item["path"])) for item in saved_outputs]
        except (KeyError, TypeError, FileNotFoundError):
            last_reason = "output_missing"
            continue
        if current_outputs != saved_outputs:
            last_reason = "output_changed"
            continue
        try:
            validate_gate(task, args.stage, str(record.get("gate", "NONE")))
        except ValueError:
            last_reason = "quality_gate_missing_or_invalid"
            continue
        result.update({
            "reusable": True,
            "reason": "signature_and_outputs_match",
            "source": source,
            "outputs": current_outputs,
            "gate": record.get("gate", "NONE"),
        })
        break
    else:
        result["reason"] = last_reason
    print(json.dumps(result, ensure_ascii=False))
    return 0


def command_start(args: argparse.Namespace) -> int:
    task = load_json(args.task)
    validate_pro_invocation(args.task, args.state, task)
    state = read_state(args.state)
    latest_event = state.get("decisions", [])[-1] if state.get("decisions") else {}
    previous_decision = latest_event.get("decision", {})
    retrying = previous_decision.get("action") == "stop_for_repair"
    authorize_stage_action(state, task, args.stage, "retry" if retrying else "start")
    input_fingerprints, config = stage_context(
        state, args.stage, task, parse_keys(args.config_keys), args.inputs
    )
    signature = build_signature(args.stage, args.stage_version, config, input_fingerprints)
    previous_run = state["runs"].get(args.stage, {})
    started = previous_run.get("started_at_utc") if previous_run.get("signature") == signature else None
    started = started or datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    state["runs"][args.stage] = {
        "signature": signature,
        "inputs": input_fingerprints,
        "config": config,
        "started_at_utc": started,
    }
    if previous_run.get("signature") == signature:
        state["runs"][args.stage]["invocations"] = int(previous_run.get("invocations", 1)) + 1
    if retrying:
        state["runs"][args.stage]["retry_after_sequence"] = latest_event.get("sequence")
    previous = state["stages"].get(args.stage)
    if isinstance(previous, dict) and previous.get("signature") != signature:
        state["stages"].pop(args.stage, None)
    write_state(args.state, state)
    print(json.dumps({"stage": args.stage, "started_at_utc": started}, ensure_ascii=False))
    return 0


def command_mark(args: argparse.Namespace) -> int:
    task = load_json(args.task)
    validate_pro_invocation(args.task, args.state, task)
    validate_gate(task, args.stage, args.gate)
    if args.cache_state:
        if args.stage in {"parse_pdf", "review_pdf", "explain_pdf", "parse_pptx", "review_pptx", "explain_pptx"}:
            raise ValueError("PDF/PPTX manifests, page images, and visual review checkpoints must stay in Pro run state")
        validate_cache_state_path(args.cache_state, task)
    state = read_state(args.state)
    latest_event = state.get("decisions", [])[-1] if state.get("decisions") else {}
    if (
        latest_event.get("completed_stage") == args.stage
        and latest_event.get("decision", {}).get("action") == "stop_for_repair"
        and state.get("runs", {}).get(args.stage, {}).get("retry_after_sequence") != latest_event.get("sequence")
    ):
        raise ValueError(f"{args.stage} failed its last gate; rerun the stage after repair before marking it")
    if not state.get("runs", {}).get(args.stage):
        authorize_stage_action(state, task, args.stage, "mark")
    input_fingerprints, config = stage_context(
        state, args.stage, task, parse_keys(args.config_keys), args.inputs
    )
    signature = build_signature(args.stage, args.stage_version, config, input_fingerprints)
    outputs = [digest_path(path) for path in args.outputs]
    now = datetime.now(timezone.utc)
    updated = now.isoformat(timespec="milliseconds")
    run = state["runs"].get(args.stage, {})
    metrics: dict[str, Any] = {}
    if run.get("signature") == signature and run.get("started_at_utc"):
        try:
            started = datetime.fromisoformat(run["started_at_utc"])
            metrics["elapsed_ms"] = max(0, round((now - started).total_seconds() * 1000))
        except (TypeError, ValueError):
            pass
    for field in ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_tokens"):
        value = getattr(args, field)
        if value is not None:
            if value < 0:
                raise ValueError(f"Usage metric must be non-negative: {field}")
            metrics[field] = value
    record = {
        "signature": signature,
        "inputs": input_fingerprints,
        "config": config,
        "outputs": outputs,
        "gate": args.gate,
        "updated_at_utc": updated,
    }
    if metrics:
        record["metrics"] = metrics
    state["stages"][args.stage] = record
    state["runs"].pop(args.stage, None)
    write_state(args.state, state)
    if args.cache_state:
        cache_state = read_state(args.cache_state)
        cache_state["stages"][args.stage] = record
        cache_state["runs"].pop(args.stage, None)
        write_state(args.cache_state, cache_state)
    print(json.dumps({"stage": args.stage, "recorded": True, "outputs": outputs, "metrics": metrics}, ensure_ascii=False))
    return 0


def command_redecide(args: argparse.Namespace) -> int:
    """Persist an explicit next-step decision after each Pro Skill or stage."""
    task = load_json(args.task)
    validate_pro_invocation(args.task, args.state, task)
    state = read_state(args.state)
    stage = args.completed_stage
    skill = args.completed_skill
    if stage not in STAGE_ORDER:
        raise ValueError(f"Unknown Pro workflow stage: {stage}")
    if args.outcome not in {"passed", "failed", "blocked"}:
        raise ValueError(f"Unknown completion outcome: {args.outcome}")
    if len(args.reason.strip()) < 4 or len(args.reason) > 1_000:
        raise ValueError("Each redecision requires a concise reason between 4 and 1,000 characters")

    if args.completion_source == "cache":
        if skill:
            raise ValueError("A cache hit has no executed Skill; omit --completed-skill")
    elif args.completion_source == "runtime":
        expected_actor = NON_SKILL_STAGE_ACTORS.get(stage)
        if not expected_actor or skill != expected_actor:
            raise ValueError(f"{stage} has no matching non-Skill runtime actor")
    else:
        allowed_skills = stage_skill_names(stage, task)
        if not skill or skill not in allowed_skills:
            raise ValueError(f"{stage} can only be recorded for its routed Skill(s): {', '.join(allowed_skills) or 'none'}")

    quiz_generator_handoff = args.completion_source == "skill" and stage == "quiz" and skill == "foreign-academic-quiz-generator"
    if args.outcome == "passed" and args.completion_source != "cache":
        if args.continue_stage:
            if args.completion_source != "skill" or quiz_generator_handoff:
                raise ValueError("continue_stage is only for an incomplete routed Skill stage")
            if stage not in state.get("runs", {}):
                raise ValueError(f"Start {stage} before recording an in-progress Skill completion")
            if stage not in required_stages(task):
                raise ValueError(f"{stage} is not required by this Pro task")
            missing_prerequisites = [dependency for dependency in stage_dependencies(stage, task)
                                     if not is_stage_complete(state, dependency, task)]
            if missing_prerequisites:
                raise ValueError(f"Cannot continue {stage}; prerequisite stages remain incomplete: {missing_prerequisites}")
            if stage in state["stages"]:
                raise ValueError(f"{stage} is already marked complete; omit --continue-stage")
            if args.next_stage or args.next_skill:
                raise ValueError("An incomplete stage must continue itself, not start a later step")
        elif quiz_generator_handoff:
            if not quiz_selected(task):
                raise ValueError("The quiz generator cannot run when the user did not select a quiz")
            if "quiz" not in state.get("runs", {}):
                raise ValueError("Start the selected quiz stage before recording quiz-generator completion")
            if "quiz" in state["stages"]:
                raise ValueError("The quiz generator handoff must be recorded before marking the combined quiz stage")
        else:
            record = state["stages"].get(stage)
            if not isinstance(record, dict):
                raise ValueError(f"Mark the completed stage before redeciding: {stage}")
            gate = str(record.get("gate", "NONE"))
            validate_gate(task, stage, gate)
            if args.gate is not None and args.gate != gate:
                raise ValueError(f"The redecision gate {args.gate} does not match the recorded stage gate {gate}")
            if stage == "quiz" and skill == "foreign-academic-solution-explainer":
                generator_recorded = any(
                    item.get("completed_stage") == "quiz"
                    and item.get("completed_skill") == "foreign-academic-quiz-generator"
                    and item.get("outcome") == "passed"
                    and item.get("decision", {}).get("next_skill") == "foreign-academic-solution-explainer"
                    for item in state.get("decisions", [])
                )
                if not generator_recorded:
                    raise ValueError("Quiz solutions require a recorded successful quiz-generator handoff")
    elif args.completion_source == "cache" and args.outcome == "passed":
        if not is_stage_complete(state, stage, task):
            raise ValueError(f"A cached {stage} stage must be copied into Pro state and gate-checked before redecision")

    if args.outcome in {"failed", "blocked"}:
        if args.continue_stage:
            raise ValueError("A failed or blocked completion cannot be marked as a stage continuation")
        if args.next_stage or args.next_skill:
            raise ValueError("A failed or blocked Skill cannot advance to another stage")
        decision = {"action": "stop_for_repair", "reason": args.reason.strip()}
        eligible: list[str] = []
        missing: dict[str, list[str]] = {}
    elif args.continue_stage:
        decision = {"action": "continue_stage", "stage": stage, "reason": args.reason.strip()}
        eligible = []
        missing = {}
    elif quiz_generator_handoff:
        if args.next_stage:
            raise ValueError("After quiz generation, the next Skill must be solution-explainer")
        expected = "foreign-academic-solution-explainer"
        if args.next_skill not in (None, expected):
            raise ValueError(f"The quiz dependency requires the next Skill to be {expected}")
        decision = {"action": "continue_skill", "next_skill": expected, "reason": args.reason.strip()}
        eligible = []
        missing = {}
    else:
        if stage == "quiz" and skill == "foreign-academic-solution-explainer":
            if args.next_skill:
                raise ValueError("Quiz solution-explainer completes the quiz stage; choose a workflow stage next")
        eligible = eligible_next_stages(state, task)
        missing = unresolved_dependencies(state, task)
        if args.next_skill:
            raise ValueError("Only the quiz-generator handoff may select a next Skill directly")
        if args.next_stage:
            if args.next_stage not in eligible:
                raise ValueError(f"Cannot start {args.next_stage}; currently eligible stages are {eligible}")
            selected_stage = args.next_stage
        elif eligible:
            selected_stage = eligible[0]
        else:
            incomplete = [candidate for candidate in required_stages(task) if not is_stage_complete(state, candidate, task)]
            selected_stage = None
            if incomplete:
                decision = {
                    "action": "wait_for_dependency",
                    "blocked_stages": incomplete,
                    "missing_dependencies": missing,
                    "reason": args.reason.strip(),
                }
            else:
                decision = {"action": "deliver", "reason": args.reason.strip()}
        if eligible:
            decision = {"action": "start_stage", "next_stage": selected_stage, "reason": args.reason.strip()}

    event = {
        "sequence": len(state.get("decisions", [])) + 1,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "workflow_run_id": task["workflow_run_id"],
        "workflow_tier": PRO_TIER,
        "completion_source": args.completion_source,
        "completed_skill": skill if args.completion_source == "skill" else None,
        "actor": skill if args.completion_source == "runtime" else None,
        "completed_stage": stage,
        "outcome": args.outcome,
        "stage_complete": bool(args.outcome == "passed" and not args.continue_stage and not quiz_generator_handoff),
        "gate": args.gate or state.get("stages", {}).get(stage, {}).get("gate", "NONE"),
        "eligible_next_stages": eligible,
        "unresolved_dependencies": missing,
        "decision": decision,
    }
    state.setdefault("decisions", []).append(event)
    write_state(args.state, state)
    log_path = Path(task["decision_log_file"]).expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps(event, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check", help="Check whether a completed stage can be reused")
    add_common_arguments(check)
    check.set_defaults(run=command_check)
    start = subparsers.add_parser("start", help="Record the start time for a workflow stage")
    add_common_arguments(start)
    start.set_defaults(run=command_start)
    mark = subparsers.add_parser("mark", help="Record a completed stage and output hashes")
    add_common_arguments(mark)
    mark.add_argument("--outputs", required=True, nargs="+", type=Path, help="Completed output files or folders")
    mark.add_argument("--gate", choices=sorted(GATE_VALUES), default="NONE", help="Quality gate recorded for this completed stage")
    mark.add_argument("--cache-state", type=Path, help="Also save this completed non-visual stage in the Pro-only persistent cache state")
    mark.add_argument("--input-tokens", type=int)
    mark.add_argument("--cached-input-tokens", type=int)
    mark.add_argument("--cache-write-input-tokens", type=int)
    mark.add_argument("--output-tokens", type=int)
    mark.add_argument("--reasoning-tokens", type=int)
    mark.set_defaults(run=command_mark)
    redecide = subparsers.add_parser("redecide", help="Record the next Pro workflow decision after a Skill or stage completes")
    redecide.add_argument("--state", required=True, type=Path, help="Pro run state JSON path")
    redecide.add_argument("--task", required=True, type=Path, help="Pro task manifest JSON path")
    redecide.add_argument("--completed-stage", required=True, help="Completed or failed stage key")
    redecide.add_argument("--completed-skill", help="Executed Skill name; omit for cache reuse")
    redecide.add_argument("--completion-source", choices=("skill", "runtime", "cache"), default="skill")
    redecide.add_argument("--outcome", choices=("passed", "failed", "blocked"), required=True)
    redecide.add_argument("--gate", choices=sorted(GATE_VALUES), help="Must match the gate recorded by mark")
    redecide.add_argument("--next-stage", help="Choose a currently eligible next stage; otherwise the first eligible stage is selected")
    redecide.add_argument("--next-skill", help="Allowed only for quiz-generator -> solution-explainer handoff")
    redecide.add_argument("--continue-stage", action="store_true", help="Record that a Skill chunk finished while the routed stage still has work to complete")
    redecide.add_argument("--reason", required=True, help="Brief decision reason; do not include source or translated text")
    redecide.set_defaults(run=command_redecide)
    args = parser.parse_args()
    try:
        return args.run(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

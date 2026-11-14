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
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
CHUNK_SIZE = 1024 * 1024

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
    config = resolve_config(task, config_keys, fallback)
    all_inputs = combine_inputs(base_inputs, stage_dependency_paths(task, stage, config))
    input_fingerprints = [digest_path(path) for path in all_inputs]
    input_fingerprints.append(runtime_fingerprint(stage, task, config))
    if stage == "publish_html":
        inventory = html_output_inventory_fingerprint(task)
        if inventory is not None:
            input_fingerprints.append(inventory)
    return input_fingerprints, config


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "stages": {}, "runs": {}}
    try:
        state = load_json(path)
    except ValueError:
        return {"schema_version": SCHEMA_VERSION, "stages": {}, "runs": {}}
    if state.get("schema_version") != SCHEMA_VERSION or not isinstance(state.get("stages"), dict):
        return {"schema_version": SCHEMA_VERSION, "stages": {}, "runs": {}}
    if not isinstance(state.get("runs"), dict):
        state["runs"] = {}
    return state


def write_state(path: Path, state: dict[str, Any]) -> None:
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
    state = read_state(args.state)
    record = state["stages"].get(args.stage)
    result: dict[str, Any] = {"stage": args.stage, "reusable": False, "reason": "no_checkpoint"}
    if not isinstance(record, dict):
        print(json.dumps(result, ensure_ascii=False))
        return 0

    task = load_json(args.task)
    try:
        input_fingerprints, config = stage_context(
            state, args.stage, task, parse_keys(args.config_keys), args.inputs
        )
    except FileNotFoundError as exc:
        result.update({"reason": "input_missing", "missing_input": str(exc)})
        print(json.dumps(result, ensure_ascii=False))
        return 0
    signature = build_signature(args.stage, args.stage_version, config, input_fingerprints)
    result["resolved_config"] = config
    if record.get("signature") != signature:
        result["reason"] = "inputs_or_settings_changed"
    else:
        saved_outputs = record.get("outputs")
        if not isinstance(saved_outputs, list) or not saved_outputs:
            result["reason"] = "no_recorded_outputs"
        else:
            try:
                current_outputs = [digest_path(Path(item["path"])) for item in saved_outputs]
            except (KeyError, TypeError, FileNotFoundError):
                result["reason"] = "output_missing"
            else:
                if current_outputs != saved_outputs:
                    result["reason"] = "output_changed"
                else:
                    result.update({"reusable": True, "reason": "signature_and_outputs_match", "outputs": current_outputs})
    print(json.dumps(result, ensure_ascii=False))
    return 0


def command_start(args: argparse.Namespace) -> int:
    state = read_state(args.state)
    input_fingerprints, config = stage_context(
        state, args.stage, load_json(args.task), parse_keys(args.config_keys), args.inputs
    )
    signature = build_signature(args.stage, args.stage_version, config, input_fingerprints)
    started = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    state["runs"][args.stage] = {
        "signature": signature,
        "inputs": input_fingerprints,
        "config": config,
        "started_at_utc": started,
    }
    write_state(args.state, state)
    print(json.dumps({"stage": args.stage, "started_at_utc": started}, ensure_ascii=False))
    return 0


def command_mark(args: argparse.Namespace) -> int:
    state = read_state(args.state)
    input_fingerprints, config = stage_context(
        state, args.stage, load_json(args.task), parse_keys(args.config_keys), args.inputs
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
        "updated_at_utc": updated,
    }
    if metrics:
        record["metrics"] = metrics
    state["stages"][args.stage] = record
    state["runs"].pop(args.stage, None)
    write_state(args.state, state)
    print(json.dumps({"stage": args.stage, "recorded": True, "outputs": outputs, "metrics": metrics}, ensure_ascii=False))
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
    mark.add_argument("--input-tokens", type=int)
    mark.add_argument("--cached-input-tokens", type=int)
    mark.add_argument("--cache-write-input-tokens", type=int)
    mark.add_argument("--output-tokens", type=int)
    mark.add_argument("--reasoning-tokens", type=int)
    mark.set_defaults(run=command_mark)
    args = parser.parse_args()
    try:
        return args.run(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

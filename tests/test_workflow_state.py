import contextlib
import io
import json
import sys
import tempfile
import argparse
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "max" / "skills" / "translation-orchestrator" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import workflow_state  # noqa: E402


class WorkflowStateDependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime = self.root / "skills" / "translation-orchestrator"
        self._write(self.runtime / "SKILL.md", "orchestrator instructions")
        self._write(self.runtime / "references" / "task-handoff.md", "handoff rules")
        for relative in workflow_state.CONTENT_RUNTIME_FILES:
            self._write(self.runtime / relative, relative)
        self._write(self.runtime / "scripts" / "term_catcher.py", "term catcher")
        self._write(self.runtime / "scripts" / "glossary_loader.py", "glossary loader")
        self._write(self.runtime / "scripts" / "image_extractor.py", "image extractor")
        self._write(self.runtime / "scripts" / "workflow_state.py", "cache fingerprint logic")
        self._write(self.runtime / "scripts" / "builder.py", "builder entry")
        self._write(self.runtime / "scripts" / "builders" / "__init__.py", "builder package")
        self._write(self.runtime / "scripts" / "builders" / "html_builder.py", "html builder")
        self._write(self.runtime / "templates" / "html_style.css", "body { color: black; }")
        self._write(self.runtime / "glossaries" / "Science" / "terms.csv", "source_term,target_term\nalpha,阿尔法\n")
        self._write(self.runtime / "glossaries" / "Agriculture" / "terms.csv", "source_term,target_term\ncrop,作物\n")
        for skill in (
            "foreign-academic-pdf-reader",
            "foreign-academic-pptx-reader",
            "foreign-academic-visual-explainer",
            "foreign-academic-lesson-translator",
            "foreign-academic-quiz-generator",
            "foreign-academic-solution-explainer",
            "foreign-academic-quality-auditor",
            "foreign-academic-html-publisher",
            "foreign-academic-docx-publisher",
        ):
            self._write(self.root / "skills" / skill / "SKILL.md", f"{skill} instructions")
        self.source = self._write(self.root / "lesson.pdf", "synthetic source handout")
        self.task = {
            "project_root": str(self.root),
            "shared_runtime": str(self.runtime),
            "source_file": str(self.source),
            "glossary_mode": "system_glossary",
            "discipline": "Science",
            "include_images": False,
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def _write(path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def signature(self, stage: str, config_keys: str, task: dict | None = None, inputs: list[Path] | None = None) -> str:
        state = {"stages": {}}
        fingerprints, config = workflow_state.stage_context(
            state,
            stage,
            task or self.task,
            workflow_state.parse_keys(config_keys),
            inputs or [self.source],
        )
        return workflow_state.build_signature(stage, "1", config, fingerprints)

    def test_translation_signature_tracks_selected_skill_and_glossary(self):
        first = self.signature("translate", "glossary_mode,discipline,include_images")

        with (self.root / "skills" / "foreign-academic-lesson-translator" / "SKILL.md").open("a", encoding="utf-8") as stream:
            stream.write("\nnew translation rule")
        after_skill_change = self.signature("translate", "glossary_mode,discipline,include_images")
        self.assertNotEqual(first, after_skill_change)

        with (self.runtime / "glossaries" / "Science" / "terms.csv").open("a", encoding="utf-8") as stream:
            stream.write("beta,贝塔\n")
        after_selected_glossary_change = self.signature("translate", "glossary_mode,discipline,include_images")
        self.assertNotEqual(after_skill_change, after_selected_glossary_change)

        with (self.runtime / "glossaries" / "Agriculture" / "terms.csv").open("a", encoding="utf-8") as stream:
            stream.write("farm,农场\n")
        after_unselected_glossary_change = self.signature("translate", "glossary_mode,discipline,include_images")
        self.assertEqual(after_selected_glossary_change, after_unselected_glossary_change)

    def test_ai_auto_does_not_depend_on_system_glossary_files(self):
        task = {**self.task, "glossary_mode": "ai_auto"}
        before = self.signature("translate", "glossary_mode,discipline,include_images", task)
        with (self.runtime / "glossaries" / "Science" / "terms.csv").open("a", encoding="utf-8") as stream:
            stream.write("gamma,伽马\n")
        after = self.signature("translate", "glossary_mode,discipline,include_images", task)
        self.assertEqual(before, after)

    def test_translation_signature_tracks_extractor_code_and_enabled_images(self):
        keys = "glossary_mode,discipline,include_images"
        before = self.signature("translate", keys)
        with (self.runtime / "scripts" / "text_extractor.py").open("a", encoding="utf-8") as stream:
            stream.write("\n# extraction behavior changed")
        after_extractor_change = self.signature("translate", keys)
        self.assertNotEqual(before, after_extractor_change)

        image_dir = self.root / "output" / "lesson" / "images"
        image = self._write(image_dir / "figure.png", "first image bytes")
        placement = self._write(self.root / "output" / "lesson" / "placement.json", "[]")
        task = {
            **self.task,
            "image_dir": "output/lesson/images",
            "placement_file": "output/lesson/placement.json",
            "include_images": True,
        }
        dependencies = workflow_state.stage_dependency_paths(task, "translate", {
            "glossary_mode": task["glossary_mode"],
            "discipline": task["discipline"],
            "include_images": True,
        })
        self.assertIn(image_dir.resolve(), dependencies)
        self.assertIn(placement.resolve(), dependencies)
        before_image_change = self.signature("translate", keys, task)
        image.write_text("changed image bytes", encoding="utf-8")
        after_image_change = self.signature("translate", keys, task)
        self.assertNotEqual(before_image_change, after_image_change)

    def test_publish_html_tracks_templates_nested_skill_and_relative_image_assets(self):
        image_dir = self.root / "output" / "lesson" / "images"
        image = self._write(image_dir / "figure.png", "synthetic image")
        placement = self._write(self.root / "output" / "lesson" / "placement.json", "[]")
        task = {
            **self.task,
            "project_root": str(self.root),
            "image_dir": "output/lesson/images",
            "placement_file": "output/lesson/placement.json",
            "include_images": True,
        }
        deps = workflow_state.stage_dependency_paths(task, "publish_html", {"include_images": True})
        self.assertIn(image_dir.resolve(), deps)
        self.assertIn(placement.resolve(), deps)

        keys = "include_images"
        first = self.signature("publish_html", keys, task, [self.source])
        with (self.runtime / "templates" / "html_style.css").open("a", encoding="utf-8") as stream:
            stream.write("\nbody { line-height: 1.5; }")
        after_template_change = self.signature("publish_html", keys, task, [self.source])
        self.assertNotEqual(first, after_template_change)

        nested_reference = self._write(
            self.root / "skills" / "foreign-academic-html-publisher" / "references" / "checklist.md",
            "HTML audit checklist",
        )
        after_nested_skill_resource = self.signature("publish_html", keys, task, [self.source])
        self.assertNotEqual(after_template_change, after_nested_skill_resource)

        image.write_text("updated synthetic image", encoding="utf-8")
        after_image_change = self.signature("publish_html", keys, task, [self.source])
        self.assertNotEqual(after_nested_skill_resource, after_image_change)
        self.assertTrue(nested_reference.is_file())

    def test_publish_signature_tracks_runtime_dependency_versions(self):
        task = {**self.task, "source_file": "lesson.md"}
        with patch.object(workflow_state.importlib.metadata, "version", return_value="1.0"):
            before = self.signature("publish_docx", "", task, [self.source])
        with patch.object(workflow_state.importlib.metadata, "version", return_value="2.0"):
            after = self.signature("publish_docx", "", task, [self.source])
        self.assertNotEqual(before, after)

    def test_pdf_parse_runtime_fingerprint_tracks_tesseract(self):
        task = {**self.task, "source_file": "lesson.pdf"}
        with patch.object(workflow_state.shutil, "which", return_value="tesseract.exe"), \
             patch.object(workflow_state.subprocess, "run", return_value=workflow_state.subprocess.CompletedProcess(
                 ["tesseract", "--version"], 0, stdout="tesseract 5.3.0\n", stderr="")):
            first = workflow_state.runtime_fingerprint("parse_pdf", task, {})
        with patch.object(workflow_state.shutil, "which", return_value="tesseract.exe"), \
             patch.object(workflow_state.subprocess, "run", return_value=workflow_state.subprocess.CompletedProcess(
                 ["tesseract", "--version"], 0, stdout="tesseract 5.4.0\n", stderr="")):
            second = workflow_state.runtime_fingerprint("parse_pdf", task, {})
        self.assertNotEqual(first["sha256"], second["sha256"])

    def test_pdf_parse_runtime_fingerprint_tracks_tesseract_languages_and_traineddata(self):
        task = {**self.task, "source_file": "lesson.pdf"}
        config = {"ocr_language": "eng"}
        tessdata = self.root / "tessdata"
        tessdata.mkdir()
        traineddata = tessdata / "eng.traineddata"
        traineddata.write_bytes(b"traineddata version one")

        def runtime_for(languages):
            def run(args, **kwargs):
                if "--version" in args:
                    stdout = "tesseract 5.3.0" + chr(10)
                elif "--list-langs" in args:
                    stdout = 'List of available languages in "test" (2):' + chr(10) + chr(10).join(languages) + chr(10)
                else:
                    stdout = str(tessdata)
                return workflow_state.subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

            with patch.object(workflow_state.shutil, "which", return_value="tesseract.exe"):
                with patch.object(workflow_state.subprocess, "run", side_effect=run):
                    return workflow_state.runtime_fingerprint("parse_pdf", task, config)

        first = runtime_for(["eng"])
        traineddata.write_bytes(b"traineddata version two")
        second = runtime_for(["eng"])
        self.assertNotEqual(first["sha256"], second["sha256"])
        third = runtime_for(["eng", "fra"])
        self.assertNotEqual(second["sha256"], third["sha256"])

    def test_publish_html_signature_tracks_file_tree_html_paths_not_file_contents(self):
        task = {**self.task, "output_dir": "output/lesson"}
        keys = "output_dir"
        before = self.signature("publish_html", keys, task)

        other_html = self._write(self.root / "output" / "another-lesson" / "translated_doc.html", "first html")
        after_new_lesson = self.signature("publish_html", keys, task)
        self.assertNotEqual(before, after_new_lesson)

        other_html.write_text("changed page body", encoding="utf-8")
        after_content_only = self.signature("publish_html", keys, task)
        self.assertEqual(after_new_lesson, after_content_only)

    def test_marked_stage_cache_is_invalidated_after_skill_change(self):
        task_path = self.root / "task.json"
        state_path = self.root / "state.json"
        output_path = self.root / "translated.md"
        output_path.write_text("synthetic translated output", encoding="utf-8")
        task_path.write_text(json.dumps(self.task), encoding="utf-8")
        common = {
            "state": state_path,
            "task": task_path,
            "stage": "translate",
            "inputs": [self.source],
            "config_keys": "glossary_mode,discipline,include_images",
            "stage_version": "1",
        }

        with contextlib.redirect_stdout(io.StringIO()):
            workflow_state.command_start(argparse.Namespace(**common))
            workflow_state.command_mark(
                argparse.Namespace(
                    **common,
                    outputs=[output_path],
                    input_tokens=None,
                    cached_input_tokens=None,
                    cache_write_input_tokens=None,
                    output_tokens=None,
                    reasoning_tokens=None,
                )
            )

        def cache_check() -> dict:
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                workflow_state.command_check(argparse.Namespace(**common))
            return json.loads(captured.getvalue())

        self.assertTrue(cache_check()["reusable"])
        with (self.root / "skills" / "foreign-academic-lesson-translator" / "SKILL.md").open("a", encoding="utf-8") as stream:
            stream.write("\nchanged instructions")
        invalidated = cache_check()
        self.assertFalse(invalidated["reusable"])
        self.assertEqual(invalidated["reason"], "inputs_or_settings_changed")

    def test_handoff_and_cache_logic_changes_invalidate_stage_signatures(self):
        first = self.signature("audit_translation", "")
        with (self.runtime / "references" / "task-handoff.md").open("a", encoding="utf-8") as stream:
            stream.write("\nchanged handoff contract")
        after_handoff_change = self.signature("audit_translation", "")
        self.assertNotEqual(first, after_handoff_change)

        with (self.runtime / "scripts" / "workflow_state.py").open("a", encoding="utf-8") as stream:
            stream.write("\n# changed cache behavior")
        after_cache_logic_change = self.signature("audit_translation", "")
        self.assertNotEqual(after_handoff_change, after_cache_logic_change)


    def test_pptx_stages_track_work_files_but_persistent_cache_uses_only_fingerprint(self):
        pptx = self._write(self.root / "lesson.pptx", "synthetic pptx bytes")
        raw_manifest = self._write(self.root / "output" / "lesson" / "pptx.raw.json", "{}")
        final_manifest = self._write(self.root / "output" / "lesson" / "pptx.json", "{}")
        source_text = self._write(self.root / "output" / "lesson" / "source.txt", "page indexed text")
        visual_assets = self.root / "output" / "lesson" / "visual_assets"
        visual_assets.mkdir(parents=True)
        self._write(visual_assets / "slide-0001.png", "synthetic image bytes")
        explanations = self._write(self.root / "output" / "lesson" / "visual-explanations.md", "PPT page 1 explanation")
        task = {
            **self.task,
            "source_file": str(pptx),
            "source_kind": "pptx",
            "pptx_raw_manifest_file": str(raw_manifest),
            "pptx_manifest_file": str(final_manifest),
            "source_text_file": str(source_text),
            "visual_assets_dir": str(visual_assets),
            "pptx_visual_explanations_file": str(explanations),
            "pptx_processing_fingerprint": "a" * 64,
        }

        review_dependencies = workflow_state.stage_dependency_paths(task, "review_pptx", {})
        explain_dependencies = workflow_state.stage_dependency_paths(task, "explain_pptx", {})
        self.assertIn(raw_manifest.resolve(), review_dependencies)
        self.assertIn(visual_assets.resolve(), review_dependencies)
        self.assertIn(final_manifest.resolve(), explain_dependencies)
        self.assertIn(visual_assets.resolve(), explain_dependencies)

        translate_dependencies = workflow_state.stage_dependency_paths(task, "translate", {"include_images": False})
        self.assertNotIn(raw_manifest.resolve(), translate_dependencies)
        self.assertNotIn(source_text.resolve(), translate_dependencies)
        self.assertNotIn(visual_assets.resolve(), translate_dependencies)

        before = self.signature("translate", "pptx_processing_fingerprint,discipline,include_images", task, [pptx])
        changed_task = {**task, "pptx_processing_fingerprint": "b" * 64}
        after = self.signature("translate", "pptx_processing_fingerprint,discipline,include_images", changed_task, [pptx])
        self.assertNotEqual(before, after)

    def test_pdf_stages_track_work_files_but_persistent_cache_uses_only_fingerprint(self):
        pdf = self._write(self.root / "lesson.pdf", "synthetic pdf source")
        raw_manifest = self._write(self.root / "output" / "lesson" / "pdf.raw.json", "{}")
        final_manifest = self._write(self.root / "output" / "lesson" / "pdf.json", "{}")
        source_text = self._write(self.root / "output" / "lesson" / "source.txt", "page indexed text")
        visual_assets = self.root / "output" / "lesson" / "visual_assets"
        visual_assets.mkdir(parents=True)
        self._write(visual_assets / "page-0001.png", "synthetic image bytes")
        task = {
            **self.task,
            "source_file": str(pdf),
            "source_kind": "pdf",
            "pdf_raw_manifest_file": str(raw_manifest),
            "pdf_manifest_file": str(final_manifest),
            "source_text_file": str(source_text),
            "visual_assets_dir": str(visual_assets),
            "pdf_processing_fingerprint": "a" * 64,
        }
        review_dependencies = workflow_state.stage_dependency_paths(task, "review_pdf", {})
        explain_dependencies = workflow_state.stage_dependency_paths(task, "explain_pdf", {})
        self.assertIn(raw_manifest.resolve(), review_dependencies)
        self.assertIn(visual_assets.resolve(), review_dependencies)
        self.assertIn(final_manifest.resolve(), explain_dependencies)
        self.assertIn(visual_assets.resolve(), explain_dependencies)

        translate_dependencies = workflow_state.stage_dependency_paths(task, "translate", {"include_images": False})
        self.assertNotIn(raw_manifest.resolve(), translate_dependencies)
        self.assertNotIn(source_text.resolve(), translate_dependencies)
        self.assertNotIn(visual_assets.resolve(), translate_dependencies)

        before = self.signature("translate", "pdf_processing_fingerprint,discipline,include_images", task, [pdf])
        changed_task = {**task, "pdf_processing_fingerprint": "b" * 64}
        after = self.signature("translate", "pdf_processing_fingerprint,discipline,include_images", changed_task, [pdf])
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()

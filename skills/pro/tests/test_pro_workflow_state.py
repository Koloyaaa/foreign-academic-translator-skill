import argparse
import contextlib
import io
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PRO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME = PRO_ROOT / "skills" / "translation-orchestrator"
WORKFLOW_STATE_PATH = RUNTIME / "scripts" / "workflow_state.py"
SPEC = importlib.util.spec_from_file_location("pro_tier_workflow_state", WORKFLOW_STATE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load Pro workflow state module: {WORKFLOW_STATE_PATH}")
workflow_state = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = workflow_state
SPEC.loader.exec_module(workflow_state)


class ProWorkflowStateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.output = self.root / "output" / "lesson"
        self.output.mkdir(parents=True)
        self.cache = self.output / ".translator-cache-pro"
        self.cache.mkdir()
        self.source = self.output / "source.txt"
        self.source.write_text("synthetic source text", encoding="utf-8")
        self.task_path = self.output / ".translation-task-pro.json"
        self.state_path = self.output / ".translation-state-pro.json"
        self.cache_state_path = self.cache / "workflow-state.json"
        self.decision_log = self.output / ".pro-decisions-test-run.jsonl"
        self.task = {
            "schema_version": 7,
            "workflow_tier": "pro",
            "quality_profile": workflow_state.PRO_QUALITY_PROFILE,
            "workflow_run_id": "test-run",
            "project_root": str(self.root),
            "lesson_name": "lesson",
            "source_file": str(self.source),
            "source_kind": "txt",
            "translation_route": "quick",
            "translation_route_reason": "synthetic test fixture",
            "output_dir": str(self.output.resolve()),
            "shared_runtime": str(RUNTIME.resolve()),
            "output_formats": ["md"],
            "quiz_levels": [],
            "quiz_language": None,
            "state_file": str(self.state_path.resolve()),
            "cache_dir": str(self.cache.resolve()),
            "cache_state_file": str(self.cache_state_path.resolve()),
            "cache_core_markdown": str((self.cache / "core.md").resolve()),
            "cache_coverage_index_file": str((self.cache / "coverage.json").resolve()),
            "cache_quiz_file": "",
            "decision_log_file": str(self.decision_log.resolve()),
            "translated_core_markdown": str((self.output / "translated_core.md").resolve()),
        }
        self.write_task()

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_task(self):
        self.task_path.write_text(json.dumps(self.task, ensure_ascii=False), encoding="utf-8")

    def quiet(self, function, args):
        with contextlib.redirect_stdout(io.StringIO()):
            return function(args)

    def start(self, stage, inputs=None, config_keys="translation_route"):
        return self.quiet(workflow_state.command_start, argparse.Namespace(
            state=self.state_path,
            task=self.task_path,
            stage=stage,
            inputs=inputs or [self.source],
            config_keys=config_keys,
            stage_version="1",
        ))

    def mark(self, stage, output, gate="NONE", cache=False, inputs=None, config_keys="translation_route"):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("synthetic output", encoding="utf-8")
        return self.quiet(workflow_state.command_mark, argparse.Namespace(
            state=self.state_path,
            task=self.task_path,
            stage=stage,
            inputs=inputs or [self.source],
            config_keys=config_keys,
            stage_version="1",
            outputs=[output],
            gate=gate,
            cache_state=self.cache_state_path if cache else None,
            input_tokens=None,
            cached_input_tokens=None,
            cache_write_input_tokens=None,
            output_tokens=None,
            reasoning_tokens=None,
        ))

    def redecide(self, stage, skill, *, outcome="passed", continue_stage=False, next_skill=None, gate=None, source="skill", reason="synthetic decision reason"):
        return self.quiet(workflow_state.command_redecide, argparse.Namespace(
            state=self.state_path,
            task=self.task_path,
            completed_stage=stage,
            completed_skill=skill,
            completion_source=source,
            outcome=outcome,
            gate=gate,
            next_stage=None,
            next_skill=next_skill,
            continue_stage=continue_stage,
            reason=reason,
        ))

    def test_each_completed_stage_records_and_authorizes_only_selected_next_stage(self):
        self.start("translate")
        translated = self.output / "translated_core.md"
        self.mark("translate", translated, cache=True)
        self.redecide("translate", "foreign-academic-quick-translator")

        state = workflow_state.read_state(self.state_path)
        event = state["decisions"][-1]
        self.assertEqual(event["decision"]["action"], "start_stage")
        self.assertEqual(event["decision"]["next_stage"], "audit_translation")
        self.assertTrue(self.decision_log.is_file())
        self.assertEqual(json.loads(self.decision_log.read_text(encoding="utf-8"))['workflow_tier'], "pro")

        with self.assertRaisesRegex(ValueError, "not authorized"):
            self.start("publish_md", inputs=[translated])
        self.start("audit_translation", inputs=[self.source, translated], config_keys="audit_scope")

    def test_redecide_is_required_between_successful_stages(self):
        self.start("translate")
        translated = self.output / "translated_core.md"
        self.mark("translate", translated)
        with self.assertRaisesRegex(ValueError, "Record a Pro redecision"):
            self.start("audit_translation", inputs=[self.source, translated], config_keys="audit_scope")

    def test_partial_skill_returns_continue_same_stage(self):
        self.task["translation_route"] = "full"
        self.write_task()
        self.start("translate")
        self.redecide("translate", "foreign-academic-lesson-translator", continue_stage=True)
        state = workflow_state.read_state(self.state_path)
        self.assertEqual(state["decisions"][-1]["decision"]["action"], "continue_stage")
        self.assertEqual(state["decisions"][-1]["decision"]["stage"], "translate")
        self.start("translate")

    def test_quiz_generator_handoff_and_selected_quiz_audit_dependency(self):
        self.task["quiz_levels"] = ["basic"]
        self.write_task()
        self.start("translate")
        translated = self.output / "translated_core.md"
        self.mark("translate", translated)
        self.redecide("translate", "foreign-academic-quick-translator")

        self.start("quiz")
        self.redecide("quiz", "foreign-academic-quiz-generator")
        state = workflow_state.read_state(self.state_path)
        self.assertEqual(state["decisions"][-1]["decision"]["action"], "continue_skill")
        self.assertEqual(state["decisions"][-1]["decision"]["next_skill"], "foreign-academic-solution-explainer")

        quiz = self.output / "quiz-final.md"
        self.mark("quiz", quiz)
        self.redecide("quiz", "foreign-academic-solution-explainer")
        state = workflow_state.read_state(self.state_path)
        self.assertEqual(state["decisions"][-1]["decision"]["next_stage"], "audit_translation")
        self.assertIn("audit_quiz", workflow_state.required_stages(self.task))

    def test_pro_path_isolation_and_visual_gate(self):
        bad_task = {**self.task, "cache_dir": str((self.output / ".translator-cache-max").resolve())}
        with self.assertRaisesRegex(ValueError, "Pro-only path"):
            workflow_state.validate_pro_invocation(self.task_path, self.state_path, bad_task)

        pdf_task = {**self.task, "source_kind": "pdf", "vision_capability": "available", "vision_capability_evidence": "synthetic image channel evidence"}
        with self.assertRaisesRegex(ValueError, "requires a completed page-by-page visual gate"):
            workflow_state.validate_gate(pdf_task, "review_pdf", "SKIPPED_NO_VISION")
        unavailable_task = {**pdf_task, "vision_capability": "unavailable"}
        workflow_state.validate_gate(unavailable_task, "review_pdf", "SKIPPED_NO_VISION")

    def test_check_reads_only_pro_cache_and_requires_valid_gate(self):
        cached_core = self.cache / "core.md"
        self.mark("translate", cached_core, cache=True)
        state = workflow_state.read_state(self.state_path)
        state["stages"].clear()
        workflow_state.write_state(self.state_path, state)
        args = argparse.Namespace(
            state=self.state_path,
            task=self.task_path,
            stage="translate",
            inputs=[self.source],
            config_keys="translation_route",
            stage_version="1",
        )
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            workflow_state.command_check(args)
        result = json.loads(captured.getvalue())
        self.assertTrue(result["reusable"])
        self.assertEqual(result["source"], "cache_state")


if __name__ == "__main__":
    unittest.main()

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "max" / "skills" / "translation-orchestrator" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import builder  # noqa: E402


class BuilderFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)
        self.markdown = "# Synthetic lesson\n\nThis is enough content for a build."

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def successful_builder(_content, output_path, **_kwargs):
        output_path = Path(output_path)
        output_path.write_text("generated artifact", encoding="utf-8")
        return output_path

    def test_any_requested_format_failure_fails_the_build_even_with_other_successes(self):
        def failed_docx(_content, _output_path):
            raise RuntimeError("synthetic DOCX failure")

        with (
            patch.object(builder, "build_html", side_effect=self.successful_builder) as html,
            patch.object(builder, "build_docx", side_effect=failed_docx) as docx,
            patch.object(builder, "build_markdown", side_effect=self.successful_builder) as markdown,
        ):
            with self.assertRaises(builder.RequestedFormatBuildError) as caught:
                builder.build_all(self.markdown, self.output_dir, ["html", "docx", "md"])

        self.assertEqual(set(caught.exception.results), {"html", "md"})
        self.assertIn("docx", caught.exception.failures)
        self.assertEqual(caught.exception.results["html"].read_text(encoding="utf-8"), "generated artifact")
        html.assert_called_once()
        docx.assert_called_once()
        markdown.assert_called_once()

    def test_stale_existing_artifact_does_not_turn_current_failure_into_success(self):
        stale_html = self.output_dir / "translated_doc.html"
        stale_html.write_text("old successful artifact", encoding="utf-8")

        with patch.object(builder, "build_html", side_effect=RuntimeError("current build failed")):
            with self.assertRaises(builder.RequestedFormatBuildError) as caught:
                builder.build_all(self.markdown, self.output_dir, ["html"])

        self.assertTrue(stale_html.is_file())
        self.assertEqual(stale_html.read_text(encoding="utf-8"), "old successful artifact")
        self.assertEqual(caught.exception.results, {})
        self.assertIn("html", caught.exception.failures)

    def test_silent_noop_cannot_reuse_an_old_nonempty_artifact(self):
        stale_html = self.output_dir / "translated_doc.html"
        stale_html.write_text("old successful artifact", encoding="utf-8")

        with patch.object(builder, "build_html", side_effect=lambda _content, output_path, **_kwargs: output_path):
            with self.assertRaises(builder.RequestedFormatBuildError) as caught:
                builder.build_all(self.markdown, self.output_dir, ["html"])

        self.assertEqual(stale_html.read_text(encoding="utf-8"), "old successful artifact")
        self.assertIn("non-empty", caught.exception.failures["html"])
        self.assertFalse(any(".building" in item.name for item in self.output_dir.iterdir()))

    def test_empty_artifact_is_a_build_failure(self):
        def empty_builder(_content, output_path, **_kwargs):
            output_path = Path(output_path)
            output_path.touch()
            return output_path

        with patch.object(builder, "build_html", side_effect=empty_builder):
            with self.assertRaises(builder.RequestedFormatBuildError) as caught:
                builder.build_all(self.markdown, self.output_dir, ["html"])

        self.assertIn("non-empty", caught.exception.failures["html"])

    def test_unsupported_requested_format_is_a_build_failure(self):
        with patch.object(builder, "build_html", side_effect=self.successful_builder):
            with self.assertRaises(builder.RequestedFormatBuildError) as caught:
                builder.build_all(self.markdown, self.output_dir, ["html", "pdf"])

        self.assertIn("unsupported", caught.exception.failures["pdf"])
        self.assertNotIn("html", caught.exception.failures)

    def test_cli_returns_failure_when_one_requested_format_fails(self):
        input_path = self.output_dir / "input.md"
        input_path.write_text(self.markdown, encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch.object(builder, "build_html", side_effect=self.successful_builder),
            patch.object(builder, "build_docx", side_effect=RuntimeError("synthetic DOCX failure")),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = builder.main(
                ["--input", str(input_path), "--output_dir", str(self.output_dir), "--formats", "html,docx"]
            )

        self.assertEqual(exit_code, 1)
        report = json.loads(stdout.getvalue().splitlines()[0])
        self.assertIn("html", report["results"])
        self.assertIn("docx", report["failures"])
        self.assertIn("Requested format build failed", stderr.getvalue())

    def test_html_build_uses_final_filename_and_hides_temporary_artifact(self):
        output_dir = self.output_dir / "output" / "lesson"
        result = builder.build_all(self.markdown, output_dir, ["html"])
        html = result["html"].read_text(encoding="utf-8")

        self.assertIn("translated_doc.html", html)
        self.assertNotIn(".building", html)
        self.assertFalse(any(".building" in item.name for item in output_dir.iterdir()))


if __name__ == "__main__":
    unittest.main()

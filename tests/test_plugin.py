import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    from PyPDF2 import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "claude-plugin/skills/ocrdeskew/scripts"))
from shotgunlib import pdfops, planner, runner

spec = importlib.util.spec_from_file_location("package_codex", ROOT / "scripts/package_codex_plugin.py")
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


def make_pdf(path, width=100, pages=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=width, height=200)
    with path.open("wb") as handle:
        writer.write(handle)


def copy_ocr(unit, output_path, quality, lang, timeout):
    shutil.copyfile(unit.path, output_path)
    return True, {"ok": True, "output_path": str(output_path), "result": {
        "quality_score": 90, "word_count": 10, "confidence": 90,
        "audit_status": "Searchable",
    }}


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_batch(self, paths, **kwargs):
        plans = planner.build_plan(paths, 2, allow_split=False)
        with patch.object(runner, "run_unit", side_effect=copy_ocr):
            return runner.execute(plans, 2, "balanced", "eng", quiet=True, **kwargs)

    def test_same_named_files_have_distinct_outputs_and_keep_originals(self):
        sources = [self.root / "a/scan.pdf", self.root / "b/scan.pdf"]
        for width, source in zip((100, 300), sources):
            make_pdf(source, width)
        original_bytes = [source.read_bytes() for source in sources]
        report = self.run_batch(sources, out_dir=self.root / "repaired")
        self.assertTrue(report["ok"])
        paths = [Path(item["output_path"]) for item in report["results"]]
        self.assertEqual(len(set(paths)), 2)
        self.assertEqual([float(PdfReader(str(p)).pages[0].mediabox.width) for p in paths], [100, 300])
        self.assertEqual([p.read_bytes() for p in sources], original_bytes)

    def test_existing_sidecar_is_preserved(self):
        source = self.root / "scan.pdf"
        make_pdf(source)
        existing = self.root / "scan-deskewed.pdf"
        existing.write_bytes(b"previous output")
        report = self.run_batch([source])
        self.assertTrue(report["ok"])
        self.assertEqual(existing.read_bytes(), b"previous output")
        self.assertNotEqual(report["results"][0]["output_path"], str(existing))

    def test_same_named_backups_do_not_overwrite_each_other(self):
        sources = [self.root / "a/scan.pdf", self.root / "b/scan.pdf"]
        for width, source in zip((100, 300), sources):
            make_pdf(source, width)
        report = self.run_batch(sources, destructive=True, backup_dir=self.root / "backup")
        self.assertTrue(report["ok"])
        backups = sorted((self.root / "backup").glob("*.pdf"))
        self.assertEqual(len(backups), 2)
        self.assertEqual(sorted(float(PdfReader(str(p)).pages[0].mediabox.width) for p in backups), [100, 300])

    def test_license_refusal_leaves_originals_and_outputs_untouched(self):
        source = self.root / "scan.pdf"
        make_pdf(source)
        original = source.read_bytes()
        plans = planner.build_plan([source], 1, allow_split=False)
        with patch.object(runner, "run_unit", return_value=(False, {
            "fatal": True, "error": "License required: expired", "license_state": "expired",
        })) as run:
            with self.assertRaises(runner.ShotgunError):
                runner.execute(plans, 1, "balanced", "eng", destructive=True, quiet=True)
            self.assertEqual(run.call_count, 1)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [source])

    def test_invalid_output_cannot_replace_original(self):
        source = self.root / "scan.pdf"
        make_pdf(source, pages=2)
        original = source.read_bytes()
        plans = planner.build_plan([source], 1, allow_split=False)

        def bad_ocr(unit, output_path, quality, lang, timeout):
            make_pdf(output_path, pages=1)
            return True, {"ok": True, "output_path": str(output_path), "result": {}}

        with patch.object(runner, "run_unit", side_effect=bad_ocr):
            report = runner.execute(plans, 1, "balanced", "eng", destructive=True, quiet=True)
        self.assertFalse(report["ok"])
        self.assertIn("page count mismatch", report["results"][0]["error"])
        self.assertEqual(source.read_bytes(), original)

    def test_archive_contains_resolvable_skills_and_shared_helpers(self):
        archive_path = self.root / "plugin.zip"
        packager.package(archive_path)
        with ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            self.assertIn("plugin.json", names)
            self.assertIn("assets/ocrdeskew.png", names)
            self.assertIn("skills/ocr-audit/SKILL.md", names)
            self.assertIn("claude-plugin/skills/ocrdeskew/scripts/shotgunlib/runner.py", names)
            self.assertFalse(any(".git/" in n or "__pycache__" in n for n in names))
            manifest = json.loads(archive.read("plugin.json"))
            self.assertTrue(manifest["extensions"]["com.openai"]["requires_local_executor"])
            interface = manifest["extensions"]["com.openai"]["interface"]
            self.assertLessEqual(len(interface["shortDescription"]), 30)
            for field in ("logo", "composerIcon"):
                self.assertIn(interface[field].removeprefix("./"), names)
            archive.extractall(self.root / "unpacked")
        skill = self.root / "unpacked/skills/ocrdeskew"
        self.assertTrue((skill / "../../claude-plugin/skills/ocrdeskew/scripts/shotgun.py").resolve().is_file())

    @unittest.skipUnless(pdfops.QPDF or importlib.util.find_spec("pypdf"), "needs qpdf or pypdf")
    def test_batch_cli_splits_merges_and_preserves_page_order(self):
        # The fake CLI only copies PDFs. This checks orchestration, not OCR accuracy.
        binary_dir = self.root / "bin"
        binary_dir.mkdir()
        binary = binary_dir / "ocrdeskew"
        binary.write_text(
            f"#!{sys.executable}\n"
            "import json, shutil, sys\n"
            "source = sys.argv[1]\n"
            "output = sys.argv[sys.argv.index('--out') + 1]\n"
            "shutil.copyfile(source, output)\n"
            "print(json.dumps({'schema_version': 'ocrdeskew.cli.v1', 'app_version': '2.0.1', "
            "'results': [{'ok': True, 'output_path': output, 'result': "
            "{'word_count': 10, 'quality_score': 90, 'confidence': 90}}]}))\n"
        )
        binary.chmod(0o755)
        sources = [self.root / "a/scan.pdf", self.root / "b/scan.pdf"]
        for start, source in zip((100, 300), sources):
            source.parent.mkdir()
            writer = PdfWriter()
            for number in range(8):
                writer.add_blank_page(width=start + number, height=200)
            with source.open("wb") as handle:
                writer.write(handle)
        report_path = self.root / "report.json"
        process = subprocess.run([
            sys.executable, str(ROOT / "claude-plugin/skills/ocrdeskew/scripts/shotgun.py"),
            "run", *(str(path) for path in sources), "--workers", "4",
            "--out", str(self.root / "outputs"), "--json-out", str(report_path),
        ], env={**os.environ, "PATH": str(binary_dir) + os.pathsep + os.environ.get("PATH", "")},
            capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        report = json.loads(report_path.read_text())
        self.assertGreater(report["plan"]["split_files"], 0)
        for start, result in zip((100, 300), report["results"]):
            pages = PdfReader(result["output_path"]).pages
            self.assertEqual([float(page.mediabox.width) for page in pages], list(range(start, start + 8)))

    def test_unlock_cli_clears_empty_password_and_preserves_unknown_password(self):
        sources = [self.root / "restricted.pdf", self.root / "password.pdf"]
        for source, password in zip(sources, ("", "user-secret")):
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=200)
            writer.encrypt(password, owner_password="owner-secret")
            with source.open("wb") as handle:
                writer.write(handle)
        originals = [source.read_bytes() for source in sources]
        script = ROOT / "claude-plugin/skills/ocrdeskew/scripts/unlock.py"
        scan = subprocess.run([sys.executable, str(script), "scan", str(self.root)],
                              capture_output=True, text=True, timeout=10)
        self.assertEqual(scan.returncode, 0, scan.stderr)
        self.assertEqual([source.read_bytes() for source in sources], originals)
        run = subprocess.run([sys.executable, str(script), "run", str(self.root)],
                             capture_output=True, text=True, timeout=10)
        report = json.loads(run.stdout)
        by_name = {Path(item["source_path"]).name: item for item in report["results"]}
        self.assertEqual(by_name["restricted.pdf"]["status"], "unlocked")
        self.assertFalse(PdfReader(by_name["restricted.pdf"]["output_path"]).is_encrypted)
        self.assertEqual(by_name["password.pdf"]["status"], "locked")
        self.assertEqual([source.read_bytes() for source in sources], originals)
        self.assertNotIn("user-secret", run.stdout)


if __name__ == "__main__":
    unittest.main()

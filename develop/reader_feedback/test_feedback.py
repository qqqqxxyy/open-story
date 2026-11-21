"""Run isolated normal-use feedback checks inside this directory."""
import ast
from concurrent.futures import ThreadPoolExecutor
import zipfile
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
TOOL = ROOT / "feedback.py"


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-feedback-")
        self.area = Path(self.temp.name).resolve()
        self.assertTrue(self.area.is_relative_to(ROOT))
        self.data = self.area / "data"
        self.addCleanup(self.cleanup_area)

    def cleanup_area(self):
        self.assertTrue(Path(self.temp.name).resolve().is_relative_to(ROOT))
        self.temp.cleanup()

    def call(self, command, *args, stdin=None, success=True, tool=TOOL, data=None):
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-X", "utf8", str(tool), command,
             "--data-dir", str(self.data if data is None else data), *map(str, args)],
            input=stdin.encode("utf-8") if stdin is not None else None,
            capture_output=True, cwd=tool.parent,
        )
        self.assertEqual(result.stderr.decode("utf-8"), "")
        response = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(response["ok"], success, response)
        self.assertEqual(result.returncode, 0 if success else 1, response)
        return response["data"] if success else response["error"]

    def add(self, score=None, story="story-a", branch="main", node="node-a", **kwargs):
        args = ["--story-id", story, "--branch-id", branch, "--node-id", node]
        if score is not None:
            args += ["--score", str(score)]
        args += kwargs.pop("args", [])
        return self.call("append", *args, **kwargs)

    def test_score_only_and_explicit_version(self):
        result = self.add(7, args=["--narrative-event-id", "narrative-a", "--narrative-sha256", "a" * 64])
        record = result["feedback"]
        self.assertEqual(record["score"], 7)
        self.assertIsNone(record["comment"])
        self.assertEqual(record["source_version"], {"narrative_event_id": "narrative-a", "narrative_sha256": "a" * 64})
        path = Path(result["file_path"]).resolve()
        self.assertTrue(path.is_relative_to(self.data))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["feedbacks"], [record])
        queried = self.call("query", "--feedback-id", record["feedback_id"])
        self.assertEqual(queried["items"], [record])
        self.assertEqual(queried["total"], 1)

    def test_exact_multiline_text_and_open_extra(self):
        text = '中文“引号”。  两个空格\r\n第二行。\n\n'
        comment = self.area / "comment.txt"
        comment.write_bytes(text.encode("utf-8"))
        extra = self.area / "extra.json"
        value = {"阅读情境": "一次读完", "自由栏目": ["甲", True, 3]}
        extra.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        first = self.add(7.5, args=["--comment-file", str(comment), "--extra-file", str(extra)])
        second = self.add(args=["--comment-file", "-"], stdin=text)
        self.assertEqual(first["feedback"]["comment"], text)
        self.assertEqual(first["feedback"]["extra"], value)
        self.assertEqual(second["feedback"]["comment"], text)
        self.assertIsNone(second["feedback"]["score"])
        self.assertEqual(self.call("query", "--keyword", "第二行")["total"], 2)

    def test_filters_order_and_pagination(self):
        a = self.add(7, args=["--comment", "Alpha"])
        b = self.add(9, node="node-b", args=["--comment", "Beta"])
        self.add(5, branch="fork", args=["--comment", "alpha again"])
        self.add(10, story="story-b")
        self.add(args=["--comment", "仅评价"])
        self.assertEqual(self.call("query", "--story-id", "story-a", "--branch-id", "main")["total"], 3)
        self.assertEqual(self.call("query", "--story-id", "story-a", "--node-id", "node-a")["total"], 3)
        selected = self.call("query", "--min-score", "7", "--max-score", "9")
        self.assertEqual([item["feedback_id"] for item in selected["items"]], [a["feedback"]["feedback_id"], b["feedback"]["feedback_id"]])
        self.assertEqual(self.call("query", "--keyword", "ALPHA")["total"], 2)
        page = self.call("query", "--story-id", "story-a", "--limit", "1")
        self.assertEqual(page["total"], 4)
        self.assertEqual(page["next_offset"], 1)
        following = self.call("query", "--story-id", "story-a", "--offset", "1", "--limit", "1")
        self.assertNotEqual(page["items"][0]["feedback_id"], following["items"][0]["feedback_id"])
        last = self.call("query", "--offset", "99")
        self.assertEqual(last["items"], [])
        self.assertIsNone(last["next_offset"])
        latest = self.call("query", "--descending", "--limit", "1")
        self.assertIsNone(latest["items"][0]["score"])

    def test_append_history_and_retry_identity(self):
        first = self.add(7, args=["--feedback-id", "feedback-fixed"])
        path = Path(first["file_path"])
        original = path.read_bytes()
        repeated = self.add(7, args=["--feedback-id", "feedback-fixed"])
        self.assertTrue(repeated["already_exists"])
        self.assertEqual(first["feedback"], repeated["feedback"])
        self.assertEqual(path.read_bytes(), original)
        changed = self.add(8, args=["--feedback-id", "feedback-fixed"], success=False)
        self.assertEqual(changed["code"], "IDEMPOTENCY_CONFLICT")
        self.add(8)
        self.add(args=["--comment", "重新阅读后补充评价"])
        self.assertEqual(self.call("query")["total"], 3)
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["feedbacks"][0], first["feedback"])
        self.assertEqual(len(document["feedbacks"]), 3)

    def test_directory_scope_and_input_validation(self):
        outside = ROOT.parent
        failure = self.call("query", data=outside, success=False)
        self.assertEqual(failure["code"], "PATH_OUT_OF_SCOPE")
        failure = self.add(7, args=["--comment-file", str(outside / "README.md")], success=False)
        self.assertEqual(failure["code"], "PATH_OUT_OF_SCOPE")
        failure = self.add(7, data=outside, success=False)
        self.assertEqual(failure["code"], "PATH_OUT_OF_SCOPE")
        self.add(11, success=False)
        self.add(args=["--comment", "  \n"], success=False)
        self.assertFalse(self.data.exists())
        self.assertEqual(self.call("query")["items"], [])
        self.assertFalse(self.data.exists())

    def test_standalone_copy_and_help(self):
        imported = set()
        for node in ast.walk(ast.parse(TOOL.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module.split(".")[0])
        self.assertTrue(imported <= sys.stdlib_module_names)
        clone = self.area / "independent"
        clone.mkdir()
        for filename in ("feedback.py", "schema.json"):
            shutil.copyfile(ROOT / filename, clone / filename)
        clone_tool = clone / "feedback.py"
        for args in (["--help"], ["append", "--help"], ["query", "--help"], ["migrate", "--help"]):
            help_result = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", str(clone_tool), *args],
                                         capture_output=True, cwd=clone)
            self.assertEqual(help_result.returncode, 0)
            self.assertEqual(help_result.stderr, b"")
        self.assertFalse((clone / "data").exists())
        self.assertEqual(self.call("query", tool=clone_tool, data=clone / "data")["total"], 0)
        result = self.add(7, tool=clone_tool, data=clone / "data")
        self.assertTrue(Path(result["file_path"]).resolve().is_relative_to(clone))
        self.assertEqual(self.call("query", tool=clone_tool, data=clone / "data")["total"], 1)


    def test_same_branch_uses_one_json_and_other_branches_are_separate(self):
        first = self.add(7)
        second = self.add(7.5, node="node-b")
        third = self.add(8, branch="fork")
        self.assertEqual(first["file_path"], second["file_path"])
        self.assertNotEqual(first["file_path"], third["file_path"])
        self.assertEqual(Path(first["file_path"]).name, "main.json")
        self.assertEqual(len(list(self.data.glob("*/*.json"))), 2)
        self.assertEqual(self.call("query", "--branch-id", "main")["total"], 2)

    def test_concurrent_append_keeps_all_feedback(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda index: self.add(7, node="node-" + str(index)), range(4)))
        self.assertEqual(len({result["file_path"] for result in results}), 1)
        queried = self.call("query")
        self.assertEqual(queried["total"], 4)
        self.assertEqual({record["node_id"] for record in queried["items"]}, {"node-" + str(index) for index in range(4)})

    def test_migrate_preserves_records_and_backup_bytes(self):
        first = self.add(7)
        second = self.add(7.5, node="node-b", args=["--comment", "原始优势；保留标点"])
        destination = Path(first["file_path"])
        originals = [first["feedback"], second["feedback"]]
        destination.unlink()
        legacy_bytes = {}
        for record in originals:
            path = destination.parent / (record["feedback_id"] + ".json")
            raw = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            path.write_bytes(raw)
            legacy_bytes[path.relative_to(ROOT).as_posix()] = raw
        try:
            migrated = self.call("migrate")
            self.assertEqual(migrated["migrated_records"], 2)
            with zipfile.ZipFile(migrated["backup_path"]) as archive:
                for name, original in legacy_bytes.items():
                    self.assertEqual(archive.read(name), original)
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8"))["feedbacks"], originals)
            self.assertEqual(list(self.data.glob("*/*.json")), [destination])
            self.assertEqual(self.call("query")["total"], 2)
            self.assertEqual(self.call("migrate")["migrated_records"], 0)
        finally:
            if "migrated" in locals():
                backup = Path(migrated["backup_path"]).resolve()
                self.assertTrue(backup.is_relative_to(ROOT))
                backup.unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)


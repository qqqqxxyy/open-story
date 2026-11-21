"""Independent, directory-scoped reader feedback; Python standard library only."""
import argparse
from contextlib import contextmanager
import msvcrt
import time
import zipfile
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parent


class FeedbackError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def fail(message):
    raise FeedbackError("INVALID_FEEDBACK", message)


def scoped(value):
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if not path.is_relative_to(ROOT):
        raise FeedbackError("PATH_OUT_OF_SCOPE", "Path must stay inside reader_feedback")
    return path


def no_constant(value):
    fail("Non-finite JSON numbers are not supported: " + value)


def read_json(path):
    with scoped(path).open("r", encoding="utf-8-sig", newline="") as stream:
        return json.load(stream, parse_constant=no_constant)


def schema():
    return read_json(ROOT / "schema.json")


def record_schema(spec):
    return spec["$defs"]["feedback_record"]


def valid_id(value, field, spec):
    spec = record_schema(spec)
    if not isinstance(value, str) or re.fullmatch(spec["properties"][field]["pattern"], value) is None:
        fail(field + " must contain letters, digits, underscores or hyphens and start with a letter or digit")
    if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", value):
        fail(field + " cannot be a reserved Windows filename")
    return value


def score_value(value, spec):
    if value is None:
        return None
    rule = record_schema(spec)["properties"]["score"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        fail("score must be a finite number")
    if not rule["minimum"] <= value <= rule["maximum"]:
        fail("score must be within " + str(rule["minimum"]) + ".." + str(rule["maximum"]))
    return int(value) if float(value).is_integer() else value


def validate(record, spec):
    if not isinstance(record, dict) or set(record) != set(record_schema(spec)["required"]):
        fail("Record fields do not match schema.json")
    if record["schema_version"] != record_schema(spec)["properties"]["schema_version"]["const"]:
        fail("Unsupported schema_version")
    for field in ("feedback_id", "story_id", "branch_id", "node_id"):
        valid_id(record[field], field, spec)
    score_value(record["score"], spec)
    comment = record["comment"]
    if comment is not None and not isinstance(comment, str):
        fail("comment must be a string or null")
    if record["score"] is None and (comment is None or not comment.strip()):
        fail("Provide a score or a nonblank comment")
    try:
        when = datetime.fromisoformat(record["recorded_at"])
    except (TypeError, ValueError):
        fail("recorded_at must be an ISO date-time")
    if when.tzinfo is None:
        fail("recorded_at must include a timezone")
    if not isinstance(record["extra"], dict):
        fail("extra must be an object")
    version = record["source_version"]
    if version is not None:
        rule = record_schema(spec)["properties"]["source_version"]
        if not isinstance(version, dict) or not version or set(version) - set(rule["properties"]):
            fail("source_version must contain a narrative_event_id or narrative_sha256")
        for key, value in version.items():
            if not isinstance(value, str) or not value:
                fail(key + " must be a nonempty string")
            pattern = rule["properties"][key].get("pattern")
            if pattern and re.fullmatch(pattern, value) is None:
                fail(key + " does not match its format")
    try:
        json.dumps(record, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError):
        fail("Record must contain only finite JSON values")
    return record


def validate_document(document, spec):
    if not isinstance(document, dict) or set(document) != set(spec["required"]):
        fail("Branch document fields do not match schema.json")
    if document["schema_version"] != spec["properties"]["schema_version"]["const"]:
        fail("Unsupported branch document version")
    for field in ("story_id", "branch_id"):
        valid_id(document[field], field, spec)
    if not isinstance(document["feedbacks"], list):
        fail("feedbacks must be an array")
    seen = set()
    for record in document["feedbacks"]:
        validate(record, spec)
        if any(record[field] != document[field] for field in ("story_id", "branch_id")):
            fail("Feedback belongs to a different story or branch")
        if record["feedback_id"] in seen:
            fail("Duplicate feedback_id in branch document")
        seen.add(record["feedback_id"])
    return document


def empty_document(story_id, branch_id, spec):
    return {"schema_version": spec["properties"]["schema_version"]["const"],
            "story_id": story_id, "branch_id": branch_id, "feedbacks": []}


def branch_path(directory, story_id, branch_id):
    return scoped(scoped(directory) / story_id / (branch_id + ".json"))


@contextmanager
def branch_lock(target):
    lock_path = scoped(target.with_suffix(".lock"))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        deadline = time.monotonic() + 5
        while True:
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise FeedbackError("FILE_BUSY", "Branch feedback file is busy; retry later")
                time.sleep(0.05)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def write_document(target, document, spec):
    validate_document(document, spec)
    target = scoped(target)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=target.parent, prefix=".feedback-", suffix=".tmp", delete=False) as stream:
            temporary = scoped(stream.name)
            stream.write(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def records(directory, spec):
    directory = scoped(directory)
    if not directory.exists():
        return []
    if not directory.is_dir():
        fail("data-dir must be a directory")
    result = []
    for path in sorted(directory.glob("*/*.json")):
        value = read_json(path)
        if isinstance(value, dict) and "feedback_id" in value:
            raise FeedbackError("MIGRATION_REQUIRED", "Run migrate to consolidate legacy feedback files")
        document = validate_document(value, spec)
        if path.parent.name != document["story_id"] or path.name != document["branch_id"] + ".json":
            fail("Branch identity does not match its file path: " + str(path))
        result.extend((scoped(path), record) for record in document["feedbacks"])
    return result


def comment_text(args):
    if args.comment_file is None:
        return args.comment
    if args.comment_file == "-":
        return sys.stdin.buffer.read().decode("utf-8-sig")
    with scoped(args.comment_file).open("r", encoding="utf-8-sig", newline="") as stream:
        return stream.read()


def append(args, spec):
    directory = scoped(args.data_dir)
    version = {}
    if args.narrative_event_id is not None:
        version["narrative_event_id"] = args.narrative_event_id
    if args.narrative_sha256 is not None:
        version["narrative_sha256"] = args.narrative_sha256.lower()
    record = validate({
        "schema_version": record_schema(spec)["properties"]["schema_version"]["const"],
        "feedback_id": args.feedback_id or "feedback-" + uuid4().hex,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "story_id": args.story_id,
        "branch_id": args.branch_id,
        "node_id": args.node_id,
        "score": score_value(args.score, spec),
        "comment": comment_text(args),
        "source_version": version or None,
        "extra": read_json(args.extra_file) if args.extra_file else {},
    }, spec)
    known = records(directory, spec)
    same_content = lambda item: json.dumps({k:v for k,v in item.items() if k != "recorded_at"}, sort_keys=True, ensure_ascii=False, allow_nan=False)
    if args.feedback_id:
        for path, old in known:
            if old["feedback_id"] != record["feedback_id"]:
                continue
            if same_content(old) != same_content(record):
                raise FeedbackError("IDEMPOTENCY_CONFLICT", "Existing feedback_id has different content")
            return {"feedback": old, "file_path": str(path), "already_exists": True}
    target = branch_path(directory, record["story_id"], record["branch_id"])
    with branch_lock(target):
        document = validate_document(read_json(target), spec) if target.exists() else empty_document(record["story_id"], record["branch_id"], spec)
        for old in document["feedbacks"]:
            if old["feedback_id"] == record["feedback_id"]:
                if same_content(old) != same_content(record):
                    raise FeedbackError("IDEMPOTENCY_CONFLICT", "Existing feedback_id has different content")
                return {"feedback": old, "file_path": str(target), "already_exists": True}
        document["feedbacks"].append(record)
        write_document(target, document, spec)
    return {"feedback": record, "file_path": str(target), "already_exists": False}


def query(args, spec):
    for field in ("story_id", "branch_id", "node_id", "feedback_id"):
        if getattr(args, field) is not None:
            valid_id(getattr(args, field), field, spec)
    for value in (args.min_score, args.max_score):
        score_value(value, spec)
    if args.min_score is not None and args.max_score is not None and args.min_score > args.max_score:
        fail("min-score cannot exceed max-score")
    if args.offset < 0 or args.limit < spec["$defs"]["query_limit"]["minimum"]:
        fail("offset must be nonnegative and limit must be positive")
    matches = []
    for _, record in records(args.data_dir, spec):
        if any(getattr(args, field) is not None and record[field] != getattr(args, field)
               for field in ("story_id", "branch_id", "node_id", "feedback_id")):
            continue
        score = record["score"]
        if args.min_score is not None and (score is None or score < args.min_score):
            continue
        if args.max_score is not None and (score is None or score > args.max_score):
            continue
        if args.keyword is not None and args.keyword.casefold() not in (record["comment"] or "").casefold():
            continue
        matches.append(record)
    matches.sort(key=lambda record: (datetime.fromisoformat(record["recorded_at"]), record["feedback_id"]), reverse=args.descending)
    page = matches[args.offset:args.offset + args.limit]
    end = args.offset + len(page)
    return {"items": page, "total": len(matches), "next_offset": end if end < len(matches) else None}


def migrate(args, spec):
    directory = scoped(args.data_dir)
    legacy = []
    if directory.exists():
        for path in sorted(directory.glob("*/*.json")):
            path = scoped(path)
            original = path.read_bytes()
            value = json.loads(original.decode("utf-8-sig"), parse_constant=no_constant)
            if isinstance(value, dict) and "feedback_id" in value:
                record = validate(value, spec)
                if path.parent.name != record["story_id"] or path.name != record["feedback_id"] + ".json":
                    fail("Legacy identity does not match its file path")
                if path.name == record["branch_id"] + ".json":
                    fail("Legacy filename conflicts with its branch destination")
                legacy.append((path, original, record))
            else:
                validate_document(value, spec)
    if not legacy:
        return {"migrated_records": 0, "branch_files": [], "backup_path": None}
    backup = scoped(ROOT / "backups" / ("feedback-v1-" + uuid4().hex + ".zip"))
    backup.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(backup, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, original, _ in legacy:
            archive.writestr(str(path.relative_to(ROOT)).replace("\\", "/"), original)
    with zipfile.ZipFile(backup) as archive:
        for path, original, _ in legacy:
            assert archive.read(str(path.relative_to(ROOT)).replace("\\", "/")) == original
    grouped = {}
    for entry in legacy:
        record = entry[2]
        grouped.setdefault((record["story_id"], record["branch_id"]), []).append(entry)
    destinations = []
    for (story_id, branch_id), entries in grouped.items():
        target = branch_path(directory, story_id, branch_id)
        with branch_lock(target):
            document = validate_document(read_json(target), spec) if target.exists() else empty_document(story_id, branch_id, spec)
            existing = {record["feedback_id"]: record for record in document["feedbacks"]}
            for _, _, record in sorted(entries, key=lambda item: (item[2]["recorded_at"], item[2]["feedback_id"])):
                old = existing.get(record["feedback_id"])
                if old is not None and old != record:
                    raise FeedbackError("IDEMPOTENCY_CONFLICT", "Migrated feedback_id has different existing content")
                if old is None:
                    document["feedbacks"].append(record)
                    existing[record["feedback_id"]] = record
            write_document(target, document, spec)
            saved = validate_document(read_json(target), spec)
            assert saved == document
            for path, original, _ in entries:
                path = scoped(path)
                if path.read_bytes() != original:
                    raise FeedbackError("FILE_CHANGED", "Legacy record changed during migration")
                path.unlink()
        destinations.append(str(target))
    return {"migrated_records": len(legacy), "branch_files": destinations, "backup_path": str(backup)}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise FeedbackError("INVALID_ARGUMENT", message)


def parser(spec):
    cli = Parser(description="独立的读者评分与评价文件工具；读写路径限定在本目录。")
    commands = cli.add_subparsers(dest="command", required=True, parser_class=Parser)
    add = commands.add_parser("append", help="追加一条评分或原始评价。")
    find = commands.add_parser("query", help="筛选并分页查询反馈；不访问故事库。")
    convert = commands.add_parser("migrate", help="将旧单条文件汇总为每个 story+branch 一个 JSON。")
    for command in (add, find, convert):
        command.add_argument("--data-dir", default=spec["$defs"]["data_directory"]["default"],
                             help="本目录内的数据子目录；相对路径从 reader_feedback 解析。")
    for name in ("story-id", "branch-id", "node-id"):
        add.add_argument("--" + name, required=True)
    rule = record_schema(spec)["properties"]["score"]
    add.add_argument("--score", type=float, help="十分制评分，范围 " + str(rule["minimum"]) + ".." + str(rule["maximum"]))
    text = add.add_mutually_exclusive_group()
    text.add_argument("--comment", help="原样保存的评价文字。")
    text.add_argument("--comment-file", help="本目录内的 UTF-8 文本文件；- 从 stdin 原样读取。")
    add.add_argument("--feedback-id", help="可选重试ID；相同ID与内容复用原记录。")
    add.add_argument("--narrative-event-id", help="显式提供的正文版本ID；脚本不访问故事库。")
    add.add_argument("--narrative-sha256", help="显式提供的正文 SHA-256。")
    add.add_argument("--extra-file", help="本目录内的 UTF-8 JSON 对象。")
    for name in ("story-id", "branch-id", "node-id", "feedback-id"):
        find.add_argument("--" + name)
    find.add_argument("--min-score", type=float)
    find.add_argument("--max-score", type=float)
    find.add_argument("--keyword", help="在原始评价中进行不区分大小写的子串查询。")
    find.add_argument("--offset", type=int, default=0)
    find.add_argument("--limit", type=int, default=spec["$defs"]["query_limit"]["default"])
    find.add_argument("--descending", action="store_true", help="按记录时间从新到旧返回。")
    return cli


def main():
    command = "unknown"
    try:
        spec = schema()
        args = parser(spec).parse_args()
        command = args.command
        result = {"append": append, "query": query, "migrate": migrate}[command](args, spec)
        response = {"ok": True, "operation": "reader_feedback." + command, "data": result, "error": None}
    except (FeedbackError, OSError, ValueError, TypeError) as exc:
        response = {"ok": False, "operation": "reader_feedback." + command, "data": None,
                    "error": {"code": getattr(exc, "code", "FILE_ERROR" if isinstance(exc, OSError) else "INVALID_FEEDBACK"), "message": str(exc)}}
    print(json.dumps(response, ensure_ascii=False, allow_nan=False))
    return 0 if response["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

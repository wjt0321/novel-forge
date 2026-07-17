"""Markdown-authoritative, per-book continuity memory and SQLite index."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping

from .models import NovelForgeError


MEMORY_SCHEMA_VERSION = 1
INDEX_SCHEMA_VERSION = 1
MARKER = "<!-- novel-forge-memory:v1 -->"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
KINDS = {"entity", "fact", "event", "knowledge", "promise"}
TIERS = {"hard", "active", "soft"}
CANDIDATE_STATUSES = {"candidate", "promoted", "rejected"}
ALL_STATUSES = CANDIDATE_STATUSES | {"canonical"}
KNOWLEDGE_STATES = {"known", "suspected", "false_belief"}
PROMISE_STATUSES = {
    "planned",
    "planted",
    "partially_paid",
    "paid_off",
    "abandoned",
}
CANON_DIRS = {
    "entity": "entities",
    "fact": "facts",
    "event": "events",
    "knowledge": "knowledge",
    "promise": "promises",
}
REQUIRED_KIND_FIELDS = {
    "entity": ("name", "entity_type"),
    "fact": ("subject", "predicate", "object", "valid_from"),
    "event": ("event_type", "participants"),
    "knowledge": ("knower", "proposition", "knowledge_state"),
    "promise": ("promise", "promise_status", "planted_chapter"),
}
COMMON_REQUIRED = (
    "schema_version",
    "id",
    "kind",
    "status",
    "tier",
    "chapter",
    "source_path",
    "evidence",
    "summary",
)


class BookMemoryError(NovelForgeError):
    """Raised when a books/ memory record or derived index is invalid."""


@dataclass(frozen=True)
class MemoryRecord:
    """Validated memory metadata extracted from a Markdown document."""

    data: dict[str, Any]

    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def kind(self) -> str:
        return self.data["kind"]

    @property
    def status(self) -> str:
        return self.data["status"]

    @property
    def tier(self) -> str:
        return self.data["tier"]

    @property
    def chapter(self) -> int:
        return self.data["chapter"]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _book_dir(root: Path, slug: str) -> Path:
    book_dir = Path(root) / "books" / slug
    if not book_dir.is_dir():
        raise BookMemoryError(f"books/ 项目不存在：{book_dir}")
    return book_dir


def _require_nonempty_string(data: Mapping[str, Any], field: str) -> None:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise BookMemoryError(f"记忆记录字段 {field} 必须是非空字符串。")


def _optional_chapter(data: Mapping[str, Any], field: str) -> None:
    value = data.get(field)
    if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
        raise BookMemoryError(f"记忆记录字段 {field} 必须是正整数或 null。")


def _validate_record_data(raw: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(raw)
    for field in COMMON_REQUIRED:
        if field not in data:
            raise BookMemoryError(f"记忆记录缺少字段：{field}")
    if data["schema_version"] != MEMORY_SCHEMA_VERSION:
        raise BookMemoryError(
            f"不支持的记忆 schema_version：{data['schema_version']}"
        )
    _require_nonempty_string(data, "id")
    if not ID_RE.fullmatch(data["id"]):
        raise BookMemoryError("记忆记录 id 只能包含 ASCII 字母、数字、点、下划线和连字符。")
    if data["kind"] not in KINDS:
        raise BookMemoryError(f"未知记忆 kind：{data['kind']}")
    if data["status"] not in ALL_STATUSES:
        raise BookMemoryError(f"未知记忆 status：{data['status']}")
    if data["tier"] not in TIERS:
        raise BookMemoryError(f"未知记忆 tier：{data['tier']}")
    _optional_chapter(data, "chapter")
    if data["chapter"] is None:
        raise BookMemoryError("记忆记录字段 chapter 必须是正整数。")
    for field in ("source_path", "evidence", "summary"):
        _require_nonempty_string(data, field)
    supersedes = data.get("supersedes")
    if supersedes is not None and (
        not isinstance(supersedes, str) or not ID_RE.fullmatch(supersedes)
    ):
        raise BookMemoryError("supersedes 必须是合法记录 id 或 null。")

    for field in REQUIRED_KIND_FIELDS[data["kind"]]:
        if field not in data:
            raise BookMemoryError(f"{data['kind']} 记录缺少字段：{field}")

    kind = data["kind"]
    if kind == "entity":
        _require_nonempty_string(data, "name")
        _require_nonempty_string(data, "entity_type")
        aliases = data.get("aliases", [])
        if not isinstance(aliases, list) or not all(
            isinstance(alias, str) and alias.strip() for alias in aliases
        ):
            raise BookMemoryError("entity.aliases 必须是非空字符串数组。")
    elif kind == "fact":
        for field in ("subject", "predicate"):
            _require_nonempty_string(data, field)
        if data["object"] is None or isinstance(data["object"], (dict, list)):
            raise BookMemoryError("fact.object 必须是标量值。")
        _optional_chapter(data, "valid_from")
        _optional_chapter(data, "valid_to")
        if data["valid_to"] is not None and data["valid_to"] < data["valid_from"]:
            raise BookMemoryError("fact.valid_to 不能早于 valid_from。")
    elif kind == "event":
        _require_nonempty_string(data, "event_type")
        participants = data["participants"]
        if not isinstance(participants, list) or not participants or not all(
            isinstance(item, str) and item.strip() for item in participants
        ):
            raise BookMemoryError("event.participants 必须是非空字符串数组。")
    elif kind == "knowledge":
        for field in ("knower", "proposition"):
            _require_nonempty_string(data, field)
        if data["knowledge_state"] not in KNOWLEDGE_STATES:
            raise BookMemoryError(
                f"未知 knowledge_state：{data['knowledge_state']}"
            )
    elif kind == "promise":
        _require_nonempty_string(data, "promise")
        if data["promise_status"] not in PROMISE_STATUSES:
            raise BookMemoryError(f"未知 promise_status：{data['promise_status']}")
        for field in ("planted_chapter", "target_chapter", "resolved_chapter"):
            _optional_chapter(data, field)
        related = data.get("related_entities", [])
        if not isinstance(related, list) or not all(
            isinstance(item, str) and item.strip() for item in related
        ):
            raise BookMemoryError("promise.related_entities 必须是字符串数组。")
    return data


def parse_memory_markdown(text: str) -> MemoryRecord:
    """Parse and validate the marked JSON metadata block in Markdown."""
    marker_pos = text.find(MARKER)
    if marker_pos < 0:
        raise BookMemoryError(f"记忆 Markdown 缺少标记：{MARKER}")
    tail = text[marker_pos + len(MARKER) :]
    match = re.search(r"```json\s*\n(.*?)\n```", tail, re.DOTALL | re.IGNORECASE)
    if not match:
        raise BookMemoryError("记忆 Markdown 缺少标记后的 fenced JSON 元数据块。")
    try:
        raw = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise BookMemoryError(f"记忆 JSON 无法解析：{exc}") from exc
    if not isinstance(raw, dict):
        raise BookMemoryError("记忆 JSON 顶层必须是对象。")
    return MemoryRecord(_validate_record_data(raw))


def render_memory_markdown(
    record: MemoryRecord | Mapping[str, Any], title: str | None = None
) -> str:
    """Render a validated record into a human-reviewable Markdown file."""
    data = record.data if isinstance(record, MemoryRecord) else dict(record)
    validated = _validate_record_data(data)
    heading = title or validated.get("summary") or validated["id"]
    metadata = json.dumps(validated, ensure_ascii=False, indent=2, sort_keys=True)
    return (
        f"# {heading}\n\n"
        f"{MARKER}\n"
        f"```json\n{metadata}\n```\n\n"
        "## 人工说明\n\n"
        "- 可在此补充解释；索引只读取上方 JSON 元数据。\n"
    )


def _replace_memory_metadata(text: str, data: Mapping[str, Any]) -> str:
    """Replace only the machine metadata block, preserving all human prose."""
    validated = _validate_record_data(data)
    marker_pos = text.find(MARKER)
    if marker_pos < 0:
        raise BookMemoryError(f"记忆 Markdown 缺少标记：{MARKER}")
    block = re.search(
        r"```json\s*\n(.*?)\n```",
        text[marker_pos + len(MARKER) :],
        re.DOTALL | re.IGNORECASE,
    )
    if not block:
        raise BookMemoryError("记忆 Markdown 缺少标记后的 fenced JSON 元数据块。")
    start = marker_pos + len(MARKER) + block.start()
    end = marker_pos + len(MARKER) + block.end()
    metadata = json.dumps(validated, ensure_ascii=False, indent=2, sort_keys=True)
    return text[:start] + f"```json\n{metadata}\n```" + text[end:]


def _relative_source(book_dir: Path, value: str, *, must_exist: bool = True) -> Path:
    posix = PurePosixPath(value.replace("\\", "/"))
    if posix.is_absolute() or ".." in posix.parts or not posix.parts:
        raise BookMemoryError("source_path 必须是本书目录内、不含 .. 的相对路径。")
    path = book_dir.joinpath(*posix.parts)
    try:
        path.resolve().relative_to(book_dir.resolve())
    except ValueError as exc:
        raise BookMemoryError("source_path 越出本书目录。") from exc
    if must_exist and not path.is_file():
        raise BookMemoryError(f"source_path 不存在：{value}")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_files(book_dir: Path) -> list[Path]:
    canon_dir = book_dir / "memory" / "canon"
    return sorted(path for path in canon_dir.rglob("*.md") if path.is_file()) if canon_dir.exists() else []


def _candidate_files(book_dir: Path) -> list[Path]:
    candidate_dir = book_dir / "memory" / "candidates"
    return sorted(path for path in candidate_dir.rglob("*.md") if path.is_file()) if candidate_dir.exists() else []


def _scan_records(
    book_dir: Path, paths: list[Path], expected_status: str | None = None
) -> list[tuple[Path, MemoryRecord]]:
    records: list[tuple[Path, MemoryRecord]] = []
    seen: dict[str, Path] = {}
    for path in paths:
        try:
            record = parse_memory_markdown(path.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, OSError) as exc:
            raise BookMemoryError(f"无法读取记忆记录 {path}: {exc}") from exc
        if expected_status and record.status != expected_status:
            rel = path.relative_to(book_dir).as_posix()
            raise BookMemoryError(
                f"{rel} status 应为 {expected_status}，实际为 {record.status}。"
            )
        if record.id in seen:
            raise BookMemoryError(
                f"重复记忆 id {record.id}：{seen[record.id]} 与 {path}"
            )
        _relative_source(book_dir, record.data["source_path"])
        seen[record.id] = path
        records.append((path, record))
    return records


def _validate_canonical_consistency(
    records: list[tuple[Path, MemoryRecord]],
) -> None:
    """Reject contradictory hard fact intervals in canonical Markdown."""
    facts = [record for _, record in records if record.kind == "fact"]
    for index, left in enumerate(facts):
        for right in facts[index + 1 :]:
            if (
                left.data["subject"] != right.data["subject"]
                or left.data["predicate"] != right.data["predicate"]
            ):
                continue
            if _intervals_overlap(
                left.data["valid_from"],
                left.data.get("valid_to"),
                right.data["valid_from"],
                right.data.get("valid_to"),
            ):
                raise BookMemoryError(
                    f"事实冲突：{left.id} 与 {right.id} 的有效期重叠 "
                    f"({left.data['subject']} / {left.data['predicate']})。"
                )


def _atomic_write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    kwargs = {} if isinstance(content, bytes) else {"encoding": "utf-8", "newline": "\n"}
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        with temp_path.open(mode, **kwargs) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


@contextmanager
def _index_lock(book_dir: Path) -> Iterator[None]:
    control = book_dir / ".novel-forge"
    control.mkdir(parents=True, exist_ok=True)
    lock_path = control / "index.lock"
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise BookMemoryError(
            f"记忆索引正被另一进程更新；若确认无进程运行，请检查 {lock_path}。"
        ) from exc
    try:
        os.write(fd, f"pid={os.getpid()} time={_now()}\n".encode("ascii"))
        os.close(fd)
        yield
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        lock_path.unlink(missing_ok=True)


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE source_files (
            path TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL,
            record_id TEXT NOT NULL UNIQUE
        );
        CREATE TABLE records (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            tier TEXT NOT NULL,
            chapter INTEGER NOT NULL,
            summary TEXT NOT NULL,
            source_path TEXT NOT NULL,
            evidence TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            supersedes TEXT,
            superseded_by TEXT,
            data_json TEXT NOT NULL
        );
        CREATE TABLE entities (
            record_id TEXT PRIMARY KEY REFERENCES records(id),
            name TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            aliases_json TEXT NOT NULL
        );
        CREATE TABLE facts (
            record_id TEXT PRIMARY KEY REFERENCES records(id),
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object_json TEXT NOT NULL,
            valid_from INTEGER NOT NULL,
            valid_to INTEGER
        );
        CREATE INDEX facts_lookup ON facts(subject, predicate, valid_from, valid_to);
        CREATE TABLE events (
            record_id TEXT PRIMARY KEY REFERENCES records(id),
            event_type TEXT NOT NULL,
            location TEXT
        );
        CREATE TABLE event_participants (
            record_id TEXT NOT NULL REFERENCES events(record_id),
            entity_id TEXT NOT NULL,
            PRIMARY KEY(record_id, entity_id)
        );
        CREATE TABLE knowledge (
            record_id TEXT PRIMARY KEY REFERENCES records(id),
            knower TEXT NOT NULL,
            proposition TEXT NOT NULL,
            knowledge_state TEXT NOT NULL
        );
        CREATE TABLE promises (
            record_id TEXT PRIMARY KEY REFERENCES records(id),
            promise_text TEXT NOT NULL,
            promise_status TEXT NOT NULL,
            planted_chapter INTEGER NOT NULL,
            target_chapter INTEGER,
            resolved_chapter INTEGER,
            related_entities_json TEXT NOT NULL
        );
        CREATE TABLE chapter_snapshots (
            chapter INTEGER PRIMARY KEY,
            generated_at TEXT NOT NULL,
            source_manifest_sha256 TEXT NOT NULL,
            context_path TEXT NOT NULL
        );
        """
    )


def _insert_record(
    conn: sqlite3.Connection, book_dir: Path, path: Path, record: MemoryRecord
) -> None:
    data = record.data
    rel = path.relative_to(book_dir).as_posix()
    source_path = _relative_source(book_dir, data["source_path"])
    source_hash = _sha256(source_path)
    conn.execute(
        "INSERT INTO source_files(path, sha256, record_id) VALUES (?, ?, ?)",
        (rel, _sha256(path), record.id),
    )
    conn.execute(
        """INSERT INTO records(
               id, kind, tier, chapter, summary, source_path, evidence,
               source_sha256, supersedes, superseded_by, data_json
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            record.id,
            record.kind,
            record.tier,
            record.chapter,
            data["summary"],
            data["source_path"],
            data["evidence"],
            source_hash,
            data.get("supersedes"),
            data.get("superseded_by"),
            json.dumps(data, ensure_ascii=False, sort_keys=True),
        ),
    )
    if record.kind == "entity":
        conn.execute(
            "INSERT INTO entities VALUES (?, ?, ?, ?)",
            (
                record.id,
                data["name"],
                data["entity_type"],
                json.dumps(data.get("aliases", []), ensure_ascii=False),
            ),
        )
    elif record.kind == "fact":
        conn.execute(
            "INSERT INTO facts VALUES (?, ?, ?, ?, ?, ?)",
            (
                record.id,
                data["subject"],
                data["predicate"],
                json.dumps(data["object"], ensure_ascii=False),
                data["valid_from"],
                data.get("valid_to"),
            ),
        )
    elif record.kind == "event":
        conn.execute(
            "INSERT INTO events VALUES (?, ?, ?)",
            (record.id, data["event_type"], data.get("location")),
        )
        conn.executemany(
            "INSERT INTO event_participants VALUES (?, ?)",
            [(record.id, participant) for participant in data["participants"]],
        )
    elif record.kind == "knowledge":
        conn.execute(
            "INSERT INTO knowledge VALUES (?, ?, ?, ?)",
            (
                record.id,
                data["knower"],
                data["proposition"],
                data["knowledge_state"],
            ),
        )
    elif record.kind == "promise":
        conn.execute(
            "INSERT INTO promises VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                record.id,
                data["promise"],
                data["promise_status"],
                data["planted_chapter"],
                data.get("target_chapter"),
                data.get("resolved_chapter"),
                json.dumps(data.get("related_entities", []), ensure_ascii=False),
            ),
        )


def rebuild_memory_index(root: Path, slug: str) -> dict[str, Any]:
    """Atomically rebuild the disposable per-book index from canonical Markdown."""
    book_dir = _book_dir(root, slug)
    records = _scan_records(book_dir, _canonical_files(book_dir), "canonical")
    _validate_canonical_consistency(records)
    control = book_dir / ".novel-forge"
    control.mkdir(parents=True, exist_ok=True)
    db_path = control / "index.sqlite3"
    manifest_path = control / "source-manifest.json"
    counts = {kind: 0 for kind in sorted(KINDS)}
    sources = []
    for path, record in records:
        counts[record.kind] += 1
        sources.append(
            {
                "path": path.relative_to(book_dir).as_posix(),
                "sha256": _sha256(path),
                "record_id": record.id,
                "evidence_path": record.data["source_path"],
                "evidence_sha256": _sha256(
                    _relative_source(book_dir, record.data["source_path"])
                ),
            }
        )
    manifest = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "generated_at": _now(),
        "sources": sources,
    }

    with _index_lock(book_dir):
        fd, temp_name = tempfile.mkstemp(prefix=".index.", suffix=".sqlite3", dir=control)
        os.close(fd)
        temp_db = Path(temp_name)
        try:
            with closing(sqlite3.connect(temp_db)) as conn:
                _create_schema(conn)
                conn.executemany(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    (
                        ("index_schema_version", str(INDEX_SCHEMA_VERSION)),
                        ("memory_schema_version", str(MEMORY_SCHEMA_VERSION)),
                        ("generated_at", manifest["generated_at"]),
                    ),
                )
                for path, record in records:
                    _insert_record(conn, book_dir, path, record)
                conn.commit()
                check = conn.execute("PRAGMA integrity_check").fetchone()[0]
                if check != "ok":
                    raise BookMemoryError(f"新记忆索引完整性检查失败：{check}")
            os.replace(temp_db, db_path)
            _atomic_write(
                manifest_path,
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            )
        finally:
            temp_db.unlink(missing_ok=True)
    return {
        "index_path": db_path.relative_to(book_dir).as_posix(),
        "manifest_path": manifest_path.relative_to(book_dir).as_posix(),
        "record_count": len(records),
        "counts_by_kind": counts,
    }


def _read_manifest(book_dir: Path) -> dict[str, Any] | None:
    path = book_dir / ".novel-forge" / "source-manifest.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def memory_status(root: Path, slug: str) -> dict[str, Any]:
    """Report whether the derived index exactly matches canonical Markdown."""
    book_dir = _book_dir(root, slug)
    db_path = book_dir / ".novel-forge" / "index.sqlite3"
    manifest = _read_manifest(book_dir)
    current = {
        path.relative_to(book_dir).as_posix(): _sha256(path)
        for path in _canonical_files(book_dir)
    }
    expected = {
        item.get("path"): item.get("sha256")
        for item in (manifest or {}).get("sources", [])
        if isinstance(item, dict)
    }
    changed = sorted(
        path for path in set(current) | set(expected) if current.get(path) != expected.get(path)
    )
    expected_evidence = {
        item.get("evidence_path"): item.get("evidence_sha256")
        for item in (manifest or {}).get("sources", [])
        if isinstance(item, dict) and item.get("evidence_path")
    }
    current_evidence: dict[str, str | None] = {}
    for path in expected_evidence:
        try:
            source = _relative_source(book_dir, path)
            current_evidence[path] = _sha256(source)
        except BookMemoryError:
            current_evidence[path] = None
    changed_evidence = sorted(
        path
        for path in expected_evidence
        if current_evidence.get(path) != expected_evidence[path]
    )
    if manifest is None or not db_path.is_file():
        state = "missing"
    elif (
        manifest.get("schema_version") != INDEX_SCHEMA_VERSION
        or changed
        or changed_evidence
    ):
        state = "stale"
    else:
        try:
            with closing(
                sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            ) as conn:
                schema = conn.execute(
                    "SELECT value FROM metadata WHERE key = 'index_schema_version'"
                ).fetchone()
                integrity = conn.execute("PRAGMA quick_check").fetchone()
            state = (
                "clean"
                if schema
                and schema[0] == str(INDEX_SCHEMA_VERSION)
                and integrity
                and integrity[0] == "ok"
                else "stale"
            )
        except sqlite3.Error:
            state = "stale"

    pending = 0
    invalid_candidates: list[str] = []
    for path in _candidate_files(book_dir):
        try:
            if parse_memory_markdown(path.read_text(encoding="utf-8-sig")).status == "candidate":
                pending += 1
        except (BookMemoryError, OSError, UnicodeDecodeError):
            invalid_candidates.append(path.relative_to(book_dir).as_posix())
    return {
        "state": state,
        "index_path": ".novel-forge/index.sqlite3",
        "record_count": len(current),
        "candidate_count": pending,
        "changed_sources": changed,
        "changed_evidence_sources": changed_evidence,
        "invalid_candidates": invalid_candidates,
    }


def _safe_input_file(path: Path) -> Path:
    if not path.is_absolute():
        raise BookMemoryError("--file 必须是绝对路径。")
    resolved = path.resolve()
    if not resolved.is_file():
        raise BookMemoryError(f"候选记录文件不存在：{path}")
    try:
        resolved.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BookMemoryError(f"候选记录不是有效 UTF-8：{path}") from exc
    return resolved


def record_candidate(root: Path, slug: str, source_file: Path) -> dict[str, Any]:
    """Validate and copy a candidate record into the book without overwriting."""
    book_dir = _book_dir(root, slug)
    source = _safe_input_file(source_file)
    record = parse_memory_markdown(source.read_text(encoding="utf-8-sig"))
    if record.status != "candidate":
        raise BookMemoryError("新候选记录 status 必须是 candidate。")
    _relative_source(book_dir, record.data["source_path"])

    for path in _canonical_files(book_dir) + _candidate_files(book_dir):
        existing = parse_memory_markdown(path.read_text(encoding="utf-8-sig"))
        if existing.id == record.id:
            raise BookMemoryError(f"记忆 id 已存在：{record.id} ({path})")
    target = (
        book_dir
        / "memory"
        / "candidates"
        / f"ch{record.chapter:02d}"
        / f"{record.id}.md"
    )
    _atomic_write(target, source.read_bytes())
    return {
        "record_id": record.id,
        "kind": record.kind,
        "chapter": record.chapter,
        "candidate_path": target.relative_to(book_dir).as_posix(),
    }


def _intervals_overlap(
    start_a: int, end_a: int | None, start_b: int, end_b: int | None
) -> bool:
    infinity = 2**63 - 1
    return start_a <= (end_b if end_b is not None else infinity) and start_b <= (
        end_a if end_a is not None else infinity
    )


def _find_candidate(book_dir: Path, candidate_id: str) -> tuple[Path, MemoryRecord]:
    matches = []
    for path in _candidate_files(book_dir):
        record = parse_memory_markdown(path.read_text(encoding="utf-8-sig"))
        if record.id == candidate_id:
            matches.append((path, record))
    if not matches:
        raise BookMemoryError(f"找不到候选记忆：{candidate_id}")
    if len(matches) > 1:
        raise BookMemoryError(f"候选记忆 id 重复：{candidate_id}")
    return matches[0]


def promote_candidate(root: Path, slug: str, candidate_id: str) -> dict[str, Any]:
    """Promote one candidate after checking canonical Markdown for conflicts."""
    book_dir = _book_dir(root, slug)
    candidate_path, candidate = _find_candidate(book_dir, candidate_id)
    if candidate.status != "candidate":
        raise BookMemoryError(
            f"候选记忆 {candidate_id} 当前状态为 {candidate.status}，不能晋升。"
        )
    canon = _scan_records(book_dir, _canonical_files(book_dir), "canonical")
    by_id = {record.id: (path, record) for path, record in canon}
    if candidate.id in by_id:
        raise BookMemoryError(f"canonical id 已存在：{candidate.id}")

    supersedes = candidate.data.get("supersedes")
    old_pair = by_id.get(supersedes) if supersedes else None
    if supersedes and old_pair is None:
        raise BookMemoryError(f"supersedes 指向不存在的 canonical 记录：{supersedes}")
    if old_pair and old_pair[1].kind != candidate.kind:
        raise BookMemoryError("supersedes 只能指向同 kind 的 canonical 记录。")

    if candidate.kind == "fact":
        for _, existing in canon:
            same_slot = (
                existing.kind == "fact"
                and existing.data["subject"] == candidate.data["subject"]
                and existing.data["predicate"] == candidate.data["predicate"]
            )
            overlap = same_slot and _intervals_overlap(
                existing.data["valid_from"],
                existing.data.get("valid_to"),
                candidate.data["valid_from"],
                candidate.data.get("valid_to"),
            )
            if overlap and existing.id != supersedes:
                raise BookMemoryError(
                    f"事实冲突：{candidate.id} 与 {existing.id} 的有效期重叠；"
                    "请修正有效期或用 supersedes 显式衔接。"
                )
        if old_pair:
            old = old_pair[1]
            if (
                old.data["subject"] != candidate.data["subject"]
                or old.data["predicate"] != candidate.data["predicate"]
            ):
                raise BookMemoryError("fact supersedes 必须保持相同 subject/predicate。")
            if candidate.data["valid_from"] <= old.data["valid_from"]:
                raise BookMemoryError("新事实 valid_from 必须晚于被取代事实。")

    target = (
        book_dir
        / "memory"
        / "canon"
        / CANON_DIRS[candidate.kind]
        / f"{candidate.id}.md"
    )
    if target.exists():
        raise BookMemoryError(f"canonical 目标已存在：{target}")

    backups: dict[Path, bytes | None] = {
        target: None,
        candidate_path: candidate_path.read_bytes(),
    }
    if old_pair:
        backups[old_pair[0]] = old_pair[0].read_bytes()
    try:
        if old_pair:
            old_path, old_record = old_pair
            old_data = dict(old_record.data)
            old_data["superseded_by"] = candidate.id
            if candidate.kind == "fact" and old_data.get("valid_to") is None:
                old_data["valid_to"] = candidate.data["valid_from"] - 1
            old_text = old_path.read_text(encoding="utf-8-sig")
            _atomic_write(old_path, _replace_memory_metadata(old_text, old_data))

        canonical_data = dict(candidate.data)
        canonical_data["status"] = "canonical"
        canonical_data["promoted_at"] = _now()
        candidate_text = candidate_path.read_text(encoding="utf-8-sig")
        _atomic_write(
            target,
            _replace_memory_metadata(candidate_text, canonical_data),
        )
        index_result = rebuild_memory_index(root, slug)

        candidate_data = dict(candidate.data)
        candidate_data["status"] = "promoted"
        candidate_data["promoted_at"] = canonical_data["promoted_at"]
        candidate_data["canonical_path"] = target.relative_to(book_dir).as_posix()
        _atomic_write(
            candidate_path,
            _replace_memory_metadata(candidate_text, candidate_data),
        )
    except Exception:
        for path, content in backups.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_write(path, content)
        try:
            rebuild_memory_index(root, slug)
        except Exception:
            pass
        raise
    return {
        "record_id": candidate.id,
        "canonical_path": target.relative_to(book_dir).as_posix(),
        "candidate_path": candidate_path.relative_to(book_dir).as_posix(),
        "superseded": supersedes,
        "index": index_result,
    }


def _manifest_digest(book_dir: Path) -> str:
    path = book_dir / ".novel-forge" / "source-manifest.json"
    return _sha256(path)


def build_context_packet(root: Path, slug: str, chapter: int) -> dict[str, Any]:
    """Build a bounded chapter context packet from a verified clean index."""
    if chapter < 1:
        raise BookMemoryError("chapter 必须是正整数。")
    book_dir = _book_dir(root, slug)
    status = memory_status(root, slug)
    if status["state"] != "clean":
        raise BookMemoryError(
            f"记忆索引状态为 {status['state']}，请先运行 rebuild-memory-index。"
        )
    db_path = book_dir / ".novel-forge" / "index.sqlite3"
    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        fact_rows = conn.execute(
            """SELECT r.id, r.summary, r.source_path, r.evidence, r.tier
               FROM facts f JOIN records r ON r.id = f.record_id
               WHERE f.valid_from <= ? AND (f.valid_to IS NULL OR f.valid_to >= ?)
               ORDER BY r.id""",
            (chapter, chapter),
        ).fetchall()
        knowledge_rows = conn.execute(
            """SELECT r.id, r.summary, r.source_path, r.evidence, r.tier
               FROM knowledge k JOIN records r ON r.id = k.record_id
               WHERE r.chapter <= ? ORDER BY r.id""",
            (chapter,),
        ).fetchall()
        promise_rows = conn.execute(
            """SELECT r.id, r.summary, r.source_path, r.evidence, r.tier,
                      p.promise_status, p.target_chapter
               FROM promises p JOIN records r ON r.id = p.record_id
               WHERE p.planted_chapter <= ?
                 AND p.promise_status NOT IN ('paid_off', 'abandoned')
               ORDER BY CASE WHEN p.target_chapter IS NULL THEN 1 ELSE 0 END,
                        p.target_chapter, r.id""",
            (chapter,),
        ).fetchall()
        event_rows = conn.execute(
            """SELECT id, summary, source_path, evidence, tier FROM records
               WHERE kind = 'event' AND chapter <= ?
               ORDER BY chapter DESC, id LIMIT 12""",
            (chapter,),
        ).fetchall()
        entity_rows = conn.execute(
            """SELECT id, summary, source_path, evidence, tier FROM records
               WHERE kind = 'entity' ORDER BY id"""
        ).fetchall()

    due_promises = [
        row
        for row in promise_rows
        if row["target_chapter"] is not None and row["target_chapter"] <= chapter
    ]
    all_rows = list(fact_rows) + list(knowledge_rows) + list(promise_rows) + list(event_rows) + list(entity_rows)
    hard = [row for row in all_rows if row["tier"] == "hard"]
    active = [row for row in all_rows if row["tier"] == "active"]
    soft = [row for row in all_rows if row["tier"] == "soft"]

    def section(title: str, rows: list[sqlite3.Row]) -> list[str]:
        lines = [f"## {title}", ""]
        if not rows:
            lines.append("- 无")
        else:
            seen: set[str] = set()
            for row in rows:
                if row["id"] in seen:
                    continue
                seen.add(row["id"])
                lines.append(
                    f"- `{row['id']}` {row['summary']} "
                    f"（来源：`{row['source_path']}`；证据：{row['evidence']}）"
                )
        lines.append("")
        return lines

    lines = [
        f"# 第 {chapter:02d} 章记忆上下文",
        "",
        f"- generated_at: {_now()}",
        f"- source_manifest_sha256: `{_manifest_digest(book_dir)}`",
        "- 本文件是可删除缓存；权威源为 `memory/canon/**/*.md`。",
        "",
    ]
    lines += section("P0 硬事实", hard)
    lines += section("P0 本章有效事实", list(fact_rows))
    lines += section("P1 活跃叙事", active)
    lines += section("P1 到期承诺", due_promises)
    lines += section("P2 软纹理", soft)
    target = book_dir / "memory" / "context-cache" / f"ch{chapter:02d}-memory.md"
    _atomic_write(target, "\n".join(lines))

    # Snapshot metadata is disposable and may be updated independently of canon.
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """INSERT INTO chapter_snapshots(chapter, generated_at, source_manifest_sha256, context_path)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(chapter) DO UPDATE SET
                 generated_at = excluded.generated_at,
                 source_manifest_sha256 = excluded.source_manifest_sha256,
                 context_path = excluded.context_path""",
            (
                chapter,
                _now(),
                _manifest_digest(book_dir),
                target.relative_to(book_dir).as_posix(),
            ),
        )
        conn.commit()
    return {
        "chapter": chapter,
        "context_path": target.relative_to(book_dir).as_posix(),
        "counts": {
            "facts": len(fact_rows),
            "knowledge": len(knowledge_rows),
            "open_promises": len(promise_rows),
            "due_promises": len(due_promises),
            "events": len(event_rows),
            "entities": len(entity_rows),
            "hard": len({row["id"] for row in hard}),
            "active": len({row["id"] for row in active}),
            "soft": len({row["id"] for row in soft}),
        },
        "record_ids": sorted({row["id"] for row in all_rows}),
    }

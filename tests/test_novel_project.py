"""Tests for the new books/<slug>/ project layout."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import app.novel_forge
from app.novel_forge.project_templates import init_book_project
from app.novel_forge.service import NovelForgeService
from app.novel_forge.skill_adapter import main

_REPO_ROOT = Path(app.novel_forge.__file__).resolve().parents[2]


def _tool_env() -> dict:
    env = dict(os.environ)
    env["NOVEL_FORGE_ROOT"] = str(_REPO_ROOT)
    return env


def _json_output(capsys) -> dict:
    out = capsys.readouterr().out.strip()
    return json.loads(out)


def test_init_book_project_creates_expected_structure(tmp_path: Path):
    result = init_book_project(tmp_path, "test-book", "Test Book", "现实悬疑")

    book_dir = Path(result["book_dir"])
    assert book_dir == tmp_path / "books" / "test-book"
    assert (book_dir / ".gitignore").exists()
    assert (book_dir / "CLAUDE.md").exists()
    assert (book_dir / "README.md").exists()
    assert (book_dir / "chapters").is_dir()
    assert (book_dir / "memory" / "entities").is_dir()
    assert (book_dir / "memory" / "future").is_dir()
    assert (book_dir / "memory" / "context-cache").is_dir()
    assert (book_dir / "memory" / "candidates").is_dir()
    assert (book_dir / "memory" / "canon" / "entities").is_dir()
    assert (book_dir / "memory" / "canon" / "facts").is_dir()
    assert (book_dir / "memory" / "canon" / "events").is_dir()
    assert (book_dir / "memory" / "canon" / "knowledge").is_dir()
    assert (book_dir / "memory" / "canon" / "promises").is_dir()
    assert (book_dir / ".novel-forge").is_dir()
    assert (book_dir / "memory" / "MEMORY.md").exists()
    assert (book_dir / "memory" / "memory-record-template.md").exists()
    assert (book_dir / "planning" / "events").is_dir()
    assert (book_dir / "reviews" / "archive").is_dir()
    assert (book_dir / "patches").is_dir()
    assert (book_dir / ".snapshots").is_dir()
    assert (book_dir / "tools" / "quality_check.py").exists()
    assert (book_dir / "tools" / "narrative_gate.py").exists()
    assert (book_dir / "planning" / "chapter-state").is_dir()
    assert (book_dir / "planning" / "scene-package-template.md").exists()
    assert (book_dir / "planning" / "action-draft-template.md").exists()
    assert (book_dir / "planning" / "dialogue-ledger-template.md").exists()
    assert (book_dir / "planning" / "chapter-state-template.md").exists()
    assert (book_dir / "evaluation" / "constitution.md").exists()
    assert (book_dir / "evaluation" / "case-template.md").exists()
    assert (book_dir / "evaluation" / "experiment-template.md").exists()
    assert (book_dir / "evaluation" / "rule-registry.md").exists()
    assert (book_dir / "evaluation" / "generation-template.md").exists()
    assert (book_dir / "evaluation" / "degraded-run-template.md").exists()
    assert (book_dir / "evaluation" / "branch-decision-template.md").exists()
    assert (book_dir / "evaluation" / "blind-evaluation-template.md").exists()
    assert (book_dir / "evaluation" / "preference-template.md").exists()
    assert (book_dir / "evaluation" / "arc-audit-template.md").exists()
    assert (book_dir / "evaluation" / "rule-decision-template.md").exists()
    assert (book_dir / "evidence" / "preferences").is_dir()
    assert (book_dir / "evidence" / "branches").is_dir()
    assert (book_dir / "evidence" / "evaluations").is_dir()
    assert (book_dir / "evidence" / "generations").is_dir()
    assert (book_dir / "evidence" / "arc-audits").is_dir()
    assert (book_dir / "evidence" / "rule-decisions").is_dir()
    assert (book_dir / ".claude" / "agents" / "context-collector.md").exists()
    assert (book_dir / ".claude" / "agents" / "consistency-guard.md").exists()
    assert (book_dir / ".claude" / "agents" / "chapter-editor.md").exists()
    assert (book_dir / ".claude" / "agents" / "causal-editor.md").exists()
    assert (book_dir / ".claude" / "agents" / "line-editor.md").exists()
    assert (book_dir / ".claude" / "agents" / "orchestrator.md").exists()

    claude_md = (book_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Test Book" in claude_md
    assert "test-book" in claude_md
    assert "chapters/eXX/ch-XX/正文.md" in claude_md
    assert "工作流版本" in claude_md
    assert "v3.6" in claude_md
    assert "严禁复制其他书的正文" in claude_md
    assert "build-memory-context" in claude_md
    assert "memory/canon" in claude_md
    assert "evidence-status" in claude_md
    assert "record-evidence" in claude_md
    assert "set-draft-mode" in claude_md
    assert "no-deliberate-defects" in claude_md
    assert "single-winner-branch" in claude_md
    assert "model-score-not-approval" in claude_md
    assert "aesthetic-does-not-override-facts" in claude_md
    assert "exploration-not-ready" in claude_md
    assert "role-name-not-independence" in claude_md
    assert "world-not-protagonist-proof" in claude_md
    assert "expertise-must-be-executable" in claude_md

    readme = (book_dir / "README.md").read_text(encoding="utf-8")
    assert "Test Book" in readme
    assert "默认工作流: v3" in readme
    assert "不得复制其他书的正文" in readme

    gitignore = (book_dir / ".gitignore").read_text(encoding="utf-8")
    assert ".novel-forge/" in gitignore

    constitution = (book_dir / "evaluation" / "constitution.md").read_text(
        encoding="utf-8"
    )
    assert "事实秩序" in constitution
    assert "因果秩序" in constitution
    assert "人物认知的有限性" in constitution
    assert "表达的不均匀" in constitution
    assert "作者偏好" in constitution
    assert "不得故意加入错别字" in constitution
    assert "模型评分不是作者批准" in constitution
    assert "不得静默拼接全部候选" in constitution
    assert "不得仿写在世作者" in constitution

    scene_template = (
        book_dir / "planning" / "scene-package-template.md"
    ).read_text(encoding="utf-8")
    assert "## 1d. 认知与可证伪假设" in scene_template
    assert "## 0b. 章际交接" in scene_template
    assert "上一章正文 SHA-256" in scene_template
    assert "same_day_continuous" in scene_template
    assert "## 1e. 规划反证与常识检查" in scene_template
    assert "## 3c. 因果归属账本" in scene_template
    assert "## 5b. 专业判断审计" in scene_template
    assert "可推翻证据" in scene_template
    assert "后果承担者" in scene_template
    assert "物理动作机制" in scene_template

    generation_template = (
        book_dir / "evaluation" / "generation-template.md"
    ).read_text(encoding="utf-8")
    assert '"elapsed_seconds"' in generation_template
    assert '"review_round"' in generation_template
    assert '"generation_stage"' in generation_template
    assert '"provenance_confidence"' in generation_template
    assert '"run_id"' in generation_template
    assert '"agent_harness"' in generation_template
    assert '"reasoning_effort"' in generation_template
    assert '"sandbox_profile"' in generation_template
    assert '"tool_capabilities"' in generation_template
    assert '"tool_failures"' in generation_template

    degraded_template = (
        book_dir / "evaluation" / "degraded-run-template.md"
    ).read_text(encoding="utf-8")
    assert "degraded_exploration" in degraded_template
    assert "tool_failures" in degraded_template
    assert "不得进入 ready" in degraded_template

    review_template = (
        book_dir / "reviews" / "review-template.md"
    ).read_text(encoding="utf-8")
    assert "previous_chapter_sha256" in review_template
    assert "evidence_quote" in review_template
    assert "previous_chapter_quote" in review_template

    memory_template = (
        book_dir / "memory" / "memory-record-template.md"
    ).read_text(encoding="utf-8")
    assert '"salience": "medium"' in memory_template

    causal_editor = (
        book_dir / ".claude" / "agents" / "causal-editor.md"
    ).read_text(encoding="utf-8")
    chapter_editor = (
        book_dir / ".claude" / "agents" / "chapter-editor.md"
    ).read_text(encoding="utf-8")
    orchestrator = (
        book_dir / ".claude" / "agents" / "orchestrator.md"
    ).read_text(encoding="utf-8")
    assert "先只读正文" in causal_editor
    assert "先只读正文" in chapter_editor
    assert "不得询问是否开始审核" in orchestrator
    assert "第三份 generation" in orchestrator
    assert "degraded_exploration" in orchestrator
    assert "不同正文 SHA-256" in orchestrator
    assert "上一章正文 SHA-256" in (
        book_dir / ".claude" / "agents" / "consistency-guard.md"
    ).read_text(encoding="utf-8")
    assert "previous_chapter_quote" in chapter_editor



def test_generated_narrative_gate_rejects_unfilled_scene_package(tmp_path: Path):
    result = init_book_project(tmp_path, "gate-book", "Gate Book", "悬疑")
    book_dir = Path(result["book_dir"])
    chapter = book_dir / "chapter.md"
    chapter.write_text("# 第一章\n\n甲走进门。\n\n乙没有起身。\n\n雨停了。\n", encoding="utf-8")
    package = book_dir / "planning" / "scene-package-ch01.md"
    package.write_text(
        (book_dir / "planning" / "scene-package-template.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    script = book_dir / "tools" / "narrative_gate.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(chapter), str(package)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=_tool_env(),
    )
    assert proc.returncode == 1
    assert "scene-package 缺少或未填写章节" in proc.stdout


def test_init_book_project_does_not_overwrite_existing_files(tmp_path: Path):
    book_dir = tmp_path / "books" / "preserve"
    (book_dir / ".claude" / "agents").mkdir(parents=True)
    (book_dir / "CLAUDE.md").write_text("existing", encoding="utf-8")
    (book_dir / ".claude" / "agents" / "context-collector.md").write_text(
        "custom agent", encoding="utf-8"
    )

    result = init_book_project(tmp_path, "preserve", "Preserve", "科幻")

    assert "CLAUDE.md" in result["skipped_files"]
    assert ".claude/agents/context-collector.md" in result["skipped_files"]
    assert (book_dir / "README.md").exists()
    assert (book_dir / "CLAUDE.md").read_text(encoding="utf-8") == "existing"
    assert (
        book_dir / ".claude" / "agents" / "context-collector.md"
    ).read_text(encoding="utf-8") == "custom agent"


def test_init_book_project_rejects_bad_slug():
    with pytest.raises(Exception):
        init_book_project(Path("/tmp"), "bad slug!", "Title", "Genre")


def test_adapter_init_novel_project_requires_confirm(tmp_path: Path, capsys):
    code = main(
        [
            "--root",
            str(tmp_path),
            "init-novel-project",
            "new-book",
            "--title",
            "New Book",
            "--genre",
            "悬疑",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"
    assert not (tmp_path / "books" / "new-book").exists()


def test_adapter_init_novel_project_success(tmp_path: Path, capsys):
    code = main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "init-novel-project",
            "init-novel-project",
            "new-book",
            "--title",
            "New Book",
            "--genre",
            "悬疑",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["operation"] == "init-novel-project"
    assert data["state_changed"] is True
    assert "created_files" in data["data"]
    assert (tmp_path / "books" / "new-book" / "CLAUDE.md").exists()
    # Adapter must not leak file contents.
    assert "小说宪法" not in json.dumps(data)


def test_service_init_novel_project_does_not_require_database(tmp_path: Path):
    # The new project layout is filesystem-only; service can still be used
    # without an existing library/ data/ setup.
    svc = NovelForgeService(tmp_path)
    result = svc.init_novel_project("fs-only", "FS Only", "短篇")
    assert (tmp_path / "books" / "fs-only" / "tools" / "quality_check.py").exists()


def test_quality_check_script_detects_issues(tmp_path: Path):
    init_book_project(tmp_path, "qc", "QC", "测试")
    script = tmp_path / "books" / "qc" / "tools" / "quality_check.py"
    sample = tmp_path / "sample.md"
    sample.write_text(
        '她说""你好""。\n'
        "你好吗。\n"
        "为人民服务五个字。\n"
        "不是A而是B。\n"
        "他有——把枪。\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(script), str(sample)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=_tool_env(),
    )
    assert proc.returncode == 0, proc.stderr
    output = proc.stdout
    assert output is not None
    assert "quote-duplication" in output
    assert "question-mark-mismatch" in output
    assert "word-count-tic" in output
    assert "not-is-flip" in output
    assert "em-dash" in output


def test_quality_check_script_clean_file(tmp_path: Path):
    init_book_project(tmp_path, "qc2", "QC2", "测试")
    script = tmp_path / "books" / "qc2" / "tools" / "quality_check.py"
    sample = tmp_path / "clean.md"
    sample.write_text('她说："你好。"\n天黑了。\n', encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(script), str(sample)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=_tool_env(),
    )
    assert proc.returncode == 0, proc.stderr
    # Canonical lint always appends a file-level colon-density metric for
    # CJK text, so "clean" means: no blocking findings and no rule findings
    # other than the metrics row.
    assert "Blocking: 0" in proc.stdout
    assert "em-dash" not in proc.stdout
    assert "not-is-flip" not in proc.stdout


def test_skill_dual_location_copies_are_identical():
    """The skill ships in two harness scan locations; they must not drift."""
    agents_copy = _REPO_ROOT / ".agents/skills/novel-forge/SKILL.md"
    claude_copy = _REPO_ROOT / ".claude/skills/novel-forge/SKILL.md"
    assert agents_copy.exists(), "missing .agents/skills/novel-forge/SKILL.md"
    assert claude_copy.exists(), "missing .claude/skills/novel-forge/SKILL.md"
    assert agents_copy.read_bytes() == claude_copy.read_bytes(), (
        "SKILL.md copies drifted; edit .agents/skills/ (canonical) and re-sync .claude/skills/"
    )


def test_skill_frontmatter_has_required_fields():
    import re

    text = (_REPO_ROOT / ".agents/skills/novel-forge/SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---")
    frontmatter = text.split("---", 2)[1]
    assert re.search(r"^name:\s*novel-forge\s*$", frontmatter, re.MULTILINE)
    assert re.search(r"^description:\s*\S", frontmatter, re.MULTILINE)


def test_skill_documents_v36_harness_and_serial_integrity():
    text = (_REPO_ROOT / ".agents/skills/novel-forge/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "v3.6" in text
    assert "degraded_exploration" in text
    assert "同章同正文 SHA-256" in text
    assert "0b. 章际交接" in text
    assert "previous_chapter_sha256" in text
    assert "tool_capabilities" in text
    assert "tool_failures" in text


def test_review_template_lists_every_canonical_role(tmp_path: Path):
    from app.novel_forge.planning_spec import REVIEW_ROLES

    result = init_book_project(tmp_path, "roles", "Roles", "现实悬疑")
    template = (
        Path(result["book_dir"]) / "reviews" / "review-template.md"
    ).read_text(encoding="utf-8")

    for role in REVIEW_ROLES:
        assert role in template


def test_evidence_templates_use_canonical_marker_and_kinds(tmp_path: Path):
    from app.novel_forge.planning_spec import EVIDENCE_KINDS

    result = init_book_project(tmp_path, "evidence", "Evidence", "现实悬疑")
    evaluation = Path(result["book_dir"]) / "evaluation"
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in evaluation.glob("*-template.md")
    )

    assert "<!-- novel-forge-evidence:v1 -->" in combined
    for kind in EVIDENCE_KINDS:
        assert f'"kind": "{kind}"' in combined


def test_generated_agents_enforce_human_narrative_policy_ids(tmp_path: Path):
    from app.novel_forge.planning_spec import HUMAN_NARRATIVE_POLICY_IDS

    result = init_book_project(tmp_path, "agents", "Agents", "现实悬疑")
    book_dir = Path(result["book_dir"])
    agent_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (book_dir / ".claude/agents").glob("*.md")
    )
    constitution = (book_dir / "CLAUDE.md").read_text(encoding="utf-8")
    skill = (_REPO_ROOT / ".agents/skills/novel-forge/SKILL.md").read_text(
        encoding="utf-8"
    )

    for policy_id in HUMAN_NARRATIVE_POLICY_IDS:
        assert policy_id in constitution
        assert policy_id in agent_text
        assert policy_id in skill

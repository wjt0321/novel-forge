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
    assert result["local_git"]["initialized"] is True
    assert result["local_git"]["commit_created"] is True
    assert result["local_git"]["remote_count"] == 0
    assert Path(result["local_git"]["git_dir"]) == (
        tmp_path / ".local-book-git" / "test-book.git"
    )
    assert (book_dir / ".git").is_file()
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
    assert (book_dir / "planning" / "chapter-sequences").is_dir()
    assert (book_dir / "planning" / "guardian-sessions").is_dir()
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
    assert (book_dir / "evaluation" / "harness-contract.json").exists()
    assert (book_dir / "evaluation" / "guardian-contract.json").exists()
    literary_rules = (
        book_dir / "evaluation" / "literary-micro-rules.md"
    ).read_text(encoding="utf-8")
    assert "literary-micro-rules/v4" in literary_rules
    assert "可以写：" in literary_rules
    assert "绝对禁止：" in literary_rules
    assert "用户硬锚漂移" in literary_rules
    assert "具体私人代价" in literary_rules
    assert "身体、物件和位置" in literary_rules
    assert "不对称" in literary_rules
    assert "完美证据链" in literary_rules
    assert "解释性修补" in literary_rules
    assert len(literary_rules) < 2200
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
    assert (book_dir / "evidence" / "runtime-audits").is_dir()
    assert (book_dir / "evidence" / "guardian-receipts").is_dir()
    assert (book_dir / "evidence" / "arc-audits").is_dir()
    assert (book_dir / "evidence" / "rule-decisions").is_dir()
    assert not (book_dir / ".claude" / "agents").exists()
    assert not (book_dir / ".claude" / "agents" / "causal-editor.md").exists()
    assert not (book_dir / ".claude" / "agents" / "line-editor.md").exists()
    assert not (book_dir / ".claude" / "agents" / "texture-editor.md").exists()
    assert not (book_dir / ".claude" / "agents" / "consistency-guard.md").exists()

    claude_md = (book_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Test Book" in claude_md
    assert "test-book" in claude_md
    assert "chapters/eXX/ch-XX/正文.md" in claude_md
    assert "工作流版本" in claude_md
    assert "v5.4" in claude_md
    assert "小说正文是唯一主产品" in claude_md
    assert "无需填写技术表单" in claude_md
    assert "result_file" in claude_md
    assert "draft/正文.md" in claude_md
    assert "ready" in claude_md
    assert "不得配置 remote" in claude_md
    assert "lean_native" in claude_md
    assert "--strict-audit" in claude_md
    assert "未知遥测保持 null" in claude_md
    assert "至少 5000 CJK" in claude_md
    assert "reader_desire" in claude_md
    assert "不得创建或注册宿主专用 Agent 类型" in claude_md
    assert "技术附属记录失败必须优先原地补记" in claude_md
    assert "不得复制其他书的正文" in claude_md
    assert "memory/canon" in claude_md
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
    assert "默认工作流: v5.4" in readme
    assert "guardian-contract.json" in readme
    assert ".local-guardian" in readme
    assert "隔离" in readme
    assert ".local-book-git" in readme
    assert "不得复制其他书的正文" in readme

    gitignore = (book_dir / ".gitignore").read_text(encoding="utf-8")
    assert ".novel-forge/" in gitignore
    assert ".local-book-git/" in (
        _REPO_ROOT / ".gitignore"
    ).read_text(encoding="utf-8")
    assert ".local-guardian/" in (
        _REPO_ROOT / ".gitignore"
    ).read_text(encoding="utf-8")

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
    assert '"prompt_template_id"' in generation_template
    assert '"prompt_sha256"' in generation_template
    assert generation_template.count("chapters/e01/ch-") == 2

    harness_contract = json.loads(
        (book_dir / "evaluation" / "harness-contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert harness_contract["schema"] == "novel-forge-harness-contract/v1"
    assert harness_contract["reasoning_policy"] == {
        "planning_and_causal_checks": "high",
        "prose_draft_default": "standard_or_medium",
        "review_default": "standard_or_medium",
        "max_reasoning": "named_exception_only",
        "numeric_style_targets_visible_to_writer": False,
    }
    assert harness_contract["role_model_selection"][
        "terminal_resolved_model_is_authoritative"
    ] is True
    assert harness_contract["local_git_policy"] == {
        "mode": "per_book_external_gitdir",
        "metadata_directory": ".local-book-git/<slug>.git",
        "remote_allowed": False,
        "automatic_checkpoints": [
            "generation_bound_draft",
            "chapter_ready",
        ],
        "checkpoint_interval": 5,
        "authority": "recovery_not_approval",
    }
    assert harness_contract["runtime_report_schema"]["const"] == (
        "novel-forge-runtime/v1"
    )
    assert harness_contract["chapter_sequence"]["maximum_chapter_count"] == 4
    assert harness_contract["guardian"]["contract_operation"] == (
        "guardian-contract"
    )
    assert harness_contract["guardian"]["formal_writer_workspace"] == (
        "isolated_writer_capsule"
    )
    assert harness_contract["guardian"]["runtime_operation"] == (
        "record-capsule-runtime"
    )
    assert harness_contract["guardian"]["authorization_operation"] == (
        "authorize-regeneration"
    )
    assert harness_contract["guardian"]["prompt_template_id"] == (
        "formal-writer/v1"
    )
    assert harness_contract["guardian"]["prompt_file"] == "instructions.md"
    assert harness_contract["guardian"]["prompt_max_characters"] == 1200
    assert harness_contract["guardian"]["acp_required"] is False

    guardian_contract = json.loads(
        (book_dir / "evaluation" / "guardian-contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert guardian_contract["schema"] == "novel-forge-guardian-contract/v1"
    assert guardian_contract["workspace"]["book_control_plane_visible"] is False
    assert guardian_contract["runtime"]["full_transcript_required"] is False
    assert guardian_contract["runtime"]["stored_in_external_guardian_sidecar"] is True
    assert guardian_contract["prompt"]["template_id"] == "formal-writer/v1"
    assert guardian_contract["prompt"]["compiled_file"] == "instructions.md"
    assert guardian_contract["prompt"]["max_characters"] == 1200
    assert guardian_contract["session"]["authorization_operation"] == (
        "authorize-regeneration"
    )

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
    assert "review_session_id" in review_template
    assert "simulated_blind" in review_template

    memory_template = (
        book_dir / "memory" / "memory-record-template.md"
    ).read_text(encoding="utf-8")
    assert '"salience": "medium"' in memory_template

    assert "本章未开始" in claude_md
    assert "创作任务禁止先探索仓库实现" in claude_md
    assert "无需填写技术表单" in claude_md
    assert "不得创建或注册宿主专用 Agent 类型" in claude_md
    assert "双审前正文仍留在 diff 区" in claude_md
    assert "第二版仍有 MUST" in claude_md
    assert "Generation 和两份 Review" in claude_md
    assert "next_chapter_pull" in (
        book_dir / "reviews" / "review-template.md"
    ).read_text(encoding="utf-8")
    assert len(claude_md) < 5000



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
    assert data["data"]["local_git"]["initialized"] is True
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


def test_root_claude_routes_automatic_writing_to_the_generic_skill():
    text = (_REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert ".agents/skills/novel-forge/SKILL.md" in text
    assert "自动生产唯一入口" in text
    assert "tools/novel-workflow.py" in text
    assert "新书先由确定性控制面通过 `init-novel-project` 初始化" in text
    assert "本章未开始" in text
    assert "只有用户明确要求探索稿" in text
    assert "不得自行创建正式章节、规划、证据、审稿记录或 ready Git 恢复点" in text
    assert "不得创建、修改、修复、包装、安装或配置 Harness" in text
    assert "不得向用户提供部署或配置 Harness 的选项" in text
    assert "没有命令 Backend 时 `start` 自动进入原生会话 Relay" in text
    assert "`next-action`" in text
    assert "`complete-role`" in text
    assert "`NOVEL_FORGE_HARNESS_COMMAND` 只启用可选 headless" in text
    assert "lean_native" in text
    assert "--strict-audit" in text
    assert "高权限只属于无模型推理的确定性控制面" in text
    assert "必须使用宿主官方 wait / join 等到角色终态" in text
    assert "创建成功、已接单、进度消息或文件暂时稳定都不算完成" in text
    assert "Python 状态机决定下一步" in text
    assert "技术表单" in text
    assert "创作角色只允许写当前书" in text
    assert "ACP 只用于事后取证" in text
    assert "不得创建或注册宿主专用 Agent 类型" in text


def test_skill_documents_v54_fiction_first_native_workflow():
    text = (_REPO_ROOT / ".agents/skills/novel-forge/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "唯一主产品" in text
    assert "lean_native" in text
    assert "--strict-audit" in text
    assert "本章未开始" in text
    assert "不要先探索" in text
    assert "next-action <slug>" in text
    assert "complete-role <slug>" in text
    assert "`NOVEL_FORGE_HARNESS_COMMAND` 只是可选 headless" in text
    assert "Python 创建项目骨架" in text
    assert "技术表单" in text
    assert "不得创建、注册、修改或安装宿主专用 Agent 类型" in text
    assert ".claude/agents" in text
    assert "ACP 只用于事后取证" in text
    assert "至少 5000 个 CJK" in text
    assert "Writer 已产生合规正文" in text
    assert "不重写正文" in text
    assert "未知遥测保持 null" in text
    assert "第二版仍有 MUST" in text
    assert "Generation 和两份 Review" in text
    assert "不配置 remote" in text
    assert "human_likeness" in text
    assert "reader_desire" in text
    assert "idle、available" in text
    assert "literary-micro-rules/v4" in text
    assert "用户硬锚" in text
    assert len(text) < 9000


def test_v38_scene_package_does_not_prefill_risk_waivers(tmp_path: Path):
    result = init_book_project(
        tmp_path,
        "lean-package",
        "Lean Package",
        "现实悬疑",
    )
    template = (
        Path(result["book_dir"]) / "planning/scene-package-template.md"
    ).read_text(encoding="utf-8")

    assert "- 关键对白意图（没有则写无需）：" in template
    assert "无需：本章没有依赖专业判断推动关键行动" not in template


def test_review_template_lists_every_canonical_role(tmp_path: Path):
    from app.novel_forge.planning_spec import REVIEW_ROLES

    result = init_book_project(tmp_path, "roles", "Roles", "现实悬疑")
    template = (
        Path(result["book_dir"]) / "reviews" / "review-template.md"
    ).read_text(encoding="utf-8")

    for role in REVIEW_ROLES:
        assert role in template
    for field in (
        "reconstruction_space",
        "reconstruction_body",
        "reconstruction_constraints",
        "reconstruction_emotion",
        "reconstruction_dialogue",
        "memorable_image_1",
        "memorable_image_2",
        "memorable_image_3",
        "editorial_causality",
        "editorial_agency",
        "editorial_dialogue",
        "editorial_texture",
        "editorial_continuity",
    ):
        assert field in template


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


def test_generated_constitution_enforces_human_narrative_policy_ids(
    tmp_path: Path,
):
    from app.novel_forge.planning_spec import HUMAN_NARRATIVE_POLICY_IDS

    result = init_book_project(tmp_path, "agents", "Agents", "现实悬疑")
    book_dir = Path(result["book_dir"])
    constitution = (book_dir / "CLAUDE.md").read_text(encoding="utf-8")
    skill = (_REPO_ROOT / ".agents/skills/novel-forge/SKILL.md").read_text(
        encoding="utf-8"
    )

    for policy_id in HUMAN_NARRATIVE_POLICY_IDS:
        assert policy_id in constitution
        assert policy_id in skill

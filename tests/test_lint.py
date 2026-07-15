from pathlib import Path

from app.novel_forge.lint import lint_text


def test_lint_detects_em_dash_and_ellipsis():
    text = "他喊道——停下。然后……"
    findings = lint_text(text)
    codes = {f.rule_code for f in findings}
    assert "em-dash" in codes
    assert "ellipsis" in codes
    assert any(f.severity == "blocking" for f in findings)


def test_lint_detects_not_is_flip():
    text = "他不是害怕，是愤怒。"
    findings = lint_text(text)
    assert any(f.rule_code == "not-is-flip" for f in findings)


def test_lint_detects_explanation_tic():
    text = "他终于明白，这才是最好的选择。"
    findings = lint_text(text)
    assert any(f.rule_code == "explanation-tic" for f in findings)


def test_lint_detects_word_count_tic():
    text = "这五个字一落，全场安静。"
    findings = lint_text(text)
    assert any(f.rule_code == "word-count-tic" for f in findings)


def test_lint_detects_colon_density():
    text = "他说：\"你好。\"她说：\"再见。\""
    findings = lint_text(text)
    density = next(f for f in findings if f.rule_code == "colon-density")
    assert density.colon_count == 2


def test_lint_detects_question_mark_mismatch():
    text = "妈妈你明天回来吗。那猫呢。"
    findings = lint_text(text)
    assert any(f.rule_code == "question-mark-mismatch" for f in findings)


def test_lint_allows_real_questions():
    text = "妈妈你明天回来吗？那猫呢？"
    findings = lint_text(text)
    assert not any(f.rule_code == "question-mark-mismatch" for f in findings)


def test_lint_detects_common_errors():
    text = "1993年入防闭坑记录。注浆机在打桩。\n邻居发的微信语音。\n、和手机摄像。\n摘要列表在屏幕上平铺开。"
    findings = lint_text(text)
    codes = {f.rule_code for f in findings}
    assert "common-error" in codes


def test_lint_detects_rhythm_monotony():
    text = "\n\n".join(["清晨六点半。", "暴雨橙色预警还在挂。", "她到办公室。", "走廊灯灭了一半。", "她走过去。", "她把门关上。"])
    findings = lint_text(text)
    assert any(f.rule_code == "rhythm-monotony" for f in findings)


def test_lint_detects_mechanical_triplet():
    text = "没有施工记录。没有注浆量数据。没有复检报告。"
    findings = lint_text(text)
    assert any(f.rule_code == "mechanical-triplet" for f in findings)


def test_lint_detects_explanatory_punchline():
    text = (
        "老方在监控室盯着屏幕看了二十分钟。"
        "画面里只有空无一人的走廊和偶尔闪过的红光。"
        "然后波形抖了一下。\n\n空洞。\n\n她收回视线。"
    )
    findings = lint_text(text)
    assert any(f.rule_code == "explanatory-punchline" for f in findings)


def test_lint_detects_quote_inconsistency():
    text = "\"什么情况。老方说。"
    findings = lint_text(text)
    assert any(f.rule_code == "quote-consistency" for f in findings)


def test_lint_allows_consistent_quotes():
    text = "\"什么情况。\"老方说。"
    findings = lint_text(text)
    assert not any(f.rule_code == "quote-consistency" for f in findings)

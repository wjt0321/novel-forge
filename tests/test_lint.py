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


def test_lint_explanatory_punchline_isolated_short_paragraph():
    # A single-sentence paragraph containing a short, conclusion-like phrase.
    text = (
        "老方在监控室盯着屏幕看了二十分钟。"
        "画面里只有空无一人的走廊和偶尔闪过的红光。"
        "然后波形抖了一下。\n\n空洞。\n\n她收回视线。"
    )
    findings = lint_text(text)
    punchlines = [f for f in findings if f.rule_code == "explanatory-punchline"]
    assert len(punchlines) == 1
    assert "空洞" in punchlines[0].evidence


def test_lint_explanatory_punchline_at_end_of_two_sentence_paragraph():
    # Two-sentence paragraph ending in a short conclusion after a long sentence.
    text = (
        "老方在监控室盯着屏幕看了整整二十分钟，画面里只有空无一人的走廊和偶尔闪过的红光，"
        "仪器发出的嗡嗡声在寂静中显得格外清晰。"
        "空洞。"
    )
    findings = lint_text(text)
    punchlines = [f for f in findings if f.rule_code == "explanatory-punchline"]
    assert len(punchlines) == 1
    assert "空洞" in punchlines[0].evidence


def test_lint_explanatory_punchline_ignores_long_paragraph_ending():
    # A short final sentence inside a long narrative paragraph is not a punchline.
    text = (
        "老方在监控室盯着屏幕，一动不动地看了整整二十分钟。"
        "画面里只有空无一人的走廊和偶尔闪过的红光。"
        "然后波形抖了一下。空洞。"
    )
    findings = lint_text(text)
    punchlines = [f for f in findings if f.rule_code == "explanatory-punchline"]
    assert len(punchlines) == 0


def test_lint_explanatory_punchline_ignores_fragments():
    # Enough CJK text to pass the minimum-length gate; the short phrases are
    # fragments inside longer sentences, not standalone sentences.
    text = (
        "今天是周六，她去上班。秀兰，她坐起来。"
        "她坐起来，伸了个懒腰，窗外阳光很好，街道上人来人往，一切看起来都很平常。"
    )
    findings = lint_text(text)
    assert not any(f.rule_code == "explanatory-punchline" for f in findings)


def test_lint_question_mark_mismatch_ignores_word_internal_me():
    text = "你在说什么。这是怎么回事。多么美好。要么放弃。"
    findings = lint_text(text)
    assert not any(f.rule_code == "question-mark-mismatch" for f in findings)


def test_lint_question_mark_mismatch_detects_real_final_me():
    text = "这是真的么。我们走吧。"
    findings = lint_text(text)
    codes = {f.rule_code for f in findings}
    assert "question-mark-mismatch" in codes


def test_lint_word_count_tic_allows_genuine_counts():
    text = "这五个字一落，全场安静。他写满了一百个字。"
    findings = lint_text(text)
    tics = [f for f in findings if f.rule_code == "word-count-tic"]
    assert len(tics) == 2


def test_lint_word_count_tic_ignores_false_positives():
    text = "这是第一行字。也是一行字。字体设计得很漂亮。"
    findings = lint_text(text)
    assert not any(f.rule_code == "word-count-tic" for f in findings)


def test_lint_detects_noun_phrase_triplet():
    text = "井水。老鼠。地龙翻身。"
    findings = lint_text(text)
    assert any(f.rule_code == "mechanical-triplet" for f in findings)


def test_lint_allows_appositive_after_full_sentence():
    text = "她喜欢花。玫瑰。百合。茉莉。"
    findings = lint_text(text)
    assert not any(f.rule_code == "mechanical-triplet" for f in findings)


def test_lint_allows_same_prefix_after_full_sentence():
    text = "检查结果不理想。没有施工记录。没有注浆量数据。没有复检报告。"
    findings = lint_text(text)
    assert not any(f.rule_code == "mechanical-triplet" for f in findings)


def test_lint_allows_verb_phrase_triplet():
    # Quoted verb phrases should not be mistaken for noun-phrase lists.
    text = '"房子会摇。摇得很厉害。所以今晚不能睡屋里。"'
    findings = lint_text(text)
    assert not any(f.rule_code == "mechanical-triplet" for f in findings)


def test_lint_detects_quote_duplication_in_prose():
    # Patch/escape artifact: ""妈，...？""
    text = '然后抬头拉林知远的手。""妈，井水是不是生气了？""'
    findings = lint_text(text)
    assert any(f.rule_code == "quote-duplication" for f in findings)


def test_lint_allows_single_quoted_dialogue():
    text = '然后抬头拉林知远的手。"妈，井水是不是生气了？"'
    findings = lint_text(text)
    assert not any(f.rule_code == "quote-duplication" for f in findings)


def test_lint_quote_duplication_ignores_code_blocks():
    text = '```json\n{"key": ""value""}\n```\n\n正文。'
    findings = lint_text(text)
    assert not any(f.rule_code == "quote-duplication" for f in findings)


def test_lint_quote_duplication_ignores_json_structural():
    # Empty JSON string value: "" is adjacent to : or ,
    text = '{"a":"","b":"x"}\n\n正文段落。'
    findings = lint_text(text)
    assert not any(f.rule_code == "quote-duplication" for f in findings)

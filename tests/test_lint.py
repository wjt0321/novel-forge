from pathlib import Path

import pytest

from app.novel_forge.lint import lint_text


def test_lint_detects_em_dash_and_ellipsis():
    text = "他喊道——停下。然后……"
    findings = lint_text(text)
    codes = {f.rule_code for f in findings}
    assert "em-dash" in codes
    assert "ellipsis" in codes
    assert any(f.severity == "blocking" for f in findings)


def test_lint_blocks_markdown_emphasis_in_prose():
    text = "他母亲走回去的时候没有说话。她走得比他**慢**。"

    findings = lint_text(text)

    match = next(f for f in findings if f.rule_code == "markdown-emphasis")
    assert match.severity == "blocking"
    assert match.line_number == 1
    assert "**慢**" in match.evidence


def test_lint_detects_not_is_flip():
    text = "他不是害怕，是愤怒。"
    findings = lint_text(text)
    assert any(f.rule_code == "not-is-flip" for f in findings)


def test_lint_detects_explanation_tic():
    text = "他终于明白，这才是最好的选择。"
    findings = lint_text(text)
    assert any(f.rule_code == "explanation-tic" for f in findings)


@pytest.mark.parametrize("text", ["他突然意识到门没锁。", "她意识到自己来晚了。"])
def test_lint_detects_consciousness_explanation_leads(text: str):
    findings = lint_text(text)

    match = next(f for f in findings if f.rule_code == "explanation-tic")
    assert match.severity == "advisory"


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


def test_lint_rhythm_monotony_skips_varied_short_paragraphs():
    # 剑来式连排短段：段落都短，但句长落差极大（高 CV），是人声不是打点。
    text = "\n\n".join([
        "二月二，龙抬头。",
        "暮色里，小镇名叫泥瓶巷的僻静地方，有位孤苦伶仃的清瘦少年，此时他正按照习俗，一手持蜡烛，一手持桃枝。",
        "星空璀璨。",
        "少年至今仍然清晰记得，那个只肯认自己做半个徒弟的老师傅，姓姚，在去年暮秋时分的清晨，被人发现坐在一张小竹椅子上，正对着窑头方向，闭眼了。",
        "如鼠见猫。",
        "陈平安很早就让出道路，八个人大致分作五批，走向小镇深处。",
    ])
    findings = lint_text(text)
    assert not any(f.rule_code == "rhythm-monotony" for f in findings)


def test_lint_rhythm_monotony_skips_dialogue_runs():
    # 对白连排： spoken lines are legitimately short and even; not a rhythm defect.
    text = "\n\n".join([
        '"吃了吗？"妈问。',
        '"吃了。"',
        '"票买了没有？"',
        '"买了。"',
        '"什么时候的？"',
        '"后天。"',
    ])
    findings = lint_text(text)
    assert not any(f.rule_code == "rhythm-monotony" for f in findings)


def test_lint_rhythm_monotony_skips_uniform_medium_runs():
    # 匀而不短：中等长度（均值≥25）的均匀短段是普通讲者陈述，不是打点。
    text = "\n\n".join([
        "他说完，笑了笑，端着那只搪瓷缸子慢悠悠回去了，百货大楼的侧门哐当一声关上。",
        "陈驰站了一会儿，蹲下来，把马胜利目光停过的那块绒布角抚平，摆齐上面的镊子。",
        "下午两点，日头偏过电线杆，摊位前来了一个穿灰中山装的老头。",
        "老头在摊前站定，先没说话，把绒布上的工具看了一遍，又抬眼看了看立着的樟木箱。",
        "表用手绢包着，一层，又一层，手绢是白的，洗得发黄，四个角对齐，包得方方正正。",
    ])
    findings = lint_text(text)
    assert not any(f.rule_code == "rhythm-monotony" for f in findings)


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


def _pad_cjk(text: str, repeats: int = 60) -> str:
    return text + "\n\n" + "他沿着街慢慢走，天色一点点暗下来，路灯次第亮起。" * repeats


def test_lint_sentence_rhythm_flags_uniform_paragraph():
    text = (
        "他走到窗前。他拉开窗帘。他看着楼下。他转身离开。他关上房门。"
        "他坐到桌边。他拿起杯子。他喝了一口水。"
    )
    findings = lint_text(text)
    assert any(f.rule_code == "sentence-rhythm" for f in findings)


def test_lint_sentence_rhythm_allows_varied_paragraph():
    text = (
        "他走到窗前，拉开窗帘，看着楼下那场已经下了整夜却没有停意思的雨。"
        "雨不大。他想起母亲昨天傍晚在电话里说的那些话，想起她说那些话时背景里电视的声音。"
        "他转身离开。"
    )
    findings = lint_text(text)
    assert not any(f.rule_code == "sentence-rhythm" for f in findings)


def test_lint_sentence_rhythm_skips_dialogue_heavy_paragraph():
    text = '"走。""不走。""为什么。""没有为什么。""你走吧。""我不走。"'
    findings = lint_text(text)
    assert not any(f.rule_code == "sentence-rhythm" for f in findings)


def test_lint_term_density_flags_coined_terms():
    text = _pad_cjk(
        "道脉震动。道脉崩裂。道脉逆流。道脉沉寂。道脉复苏。"
        "残剑嗡鸣。残剑出鞘。残剑归鞘。残剑碎裂。残剑低吟。"
        "九斩破空。九斩裂地。九斩断流。九斩归一。九斩无声。"
    )
    findings = lint_text(text)
    assert any(f.rule_code == "term-density" for f in findings)


def test_lint_term_density_ignores_common_words():
    # 核(核实/核对), 法(办法), 压(压力), 脉冲 are legitimate vocabulary.
    text = _pad_cjk(
        "银行要核实来源，他没有办法，压力很大。"
        "银行再次核实，他还是没有办，压力更大。"
        "第三次核实来了，他仍然毫无办法。"
        "脉冲信号出现了五次，低频脉冲五次。"
    )
    findings = lint_text(text)
    assert not any(f.rule_code == "term-density" for f in findings)


def test_lint_term_density_skips_short_text():
    text = "道脉震动。道脉崩裂。道脉逆流。道脉沉寂。道脉复苏。"
    findings = lint_text(text)
    assert not any(f.rule_code == "term-density" for f in findings)


def test_lint_simile_density_flags_heavy_use():
    # ~6 similes in ~500 CJK → well above 3/1000.
    similes = "他的声音像钝刀。夜色仿佛凝固。风好似刀子。灯光宛如流水。气氛犹如冰点。她笑得像朵花。"
    text = _pad_cjk(similes, repeats=45)
    findings = lint_text(text)
    assert any(f.rule_code == "simile-density" for f in findings)


def test_lint_simile_density_allows_restrained_use():
    text = _pad_cjk("他笑得像朵花。", repeats=45)
    findings = lint_text(text)
    assert not any(f.rule_code == "simile-density" for f in findings)


def test_lint_simile_density_ignores_non_simile_words():
    # 想象/画像/录像/像素 are not similes and must not inflate the count.
    text = _pad_cjk("他看着画像，想象着录像里的像素。", repeats=45)
    findings = lint_text(text)
    assert not any(f.rule_code == "simile-density" for f in findings)


def test_not_is_flip_still_blocks_declarative_punchline():
    findings = lint_text("他不是离开，是重生。")
    assert any(f.rule_code == "not-is-flip" for f in findings)


def test_not_is_flip_exempts_questions_and_irony():
    # 剑来 ch01 同款：反讽疑问句是机锋，不是 AI 腔。
    findings = lint_text("当时陈平安就纳闷，难道打铁这门活计，不是看臂力大小，而是看面相好坏？")
    assert not any(f.rule_code == "not-is-flip" for f in findings)


def test_not_is_flip_exempts_dialogue():
    findings = lint_text('"你不是输了，是从来没上过牌桌。"她说。')
    assert not any(f.rule_code == "not-is-flip" for f in findings)


def test_not_is_flip_blocks_narration_flip():
    findings = lint_text("屏幕亮起来的第一件事不是通讯录，是邮箱。")
    assert any(f.rule_code == "not-is-flip" for f in findings)


@pytest.mark.parametrize(
    "text",
    [
        "她翻到 ch04 老魏认出的第三页。",
        "她翻到ch04老魏认出的第三页。",
        "屏幕上写着 SHA-256 校验失败。",
        "他在正文.md里留下了 generation evidence。",
        "这一章已经 surface_checked，可以进入 ready。",
        "这一章已经ready，可以交付。",
    ],
)
def test_lint_blocks_workflow_metadata_leaking_into_prose(text):
    findings = lint_text(text)

    assert any(
        finding.rule_code == "workflow-meta-leak"
        and finding.severity == "blocking"
        for finding in findings
    )


def test_lint_does_not_flag_ordinary_review_language_as_workflow_leak():
    findings = lint_text("她把合同交给审核员，等对方盖章。")

    assert not any(
        finding.rule_code == "workflow-meta-leak" for finding in findings
    )


def test_lint_does_not_flag_generation_as_an_ordinary_story_word():
    findings = lint_text(
        '屏幕上印着“Next Generation”，那是旧飞船的宣传语。'
    )

    assert not any(
        finding.rule_code == "workflow-meta-leak" for finding in findings
    )

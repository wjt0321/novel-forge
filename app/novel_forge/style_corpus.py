"""Style corpus: positive technique genes and AI-tell anti-patterns.

Single source for the two reference frames injected into each book's
voice bible:

- ``POSITIVE_STYLE_GENES`` distils technique-level patterns from well-known
  published fiction (Hemingway's iceberg omission, Shen Congwen's
  character-attached narration, Wang Zengqi's short-breath prose and idle
  strokes, Jin Yong's dialogue modes). Entries describe *narrative
  functions and measurable signals* only — no copyrighted excerpts are
  reproduced, and the voice bible explicitly forbids copying exemplar
  wording.
- ``AI_TELL_PATTERNS`` catalogues recurring machine-flavor patterns
  reported across writing-craft and LLM-detection literature (uniform
  sentence length, connective tics, emotion labeling, rule-of-three
  padding, bookish dialogue, synonym carousels, summary endings, ...).
  Density is the tell, not single occurrences.

The corpus is advisory input for authors and reviewers; it never decides
a verdict by itself (same contract as lint advisories).
"""

from __future__ import annotations

STYLE_CORPUS_VERSION = "style-corpus/v1"

# --- Positive technique genes -------------------------------------------------
# Each gene: id / source / principle / practice tuple / signal. Sources are
# named for attribution of the TECHNIQUE as publicly analysed; entries contain
# only original paraphrase.

POSITIVE_STYLE_GENES: tuple[dict[str, str | tuple[str, ...]], ...] = (
    {
        "id": "iceberg-omission",
        "source": "海明威 · 冰山省略",
        "principle": "写八分之一，剩下的交给读者经验：删掉一切可有可无，情绪不直写，凝结在动作与对白里。",
        "practice": (
            "删掉解释情绪的句子，只留可见可听的动作与物件",
            "对白不带情绪副词，让语调变化由读者补全",
            "重要转折前后留白，不替读者总结意义",
        ),
        "signal": "情绪命名词密度低；对白占比高；解释性导语接近零",
    },
    {
        "id": "telegraph-rhythm",
        "source": "海明威 · 电报节奏",
        "principle": "名词和动词直抵事物；形容词副词是敌人。短句为主，偶尔一个长句制造起伏。",
        "practice": (
            "初稿后做形容词审计：每个形容词证明自己值得留下",
            "长短句交错成呼吸，避免连续等长句",
            "用具体名词替换华丽抽象词",
        ),
        "signal": "句长方差大而有序；形容词/副词密度低",
    },
    {
        "id": "attach-to-character",
        "source": "沈从文 · 贴着人物写",
        "principle": "人物是主导，其余都是派生：环境、抒情、议论只能附着于人物，不能游离。叙述语言随人物身份换挡。",
        "practice": (
            "每段自问：这段话是这个人注意到的吗",
            "写什么人就用什么人的语言层次，避免学生腔",
            "作者的心贴住人物，贴不住就会浮、泛、飘、滑",
        ),
        "signal": "视角泄漏少；叙述语域随场景人物变化",
    },
    {
        "id": "plain-dialogue",
        "source": "沈从文 · 对白朴素律",
        "principle": "对话就是人物说的普普通通的话：不要哲理，不要诗意。两个聪明脑壳打架不是对话。",
        "practice": (
            "对白只说自己最关心的事，绝不多说一句",
            "允许半句话、被打断、答非所问",
            "把对白里的妙语删到只剩人物真会说的那句",
        ),
        "signal": "对白内无书面连接词；各角色语言指纹可区分",
    },
    {
        "id": "short-breath",
        "source": "汪曾祺 · 短句切开",
        "principle": "能切开就切开；长句短句怎么搭配是语言的奥妙。散句为主，偶尔一组四字句点睛。",
        "practice": (
            "超短句做节拍（他懂了。来不及了。）",
            "长句留给需要铺开的感知段落",
            "文言韵律只在收束处偶一为之",
        ),
        "signal": "存在 2-5 字超短句；段落长短参差",
    },
    {
        "id": "idle-stroke",
        "source": "汪曾祺 · 闲笔",
        "principle": "不推进剧情的描写让世界活着：一碗面、一眼月亮、配角一句无关的话。全是目的的文字没有呼吸。",
        "practice": (
            "每章留一两处纯感官闲笔（气味、触感、声音）",
            "闲笔选本世界真实有的东西，不服务隐喻",
            "闲笔放在节奏需要喘息处，不按配额插入",
        ),
        "signal": "非情节感官细节存在；信息密度有松有紧",
    },
    {
        "id": "plain-sketch",
        "source": "汪曾祺 · 白描忌成语",
        "principle": "少用形容词，不用成语写景——隔了一层，不够贴。叠词拟声让文字口语化、有表现力。",
        "practice": (
            "写景用眼前具体的词，不用现成四字套语",
            "以动作和物象代替评价性形容",
            "拟声词、叠词用在贴身处而非抒情处",
        ),
        "signal": "成语密度低；具体感官名词占比高",
    },
    {
        "id": "dialogue-modes",
        "source": "金庸 · 对白三式",
        "principle": "单人连说、双人问答、动作响应三种方式交替，不由叙述者转述全部话语。",
        "practice": (
            "群戏里用动作响应拍带出谁在说话",
            "关键交锋用双人问答逐拍推进",
            "避免连续多轮归属标签堆叠",
        ),
        "signal": "对白呈现形式多样；归属清晰但不机械",
    },
)

# --- AI-tell anti-patterns ----------------------------------------------------
# Each tell: id / category / pattern / fix. Compiled from public writing-craft
# discussions of machine-flavored prose and LLM-detection guides; they are
# editing heuristics, not authorship proof.

AI_TELL_PATTERNS: tuple[dict[str, str], ...] = (
    {
        "id": "uniform-sentence-length",
        "category": "句法",
        "pattern": "句长惊人均匀（20/22/19/21 字连排），缺少长短交错的呼吸——这是最强的统计特征。",
        "fix": "拆最长句为三四个短句，或合并短句成一个有节奏的长句；穿插两三字超短句。",
    },
    {
        "id": "connective-tic",
        "category": "句法",
        "pattern": "叙事行高频使用书面连接词：此外、与此同时、不仅如此、值得注意的是、总的来说。",
        "fix": "句子逻辑靠上下文暗示，删掉路标词；保留的连接词一次不超过一处。",
    },
    {
        "id": "emotion-label",
        "category": "情绪",
        "pattern": "情绪直接贴标签：一阵深深的悲伤涌上心头、愤怒攫住了他。标准情感词 + 涌/袭/攫动词。",
        "fix": "改写为身体变化 + 决定 + 行动延迟：手在做什么，选择了不说哪句话。",
    },
    {
        "id": "rule-of-three",
        "category": "结构",
        "pattern": "三段式排比成瘾：是X，是Y，更是Z；每段三个要点。工整是公文特征不是叙事特征。",
        "fix": "改为两项或四项不等长列举；或拆散进动作与对白。",
    },
    {
        "id": "bookish-dialogue",
        "category": "对白",
        "pattern": "所有角色说话字正腔圆、语法完美，像播音员；没有人说半句话、语气词或错配表达。",
        "fix": "加口语词与语气词；让角色说半句被打断；粗人说粗话，书生咬文嚼字。",
    },
    {
        "id": "textbook-paragraph",
        "category": "结构",
        "pattern": "每段总分总：先总论、再展开、末句总结。教科书写法，小说不需要讲道理。",
        "fix": "从画面切入，跳回忆再切回现实，中间不做过渡说明，读者自己补逻辑。",
    },
    {
        "id": "synonym-carousel",
        "category": "词汇",
        "pattern": "同指轮换避重复：主人公/主要角色/中心人物/英雄轮流指同一人，像同义词检测器在跑。",
        "fix": "中文叙事靠语境消歧，同一人就用名字或省略主语，不必花式换称。",
    },
    {
        "id": "false-range",
        "category": "修辞",
        "pattern": "虚假范围：从X到Y——但 X 与 Y 不在真实刻度上（从绝望到希望、从平凡到伟大）。",
        "fix": "删掉范围壳，直接写两端中真正要的那一件事。",
    },
    {
        "id": "generic-uplift",
        "category": "收束",
        "pattern": "通用升华收尾：这或许就是成长的代价、夜色中他想了很多、未来还很长。模糊乐观或感慨总结。",
        "fix": "章末落在一个具体画面、动作或未接完的对白上，意义让读者带走。",
    },
    {
        "id": "metaphor-stack",
        "category": "修辞",
        "pattern": "隐喻堆叠与通用隐喻：像一幅徐徐展开的画卷、命运的交响乐类高频比喻一句接一句。",
        "fix": "一段最多一个比喻；优先找准确的动词与名词，删掉装饰性比喻。",
    },
    {
        "id": "hedge-stack",
        "category": "句法",
        "pattern": "过度限定连用：似乎、仿佛、某种意义上、在某种程度上挤在同一句里。",
        "fix": "一句话只保留一个限定词，或者干脆把判断交给动作结果。",
    },
    {
        "id": "copula-avoidance",
        "category": "词汇",
        "pattern": "系动词回避：充当着/扮演着……的角色、作为……存在着，替代简单的是/有。",
        "fix": "换回是、有、在；简单系动词反而干净。",
    },
    {
        "id": "no-aftermath",
        "category": "结构",
        "pattern": "零闲笔零余波：每一句都推进剧情或传达信息，事件之后没有消化事件的时间。",
        "fix": "大事之后给一两拍身体余波或无关对话，让读者喘息。",
    },
    {
        "id": "action-beat-clockwork",
        "category": "对白",
        "pattern": "对白后机械插动作拍：每句话必跟一个动作，像节拍器在对白里走针。",
        "fix": "动作拍只为归属不清或权力变化服务，其余整段留纯对白。",
    },
)


def render_positive_genes_brief(max_chars: int = 1500) -> str:
    """Render the positive gene library as one bounded brief."""
    lines: list[str] = []
    for gene in POSITIVE_STYLE_GENES:
        practices = "；".join(gene["practice"])  # type: ignore[arg-type]
        line = (
            f"- {gene['source']}｜{gene['principle']}"
            f"做法：{practices}。信号：{gene['signal']}。"
        )
        lines.append(line)
    text = "\n".join(lines)
    if len(text) <= max_chars:
        return text
    kept: list[str] = []
    total = 0
    for line in lines:
        if total + len(line) > max_chars and kept:
            break
        kept.append(line)
        total += len(line)
    return "\n".join(kept)


def render_ai_tells_brief(max_chars: int = 1200) -> str:
    """Render the AI-tell catalog as one bounded checklist."""
    lines: list[str] = []
    for tell in AI_TELL_PATTERNS:
        lines.append(
            f"- [{tell['category']}] {tell['pattern']}→ {tell['fix']}"
        )
    text = "\n".join(lines)
    if len(text) <= max_chars:
        return text
    kept: list[str] = []
    total = 0
    for line in lines:
        if total + len(line) > max_chars and kept:
            break
        kept.append(line)
        total += len(line)
    return "\n".join(kept)

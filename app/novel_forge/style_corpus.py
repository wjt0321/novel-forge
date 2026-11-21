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

from typing import Sequence

STYLE_CORPUS_VERSION = "style-corpus/v3"

# --- Default reference subsets ------------------------------------------------
# The full library lives in the author-facing ``memory/style-reference.md``.
# Only these few entries reach a Writer capsule, so a draft always has a stated
# target even when the author has adopted nothing yet. Keep both lists short.

CORE_POSITIVE_GENE_IDS: tuple[str, ...] = (
    "iceberg-omission",
    "attach-to-character",
    "plain-dialogue",
    "object-carries-feeling",
)
CORE_AI_TELL_IDS: tuple[str, ...] = (
    "not-only-flip",
    "emotion-label",
    "pov-drift",
    "summary-closing-paragraph",
    "generic-uplift",
)


def _truncate_lines(lines: list[str], max_chars: int | None) -> str:
    """Join lines, optionally keeping the longest prefix that fits the budget."""
    text = "\n".join(lines)
    if max_chars is None or len(text) <= max_chars:
        return text
    kept: list[str] = []
    total = 0
    for line in lines:
        if total + len(line) > max_chars and kept:
            break
        kept.append(line)
        total += len(line)
    return "\n".join(kept)

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
    {
        "id": "spectator-gap",
        "source": "鲁迅 · 看客留白",
        "principle": "不写内心说明，用旁人的眼光、安静和半截话折射当事人的处境；讽刺由叙述者退让产生。",
        "practice": (
            "把心理陈述换成周围人的动作与注视",
            "让最重的话停在嘴边不说出",
            "叙述者只记录，不替人物认罪或喊冤",
        ),
        "signal": "心理形容少；旁观动作与沉默占比高",
    },
    {
        "id": "voice-is-character",
        "source": "老舍 · 声口即人",
        "principle": "人物身份由语言本身承担：用词层次、句法长短、行话与口语节奏区分人，叙述语言也向人物靠拢。",
        "practice": (
            "同一件事让两个角色各说一遍，措辞不可互换",
            "行话只用在对的人嘴里",
            "删掉书面腔，改成人物真会说的说法",
        ),
        "signal": "各角色用词层次可辨；叙述语域随人物换挡",
    },
    {
        "id": "object-carries-feeling",
        "source": "张爱玲 · 物件代情",
        "principle": "情绪不命名，交给可看见的器物、衣料、光线与空间；物质细节同时承担阶层与处境信息。",
        "practice": (
            "把心情句改写为一个被人物注意到的物件状态",
            "让物件在关键节点再次出现形成回环",
            "物件描写顺带交代地位、年代与规矩",
        ),
        "signal": "情绪命名词低；具体器物密度高且会复现",
    },
    {
        "id": "zero-degree-tone",
        "source": "余华 · 零度叙述",
        "principle": "惨烈的事用平静语序平铺说完，不加评论也不求救赎；有意的重复句式制造节拍与钝痛。",
        "practice": (
            "删掉一切评价性副词与感叹",
            "同一结构连续复现，只换掉一个变量",
            "越重的消息越短的句式",
        ),
        "signal": "评价词接近零；出现有意图的结构重复",
    },
    {
        "id": "mundane-world",
        "source": "阿城 · 闲话养正文",
        "principle": "世故、手艺与器物细节先把世界立住，主题不在句面上说；越是要紧的道理越藏在日常交代里。",
        "practice": (
            "写一门手艺就写到工具与动作可查",
            "道理借配角一句闲话说完即止",
            "严禁总结段点题",
        ),
        "signal": "行话与器物细节具体；无点题段",
    },
    {
        "id": "one-metaphor-only",
        "source": "钱钟书 · 一喻到位",
        "principle": "一段只给一个比喻，且喻体来自该人物可及的知识范围；宁可没有比喻，不要第二个。",
        "practice": (
            "数一段里的比喻数，超过一个就删",
            "喻体按人物职业与阅历取材",
            "优先换回准确的动词",
        ),
        "signal": "比喻密度低且与人物身份一致",
    },
    {
        "id": "hard-cut",
        "source": "卡佛 · 跳跃不解释",
        "principle": "省略过渡与交代，场景之间硬切；读者自己搭桥，被省掉的部分往往最狠。",
        "practice": (
            "删掉到达、离开、时间衔接等枢纽句",
            "在情绪最高点切走，不写后果说明",
            "对白直接换场，不写谁先开口",
        ),
        "signal": "过渡性连接句少；场景起于半途",
    },
    {
        "id": "table-worldbuilding",
        "source": "马丁 · 餐桌式世界观",
        "principle": "制度、物价、等级与历史通过吃什么、怎么称呼、谁先动筷交代，绝不开设定讲座。",
        "practice": (
            "设定信息寄生在动作、称谓与账目上",
            "限知视角一章，叙述只知此人所知",
            "群戏用一件共同事务把话逼出来",
        ),
        "signal": "无解说段；设定来自日常细节",
    },
    {
        "id": "fair-play-clue",
        "source": "阿加莎 · 公平线索",
        "principle": "关键线索必须提前以平凡面目出现，回收时读者能自行往前对上；隐瞒即作弊。",
        "practice": (
            "每个反转回到前文指出它的物质来源",
            "把要用的线索藏在闲谈或差事里",
            "新人物带来新解释，不带来新事实",
        ),
        "signal": "回收点均有前置出处；无天降信息",
    },
    {
        "id": "detached-suspense",
        "source": "东野圭吾 · 情感后置",
        "principle": "办案与取证段落保持克制，把情感冲击留到最后一步引爆；动机由行动链自证。",
        "practice": (
            "程序段落不掺抒情",
            "把最私人的一句话压到真相之后",
            "动机不辩解，让人物按自己的逻辑做完",
        ),
        "signal": "前段冷、末点热；无动机自白",
    },
    {
        "id": "rule-cost-ledger",
        "source": "规则怪谈与《诡秘之主》类 · 条款代价账",
        "principle": "超自然规则写成可核对的条款，字面判定严格；每次违规都留下量化后果，恐惧来自代价而不来自形容词。",
        "practice": (
            "规则条目编号化，判定只按字面",
            "违约后果落到工钱、名额、时间或身体",
            "严禁叙述者解释规则来历",
        ),
        "signal": "条款与后果一一对应；无设定解说",
    },
    {
        "id": "serialized-grind",
        "source": "网文长篇 · 日常 grind 蓄势",
        "principle": "以重复劳作、账目与规矩把世界压实，长线伏笔靠琐碎细节兑现；爽点之前必须有可见的成本。",
        "practice": (
            "给主角一套可复演的日常程序",
            "兑现时回收前文某件具体的小事",
            "力量或信息增益都标价格与副作用",
        ),
        "signal": "重复程序可核对；增益有代价",
    },
    {
        "id": "life-goes-on",
        "source": "契诃夫 · 生活还在继续",
        "principle": "故事在事情没说完时停下，后文是吃饭、赶路、别人的闲事，不给教训。",
        "practice": (
            "删掉结尾的明白了",
            "最后一段写一件与主题无关的日常",
            "人物可以没想通",
        ),
        "signal": "收束无总结句；末段是日常动作",
    },
    {
        "id": "pain-is-local",
        "source": "莫言 · 疼在具体处",
        "principle": "强烈感受只落在一处身体或一种味道上，不把五感排成清单，也不升到民族或命运。",
        "practice": (
            "一场只留一种主导感觉",
            "用那一处的具体名词，不用惨烈之类的评语",
            "旁人继续做自己的事",
        ),
        "signal": "单场景主导感官不超过一种；无命运判词",
    },
    {
        "id": "marvel-as-fact",
        "source": "马尔克斯 · 奇事当事实",
        "principle": "异常的事用报账的语气说完，不解释原理，也不提醒读者这很神奇。",
        "practice": (
            "奇事与买菜用同一种句子",
            "不写众人震惊",
            "来历只给一句，随即去做下一件小事",
        ),
        "signal": "异常事件无解说；语气与日常相同",
    },
    {
        "id": "one-line-one-act",
        "source": "古龙 · 一句一事",
        "principle": "一句只做一件事。对白本身就是动作，不加情绪标签，段与段之间留空白。",
        "practice": (
            "长句拆开，直到一句里只剩一个动作或一句说",
            "删掉他说道之后的神态说明",
            "用空行代替过渡",
        ),
        "signal": "单句信息点少；对白后少有神态从句",
    },
    {
        "id": "banquet-shows-person",
        "source": "曹雪芹 · 席面上见人",
        "principle": "人的地位、亲疏和心计从座次、称呼、谁先动筷和一句闲话里显出来，不开人物介绍。",
        "practice": (
            "用称呼的变化代替关系说明",
            "让配角忙自己的事，顺便露出主角",
            "礼仪出错比心理描写更有用",
        ),
        "signal": "无人物小传；关系来自称谓与次序",
    },
    {
        "id": "manners-are-power",
        "source": "奥斯汀 · 礼节即权力",
        "principle": "权力发生在该说不该说、谁先停顿、谁把话接过去。叙述可以轻，刀在对白里。",
        "practice": (
            "冲突写成一句不合时宜的话",
            "用旁人的反应显示这句话的分量",
            "不写她感到被冒犯了",
        ),
        "signal": "冲突落在说辞与停顿；少心理命名",
    },
    {
        "id": "stop-at-instant",
        "source": "川端康成 · 停在一瞬",
        "principle": "情绪停在一个看见的瞬间，不解释这个瞬间意味着什么，也不把景物写成心情的比喻。",
        "practice": (
            "收在一个物件或一个动作上",
            "景物就是景物",
            "删掉由此他想到",
        ),
        "signal": "收束是具体瞬间；无由此想到",
    },
    {
        "id": "idea-becomes-cost",
        "source": "刘慈欣 · 概念变成后果",
        "principle": "大概念只通过一个可核对的后果存在：谁付出什么、哪一项数字改变了决定。不讲课。",
        "practice": (
            "设定改写成一次操作的结果",
            "数字只在有人用它做选择时出现",
            "删掉原理回顾段",
        ),
        "signal": "无讲解段；概念带有可见代价",
    },
    {
        "id": "absurd-argument",
        "source": "王小波 · 用荒唐事讲理",
        "principle": "道理不正面宣布，放进一件具体的荒唐事或一句反话里，说完就去做别的。",
        "practice": (
            "把议论改成一件做错的小事",
            "反话只说一句",
            "不要在段末翻译这句反话",
        ),
        "signal": "无段末释义；道理依附于事件",
    },
    {
        "id": "scene-beside-person",
        "source": "萧红 · 景物与人事并置",
        "principle": "景色和人事放在相邻的句子里，不写因为风景所以心情。关系让读者自己接。",
        "practice": (
            "一段里让一件家务和一件心事隔句出现",
            "不使用因此、于是来焊接它们",
            "结束在还没做完的家务上",
        ),
        "signal": "景物与人事并列；少因果焊接词",
    },
    {
        "id": "violence-unadorned",
        "source": "麦卡锡 · 连动不渲染",
        "principle": "一连串动作用平直的句子接上，不渲染血腥，也不停下来评价谁是对的。",
        "practice": (
            "动词连着动词，中间不插感想",
            "伤只写它妨碍了下一个动作",
            "不给凶手或受害者加道德判词",
        ),
        "signal": "动作链中无评价词；伤害服务于下一步",
    },
    {
        "id": "later-look-back",
        "source": "门罗 · 事后才回头",
        "principle": "先写后来的一个普通场面，再漏出以前的一件事。不按时间表讲完，也不宣布现在她懂了。",
        "practice": (
            "开场放在事件之后",
            "旧事只给改变了现在这一动作的那一截",
            "禁止终于明白",
        ),
        "signal": "时间不是一条直线；无顿悟句",
    },
    {
        "id": "thought-in-progress",
        "source": "托尔斯泰 · 念头正在发生",
        "principle": "写人物这一分钟实际在想的下一句，包含自相矛盾。不写他是一个什么样的人。",
        "practice": (
            "念头跟着眼前的刺激改道",
            "允许想了两句就去做一件小事",
            "删掉性格总结",
        ),
        "signal": "心理是进行中的句子；无性格说明书",
    },
    {
        "id": "two-accounts",
        "source": "芥川龙之介 · 两说并存",
        "principle": "同一件事留下两种说法，叙述者不裁判哪一种是真的。",
        "practice": (
            "让两个当事人的说法在事实细节上对不上",
            "不写真相其实是",
            "读者要的那一处就让它空着",
        ),
        "signal": "关键事实有两个版本；无裁判句",
    },
    {
        "id": "repeat-without-gloss",
        "source": "杜拉斯 · 重复而不解释",
        "principle": "同一句或同一个物件隔一段再出现，不解释为什么要重复。重复本身就是压力。",
        "practice": (
            "选一句短话复现两次",
            "第二次不要加他终于懂得",
            "重复之间做别的事",
        ),
        "signal": "有意复现且无释义",
    },
    {
        "id": "labor-and-ledger",
        "source": "路遥 · 劳动与账",
        "principle": "人的处境通过干活、工分、路和一顿饭的花费立住。不喊志向，不替人物做总结发言。",
        "practice": (
            "写清楚这一天的活计和开销",
            "决心放进下一步要干的活里",
            "删掉旁白的赞美",
        ),
        "signal": "有可核对的劳动与花费；无颂词",
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
    {
        "id": "not-only-flip",
        "category": "句法",
        "pattern": "否定翻转机械句成依赖：不是X，而是Y / 他要的不是钱，是尊严。用否定来制造深度，实为替读者做排除法。",
        "fix": "直接写 Y 本身；只保留一次真正的纠正性否定，且由人物说出而非旁白。",
    },
    {
        "id": "explanatory-appositor",
        "category": "结构",
        "pattern": "新名词一出现就挂同位语解释，深绿色窗帘——那种老式塔楼常用的遮光布；解释密度高得像注释文档。",
        "fix": "让用途、代价或别人的反应来解释这个词，或直接不解释。",
    },
    {
        "id": "pov-drift",
        "category": "视角",
        "pattern": "段落内从人物滑向作者：他不知道的是、多年以后他才明白、如果当时回头就会看见。限知视角被旁白凿穿。",
        "fix": "删掉全部预知与追述式旁白；信息只能经人物的感知、谈话或物证进入。",
    },
    {
        "id": "loop-echo",
        "category": "修辞",
        "pattern": "顶针回环成瘾：他沉默了，沉默得像一堵墙；握紧的手，握紧的是不肯认。分句级回环反复出现即成机器纹。",
        "fix": "回环只用于一处真正的结构性呼应，其余改为新的具体动作。",
    },
    {
        "id": "trailer-ending",
        "category": "收束",
        "pattern": "章末预告腔：而他不知道的是，这将是他最后一次接这个电话；命运的齿轮开始转动。用旁白预告后果代替悬念本身。",
        "fix": "章末落在一个未完成动作、一句没接的话或一个具体物件上，让缺口自己勾人。",
    },
    {
        "id": "fake-precision",
        "category": "词汇",
        "pattern": "无来由的精确数字充当可信度：三点十七分、七步、十三级台阶，但人物没有理由数、也没人用它做决定。",
        "fix": "删掉；只有当这个数字进入人物的选择、代价或账目时才保留。",
    },
    {
        "id": "emotion-triad",
        "category": "情绪",
        "pattern": "情绪转折固定三连：愣住→眼眶发热→深呼吸。同一套身体反应在所有强情绪节点按同一顺序复用。",
        "fix": "为该人物该处境找一种不体面的反应（去做无关的事、说错话、惦记小钱）。",
    },
    {
        "id": "sensory-quota",
        "category": "描写",
        "pattern": "五感配额化：每个新场景机械凑齐视听嗅触，四句一套像填表。",
        "fix": "只写视角人物此刻会注意的那一两种感觉，允许一段没有环境描写。",
    },
    {
        "id": "setting-mouthpiece",
        "category": "对白",
        "pattern": "设定传声筒：配角向已知内情的人解释世界观，台词替作者完成任务。",
        "fix": "把交代改成交价、规矩或争执；能不问就不解释。",
    },
    {
        "id": "grade-word-premodifier",
        "category": "词汇",
        "pattern": "万能形容词前置：深深的、巨大的、莫名的、难以言喻的，修饰语强度代替内容。",
        "fix": "换成该人物职业内的具体名词与动词；形容词撑不住就重写这句。",
    },
    {
        "id": "summary-closing-paragraph",
        "category": "结构",
        "pattern": "段落或章节末尾出现总结句：这一刻他终于明白、这一夜改变了他此后的所有决定。",
        "fix": "删掉末句；意义由读者从动作与后果里得出。",
    },
    {
        "id": "theme-declaration",
        "category": "结构",
        "pattern": "点题句：人物直接说出主题（人这辈子总要搬一次家），把小说写成寓言的注释。",
        "fix": "让主题从重复的处境与代价里浮现；要说也只说半句且被立刻打断。",
    },
    {
        "id": "mirror-symmetry",
        "category": "修辞",
        "pattern": "工整对偶癖：A教会他X，B让他明白Y；两两对称的句式排列让文本像标语。",
        "fix": "把其中一项写长、一项写短或直接删掉，破坏对称。",
    },
    {
        "id": "polished-roughness",
        "category": "对白",
        "pattern": "打磨过的粗糙：蓝领或底层角色满口谚语、句句有节奏感，像演员演工人。",
        "fix": "让这类角色废话多、说半截、词不达意，删掉所有漂亮的粗话。",
    },
    {
        "id": "glint-in-the-eye",
        "category": "情绪",
        "pattern": "眼中闪过一丝复杂、狠厉或温柔，用眼睛代替人物刚刚做的决定。",
        "fix": "写他盯住的那件东西，或他改口的那半句。",
        "bad": "他眼中闪过一丝复杂。",
        "good": "他把找零推回去，又抽回一张。",
    },
    {
        "id": "ritual-breath",
        "category": "情绪",
        "pattern": "每到情绪节点就深吸一口气、握紧拳头、喉结滚动，成套的身体仪式。",
        "fix": "写他手上没做完的那件事。",
        "bad": "他深吸一口气，握紧了拳头。",
        "good": "水开了，他没去关火。",
    },
    {
        "id": "frozen-air",
        "category": "描写",
        "pattern": "空气仿佛凝固、时间仿佛静止、气氛降到冰点，用空间代替现场里的人。",
        "fix": "写屋里谁先出了声，或谁先把东西放下。",
        "bad": "空气仿佛凝固了。",
        "good": "没人夹菜。母亲先把筷子放下。",
    },
    {
        "id": "mixed-flavors",
        "category": "情绪",
        "pattern": "心中五味杂陈、心湖掀起波澜、一股暖流涌上，情绪被写成风景。",
        "fix": "直接说他怕或他恼，或者写他去做的一件小事。",
        "bad": "他心中五味杂陈。",
        "good": "他怕。他把剩下的半碗面吃完了。",
    },
    {
        "id": "body-only-emotion",
        "category": "情绪",
        "pattern": "同一段里胸口发紧、指尖冰凉、后背渗汗连用，情绪只剩身体感觉。",
        "fix": "身体感觉只留一处，其余改成他做了什么。",
        "bad": "胸口发紧，指尖冰凉，后背渗汗。",
        "good": "他怕，还是把合同签了。",
    },
    {
        "id": "tidy-cause-chain",
        "category": "结构",
        "pattern": "于是、因此、接着连成一条，每件事都由上一件事推出，没有旁人和意外。",
        "fix": "留一件不是主角推动的事，写完就继续。",
        "bad": "因此他决定留下，于是一切都改变了。",
        "good": "他想走。房东先把电闸拉了。",
    },
    {
        "id": "growth-reconciliation",
        "category": "收束",
        "pattern": "结尾是想通、和解、自己把问题解决，三段一起出现。",
        "fix": "停在没办完的后果上，不要写成成长完成。",
        "bad": "他终于明白，也原谅了父亲，问题就此解决。",
        "good": "父亲的钥匙还在他口袋里。门没锁。",
    },
    {
        "id": "sense-inventory",
        "category": "描写",
        "pattern": "新场景按看见、听见、闻到各写一句，像在填五感表。",
        "fix": "只留这个人此刻会注意的一种。",
        "bad": "他看见灰，听见风，闻到锈。",
        "good": "锁是锈的，钥匙拧了两次才动。",
    },
)


def _gene_line(gene: dict[str, str | tuple[str, ...]]) -> str:
    practices = "；".join(gene["practice"])  # type: ignore[arg-type]
    return (
        f"- {gene['source']}｜{gene['principle']}"
        f"做法：{practices}。信号：{gene['signal']}。"
    )


def _gene_label(gene: dict[str, str | tuple[str, ...]]) -> str:
    """Short author-facing label: the technique name without its author."""
    return str(gene["source"]).split(" · ")[-1]


def render_positive_genes_brief(max_chars: int | None = None) -> str:
    """Render the positive gene library.

    ``max_chars=None`` keeps the full library: this is an author-facing
    reference file, not model context. Pass a budget only for injections.
    """
    lines = [_gene_line(gene) for gene in POSITIVE_STYLE_GENES]
    return _truncate_lines(lines, max_chars)


def render_ai_tells_brief(max_chars: int | None = None) -> str:
    """Render the AI-tell catalog (full by default; bounded when injected)."""
    lines = []
    for tell in AI_TELL_PATTERNS:
        line = f"- [{tell['category']}] {tell['pattern']}→ {tell['fix']}"
        bad = str(tell.get("bad") or "").strip()
        good = str(tell.get("good") or "").strip()
        if bad and good:
            line += f" 反：{bad} 正：{good}"
        lines.append(line)
    return _truncate_lines(lines, max_chars)


def _first_clause(value: str) -> str:
    """First clause boundary: never leaks a dash, a second sentence, or a tail."""
    text = str(value).strip()
    for separator in ("：", "；", "。", "——"):
        text = text.split(separator, 1)[0]
    return text.strip()


def _gene_gist(gene: dict[str, str | tuple[str, ...]]) -> str:
    """Terse gist: the leading clause of the principle."""
    return _first_clause(gene["principle"])


def gene_checklist_lines() -> list[str]:
    """Unchecked adoption checklist for the voice bible, derived from the corpus."""
    return [
        f"- [ ] {_gene_label(gene)}"
        for gene in POSITIVE_STYLE_GENES
    ]


def _rotated(items: Sequence[dict], chapter: int, count: int) -> list[dict]:
    """Return ``count`` items, shifting with the chapter so capsules differ."""
    if not items or count <= 0:
        return []
    start = (max(int(chapter), 1) - 1) % len(items)
    return [items[(start + offset) % len(items)] for offset in range(count)]


def _tell_line(tell: dict[str, str]) -> str:
    bad = str(tell.get("bad") or "").strip()
    good = str(tell.get("good") or "").strip()
    if bad and good:
        return f"- 避 {bad} → {good}"
    return f"- 避 {tell['category']}·{_first_clause(tell['pattern'])}"


def render_writer_style_brief(
    adopted: Sequence[str] = (),
    max_chars: int = 420,
    *,
    chapter: int = 0,
) -> str:
    """Capsule style card: at most two techniques, plus two concrete avoids.

    The full library stays in ``memory/style-reference.md``. A chapter with no
    author selection gets the name menu so the writer picks one or two; it does
    not receive every principle. Author-checked labels are capped at two.
    """
    wanted = [str(item).strip() for item in adopted if str(item).strip()]
    genes = []
    if wanted:
        genes = [
            gene
            for gene in POSITIVE_STYLE_GENES
            if any(
                key in str(gene["source"]) or key == gene["id"]
                for key in wanted
            )
        ][:2]
    lines: list[str] = []
    if genes:
        lines.append("本章只用下面 1 到 2 种，不要再叠加。")
        for gene in genes:
            lines.append(f"- 学 {gene['source']}：{_gene_gist(gene)}")
    elif chapter:
        names = "、".join(_gene_label(gene) for gene in POSITIVE_STYLE_GENES)
        lines.append(f"写法只取 1 或 2 种，不要叠加：{names}。")
    else:
        genes = [
            gene
            for gene in POSITIVE_STYLE_GENES
            if gene["id"] in CORE_POSITIVE_GENE_IDS
        ][:2]
        for gene in genes:
            lines.append(f"- 学 {gene['source']}：{_gene_gist(gene)}")
    if chapter:
        paired = [
            tell
            for tell in AI_TELL_PATTERNS
            if str(tell.get("bad") or "").strip()
            and str(tell.get("good") or "").strip()
        ]
        tells = _rotated(paired or AI_TELL_PATTERNS, chapter, 2)
    else:
        tells = [
            tell for tell in AI_TELL_PATTERNS if tell["id"] in CORE_AI_TELL_IDS
        ][:2]
    lines.extend(_tell_line(tell) for tell in tells)
    return _truncate_lines(lines, max_chars) or "- 未登记。"

# MiniMax M3 五章连续实验：Markdown 格式漂移

## 样本

- 项目：`yanshi-lu`
- Harness：Claude Code + Novel Forge Skill
- 模型：MiniMax-M3[1M]
- generation 记录：5 个语义版本，全部为 `generation_stage=raw`
- 推理强度：全部记录为 `reasoning_effort=max`
- 审稿来源：六角色均与生成同 provider/model，`review_confidence=single_origin`
- 当前结果：五章均被推进到 `ready`，但不具备模型比较资格

实验书原文件已按用户要求于 2026-07-18 从本地 `books/` 删除。本文件与同名 JSON 保存可复核的量化结论、正文 SHA-256、原始文件时间戳和 v3.7 门禁结果。

## 污染曲线

| 章节 | CJK | `**` 标记数 | 粗体 span | 粗体内 CJK | 占本章 CJK |
|---|---:|---:|---:|---:|---:|
| ch01 | 5018 | 0 | 0 | 0 | 0.00% |
| ch02 | 5072 | 1394 | 694 | 892 | 17.59% |
| ch03 | 5021 | 4711 | 2332 | 2357 | 46.94% |
| ch04 | 5143 | 5119 | 2542 | 2520 | 49.00% |
| ch05 | 5370 | 5237 | 2597 | 2547 | 47.43% |

第 2 章前半主要是关键词强调；到正文第 165 行附近开始退化为连续逐词、逐字强调。第 3 章场景包的 `**` 标记从前一章的 336 个增加到 2028 个，之后正文稳定在近半汉字被 Markdown span 包裹。

五章正文 SHA-256：

| 章节 | SHA-256 |
|---|---|
| ch01 | `b9836f73877ed504457989138fc4382630cf9d273ce19dfe471534fb2062e25c` |
| ch02 | `b81def7e341400edd3af746d0e63aaa3db3b8455cb0b1893fbb5efd5d0285a32` |
| ch03 | `85b1769d810af056d4c01af0f854af180ff5b9b0d4f442eb0cc5246b0781c7ac` |
| ch04 | `877cdd4404ca9d029296ab4c1de88102c01a44c8166f33296fb58dc0f41d5a37` |
| ch05 | `a0de2ec6b7aa8f0f3d9879f2566b922d1d28746cf96894c8cca5d4f7a1378fcf` |

## 传播路径

1. ch01 正文干净，但规划模板本身合法使用 Markdown 粗体标签。
2. ch02 正文开始模仿规划材料的强调语法，并在后半章加速碎片化。
3. ch03 context/planning 读取 ch02 后，把污染格式当作内容特征继续复制。
4. texture-editor、blind-reader 等角色直接引用带 `**` 的原文并给出 pass。
5. 旧 lint 只报告节奏、字数与机械三连，`Blocking: 0`；`ready` 因而没有被阻止。

## 结论

这不是单次随机 hallucination 能完整解释的现象，更接近“模型格式模仿 + 跨章上下文反馈 + 门禁漏检”。模型负责产生第一次错误，工作流负责没有及时阻断并放大它。

Token 消耗也不能只归因于小说正文长度。该项目本地资产约为：

| 区域 | 文件数 | 字节 | CJK |
|---|---:|---:|---:|
| `.claude/agents` | 8 | 22,201 | 4,773 |
| planning | 20 | 144,672 | 30,294 |
| memory | 6 | 16,749 | 4,055 |
| reviews | 31 | 125,638 | 23,614 |
| chapters | 5 | 119,661 | 25,624 |
| evidence | 7 | 15,293 | 1,795 |

如果 Max 模式反复全文读取规划、正文和六角色审稿，成本会被流程资产显著放大。v3.7 因此采用 source-hygiene blocking、`surface_checked` 硬迁移和昂贵审核前短路，而不是继续增加审稿层。

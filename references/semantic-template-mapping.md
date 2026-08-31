# 语义到 B-roll 模板的映射

本映射把教程中的运行时判断固化成可维护目录。它不根据单个关键词选模板，而按下面的顺序路由：

1. 先写清 `viewer_takeaway`：这一镜结束时观众必须理解什么。
2. 判断 `screen_role`。讲人、经历、态度和情绪用 A；讲知识增量、证据、关系和步骤用 B。
3. B-roll 判断 `material_type`：`verified-media`、`no-material` 或 `text-only`。
4. 判断一个主 `semantic_structure`：`comparison`、`aggregation`、`filtering`、`hierarchy`、`causality`、`replacement`、`expansion`；再用 `semantic_pattern` 描述具体骨架模式。
5. 用主结构找到候选族，再用具体模式、信息项数量、时长、画幅匹配 `templates/template-index.json`。
6. 本地没有合适模板时，强制查询 `semantic-template-map.json` 中同结构的外部候选；读取具体镜头卡，`port-required` 候选还要读取实现文件。
7. 输出候选与最小改造范围，按项目审核模式确认或自检后实现或移植。候选均不适合时必须记录逐项拒绝理由，不能直接从零创建 SVG。

## 七类结构的判定边界

| 结构 | 核心问题 | 常见语言 | 不要误用 |
|---|---|---|---|
| `comparison` | 两个或多个对象有什么差异 | 相比、而、前后、两种 | 重点是动作导致结果时改用 `causality` |
| `aggregation` | 多个来源如何汇到一个结果 | 汇总、统一、集中、整合 | 只是逐项列出时改用 `expansion` |
| `filtering` | 如何从候选中保留目标 | 筛选、排除、选择、聚焦 | 只是强调一个已有结论时可用文字动效 |
| `hierarchy` | 信息的父子、主次或层级是什么 | 分为、包含、上层、下层、核心 | 只有时间先后时改用 `causality` 或时间线 |
| `causality` | 一个动作或条件如何导致结果 | 因为、所以、触发、导致、如果就 | 只陈列相关性时不能强行画因果箭头 |
| `replacement` | 同一位置或对象如何从旧状态变成新状态 | 从…变成、替代、升级、切换 | 两个状态需同时比较时改用 `comparison` |
| `expansion` | 一个概念如何逐项展开 | 包括、分别是、步骤、展开来说 | 多项最终合成一个结果时改用 `aggregation` |

主结构只能有一个；交叉特征写入 `secondary_structures`，不用于第一轮模板检索。`semantic_pattern` 可以自由描述具体关系，但应优先复用已有模板的模式名。无法确定主结构时保持 `unresolved`，不得为了命中模板随意贴标签。

## 画面表现与语义结构的关系

`presentation_type` 与语义结构是不同维度：

- `character`：人物表达；通常属于 A-roll。
- `scene`：具体情境或动作；通常属于 A-roll，也可作为有素材 B-roll。
- `verified-media`：截图、录屏、照片或真实证据。
- `infographic`：步骤、关系、比较、流程、数据和因果。
- `text-motion`：引文、关键词、概念替换和结论。

同一个 `comparison` 可以用真实截图拉杆，也可以用双栏信息图；不能仅凭语义结构决定最终画面形式。

## 外部候选状态

- `reference-only`：只有镜头配方或演示，必须重新实现。
- `port-required`：存在其他框架源码，必须移植并验证 seek-safe。
- `structure-study-only`：许可证未确认，只允许抽象研究结构，不能复制源码。
- `local-template`：已进入本地模板索引，并按索引中的状态判断是否可直接使用。

外部候选不是本地模板。只有完成许可证记录、HyperFrames 移植、目标画幅与 seek-safe 验证后，才能加入 `templates/template-index.json`。

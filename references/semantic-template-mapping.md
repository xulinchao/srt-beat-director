# 语义到 B-roll 模板的映射

本映射把项目的运行时判断固化成可维护目录。它不根据单个关键词选模板，而按下面的顺序路由：

1. 先写清 `viewer_takeaway`：这一镜结束时观众必须理解什么。
2. 判断 `screen_role`。讲人、经历、态度和情绪用 A；讲知识增量、证据、关系和步骤用 B。
3. B-roll 判断 `material_type`：`verified-media`、`no-material` 或 `text-only`。
4. 判断一个主 `semantic_structure`：`comparison`、`aggregation`、`filtering`、`hierarchy`、`causality`、`replacement`、`expansion`；再用 `semantic_pattern` 描述具体骨架模式。
5. 按 §6 双层策略选型：快路径先查本地认证模板（`template-index.json`）；本地没有时通过 `config/project.json` 的 `repositories_root` 召回参考仓库候选。新程序化 B-roll 按 [表达选型](broll-expression-selection.md) 提供动作简报，跨语义类别查看实际预览与源码；选择器分数只排浏览顺序，确认来源后才算命中。未确认来源时完成外部研究，再决定慢路径静帧布局。
6. 选定唯一来源与运动方案后，按复杂度复用布局证据或检查必要关键状态，记录 layout_review；多状态镜头带原旁白动态预览，不以终态截图代替运动验收。当前原生快路径支持 Remotion / HyperFrames；Motion Canvas 候选保留其真实框架身份，须另行完成适配与运行校验，不能标为 HyperFrames。
7. 只有遍历本地模板与参考仓库仍不合适，才允许有证据的自建，须逐项记录实际检查的候选与拒绝理由；目录为空或拒绝两项不代表完成研究。

## 七类结构的判定边界

| 结构 | 核心问题 | 常见语言 | 不要误用 |
|---|---|---|---|
| `comparison` | 两个或多个对象有什么差异 | 相比、而、前后、两种 | 重点是动作导致结果时改用 `causality` |
| `aggregation` | 多个来源如何汇到一个结果 | 汇总、统一、集中、整合 | 只是逐项列出时改用 `expansion` |
| `filtering` | 如何从候选中保留目标 | 筛选、排除、选择、聚焦 | 只是强调一个已有结论时可用文字动效 |
| `hierarchy` | 信息的父子、主次或层级是什么 | 分为、包含、上层、下层、核心 | 只有时间先后时用 `expansion` 配时间线模式，不当作因果 |
| `causality` | 一个动作或条件如何导致结果 | 因为、所以、触发、导致、如果就 | 只陈列相关性时不能强行画因果箭头 |
| `replacement` | 同一位置或对象如何从旧状态变成新状态 | 从…变成、替代、升级、切换 | 两个状态需同时比较时改用 `comparison` |
| `expansion` | 一个概念如何逐项展开 | 包括、分别是、步骤、展开来说 | 多项最终合成一个结果时改用 `aggregation` |

主结构只能有一个；交叉特征写入 `secondary_structures`，不改变主分类。动作标签可跨这些分类检索。`semantic_pattern` 可以自由描述具体关系，但应优先复用已有模板的模式名。无法确定主结构时保持 `unresolved`，不得为了命中模板随意贴标签。

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
- `available`：存在源框架源码；选用前仍须核对动作、许可证、运行路由、目标画幅与 seek-safe。当前 Remotion / HyperFrames 可评估原生制作，Motion Canvas 尚不属于已验证的原生快路径。
- `structure-study-only`：许可证未确认，只允许抽象研究结构，不能复制源码。
- `local-template`：已进入本地模板索引，并按索引中的状态判断是否可直接使用。

外部候选不是本地模板。只有完成许可证记录、原生框架的实际渲染、目标画幅与 seek-safe 验证后，才能加入 `templates/template-index.json`，并记录 `runtime` 与 `animation_status`。Remotion 原生效果无需先转成 HyperFrames 才能收录。

发布后的 Skill 可先独立校验目录结构，不要求本地存在开发阶段的外部仓库副本：

```text
python scripts/validate_semantic_map.py \
  --mapping references/semantic-template-map.json \
  --template-index templates/template-index.json \
  --out references/semantic-template-validation-report.json
```

实际选择外部候选时，再取得对应仓库，并通过 `--repositories-root <external-repositories-root>` 验证具体镜头卡和实现文件。

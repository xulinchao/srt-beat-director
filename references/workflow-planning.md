# 预检与视觉编排

适用：新任务的输入整理、内容分析、分镜；续做只处理受影响部分。先读 SKILL.md 的范围与续做规则。本页完成后按本次交付范围停止，或进入 [视觉基线与资产](workflow-production.md)。

## 输入与参考

完整生产需要可解析的 SRT 和对应 MP3；继续现有项目时先定位其已保存输入。可选输入包括 IP、三视图、视觉参考、真实截图/录屏、品牌规范、本地模板和输出规格。默认不设计或加入固定 IP 人物；只有用户明确要求设计或使用 IP、且尚未说明 B-roll 用途时，才询问一次该 IP 是否参与 B-roll，并把答复写入单片 DESIGN 的角色参与说明。已有明确答复直接沿用。重新设计或新建同系列任务时先继承已确认的 IP 与讲解需求；不得把“未要求 IP”的默认值覆盖到已有选择上。未要求 IP 时不为填满人物画面而创造跨镜头 IP；普通剧情人物是否出现仍由文案决定。参考用途登记到 `input/references/index.json`，区分 `character-identity`、`visual-style`、`layout-reference`、`motion-reference`、`verified-media`，再运行 `scripts/validate_references.py`。同一参考可登记多个用途，未声明的用途不能自行推断。

从配置、输入和用户要求确定主画面模式（`fixed-character-micro-scene` / `full-ai-scene`）、画幅、分辨率、帧率、平台、人物与风格、真实性限制、字幕安全区、样片区间和输出目录。没有现有规格时，默认横屏 `16:9`、`1920x1080`、`30fps`、约 45 秒代表性样片；用户明确指定或已有项目已确定的规格优先。初始化新任务时，将选定规格显式传入 `init_project.py` 的 `--aspect-ratio`、`--width`、`--height` 和 `--fps`。

用户以参考视频定风格时，先抽帧覆盖全片，再补代表镜头的建立/变化/结果；提炼配色、材质、字体、空间与动作语法，按本次文案重新设计。样片区间不限制参考分析范围，用户明确限制除外。只有明确要求复刻内容才沿用脚本和镜头。选择道系青年纸感/深绿网格时，读取 [可选预设](../assets/style-presets/dao-paper-grid/STYLE.md)，验证后写入单片 DESIGN。

## 本阶段读取

- 首次导演/改变方法：[方法基线](method-baseline.md)、[导演决策](directing.md)；知识分享/读书稿另读 [阅读方向](knowledge-reading-direction.md)。
- 字段：[契约](contracts.md) §1–5、§8；新动作/连续镜头门读 §10–11。
- 设计：[设计真源](design-system.md) 与 [DESIGN 模板](../templates/DESIGN.md)，未定稿时保留草稿。
- 分镜提示词：[production-prompts.md](production-prompts.md) §1 `visual-plan-v1`；实际代入并保存实例。
- 所有 B-roll 先读 [表达选型](broll-expression-selection.md) 的“两条创意路径”和“分镜必须说清的内容”；按实际内容选择成熟表达借鉴或内容驱动设计。
- 逐镜工具：[工具选型](broll-runtime-selection.md)；程序化 B-roll 再读 [表达选型](broll-expression-selection.md)、[语义映射](semantic-template-mapping.md)、[B-roll 生产](broll-production.md) 与生产提示词 §6。
- 新自制动效按 [连续镜头质量](sequence-quality.md) 查实际演示，覆盖照片动画与 A/B 镜头。无素材信息图完整研究流程另见 [外部研究](broll-external-research.md)。
- 关键动作的声音需要按 [音效](sound-design.md) 写入计划，BGM 按用户要求。

## 预检

仅新任务可运行 `scripts/init_project.py`；已有任务只补缺失真源。新任务的样片区间写入 `config/project.json`，`--sample-end-ms` 默认 45000ms；能读到音频时长时，超过音频长度的区间自动收敛到音频时长，短音频无需手工改默认值，收敛与未探测到音频时长都会在初始化输出中提示。运行 `python scripts/preflight.py --srt <path> --audio <path> --out-dir <project>/planning`，检查编码、时间顺序、重叠、空字幕、音频时长和末尾偏差，交付预检报告。输入未变化且已有有效报告时复用。

现有 ChatCut 项目按执行引用只读盘点身份、规格、字幕、轨道、素材池、已放置镜头及可复用计划，保存 `planning/project-inventory.json/.md`。完成盘点前不得替换素材。

## 内容理解与分镜

提取主题、主张、章节、论证、情绪和结论，合并相邻字幕为完整语义段，写清观众理解点和未经原文支持的推断，保存内容分析。仅要求分析时在此交付；需要分镜时再使用 `visual-plan-v1`，保存 `planning/visual-plan-prompt.json` 并生成 `planning/visual-plan.json`。

每镜记录 A/B 职责、表现形式、构图、有效变化、衔接、来源、`visual_design.motion_intent`（动效方式及旁白触发/停留节奏）、`production.primary_tool`（该镜最终视觉资产的制作工具）、回退和素材缺口；`changes` 与 `narration_beats` 一一对应，节拍绑定原始 cue 起点与 cue 原文连续片段。工具须在分镜阶段逐镜确定并写入 JSON，在八列表格之后的“逐镜制作路由”表中可读呈现。A/B 职责由叙事用途确定，H3、HyperFrames、Remotion 均不自动决定镜头职责；若以首尾帧驱动，首帧、尾帧、H3 workflow 和运动提示分别记录。程序化信息图 B-roll 选型按上表读取引用，新计划标记 `broll_matching_policy="expression-first-v1"` 与 `broll_layout_policy="motion-first-v1"`，先用 `validate_template_index.py`、`validate_semantic_map.py` 检查当前索引与语义目录，再将动作简报通过 `--expression-brief` 传入 `select_broll_template.py`，保存逐镜选择报告，确定 `semantic_structure`、具体 `visual_structure`、`semantic_pattern`、`item_count`、模板和工具；选择时列出最近三个 B-roll 的结构签名并完成复用审查，需要外部研究时先完成研究记录与校验。尚未解决的项留在草稿或素材请求中，不伪造通过。

新任务按数据契约 §10 声明 `motion_review_policy=evidence-first-v1`、代表镜头和每镜运动方式；非静止镜头写清可见动作、结果及必要状态。同一旁白节拍可含多个动作状态，不能因字幕少而改为静止。

启用`sequence_review_policy=sequence-quality-v1`时，在计划根节点填写`sequence_direction`；每镜`production.assembly_tool`与主工程一致。非静止程序化镜头或`custom_motion=true`的镜头声明`motion_reference_review`，参考要求覆盖A/B、真实照片和场景自制动效，不只覆盖无素材信息图。字段与复用边界见契约 §11。

生成可审阅的八列表格：`镜头 | 时间 | 配音文案 | A-roll / B-roll | 画面类型 | 画面设计 | 动态变化 | 画面衔接`。编号从 `S001` 连续递增，时间列用原始语义边界毫秒值，配音逐字保留。逐个接缝按 [导演规则](directing.md#切点与声音错开) 判断是否错开；需要时在后一镜 `transition.visual_cut` 登记偏移、理由与交接画面，“画面衔接”栏派生实际切点，不能只写在自然语言中。表后列出“需要补充的素材”“需要确认的视觉方向”“制作难度较高的镜头”，没有则写“无”。

```text
python scripts/validate_plan.py --preflight <project>/planning/preflight-report.json --project <project>/config/project.json --content-analysis <project>/planning/content-analysis.json --visual-plan <project>/planning/visual-plan.json --out-dir <project>/planning
python scripts/render_plan_markdown.py --plan <project>/planning/visual-plan.json --out <project>/planning/visual-plan.md
python scripts/validate_plan_markdown.py --plan <project>/planning/visual-plan.json --markdown <project>/planning/visual-plan.md
```

再按数据契约 §8 运行 `validate_prompt_usage.py --stage planning`。结构校验通过后，仍须按 QA 分镜门审查图片、讲解文字、IP、动作与保持是否明确；存在关键素材、表达或工具未决项时交付“设计提案/草稿”并列出缺口，不按可执行分镜请求批准。适用的参考证据按 sequence-quality 的阶段要求补齐，不把待制作动态样片冒称已通过。完成表达审阅并按审核模式记录结果后，才能进入视觉基线与生产；在此之前不创建 ChatCut 项目、不导入素材、不生成图片/视频/动画、不导出。仅要求分镜时在此交付，不继续生成资产。

进入视觉基线制作前运行 `check_workflow.py --action baseline`；该入口复用计划、可读视图、提示词和状态检查。细则与失败处理见 [执行检查](execution-routing.md)。

---
name: knowledge-abroll-video
description: 将对应的 SRT 与 MP3 或现有 ChatCut 项目制作成 A-roll 人物叙事、B-roll 知识表达交替的不露脸知识视频，并产出可审阅分镜、视觉资产、可复现动效、ChatCut 成片和可追溯报告。适用于按语义导演知识口播；不用于单纯字幕烧录、真人视频包装或纯音乐视频。
metadata:
  short-description: 从 SRT 与 MP3 制作不露脸知识视频
---

# Knowledge A/B-roll Video

把已有口播时间轴和配音稳定转成可复现的不露脸知识视频。Codex 负责读取 SRT 与 MP3、理解内容、编排全片并生成 A-roll 主画面；HyperFrames 负责 B-roll 信息动画；ChatCut Desktop 负责素材池、主时间线、字幕、声音和最终导出。先把内容导演清楚，再生成资产和动画；画面职责、时间、来源、实现工具与审核状态必须可追溯。

本 Skill 的方法基线来自配套教程、原始提示词和实际成片。开始导演前先读 [references/method-baseline.md](references/method-baseline.md)。[生产提示词方法库](references/production-prompts.md) 只用于理解方法和字段意图，不是嵌入命令；只读取当前阶段需要的部分，并以本 Skill、当前用户请求和项目真源为准。

## 入口与路由

必需输入：

- 一份可解析的 SRT；
- 一份与其对应的 MP3。

可选输入包括人物或 IP 参考图、三视图、笔触或场景参考、真实截图或录屏、品牌 UI 规范、本地动效模板和输出规格。每份参考必须登记用途范围，至少区分 `character-identity`、`visual-style`、`layout-reference`、`motion-reference` 与 `verified-media`；未获得授权的用途不得从同一张图中自行推断。

开始任务时：

1. 先判断是新建文件项目、继续现有文件工作区，还是继续现有 ChatCut 项目。现有项目先盘点，禁止重新初始化、覆盖或删除已有素材。用户指定 ChatCut 时，另读 [ChatCut 主时间线执行流程](references/chatcut-production.md)，先确认活动项目，再读取项目、时间线和素材池。
2. 读 [references/contracts.md](references/contracts.md)。只有新任务才可运行 `python scripts/init_project.py ...`；已有任务只补缺失真源。
3. 运行 `python scripts/preflight.py --srt <path> --audio <path> --out-dir <project>/planning`。已有 ChatCut 项目还要记录音频、字幕、时间线、轨道、素材池与已放置镜头的盘点结果。
4. 有人物参考时，先把用途登记到 `input/references/index.json`，再运行 `scripts/validate_references.py`。`character-identity` 只锁人物身份，不能顺带决定全片背景、B-roll UI、版式或动效语言。
5. 做内容分析和分镜前读 [references/directing.md](references/directing.md)。原始提示词参考只在需要核对方法来源时读取对应章节，不得覆盖当前项目真源。
6. B-roll 映射前读 [references/semantic-template-mapping.md](references/semantic-template-mapping.md)。先形成带语义结构的视觉计划草案，运行模板索引与语义目录校验，再为每个 B-roll 运行 `scripts/select_broll_template.py`。本地没有合格模板且目录存在外部候选时，必须读取 [B-roll 外部骨架研究门](references/broll-external-research.md)，检查具体镜头卡和实现文件，生成 `planning/broll-research/<shot-id>.json` 并通过 `scripts/validate_broll_research.py`；不得直接写 `new:<id>` 或开始制作 SVG。
7. 模板与外部研究路由完成后，运行 `scripts/validate_plan.py`，再用 `scripts/render_plan_markdown.py` 重生派生视图。外部来源必须落到具体文件、当前项目中的实现和实际渲染结果，不能只记录仓库链接。
8. 审核、样片和交付前读 [references/qa.md](references/qa.md)，并运行 `scripts/validate_state.py` 检查批准哈希和过期状态。
9. 只有实际使用 HyperFrames 时才读 `hyperframes` Skill，再按需读取底层 Skill；不用 HyperFrames 的镜头不得为满足流程而强行调用。

## 执行路径

- **ChatCut 主时间线路径**：用户指定 ChatCut，或现有项目已在 ChatCut 中时使用。ChatCut Desktop 是唯一主时间线和最终导出工具；本地文件、生成素材和 HyperFrames 渲染结果都导入同一素材池后组装。现有时间线不得被无保护覆盖；优先复制为新版本，原时间线和素材保留。
- **HyperFrames 主工程路径**：只有用户明确选择 HyperFrames 作为整片工程，或当前环境没有 ChatCut 且用户接受时使用。不要因为 B-roll 使用 HyperFrames，就把 ChatCut 主时间线改成 HyperFrames 主工程。
- **仅规划路径**：用户只要内容分析、分镜或素材清单时，在对应交付完成后停止，不生成高成本资产或改动外部时间线。

如果用户明确要求连续执行，视觉计划和低成本样片由代理按 QA 门自检后继续，不再额外请求形式化确认；工具明确要求的计费、账户授权、发布或系统权限仍需暂停。记录审核来源，不能把代理自检写成“用户已确认”。

若只是给现有视频烧录字幕、包装真人口播或按音乐节拍剪片，路由到对应专用视频 Skill，不使用本 Skill。

## 启动确认

先从项目配置、活动时间线、参考索引和用户请求中解析真正影响方向的参数：

- 主画面模式：`fixed-character-micro-scene` 或 `full-ai-scene`；
- 画幅、分辨率、帧率和发布平台；
- 人物来源与视觉风格；
- 每份参考图允许影响什么：只锁人物身份，还是也允许影响笔触、配色、版式或动效；
- 必须使用、必须核实或禁止编造的素材；
- 外部字幕安全区；
- 样片区间与输出目录。

上下文已经确定的参数不得重复询问。只有缺失信息会显著改变全片、无法从现有项目安全推断时才询问；否则按已记录配置推进。推荐默认值为：社交短视频 `9:16`、`1080x1920`、`30fps`、约 45 秒代表性样片；现有项目规格或用户明确选择优先。

## A/B-roll 操作定义

- **A-roll 是讲人。** 用固定 IP 或完整人物场景承载态度、经历、情绪、动作、开场、过渡和总结；没有具体知识增量但必须说的话，优先用 A-roll 场景化。
- **B-roll 是讲内容。** 用图形、文字、截图、录屏、数据或操作演示承载知识、概念、步骤、关系、比较、证据和信息增量。
- A-roll 的主持人、主角、配角、第一人称是构图视角；B-roll 的有素材、无素材、纯文字是素材类型。人物、场景、真实素材、信息图形、文字动效是表现形式。职责、素材类型、表现形式和语义结构不能混成同一分类维度。
- 默认建立强区分的双舞台：A-roll 使用明亮、手绘、有人物和环境的场景；B-roll 使用独立的深色知识舞台。截图和录屏保留原色，但由 B-roll 舞台、标注和排版承载。用户可改配色，但必须重新验证 A/B 是否仍能一眼区分。
- A/B 应自然交替以刷新注意力，但完整语义优先。连续三镜以上同类画面必须写明理由，并改变视角或信息结构，不能为交替而硬切。

## 不可变规则

- 先阅读全文并按完整语义分段，禁止一条 SRT 对应一张图或按固定秒数机械切镜。
- 全片只有两个交替出现的全屏舞台：A-roll 人物叙事与 B-roll 知识表达。首版不把 B-roll 作为浮层盖在 A-roll 人物上。
- 每条视频只选一种主画面生产模式并贯穿全片。重复人物、标志性物体和视觉世界必须一致。
- 人物 IP 与全片视觉系统是两个独立变量。标记为 `character-identity` 的参考只用于脸型、发型、头身比例、服装、配饰和标志性元素；不得据此复制背景、配色、信息卡、字体、构图或动效语言，除非同一参考同时获得对应用途授权。
- 主画面必须是居中或重心稳定、封闭、完整、可独立读懂的情境；关键人物、道具和线条不得被画布截断。
- B-roll 负责结构、关系、步骤、对比、证据和真实对象。动画顺序跟随口播信息出现顺序。
- 保留 SRT 原文和时间；镜头语义边界落在 SRT 边界上，MP3 决定最终总时长。开头静音显示首镜稳定帧，镜头间字幕空隙保持上一镜，尾部空隙保持末镜，禁止产生未定义黑帧。
- 字幕由主时间线统一管理；A/B 资产本身不重复烧录字幕，只保留配置化的字幕安全区。ChatCut 路径在时间线上导入、校对和导出字幕。
- 不编造产品界面、数据、案例、截图或引用。缺失时写入素材请求并停止该镜头的真实性实现。
- 所有时间轴和动画必须确定、seek-safe；禁止依赖刷新顺序、实时随机数或播放历史。
- JSON 是真源，Markdown 是给人看的派生视图。修改分镜时先改 JSON，再同步生成人类可读版本。

## 工作流与门控

### 0. 预检

登记原始输入，检查 SRT 编码、时间顺序、重叠、空字幕、音频时长和末尾偏差。输入问题先报告；默认不重写文案、不重新配音、不做声学对齐。

现有 ChatCut 项目还要检查：活动项目身份、时间线时长与规格、字幕状态、轨道和已放置素材、素材池中的图片/视频/音频/动效、现有视觉计划的可复用程度、已完成 A-roll 与缺失 B-roll。只读盘点完成前不得替换时间线素材。

### 1. 内容理解

提取主题、核心主张、章节、论证关系、情绪变化与结论。把相邻字幕合并为完整语义段；每段写清“观众要理解的一句话”以及原文未授权的推断。

### 2. 视觉编排

为每个镜头确定 A/B 职责、A 视角或 B 素材类型、表现形式、构图、有效动态变化、衔接、素材来源、风险、实现工具、回退路径和素材缺口。B-roll 还必须写一个标准主 `semantic_structure`、具体 `semantic_pattern` 和 `item_count`；标准结构只使用 `comparison`、`aggregation`、`filtering`、`hierarchy`、`causality`、`replacement`、`expansion`。具体模式用于同一结构族内选择骨架，不得用一次性模式名代替标准结构。先全片审查 A/B 节奏、重复表达、信息过载和缺失素材，不立即生成资产。

生成 `planning/visual-plan.json` 与派生的 `planning/visual-plan.md`，然后运行：

```text
python scripts/validate_plan.py \
  --preflight <project>/planning/preflight-report.json \
  --project <project>/config/project.json \
  --content-analysis <project>/planning/content-analysis.json \
  --visual-plan <project>/planning/visual-plan.json \
  --out-dir <project>/planning

python scripts/render_plan_markdown.py \
  --plan <project>/planning/visual-plan.json \
  --out <project>/planning/visual-plan.md
```

只有校验通过后才能进入视觉基线和资产阶段。手动审核模式等待用户确认；用户已明确授权连续执行时，按代理自检模式记录结果并继续。

### 3. 视觉基线

分别建立人物身份规范与视觉系统规范，再建立画面安全区、B-roll UI token，并制作一个典型 A 画面和一个典型 B 画面。人物身份与视觉系统必须分别记录参考范围和批准状态。人物三视图必须和用户原始 IP 的发色、发型、头身比例、服装和标志物逐项核对，不能只凭“整体相似”批准。只改变信息卡、主色、笔触、背景或动效语言时，不得误判为人物 IP 也失效；人物真源不一致时，所有依赖人物的 A-roll 资产必须过期。

### 4. 资产与模板

按真实依赖顺序生成资产：先人物或风格参考，再生成依赖它们的 A-roll；互不依赖的 B-roll 可以并行准备。A-roll 应按语义组合 `presenter`、`protagonist`、`supporting`、`first-person` 等视角，不能让固定人物全片反复居中站立；不要求机械凑齐四类，但连续 A-roll 必须改变叙事视角、动作或场景关系。

B-roll 按 `verified-media / no-material / text-only` 路由，并按表现形式、语义结构、信息项数量、时长和画幅匹配模板。生产顺序为：已核实素材直接复用；关系、流程、对比、因果等无素材信息动画由 HyperFrames 实现；需要动态抽象场景时再用视频生成；章节、金句和结论克制使用文字动效。HyperFrames 实现失败时先简化同一骨架或改用已研究的其他候选；仍失败则标记素材缺口并继续其他镜头，禁止静默换成无关静态图或把 ChatCut 临时动效当作默认替代。只有用户明确改变工具分工时，才把其他动效工具设为主实现。

模板索引先通过 `scripts/validate_template_index.py`，语义目录通过 `scripts/validate_semantic_map.py`。只有带可审阅预览、可追溯来源、明确动作阶段并得到质量批准的本地模板才可复用；否则必须先研究 `references/semantic-template-map.json` 中同结构的具体外部候选。候选均不适合时，只有在逐项记录拒绝理由和借鉴的运动原则后才允许从零实现；目录没有候选时才研究未索引仓库。复制或改造源码前记录来源、许可证、原框架和兼容性；未声明许可证的公开仓库只允许研究结构，不默认允许复制源码。静态 SVG 可以是 HyperFrames 组件，但不能单独作为完成的 B-roll 动画。

每项资产记录提示词、模型、参数、版本、来源和校验结果。只重做未通过或已过期的资产；单纯调整文字、布局或时间轴时不要重新出图。

### 5. 样片与主时间线

以 MP3 为主音轨，按照视觉计划构建确定性时间轴。ChatCut 路径中先把音频、字幕、A-roll、B-roll、真实素材和 HyperFrames 渲染结果统一导入 ChatCut，再按镜头边界放置；计划标为 B-roll 的区间必须在时间线上出现对应的信息表达，不能继续由装饰性静态图占位。

样片优先选择同时包含 A 画面、B 画面、一次完整切换、人物或场景一致性和典型信息动效的 30–60 秒区间。若全片不超过 60 秒，样片可以是整条低成本预览。样片必须通过结构、视觉和音画检查；手动审核模式等待确认，连续执行模式自行修复后继续。高成本批量生成只能在视觉基线稳定后进行；连续执行授权不等于允许绕过计费确认或真实性门控。

### 6. 全片与验收

沿用已锁定视觉基线完成全片，先低成本预览，再检查所有镜头的同步、构图、文字、人物、遮挡、裁切、节奏与来源。ChatCut 路径还必须做视觉计划到时间线的逐镜覆盖审计，并由 ChatCut Desktop 导出最终 MP4。修复后重新验证，最后输出 MP4、QA 报告、时间线审计和完整 manifest。

交付报告至少列出：实际使用的 A-roll 与 B-roll、ChatCut 生成或内置素材、HyperFrames 渲染素材、复用的已有文件、使用开源结构的镜头及具体仓库路径、原框架与许可证、时间线与视觉计划的一致性、剩余素材缺口、成片时间线 ID 和最终导出文件绝对路径。计划、提示词、静态预览或仓库链接都不能冒充已完成资产。

## 停止条件

遇到以下情况时保留已有产物并明确说明，不得假装完成：

- SRT 或 MP3 无法读取，或时间冲突无法安全推断；
- 用户要求真实产品、数据、截图或案例，但缺少可核实素材；
- 主画面模式、画幅或视觉基线仍存在会改变全片的冲突；
- 当前分镜、视觉基线或样片在所选审核模式下尚未通过；
- 外部生成、发布或账户操作需要新的授权；
- 某个阻塞镜头的选定实现和已声明回退路径全部失败，且尚未找到根因。

## 完成定义

只有当最新人物真源、视觉计划和视觉基线的审核哈希一致，最终 MP4 存在且可验证、音频与视频时长一致、全部镜头通过 QA、素材来源可追溯，并且输入、配置、分镜、B-roll 研究记录、提示词、资产、工程、样片、报告和 manifest 均已保留时，任务才算完成。ChatCut 路径还要求活动成片时间线与视觉计划逐镜一致，最终文件由 ChatCut Desktop 导出；外部仓库只有落实到具体源文件、当前实现、渲染文件和时间线实例才算真正使用。历史样片即使曾通过 QA，只要绑定了已作废基线，就只能作为历史证据，不能作为当前完成证明。

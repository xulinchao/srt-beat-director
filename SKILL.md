---
name: knowledge-abroll-video
description: 根据 SRT 与对应 MP3 或现有 ChatCut 项目，按语义编排和制作 A-roll 人物叙事、B-roll 知识表达协作的不露脸视频；支持内容分析、分镜、素材、样片、成片及续做。用于知识口播导演，不用于单纯字幕烧录、真人视频包装或纯音乐视频。
metadata:
  short-description: 从 SRT 与 MP3 制作不露脸知识视频
---

# Knowledge A/B-roll Video

把 SRT 与对应 MP3，或已有 ChatCut 项目，按完整语义制作成 A-roll 人物叙事与 B-roll 知识表达协作的不露脸视频。按用户所需交付内容分析、分镜、素材、样片或完整成片；仅维护本 Skill、检查文件或局部修复时，不启动整片生产流程。单纯字幕烧录、真人口播包装和纯音乐视频使用对应专用 Skill。

## 任务范围与审核

- 先识别新任务、现有文件工作区或现有 ChatCut 项目，以及本次交付阶段。已有任务先盘点并复用有效真源和资产，只补缺失或重做受影响部分；不得重新初始化、删除素材或覆盖原时间线。
- 用户明确指令优先于本 Skill 的默认流程。沿用已确定的规格、参考用途和审核授权；能安全推断的参数记录假设后推进，只有缺失信息会显著改变结果时才询问。
- 评估当前能力和优化规则时，以当前 `SKILL.md`、直接引用的契约及实现为准。历史报告只证明当时结果，不用旧样片或旧限制定义当前能力；不为同步说明而修改无关历史文档、记录或工作区。
- 用户提供参考视频用于建立风格时，目标是提炼可复用的配色、线条、材质、字体、空间与动作语法，并根据本次文案重新设计主体关系、构图、道具和变化。先抽帧覆盖全片，再补代表镜头的建立/变化/结果；样片制作区间不自动限制风格分析区间，用户明确限制资料读取范围时除外。只有用户明确要求复刻内容时才沿用参考视频的脚本、声音、镜头和版式；风格参考不默认变成固定分镜模板。已选风格记录到项目 DESIGN，经过真实文案样片验证后再沉淀为可选风格预设。
- `review_mode=manual` 保留用户审阅门；用户已明确要求自检后连续制作时使用 `continuous`，通过同一 QA 后继续，不逐镜重复索要确认。审核来源和最终批准规则统一见 [qa.md](references/qa.md)。代理自检不能记作用户确认。
- 连续制作不自动授权新增计费、发布、账户或系统权限操作。确需新授权时，先准备可审阅结果，再暂停相应操作；继续无依赖且已授权的工作。
- 如果具体 Skill 指令导致暂停，说明文件、相关原文和受阻动作；不要把建议自行解释成审批门。
- **出图全局停止门**：图片生成与编辑必须使用用户指定的内置 GPT 出图能力。工具不可用、调用失败、限流时，立即中断整个视频工作流并提示；不自动换模型、转 ComfyUI 或继续其他镜头。检查与恢复按 [出图停止规则](references/image-generation-policy.md)，优先于局部失败继续和连续制作授权。
- 用中文简洁汇报结果、文件位置和缺口；必要的分镜表与报告保留结构，过程不重复讲解规则。

## 按任务读取上下文

先确定当前阶段，只读取对应引用及其必要依赖；同一章节在上下文中且未变化时可复用，不逐镜重读。脚本路径相对本 Skill 根目录，`<project>` 指当前视频工作区；下文命令中的占位符须替换为实际路径。

| 当前工作 | 读取内容 |
|---|---|
| 初次导演或改变表达方法 | [method-baseline.md](references/method-baseline.md)、[directing.md](references/directing.md)；知识分享与读书稿另读 [knowledge-reading-direction.md](references/knowledge-reading-direction.md) |
| 创建或修改项目记录 | [contracts.md](references/contracts.md) 对应章节：目录 §1、真源 §2、配置 §3、内容 §4、计划 §5、模板 §6、交付 §7、提示词 §8 |
| 设计规范、角色互动或新视觉方向 | [design-system.md](references/design-system.md)、[DESIGN 模板](templates/DESIGN.md)；内容规划即加载，设计未定可保留草稿 |
| 用户选择道系青年纸感/深绿网格风格 | [可选风格预设](assets/style-presets/dao-paper-grid/STYLE.md)及其参考用途索引；按新文案设计，验证范围与待确认差距以预设为准 |
| 内容分析与分镜 | [production-prompts.md](references/production-prompts.md) §1 `visual-plan-v1` |
| 单张人物身份参考生成三视图 | 生产提示词 §2 `character-turnaround-v1`；仅重复人物需要时使用，已有核实三视图不重复生成 |
| A-roll 生产（图片、状态序列或连续动画） | 生产提示词 §3 `a-roll-image-v1`、§5 `a-roll-action-sequence-v1`；固定人物视角加 §4 `a-roll-view-v1`；出图先读 [出图停止规则](references/image-generation-policy.md)；选用生成视频时读 [comfyui-video-production.md](references/comfyui-video-production.md)，选用程序化动画时读 [制作工具决策](references/broll-runtime-selection.md) |
| B-roll 选型与生产 | 生产提示词 §6 `b-roll-motion-selection-v1`、[semantic-template-mapping.md](references/semantic-template-mapping.md)、[broll-production.md](references/broll-production.md)；需要出图先读 [出图停止规则](references/image-generation-policy.md)，需要生成视频时读 [comfyui-video-production.md](references/comfyui-video-production.md)；用户另行明确改用本地出图后才读 [本地图片生产](references/comfyui-image-production.md) |
| 无素材信息图未命中合格本地模板 | [broll-external-research.md](references/broll-external-research.md)；按当前结构读取具体候选卡及必要源码 |
| 逐镜工具选择（A/B 均适用） | [broll-runtime-selection.md](references/broll-runtime-selection.md)；只加载选中框架的执行 Skill，HyperFrames 用 `hyperframes`，Remotion 用可用的制作/渲染技能；ComfyUI 视频先运行环境探测 |
| 完整视频的 ChatCut 主工程与时间线（新建或续做） | [chatcut-production.md](references/chatcut-production.md)；续做时先只读盘点，完整新制在分镜和视觉基线通过后创建 |
| 分镜动作音效、声音组装与验收 | [sound-design.md](references/sound-design.md)；沿用既有字段与审核模式 |
| 阶段审核、恢复过期状态或交付 | [qa.md](references/qa.md) 对应门控；快照与扫描证据字段见契约 §9 |
| 沉淀可复用 B-roll 模板 | [template-library.md](references/template-library.md)，只认证实际渲染通过的模板 |

生产提示词是执行真源，按阶段代入真实输入并保存实际提示词实例；字段和命令见数据契约 §8。不能只引用原则或伪造历史使用记录。依赖以随 Skill 发布的文件、当前输入和实际可用工具为准，不要求读取未随包发布的本地研究目录。

## 输入与执行路径

完整生产需要可解析的 SRT 和对应 MP3；继续现有项目时先定位其已保存输入。可选输入包括 IP、三视图、视觉参考、真实截图/录屏、品牌规范、本地模板和输出规格。默认不设计或加入固定 IP 人物；只有用户明确要求设计或使用 IP、且尚未说明 B-roll 用途时，才询问一次该 IP 是否参与 B-roll，并把答复写入单片 DESIGN 的角色参与说明。已有明确答复直接沿用。未要求 IP 时不为填满人物画面而创造跨镜头 IP；普通剧情人物是否出现仍由文案决定。参考用途登记到 `input/references/index.json`，区分 `character-identity`、`visual-style`、`layout-reference`、`motion-reference`、`verified-media`，再运行 `scripts/validate_references.py`。同一参考可登记多个用途，未声明的用途不能自行推断。

从配置、输入和用户要求确定主画面模式（`fixed-character-micro-scene` / `full-ai-scene`）、画幅、分辨率、帧率、平台、人物与风格、真实性限制、字幕安全区、样片区间和输出目录。没有现有规格时，默认横屏 `16:9`、`1920x1080`、`30fps`、约 45 秒代表性样片；用户明确指定或已有项目已确定的规格优先。初始化新任务时，将选定规格显式传入 `init_project.py` 的 `--aspect-ratio`、`--width`、`--height` 和 `--fps`。

- **ChatCut 主工程（完整视频默认）**：新制完整视频默认使用 ChatCut Desktop 管理素材池、字幕、声音、主时间线和最终导出；续做已有项目时先只读盘点并保护原时间线。`init_project.py` 创建的是本地工作区，不等于 ChatCut 项目；新 ChatCut 项目须在分镜与视觉基线通过后创建。
- **单镜制作工具**：在视觉编排阶段为每镜填写 `production.primary_tool`；HyperFrames、Remotion、ChatCut Motion Graphics、ComfyUI MiniMax H3 等只负责计划指定的镜头/动效资产。HyperFrames 或 Remotion 渲染出的镜头必须导入 ChatCut，不能因此改换主时间线。
- **HyperFrames 主工程例外**：用户明确要求独立 HyperFrames 成片，或在 ChatCut 不可用时已接受替代路径，才采用；不能因单镜选用 HyperFrames 而改换主工程。仅做分析、分镜或素材清单时不创建任何剪辑工程。
- **阶段交付**：只做分析、分镜或素材清单时，完成对应交付后停止；局部修复只进入受影响阶段及其依赖检查。

## 核心制作约束

决策顺序固定为：理解文案与观众任务 → 确定 A/B 叙事职责 → 设计主体、关系、状态和旁白节拍 → 选择制作工具 → 制作资产 → ChatCut 组装 → 实际成片验收。工具选择不得反向改写叙事职责；H3 可制作 A-roll 人物叙事，也可制作 B-roll 解释性场景，HyperFrames/Remotion 同样按镜头需要使用。画风、情绪、角色和材质由每片 DESIGN 决定，具体案例的偏好不作为本 Skill 的默认画风。

- A-roll 讲人，承载态度、经历、情绪、动作和过渡；B-roll 讲内容，承载概念、关系、步骤、比较和证据。人物视角、素材类型、表现形式和语义结构分别记录，字段以数据契约为准。
- A/B 按观众的主要理解任务判断，不按语法主语、人物是否出现或画面是否有文字划分，也不固定配色、时长比例或交替节奏。A-roll 可让文字成为人物操作的道具，B-roll 可让人物指示、操作或回应信息；是否成立取决于主次与解释收益。禁止把与人物/叙事无关的信息卡直接贴到已有 A-roll 上；允许按同一镜头重新设计构图、节拍和互动后合成。具体判断与制作关系见 [DESIGN](references/design-system.md)，真实截图/录屏保留原色。
- 每镜先确定需要自然连续动作、刻意的定格状态切换、程序化信息动效还是有理由的静止，再选制作工具。人物/场景连续动作适合按需使用 ComfyUI 视频工作流；定格动画优先评估独立状态图与时间线节奏，需生成帧间动作时再评估视频生成，信息动效仍用适合精确排版和旁白节拍的工具。不能把“所有视频都走 ComfyUI”或“所有状态图都要插帧”当作默认规则。
- A-roll 支持生成式连续视频、程序化/分层动画、状态序列及有理由的静止；不因 A-roll 身份限制为图片，也不因使用视频改判 B-roll。`fixed-character-micro-scene` / `full-ai-scene` 管人物与场景组织，不限定运动方式；同片各镜可按语义选择不同运动方式并保持 DESIGN 一致。新图片/首尾帧仍使用内置 GPT，后续视频生成沿用逐镜路由，两者职责分开。
- 先阅读全文，按完整语义分段，不按单条字幕或固定秒数机械切镜。连续三镜以上同类画面写明语义理由，并改变视角或信息结构。
- 每个 B-roll 语义段必须先确定一个能表达本段关系的具体 `visual_structure`，例如文档组装、双栏对比、问题雷达、经历桥、判断天平或学习循环；不能把“深色背景、三张卡片、列表”当作所有知识段的默认答案。统一的是配色、字体、材质和标注系统，变化的是空间关系、阅读路径和动作语法。
- 选择 B-roll 结构前对照最近三个 B-roll，审查复用的解释收益，不以重复本身否决。核心图递进、同维度案例比较和结尾回顾可保持布局；在 `broll_structure_exceptions` 记录理由与内容推进或回顾用途，不能靠改名冒充新结构。
- 每片只选一种主画面生产模式，重复人物、标志性物体和视觉世界保持一致。人物身份与视觉系统独立记录、审核；`character-identity` 不自动授权复制背景、字体、版式和动效。
- 主画面重心稳定、构图封闭，关键人物、道具和线条完整收在画布内。动作与信息变化跟随旁白，不用装饰循环代替叙事。
- 保留 SRT 原文和时间，语义边界落在 SRT 边界上；MP3 决定总时长。开头静音显示首镜稳定帧，镜头间字幕空隙保持上一镜，尾部保持末镜。
- 字幕由主时间线统一管理，镜头资产不重复烧录字幕，保留配置化安全区。默认不重写文案、不重新配音、不做声学对齐。
- 关键动作按需配简单音效，强化材质、重量与因果；分镜标记声音意图，制作时对齐实际动作帧，在主时间线独立放置并以旁白清晰为先。不要每次文字出现都配声；BGM 与复杂声音设计仍按用户要求添加。执行与验收见 [sound-design.md](references/sound-design.md)。
- 不编造产品界面、数据、案例、截图或引用。缺失真实素材时登记请求并暂停该镜头的真实性实现，继续无依赖镜头。
- 时间轴和动画必须确定、seek-safe，不依赖刷新顺序、实时随机数或播放历史。
- 实际导出文件必须经过全片逐帧黑闪扫描，并人工核对异常帧与前后画面；编辑器预览、导出成功和稀疏抽帧不能代替成片检查。每次重导或补帧后独立复检，执行细则见 [qa.md](references/qa.md) §6。
- JSON 是真源，Markdown 是派生视图。修改 JSON 后同步可读版本；只重做未通过或已过期资产，单纯文字、布局、时间调整不默认重新出图。

## 阶段与交付

默认依赖顺序：预检 → 内容理解与分镜 → 视觉基线 → 资产与动效 → 主时间线与样片 → 全片验收。续做时从有效状态继续；按当前阶段运行必要检查，通过后仅因输入变化、失败或未解决问题重跑。

### 1. 预检

仅新任务可运行 `scripts/init_project.py`；已有任务只补缺失真源。新任务的样片区间写入 `config/project.json`，`--sample-end-ms` 默认 45000ms；能读到音频时长时，超过音频长度的区间自动收敛到音频时长，短音频无需手工改默认值，收敛与未探测到音频时长都会在初始化输出中提示。运行 `python scripts/preflight.py --srt <path> --audio <path> --out-dir <project>/planning`，检查编码、时间顺序、重叠、空字幕、音频时长和末尾偏差，交付预检报告。输入未变化且已有有效报告时复用。

现有 ChatCut 项目按执行引用只读盘点身份、规格、字幕、轨道、素材池、已放置镜头及可复用计划，保存 `planning/project-inventory.json/.md`。完成盘点前不得替换素材。

### 2. 内容理解与视觉编排

提取主题、主张、章节、论证、情绪和结论，合并相邻字幕为完整语义段，写清观众理解点和未经原文支持的推断，保存内容分析。仅要求分析时在此交付；需要分镜时再使用 `visual-plan-v1`，保存 `planning/visual-plan-prompt.json` 并生成 `planning/visual-plan.json`。

每镜记录 A/B 职责、表现形式、构图、有效变化、衔接、来源、`visual_design.motion_intent`（动效方式及旁白触发/停留节奏）、`production.primary_tool`（该镜最终视觉资产的制作工具）、回退和素材缺口；`changes` 与 `narration_beats` 一一对应，节拍绑定原始 cue 起点与逐字短语。工具须在分镜阶段逐镜确定并写入 JSON，在七列表格之后的“逐镜制作路由”表中可读呈现。A/B 职责由叙事用途确定，H3、HyperFrames、Remotion 均不自动决定镜头职责；若以首尾帧驱动，首帧、尾帧、H3 workflow 和运动提示分别记录。程序化信息图 B-roll 选型按上表读取引用，先用 `validate_template_index.py`、`validate_semantic_map.py` 检查当前索引与语义目录，再运行 `select_broll_template.py` 保存逐镜选择报告，确定 `semantic_structure`、具体 `visual_structure`、`semantic_pattern`、`item_count`、模板和工具；选择时列出最近三个 B-roll 的结构签名并完成复用审查，需要外部研究时先完成研究记录与校验。尚未解决的项留在草稿或素材请求中，不伪造通过。

生成可审阅的七列表格：`镜头 | 时间 | 配音文案 | 画面类型 | 画面设计 | 动态变化 | 画面衔接`。编号从 `S001` 连续递增，时间用原始边界毫秒值，配音逐字保留。表后列出“需要补充的素材”“需要确认的视觉方向”“制作难度较高的镜头”，没有则写“无”。

```text
python scripts/validate_plan.py --preflight <project>/planning/preflight-report.json --project <project>/config/project.json --content-analysis <project>/planning/content-analysis.json --visual-plan <project>/planning/visual-plan.json --out-dir <project>/planning
python scripts/render_plan_markdown.py --plan <project>/planning/visual-plan.json --out <project>/planning/visual-plan.md
python scripts/validate_plan_markdown.py --plan <project>/planning/visual-plan.json --markdown <project>/planning/visual-plan.md
```

再按数据契约 §8 运行 `validate_prompt_usage.py --stage planning`。计划与可读视图校验通过并按审核模式记录结果后，才能进入视觉基线与生产；在此之前不创建 ChatCut 项目、不导入素材、不生成图片/视频/动画、不导出。仅要求分镜时在此交付，不继续生成资产。

### 3. 视觉基线

读取 [设计真源与角色互动](references/design-system.md)，使用 [DESIGN 模板](templates/DESIGN.md)。已确认且适用的规范直接复用；新方向先以真实文案审阅代表 A/B、角色互动和高信息量镜头的开始/变化/结果，再完成带口播短片验证。设计、计划、选型和提示词绑定同一 design_ref，运行 validate_design.py；不预设账号最终画风，不把自检当用户确认。

建立视觉系统规范；有重复人物或用户要求的 IP 时再建立相应人物身份规范。确定构图安全区、B-roll UI token，并制作典型 A/B 画面。用户要求原创 IP 但没有参考图时，先按其设计要求用默认图片工具制作候选基准图，经过既有视觉基线审阅后才把选定版本登记为身份参考，不自行将候选图提升为身份真源。已有单张获准的人物身份参考、且需要规范化重复人物时才使用 `character-turnaround-v1`，保留 `prompts/character/` 实例；已有核实三视图不重复生成。普通重复人物的身份规范不等于用户要求设计 IP。对实际使用的重复人物逐项核对发色、发型、头身比例、服装和标志物。

人物身份与视觉系统分别记录参考范围、批准状态和哈希。只改信息卡、配色或动效不使人物身份自动失效；人物真源改变使依赖它的 A-roll 与角色参与的 B-roll 过期。计划和必要视觉基线通过后才新建 ChatCut 项目。

### 4. 资产与动效

按对应章节保存 `prompts/a-scenes/<shot-id>.json`、`prompts/b-scenes/<shot-id>.json`，需要时派生 Markdown。进入镜头资产制作前运行 `validate_prompt_usage.py --stage prepared`。先生产人物/风格参考，再生成依赖它的 A-roll；无依赖的 B-roll 可并行准备。

A-roll 使用画面与动作序列提示词，固定人物再使用视角提示词。`action_sequence` 原样继承计划节拍，数量由语义决定，不按时长凑动作。单状态需计划 `static_reason` 并在实例中继承；多状态逐项保留资产或连续动画证据。以简洁人物处境为主，按语义选择视角、动作、景别和场景关系。

B-roll 使用 `motion_sequence` 原样继承计划节拍；生成场景保存工具与参考素材选择依据，程序化信息图复用编排阶段已通过的索引检查、选型、结构复用审查和研究记录；候选、输入或约束变化时才重新选择。已核实素材优先复用。合格模板具备预览、来源、明确动作阶段与质量批准；无合格模板按外部研究门选择唯一来源，记录许可证、原框架和兼容性，只做允许的最小适配。候选均不适合时，记录拒绝理由和吸收的运动原则后才自建；目录无候选才研究未索引仓库。未声明许可证的公开代码只允许抽象结构研究。生产时不得把已批准的结构重新退化成通用列表、三卡或同构容器。

程序化镜头记录 `production.runtime_decision`；只有代码模板/动效实现层的新制作默认 HyperFrames，合格成熟效果可在原框架制作。Remotion 与 HyperFrames 按逐镜候选、表达、节拍和运行条件选用，不要求整片同时使用两者。需要生成连续场景动作或有用首尾帧约束的镜头，可按 [ComfyUI 视频资产生产](references/comfyui-video-production.md) 评估 MiniMax H3；其生成镜头沿用计划中的 A/B 职责并导入 ChatCut。有意设计的定格动画可使用状态序列，或在设计确需首尾帧生成时使用相应 H3 workflow；在 `motion_intent` 中写清跳变/连续运动的选择及原因。条件相近优先 HyperFrames，移植需具体依据。来源实现失败时回退到另一个已记录候选并重新确定唯一来源，不拼接多个骨架。仍失败则记录缺口，继续其他镜头；静态 SVG 只能是动画组件，不能冒充完成动效。

所有新图片与编辑（包括 IP 候选、三视图、A/B 状态图和视频首尾帧）先执行 [出图停止规则](references/image-generation-policy.md)。指定内置出图能力不可用时立即停整条工作流，保留已有产物并提示，不自动降级。若镜头选用 ComfyUI 连续动作，首尾状态图仍受同一出图门约束；从同一已核实身份/场景参考建立，优先由首帧编辑尾帧，检查人物、服装、背景、机位、画幅和计划动作的一致性。图片通过检查并登记后，才能作为 A-roll、B-roll 或视频首尾帧输入。

逐项记录提示词、模型、参数、版本、来源和校验结果。工具或选型变化回写计划、重生可读视图并复核受影响门控。

### 5. 主时间线与样片

以 MP3 为主音轨，按计划构建确定性时间轴。ChatCut 路径把音频、字幕、A/B 资产、真实素材与各框架渲染结果导入同一项目，按镜头边界放置；B-roll 区间必须有对应信息表达。

落实分镜中计划的动作音效，按实际接触、启动或落定帧对齐有效起音，检查与源声音是否重复。样片需带原旁白和已计划音效试听；在时间线审计和 QA 中记录实际素材、同步位置与声音检查结果。

选择包含 A、B、完整切换、一致性样例和典型信息动效的 30–60 秒样片；全片不超过 60 秒时可用整条低成本预览。按 QA 检查结构、视觉、音画与实际使用的框架产物，修复后按审核模式继续。视觉基线稳定且样片通过后再扩展高成本批量生产。

### 6. 全片与验收

沿用有效基线完成全片，低成本预览后按 [qa.md](references/qa.md) §6–7 逐镜检查、按 B-roll 出现顺序复查视觉结构重复、审计节拍到实际 item/asset 的映射并导出。ChatCut 路径由 ChatCut Desktop 导出最终 MP4。每次导出或修复后运行 `scan_video.py`，复核候选并把报告哈希绑定到 QA；交付前运行 `validate_state.py`、`validate_prompt_usage.py --stage produced` 和 `validate_delivery.py --mode review`，批准后运行 `--mode final`。样片批准须绑定当前依赖快照，实际命令见 QA §5、§7。

报告按 [ChatCut 执行流程](references/chatcut-production.md) §5 和数据契约 §7 记录实际资产、每镜使用的 `prompt_id` 与提示词实例、来源、工程/渲染路径、时间线 ID、最终绝对路径与剩余缺口。计划、静态预览或仓库链接不能冒充已完成资产。

## 阻塞与完成标准

指定内置出图能力不可用时，执行全局停止门：保留产物并提示，停止整个视频工作流，包括无依赖镜头。其他输入不可读、时间冲突、全片方向冲突、所需审核未通过或实现与声明回退均失败时，保留产物、说明原因和受影响阶段，按影响范围继续无依赖且已授权的工作。缺失真实证据只阻塞对应镜头；不得以占位或虚假批准绕过。

完成标准按本次任务范围判断：分析交付内容分析；分镜交付通过对应检查的 JSON、七列表格、提示词记录及缺口；素材/样片交付实际文件、来源与适用 QA。完整成片须满足 QA §6–7，保留输入、配置、计划、提示词、研究记录、资产、源工程、样片、报告和 manifest；无关阶段不要求补做。

最终 MP4 必须存在且可验证，时长误差不超过 `max(1 帧, 50ms)`，所有镜头通过 QA，状态绑定当前真源哈希，来源可追溯。`review` 通过只证明候选可审；按审核模式记录 `approvals.final` 且 `final` 校验通过才称最终批准交付。历史样片和报告绑定已作废基线时仅作为历史证据。

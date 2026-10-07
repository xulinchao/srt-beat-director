# 按视觉表达选择动效

> 主流程见 [production-prompts.md](production-prompts.md) §6。本文件区分创意路径与实现选型；字段以 [contracts.md](contracts.md) 为准。

所有 B-roll 先完成下方表达决策；后续简报、选择器与代码来源规则用于程序化选型。文案主题、框架名称和“比较/因果”等粗标签不能单独决定模板。

## 两条创意路径，共用一份分镜

先盘点本段的信息单元、实际素材及缺口，继承用户已确定的 IP、风格和讲解需求，再选择路径；同一片可以混用，同一镜可以迭代比较。

| 路径 | 适用情况 | 工作顺序 |
|---|---|---|
| 成熟表达借鉴 | 枚举、比较、步骤、图片展示等常见理解任务 | 盘点内容 → 查看具体动态候选 → 比较关系、容量和阅读顺序 → 代入本片内容与风格 |
| 内容驱动设计 | 特定空间、人物处境、结构拆合或故事关系 | 盘点内容 → 设计主体关系、必要状态与结果 → 用相关动态参考检查并改进表达 → 选择实现 |

内容驱动设计可以直接开始，不以模板搜索失败为前提。两者都要比较表达收益；明确适配的简单镜头无需硬凑两个方案，需要取舍时写明被舍弃方案及原因。参考不足时可交付标明缺口的提案，不能声称已验证成熟效果。

创意路径不等于工具路线：两者均可采用现有视频、图片状态序列、H3、程序化动画或混合镜头。自然动作和空间情境可优先评估 H3；精确文字、数量、位置与指示关系由可控图层保证。H3 不要求先证明代码动画失败，也不因“要动”就成为默认选择。自建程序化实现仍遵循后文来源研究门；它限制实现前的证据，不限制先提出原创观看方案。

### 分镜必须说清的内容

沿用现有字段，不增加第二份时间表：在 `visual_design.elements` 写出实际图片/物件与讲解文字原文，注明素材身份、对应关系及缺口；`character_role` 写 IP 在本镜的职责或不出现的理由；`motion_intent`、`changes`、`final_state` 写出进入顺序、当前强调、前项是否保留、结束画面以及从哪一状态保持到哪一原始旁白锚点或镜头结束。需要更细动作时使用现有 `motion_check.required_states`，不伪造 cue。

讲解文字承担命名、比较、关系和结论，区别于逐字字幕；没有必要时可明确写“无需讲解文字”，不能整片默认省略。阅读保持是表达的一部分，停留期间不再移动需要阅读的主体。图片依次展示可以成立，但必须说明观众逐项看什么、如何比较、看完后留下什么。

设计提案可保留未决项；可执行分镜须完成上述决定及逐镜工具依据。检查方法见 [分镜门](qa.md#2-分镜门)，结构脚本通过不代表表达已完成。

## 0. 先发现动作，不要求导演凭空发明动效名

`expression_brief` 是**选定表达后的检索输入**，不是创意起点。只给一段文案就要求先写 `main_motion` 和 `motion_tags`，会迫使代理用自己熟悉的淡入、框线或临时 SVG 填空。先用旁白与真实材料回答四个问题：观众此刻在问什么；可供观看的原始资料/物件是什么；资料中哪一处支持下一句话；镜头结束时观众应能亲自看见什么变化。若没有可核实的原处，就不能用“从原资料框选提取”的表演制造证据感。

按所选创意路径浏览实际演示或先拟观看方案，例如比较“在原处定位→放大细看”和“同位替换→比较差异”。从镜头卡的适用情境、意图和阶段寻找相邻骨架；题材和原配色不是筛选条件。拟定主要动作后填写 `subjects`、`element_relation`、`main_motion`、`phase_order`、`invariants`、`motion_tags` 和 `search_queries`，运行选择器并据实际预览修订。来源在候选审阅后确认，不要求检索前已找到来源。零命中或只有同类卡片，不能说明没有合适动作；空模板索引也不能称为已有成熟库。

### 例：鼠标框出资料，资料从选区出现

这不是“加个矩形”的装饰。它表达的是**原处定位 → 证据提取 → 保留出处 → 得出解释**。先展示能辨认身份的原页或照片；光标拖出只覆盖有依据的区域；框定后该区域以同一内容放大到阅读区，原处仍可被看见；观众读完证据再出现解释句。选区、放大件和解释必须指向同一个事实。若只是概念示意、没有真实可选的原始区域，改用物件拆解或文字关系动画，不伪造鼠标操作。

本地 `video-shotcraft` 副本没有查到上述完整顺序的单张镜头卡。相邻参考有 `cursor-flyover`（光标与相机同步定位）、`scanline-annotate-focus`（原页区域被定位后标注）、`canvas-materialize-moves` A 式（已有内容离开原容器并成为新实体）和 `doc-park-left-pill-deal`（原文驻留，解释逐条出现）。它们各自解决一部分问题，不能把四张的动作阶段拼起来冒称“复用一张模板”；要做完整拖框提取，应按外部研究记录评估后走自建，先用真实资料做短预览，再验出处连续性、阅读时长和本片画风。仅需在原页中找一处时，可优先评估 `scanline-annotate-focus` 的定位骨架，但不强行加入扫描线或光标。

### 列表、数字和文字先拆信息，再选动作

分镜前逐字核对本段旁白，列出观众必须看见的信息单元：每个条目、数字及其单位、两项之间的对应关系、出处和最后的判断。分别标记“需要出现在画面”“可以由口播承担”“缺真实素材暂不能展示”。`item_count` 应反映真实单元数，不能把整段文字算成一个标题；`changes` 与 `narration_beats` 说明它们在哪一拍进入或改变，制作时逐一映射到 `motion_sequence`。并非每个字都要上屏，但删去一项不能让观众错过本段要证明的关系。

| 文案中的理解任务 | 可比较的观看动作 | 结束时必须看见 |
| --- | --- | --- |
| 依次列出步骤、材料或证据 | 逐项落位并保留前项；沿同一路径依次点亮 | 条目顺序、各自内容和整体关系 |
| 数字说明规模或差异 | 数字与它修饰的物件同位出现；按单位展开或并置比较 | 数字、单位、所指对象和结论 |
| 原文支持一个解释 | 原处定位后放大可读内容；原文驻留，解释随后出现 | 观众能回到原文判断解释从何而来 |
| 两种说法冲突或版本变化 | 同位替换、前后对照或差异逐项显露 | 哪一处不同，以及改变了什么判断 |

本地 `video-shotcraft` 可从动作卡开始实看：`list-reveal` 是条目逐项落位且最终保留全表；`doc-park-left-pill-deal` 是原文驻留、结论逐条出现；`ai-stream-response` 是摘要先到、证据行随后汇入，只有确实适合“先给结论再补证据”的叙述才用；`picker-carousel-feature-cycle` 一次聚焦一项，适合逐个选择，不适合必须同时比较的清单。它们的原始 UI 皮肤、项数和节奏不自动适合本片；按真实文案、画幅和 DESIGN 看演示并检查中文容量。数字图表不能因有数字就套 `hatch-depth`：该卡表达的是占位图转为实时数据，与史料中一个确定数量的语义不同。

列表本身可以是正确结构，不因“不能默认通用列表”而禁用。需要列表时，先建立容器和阅读顺序，再按口播逐项进入；当前项有清楚的注意力重心，已出现项保持可回看，最后给全表稳定停留。几项落在同一个 SRT cue 时，可在该 cue 内错峰显示，但不虚构额外旁白节拍。若时间不足以读完，就拆镜、精简上屏文字或让口播承担次要项，不能把全部内容一闪而过。验收抽取每项出现前、出现时、全表落定三种状态，检查文字、数字、对应物、层级、间距和停留；标题有动效而条目缺失，判为信息未覆盖。

## 1. 写清动作，再检索

新编排在 visual-plan.json 根节点写 `broll_matching_policy="expression-first-v1"`。每镜把以下简报保存为 `planning/template-selection/<shot-id>-expression.json`，并通过选择器的 `--expression-brief` 传入；选择报告保存同一对象，不额外维护一套分镜。

```json
{
  "subjects": ["两块桃木板", "板上的文字"],
  "element_relation": "两块木板位置固定，文字附着在板面",
  "main_motion": "木板翻面，神名被联语替换",
  "phase_order": ["建立神名", "翻面替换", "联语落定并保持"],
  "invariants": ["两块木板的中心位置、尺寸、材质与统一背景保持"],
  "motion_tags": ["content-flip"],
  "search_queries": [
    "flip two cards to reveal different text while keeping their positions",
    "front back face rotation reveal with a settled readable result"
  ]
}
```

subjects 记录当前内容；搜索查询描述动作，不要求参考也谈桃符。motion_tags 是明确的动作特征，优先沿用候选已有名称，例如 content-flip、same-position-replacement、quantity-count、object-aggregation、split-and-place、progressive-reveal。不能填“桃符/文化/高级/国潮”等题材或审美词。

选择器先扫描统一候选语料，按 BM25、显式动作标签和可选真实向量召回，用 RRF 融合排序，再核对显式约束。关系、核心动作、阶段和不变量均进入检索描述；词汇相关不等于关系成立，向量相似也不保证阶段顺序正确。无向量缓存时明确使用离线检索，不自动判定自然语言关系或美感。候选缺少能力元数据时记为未知，继续看预览与源码，不凭粗标签宣布匹配。

本镜有必要时在简报加入 `requirements`，例如 `{"preserves_position":true,"preserves_carrier":true}`；检查列表可用 `retains_previous`、`final_overview`，证据镜头可用 `retains_source`。完整键见 contracts §6。同位内容替换与载体替换分别核对 preserves_carrier、preserves_content；不把皮肤相近当成关系匹配。不要为提高分数填写不必要约束。

真实文献、截图或照片属于 `verified-media` 时，仍要为其展示动作做上述发现与比较；现有 `broll-external-research` 校验门只覆盖 `no-material + infographic`，不能把未触发该门理解为证据镜头已找到合适动效。保留原件身份、选区依据及实际预览，在逐镜选型报告中记录动作适配判断。

```text
python scripts/select_broll_template.py --index <project>/templates/template-index.json --project <project>/config/project.json --semantic-structure replacement --item-count 2 --duration-ms 8000 --aspect-ratio 16:9 --material-type no-material --presentation-type infographic --semantic-map references/semantic-template-map.json --external-sources references/external-broll-sources.json --visual-style <project>/config/visual-style.json --expression-brief <project>/planning/template-selection/S001-expression.json --out <project>/planning/template-selection/S001.json
```

传 `--project` 读取 `config/project.json` 的 repositories_root，也可显式使用 `--repositories-root`。未配置时报告检索未执行；配置路径不存在时报错，不能把环境问题记录为“已搜索但没有候选”。

选择器返回 `candidates-recalled` 时，`selected` 仍为 null；融合排名、matched_keywords 和 constraint_fit 只帮助决定先看哪些候选。实际查看后，按 [外部骨架研究门](broll-external-research.md) 填写 `reference_confirmation` 并运行研究校验；未确认来源或转为 `new:<id>` 时，仍走完整研究记录与扩大搜索。`framework` 来自参考仓库：video-shotcraft / remotion / remocn 为 Remotion，hyperframes / hyperframes-launches 为 HyperFrames，motion-canvas 系列保留 Motion Canvas 身份，但当前不走原生制作快路径。

### 检索执行与语义向量

离线默认路径无需第三方 Python 包：完整扫描各来源，统一描述；整词匹配去普通词，有限中英动作词表提供可解释扩展，简短动作描述的 BM25 权重高于长正文；与标签召回用 RRF 融合，并保留各来源的相关候选；已知显式约束冲突降为探索项。`match_basis=lexical` 是词汇相关，`motion` 是标签命中，`semantic` 仅在真实 embedding 缓存生效时出现。报告 retrieval.semantic.enabled=false 时，不得写“语义模型已匹配”。各来源描述与源码信息量不同，能力未知仍需实际查看；前三名不能机械凑确认。

需要真实向量时，先导出统一目录，再对已配置且已授权的 OpenAI 兼容 embedding 服务显式执行；无服务配置时继续离线路径，不自动安装模型、上传文件或调用计费接口。下列地址与模型名是占位参数，须换成实际配置：

```text
python scripts/build_broll_catalog.py --repositories-root <repositories> --semantic-map references/semantic-template-map.json --out <project>/planning/broll-catalog.json
python scripts/prepare_broll_embeddings.py --catalog <project>/planning/broll-catalog.json --expression-brief <project>/planning/template-selection/S001-expression.json --api-base <authorized-api-base> --model <embedding-model> --out <project>/planning/template-selection/S001-vectors.json
```

需要密钥时使用 `--api-key-env <变量名>`，不将密钥写进文档或参数值。向量脚本发送检索描述，属于实际外部调用；使用已有授权范围，本机服务也须明确配置。缓存按服务地址、模型与文本哈希复用；查询改变只重新计算查询，候选描述改变只更新受影响候选。选择器加 `--retrieval-vectors <project>/planning/template-selection/S001-vectors.json` 即启用第三路召回；过期查询和无效向量报错，候选描述过期跳过并提醒。目录描述不是认证证据，开始/变化/结果和带旁白预览仍决定最终适配。

## 2. 程序化实现：先核对复用，扩大搜索后才自建

1. 先检查已认证本地模板与本任务已经认可的镜头；后者可作参考，未经容量与 seek 验证不能冒充通用认证模板。
2. 按动作检查登记候选，跨语义类别、跨 HyperFrames/Remotion 找骨架；两个框架独立渲染素材进入 ChatCut，框架不作为画风。
3. 有合适来源时先看实际演示，再读实现和许可证，保留核心运动。原示例是产品卡片不构成拒绝理由：文字、图像、字体、配色与必要尺寸可以适配；改变对象关系或核心阶段才算改骨架。
4. 没有合适来源时，使用至少两种动作查询覆盖至少两个搜索来源。优先覆盖 HyperFrames catalog/示例与 Remotion 的具体开源实现；也可继续查已取得仓库中未登记的相关镜头。登记表只是起点，不能检查两个明显无关的候选就宣称无匹配。
5. 在研究记录 expanded_search 保存实际 source、query、outcome 和 candidate_ids。无结果用空数组；不可用写明实际错误，不把失败记为没有候选。发现的相关候选须完成评估；已登记来源可以从搜索进入比较，未登记来源放入 discovered_candidates，不需为单个视频扩写全局目录。
6. 只有扩大搜索后仍不适合，才使用 custom-after-external-review。拒绝理由须指出关系、动作、阶段或实际改造边界；“题材不同”“字号/颜色不同”“不是常用框架”不足以拒绝。自建仍先用真实素材做代表短片，与已认可基线比较，通过既有 QA 后再扩大制作。

选中来源有且只有一个。保留未选候选的评价，不混入它们的布局、easing 或阶段。已有连续制作授权继续适用，这些步骤是代理的研究和验证工作，不增加逐镜用户审批。

## 3. 图像、SVG 与文字的职责

- 主体物件和人物先按 DESIGN 选择真实素材、统一画法的生成图、分层透明素材或已验证图形组件，再决定怎样动。默认不以临时 SVG 几笔轮廓替代有质感的主体。
- SVG 用于合适的精确图表、路径、遮罩或辅助组件；要有具体参考、设计适配和解释收益。用户明确不喜欢 SVG 主体/描线动画时作为本片硬约束记录并执行；不能把同样的粗糙线稿改成 Canvas/CSS 就当解决。
- 文字动效优先作用于关键词、数量、关系和替换结果：逐字强调、计数、分组或内容替换应跟随理解任务；下划线、位置漂移和重复淡入不能充当默认方案。
- 卡片背景只用于确有意义的承载、分组或真实界面。来源/引用可以直接排版；不默认每段加底框、双边框、圈线和页脚。
- 删除内部制作说明、待核标签和重复标注。文献身份、生成示意与真实证据的必要区分仍保留；详细考据和制作记录放到交付说明，不占据每个镜头。

## 4. 真正检查画面

选中候选须保存实际演示/预览截图或视频的项目相对路径。结构明显不适配时可在源码阶段拒绝，不伪造“已预览”。结构合适但风格不同的候选，应先用本片真实文字与素材适配后检查，不因原始配色直接排除。

制作前比较开始、变化、结果三帧；代表短片带原旁白检查速度、重量、停顿和结果可读时间。按相邻镜头连看，逐项记录：

- 素材笔触、明暗、材质和细节精度是否同属一个系统；只统一背景色不算通过。
- 主体比例、文字层级、对齐、间距和留白是否有明确观看重心。
- 强调色是否标明当前重要信息，是否出现无解释收益的框、线、圈和小字。
- 每个关键动作是否使对象/关系发生可读变化，且开始状态、遮挡和落点正确。
- 中文居中、字距、换行、透明边缘、字体加载和跨框架接缝是否完整。

出现具体缺陷即返工受影响镜头。渲染成功、字段齐全、黑帧检测通过，不证明画面质量通过。自建连续出现时先复核检索范围与参考适配，并对照基线短片，不机械换布局或强塞模板。

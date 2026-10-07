# 文件与数据契约

## 1. 项目目录

每个视频使用独立目录。以下为首版稳定结构：

```text
project/
  input/
    source.srt
    narration.mp3
    references/
      index.json
    supplied-media/
  config/
    project.json
    visual-style.json
    character-bible.json
  planning/
    preflight-report.json
    preflight-report.md
    project-inventory.json
    project-inventory.md
    content-analysis.json
    content-analysis.md
    visual-plan.json
    visual-plan.md
    visual-plan-prompt.json
    visual-plan-prompt.md
    template-selection/
      <shot-id>.json
      <shot-id>.md
    broll-research/
      <shot-id>.json
    broll-research-validation.json
    broll-research-validation.md
    plan-validation-report.json
    plan-validation-report.md
    material-requests.json
    material-requests.md
  prompts/
    character/
    a-scenes/
    b-scenes/
  assets/
    a-scenes/
    b-scenes/
    verified-media/
    fonts/
  templates/
    selected/
    adapted/
    template-index.json
  hyperframes/
    source/
    timeline.json
  remotion/
    <shot-id>/
  preview/
    sample.mp4
    review-notes.md
  render/
    final.mp4
  reports/
    timeline-audit.json
    timeline-audit.md
    qa-report.json
    qa-report.md
    delivery-validation-report.json
    delivery-validation-report.md
    manifest.json
```

`character-bible.json` 仅在人物或重复角色存在时创建。不要制造空占位目录或文件；在对应阶段首次需要时创建。

`prompts/` 不是可选日志，而是生产提示词的实际使用记录。只有进入对应阶段时才创建实例文件；不能预先制造空占位。

`input/references/index.json` 为参考用途范围真源。每项至少记录：

```json
{
  "id": "ref-character-01",
  "path": "input/references/character.png",
  "roles": ["character-identity"],
  "allowed_influence": ["face", "hair", "body-proportion", "wardrobe", "signature-prop"],
  "forbidden_influence": ["global-palette", "background", "b-scene-ui", "layout", "motion-language"],
  "source": "user-provided",
  "identity_lock": {
    "hair_color": "",
    "hair_shape": "",
    "body_proportion": "",
    "wardrobe": [],
    "signature_elements": []
  }
}
```

允许的角色包括 `character-identity`、`visual-style`、`layout-reference`、`motion-reference` 与 `verified-media`。角色未声明即视为未授权；同一文件可以有多个角色，但必须显式登记。

`character-identity` 必须登记 `identity_lock`。生成的三视图和 `character-bible.json` 必须引用原始 `reference_id` 并复制同一份锁定字段；不得把生成图自行提升成新的身份真源。运行：

```text
python scripts/validate_references.py \
  --index <project>/input/references/index.json \
  --character-bible <project>/config/character-bible.json \
  --out-dir <project>/planning
```

## 2. 真源规则

新任务启用 `project.design_contract_version="1.0"`，新增 `config/DESIGN.md`。设计引用、继承、审批及逐镜互动字段的扩展契约见 [design-system.md](design-system.md)，模板见 [DESIGN.md](../templates/DESIGN.md)。旧任务显式迁移前保留兼容提醒，不自动改旧批准。visual-style 的 resolved_design 是派生参数快照，设计规则以 DESIGN 为准。

- `config/project.json`：项目级输入、输出、规格、模式和门控状态的真源；
- `planning/content-analysis.json`：全文结构和语义段的真源；
- `planning/visual-plan.json`：镜头与时间轴的真源；
- `config/visual-style.json` / `character-bible.json`：视觉一致性的真源；
- 启用 DESIGN 后，visual-style 管设计引用、审阅和执行状态；character-bible 继续管身份，DESIGN 管视觉规则，不分别维护重复参数；
- `input/references/index.json`：参考图片和素材允许影响范围的真源；
- `templates/template-index.json`：模板来源和能力的真源；
- `reports/timeline-audit.json`：计划节拍到主时间线实例的落实真源；
- `reports/qa-report.json`：画面、音画、裁切和编码检查的真源；
- `reports/manifest.json`：最终交付清单真源；
- 三者共享完全相同的 `final_artifact` 对象，并由 `scripts/validate_delivery.py` 交叉校验。

同名 Markdown 文件是派生的人类可读视图。不要分别维护两套内容；修改后以 JSON 重生成或同步 Markdown。

## 3. `project.json` 最小字段

```json
{
  "schema_version": "0.3",
  "project_id": "example",
  "inputs": {"srt": "input/source.srt", "audio": "input/narration.mp3"},
  "output": {"directory": "render", "filename": "final.mp4"},
  "video": {"aspect_ratio": "16:9", "width": 1920, "height": 1080, "fps": 30},
  "primary_timeline": "chatcut",
  "review_mode": "manual",
  "sequence_review_policy": "sequence-quality-v1",
  "sequence_review": {"sample": null, "full": null},
  "chatcut": {"project_id": null, "project_name": null, "timeline_id": null},
  "a_scene_mode": "fixed-character-micro-scene",
  "subtitle_safe_area": {"bottom_fraction": 0.22},
  "timeline_policy": {
    "initial_gap": "show-first-shot",
    "inter_shot_gap": "hold-previous-shot",
    "tail_gap": "hold-last-shot"
  },
  "sample": {"start_ms": 0, "end_ms": 45000},
  "status": {
    "plan": "draft",
    "visual_baseline": "pending",
    "sample": "pending",
    "final": "pending"
  },
  "approvals": {
    "plan": {"sha256": null, "approved_at": null, "review_source": null},
    "visual_baseline": {"sha256": null, "approved_at": null, "review_source": null},
    "sample": {"sha256": null, "approved_at": null, "review_source": null, "artifact": null},
    "final": {"sha256": null, "approved_at": null, "review_source": null}
  },
  "final_artifact": null
}
```

允许值：

- `a_scene_mode`：`fixed-character-micro-scene`、`full-ai-scene`；
- `primary_timeline`：`chatcut`、`hyperframes`；完整视频默认 `chatcut`。用户明确选择独立 HyperFrames 成片，或在 ChatCut 不可用时已接受替代路径，才使用 `hyperframes`；单镜工具选择不能改变此字段；
- `review_mode`：`manual`、`continuous`。`continuous` 只在用户明确要求自检后继续时使用，不等于预先批准计费、发布、账户或系统权限；
- `review_source`：通过门控时记录 `user` 或 `agent-qa-under-user-authorization`。后者只允许在 `review_mode=continuous` 时使用；不得把代理自检记录成用户确认；
- `chatcut`：仅在 ChatCut 路径使用。`project_id`、`timeline_id` 必须来自实际工具读取，不能凭名称猜测；
- 计划、基线和样片状态使用 `draft`、`pending`、`pending-user-review`、`approved`、`stale` 或 `not-required`；最终状态使用 `pending`、`rendered-pending-user-review`、`approved` 或 `stale`；
- 修改影响内容或视觉基线的真源后，将下游状态标记为 `stale`。
- 每次批准绑定当前真源或样片的 SHA-256；修改被绑定文件后，不能沿用旧批准。
- 镜头 `start_ms`/`end_ms` 描述语义边界。字幕前、镜头间和尾部空隙按 `timeline_policy` 补齐到完整音频时长，不能让合成器自行猜测。
- `final_artifact` 在未导出时为 `null`；导出候选存在后使用第 7 节的统一对象。手动审核下，技术闭环通过只把最终状态写成 `rendered-pending-user-review`，不能代替用户批准。
- `repositories_root`（string | null）：本地参考仓库根目录的绝对路径。B-roll 选型时 AI 可读取该路径下的实际源码和 demo（如 video-shotcraft 镜头配方卡、hyperframes-launches 合成示例）。未配置时只搜索本地模板库。示例：`"i:/Project/srt-beat-director/research/reference-repos"`。由 `init_project.py --repositories-root` 写入；
- `design_contract_version`（string）：设计规范契约版本号。当前固定 `"1.0"`；
- `video.status`（string）：视频规格来源。枚举值：`"user-specified"` | `"detected"`；
- `chatcut.timeline_name`（string）：ChatCut 主时间线名称；
- `a_scene_mode_status`（string）：A-roll 场景模式状态；
- `status.character_identity`（string）：人物身份规范状态；
- `approvals.sample.dependencies`（object | null）：样片审批时的依赖快照。详见 §9。

## 4. `content-analysis.json` 最小字段

```json
{
  "topic": "",
  "core_claim": "",
  "sections": [],
  "argument_flow": [],
  "emotional_arc": [],
  "conclusion": "",
  "semantic_segments": [
    {
      "id": "SEG001",
      "cue_ids": [1, 2],
      "start_ms": 0,
      "end_ms": 5200,
      "verbatim_text": "",
      "viewer_takeaway": "",
      "rhetorical_role": "setup",
      "forbidden_inferences": []
    }
  ]
}
```

## 5. `visual-plan.json` 最小字段

`planning/visual-plan.json` 是镜头和时间的机器真源，但不能替代对用户的可读交付。由它生成的 `planning/visual-plan.md` 必须包含且只能以如下七列作为视觉编排表主体：

```markdown
| 镜头 | 时间 | 配音文案 | 画面类型 | 画面设计 | 动态变化 | 画面衔接 |
|---|---|---|---|---|---|---|
```

其中“画面类型”使用用户可读的五类名称：`人物画面`、`场景画面`、`真实素材`、`信息图形`、`文字动效`；A/B 职责、素材子类型、语义结构、工具和风险保留在 JSON 或表格后的补充检查中。保持七列表格稳定，表格之后增加由 JSON 派生的“逐镜制作路由”表，逐镜列出 A/B 职责、动效方式、主制作工具和工具决策依据/辅助链路；不能只在计划 JSON 中隐藏工具选择。镜头 ID 必须从 `S001` 连续递增，时间必须显示为毫秒，配音文案必须来自 `verbatim_text`，不得改写。路由表之后固定输出“需要补充的素材”“需要确认的视觉方向”“制作难度较高的镜头”三个部分；无内容时写“无”。

```json
{
  "schema_version": "0.1",
  "broll_structure_exceptions": [],
  "shots": [
    {
      "id": "S001",
      "start_ms": 0,
      "end_ms": 5200,
      "cue_ids": [1, 2],
      "verbatim_text": "",
      "viewer_takeaway": "",
      "screen_role": "A",
      "screen_subtype": "micro-scene",
      "material_type": null,
      "presentation_type": "character",
      "a_view": "protagonist",
      "semantic_structure": null,
      "semantic_pattern": null,
      "visual_structure": null,
      "item_count": null,
      "visual_design": {
        "subject": "",
        "composition": "",
        "shot_scale": "medium",
        "elements": [],
        "final_state": "",
        "motion_intent": "说明该镜的动效方式、旁白触发点及状态停留/转变；静止镜头说明静止理由"
      },
      "changes": [
        {"at_ms": 0, "event": "主体发生可见变化"}
      ],
      "narration_beats": [
        {
          "cue_ids": [1],
          "at_ms": 0,
          "trigger_text": "逐字来自绑定 cue 的连续原文",
          "information_change": "这一短语触发的新信息",
          "state_after": "变化后观众能读到的状态"
        }
      ],
      "transition": {"from_previous": "", "to_next": ""},
      "materials": [],
      "production": {
        "primary_tool": "existing-media",
        "fallback_tools": [],
        "asset_status": "available",
        "asset_gap": null
      },
      "template_id": null,
      "broll_research_record": null,
      "risk": [],
      "status": "draft"
    }
  ]
}
```

`screen_role` 只允许 `A` 或 `B`。A 的子类型由项目级主画面模式约束；B 的 `material_type` 使用 `verified-media`、`no-material` 或 `text-only`，`presentation_type` 使用 `verified-media`、`infographic`、`text-motion` 或 `scene`。生成式解释场景使用 `material_type=no-material`、`presentation_type=scene`、`screen_subtype=scene`，`template_id` 可为 null；生成素材不能标为 verified-media。生成场景保留理解点、语义结构、状态节拍及生成证据，不强制走代码模板研究门。旧字段 `screen_subtype` 只保留画面实现类别，不能代替这两个映射字段。`start_ms` 和 `end_ms` 必须来自 SRT 边界。

`production` 记录计划如何落实，不替代画面语义字段：

逐镜制作路由表按 JSON 核对职责、动效方式和主工具。缺少 `motion_intent` 且没有 `static_reason`，或没有 `primary_tool` 时，渲染出的占位说明不能通过 Markdown 校验。旧计划按需补齐真实设计意图并重生视图，不改历史批准或伪造生成记录。

- `primary_tool`：该镜头最终视觉资产的主制作工具。允许值包括 `existing-media`、`gpt-image2`、`chatcut-image`、`chatcut-video`、`chatcut-motion-graphics`、`hyperframes`、`remotion`、`comfyui-minimax-h3-fl2v`、`comfyui-minimax-h3-i2v`、`comfyui-minimax-h3-r2v`、`comfyui-minimax-h3-multi-reference`、`comfyui-qwen21-t2i`、`comfyui-qwen21-edit`、`comfyui-qwen21-multi2`、`comfyui-qwen21-multi4`、`comfyui-qwen21-multi6`、`comfyui-qwen-edit-2509`、`comfyui-qwen-edit-2509-faceswap`、`comfyui-qwen-edit-masked`、`comfyui-qwen-edit-multi`、`comfyui-qwen-edit-multi-hq`、`comfyui-z-image-base`、`comfyui-z-image-turbo`、`comfyui-crop-image` 或具体的其他可用工具；
- `fallback_tools`：仅记录允许回退的制作路径，不能把无关静态图作为动态镜头的默认回退；内置出图工具不可用时必须全局停止，图片路由使用空数组，不登记替代出图工具。不限定 GPT 的具体模型版本，执行前按 [出图停止规则](image-generation-policy.md) 核实内置出图能力；
- `asset_status`：`available`、`to-generate`、`in-progress`、`ready`、`failed`、`gap`；
- `asset_gap`：没有缺口时为 `null`，有缺口时写清缺少什么、为什么无法继续该镜头和是否影响全片导出。
- `video_generation`：ComfyUI 视频镜头的 workflow、首帧、尾帧（fl2v 必填）、运动提示词、输出规格、任务 ID、输出路径和实际帧证据；字段契约见 [comfyui-video-production.md](comfyui-video-production.md)。
- `image_generation`：ComfyUI 本地图片镜头的 workflow、输入图或 mask、提示词、seed、输出路径和结果证据；字段契约见 [comfyui-image-production.md](comfyui-image-production.md)。
- 新制计划的每镜都在 `visual_design.motion_intent` 说明运动方式（定格状态序列、生成式连续动作、程序化信息动效或有理由的静止）、旁白触发点及停留/转变；定格动画写明状态图和跳变节奏。`production.primary_tool` 必须逐镜明确，七列表格后的路由表从该字段派生。H3 生成的视频镜头沿用已确定的 `screen_role`，A/B 均可使用；其首尾帧、workflow、运动提示、任务与成片路径写入 `production.video_generation`；其他工具链只作为该镜生成素材或渲染的实现步骤，不能因此改变 ChatCut 主时间线。
- 完整新制视频的 `primary_timeline` 默认 `chatcut`，例外条件见配置章节。`no-material + infographic` B-roll 可按逐镜计划使用 `hyperframes`、`remotion`、`chatcut-motion-graphics` 或合适的 H3 视频生成工具；HyperFrames/Remotion 的代码动效新制默认 HyperFrames，成熟模板可原生复用。A/B 两类镜头使用这两种代码框架时都必须填写 `production.runtime_decision`，字段和决策规则以 [制作工具决策](broll-runtime-selection.md) 为准。无论单镜工具如何选择，ChatCut 统一管理素材、字幕、声音、组装主时间线与导出。

连续三镜以上同一 `screen_role` 时，在计划根节点增加 `roll_run_exceptions`，逐段记录 `start_shot_id`、`end_shot_id`、`screen_role` 与非空 `reason`。理由必须说明为什么语义不可拆，以及连续镜头如何改变视角或信息结构；不能只写“节奏需要”。

- A-roll 固定人物模式必须使用 `a_view`：`presenter`、`protagonist`、`supporting`、`first-person`；
- 所有镜头的 `changes` 与 `narration_beats` 按顺序一一对应。每个 beat 的 `cue_ids` 必须属于当前镜头，`at_ms` 等于首个绑定 cue 的开始时间，`trigger_text` 逐字来自绑定 cue 的连续原文（可以是所有绑定 cue 的全文拼接，也可以是其中一个 cue 的连续片段）；不得事后凭感觉填写任意时间点，也不得跳词拼接非连续文本；
- A-roll 至少 1 个旁白语义节拍，数量不由时长决定。旁白节拍数量不等于动作状态数量：一个节拍可以包含进入、操作、接触和停住。仅选择 single-state 的静止实现必须填写非空 shot.static_reason；changes 与 narration_beats 仍保留对应的建立状态。显式运动方式与状态证据见 §10，装饰运动不计作叙事变化；
- static_reason 是镜头级条件必填字符串，七列表格在画面设计中显示。旧单状态计划需根据实际语义补写、重生 Markdown 并复核受影响审批；不得仅为通过校验复制空泛理由，也不自动批改历史工作区。生产提示词更新后按 §8 重建实际需要重新执行的实例，不替换旧哈希冒充已执行；
- B-roll 的有效阶段数服从已经批准的 `narration_beats`，每个阶段负责一次信息建立、关系改变、重点确认或结论落定；额外入场和尾部阅读保持不写成旁白节拍；
- B-roll 必须填写 `material_type`、`presentation_type`、`semantic_structure` 与正整数 `item_count`；
- `semantic_structure` 只允许 `comparison`、`aggregation`、`filtering`、`hierarchy`、`causality`、`replacement`、`expansion`；交叉特征写入可选的 `secondary_structures`；
- `semantic_pattern` 可写具体骨架模式，例如 `before-after-slider` 或 `true-boundary-vs-temporary-fatigue`；它辅助排序，不能代替标准主结构，也不限制按动作跨类别检索；
- 每个 B-roll 必须填写具体 `visual_structure`，描述观众可见的空间关系、阅读路径和核心动作，例如 `document-assembly`、`question-radar` 或 `experience-bridge`；`cards`、`list`、`infographic`、`dark-ui` 等笼统外观词不能单独满足该字段；
- 结构重复扫描按最近三个 B-roll 检查 visual_structure、模板与构图或语义模式与构图组合。匹配只产生 warning，不证明视觉疲劳；具体结构缺失或笼统名称仍是 error；
- 复用时在 broll_structure_exceptions 填写 shot_id、compared_shot_id、semantic_reason、visible_difference。后者可说明新增内容、重点变化或布局不变的回顾用途，不强制结构差异。未完整记录的近邻重复保留 warning，由人工 QA 处理；跨窗口复用也记录；
- B-roll 的 `materials` 必须能判断为现有已核实素材、待补素材或无需真实素材；
- `template_id` 只能使用以下路由：合格本地模板 ID、`external-research:<structure>`、`external:<candidate-id>` 或 `new:<id>`。
- `external-research:<structure>` 表示尚未完成研究，只能停留在规划状态，不能开始实现。
- `external:<candidate-id>` 有两条证据路径：外部来源引用已通过的 `broll_research_record`；配置的参考仓库来源使用 `candidates-recalled` 选择报告中的 `reference_confirmation`，其中 `confirmed_source_id` 必须等于 `<candidate-id>`，该镜 `broll_research_record` 留空。关键词分数只供召回，不能自动确认来源。
- 参考仓库确认记录包含 `confirmed_source_id`、`confirmed_file_path`（候选的绝对源码/镜头卡路径）、`preview_path`（项目内相对路径）、`motion_adaptation_reason`、`phase_adaptation_reason`、`native_framework` 和 `license_basis={license_id,evidence_path}`（其中 evidence_path 相对来源仓库）。校验会核对候选身份、文件存在且未越界、预览、框架和许可证依据；实际动作与画面适配仍须人工或代理观看判断。Motion Canvas 等尚无原生制作路由的来源只能研究或进入完整适配流程，不能冒称 HyperFrames。
- `new:<id>` 始终需要 `broll_research_record=planning/broll-research/<shot-id>.json`，决策为 `custom-after-external-review` 并满足扩大搜索契约。若选择器曾召回参考仓库候选，研究记录还须有 `reference_candidate_reviews=[{candidate_id,rejection_reason}]`，记录实际检查的候选与拒绝理由；不凭目录为空或分数低直接自建。
- `no-material + infographic` 没有合格本地模板时，选定参考仓库来源可用上述轻量确认；选定外部来源或自建时必须填写 `broll_research_record`。详细契约见 [broll-external-research.md](broll-external-research.md)。

## 6. 模板索引

跨项目入库还须在真实认证时绑定完整条目的 `template_sha256`、记录 `checks.portable=pass` 并绑定包内分发依据 `source.license_evidence`，使用 `scripts/promote_template.py` 先只读预检。字段及可移植包范围见 [模板沉淀流程](template-library.md)。不将入库校验当作新认证，也不补写旧通过记录。

新编排在 visual-plan.json 根节点写 broll_matching_policy="expression-first-v1"。程序化 B-roll 选择器必须传 --expression-brief；新选择报告 schema_version=0.2，保存 matching_policy、expression_brief、matched_motion_tags、match_basis、selection_warnings 和容量适配状态。`match_basis=semantic-only` 的候选只供进一步探索，不是动作匹配。简报字段与研究记录 schema_version=0.2 见 [按视觉表达选型](broll-expression-selection.md)及 [外部研究契约](broll-external-research.md)。动作相关候选可跨语义类别，目录为空仍需研究。选择报告状态只有 `local-match`、`candidates-recalled`、`external-research-required` 三种；未知状态一律报错。
`candidates-recalled` 报告用 `reference_confirmation_or_research_required_before_implementation=true` 表示二选一门；其 `research_record_required_before_implementation=false` 只表示参考仓库确认后可免完整研究，不允许未确认即实现。

选择报告新增 `retrieval` 描述 hybrid-rank-v1：统一候选描述上的 BM25（简短描述优先，整词与有限中英词表扩展）、显式 motion_tags 和可选真实向量通过 RRF 融合，不混加仓库原始分数；保留各来源的相关候选，再按显式约束排序。参考候选的 `match_basis` 可为 `motion`（标签命中）、`lexical`、`semantic`（真实向量）、`semantic-only`（仅粗分类探索），不代表已通过适配。`retrieval_scores`、`retrieval_ranks` 可解释各通道；RRF 分数不是百分比或成功概率。`matched` 只表示值得动态审阅，只有普通词交集或明确约束冲突时为 false。`review_required` 提醒对象关系、动作、阶段、不变量与动态预览尚需实际检查。

`expression_brief.requirements` 与候选/模板 `capabilities` 均为可选布尔对象，键限定为 `preserves_position`、`preserves_content`、`preserves_carrier`、`retains_previous`、`final_overview`、`retains_source`。requirements 只写本镜确实必要的约束；capabilities 只写已经核对来源卡或实现的能力，缺失为未知，不从自由文字猜测布尔结果。`constraint_fit={status,supported,conflicts,unknown}` 区分符合、冲突、待核；确认参考仓库来源时不允许已知冲突走最小修改快路径。需改变核心阶段或能力时走完整适配/自建流程。阶段顺序与自由描述的含义仍不由程序自动判定。

`--retrieval-vectors` 为可选 1.0 JSON：`model` 标明同一 embedding 模型；`query={expression_sha256,vector}` 绑定当前简报（排序键、无多余空白的 UTF-8 JSON SHA-256）；`candidates` 以 `source:id:absolute-path` 为键，每项含 `text_sha256` 和 `vector`。查询过期、无效向量或维度不一致报错；候选描述过期跳过该向量并提醒；无缓存时明确记录 semantic.enabled=false，不声称已用语义模型。详见 [检索执行](broll-expression-selection.md#检索执行与语义向量)。

新增验证模板应同时保存 `source_file`、短 preview、`element_relation`、`text_capacity`（中文每行字数/行数/最小字号及实际 `font_path`）、`animation_phases`、`replaceable_fields`、许可证与实际渲染/seek 验证证据 `validation_evidence`。后者是项目相对 JSON 文件路径，报告绑定源码、预览、字体及审阅证据的哈希，格式见 [模板沉淀流程](template-library.md)。目录存在或外部仓库登记不代表通过；改文案仍需容量与阅读验收。新条目写 `metadata_version="1.0"`，旧条目只保留兼容提醒，逐项补证后才升级。选择器 CLI 会先检查索引及认证证据，失效证据不能直接进入选型。

模板与外部候选可登记 motion_tags（非空动作特征字符串数组），用于跨语义召回，不替代实际预览和关系/阶段审阅。没有动作元数据的旧模板仅作待研究候选，不能凭粗分类在新表达选型中直接宣布复用。时长、项数、画幅不符合认证边界的动作相关候选保留为需适配参考；调整后重新检查，不能沿用原认证宣称验证通过。

每个模板至少记录：

```json
{
  "id": "comparison-01",
  "semantic_structure": "comparison",
  "item_range": [2, 4],
  "duration_ms": [3500, 9000],
  "aspect_ratios": ["9:16", "16:9"],
  "replaceable_fields": [],
  "animation_phases": [],
  "preview": "",
  "source": {"url": "", "license": "", "original_framework": ""},
  "runtime": "hyperframes",
  "animation_status": "animation-verified",
  "known_limits": []
}
```

`runtime` 使用 `hyperframes` 或 `remotion`，表示当前实现的运行框架，与 `source.original_framework` 独立。`animation_status` 使用以下状态；旧条目兼容 `hyperframes_status` 且缺少 `runtime` 时按 HyperFrames 处理。新条目不再用 HyperFrames 专有字段记录 Remotion 状态。

- `styleframe-only`：只有静态终态，不可作为可直接复用的动效模板；
- `implementation-required`：结构已选定，尚未在指定 runtime 完成实现；
- `animation-verified`：动画、seek-safe 和目标画幅均已验证；
- `superseded`：已过期，不参与匹配。

用 `scripts/select_broll_template.py` 匹配时，静态模板可以作为设计候选，但输出必须明确 `implementation_required=true`，不能声称“只替换文案即可”。

## 7. Manifest

最终 `reports/manifest.json` 至少列出每个输入、真源、采用的提示词、B-roll 研究记录、资产、模板、工程文件、样片、成片和报告的相对路径、SHA-256、来源或生成方式、版本与状态。派生缓存可记录，但不能替代真源。

清单统一使用非空 `files` 数组，每项为 `{path, sha256, source, version, status}`，后三项为非空字符串，路径必须位于项目内。逐项校验实际文件哈希，拒绝重复路径及 stale/rejected/failed/missing 项。至少登记输入、project/visual-style、内容分析、分镜及其提示词实例、逐镜提示词与实际输出、适用的选择/研究/布局证据、样片及依赖快照内文件、时间线审计及原始工程读取证据、QA/扫描和最终文件。程序化镜头在 `production.source_files` 填写所选 HyperFrames/Remotion 的项目内源工程文件路径数组，并登记到清单；仅列渲染 MP4 不算保留源工程。manifest 自身不登记自身哈希，以避免循环；交付校验报告在校验后产生，不要求预先登记。最终批准改变 project.json 后重新生成其清单哈希，再执行 final 校验，不改写历史审批。

```json
{"files": [{"path": "input/source.srt", "sha256": "实际文件哈希", "source": "user-supplied", "version": "1", "status": "current"}]}
```

ChatCut 路径的 manifest 还要记录项目 ID、成片时间线 ID、导出任务或结果、每个计划镜头对应的时间线素材实例，以及 HyperFrames / Remotion 渲染文件导入后的 ChatCut asset ID。`reports/timeline-audit.json` 逐镜比较 `visual-plan.json` 与实际时间线；仅有本地渲染文件但未导入或未放置，不算镜头已落实。

`config/project.json`、`reports/qa-report.json` 与 `reports/manifest.json` 必须复制同一个 `final_artifact` 对象，不得分别使用 `rendered_artifact`、`artifact`、`final` 等近义字段：

```json
{
  "path": "render/final.mp4",
  "sha256": "",
  "bytes": 0,
  "duration_ms": 0,
  "timeline_id": "",
  "export_task_id": null,
  "exported_at": "",
  "exporter": "chatcut-local-export",
  "video": {"codec": "h264", "width": 1920, "height": 1080, "fps": 30},
  "audio": {"codec": "aac", "sample_rate": 48000, "channels": 2}
}
```

`reports/timeline-audit.json` 的每个镜头必须使用同一套节拍证据：

```json
{
  "id": "S001",
  "screen_role": "A",
  "plan_range_ms": [0, 5200],
  "timeline_range_frames": [0, 156],
  "status": "pass",
  "beats": [
    {
      "at_ms": 0,
      "trigger_text": "逐字来自绑定 cue 的连续原文",
      "timeline_at_ms": 0,
      "status": "covered",
      "evidence": {
        "artifact": "assets/a-scenes/S001-state-01.png",
        "artifact_time_ms": null,
        "timeline_items": [
          {"item_id": "", "asset_id": "", "range_frames": [0, 78]}
        ]
      }
    }
  ]
}
```

`timeline_at_ms` 与计划 `at_ms` 的误差不得超过 `1000/fps` 毫秒，不使用成片总时长的 50ms 下限。`timeline_range_frames` 和素材实例 `range_frames` 均为零起点、左闭右开的整数帧区间。边界按 `floor(ms*fps/1000+0.5)` 换算：首镜从第 0 帧开始，镜头保持到下一镜语义起点，末镜到实际解码总帧数，以落实空隙保持策略。每个实例范围须在当前镜头范围内并覆盖该 beat 的实际时间点；镜头级范围记录完整画面，实例级范围记录本节拍真正使用的资产，不能填计划范围冒充实测。`evidence.artifact` 和 `artifact_time_ms` 必须与逐镜提示词实例中的同序节拍一致。ChatCut 路径的每个节拍至少包含一个真实 `item_id` 与 `asset_id`；本地文件存在但没有进入成片时间线不算 `covered`。

### 独立时间线证据

实例身份、源文件路径和时间字段均须绑定原始工程数据。字段来自另一份读取结果时，使用 `{path: "reports/raw-asset-v1.json", pointer: "/localPath"}`，并把该文件登记到 sources；适用于从素材检查结果取得实际本地路径。原始本地路径可以是绝对路径，归一化快照的 artifact 必须是项目内相对路径，两者须指向同一文件。缺少可核对字段时登记缺口，不能按计划填入默认值来制造通过。

审计根节点增加 `source_snapshot={path,sha256}`，指向项目内独立快照（例如 `reports/timeline-source-v1.json`），不从审计表反向复制实例。ChatCut 制作时保存项目读取、逐实例检查的实际原始结果；其他主时间线路径保存其实际工程读取结果。将原始结果保存为 JSON，保留对应字段，按下列格式归一化并逐项绑定到原始结果中的 JSON Pointer。不要改造原始数据使其符合审计。转换单位时显式指定 scale；帧边界转换另设 round_to_frame=true。工具返回文本中的 JSON 可以无修改提取并保存；提取失败或字段无法解释时保留错误，不宣称已核验。

```json
{
  "schema_version": "1.0",
  "captured_at": "实际采集时间",
  "project_id": "实际主工程 ID",
  "timeline_id": "实际成片时间线 ID",
  "fps": 30,
  "final_sha256": "本次导出文件哈希",
  "plan_sha256": "当前分镜哈希",
  "sources": [{"path": "reports/raw-timeline-v1.json", "sha256": "原始读取结果哈希"}],
  "items": [{
    "item_id": "实际实例 ID", "asset_id": "实际素材 ID",
    "artifact": "assets/shot.mp4", "sha256": "实际源文件哈希",
    "range_frames": [0, 156], "source_start_ms": 200, "playback_rate": 1,
    "origin": {"path": "reports/raw-timeline-v1.json", "fields": {
      "item_id": "/items/0/id", "asset_id": "/items/0/assetId",
      "artifact": "/items/0/localPath",
      "range_frames": [
        {"pointer": "/items/0/startUs", "scale": 0.00003, "round_to_frame": true},
        {"pointer": "/items/0/endUs", "scale": 0.00003, "round_to_frame": true}
      ],
      "source_start_ms": {"pointer": "/items/0/sourceStartUs", "scale": 0.001},
      "playback_rate": "/items/0/playbackRate"
    }}
  }]
}
```

示例原始字段名仅展示映射写法，必须换成当前工具实际返回的字段；不得据此推断 ChatCut 的固定返回结构。`source_start_ms` 是实例裁切后的源起点，`playback_rate` 为正数（原速为 1）。静态素材同样记录 source_start_ms=0、playback_rate=1，但节拍 artifact_time_ms 保持 null。连续素材证据满足 `源时间 = source_start_ms + (timeline_at_ms - 实例起始帧 × 1000/fps) × playback_rate`，容差为一个时间线帧对应的源时间。每个 ID、范围、裁切和速度均与原始读取结果比对，源文件哈希与节拍资产一致。当前通用映射不支持非线性变速、倒放或多段时间扭曲；先渲染为线性资产，再作为新实例审计。

导出后将本次 final_sha256 写入新版本快照，再绑定审计；重导或工程修改需重新采集适用证据，不能只更新旧快照哈希。离线检查证明保存证据之间的一致性，不证明在线项目从此未改变，也不能证明伪造的原始读取结果是真实调用；最终仍核对实际工具结果和导出画面。旧项目缺快照或 files 清单时明确阻塞此次交付，按续做范围补真实证据，不自动补造或修改历史批准。

## 8. 生产提示词实例

`references/production-prompts.md` 是提示词真源。实际使用不能只靠报告中写一句“已参考”，必须保存实例 JSON 和可选的 Markdown 派生视图：

- 全片编排：`planning/visual-plan-prompt.json/.md`，使用 `visual-plan-v1`；
- 单图生成角色三视图：`prompts/character/turnaround.json/.md`，使用 `character-turnaround-v1`；
- 每个 A-roll：`prompts/a-scenes/<shot-id>.json/.md`，使用 `a-roll-image-v1` 与 `a-roll-action-sequence-v1`；固定人物模式还要同时使用 `a-roll-view-v1`；
- 每个 B-roll：`prompts/b-scenes/<shot-id>.json/.md`，使用 `b-roll-motion-selection-v1`。

最小 JSON：

```json
{
  "schema_version": "0.3",
  "subject_id": "S001",
  "prompt_ids": ["a-roll-image-v1", "a-roll-view-v1", "a-roll-action-sequence-v1"],
  "prompt_source": "references/production-prompts.md",
  "prompt_source_sha256": "",
  "inputs": {},
  "resolved_prompt": "",
  "action_sequence": {
    "mode": "state-sequence",
    "static_reason": null,
    "beats": [
      {
        "beat_id": "A01",
        "at_ms": 0,
        "trigger_text": "",
        "visual_state": "",
        "implementation": "generated-state-frame",
        "evidence": {"artifact": "", "artifact_time_ms": null}
      }
    ]
  },
  "artifacts": [],
  "selection_report": null,
  "status": "prepared"
}
```

### 新执行的分区绑定

新增 `prompt_binding` 时保留执行时的完整原文哈希，另记录所用章节与共用规则：

```json
{
  "prompt_binding": {
    "policy": "per-prompt-v1",
    "common_sha256": "执行时的共用规则哈希",
    "prompts": {"a-roll-image-v1": "执行时的完整章节哈希"},
    "source_snapshot": {"path": "prompts/sources/a-image-source-v1.md", "sha256": "与 prompt_source_sha256 相同"}
  }
}
```

`prompts` 的键必须精确等于实例 `prompt_ids`，上例只演示单个 ID。章节边界是代码围栏外的二级标题；哈希覆盖标题、章节说明和完整提示词，围栏内标题不分区。无 prompt_id 的部分（文件前言、索引、使用规则等）合并为共用规则，变化影响所有新实例。换行统一 LF，其他文本变化仍计入哈希；重复 ID 或未闭合围栏报错。

在真实新执行的准备阶段捕获绑定字段及不可覆盖的原文副本，然后将绑定字段合并进本次实例，实际填写 inputs/resolved_prompt/状态与产物；命令只捕获真源，不代表已执行或审核通过：

```text
python scripts/prompt_bindings.py --project-dir <project> --source references/production-prompts.md --prompt-id a-roll-image-v1 --prompt-id a-roll-action-sequence-v1 --prompt-id a-roll-view-v1 --archive prompts/sources/S001-source-v1.md --out prompts/sources/S001-binding-v1.json
```

原文副本必须在项目内，哈希与 `prompt_source_sha256` 一致；校验先确认分区字段确实来自该副本，再与当前真源同 ID 章节及共用规则比较。只改未使用章节不使实例失效，改使用章节或共用规则仍须真实复核与重新执行。原文副本登记到交付 manifest；不得修改旧副本、替换旧哈希或将此次捕获当作历史使用证据。未声明分区协议的旧实例继续整文件严格校验。

B-roll 使用同一外层结构，但把 `action_sequence` 替换为：

```json
{
  "motion_sequence": {
    "mode": "continuous-motion",
    "static_reason": null,
    "beats": [
      {
        "beat_id": "B01",
        "at_ms": 0,
        "trigger_text": "",
        "visual_state": "",
        "implementation": "rendered-motion",
        "evidence": {"artifact": "", "artifact_time_ms": 0}
      }
    ]
  }
}
```

字段规则：

- `prompt_ids` 必须覆盖当前阶段要求的稳定 ID，不能用自由名称代替；
- `prompt_source_sha256` 必须等于执行时 `references/production-prompts.md` 的 SHA-256；不含 `prompt_binding` 的旧实例仍按整文件校验，真源改变后过期。新执行可使用分区绑定；不得把旧实例补绑为新协议冒充重新执行；
- `inputs` 保存实际代入的镜头文案、时间、导演意图、参考图、视觉规范或 B-roll 结构等输入，不能是空对象；
- `resolved_prompt` 保存已经替换占位符、可实际执行的完整提示词，不能只写章节链接或摘要；
- A-roll 的 action_sequence.mode 使用 single-state、state-sequence 或 continuous-motion。single-state 只落实一个计划节拍，不限制时长；任何单状态实现均需继承 shot.static_reason 到 action_sequence.static_reason。多状态必须完整落实计划节拍，不得用静止理由删减；
- B-roll 的 `motion_sequence.mode` 使用 `single-state`、`state-sequence`、`continuous-motion`、`verified-media-sequence` 或 `text-motion`；它的 beats 与计划 `narration_beats` 数量和顺序一致。single-state 只落实一个计划节拍，必须继承非空 shot.static_reason，不限制时长；阅读保持可以成立，多状态不得借静止理由删减；
- `action_sequence.beats` 与 `motion_sequence.beats` 的每项必须填写 `at_ms`、`trigger_text`、`visual_state` 和 `implementation`，且时间和短语与计划同序节拍完全一致。这里的 beats 是旁白锚点，不是动作内部状态的计数器；同一节拍内的必要状态按 §10 登记，不伪造新的 cue 起点。`produced` 阶段还必须填写 `evidence.artifact`；状态序列每个节拍使用不同资产，连续动画或文字动效可以共用文件，但每个节拍使用不同的 `artifact_time_ms`；实际素材必须可由 ffprobe 探测到视频流与正时长，证据时间为非负整数且严格小于源时长，不能用图片、空文件或越界时间冒充连续动画；
- `status` 使用 `prepared`、`used`、`completed` 或 `failed`。`prepared` 只证明提示词已实例化，不能证明已执行；`produced` 验证只接受 `completed`；
- `artifacts` 记录提示词产生的实际输出。`completed` 时至少有一个存在的项目相对路径；
- B-roll 的 `selection_report` 必须指向 `planning/template-selection/<shot-id>.json`，并与该镜头实际选型一致；
- `layout_still`（string | null）：兼容旧实例的落定帧路径；新实例可留 null，通过下述 layout_review 记录实际采用的检查，不强制为每镜另写静态 HTML；
- 新计划根节点声明 `broll_layout_policy="motion-first-v1"`；B-roll 实例包含 `layout_review={status,mode,reason,artifacts,review_source,dynamic_preview}`。mode 为 `key-states`（至少两个不同关键状态）、`reuse`（复用适用的既有布局/容量检查证据）、`source-readability`（核对文献/照片/引文身份与可读性）或 `static-hold`（仅 single-state）。reason 说明本镜为什么采用此方式，artifacts 为非空项目内相对证据路径数组，review_source 为 user 或 continuous 授权下的 agent-qa-under-user-authorization。status 为 planned 或 completed（缺省兼容为 completed）。准备阶段尚未生成状态图时可记录 planned、目标 artifacts 路径与 review_source=null，prepared 只验证检查计划与路径边界，不代表已审核；实际检查完成后改为 completed 并填写真实来源，校验授权模式与文件。produced 要求 completed，多状态镜头还必须有实际带原旁白审阅短片的 dynamic_preview 项目相对路径。文件存在不证明已看过或声音已合格，QA 仍核对实际观看证据。未知 policy 报错，旧计划未声明时仅兼容并提示未执行此门；不自动迁移旧审批与实例。
- 单图角色三视图只有 `character-bible.json` 声明 `generation_mode=generated-from-single-reference` 时才强制要求；用户直接提供并核实三视图时使用 `generation_mode=user-supplied-turnaround`，不伪造生成提示词实例。

按阶段运行：

```text
python scripts/validate_prompt_usage.py \
  --project-dir <project> \
  --production-prompts references/production-prompts.md \
  --stage planning \
  --out-dir <project>/planning

python scripts/validate_prompt_usage.py \
  --project-dir <project> \
  --production-prompts references/production-prompts.md \
  --stage prepared \
  --out-dir <project>/planning

python scripts/validate_prompt_usage.py \
  --project-dir <project> \
  --production-prompts references/production-prompts.md \
  --stage produced \
  --out-dir <project>/reports

python scripts/validate_delivery.py \
  --project-dir <project> \
  --production-prompts references/production-prompts.md \
  --mode review \
  --out-dir <project>/reports
```

`--mode review` 验证已经导出、可交给用户审片的技术闭环，允许 `status.final=rendered-pending-user-review`；用户或获授权的连续执行审核真正批准后，再使用 `--mode final`，此时必须有与成片哈希一致的 `approvals.final`。技术通过不能冒充用户批准。

## 9. 样片依赖与实际媒体证据

`approvals.sample` 在原有 artifact、sha256、approved_at、review_source 之外增加：

```json
{"dependencies": {"path": "preview/sample-dependencies-v2.json", "sha256": "实际快照哈希"}}
```

用 `scripts/sample_dependencies.py` 生成快照，随后按真实 QA 结果批准；生成快照本身不批准样片。新快照使用 `schema_version="2.0"`，绑定样片路径与哈希，并保存 `dependencies.settings`、`shot_ids`、`files[{path,sha256}]` 和 `plan_scope`。计划分区保存所有非 shots 根字段（未知字段保守地视为共用规则），以及覆盖样片区间的完整镜头对象与裁切后的 `display_range_ms`，包含首镜补前空隙、镜间保持和尾镜保持。仅区间外镜头变化或计划 JSON 排版变化不会作废样片；镜头移动进入样片、区间内设计/节拍/边界变化仍失效。共用输入 SRT/音频、视觉规范、候选审阅、人物规范与参考索引、DESIGN 及账号规范/字体/样张仍整体绑定；区间内的提示词原文快照、输出、源工程、选择/研究与布局检查证据逐文件绑定。配置只绑定输入、规格、样片区间、时间线策略、字幕区、主模式和主时间线，避免把审批本身纳入哈希形成循环。

旧 `1.0` 快照继续绑定完整计划，不自动迁移、重写哈希或批准记录。切换到 2.0 时先真实复核再用新文件保存快照。全片计划批准仍绑定完整计划；区间外变更需复核计划批准，但无需因此重复批准未受影响的 2.0 样片。最终成片和工程快照仍绑定完整计划，不缩小交付检查范围。

当前对计划采用全文件哈希，属于保守失效：仅回填制作状态也会要求复核快照，但不要求重新生成未变化资产。后续若引入语义投影哈希须显式版本化，不能临时忽略字段。状态校验只报告依赖过期，不自动改审批或旧快照。新旧项目已批准样片均须满足此项；旧样片需真实复核后补证。

`qa-report.json` 增加：

```json
{"frame_scan": {"path": "reports/frame-scan-v1.json", "sha256": "复核完成后的报告哈希"}}
```

`scripts/scan_video.py` 生成扫描 JSON：`schema_version="1.0"`、`artifact_path`、`artifact_sha256`、`scan_complete`、`fps`、`decoded_frames`、`media`、`detector`、`candidates`。每个候选包含零起点 `frame`、`time_ms`、原因和测量值。人工或获授权代理查看候选原帧及前后帧后，正常候选填写：

```json
{"review": {"decision": "accepted", "reason": "具体正常暗场或切镜依据", "evidence": {"path": "reports/frame-review-v1.md", "sha256": "实际证据哈希"}}}
```

证据文件须指向可核对的原分辨率帧及结论。未处理候选、失效报告、缺失证据均阻止交付。坏帧应修复并对新文件重新扫描，不通过 `accepted` 放行。重新导出和补帧不能沿用旧报告；扫描器拒绝覆盖已有文件。

`validate_delivery.py` 实际运行 ffprobe 解码计数并检查视频流规格、时长、音频流、帧数、扫描绑定、状态依赖和时间线区间。project、QA、manifest 中完整 `final_artifact` 对象必须一致。该检查仍不能证明字幕语义、画面美感、实际音轨内容或听感正确，继续执行 QA 的人工/授权代理检查。

## 10. 动作设计与视觉审阅证据

新初始化项目在 project.json 设置 `motion_review_policy="evidence-first-v1"`，新计划使用同名值；未知值或新项目漏声明均报错。旧项目未接入时只提示没有验证此门，不自动改写旧审批、哈希或生产实例。新执行的提示词变更按 §8 重新捕获，旧图像和实例保留原版本。

### 10.1 计划

- `baseline_shot_ids`：非空、不重复的现有镜头 ID 数组，明确本次视觉基线要验证的代表镜头。按实际表达、高信息量和高风险动作选择，不要求全片每镜都做独立基线。
- `visual_design.motion_mode`：`single-state`、`state-sequence`、`continuous-motion`、`verified-media-sequence`、`text-motion`。与逐镜实例的 action_sequence/motion_sequence.mode 相同。只对显式 single-state 要求 static_reason；不能从 changes、cue 或 narration_beats 数量推断静止。
- 非静止镜头的 `visual_design.motion_check`：非空 `action`（主体怎样操作或改变）、`visible_result`（观众要看见什么结果），以及 `required_states=[{id, beat_index, description}]`。状态 ID 唯一，描述实际可见状态，beat_index 引用现有 narration_beats 的零起点序号。同一节拍可以包含多个状态，不另造 SRT 锚点。至少两个必要状态，数量和是否包含接触／连接由动作决定，不固定三张。主体与对象沿用 subject、relation，不另建时间真源。

```json
{
  "motion_review_policy": "evidence-first-v1",
  "baseline_shot_ids": ["S001"],
  "shots": [{
    "id": "S001",
    "visual_design": {
      "motion_mode": "continuous-motion",
      "motion_check": {
        "action": "同一头罐沿竖直轴上移，身罐保持原位",
        "visible_result": "两罐相对的罐口与连接间距清楚",
        "required_states": [
          {"id": "assembled", "beat_index": 0, "description": "完整器物"},
          {"id": "separated", "beat_index": 0, "description": "头罐上移、相对罐口显露"}
        ]
      }
    }
  }]
}
```

这是新增字段示例，其他必填字段仍按 §5。七列表格从 JSON 同步展示运动方式、验收动作、结果和必要状态。

### 10.2 候选与批准

候选 JSON 使用 `{policy, scope, plan_sha256, design_ref, shots}`。policy 为 evidence-first-v1；plan_sha256 绑定当前 visual-plan.json，design_ref 与计划相同。scope：

- `style-preview`：允许仅展示一个已声明的状态，检查实际媒体和引用，不宣称动作覆盖或基线通过。
- `state-preview`：检查所展示镜头的全部 required_states；可单独交付局部静帧验证，但不批准为动作基线。
- `motion-baseline`：覆盖 baseline_shot_ids，必要状态齐全，非静止镜头有实际带原旁白短片和通过的技术／表达检查，才可进入既有批准门。合理静止镜头仅验证 hold 状态及阅读理由，不强制生成动画。

每个 shots 项使用以下结构；路径与哈希必须来自实际产物：

```json
{
  "shot_id": "S001",
  "state_evidence": [
    {"state_id": "assembled", "artifact": "preview/S001.mp4", "sha256": "实际SHA-256", "artifact_time_ms": 0},
    {"state_id": "separated", "artifact": "preview/S001.mp4", "sha256": "实际SHA-256", "artifact_time_ms": 1200}
  ],
  "dynamic_preview": {"artifact": "preview/S001.mp4", "sha256": "实际SHA-256"},
  "narration_sha256": "当前input音频的实际SHA-256",
  "technical_review": {"status": "pass", "notes": "视频可读、时间点在范围内，已核对构图与文字"},
  "expression_review": {
    "status": "pass", "review_source": "user",
    "observed_action": "实际片段中头罐上移，身罐未移动",
    "observed_result": "两罐口在拆分停点同时可辨",
    "action_matches": true, "result_matches": true, "narration_matches": true
  }
}
```

静帧证据的 artifact_time_ms 为 null 或省略，须为可解码的单帧图片；视频状态须填写非负、严格小于实际时长的时间点。不同状态不能复用内容哈希相同的图片或同一视频时间点；同图另存不同文件名不算新状态。静止镜头用 `state_id="hold"`。dynamic_preview 必须为可解码的实际视频，含音轨并绑定当前旁白；音轨内容和听感仍需真实试听，哈希声明不能证明已混入正确声音。

技术检查和表达检查独立：表达观察须记录实际行动和实际结果，action_matches、result_matches、narration_matches 任一为 false 均不能批准。review_source 沿用 manual/continuous 授权规则。脚本只核对证据完整性、媒体与审核记录，不能据布尔值认定画面因果或美感自动合格，不伪造已看过／已试听记录。

```text
python scripts/validate_visual_review.py --project-dir <project> --review <project>/preview/visual-review.json --out <project>/planning/visual-review-validation.json
python scripts/validate_visual_review.py --project-dir <project> --review <project>/preview/visual-review.json --approve-baseline --out <project>/planning/baseline-validation.json
```

`--approve-baseline` 只验证批准条件，不写审批。validate_state.py 在新基线标为 approved 时再次执行同一证据门；旧批准仅检查历史一致性并提示兼容边界。produced 阶段逐镜实例新增 `motion_review`，采用上面的单镜结构并补 `plan_sha256`；validate_prompt_usage.py 检查全片所有实际制作镜头，不能只验证代表镜头后将其他镜头记为完成。既有 layout_review 和时间线审计继续有效，不以本记录替代正式资产与导出检查。

## 11. 连续镜头质量门

新任务配置`sequence_review_policy="sequence-quality-v1"`及`sequence_review={sample:null,full:null}`。sample/full值是版本化审阅JSON的项目内相对路径；未生成时保留null。旧任务缺此policy只提示兼容，不自动补审批或改历史实例；未知值报错。执行方法见[sequence-quality.md](sequence-quality.md)。

计划根`sequence_direction={visual_thread,continuity,layout_rules,motion_language}`四项为非空字符串，分别说明整片观看主线、镜头承接、空间规则和动作节奏，引用本片DESIGN而不另维护字体/配色参数。每镜`production.assembly_tool`等于项目`primary_timeline`。非静止的HyperFrames、Remotion、ChatCut Motion Graphics镜头，或`production.custom_motion=true`的其他镜头，声明`production.motion_reference_review`（项目相对JSON路径）；单状态必要阅读、原样使用已有片段与常规剪辑裁切不强制研究。实际制作工具变化须回写primary_tool，不能以旧material_type规避。

### 动效参考记录

可由同类镜头共用，也可指向已有broll-research记录。通用检查使用其下列字段，信息图完整研究门的额外字段与校验继续适用：

- `decision`：reuse-native-source、study-and-reimplement、custom-after-external-review。
- `inspected_candidates`：非空数组，ID不重复；每项含`id`、具体`source_locator`或`shot_card`、`assessment`，及`preview_evidence={status:"inspected",artifact,sha256}`。预览为可解码图片或视频，artifact与哈希均指向项目内实际文件。声明inspected不是自动证明已观看。
- 复用/研究重实现的`selected_candidate`是其中唯一一个ID。原生复用候选另有`license`、`license_evidence={path,sha256}`及非空`implementation_files`；实现文件须在项目或配置repositories_root内可读，可按repository子目录解析。来源代码不因可读取就自动取得许可；未确认许可只研究结构。
- 自建的`selected_candidate=null`，有`custom_reason`、`borrowed_motion_principles`，每个已检查候选有`rejection_reason`；不能伪造搜索或以候选数量代替适配判断。

### 样片/整片连续审阅

审阅结构如下。哈希来自实际文件；`plan_scope_sha256`由`scripts/sequence_quality.py`的`scope_hash(plan,shot_ids)`计算，绑定计划公共字段及范围内镜头。`plan_snapshot`为审阅当时计划的不可变副本，scope_hash也须与当前范围相同。区间外镜头改变不使未受影响样片自动过期；DESIGN、原旁白、SRT、公共规则或区间内镜头改变需要复核。

```json
{
  "policy": "sequence-quality-v1",
  "scope": "sample",
  "range_ms": [0, 45000],
  "plan_snapshot": {"path": "planning/revisions/sample-v1/visual-plan.json", "sha256": "实际SHA-256"},
  "plan_scope_sha256": "实际范围哈希",
  "design_ref": {"path": "config/DESIGN.md", "version": "本片版本", "sha256": "实际SHA-256"},
  "narration_sha256": "原MP3实际SHA-256",
  "srt_sha256": "原SRT实际SHA-256",
  "artifact": {"path": "preview/sample-v1.mp4", "sha256": "实际SHA-256"},
  "timeline": {
    "runtime": "chatcut", "project_id": "实际项目ID", "timeline_id": "实际时间线ID",
    "exporter": "chatcut-local-export",
    "source_snapshot": {"path": "preview/sample-v1-timeline-source.json", "sha256": "实际SHA-256"}
  },
  "review_source": "agent-self-check",
  "normal_speed_viewed": true,
  "sequence_checks": {
    "visual_continuity": {"status": "pass", "notes": "具体观察与镜头承接结果"},
    "ppt_feel": {"status": "pass", "notes": "运动怎样承担解释，必要静止段为何成立"},
    "reading_rhythm": {"status": "pass", "notes": "正常速度下的阅读、动作停点与旁白顺序"}
  },
  "shots": [
    {
      "shot_id": "S001", "actual_tool": "hyperframes", "item_ids": ["实际镜头实例ID"],
      "explanation_review": {"status": "pass", "notes": "实际变化与理解收益"},
      "layout_review": {"status": "pass", "notes": "主体、文字、出处及字幕区在运动中可读"},
      "state_evidence": [
        {"phase": "start", "artifact": "preview/sample-v1-S001-start.png", "sha256": "实际SHA-256", "artifact_time_ms": 0},
        {"phase": "change", "artifact": "preview/sample-v1-S001-change.png", "sha256": "实际SHA-256", "artifact_time_ms": 900},
        {"phase": "result", "artifact": "preview/sample-v1-S001-result.png", "sha256": "实际SHA-256", "artifact_time_ms": 1800}
      ]
    }
  ],
  "transitions": [
    {"from": "S001", "to": "S002", "artifact_time_ms": 2000,
     "evidence": {"path": "preview/sample-v1-S001-S002.png", "sha256": "实际SHA-256"},
     "status": "pass", "notes": "接缝或实际混合中间态的观察"}
  ]
}
```

示例省略后续shots，实际必须按range_ms顺序覆盖全部相交镜头；sample范围等于配置样片区间，full从零覆盖所有镜头并绑定final_artifact.path/sha256。视频规格与项目一致、时长匹配区间且含音轨；没有原旁白正常速度观看记录不得通过。必要静止镜头使用phase=hold，非静止镜头至少有start/change/result三个不同时间点，高风险接触或交叉另补证据，不按三个固定截图上限验收。

所有artifact_time_ms是**审阅视频内**时间，range_ms是原计划区间；二者相差range_ms[0]，不改写原cue。运动静帧时间须在该镜实际显示范围内（含配置的空隙保持）；每个相邻镜头有一项transitions，顺序对应，证据时间位于这对镜头的视频范围内。静帧须可解码并校验哈希，实际是否对应声明时间仍需观看核对。

timeline.source_snapshot沿用 §7 的1.0独立工程读取证据，items帧区间以本次审阅视频零点计，final_sha256绑定本次审阅视频、plan_sha256绑定plan_snapshot的哈希。原始sources及origin字段映射必须真实，不从计划复制“实际工程”。样片复核使用已保存计划快照再核对当前scope_hash，正式交付审计仍按当前完整计划验证。ChatCut项目/时间线ID与配置一致，exporter=chatcut-local-export；实际工具与计划一致。每镜item_ids覆盖显示帧区间，并至少有一个位于该镜范围内的独立实例，不能由一个跨全片的合成item覆盖所有镜头。程序化镜头保留production.source_files。

review_source可为user、agent-self-check、agent-qa-under-user-authorization；最后一种仅continuous授权可用。agent-self-check仅记录普通内部质量检查，不写approvals、不代替manual确认。检查结论用`{status,notes}`，通过时status=pass并写具体观察；fail/pending或缺观察均阻塞扩大与交付。旧审批不自动升级为新检查通过。

planning并入validate_plan；prepared及produced提示词校验复查动效参考；sample批准由validate_state复查，v2样片依赖快照收录质量证据文件；扩大前显式运行validate_sequence_quality --stage expand；review和final交付检查full并将实际证据文件纳入manifest。脚本不进行视觉审美评分、自动检测所有遮挡或证明观看发生，实际观看与原有QA仍必需。

启用本policy的新任务必须使用2.0样片依赖快照，不能降级为1.0而省略质量证据绑定；旧任务原1.0/2.0快照仍按原规则核验。

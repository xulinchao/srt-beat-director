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
    manifest.json
```

`character-bible.json` 仅在人物或重复角色存在时创建。不要制造空占位目录或文件；在对应阶段首次需要时创建。

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

- `config/project.json`：项目级输入、输出、规格、模式和门控状态的真源；
- `planning/content-analysis.json`：全文结构和语义段的真源；
- `planning/visual-plan.json`：镜头与时间轴的真源；
- `config/visual-style.json` / `character-bible.json`：视觉一致性的真源；
- `input/references/index.json`：参考图片和素材允许影响范围的真源；
- `templates/template-index.json`：模板来源和能力的真源；
- `reports/qa-report.json` 与 `manifest.json`：最终验证和交付真源。

同名 Markdown 文件是派生的人类可读视图。不要分别维护两套内容；修改后以 JSON 重生成或同步 Markdown。

## 3. `project.json` 最小字段

```json
{
  "schema_version": "0.1",
  "project_id": "example",
  "inputs": {"srt": "input/source.srt", "audio": "input/narration.mp3"},
  "output": {"directory": "render", "filename": "final.mp4"},
  "video": {"aspect_ratio": "9:16", "width": 1080, "height": 1920, "fps": 30},
  "primary_timeline": "chatcut",
  "review_mode": "manual",
  "chatcut": {"project_id": null, "project_name": null, "timeline_id": null},
  "a_scene_mode": "fixed-character-micro-scene",
  "subtitle_safe_area": {"bottom_fraction": 0.22},
  "timeline_policy": {
    "initial_gap": "show-first-shot",
    "inter_shot_gap": "hold-previous-shot",
    "tail_gap": "hold-last-shot"
  },
  "sample": {"start_ms": 0, "end_ms": 45000},
  "status": {"plan": "draft", "visual_baseline": "pending", "sample": "pending"},
  "approvals": {
    "plan": {"sha256": null, "approved_at": null, "review_source": null},
    "visual_baseline": {"sha256": null, "approved_at": null, "review_source": null},
    "sample": {"sha256": null, "approved_at": null, "review_source": null}
  }
}
```

允许值：

- `a_scene_mode`：`fixed-character-micro-scene`、`full-ai-scene`；
- `primary_timeline`：`chatcut`、`hyperframes`；用户指定 ChatCut 时不得因为部分 B-roll 使用 HyperFrames 而改写此字段；
- `review_mode`：`manual`、`continuous`。`continuous` 只在用户明确要求自检后继续时使用，不等于预先批准计费、发布、账户或系统权限；
- `review_source`：通过门控时记录 `user` 或 `agent-qa-under-user-authorization`。后者只允许在 `review_mode=continuous` 时使用；不得把代理自检记录成用户确认；
- `chatcut`：仅在 ChatCut 路径使用。`project_id`、`timeline_id` 必须来自实际工具读取，不能凭名称猜测；
- 各状态：`draft`、`pending`、`approved`、`stale`；
- 修改影响内容或视觉基线的真源后，将下游状态标记为 `stale`。
- 每次批准绑定当前真源或样片的 SHA-256；修改被绑定文件后，不能沿用旧批准。
- 镜头 `start_ms`/`end_ms` 描述语义边界。字幕前、镜头间和尾部空隙按 `timeline_policy` 补齐到完整音频时长，不能让合成器自行猜测。

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

其中“画面类型”使用用户可读的五类名称：`人物画面`、`场景画面`、`真实素材`、`信息图形`、`文字动效`；A/B 职责、素材子类型、语义结构、工具和风险保留在 JSON 或表格后的补充检查中。表格中的镜头 ID 必须从 `S001` 连续递增，时间必须显示为毫秒，配音文案必须来自 `verbatim_text`，不得改写。表格之后固定输出“需要补充的素材”“需要确认的视觉方向”“制作难度较高的镜头”三个部分；无内容时写“无”。

```json
{
  "schema_version": "0.1",
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
      "item_count": null,
      "visual_design": {
        "subject": "",
        "composition": "",
        "shot_scale": "medium",
        "elements": [],
        "final_state": ""
      },
      "changes": [],
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

`screen_role` 只允许 `A` 或 `B`。A 的子类型由项目级主画面模式约束；B 的 `material_type` 使用 `verified-media`、`no-material` 或 `text-only`，`presentation_type` 使用 `verified-media`、`infographic` 或 `text-motion`。旧字段 `screen_subtype` 只保留画面实现类别，不能代替这两个映射字段。`start_ms` 和 `end_ms` 必须来自 SRT 边界。

`production` 记录计划如何落实，不替代画面语义字段：

- `primary_tool`：`existing-media`、`chatcut-image`、`chatcut-video`、`chatcut-motion-graphics`、`hyperframes` 或具体的其他可用工具；
- `fallback_tools`：按失败后的真实尝试顺序列出，不能把无关静态图作为动态镜头的默认回退；
- `asset_status`：`available`、`to-generate`、`in-progress`、`ready`、`failed`、`gap`；
- `asset_gap`：没有缺口时为 `null`，有缺口时写清缺少什么、为什么无法继续该镜头和是否影响全片导出。
- 当前标准流程中，`no-material + infographic` B-roll 的 `primary_tool` 必须为 `hyperframes`；ChatCut 只负责这些渲染结果的素材管理、时间线组装与导出。只有用户明确改变工具分工时才能使用其他主工具，并在计划中说明例外。

连续三镜以上同一 `screen_role` 时，在计划根节点增加 `roll_run_exceptions`，逐段记录 `start_shot_id`、`end_shot_id`、`screen_role` 与非空 `reason`。理由必须说明为什么语义不可拆，以及连续镜头如何改变视角或信息结构；不能只写“节奏需要”。

- A-roll 固定人物模式必须使用 `a_view`：`presenter`、`protagonist`、`supporting`、`first-person`；
- B-roll 必须填写 `material_type`、`presentation_type`、`semantic_structure` 与正整数 `item_count`；
- `semantic_structure` 只允许 `comparison`、`aggregation`、`filtering`、`hierarchy`、`causality`、`replacement`、`expansion`；交叉特征写入可选的 `secondary_structures`；
- `semantic_pattern` 可写具体骨架模式，例如 `before-after-slider` 或 `true-boundary-vs-temporary-fatigue`；它用于同一主结构内排序，不能代替标准主结构；
- B-roll 的 `materials` 必须能判断为现有已核实素材、待补素材或无需真实素材；
- `template_id` 只能使用以下路由：合格本地模板 ID、`external-research:<structure>`、`external:<candidate-id>` 或 `new:<id>`。
- `external-research:<structure>` 表示尚未完成研究，只能停留在规划状态，不能开始实现。
- `external:<candidate-id>` 必须引用 `broll_research_record` 中已检查并选中的候选。
- `new:<id>` 不是本地无匹配时的直接回退。只允许在 `broll_research_record` 的决策为 `custom-after-external-review`、目录候选均有拒绝理由且记录了借鉴的运动原则后使用。
- `no-material + infographic` 没有合格本地模板时必须填写 `broll_research_record`，路径为 `planning/broll-research/<shot-id>.json`。详细契约见 [broll-external-research.md](broll-external-research.md)。

## 6. 模板索引

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
  "hyperframes_status": "animation-verified",
  "known_limits": []
}
```

`hyperframes_status` 建议使用：

- `styleframe-only`：只有静态终态，不可作为可直接复用的动效模板；
- `implementation-required`：结构已选定，尚未接入 HyperFrames；
- `animation-verified`：动画、seek-safe 和目标画幅均已验证；
- `superseded`：已过期，不参与匹配。

用 `scripts/select_broll_template.py` 匹配时，静态模板可以作为设计候选，但输出必须明确 `implementation_required=true`，不能声称“只替换文案即可”。

## 7. Manifest

最终 `manifest.json` 至少列出每个输入、真源、采用的提示词、B-roll 研究记录、资产、模板、工程文件、样片、成片和报告的相对路径、SHA-256、来源或生成方式、版本与状态。派生缓存可记录，但不能替代真源。

ChatCut 路径的 manifest 还要记录项目 ID、成片时间线 ID、导出任务或结果、每个计划镜头对应的时间线素材实例，以及 HyperFrames 渲染文件导入后的 ChatCut asset ID。`reports/timeline-audit.json` 逐镜比较 `visual-plan.json` 与实际时间线；仅有本地渲染文件但未导入或未放置，不算镜头已落实。

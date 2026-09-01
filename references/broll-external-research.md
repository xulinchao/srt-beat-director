# B-roll 外部骨架研究门

仅在 B-roll 为 `no-material + infographic` 且没有合格本地模板时读取。本门的目的不是强制复制开源代码，而是避免代理跳过已有动效经验，直接把临时 SVG、卡片或线条当作成熟信息动画。

## 强制顺序

1. 运行 `scripts/select_broll_template.py`，保存逐镜选择报告。
2. 若报告为 `external-research-required`，先检查 `external_candidates`，不得直接写 `new:<id>` 或开始实现。
3. 至少检查 `min(2, 当前结构候选数)` 个候选。每个候选先读镜头卡；状态为 `port-required` 时还要读镜头卡指向的具体实现文件。
4. 比较语义适配、元素关系、主要运动、阶段顺序、原框架、许可证和最小改造范围；比较结果只用于选出一个唯一实现来源。
5. 选择以下一种决策：
   - `port-external-skeleton`：许可证允许移植，保留骨架并改造成当前主实现载体（HyperFrames 或 ChatCut Motion Graphic）；
   - `study-and-reimplement`：只允许研究结构，在当前主实现载体中按单一来源重新实现；
   - `custom-after-external-review`：候选均不适合，记录逐项拒绝理由后从零实现，但仍吸收已验证的运动原则。
6. 把记录保存到 `planning/broll-research/<shot-id>.json`，运行 `scripts/validate_broll_research.py`。验证通过前禁止实现该 B-roll。

每个镜头必须有且只有一个 `selected_candidate`。`inspected_candidates` 可以包含多个候选，但未选候选只能写拒绝理由，不得把其运动阶段、布局或节奏混入 `migration_plan` 或最终实现。最终资产描述必须能映射到一个唯一的镜头卡/实现文件。

```text
python scripts/validate_broll_research.py \
  --visual-plan <project>/planning/visual-plan.json \
  --template-index <project>/templates/template-index.json \
  --semantic-map references/semantic-template-map.json \
  --research-dir <project>/planning/broll-research \
  --repositories-root research/reference-repos \
  --out <project>/planning/broll-research-validation.json
```

连续执行模式可以由代理自行比较和选择，不需要为每镜暂停；但研究记录和验证不能省略。手动审核模式按项目既有门控处理。

## 研究记录

```json
{
  "schema_version": "0.1",
  "shot_id": "S006",
  "selector_report": "planning/template-selection/S006.json",
  "inspected_candidates": [
    {
      "id": "shotcraft-before-after-slider",
      "repository": "video-shotcraft",
      "shot_card": "references/shots/data/before-after-slider-scrub.md",
      "implementation_files": [
        "demos/data/before-after-slider-scrub/BeforeAfterSliderScrub.tsx"
      ],
      "license": "Apache-2.0",
      "fit": "selected",
      "assessment": "快甩建立差异、慢扫留出阅读期，适合两状态比较。",
      "rejection_reason": null
    }
  ],
  "decision": "port-external-skeleton",
  "source_policy": "single-source",
  "selected_candidate": "shotcraft-before-after-slider",
  "implementation_source": {
    "candidate_id": "shotcraft-before-after-slider",
    "repository": "video-shotcraft",
    "shot_card": "references/shots/data/before-after-slider-scrub.md",
    "implementation_files": [
      "demos/data/before-after-slider-scrub/BeforeAfterSliderScrub.tsx"
    ],
    "mode": "port-skeleton-to-current-runtime"
  },
  "extracted_skeleton": {
    "element_relation": "两版内容同位叠放",
    "main_motion": "分割杆先快甩后慢扫",
    "phase_order": ["建立旧状态", "快速揭示", "慢速比较", "定格结论"]
  },
  "custom_reason": null,
  "borrowed_motion_principles": []
}
```

字段要求：

- `inspected_candidates` 只能引用当前语义结构目录中的候选；路径必须落到本地仓库的具体文件。
- `fit` 使用 `selected`、`partial` 或 `rejected`。未选候选必须写非空 `rejection_reason`。
- 选择外部骨架时，`template_id` 写成 `external:<candidate-id>`。
- 从零实现时，`template_id` 才能写 `new:<id>`；所有已检查候选必须被拒绝，并提供 `custom_reason` 与至少一个 `borrowed_motion_principles`。
- `extracted_skeleton.phase_order` 至少三个可审阅阶段；单纯淡入、背景循环和镜头慢推不算完整骨架。

## SVG 边界

SVG 可以作为 HyperFrames 动画中的图标、路径、遮罩或矢量组件，但静态 SVG 文件不能单独满足 `no-material + infographic` B-roll。完成状态至少需要可定位恢复的时间动画、三个有效阶段、可审阅预览和实际渲染结果。

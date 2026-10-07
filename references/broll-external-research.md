# B-roll 外部骨架研究门

仅在 B-roll 为 `no-material + infographic` 且未确认合格本地模板或参考仓库来源时执行完整外部研究门。本门的目的不是强制复制开源代码，而是避免代理跳过已有动效经验，直接把临时 SVG、卡片或线条当作成熟信息动画。

## 两类来源，两种要求

本文件的`no-material + infographic`条件限定的是**完整外部搜索流程**。新任务其他自制动效也按[连续镜头质量门](sequence-quality.md)查看具体运动来源并记录适配；素材存在或scene分类不能自动豁免。可复用这里已通过的具体研究记录，不重复写第二份候选比较，也不降低本文件的更严格要求。

- **参考仓库（本地可达）**：通过 `config/project.json` 的 `repositories_root` 配置的仓库（如 video-shotcraft、hyperframes-launches）属于本地候选来源。选择器的 `candidates-recalled` 只表示召回；实际检查并填写 `reference_confirmation` 后可走轻量确认，不需要完整外部研究记录。来源许可仍须核实并记录依据。
- **真正的外部来源**：参考仓库中也没有匹配时，搜索互联网或其他未配置来源。只有这类来源需要执行下文的强制顺序、研究记录与校验。

## 参考仓库来源：§6 快路径简化流程

按 [production-prompts.md](production-prompts.md) §6 执行：

1. **召回与核对**：选择器以 BM25、显式标签和可选真实向量混合召回，并核对显式约束，不自动选中；逐个看实际预览、源码和镜头卡，核对元素关系、核心动作、阶段、中文容量与许可。题材或单个关键词相同不算动作适配。
2. **确认唯一来源**：在 `planning/template-selection/<shot-id>.json` 填写 `reference_confirmation`，字段见 [数据契约](contracts.md) §5。`confirmed_source_id` 与计划的 `external:<id>` 一致，`confirmed_file_path` 与召回候选一致；保存项目内预览、动作与阶段适配理由、来源框架和实际许可证依据。再按骨架检查必要关键状态或复用适用布局证据，记录 layout_review；多状态另做动态预览。
3. **最小修改 + 动画实现**：只改字体、颜色、间距、安全区等 DESIGN 适配项，保留骨架的核心运动和阶段结构；效果直接在其原生框架渲染，输出片段导入 ChatCut。

仓库内扫描还会发现未登记候选，不能假设其许可已确认。参考候选实际查看后均不适合时，记录拒绝理由并进入下文的完整外部研究门；自建 `new:<id>` 始终需要研究记录和扩大搜索证据。
若选择报告为 `candidates-recalled` 后转自建，完整研究记录增加 `reference_candidate_reviews`，逐项保存实际查看的 `{candidate_id, rejection_reason}`；至少有一项，ID 必须来自该选择报告的召回候选。未逐个查看的其他候选应在 `custom_reason` 说明为何不值得继续适配，不能把分数低直接写成动作不合适。

## 外部研究强制顺序

1. 运行 `scripts/select_broll_template.py`，保存逐镜选择报告。
2. 若报告为 `external-research-required`，或 `candidates-recalled` 的参考候选经实际查看均不适合，继续检查 `external_candidates` 并扩大搜索；不得直接写 `new:<id>` 或开始实现。
3. 新选型按 [动作表达简报](broll-expression-selection.md) 使用 expression-first-v1，跨语义类别和框架找骨架；候选数量不作为完成标准。先看实际演示，读镜头卡与实现；结构明显不适配可先拒绝，不能因此跳过扩大搜索。
4. 比较元素关系、核心动作、阶段、不变量、中文容量、设计适配、许可证与改造范围。题材、原始颜色、字体和外观可适配，不作为单独拒绝理由。初始候选均不合适或目录为空时，至少以两种动作查询覆盖两个搜索来源，记录实际 expanded_search；发现新来源登记 discovered_candidates，不限定为登记表内候选。
5. 选择以下一种决策：
   - `reuse-native-source`（默认）：合格的源码在其原生框架制作，`implementation_source.runtime` 与镜头 `primary_tool` 一致；工具决策使用 `native-reuse`，渲染片段导入 ChatCut，不执行跨框架移植；
   - `study-and-reimplement`：许可证未确认或只允许研究结构时，在选定框架中按单一来源重新实现；
   - `custom-after-external-review`：扩大搜索后仍不适合，所有已检查候选明确被拒绝，记录动作不适配理由与可追溯原则；先以真实素材做代表短片，通过既有视觉 QA 后再扩大制作。
6. 把记录保存到 `planning/broll-research/<shot-id>.json`，运行 `scripts/validate_broll_research.py`。验证通过前禁止实现该外部来源的 B-roll。

复用或重实现时必须有且只有一个 `selected_candidate`，自建时为 `null`。`inspected_candidates` 可以包含多个候选，但未选候选只能写拒绝理由，不得把其运动阶段、布局或节奏混入 `migration_plan` 或最终实现。最终资产描述必须能映射到一个唯一的镜头卡/实现文件。

```text
python scripts/validate_broll_research.py \
  --visual-plan <project>/planning/visual-plan.json \
  --template-index <project>/templates/template-index.json \
  --semantic-map references/semantic-template-map.json \
  --research-dir <project>/planning/broll-research \
  --repositories-root <external-repositories-root> \
  --out <project>/planning/broll-research-validation.json
```

连续执行模式可以由代理自行比较和选择，不需要为每镜暂停；参考仓库来源需通过轻量确认校验，外部来源与自建需通过完整研究校验。手动审核模式按项目既有门控处理。
轻量确认使用 `config/project.json` 中的 `repositories_root` 核对参考文件；上方命令的 `--repositories-root` 用于完整外部研究取得的仓库副本，两者不必是同一路径。

## 研究记录

角色替换与新增互动的边界见 [broll-production.md](broll-production.md)：保持骨架可素材适配，改变骨架则记录候选不适用并走已有自建决策。assessment 补充主体/关系/变化、中文容量、内部节拍、设计兼容、依赖及具体预览检查；实际渲染通过前不能记为验证模板。

```json
{
  "schema_version": "0.2",
  "shot_id": "S006",
  "selector_report": "planning/template-selection/S006.json",
  "expression_brief": {
    "subjects": ["旧状态图", "新状态图"],
    "element_relation": "两版内容同位叠放",
    "main_motion": "分割边界扫过并揭示新状态",
    "phase_order": ["建立旧状态", "揭示差异", "比较并保持"],
    "invariants": ["图片位置和尺寸保持"],
    "motion_tags": ["same-position-replacement", "boundary-reveal"],
    "search_queries": ["reveal before after images at the same position", "scrub a divider across two aligned images"]
  },
  "discovered_candidates": [],
  "expanded_search": [],
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
      "preview_evidence": {"status": "inspected", "artifact": "planning/broll-research/S006-reference-preview.png"},
      "rejection_reason": null
    }
  ],
  "decision": "reuse-native-source",
  "source_policy": "single-source",
  "selected_candidate": "shotcraft-before-after-slider",
  "implementation_source": {
    "candidate_id": "shotcraft-before-after-slider",
    "repository": "video-shotcraft",
    "runtime": "remotion",
    "shot_card": "references/shots/data/before-after-slider-scrub.md",
    "implementation_files": [
      "demos/data/before-after-slider-scrub/BeforeAfterSliderScrub.tsx"
    ]
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

- expression-first-v1 的 `inspected_candidates` 可以引用全局目录中动作适配的候选，或 discovered_candidates 中新取得的具体来源；不能限定为当前粗语义类别。外部来源路径须在执行时 --repositories-root 指定的仓库副本内；已确认的参考仓库来源走上方轻量流程，自建仍须本研究记录。
- `expression_brief` 原样复制选择报告中的对象。选中来源记录 `preview_evidence={status: inspected, artifact: 项目相对文件路径}`，指向实际截图或演示视频；技术检查只能验证文件存在，实际观看仍由代理/用户审核。
- `discovered_candidates` 每项含唯一 id、repository、path（镜头卡）、license、status、source_url（原始来源链接）；有可运行源码时 status=available，许可证未确认时 status=structure-study-only，并在 inspected_candidates 指向实际 implementation_files。不能覆盖已登记 ID 或使用越界路径。
- 自建的 `expanded_search` 至少有两种不同 query 和两个 source，每项含非空 source/query/outcome 与 candidate_ids 数组；无结果为空数组，工具失败写明错误。candidate_ids 登记实际发现的动作相关候选，不是整页无关搜索结果；这些 ID 须有目录或 discovered_candidates 来源，并在 inspected_candidates 完成评估。扩大搜索找到的已登记来源也可选中，不因初轮选择器未召回而拒绝。记录实际查询和结果，不能复制示例伪造执行。
- 新规划根节点 broll_matching_policy 和新选择报告 matching_policy 使用 expression-first-v1，不能通过遗漏字段绕过新研究门。
- `fit` 使用 `selected`、`partial` 或 `rejected`。未选候选必须写非空 `rejection_reason`。
- 选择外部骨架时，`template_id` 写成 `external:<candidate-id>`。
- 从零实现时，`template_id` 才能写 `new:<id>`；所有已检查候选必须为 rejected，提供 custom_reason、borrowed_motion_principles 和实际扩大搜索证据，不能保留尚待适配的 partial 候选直接自建。
- `extracted_skeleton.phase_order` 至少三个可审阅阶段；单纯淡入、背景循环和镜头慢推不算完整骨架。

## SVG 边界

SVG 的适用职责服从 [表达选型](broll-expression-selection.md) 和当前 DESIGN；默认不以临时线稿代替主体素材，用户禁用项必须执行。静态 SVG 文件不能单独满足 no-material + infographic B-roll；动画仍需实际信息阶段、可审阅预览与实际渲染，不能靠路径描入和下划线凑阶段。

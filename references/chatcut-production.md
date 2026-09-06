# ChatCut 主时间线执行

仅在用户指定 ChatCut，或任务要继续现有 ChatCut 项目时读取。本文件规定如何把分镜和外部资产落实成 ChatCut 成片；内容导演、数据契约和 QA 分别以 `directing.md`、`contracts.md`、`qa.md` 为准。

## 1. 确认目标与保护现状

1. 先用 ChatCut Desktop 读取活动项目；按项目 ID 和名称确认目标，不能只凭当前窗口猜测。
2. 读取项目摘要、时间线列表、活动时间线和素材池。记录时间线规格、时长、字幕、轨道、素材类型与数量。
3. 预览时间线结构和代表帧，逐项判断已有 A-roll、有效 B-roll、装饰性占位和空白区间。
4. 不删除素材，不覆盖原时间线。要重组整片时优先复制原时间线为新版本，在副本上工作。
5. 本地文件注册到 ChatCut 后仍要记录原始路径；ChatCut asset ID 不能替代来源记录。

这一步是对已有项目的只读盘点，不是提前开工。新建 ChatCut 项目应延后到视觉编排表和必要的视觉基线通过之后；即使用户一开始就说“新建项目并导出”，也先完成编排门。新项目的职责是承载素材池、主时间线、字幕和最终导出，不负责替代内容理解、视觉编排或 B-roll 模板选择。

盘点输出写入 `planning/project-inventory.json/.md`。只读盘点完成前不得替换时间线素材。

## 2. 从计划到资产

每个镜头的 `production` 必须说明主工具、回退顺序、当前素材状态和缺口。

A-roll：

- 复用符合人物身份和语义的已有场景；
- 固定人物模式按语义组合主持人、主角、配角/旁观者和第一人称视角；
- 连续 A-roll 改变视角、动作、景别或人物与环境的关系，不能全片重复人物居中慢推；
- 静态图只承载一个原子动作和结果，长镜头需要分阶段画面或真实动态素材。
- 按 `action_sequence.beats` 放置状态图或连续动画。4000ms 到 5999ms 至少落实两个状态，6000ms 及以上至少三个；Slow Push 只能作为辅助镜头运动，不能充当动作状态。
- `state-sequence` 在时间线上为每个状态保留可定位的不同素材实例；`continuous-motion` 为每个状态记录同一素材内不同的证据时间点。

B-roll：

1. 已核实截图、录屏、照片、数据和视频直接复用；
2. 关系、流程、对比、因果等无素材信息动画按 [制作工具决策](broll-runtime-selection.md) 使用 HyperFrames 或 Remotion，分别渲染后导入 ChatCut；新制作默认 HyperFrames，成熟效果可原生复用；
3. 需要动态抽象场景时再使用可用视频生成工具；
4. 章节、金句和结论克制使用文字动效，程序化制作同样记录工具决策；只有用户明确改变工具分工时才使用 ChatCut Motion Graphics 作为制作工具；
5. 动态生成失败时按计划回退，不能静默换成无关静态图。

所有 B-roll 按 `motion_sequence.beats` 放置和验收。渲染文件内的 `artifact_time_ms` 是源资产时间，`timeline_at_ms` 是主时间线时间，两者不能混写；每个计划节拍都要在时间线审计中找到实际 item 与 ChatCut asset。

## 3. 镜头渲染与外部仓库

HyperFrames 与 Remotion 都是 B-roll 动效实现层，各自维护源工程，ChatCut 保持唯一主时间线。只调用本镜选中的框架；导入统一规格的完整画面视频，并按原速保持内部旁白节拍。记录实际运行验证和渲染结果，不能把双框架路由文档当作混合制作已验证的证据。

本地模板不匹配时才能研究外部仓库。一次外部来源使用必须同时留下：

- 对应镜头 ID；
- 仓库、具体子目录或源文件；
- 原框架与许可证；
- 提取的元素关系、主要动作和阶段顺序；
- 当前项目中的实现路径与修改说明；
- 通过检查的渲染文件；
- 导入后的 ChatCut asset ID 和时间线 item ID。

`hyperframes-launches` 未确认许可证时只研究抽象结构，重新实现而不复制源码或素材。`video-shotcraft` 先读 `references/shots/` 镜头卡，再读对应 Remotion demo；原生制作或移植均记录 Apache-2.0 来源和修改，工具选择遵循逐镜 `runtime_decision`。

只有仓库链接、研究笔记或本地渲染文件，均不能证明镜头已经进入成片。

## 4. 组装与失败处理

把音频、字幕、A-roll、B-roll、已有素材及 HyperFrames / Remotion 渲染结果放入同一 ChatCut 项目，按 `visual-plan.json` 的镜头边界放置。

- B-roll 区间必须出现对应的信息表达；装饰性静态场景不算覆盖。
- 音频为时间真源，字幕保持原文和时间；画面保留字幕安全区。
- 开头空隙保持首镜，镜头间空隙保持上一镜，尾部保持末镜。
- 一个镜头失败时保留错误记录，尝试声明的回退路径并继续其他镜头。
- 需要真实证据但素材缺失时停止该镜头的真实性实现，不影响其他无依赖镜头继续。

## 5. 样片、审计与导出

先做低成本样片；全片不足 60 秒时可以直接用整条低成本版本。按 `qa.md` 检查并修复后，再扩展高成本资产或最终质量。样片和最终时间线都必须逐镜回填 `visual-plan.json` 的 S001…镜头映射，不能只证明“有音频、有字幕、有一张图”。

`review_mode=manual` 等待用户确认。`review_mode=continuous` 由代理完成同一 QA，记录 `review_source=agent-qa-under-user-authorization` 后继续；计费、账户、发布和系统权限不包含在连续执行授权中。

最终生成 `reports/timeline-audit.json/.md`，逐镜记录：计划时间、实际时间线范围、ChatCut item ID、asset ID、A/B 职责、来源、实现工具和覆盖状态。A-roll 的 `action_sequence` 与 B-roll 的 `motion_sequence` 都逐节拍记录计划 `at_ms`、实际 `timeline_at_ms`、生产证据资产、文件内证据时间和时间线实例；计划多个状态而时间线只放置单张图加推镜、或 B-roll 只有本地渲染而没有时间线 item 时，均判定为未覆盖。所有镜头覆盖、时长和 QA 通过后，使用 ChatCut Desktop 导出最终 MP4，并验证文件存在、非空和时长合理。

交付报告列出实际 A-roll、B-roll、ChatCut 素材、HyperFrames / Remotion 素材、已有文件、开源来源与具体路径、时间线一致性、素材缺口、成片时间线 ID 和最终导出绝对路径。把统一 `final_artifact` 同步写入项目配置、QA 和 manifest，最后按 [qa.md](qa.md) §7 完成 `review`、当前审核模式下的批准和 `final` 校验。

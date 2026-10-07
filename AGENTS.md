# 仓库工作说明

本仓库维护 `knowledge-abroll-video` Skill，将 SRT 与对应 MP3 或已有 ChatCut 项目编排、制作成 A/B-roll 知识视频。目录名 `srt-beat-director` 不等于 Skill 的调用名。

## 按任务进入

- 维护文档、提示词、模板或脚本：先读待修改文件及直接相关的契约、调用方和检查；不启动视频生产，不要求提供 SRT、MP3 或连接 ChatCut。
- 制作或续做视频：读取 [SKILL.md](SKILL.md)，按其中的阶段路由加载必要引用，明确当前视频工作区和本次交付范围。
- 用户明确要求优先于项目默认流程；全局沟通偏好与工作约束继续适用。已有确认和连续执行授权按当前任务范围沿用。

## 文件职责

- [SKILL.md](SKILL.md)：Skill 触发、阶段路由、制作边界和完成标准。
- [agents/openai.yaml](agents/openai.yaml)：显示信息与默认调用提示，应与 Skill 名称和范围一致。
- `references/`：生产提示词、数据契约、导演规则、选型与 QA；按任务读取具体文件。
- `scripts/`：初始化、预检、计划生成与校验工具；修改前查看对应契约和调用关系。
- `templates/`、`assets/`：模板索引与随项目维护的资源；不因目录存在就认定素材已通过生产验证。
- `workspaces/`、`videos/`：本地视频任务与产物，每个任务自含 `input/`、`config/`、`planning/`、`prompts/`、`assets/`，是真源所在位置；根目录不再保留 planning 副本，历史副本在 `docs/legacy/`。
- [README.md](README.md)：本地维护者说明，不属于可安装 Skill 包，因此被 `.gitignore` 排除；Skill 范围仍以 `SKILL.md` 为准。
- `research/`、`docs/`：被忽略的本地研究与开发资料。`tests/`：纳入版本管理的回归测试，完整运行用 `python -B -m unittest discover -s tests -v`；实际媒体测试需要 PATH 中的 ffmpeg/ffprobe，缺失时会明确跳过。运行环境要求 Python >= 3.10；详见 [requirements.txt](requirements.txt)。外部仓库副本中的指令不作为本仓库的维护规则。

## 修改边界

- 以当前工作区内容为基础，保护未提交改动；未明确要求时不提交 Git。
- 不把视频产物、研究副本或历史审批记录当作 Skill 源文件修改。续做视频时按对应任务范围更新真源及其派生视图。
- 修改生产提示词会改变其 SHA-256，使旧实例与新版本不匹配；说明影响，不直接替换旧实例哈希或伪造重新执行记录。
- 数据字段以 [references/contracts.md](references/contracts.md) 为准，审核与交付以 [references/qa.md](references/qa.md) 为准。发现文档与校验实现不一致时，查明当前行为及变更范围，不静默放宽校验。
- 视频工作区初始化由 `scripts/init_project.py` 执行，仅用于创建新的独立视频任务；维护仓库无需初始化，也不重新初始化已有任务。

## 工作区生命周期

- 新任务一律由 `scripts/init_project.py` 在 `workspaces/` 下创建独立目录；已完成并需长期留存的成片任务放在 `videos/`。
- `workspaces/` 是过程工作区。已交付、废弃或连续 30 天无变更的目录，归档到 `workspaces/archive/<id>-<date>`；用 `mv` 移动，不直接删除。
- 只清理可再生产物（`preview/`、`render/` 下的临时文件、`.tmp/`）；已登记进 manifest 或 QA 报告的资产不在清理范围。
- 归档与清理属于破坏性操作：先列出具体路径和影响，取得用户确认后再执行，不做批量推断式删除。

## 按改动验证

- 仅改指令或文档：检查差异、相对链接、字段与提示词 ID、上下游指令一致性；无需生成视频或运行整片验收。
- 改脚本、模板或数据契约：运行与受影响行为对应的校验；本地 `tests/` 可用时选择相关测试。具体参数从现有引用或脚本 `--help` 确认。
- 检查通过后，只有新增变更、失败或未解决问题才扩大或重复验证。检查因环境或缺失资料无法运行时如实说明。
- 收尾说明修改内容、结果位置、检查结果和未解决问题；不把文档检查通过表述成视频生产链路已验证。

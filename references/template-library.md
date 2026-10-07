# 把已完成镜头沉淀为模板

模板库用于减少后续镜头重复研究和实现。当前随包索引为空；候选目录和下述优先级不代表已有可用模板。只维护 Skill 时可完善契约与校验，不启动无输入的视频生产。

模板按主体关系、核心动作、阶段和不变量沉淀，不以原示例题材命名检索能力。登记 motion_tags 支持跨语义召回，保留具体预览和适配边界；本片已有认可镜头可先引用为参考，认证仍需真实渲染、容量、seek 与审核证据。选择流程见 [按视觉表达选型](broll-expression-selection.md)。

外部动作目录的 skeleton、capabilities 和 known_limits 用于检索与适配判断，不能提升为认证证据。同位内容替换须核对载体保持，同位载体替换须核对内容保持；逐项展开须核对前项保留与最终共览；主体让位再揭示引文须核对引用与物件的对应及阅读期。先以不同内容测试这些骨架，再决定认证，不把单片成功或开发用例的检索命中率当作通用质量保证。

## 首批认证顺序

从实际完成并通过 QA 的镜头优先提取以下五类，每类先沉淀一个适用范围窄、可验证的模板：

| 优先结构 | 标准语义 | 必须保留的解释能力 | 容量/节拍检查 |
|---|---|---|---|
| 同维双栏比较 | comparison | 同一维度下两个对象的差异 | 长短文案不改变对齐关系 |
| 步骤路径推进 | causality 或 expansion，按内容判断 | 前后顺序；无因果证据时不得暗示因果 | 3–5 步、逐步触发和末态阅读 |
| 条件筛选收敛 | filtering | 为什么保留、为什么排除 | 选中与淘汰状态均可读 |
| 层级树展开 | hierarchy | 上下级归属 | 层数、分支和中文换行 |
| 文档组件组装 | aggregation | 部件如何形成整体 | 组件归属、最终整体与重叠控制 |

结构相近仍先判断当前语义，不为复用改结论。执行首个具体模板时继续遵守既有外部研究门；成功认证后，相同模板的来源与实现证据直接复用，新镜头只复核文案容量、节拍和 DESIGN。

## 可移植包

每个模板把源码、必要依赖资源、字体（许可证允许时）、短预览、seek/容量截图和审阅记录放在 `templates/library/<template-id>/`。索引所有路径相对视频项目根目录。不要包含 node_modules、缓存或仅在开发机存在的绝对路径。不可分发的字体记录替代和限制，不宣称换字体后仍已验证。

`init_project.py` 为新任务复制索引和整个 library，避免只复制索引却丢失源码及预览；已有任务不重新初始化。认证模板的原文案与测试规格是验证边界，不自动覆盖全部时长、画幅和字数。

## 认证证据

索引使用 contracts §6 的 `metadata_version="1.0"`，`validation_evidence` 指向如下 JSON。下面是字段示例，不是通过记录：

```json
{
  "schema_version": "1.0",
  "template_id": "实际模板 ID",
  "status": "pass",
  "video": {"width": 1920, "height": 1080, "fps": 30},
  "seek_times_ms": [0, 2000, 5000],
  "checks": {"render": "pass", "seek_safe": "pass", "chinese_capacity": "pass", "visual": "pass"},
  "files": [
    {"path": "templates/library/example/index.html", "sha256": "实际源码哈希"},
    {"path": "templates/library/example/preview.mp4", "sha256": "实际渲染哈希"},
    {"path": "templates/library/example/font.woff2", "sha256": "实际字体哈希"},
    {"path": "templates/library/example/review.md", "sha256": "实际审阅记录哈希"}
  ],
  "review": {"source": "user", "evidence": "templates/library/example/review.md"}
}
```

`text_capacity.font_path` 指向实际测试字体。files 还应覆盖导入的脚本、样式、数据和其他实际依赖，不能只绑定入口文件。审阅记录列明渲染命令与日志、开始/变化/结果截图、乱序 seek 对照、中文容量上限测试、许可证、限制及实际审核来源。只有用户已授权自检时，source 才能用 `agent-qa-under-user-authorization`；脚本校验无法证明这项授权真实存在。

完成真实检查后再写 `animation_status="animation-verified"`。未完成时保留 `implementation-required`，不填虚假通过证据。运行：

```text
python scripts/validate_template_index.py --index templates/template-index.json --out .tmp/template-library-validation.json
python scripts/validate_semantic_map.py --mapping references/semantic-template-map.json --template-index templates/template-index.json --out .tmp/semantic-map-validation.json
```

索引校验会核对认证报告、源码/预览/字体及列出的依赖哈希；选择器 CLI 会先执行该检查。更新源码或资源后旧认证失效，重新渲染和复核再更新证据。认证记录验证仍不替代实际画面审阅。

## 已认证模板入库

`scripts/promote_template.py` 只接收来源索引中已有的 `metadata_version="1.0"`、`animation_status="animation-verified"` 条目，不从历史成片自动推导认证。不运行渲染，不创建或改写审核证据，默认只读预检：

```text
python scripts/promote_template.py --source-project <project> --target-project <skill-root> --template-id <id>
```

可分发包须在 `templates/library/<id>/`，全部包内文件（认证 JSON 自身除外）精确登记到认证 files，报告及其引用也在同一包内。源码、预览、字体、许可证、依赖清单/锁文件、截图和审核记录不得遗漏，不能含包外文件、链接、node_modules 或缓存。`source.license_evidence` 指向包内并绑定哈希的实际分发依据，覆盖源码和资源许可；工具不能代替许可证内容审查。

新认证时增加 `template_sha256`：对完整索引条目执行排序键、紧凑分隔符、ensure_ascii=false 的 UTF-8 JSON SHA-256（`validate_template_index.template_digest`），以防未经复核扩大字数/画幅/时长或改写替换字段。实际完成脱离原工作区的依赖与复现检查后，增加 `checks.portable="pass"`，具体步骤和结果记入已绑定的 review.md。不要只为入库补写历史通过记录；旧证据需真实重新检查后另存。

预检核对现有认证、全包哈希及实际解码预览的宽高/帧率与 seek 时间边界。通过后显式加 `--apply`，原样复制包并追加目标索引，不覆盖已有 ID/目录，不更新来源工作区、不重算认证。复制失败时不登记索引，保留失败目录供检查；先核对具体路径再决定后续处理。通过入库检查仍不证明 seek 的视觉确定性、中文容量或审核授权真实存在，须保留相应实际检查与来源。该工具不把一次镜头的成功扩展成全部参数范围的通用认证。

检索回归使用 `scripts/evaluate_broll_retrieval.py --repositories-root <repositories> --semantic-map references/semantic-template-map.json --cases tests/fixtures/broll-retrieval-cases.json --out <review-output>.json`。随包用例覆盖已知中英动作查询，属于开发回归集；新项目需保留未参与调参的查询、可接受候选标注和用户返工原因，另测首次召回、选型适配和首稿质量，不混用这些指标。

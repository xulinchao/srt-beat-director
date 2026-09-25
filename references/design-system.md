# DESIGN 接入与角色互动

## 真源、版本与复用

新任务在 `config/project.json` 写 `design_contract_version: "1.0"`。视觉设计前从 [DESIGN 模板](../templates/DESIGN.md) 创建 `config/DESIGN.md`。账号规范可保存在输入目录的版本文件中，单片的 `account` 用 `{path, version, sha256}` 引用（路径相对单片 DESIGN）；不复制整份规范。账号仅允许一层引用，不递归继承。

DESIGN 的唯一 `design-spec` 块管可检查的视觉参数，正文管画法、表现和例外；两者均受整个文件的哈希绑定。用户当前明确要求优先；落实到单片差异再复核，不能绕过身份参考授权。单片 `rules` 的一级键覆盖账号同名键，未覆盖的继承账号；数组整体替换。`video` 与字幕区还须与 project.json 一致，冲突时报错，不暗选一份。

`config/visual-style.json.design_ref` 和计划根 `design_ref` 均为 `{path: "config/DESIGN.md", version, sha256}`（路径相对项目）。visual-style 保留审批、candidate_review 及已有执行记录；其 `resolved_design` 是 DESIGN 合并后 rules 的派生快照，不独立编辑。character-bible 和 reference index 继续管身份及授权范围，不在 DESIGN 重写身份锁定。生产实例和 B-roll 选择报告的 `design_ref` 复制同一引用；实际提示词必须展开本镜适用规则及角色互动方案，不只写路径。

`visual-style.json.design_review` 使用 `{status, review_source, evidence, sha256}`。status 为 `draft`、`pending-user-review`、`approved` 或 `stale`；sha256 绑定当前单片 DESIGN；evidence 为可核对的审阅记录文件（相对项目），写明审核人/来源、时间、实际意见和样张。代理自检仅在 continuous 授权下使用 `agent-qa-under-user-authorization`；只有真实用户确认才用 `user`。项目既有 visual_baseline 门和 candidate_review 继续保留，不用此记录代替原门控。

已有已确认且适用的账号规范和样张可直接引用；单片无新视觉决定时，在证据中记录复用依据，不重复要求选风格。有新方向时，用真实文案挑选代表 A/B、角色互动、高信息量镜头，先审阅开始/变化/结果静帧，再制作带原口播的短片，经 QA 后扩大生产。manual/continuous 沿用已有授权，不增设逐镜门。规范缺失可继续内容分析和草稿，不能把暂定配色当批准基线。

修改 DESIGN 或其账号引用时列明受影响 shot ID、参数和原因，记到既有计划 risk/production.asset_gap；受影响镜头及依赖样片/最终状态置 stale，未受影响素材可按哈希复用。全文件哈希不符必须复核引用与审批，不直接改旧审批哈希，不默认重做全片。旧任务没有 design_contract_version 时保留兼容提示；本轮不批量迁移旧工作区。旧任务开始采用此流程时显式登记版本并补齐当前阶段字段。

## 逐镜编排

固定 IP 不是默认画面资产。用户明确要求设计或使用 IP、且未说明 B-roll 用途时，在视觉编排前只询问一次是否让它参与 B-roll；已有答复直接沿用，记录选择及使用范围到单片 DESIGN 的“角色参与图解”。用户未提出 IP 时不主动设计。普通剧情人物不自动获得跨镜头 IP 身份。即使用户同意 IP 参与，也先判断它在本镜是否能指示、承载、操作或回应信息；不能因它存在就塞进真实截图、密集文字或每个信息镜头。人物身份和视觉系统分别受参考用途与 DESIGN 约束。

顺序：viewer_takeaway → 功能 → 主体关系 → 载体 → 必要变化 → DESIGN 适配。`visual_design` 增加非空 `function`、`relation`、`carrier`、`character_role`；最后一项可以写“不出现：没有解释收益”。解释、例证、强调、导航、氛围可交叉，是选型标签而非密度排序。例子、模拟、作者引文、转述和个人判断须有清楚归属。一个理解任务用一个主结构，允许原图递进。

复杂互动才增加 `visual_design.interaction`：

```json
{
  "participants": ["character", "object-left"],
  "layout": "人物居中，左掌承载小对象，右侧留阅读区",
  "occlusion": "掌心在对象后，前侧手指遮挡对象下缘",
  "events": [
    {"beat_index": 0, "offset_ms": 0, "duration_ms": 500,
     "actor": "object-left", "target": "character", "action": "落到左掌后停住",
     "contact": "对象底部对齐左掌锚点", "reaction": "接触后手臂承重"}
  ],
  "assets": [{"id": "character", "path": "assets/b-scenes/character.png"}],
  "fallback": "动作失败时改为逐项指示，保留对象归属并重新审核受影响节拍"
}
```

beat_index 为 narration_beats 的零起点索引；event 时间为该 beat.at_ms + offset_ms，offset_ms 非负，结束不得越过下一 beat 或镜头终点。它只描述节拍内入场/接触/反应，不新增语义触发点。普通镜头用 changes 即可。参与对象必须可定位；无接触时 contact 写“无接触”并说明空间关系。assets 只登记实际准备使用的分层文件；准备期缺失登记 asset_gap，produced 时文件必须存在。

道童可沿路径导航、托举小对象、逐项指示或操作筛选，不能按信息类型自动指定动作。无真实量值时路径不用精确百分比；相关性不可画成因果触发。大卡片保证文字容量，人物退到侧边、头像/手部或退出，不挤字幕。

双手展示示例需按口播让对象落到对应手掌，接触后停住，再安排视线和无奈反应；不是各素材独立播放。分层制作优先使用一致身份的透明人物状态、独立文字/图片/物品、锚点与遮罩，必要时采用骨骼或状态切换。文字由实际字体排版，不以生成完整含字图片作为通用路径。素材或动作失败先记录具体缺口，再提出保留语义的替代并复核；不能偷偷改成贴纸加卡片。

## 校验与实际画面

运行 `python scripts/validate_design.py --project-dir <project> --stage planning|prepared|produced`；提示词校验会调用同一检查，状态校验复查引用。planning 允许设计待确认，prepared 要求设计审批和规则齐全，produced 检查互动资产存在。脚本检查引用、哈希、字体文件、参数、节拍及派生快照；不证明字体实际载入或视觉质量。

实际样片检查人物一致性、信息密度、手部接触、遮挡、阅读停留、角色是否抢信息和连续镜头协调；保留 qa.md 的音画同步、确定性 seek、字体载入、帧数与黑闪验收。换文案后重新检查容量、换行和阅读时间，网页正常不能代替成片验证。

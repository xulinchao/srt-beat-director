# 单片设计规范

复制到视频工作区 `config/DESIGN.md`，填入实际规格。以下唯一 `design-spec` JSON 块供校验读取；空值表示尚未确定，不能用于生产。账号规范使用同一格式，设 `scope=account`、`account=null`，存为可随项目取得的版本文件。单片只填写差异；`rules` 按一级键覆盖账号规则，数组整体替换。

```design-spec
{
  "schema_version": "1.0",
  "scope": "film",
  "version": "draft-1",
  "account": null,
  "rules": {},
  "samples": []
}
```

## 人物与场景

默认不设计固定 IP；用户明确要求设计或使用 IP 时，引用 `input/references/index.json` 的人物 ID，身份锁定仍由参考索引和 character-bible 管理。填写实际使用人物的头身比例、动作尺度、基础画法、必要道具、场景密度和可接受景别。头像、手部或全身按信息任务选择，不预设每镜姿势。

## 字体与空间

在 rules 填写 `fonts`（对象数组，每项 family、path）、`font_sizes`（标题/正文/标注的像素值）、`max_chars_per_line`、`max_lines`、`margin_fraction`、`subtitle_bottom_fraction`、`video`（width、height、fps、aspect_ratio）。字体路径相对当前 DESIGN 文件；必须是实际可用文件。说明目标观看尺寸、换行规则、文字超容量时如何删减或拆分；不靠缩小到不可读解决。

## 色彩与图形

在 rules 填写 `colors`（颜色职责到具体色值）、`graphic_language`（线宽、箭头、标签、引用标识）、`character_direction`、`scene_density`、`motion`（入场、变化、强调、退出、阅读停留）、`exceptions`（特例及理由）。不预填账号最终画风。真实截图保留原色，样式不能改变信息含义。

## 角色参与图解

用户明确要求 IP 且未说明 B-roll 用途时，只询问一次是否让它参与；已有答复直接记录选择与适用范围，未提出 IP 时写明本片不设计固定 IP。若启用，说明何时展示、指示、操作、承载或反应，以及缩小、移侧、改头像/手部或退出的条件；并非每个 B-roll 都必须出现。信息和字幕优先；复杂互动依 references/design-system.md 的计划字段记录接触和遮挡，不在本文维护逐镜时刻。

## 样张与审阅

`samples` 填写可比对的真实样张引用 `{ "path": "../preview/styleframe.png", "sha256": "实际哈希" }`，路径相对本文。描述开始、变化、结果与适用条件。审批状态及证据只写在 visual-style.json 的 design_review；本文件标题、版本号或代理生成行为均不代表用户批准。

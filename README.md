# srt-beat-director（本地工作仓库）

本仓库维护 Skill **`knowledge-abroll-video`**：把 SRT 与对应 MP3，或已有 ChatCut 项目，制作成 A-roll 讲人、B-roll 讲内容的不露脸知识视频。

**目录名不等于 Skill 调用名。** 调用时使用 `knowledge-abroll-video`；目录名 `srt-beat-director` 是历史遗留，不代表当前范围。

## 仓库内容

三类内容混装，版本管理边界不同：

| 内容 | 位置 | Git |
|---|---|---|
| Skill 包（可分发） | `SKILL.md`、`references/`、`scripts/`、`templates/`、`agents/` | 纳入版本管理 |
| 本地视频任务 | `workspaces/`、`videos/` | 已忽略 |
| 本地研究与开发资料 | `research/`、`docs/`、`workflows/` | 已忽略 |

本文件面向本地维护者，不属于可安装的 Skill 包，因此被 `.gitignore` 排除。Skill 的触发条件、阶段路由和完成标准一律以 `SKILL.md` 与 `agents/openai.yaml` 为准。

## 真源位置

视频任务真源在 `videos/<project-id>/` 与 `workspaces/<workspace-id>/`，每个任务自含 `input/`、`config/`、`planning/`、`prompts/`、`assets/`。仓库根目录不再保留 planning 副本；历史副本见 `docs/legacy/`。

## 常用命令

```text
python -B -m unittest discover -s tests -v
```

完整回归需要 PATH 中的 ffmpeg/ffprobe，缺失时媒体相关用例会明确跳过，不算失败。

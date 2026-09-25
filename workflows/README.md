# ComfyUI 共享工作流

这里保存 Skill 级的 ComfyUI API 工作流。视频任务只传入自己的首帧、尾帧、提示词和输出目录；不在视频任务里维护工作流副本。

## 图片关键帧

| 文件 | 用途 | 默认设置 |
|---|---|---|
| `qwen_image_2_1_t2i_api.json` | 没有参考图时生成首帧或独立 B-roll 图片 | INT8 模型，25 步，16:9、约 1 MP |
| `qwen_image_2_1_edit_keyframe_api.json` | 从已有首帧编辑出同一镜头的下一状态图 | 单张参考图，INT8 模型、Cache、25 步；默认沿用参考图尺寸 |

两份工作流来自用户提供的 Qwen Image 2.1 API 文件，保留本机已有的模型和采样配置，移除了特定视频项目的长提示词及换衣服示例。编辑版默认以参考图潜空间为输出尺寸；通过执行器同时传入 `--width`、`--height` 时，会切换到指定尺寸的空潜空间。首尾关键帧应在人物、机位、背景和画幅上一致，仅改变动作状态。图片输出仍需人工检查，再作为 H3 FL2V 的输入。

```powershell
python scripts/run_comfyui_image_workflow.py --workflow workflows/qwen_image_2_1_t2i_api.json --prompt "<首帧描述>" --out-dir <视频任务>/assets/generated-images --dry-run
python scripts/run_comfyui_image_workflow.py --workflow workflows/qwen_image_2_1_edit_keyframe_api.json --input <首帧.png> --prompt "<保持人物与场景，只改变动作状态>" --out-dir <视频任务>/assets/generated-images --dry-run
```

这里的 INT8、25 步是可运行的基线选择，不是经过本机耗时/画质对照证明的最优值；后续 H3 工作流已按官方接法增加 KJNodes Sage Attention `auto`，但效果仍需本机 A/B 验证。

## MiniMax H3 视频

| 文件 | 用途 | 默认加速 |
|---|---|---|
| `minimax_h3_fl2v_turbo_api.json` | 首尾两张状态图之间生成连续动作 | FL2V Turbo LoRA，8 步 |
| `minimax_h3_fl2v_turbo_native_api.json` | 首尾帧的高原生画质版本，H3 直接输出生成分辨率，不做任何超分或重缩放 | Turbo 8 步 + KJNodes Sage `auto`；1344×768（0.98 MP）、原生 24 fps |
| `minimax_h3_i2v_turbo_api.json` | 只有首帧时生成后续动作 | FL2V Turbo LoRA，8 步 |
| `minimax_h3_r2v_turbo_api.json` | 两张参考图约束主体或风格 | R2V Turbo LoRA，4 步 |
| `minimax_h3_r2v_3ref_optimized_api.json` | 三张参考图与结构化提示词，适合多主体剧情镜头 | R2V Turbo LoRA，4 步；可切回 20 步对照 |

基础 FL2V、I2V、R2V 文件以本机保存的 ComfyUI 官方模板 API 请求为起点整理，明确打开 Turbo 开关、保留与之联动的采样步数，并移除输出音轨。基础版默认 24 fps、约 0.4 MP、124 帧的 H.264 MP4，用于先验证动作；原生版把默认画布提到约 0.98 MP，分辨率与默认 0.4 MP 的差异见上表。镜头确实需要生成式连续动作时，`FL2V` 是两张相近状态图之间的首选；定格动画由状态图按设计节奏切换，不需要 H3 插帧。`R2V` 不保证最后一帧落在第二张参考图上。

三参考图版直接从用户提供的 API 工作流整理；[原件副本](source/minimax_h3_multi_ref_user_original_api.json)只作对照，不用于生产。[原始提示词](source/minimax_h3_multi_ref_user_original_prompt.txt)单独保存，可通过 `--prompt-file` 使用。优化版保留三个参考图槽和 `subject_definitions` / `summary` / `retention_analysis` / `detailed_description` 提示词结构；此前基于错误 Python 环境探测移除了 Sage 节点，后经实际 ComfyUI `.venv` 确认 SageAttention 1.0.6 可用，现已恢复 `PathchSageAttentionKJ` 的 `auto` patch。优化版还移除 20 步上的 EasyCache 和重复编码输出，换成本机已有的 pruned INT8 模型、低显存文本编码器及 R2V Turbo LoRA。默认 4 步、约 0.4 MP、124 帧；节点 `247` 改为 `false` 会同时切回基础模型与 20 步采样，用同一 seed 比较动作和细节。

正式 FL2V 默认使用原生版，固定 `1344×768`、Turbo 8 步、24 fps、124 帧；直接 `VAEDecode → CreateVideo → SaveVideo`，不增加超分、latent 放大或二次采样，以控制生成耗时。基础 0.4 MP 版本仅供按需验证动作，不要求每个镜头先生成低清再生成正式版。

分辨率选择器当前为 `megapixels: 0.98`、`multiple: 32`。本机节点使用 `MP × 1024 × 1024` 并将宽高各自四舍五入到 32 的倍数：`0.98` 得到 `1344×768`，`0.9` 得到 `1280×736`。需要确定尺寸时同时传入 `--width 1344 --height 768`，执行器直接覆盖 H3 输入。

`1344×768` 并非精确 16:9。若最终时间线为 1920×1080，在 ChatCut 按镜头构图选择等比裁切或留边，不拉伸人物；时间线适配不触发额外 AI 生成。三个 `.json.removed` 文件仅保留停用备份，不作为生产入口，执行器拒绝提交。

H3 模型路径配置请求 KJNodes `PathchSageAttentionKJ` 的 `auto`。本机 ComfyUI `.venv` 已装 SageAttention `2.2.0+cu130torch2.10.0andhigher.post6`（Torch `2.10.0+cu130`），但仍然需要用相同 seed、帧数、分辨率与 SDPA 基线做真实对照，不把可导入等同于更快。本机无 `sageattn3`，不要把 SageAttention 3 写成已启用。


```powershell
python scripts/run_comfyui_workflow.py --workflow workflows/minimax_h3_fl2v_turbo_native_api.json --first-frame <首帧.png> --last-frame <尾帧.png> --width 1344 --height 768 --prompt "清楚描述首尾状态之间的物品交接动作" --out-dir <视频任务>/assets/video-scenes --dry-run
```

确认 dry-run 请求后去掉 `--dry-run` 生成。输出为 H3 原生 24 fps、无音轨，分辨率即 H3 的生成画布（默认 `1344×768`）；接入 `1920×1080` 时间线时的放大交给后期链路，不在本工作流内做。原生版也不替代镜头动作审核。

原件的三个 `pasted/…png` 输入文件当前在 ComfyUI input 目录下不存在。执行三参考图版时，通过 `--reference-frame` 按主体 1、主体 2、场景/主体 3 的顺序传入三个实际文件。

```powershell
python scripts/run_comfyui_workflow.py --workflow workflows/minimax_h3_r2v_3ref_optimized_api.json --reference-frame <主体1.png> --reference-frame <主体2.png> --reference-frame <场景.png> --prompt-file workflows/source/minimax_h3_multi_ref_user_original_prompt.txt --out-dir <视频任务>/assets/video-scenes --dry-run
```

执行方式、环境探测和 Sage Attention 的可用条件见 [ComfyUI 视频资产生产](../references/comfyui-video-production.md)。这些是 API 格式 JSON，供仓库脚本提交；不是带画布布局的 ComfyUI 原生编辑文件。


## 设计图参考动效（带同步音效）

[minimax_h3_motion_ref_audio_api.json](minimax_h3_motion_ref_audio_api.json) 是从用户修复版适配的单图 `Ref2VA + native` 音视频分支：1344×768、24 fps，无视频超分。保留视频 8 / 音频 10 的实验采样组合，默认 209 帧（约 8.708 秒）。图片是参考而非精确首帧；音轨保留以便后期混音。执行命令、静帧规则及未验证边界见 [视频生产说明](../references/comfyui-video-production.md#设计图参考动效与同步音效)。

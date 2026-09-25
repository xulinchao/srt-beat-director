# ComfyUI 视频资产生产

ComfyUI/MiniMax H3 是逐镜视频资产生产器，不是主时间线。它可制作计划明确的连续动作，也可在设计需要首尾帧间生成运动、呈现定格动画质感时作为一种镜头实现；A/B 职责沿用叙事计划，H3 两类都能制作。定格动画仍可按独立状态图的停留与跳变制作，不默认交给 H3；信息图和文字动效优先使用能保证精确排版与旁白节拍的工具。镜头计划、字幕和最终导出仍由 ChatCut 主时间线管理。

## 运行前环境检查

执行视频资产生产前，先运行：

```text
python scripts/inspect_comfyui.py --url http://127.0.0.1:8188 --out-dir <project>/planning/comfyui
```

检查必须确认 `/system_stats` 可访问、CUDA 设备可见、ComfyUI input/output 目录可读写，并记录工作流节点依赖。工作流文件在本 Skill 仓库的 `workflows/`，具体视频任务只保存输入图、请求快照和生成结果。模型或自定义节点缺失会在提交时报告；实际输出仍须用 `ffprobe` 和视觉检查确认。环境检查失败时只阻塞依赖 ComfyUI 的镜头，不把静态图片冒充视频资产。

## 工作流选择

| 工作流 | 输入 | 适用场景 | 默认级别 |
|---|---|---|---|
| `workflows/minimax_h3_fl2v_turbo_api.json` | 首帧、尾帧、运动提示词 | 两张状态图之间生成连续动作 | 仅按需用于低成本动作预览；Turbo LoRA 8 步 |
| `workflows/minimax_h3_fl2v_turbo_native_api.json` | 首帧、尾帧、运动提示词 | 正式首尾帧镜头的默认入口 | H3 1344×768、Turbo 8 步、KJNodes Sage `auto`；VAE 解码后直出，无超分无重缩放 |
| `workflows/minimax_h3_i2v_turbo_api.json` | 首帧、运动提示词 | 只有起始设计图，尾帧由模型推导 | 尾帧缺失时使用；Turbo LoRA 8 步 |
| `workflows/minimax_h3_r2v_turbo_api.json` | 两张参考图、运动提示词 | 需要角色或场景参考，但不要求严格尾帧落点 | 参考驱动镜头；Turbo LoRA 4 步 |
| `workflows/minimax_h3_r2v_3ref_optimized_api.json` | 三张参考图、结构化提示词 | 多主体或场景剧情演绎；由用户提供的多图工作流优化 | Turbo LoRA 4 步，可切换 20 步对照 |

选用 H3 且设计了准确首尾状态时，`fl2v` 优先，因为 `MiniMaxH3ImageToVideo` 同时暴露 `first_frame`、`last_frame` 和 `prompt`。`i2v` 没有 `last_frame`，不能承担需要状态准确落点的镜头。`r2v` 与多图参考工作流适合参考一致性，不等于首尾帧约束。这里的优先级只在已选 H3 的镜头内生效；不把所有定格动画或信息动效自动改成生成式视频。

这五个文件是供 `scripts/run_comfyui_workflow.py` 提交的 **API 格式**工作流，属于 Skill 源文件，不复制到每个视频任务。前三个根据本机保存的官方导出请求整理，三参考图版根据用户提供的原件整理；Turbo 开关已打开，模型和采样步数由同一个开关同时切换。输出为 24 fps H.264 MP4，移除了生成音频的解码与封装。正式 FL2V 默认原生版 1344×768、124 帧；其他基础版本约 0.4 MP。动作预览按需执行，不要求正式镜头重复生成。`fl2v` 的首尾帧可由默认 GPT Image 2 制作；优先从同一已核实参考生成首帧，再编辑尾帧。提交前核对人物身份、服装、道具、背景、机位、画幅和动作方向，提示词写清具体动作、固定元素与最终落点。不因选择 H3 而强制改用本地图片工作流。

正式 FL2V 使用 `minimax_h3_fl2v_turbo_native_api.json`：1344×768、Turbo 8 步、24 fps，无音轨；`VAEDecode → CreateVideo → SaveVideo`，没有超分、latent 放大、二次采样或解码后的重缩放。停用工作流保留为 `.json.removed` 备份，不可提交。

节点 `115` 的 `megapixels: 0.98`、`multiple: 32` 对应 1344×768；`0.9` 对应 1280×736，不等同于 1344。正式命令显式传入宽高以固定尺寸。该画幅略偏离 16:9，接入 1920×1080 时间线时按构图选择等比裁切或留边，避免拉伸。镜头生成尺寸与最终导出尺寸分别记录，不把最终 1080p 规格反向用于提高 H3 生成成本。

所有 H3 工作流配置 KJNodes `PathchSageAttentionKJ` 的 `auto`。仍需和 SDPA 基线比较速度、稳定性和画质；不把节点配置当作已运行成功的证据。原生输出仍需检查人物、手部、道具与帧间一致性。

Sage Attention 是 Turbo 之外的注意力加速。此前误用 `standalone-env` 探测，得出“ComfyUI 没有 SageAttention”的结论；实际 ComfyUI `.venv` 是 Torch `2.10.0+cu130`，已安装 SageAttention `2.2.0+cu130torch2.10.0andhigher.post6`（此前曾为 `1.0.6`，2026-09-24 升级并已在 GPU 上实测通过：`sageattn_qk_int8_pv_fp16_cuda` 后端在 sm_120 可用，纯注意力内核相对 SDPA 约 5.8×），KJNodes `PathchSageAttentionKJ` 也已注册，但没有 `sageattn3`。所有项目级 H3 视频工作流均配置 KJNodes Sage `auto` patch。这些设置仍须用相同 seed、帧数、分辨率与 SDPA 基线做真实对照，不把可导入等同于内核已成功或保证更快。参见 [ComfyUI 官方 H3 加速说明](https://github.com/Comfy-Org/docs/blob/main/tutorials/video/minimax/minimax-h3.mdx)。

## 镜头数据

以下是镜头 `production` 对象，`screen_role` 保存在镜头根节点。人物叙事使用 A-roll 的 `action_sequence`，解释性动画使用 B-roll 的 `motion_sequence`；两者都按既定旁白节拍映射到生成视频内的实际状态。

```json
{
  "primary_tool": "comfyui-minimax-h3-fl2v",
  "fallback_tools": ["existing-media", "chatcut-image"],
  "asset_status": "to-generate",
  "video_generation": {
    "workflow": "workflows/minimax_h3_fl2v_turbo_native_api.json",
    "first_frame": "assets/a-scenes/S001-state-01.png",
    "last_frame": "assets/a-scenes/S001-state-02.png",
    "motion_prompt": "固定机位，主角递出纸包，店主接过后抬手微笑，只改变手和表情，保持人物、道具、背景和画幅一致。",
    "width": 1344,
    "height": 768,
    "fps": 24,
    "duration_frames": 124,
    "seed": 123456
  }
}
```

一个镜头有多个旁白节拍时，优先按节拍生成短片段；一条视频覆盖多个节拍时，必须记录每个节拍在视频内的 `artifact_time_ms`。
`i2v` 记录 `first_frame`；两参考图 `r2v` 在 `video_generation.reference_frames` 按输入槽顺序记录 2 张图，三参考图版记录 3 张图，不将参考图伪称为必须落点的 `first_frame` / `last_frame`。

## 执行与落档

调用者从镜头记录取参数传给执行器。执行器复制首尾帧到 ComfyUI input 目录，替换 workflow 的 `LoadImage.image`、MiniMax-H3 节点的 `prompt`、`length` 和 seed，通过 `/prompt` 提交，轮询 `/history/{prompt_id}`，定位 `SaveVideo` 输出并复制到任务资产目录。随后单独用 `ffprobe` 校验实际帧率、分辨率、帧数、时长和音轨，通过后导入 ChatCut，并回写 ChatCut asset ID 与 timeline item ID；当前执行器本身尚不完成媒体检查和 ChatCut 登记。

仓库提供的最小执行器是 `scripts/run_comfyui_workflow.py`。先用 `--dry-run` 检查请求，再去掉该参数提交；FL2V 传 `--first-frame`、`--last-frame`，参考图工作流按图槽顺序重复传 `--reference-frame`，运动提示词通过 `--prompt` 或 `--prompt-file` 传入。`--workflow` 使用本仓库路径，`--out-dir` 使用本次视频任务的资产目录。例如在仓库根目录执行：

```powershell
python scripts/run_comfyui_workflow.py --workflow workflows/minimax_h3_fl2v_turbo_native_api.json --width 1344 --height 768 --first-frame <首帧.png> --last-frame <尾帧.png> --prompt "主体自然走向尾帧位置，保持背景和机位不变" --out-dir <视频任务>/assets/video-scenes --dry-run
```

原生版正式镜头示例（不要求先运行低清版）：

```powershell
python scripts/run_comfyui_workflow.py --workflow workflows/minimax_h3_fl2v_turbo_native_api.json --first-frame <首帧.png> --last-frame <尾帧.png> --width 1344 --height 768 --prompt "清楚描述首尾状态之间的物品交接动作" --out-dir <视频任务>/assets/video-scenes --dry-run
```

该图在 ComfyUI 队列里只有 H3 生成与封装两段：`VAEDecode` → `CreateVideo(24 fps)` → `SaveVideo`，中间没有超分级联，因此不增加超分模型加载与二次采样的耗时。API 执行器会复制首尾帧并改写 H3 提示词/帧数/尺寸。先 dry-run 核对首尾图和 H3 的 `1344×768` 输入，确认后再提交正式任务。

执行器只负责生成和回收视频，不代替 ChatCut 导入和时间线登记。MiniMax H3 原生 24 fps；若项目时间线采用 30 fps，必须在导入和逐镜审核时处理帧率差异，不能把计划中的 30 fps 当成模型实际输出帧率。

基础视频工作流输出无音轨视频；下述动效音视频分支保留原生音轨。旁白、字幕和最终混音由 ChatCut 主时间线管理。

生成后先核对首尾状态是否与输入对应，再检查中段的人物身份漂移、道具或背景变形、动作断裂、重复帧和意外闪变；符合设计的片段才登记为可用资产。定格动画按计划的停留时长、跳变时点与旁白节拍检查，不用连续动作的流畅度标准否定刻意跳变。最终导出仍按 [QA](qa.md) 全片扫描和逐镜复核。

失败时保留错误记录和 workflow 快照。只有镜头记录声明了回退工具，才能回退到已有视频或静态图。


## 设计图参考动效与同步音效

`workflows/minimax_h3_motion_ref_audio_api.json` 从用户修复的 Work-Fisher API 工作流适配，采用 `MiniMaxH3AudioConditioningT8` 的 `Ref2VA + native`。保持用户已修好的 Ref2VA 模型、Turbo LoRA、专用 Sage 节点与采样参数；移除未接入输出的孤立节点。它是待实际生成验收的独立候选分支，不替换原 FL2V 无音轨流程。

- 参考图用于主体、布局和风格，不保证成为首帧；严格端点镜头继续使用 FL2V/I2V。
- 动效设计图用 GPT 时直接请求 2048×1152；用 ComfyUI 生图时，在构图确认后进行静帧二采精修，再核对真实尺寸、人物、文字与几何。普通插值放大不算二采。当前仓库 Qwen 工作流还未实现这一步，不得把单采结果标成二采完成；缺少已验证二采工作流时记录阻塞。该要求仅适用于动效设计图，不推广到所有图片。
- 视频默认 1344×768、24 fps，不做视频超分。时长节点为 8 秒，按 H3 的 17n+5 网格得到 209 帧，约 8.708 秒；按旁白修改 `--length` 并核对实际输出，不用提示词中的秒数代替节点参数。
- 当前保留视频 8 步、音频 10 步；联合模型调用约 10 次，不能按 LoRA 名称宣称只运行 4 步。降到其他步数组合需另做画质和声音对照，不宣称已经优化速度。
- 按动作生成短音效，默认不生成对白、旁白或 BGM。提示词不保证音轨干净，生成后必须试听；可读标题、数值和精确 UI 交给 HyperFrames/Remotion。
- 输入 2048×1152 不等于模型内部完整保留此尺寸，参考编码可能缩放；输出尺寸由视频节点控制。

```powershell
python scripts/run_comfyui_workflow.py --workflow workflows/minimax_h3_motion_ref_audio_api.json --reference-frame <设计图.png> --prompt-file <本镜动作与音效.txt> --out-dir <视频任务>/assets/video-scenes --dry-run
```

这是 API JSON，通过执行器提交。`--dry-run` 仅做离线请求编排，不验证 GPU 生成。T8 分支必须使用 `--reference-frame`，不能把参考图作为 `--first-frame` 传入。当前镜头计划校验中 `comfyui-minimax-h3-r2v` 要求两张参考图，此单图音视频分支暂不登记为该 runtime，也不伪造第二张图；先作为资产生产候选，实际生成验收后以 `existing-media` 引入计划。

MP4 保留生成音轨。接入主时间线时按 [动作音效](sound-design.md) 拆轨、对齐和试听；已有合适声音直接复用，禁止再叠一份相同音效。若出现无关对白、音乐或噪声，只替换音效即可解决时不重生成画面。实际画面、音轨、帧数、时长、速度均需样片验收。

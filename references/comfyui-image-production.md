# ComfyUI 本地图片资产生产

本文件仅在用户另行明确更改内置出图要求、指定本地生成时使用。内置工具不可用或限流时，按 [出图停止规则](image-generation-policy.md) 执行全局停止；选用 H3 连续动作也不构成本地出图授权。获授权的 ComfyUI 仅承担图片生成/编辑，ChatCut 仍负责主时间线、字幕、旁白、声音和导出；生成结果必须先落到项目资产目录并登记来源。

## 用户指定的本地路由

核实用户已明确更改本次出图要求，把本镜 `production.runtime_decision.mode` 设为 `user-request`，在 `user_request` 记录原话、在 `reason` 写明原因；不能填写 `fallback` 或 `capability-exception` 绕过停止门。本地工作流只在环境探测通过、模型与节点可用时进入生产；探测失败时保留缺口，不把未生成的占位图登记为可用资产。需要将图片交给 H3 制作连续动作时，优先从同一参考生成首帧并编辑尾帧，检查身份、服装、道具、背景、机位、画幅和动作落点；不独立随机生成两张相似图后直接提交。

| 工作流 | 输入 | 适用场景 | runtime |
|---|---|---|---|
| `workflows/qwen_image_2_1_t2i_api.json` | 文本 | Qwen Image 2.1 文生图，可作为首帧 | `comfyui-qwen21-t2i` |
| `workflows/qwen_image_2_1_edit_keyframe_api.json` | 1 张首帧 + 编辑提示词 | 生成同一镜头的下一状态图 | `comfyui-qwen21-edit` |
| `edit_qwen21_multi2/4/6.json` | 2 / 4 / 6 张参考图 + 文本 | 多参考一致性 | 对应 `comfyui-qwen21-multi2/4/6` |
| `edit_qwen_image_edit_2509.json` | 1 张输入图 + 编辑提示词 | 普通图像编辑 | `comfyui-qwen-edit-2509` |
| `edit_qwen_image_edit_2509_faceswap.json` | 原图 + 人脸参考图 | 换脸或身份替换 | `comfyui-qwen-edit-2509-faceswap` |
| `edit_qwen_multi.json` / `_hq.json` | 3 张参考图 + 编辑提示词 | 多图编辑；`_hq` 与普通版拓扑相同，仅切换质量/缓存开关 | `comfyui-qwen-edit-multi` / `comfyui-qwen-edit-multi-hq` |
| `edit_qwen_masked.json` | 3 张参考图 + mask | 局部区域编辑 | `comfyui-qwen-edit-masked` |
| `t2i_z_image_turbo.json` / `z-image.json` | 文本 | 快速文生图 | `comfyui-z-image-turbo` |
| `t2i_z_image_base.json` | 文本 | 质量优先的 Z-Image 文生图 | `comfyui-z-image-base` |
| `crop_image.json` | 1 张图 | 生成前的裁切预处理 | `comfyui-crop-image` |

表中 `workflows/` 开头的两份是本仓库实际提供的共享 API 工作流；其余名称是此前环境调查中的候选方案，当前仓库尚未收录对应 JSON，不能直接按表调用。本机 `/object_info` 可找到这两份 Qwen 2.1 工作流的节点和模型，证明具备接入条件；真正出片仍要提交最小样片验证显存、采样时间和视觉质量。Sage Attention 和 Lightning LoRA 尚未在此工作流验证。

## 执行

先探测环境和工作流：

```text
python scripts/inspect_comfyui.py --url http://127.0.0.1:8188 \
  --workflow <workflow.json> --out-dir <project>/planning/comfyui
```

图片工作流使用：

```text
python scripts/run_comfyui_image_workflow.py \
  --workflow workflows/qwen_image_2_1_edit_keyframe_api.json \
  --input <first-frame.png> \
  --prompt "<image prompt>" \
  --out-dir <project>/assets/generated-images --dry-run
```

确认请求中的 `LoadImage.image`、mask、正向提示词和输出前缀正确后，去掉 `--dry-run` 提交。执行器会复制输入图到 ComfyUI input，提交 `/prompt`，轮询 `/history/{prompt_id}`，回收 `SaveImage` 输出并写入结果报告。它不会自动导入 ChatCut。

## 记录

图片镜头的 `production` 至少记录：

```json
{
  "primary_tool": "comfyui-qwen21-edit",
  "fallback_tools": [],
  "asset_status": "to-generate",
  "runtime_decision": {
    "mode": "user-request",
    "user_request": "本次更改出图要求，改用本地 Qwen Image 2.1 编辑。",
    "reason": "用户已另行明确指定本次使用本地图片工具",
    "alternative_reason": "本地 Qwen Image 2.1 编辑工作流节点和模型均已通过环境探测",
    "evidence": ["planning/comfyui/environment-report.json"]
  },
  "image_generation": {
    "workflow": "workflows/qwen_image_2_1_edit_keyframe_api.json",
    "inputs": ["assets/a-scenes/S001-state-01.png"],
    "prompt": "保持人物身份和构图，只替换手中的道具。",
    "seed": 123456,
    "output": "assets/generated-images/S001-state-01-edited.png"
  }
}
```

输出通过尺寸、格式和视觉 QA 后，才把 `asset_status` 改为 `ready`，并记录 ChatCut asset ID。后续镜头遵循当前有效的出图授权；已经批准的本地资产不因工具恢复而自动重做，历史记录不改写。


## 动效设计图的额外规格

用于设计图参考动效时，GPT 直接请求 2048×1152；ComfyUI 路线先确认构图，再二采精修并检查真实尺寸与细节。二采不等同于普通重采样，当前两份 Qwen API 图尚未提供已验证的二采阶段。具体适用边界及视频分支见 [设计图参考动效](comfyui-video-production.md#设计图参考动效与同步音效)。

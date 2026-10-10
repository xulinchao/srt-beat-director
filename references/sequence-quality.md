# 连续镜头质量与制作前检查

用于新制视频，以及明确接入本门的续做任务。既有导演、DESIGN、逐镜动作和manual/continuous审核规则继续适用；本门把开源参考、整体PPT感、运动中布局和实际制作路由接成可核对的执行证据。字段以[契约 §11](contracts.md#11-连续镜头质量门)为准。

## 1. 先确定整片观看过程

在分镜计划的`sequence_direction`写清视觉主线、镜头承接、布局规则和动作语言。例如，观众从整件观察到关键部位，接着看该部位怎样参与操作，再比较用途改变后的实例。每个动作的收益应能落到已有`viewer_takeaway`与`motion_check.visible_result`；不为填写字段重复旁白。

相邻镜头可以更换照片、地区或表达方式，但要说明观众为什么在此时转看新对象。主体尺度、阅读方向、标签归属、出处与字幕区协调；统一不要求全片同一版式，也不禁止必要的静止阅读。

## 2. 自制动效先看真实来源

研究范围按**实际制作行为**判断，覆盖A/B、照片定位、证据提取、结构拆合、实例对照和场景中的精确图解。HyperFrames、Remotion、ChatCut Motion Graphics的非静止新制镜头，或`custom_motion=true`的其他镜头，必须有`production.motion_reference_review`。

原样使用已有视频、必要的单状态证据阅读、常规剪辑裁切不强制研究；照片被制作成新的定位/比较动画时不能仍以“有素材”免除检查。若实际改由程序化工具制作，先回写`primary_tool`，再复核依赖与参考。图解的完整模板/外部研究门仍按[broll-external-research.md](broll-external-research.md)执行，本门不降低其搜索和许可要求。

研究深度与改造风险对应：已有合格骨架的普通枚举或强调可复用适用记录，核对本次容量与节拍即可，不重启整轮外部研究。新的程序化关系或复杂遮挡仍实际审阅来源。两条创意路径不改变此实现检查；H3 场景按其身份、状态、运动与实际视频检查，混合镜头的程序化部分仍适用本门。

先观看实际动态演示，比较对象关系、核心动作、阶段、中文容量和改造范围，再决定唯一来源或自建。参考数量不是通过依据，同类镜头可以引用同一份已验证记录，不要求每镜重复搜索。可以指向现有`broll-research`记录；新门要求其中候选预览有真实文件与SHA-256，原生复用有许可证依据和可读取的具体实现文件。旧记录不自动补哈希或改成已经看过。

许可证未确认时仅研究动作结构，不复制代码。自建记录实际查看候选的拒绝原因及吸收的运动原则；不能因目录为空、题材不同或偏好某框架直接自建。预览和源码不存在时保留缺口，继续允许的无依赖工作，不把候选名单当作研究完成。

## 3. 用相邻镜头验证，再扩大制作

按文案选取包含相邻镜头的代表样片，覆盖实际主要表达方式、关键衔接、高信息密度和高风险动作。沿用项目样片区间；不为凑时长增加内容。整片只有一镜时检查该镜完整过程，短片可用全片样片。先按既有门制作必要资产、建立ChatCut样片时间线并导出，再检查：

本片有知识解释 B-roll 时，复核既定样片是否覆盖其主要难点，例如材料指认、结构拆合、同维度比较或密集文字。A-roll 的人物与画风通过不能替代这些验证；缺少的表达用受影响镜头的局部短片补查，并记录到已有动态预览/审阅证据，不移动既定样片区间、不新增用户审批点。用真实图片、实际中文与原旁白检查，避免只在开场或占位素材上验证风格后批量生产。B-roll 的解释判断按 [知识关系怎样变成观看过程](broll-expression-selection.md#知识关系怎样变成观看过程)，文字与载体按单片 DESIGN 核对。

- 正常速度带原旁白连看：信息是否推进、动作是否有解释收益、阅读与停点是否够用；不能靠逐句暂停才读得清。
- 每个运动镜头的开始、**运动中间态**、落定状态：主体与解释文字有没有争位置，标签是否跟随正确对象，关键部位和字幕区是否完整。接触、嵌合或交叉另补相应高风险帧。
- 每个相邻镜头接缝或混合中间态：主体尺度与阅读顺序是否突跳，有无双重文字、残影、空白或重复来源叠压。声明 `transition.visual_cut` 时按实际切点取样，在原接缝 notes 中记录先看后听/延后保持是否帮助理解、是否保留前镜阅读和后镜信息触发；不能仅凭偏移字段判断节奏通过。
- 整体PPT感：连续换图、逐条出字是否承担了本应由过程或关系变化完成的解释。照片推拉可以帮助原处定位，必要列表可以成立；不能仅因元素在动就通过。

出现遮挡、信息缺失、无解释收益的主要运动或明显散装感，记录具体镜头/时间/原因，先返工受影响设计。没有正常速度连看记录、缺运动中间态或PPT感审阅为fail/pending时，不扩大批量制作。通过后复用有效来源和布局规则；新表达或高风险动作仍补局部验证。

返工先区分知识表达、信息密度、素材支持、动作执行与视觉系统的问题，再修改对应真源。若观众看不出比较维度或结构关系，先改观看过程；若关系已清楚但文字争位置，再调整文字归属与载体。新增卡片、描边、推镜或音效不能代替前者。全局文字或载体替换前，先用干净底面、复杂全图与高信息量等本片实际适用场景验证，复用未受影响资产，不把局部尝试直接铺到整片。

## 4. 候选与正式流程的边界

全时长“预览”“候选”仍遵循已选主工程与同一质量检查，不是绕过ChatCut的例外。用户明确要求完整候选时，可在完成内部样片检查后制作候选，不伪造用户批准；正式扩大生产继续遵循既有manual/continuous审批。普通内部自检记录为`agent-self-check`，不写入approvals；continuous来源只在已有用户连续授权下使用。

逐镜渲染由计划工具完成；ChatCut路径将独立镜头素材、原旁白、字幕和声音放入实际时间线，由ChatCut导出样片及整片。每镜映射真实item/asset，不能把已经合成好的整片导入后用同一个item充作所有镜头。记录实际工具与计划不同、实际主工程不同或源工程缺失时，先回写路由、说明影响并复核；不能以检查通过掩盖实现差异。

## 5. 阶段命令与能力边界

生产前入口见 [execution-routing.md](execution-routing.md)：`check_workflow.py` 在 `expand`/`candidate` 中调用同一 expand 检查，在交付中复用 delivery 检查。以下专项命令保留用于阶段证据核对与定位失败，无变化时不重复运行。

```text
python scripts/validate_sequence_quality.py --project-dir <project> --stage planning --out <project>/planning/sequence-plan-validation.json
python scripts/validate_sequence_quality.py --project-dir <project> --stage prepared --out <project>/planning/motion-reference-validation.json
python scripts/validate_sequence_quality.py --project-dir <project> --stage sample --out <project>/planning/sequence-sample-validation.json
python scripts/validate_sequence_quality.py --project-dir <project> --stage expand --out <project>/planning/sequence-expansion-validation.json
python scripts/validate_sequence_quality.py --project-dir <project> --stage delivery --out <project>/reports/sequence-delivery-validation.json
```

planning并入计划校验；prepared并入提示词prepared/produced校验；批准样片时由状态校验复查sample，扩大前显式运行expand；交付review和final都检查delivery。检查只读证据、不生成媒体、不写批准。自动检查能拦住缺证据、过期哈希、路由不一致和明确未通过项，不能证明代理真的观看、动作因果成立或视觉美感合格。实际观看意见要包含具体观察，不能只有布尔值、工具日志或“无报错”。

新初始化任务自动声明`sequence_review_policy=sequence-quality-v1`；旧任务仅兼容提示。接入旧任务须先补真实检查，不重写历史审批、提示词哈希或旧执行记录。

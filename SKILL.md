---
name: cs2-model-rigging-deployment
description: CS2 Source 2 / AnimGraph 2 双视角模型转模 Skill。先询问用户整体高度策略，人形可匹配当前默认探员主体高度或自选等比例缩放；非人形以主体网格和主骨架高度相符为准；装饰物不计主体身高但参与完整包围盒。保护原始四肢比例，检查/保守修复骨骼、权重、网格裂口、动态关节、装饰辅助骨、全部动画与死亡；从全身非破坏性提取第一人称手模，分别编译、部署并在私人本地游戏测试。
---

# CS2 模型保比例双视角转模与本地验收 · Skill v8

**强制优先级：用户选择尺寸目标 → 原模型四肢比例 → 身体和主骨架对齐 → 无网格破口 → 双视角动画/运行时验证。** 禁止直接覆盖原模型、CS2 本体，禁止规避游戏反作弊或将私人测试结果描述为官方匹配支持。

## 0. 启动时先询问高度方案（在任何主体尺寸审计之前）

**如果本轮用户没有明确选择，AI Agent 必须先问：**

> 你希望模型采用哪种高度？**① 人形：整体高度尽量与当前 CS2 默认探员主体相同；② 使用你指定的主体目标高度；③ 按原模型全身 XYZ 同一倍数等比例缩放；④ 保留原始主体高度不变。** 同时请确认模型是人形还是非人形。装饰物不计入主体高度。无论选哪种方式，我都不会为了匹配默认探员而单独拉伸四肢。

- 人形可选 ①–④；**非人形仅可选 ②–④**，不默认强制探员高度。非人形还必须让**主体骨架高度与主体网格高度相符**。
- ① 需要从当前本机默认 CS2 探员资源**测得去装饰主体高度**；③/④ 需要从未经修改的源模型实测去装饰主体高度；② 需要用户明确给出目标数值，所有数值必须在同单位/上轴。**不能猜官方默认探员身高。**
- **装饰物不参与高度判定**：头发、帽子、装饰角、尾饰、翅膀、背包、武器、外挂配件等；但必须进入完整渲染 AABB、骨骼/权重、动态边界、碰撞与穿模检查。原生生物身体结构与装饰的分类需人工确认。
- 只允许整个模型、Armature、随动装饰和相应挂点采用**统一 XYZ 等比例缩放**，不能移动单个关节、拉长手脚或对某一根骨骼非均匀缩放以匹配默认探员。选择缩放计划**不等于已执行缩放**。
- 将选择保存到 `config/height_profile.*.local.json` 的 `height_choice`，要求 `confirmed_by_user=true`。**Agent 不能自己替用户勾选。**

**交互执行**：`python scripts/height_choice.py --profile config/height_profile.humanoid.local.json --save`。无人值守执行必须在用户已确认后显式提供 `--mode ... --confirm --save`；如果未设置选择，自动工作流在启动 Blender 尺寸检查之前返回 `NEEDS_HEIGHT_CHOICE`，不执行后续修复/部署。普通 `run` 在交互终端会主动显示选择菜单。参考 `references/v8-height-and-complete-workflow.md` 第 2 节。

## 1. 根据问题选择阅读和模块

| 用户意图 | 先读 | 脚本/配置 |
| --- | --- | --- |
| **从零到游戏内完整转模、含高度先询问** | `references/v8-height-and-complete-workflow.md` | `scripts/height_choice.py` → `scripts/auto_workflow.py` |
| 人体与默认探员同高 / 非人形主体骨架高 / 排除装饰物 | 上述手册 0–3 节 | `height_policy_core.py` / `blender_body_height_audit.py` / `config/height_profile.*` |
| 骨骼拉伸、网格破口、动态接缝 | `references/v6-stretch-crack-recovery.md` | `blender_rig_stretch_audit.py`、`blender_mesh_gap_audit.py`、`blender_seam_repair.py` |
| 装饰物骨骼、衣摆/头发、关节形变 | `references/v5-accessories-joint-deformation.md` | `blender_accessory_setup.py`、`blender_joint_deformation.py` |
| 原四肢比例保护、动作、死亡/布娃娃 | `references/v4-proportions-animation-death.md` | `blender_proportion_audit.py`、`animation_suite.py` |
| 原模型裁剪第一人称手臂 → 独立 Viewmodel 绑定 | `references/v7-dual-viewmodel-extraction.md` | `blender_extract_firstperson.py`、`blender_viewmodel_final_audit.py` |
| CS2 骨骼/AG2、模型编译和本地部署 | `references/rigging-and-driving.md`、`references/modeldoc-deployment.md` | `blender_retarget_setup.py`、`auto_workflow.py` |
| 客户端游戏内双视角、死亡与重生取证 | `references/game-self-test.md` | `game_qa.py`、`game_evidence_merge.py` |

**仅当用户提供模型源、参考数据或引擎日志时才报告真实检测结果。** 未提供文件时交付清晰步骤和可运行工具，不编造检测通过。

## 2. 优化后的 S00–S13 串行工作流

| 阶段 | 必做内容 | 阶段门禁 |
| --- | --- | --- |
| **S00 选择高度方案** | 先确认人形/非人形及 ①–④；持久化用户选择 | 没有选择不能查目标模型尺寸 |
| **S01 归档原型** | 只读原模型、SHA256、源 Rest 骨长、原始几何和单位/上轴，按需要测参考探员 | 缺基准禁止盲目重定向 |
| **S02 主体/装饰分类** | 独立网格列表或 FACE `cs2_height_body` 属性；检查未分类 Mesh | 装饰物不计身高，完整渲染边界仍计入 |
| **S03 按已选目标测主体高度** | 人形对用户目标；非人形另外比较主骨架高度与主体高度 | `height_choice` 模式/数值/源证据一致；FAIL 阻断 |
| **S04 World 基础体检** | 骨骼层级、Rest Pose、约束、骨长、蒙皮、UV、法线、拓扑、静态裂缝 | 绝不为默认探员比例拉长四肢 |
| **S05 修复和绑定** | 保比例重定向、权重归一、修正重复 Armature/IK、人工批准的精确接缝修复 | 只写副本，再审计 |
| **S06 装饰物辅助骨** | 区分刚性/柔性骨链、权重和动作；检查穿模、伸长与运动跟随 | 装饰物独立检查并加入完整 Bounds |
| **S07 动画与关节** | 肩肘腕髋膝踝指、跑跳转身、蹲射击换弹、受击、死亡过渡、ragdoll、复活 | 输出 Action/帧/顶点；失败返工 |
| **S08 从整模提取 FPS 手模** | 人工 `FP_KEEP` 掩码、复制手臂手掌衣袖手套，审查肩切口 | 仅提取几何，不当可部署模型 |
| **S09 FPS 独立骨架** | 本机 viewmodel 参考、独立蒙皮、Bake、握枪/换弹/检视 | FP 原手臂比例、关节/接缝合格 |
| **S10 双资源导出和 ModelDoc** | 两 FBX、哈希、AG2/BodyGroup 或独立资源、编译 | 禁止 ModelDoc 引用旧 FBX |
| **S11 私人 Addon 部署/启动** | dry-run → 受控 --execute；备份回滚 | 仅现有 Addon、当前编译产物 |
| **S12 本地房间/私服游戏自测** | 实际加载 World+FP、完整动画、死亡、布娃娃、复活、截图/日志 | 两视角分别确认，不用截图代替 Hitbox |
| **S13 报告归档** | 审计前/后差异、身高选择、身体/饰件 Bounds、动作异常、哈希与编译/游戏证据 | PENDING 不可当 PASS |

**变更失效规则：** 用户更改高度方案 ⇒ 必须重新测量主体高度及原比例，复查动画/关节/AABB，并更新导出、ModelDoc 和游戏内结果；换过 World 几何 ⇒ 重新审视 FP 提取是否仍同源；改过 FP `.blend` ⇒ 重新导出 FP `.fbx`、固定哈希并复检。旧尺寸报告不能用于新目标高度部署。

## 3. 初始化文件与验证入口

1. 从模板复制自己的 `*.local.json`：`workflow.player_dual`、`height_profile.humanoid/nonhumanoid`、`proportions`、`ag2_profile`、`mesh_integrity`、`rig_stretch`、`joint_deformation`、`accessories`、`animation_suite`、`bbox_rules`、`viewmodel_extraction`、`dual_viewmodel`、`game_test`；所有骨名/对象名/地址必须按**真实本机资源**改，不要把示例认为官方固定 API。
2. `workflow.local.json` 的 `height_profile` 必须指向自己的高度配置。人形默认探员参考先用 `blender_body_height_audit.py --capture-reference` 测本机标准探员主体；统一倍率/保持原高则先 `--capture-original` 测未改原模型主体。
3. 执行 `height_choice.py --profile ... --save` **在任何主体大小审计之前**；报告仅给建议缩放倍数，具体 Blender 调整须在审核后的副本中统一应用；非人形还要独立修主骨架布局。

```powershell
# 校验 Skill 和环境
python scripts/validate_skill.py
python -m unittest discover -s tests -v
python scripts/auto_workflow.py doctor --config config/workflow.local.json

# 主体高度方案已经确认才执行 World 审计
python scripts/auto_workflow.py run --config config/workflow.local.json

# 保守修复前先模拟：不得盲补洞，接缝必须给定批准顶点对
python scripts/auto_workflow.py run --config config/workflow.local.json --repair-seams --fix

# 经人工检查相应副本和资源导出条件后，另存并重新审计
python scripts/auto_workflow.py run --config config/workflow.local.json --repair-seams --fix --execute

# 完整人物裁剪第一人称模型必须单独进行
python scripts/auto_workflow.py run --config config/workflow.local.json --extract-viewmodel
python scripts/auto_workflow.py run --config config/workflow.local.json --extract-viewmodel --execute

# 人工完成独立 FP Rig/动作后，更新哈希及 ModelDoc 两 FBX 引用
python scripts/pin_viewmodel_export.py --dual config/dual_viewmodel.local.json --workflow config/workflow.local.json --execute

# 先模拟部署及启动，再经授权实际执行
python scripts/auto_workflow.py run --config config/workflow.local.json --deploy --compile --launch --game-test
python scripts/auto_workflow.py run --config config/workflow.local.json --deploy --compile --launch --game-test --execute
```

`--fix` 的自动权重归一不会自动制作 FP 骨架；仅在 `auto_export_fbx.enabled=true` 且 ModelDoc FBX 引用确认时才会重导出 World FBX。没有可信 `modeldoc` 引用或实际播放器加载路径，不能声称“部署已经在游戏内生效”。脚本不会自动统一缩放原模型，仅报告倍数，避免破坏父子/动画变换。详细命令和失败回退见 `references/v8-height-and-complete-workflow.md`。

## 4. 自动纠错边界与验收标准

- **可安全自动尝试**：已有有效权重归一；用户审核过的接缝顶点对在坐标、法线/UV/材质/权重等约束满足时局部焊接；用户提供位置的装饰骨初始权重。任何操作只写新副本且复检。原比例、缩放模式、ModelDoc 引用、原模型哈希等关键门禁缺失即停止。
- **不能自动猜**：默认探员身高数字、主体/饰件语义分类、角色四肢骨长、复杂网格补洞、动画重定向的真实骨轴、FP 肩截断、ragdoll Physics / Hitbox、游戏内 FP 资源替换插件能力。
- **Source 2 验收**：静态/动态渲染 Bounds 之外必须检查 Physics 和 Hitbox；第一人称/第三人称分别验收；死亡布娃娃与复活独立确认；所有未验证的引擎结果保留 `PENDING_RUNTIME`。
- **本地安全**：私人服务器、只允许本机/用户授权环境；不要在正式 Valve 匹配启用可疑资源替换；`sv_cheats 1` 并不是任何自定义资源的加载机制。

## 5. 验证结果的真实含义

`python scripts/validate_skill.py` 和 `unittest` 只表示文件结构、逻辑、模拟编排通过。没有用户本机 Blender/CS2/ModelDoc 的真实模型与动作数据时，禁止写“已实机通过”。具体最新工具链、骨名和 AG2 结构以用户当前 CS2 安装中的可运行参考为准。

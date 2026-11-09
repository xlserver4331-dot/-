---
name: cs2-model-rigging-deployment
description: 面向 CS2 Source 2 AG2 自定义人物模型，保留原始身体四肢比例，自动检查/保守修复骨骼蒙皮、关节拉伸和网格裂口、装饰物辅助骨及全动作；从完整人物非破坏性裁剪第一人称手臂与衣袖，分别绑定 World/Viewmodel 骨架并验证 ModelDoc、私人服务器部署及游戏内动作。
---

# CS2 模型双视角转模、纠错与部署 Skill · v7

**最高优先级：原始人物比例 > CS2 探员默认长度。全身转模和第一人称手模均禁止拉伸四肢。所有写操作仅限用户明确许可的副本及私人 Addon，严禁直接覆盖 CS2 本体、规避反作弊或在官方匹配中部署替换模型。**

## 0 · 任务路由（只读相应章节，不要一次性盲跑）

| 用户问题 | 首先阅读 | 执行入口 |
| --- | --- | --- |
| **从整个人物模型制作独立第一人称手模** | `references/v7-dual-viewmodel-extraction.md` | `blender_extract_firstperson.py` / `auto_workflow.py --extract-viewmodel` |
| **第一人称手变形、丢失、还是默认手套** | `references/v7-dual-viewmodel-extraction.md` D–H | `blender_viewmodel_final_audit.py`、`dual_viewmodel_gate.py` |
| 骨骼被拉长/网格破口/动态接缝 | `references/v6-stretch-crack-recovery.md` | `blender_rig_stretch_audit.py`、`blender_mesh_gap_audit.py`、`blender_seam_repair.py` |
| 装饰物骨骼/自然摆动/肘膝塌陷 | `references/v5-accessories-joint-deformation.md` | `blender_accessory_audit.py`、`blender_joint_deformation.py` |
| 原始四肢比例、完整动画、死亡和布娃娃 | `references/v4-proportions-animation-death.md` | `blender_proportion_audit.py`、`animation_suite.py` |
| CS2 AG2 绑定、动画驱动、武器挂点 | `references/rigging-and-driving.md` | `blender_retarget_setup.py`、`blender_audit.py` |
| 包围盒/ModelDoc/部署/启动 | `references/bounding-boxes.md`、`references/modeldoc-deployment.md`、`references/automation-and-launch.md` | `auto_workflow.py` |
| 本地游戏内真实角色验收 | `references/game-self-test.md` | `game_qa.py`、`game_evidence_merge.py` |

**当用户提供 `.blend` / FBX / ModelDoc / 运行日志时，先检查模型真实文件并报告错误对象与动作帧；没有提供真实模型时只交付工具和流程，明确 Blender/CS2 实机结果尚未验证。**

## 1 · 依赖和可靠性原则

- Python 3.10+；Blender 需支持 Python / bmesh / FBX Export；CS2 Workshop Tools + 当前本机游戏参考模型；私人服务器和必要的允许的模型加载插件仅在游戏自检阶段需要。
- 默认只读 / dry-run；**只有 `--execute` 才可以输出新 `.blend`、实际部署、编译或启动**。提取不自动改骨骼/权重、不会自动裁切未经手工标记的身体。
- **游戏视角分离**：世界模型是完整人物；第一人称由同一原人物中裁剪出可见手臂/手掌/衣袖/手套几何，然后**换绑独立 viewmodel skeleton 并使用自身动作**。不要复用世界模型 Armature 来冒充视角切换。
- 角色比例以原始文件的 Rest 骨长为基准；只允许人工确认的**统一整体缩放**；任何 Rest/动画四肢拉伸、IK Stretch、重复 Armature、裂口都应阻断。
- BodyGroup、viewmodel skeleton、AG2 图和资源引用必须以**当前本机可运行 CS2 探员**为基准；旧教程示例不代表每次更新都兼容。**同一个 ModelDoc 中两套网格不保证游戏自动显示自定义第一人称。**
- 只有真实引擎和观察者证据才能判定游戏内 `PASS`。截图像素差异只能作为线索。死亡/布娃娃在 World 侧；FPS 侧检查死亡隐藏与复活手模恢复。

## 2 · v7 优化执行顺序（按依赖关系，不得跳级）

| 阶段 | 内容 | 后置门禁 |
| --- | --- | --- |
| **P0 原始归档** | 不可变全身源模型、SHA256、原始骨长与法线/UV/材质快照，标记真实错误帧 | 无原始基准禁止绑定 |
| **P1 世界模型修复** | v6 拉伸/破口诊断 → v5 权重/装饰骨/关节动态 → v4 包围盒、动作、死亡、布娃娃 | World 关键项目均通过 |
| **P2 FP 手臂提取** | 在原全身模型中为左右手臂、手指、衣袖画 `FP_KEEP` 掩码 → 自动复制与裁剪到**新副本** | `EXTRACTED_REQUIRES_RIGGING`，不允许部署 |
| **P3 FP 独立骨架** | 导入/参考 `viewmodel.vnmskel` → 骨名/Rest 校准 → 不拉伸重定向 → Bake → 重新蒙皮 | 目标 Armature 与世界骨架分开 |
| **P4 FP 专项动态 QA** | 肘/腕/手指、袖口、手套、握枪、瞄准、换弹、检视、枪械种类、动画伸长和 AABB | 无裂口/拉伸、原手臂比例正确 |
| **P5 双资源导出** | `world_final.fbx` 与 `firstperson_final.fbx` 独立导出，核对源模型哈希；更新相应 ModelDoc Mesh/BodyGroup | 不允许发布旧 FBX |
| **P6 双视角 ModelDoc 编译** | 共享 `.vmdl` 的 `first_or_third_person` BodyGroup，或独立 `.vmdl`；AG2 World/Viewmodel 参考、材质与资源编译 | 确认两套资源被引用，编译产物存在 |
| **P7 私人服务器部署/启动** | 只向已创建的 `csgo_addons/<addon>` 按清单部署、备份与回滚；本地专用服启动 | 禁止修改本体；无客户端挂载不能宣称成功 |
| **P8 游戏内双视角验收** | 第一/第三人称显示、idle/run/jump/crouch/turn、开火换弹/检视/刀具、受击/死亡 ragdoll/复活 | 分别记录 World PASS / Viewmodel PASS / Pending |
| **P9 报告归档** | 审计前后 JSON、裂缝帧和顶点、各关节、两 FBX 哈希、编译日志、游戏截图、失败阻断及修复建议 | 无证据不得标 PASS |

**阶段耦合规则：** 世界模型变更后必须重新提取/审视对应第一人称几何；第一人称 `.blend` 变更后重新导出 `.fbx` 并重填哈希。不能在一个命令里边盲裁切、边修骨架、边部署。`--extract-viewmodel` 强制独立成轮，防止未经重定向的手模被加载到游戏。

## 3 · 首次初始化（路径全部为用户自填样例）

复制模板：

- `config/workflow.player_dual.example.json` → `config/workflow.local.json`，指定真实路径、模型、检查配置及两套部署清单。必须把 `firstperson_source_blend_file` 设为从原始全身模型另存、含 `FP_KEEP` 掩码的工作副本；世界模型仍从 `blend_file` 单独读取。
- `config/viewmodel_extraction.example.json` → `config/viewmodel_extraction.local.json`，填写原全身 Mesh、Mask 与审核后的肩部裁断位置。
- `config/dual_viewmodel.example.json` → `config/dual_viewmodel.local.json`，填写独立 FP 网格、骨架对象、提取报告、ModelDoc 和部署条件。
- `config/firstperson_bone_map.example.json` → `config/firstperson_bone_map.local.json`，用**当前本机参考**替换示例骨名，并将映射标记人工审核。
- 复制其余 `ag2_profile/proportions/mesh_integrity/rig_stretch/joint_deformation/accessories/bbox_rules/animation_suite/game_test` 模板供 World 与 FP **分别使用**。提供真正的原模型比例基准，不要直接沿用示例阈值判 PASS。

参考 `references/v7-dual-viewmodel-extraction.md` C 节用 Blender 的 Edit Mode / Vertex Groups 人工标定手臂区域；如果模型只有 `Body` 一个 Mesh，删除提取配置中不存在的 `Sleeves` 模板条目。

## 4 · 命令和检查入口

```powershell
# 0. 环境预检（不修改原模型）
python scripts/auto_workflow.py doctor --config config/workflow.local.json

# 1. 完整模型先修 P1；必要时单独运行 v6 裂口/拉伸修复
python scripts/auto_workflow.py run --config config/workflow.local.json

# 2. 从完整人物做第一人称手臂裁剪，先只读预演
python scripts/auto_workflow.py run --config config/workflow.local.json --extract-viewmodel
python scripts/auto_workflow.py run --config config/workflow.local.json --extract-viewmodel --execute

# 3. 人工在生成的 firstperson_cut_preview.blend 中重绑到独立 Viewmodel rig，修完并另存新 .blend；导出单独 FP FBX
# 4. 锁定新 .blend 和 FP FBX 的实际 SHA256（有备份）
python scripts/pin_viewmodel_export.py --dual config/dual_viewmodel.local.json --workflow config/workflow.local.json
python scripts/pin_viewmodel_export.py --dual config/dual_viewmodel.local.json --workflow config/workflow.local.json --execute

# 5. 双视角 Blender 审计、AG2/网格/比例/关节检查
python scripts/auto_workflow.py run --config config/workflow.local.json

# 6. 本地部署、编译、启动与游戏测试，先 dry-run
python scripts/auto_workflow.py run --config config/workflow.local.json --deploy --compile --launch --game-test

# 7. 只在已配置真实私人环境、备份与操作授权后执行
python scripts/auto_workflow.py run --config config/workflow.local.json --deploy --compile --launch --game-test --execute
```

**`--extract-viewmodel` 只负责从原始完整 Mesh 提取有蒙皮的几何副本**。它会保留 UV、材质与已有原骨架权重，但不创建已验证的 FPS Armature，也不生成 `viewmodel` 动画。此后必须手动完成骨骼重定向、权重/握枪动作修正与独立源资源导出。提交部署前双模型门禁会校验独立 FP 审计、SHA256、ModelDoc/BodyGroup、编译清单。

## 5 · 强制检查与安全纠错

1. **骨骼/权重**：原始骨长（含左右上下臂、大腿、小腿）、Rest/Pose 比例、骨骼父子关系、无效顶点组、未绑定点、权重归一、重复 Armature、IK Stretch、Copy Scale。
2. **网格破口/关节**：静态开放边、缺面、非流形、异常法线、动态 seam gap、肩肘腕髋膝踝手指边长/面积压缩、袖口/手套接缝；报告精确 `mesh + vertex + Action + frame`。
3. **装饰骨**：头发、衣摆、配饰按刚性或柔性链配置，检查权重、动作跟随和不拉长；不能未经验证就声明 Source 2 动态物理支持。
4. **动画**：World（跑跳、攀/蹲、换弹、射击、受击、死亡、布娃娃、复活）与 FP（握持、切枪、后坐力、开火、换弹、检视、手指、死亡手模隐藏/复活显示）**分开评分**。
5. **包围盒**：World/FP 静态 AABB、动作采样动态 AABB、渲染 Bounds、Hitbox、Physics/Collision 分别检查；真实 Hitbox 需引擎证据。
6. **仅允许自动修复**：有可靠有效权重的归一化；或经人工指定顶点对、哈希/UV/材质/权重全面校验的接缝焊接，且只写入**新副本**。不自动猜骨长、重绘整个蒙皮、全网格补洞或为匹配默认探员拉长四肢。

## 6 · 双视角发布门禁与故障路由

- 玩家模型一旦要求 `--deploy/--compile/--launch/--game-test`：必须提供 `dual_viewmodel`，并核对 `viewmodel_blend_file`、独立第一人称检查及两个 SHA256；ModelDoc 当前引用两套 FBX，部署清单中存在 FP FBX，编译清单核验目标 `.vmdl_c`。**缺任意一项阻止自动发布**。
- 当共享 `.vmdl`：`packaging_mode=shared_bodygroup`，必须审核 BodyGroup、`viewmodel.vnmskel` 和 AG2 映射；也支持 `packaging_mode=separate_vmdl`，需核对独立 `.vmdl_c`。这两个设置属于**工程方案**，必须以用户当前 CS2 资源实测，不是“自动在客户端生效”承诺。
- 当 FPS 手是默认的、T-pose、袖口分离或开枪时被拉长：阅读 `references/v7-dual-viewmodel-extraction.md` 的 H 节。禁止直接改世界模型手臂长度。
- 本地私服插件只支持 World 换模时，游戏自检必须报告 `PENDING_RUNTIME_VIEWMODEL`，不可宣称整个 Skill 已完成游戏内换手。
- 所有修复和部署记录 `reports/run_*/workflow_result.json`，独立 FPS 的 `firstperson_extraction.json` 和 `firstperson_final_audit.json`，编译日志与游戏内截图另存。任何真实游戏运行/服务器权限缺失都应解释清楚。

## 7 · 自检

```powershell
python scripts/validate_skill.py
python -m unittest discover -s tests -v
```

这些是**离线静态与模拟测试**，不证明真实 Blender/ModelDoc/CS2 已编译或正常切换视角。参照 `references/sources.md` 与 v7 参考链接确认游戏版本差异；不要直接复制旧教程的 AnimGraph 1 配置。

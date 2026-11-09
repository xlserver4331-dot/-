# CS2 v4：原始四肢比例锁定、第一人称手模与死亡/布娃娃完整动画验收

本文件为 `SKILL.md` 的**强制参考**。所有带有自动化字样的项目只在用户明确授权、已配置的本机私人测试环境执行。此文件是工作流设计及工具使用方法；它不会自动安装插件或证明游戏已实测通过。

## 1. 最重要的不可变规则

**目标是保留用户原始人物的肢体比例。CS2 官方探员四肢长度不是目标，也不是长度校准基准。**

- 可行：整个人物统一倍率，原始骨架长度按同一倍率复制到目标骨架；通过改骨骼**旋转、层级映射、IK 目标、动画时间、武器挂点及摄像机参数**适配。
- 禁止：单独拉长上臂/前臂/大腿/小腿、为了对齐 Valve 的标准探员而拉伸网格或骨骼；非均匀对象缩放；允许 `Stretch To` 或 IK Stretch 改变长度；对动作使用骨骼 Scale 来“凑”枪械位置。
- 特别提醒：正确的姿势不等于正确的长度。只检查“手是否握住枪”会遗漏整个前臂已被拉长的问题。
- **首选方案**：使用原始人物的人体关节位置/长度构建与目标 CS2 AG2 命名与拓扑兼容的绑定骨架；将原有动画变为目标姿势/Rotations；必要时调整目标/挂点，而不是把人体拉成标准探员。
- 若当前 AG2 动作无法容纳短手臂/异形人体，请标记 `PENDING/FAIL` 并提供针对该模型的 IK、武器/动画适配方案；**绝不允许自动修改四肢长度来消除报警**。

## 2. 原始模型长度基准：真实操作

先把 `config/proportions.example.json` 复制为 `config/proportions.local.json`，并认真修改其中的 `source_armature`、`target_armature` 及每个 `source`/`target` 关节点名称。默认 Mixamo/AG2 名称只是例子，不能直接当作真实角色骨架。

长度是 **rest/bind pose 下两个关节（骨头 HEAD）之间的空间距离**。评估用源模型躯干锚点求整体等比例倍率，再比较 8 段原始四肢。这样同时拉长全部四肢也不会因为用了肢体长度的中位数估算尺度而漏检。

```powershell
# 1. 对未经修改的原始角色截取不可变源基准（不要从已拉伸/已纠错的结果提取）
blender -b "D:\models\original.blend" --python scripts/blender_proportion_audit.py -- --mode capture --config config/proportions.local.json --out config/original_proportions.local.json

# 2. 对重定向后的世界模型做比例检查（如果有 Action，会采样姿态伸缩）
blender -b "D:\models\cs2_world.blend" --python scripts/blender_proportion_audit.py -- --mode audit --config config/proportions.local.json --baseline config/original_proportions.local.json --out reports/world_proportions.json
```

输出包括：`uniform_scale_from_torso`、逐段 `relative_deviation`、`object_scale_violations`、`pose_stretch.violations`。默认容差：Rest 比例 3%，对象非均匀 0.5%，动态伸缩 1.5%；这是**质量验收参数，非 Valve 官方阈值**。根据精确测量和模型规模可修改。没有原始模型/没有可信躯干锚点时为 `PENDING`；超限为 `FAIL`。无可用 Blender Action 时仅原始 Rest 比例可初判，AG2 动态拉伸必须进游戏复核。

本脚本是只读检测。`scripts/blender_auto_fix.py` **不得**修改骨长、人体网格尺度、骨骼 Rest 位姿或第一人称手臂形状。非直接父子的关节不可以用头到头长度不变推导姿态伸缩；需要调整测试骨骼对。

### 2.1 绑定方法：避免默认探员拉伸

1. 对源人物标定肩-肘-腕、髋-膝-踝与躯干基准；源文件备份并记录 hash。
2. 依据 `config/retarget_map.example.json` 建立名称映射，匹配目标 CS2 AG2 关节层级，而非复制默认骨骼的长度。
3. 以源关节坐标在目标骨架建立/校正骨头 HEAD；保留 AG2 对根、手部、武器骨骼及辅助骨骼的约束，任何添加/移动都应基于目标资源验证是否可行。
4. 优先用 Copy Rotation、姿态校正矩阵、手部 IK 的位置目标和适当武器 attachment 解决握枪问题。禁用 Stretch To、Copy Scale 造成的非均匀形变，所有临时约束烘焙成有效动作后再删除。
5. 测量原始 vs 绑定后的长度，Blender 中抽样所有关键 Action，确认无肢体长度突变；一旦 FAIL 停止导出。
6. 各动作检查手臂/腿部比例是否不变；若角色比例极端导致官方动画不可复用，承认该模型需要自定义动画/驱动，而非私自改成标准探员身材。

## 3. 第一人称手模是独立资源链路

CS2 世界模型（third-person）通过不等同于第一人称 viewmodel（arms + gloves + weapon）通过。第一人称通常有另一套模型、相机和动画资源，实际替换是否生效取决于客户端资源及服务器插件，不可推断。

**源模型**：如项目提供手部/手臂 `.blend`，在 `workflow.local.json` 填写以下字段：

- `viewmodel_blend_file`
- `viewmodel_ag2_profile`：针对手模骨架重新校准；**不要复用世界模型的父级表**。
- `viewmodel_bbox_rules`：独立的手部视野/局部边界基准；不是玩家世界碰撞盒。
- `viewmodel_proportion_profile`：独立的源手臂关节点映射。
- `viewmodel_original_proportions`：由原始手模捕获的基准 JSON。

`auto_workflow.py run` 发现 `viewmodel_blend_file` 时会执行独立 `blender_audit_viewmodel.json`；缺少任一关联路径会中止，而不是混用世界模型配置。没有提供第一人称源文件，报 `PENDING_NO_VIEWMODEL_SOURCE`，**不假装已检验手部源资产**。

**游戏内必检**：第一人称待机、装备/出枪、开火、换弹、检视、换武器、刀攻击；主要观察肘/腕/手指长度是否正常、手套是否穿模、枪把握持是否错位、换弹弹匣动作与两只手是否正确、镜头裁切/FOV 是否遮挡。可选补测手雷出/收与投掷；默认脚本不自动扔手雷以免误操作。

**故障处理**：优先调 viewmodel 摄像机、握枪姿势、动画重定向和武器挂点；**不能**单独拉长手臂以贴合第一人称武器位置。

## 4. 动画验收必须覆盖完整状态机（包括死亡）

`config/animation_suite.example.json` 描述世界模型、第一人称两条检测轨道。对于游戏通过 AG2/物理系统驱动、并没有独立 Blender Action 的状态，使用 `runtime_only`，不得凭空声明缺少一个命名为 `death` 的 Action 就是模型错误。若项目明确提供某段 Action，则写入 `source_action` 并按需要用 `action_required` 强制核验。

| 类别 | 检测状态 | 必须看什么 |
| --- | --- | --- |
| 基础移动 | idle、walk、run、turn | 肩髋旋转、脚部落地、转身根骨骼 |
| 蹲跳 | crouch、crouch_move、jump_start、airborne、land | 过渡、脚踝、膝盖、落地穿地 |
| 武器 | aim、fire、reload、weapon_switch、knife_attack、grenade_throw | 武器挂点、左右手、枪口与指尖 |
| 受击 | hit_react | 实际受击事件是否正确驱动，不用摄像机晃动代替第三人称证据 |
| **死亡** | **death_transition** | **活体状态到死亡状态转变，root_motion/姿态是否突变或 T-pose** |
| **布娃娃** | **ragdoll_fall、ragdoll_rest** | **物理倒地、身体触地、最终静止，不飞出、不陷地、不四肢拉长** |
| 复活 | respawn | 角色重生、骨架恢复、装备姿势与第一人称手臂正确重新加载 |
| 第一人称 | arms_idle、weapon_draw/fire/reload/inspect、knife、grenade、death_view_transition | 手指/手腕/手臂比例，视角切换和死亡时 Viewmodel 状态 |

**“死亡动画”和“布娃娃物理”不能互相替代**：项目可能采用一个死亡过渡序列后切入 ragdoll，也可能由游戏直接用物理驱动。必须在目标 CS2 版本真实验证。

## 5. 本机私人服务器中的死亡测试：分开取证

1. 在**用户自己控制的本地私人服**校准 `sv_cheats 1`。正确写法有一个空格。客户端连接专用服时是否能执行取决于服务端权限，故配置中的 `sv_cheats_confirmed` 必须由用户手工验证；工具不会尝试绕过权限/反作弊。
2. 先完成移动和第一人称所有测试；死亡动作设为**最后一步**，避免死亡之后误当作仍在场可操作。
3. 在 `config/game_test.local.json` 的 `death_test` 下显式设置三个布尔字段 `enabled=true`, `allow_self_kill=true`, `sv_cheats_confirmed=true`，追加最后一个 Step：

```json
{"id":"death","action":"death","view":"thirdperson","seconds":2.0}
```

4. 脚本在本地游戏控制台发送白名单命令 `kill`（只对**自己的测试角色**），采集之后的**当前客户端画面**；`TRIGGER_SENT_PENDING_OBSERVER_EVIDENCE` 不表示第三人称布娃娃通过。
5. **必须另用第二本地客户端、观察者视角、演示录像，或兼容的服务端记录**观察角色死亡倒地。确保录像中同一模型、同一触发事件和同一地图/测试回合；按需要在 `observer_evidence_path` 记录录像路径。
6. 验证：死亡前站姿 → 受击（另测）→ 死亡过渡 → ragdoll 起始 → 落地接触 → 稳定静止；检查四肢长度、关节崩溃、布娃娃碰撞体、装备残留、尸体物理、地面穿透。若启用自动复活，**在新的独立回合**测试复活与第一人称重新初始化；当前脚本不会自动验证复活。
7. 报告中的 `death_transition_live`、`ragdoll_physics_live` 和 `respawn_live` 一律 `PENDING`，直至补充可信观察者/引擎证据。仅自身死亡画面或已发送 `kill` 不能证明这些项 PASS。

### 5.1 游戏内第一人称/死亡证据不会自动通过

- v4 桌面输入可截取某一时间点画面并做低细节、同视角像素回归，**并不包括图像语义检测算法**，无法准确独立判定 T-pose、穿模、骨骼、Hitbox、布娃娃质量。
- 多视角、完整动画/死亡过渡最可靠的是高帧率录像、观察者视角及 ModelDoc/引擎工具交叉确认。
- 与 Valve 官方匹配无关。不改变反作弊设置、不更改游戏本体文件、不进行任意服务器指令注入。

## 6. 验收门禁与报告解释

`blender_audit.json` 增加 `checks.source_proportions` 和 `checks.animation_suite`。玩家模型进入资源部署前：原始比例必须 `PASS`；Action 清单不能 `FAIL` 或未配置。无 Blender Action 但拥有经捕获的源 Rest 比例时，可先部署以进行必要的 AG2 运行时验收；动态拉伸在游戏中仍属于待证项。

`engine_validation.pending.json` 增加 `viewmodel_arms_live`、`viewmodel_animation_live`、`original_limb_proportions_live`、`hit_reaction_live`、`death_transition_live`、`ragdoll_physics_live`、`respawn_live`、`animation_suite_live`。完成最后阶段前，它们**全部不能自动 PASS**。

如果发现局部拉伸、第一人称手模异常或死亡物理错误，禁止“只为了通过而拉长骨骼”；记录 `FAIL`，从 IK、动画逻辑、重定向、碰撞/布娃娃关节与物理约束着手排查后重新部署测试。

# CS2 v8 全流程手册：先询问高度策略，再保比例转模、双视角导出和游戏内验收

> 适用 Blender + Counter-Strike 2 Workshop Tools/ModelDoc + 允许加载自定义角色资源的本地私人测试环境。**本手册不是“官方匹配可替换模型”的承诺**。所有自动纠错和部署必须在用户确认的副本/Addon 内执行。第一人称游戏运行时的替换是否可用，取决于当前游戏资源加载路径与私人测试插件。

## 0. 不可违反的原则（每次运行先读）

1. **先询问，再测主体高度。** 如果用户没有明确选择身高策略，Skill 必须提问，不允许自行按 CS2 默认探员尺寸处理。无交互批处理遇到缺少选择必须拒绝运行（`NEEDS_HEIGHT_CHOICE`）。
2. **只允许统一等比例缩放**：X、Y、Z 同倍率；网格、主体骨架、装饰物、挂点、可关联的物理形体需要在同一世界变换下协调。禁止分别拉伸手、腿、躯干，禁止用 IK Stretch、Stretch To、Copy Scale 或骨骼局部非均匀缩放“凑”默认探员。
3. **人体模型**可以选择和当前本机默认探员的主体高度尽可能一致，也可以明确选择目标高度、整体比例系数或原始高度。默认探员只是**整体高度参考**，不是四肢骨长或体型比例模板。
4. **非人形模型**不强迫匹配人类探员高度；无论最终选什么整体大小，都必须检查“**主骨架垂直跨度 ≈ 主体网格垂直跨度**”。骨架和网格已经错位时，整体缩放两者不能消除相对偏差，必须校准 Rig Rest/关节布置或制作专用动作，不得拉伸几何。
5. **装饰物不计入主体高度**。头发尖、帽子、纯装饰角、尾饰、翅膀、披风、背包、武器、外置护具等不参与高度目标。但装饰物仍属于完整渲染 AABB、动画边界、权重、辅助骨、碰撞安全和穿模检查；如果“角/尾/耳”是角色原始不可分割的身体结构，须由作者先明确将它归为主体还是装饰。
6. **原始模型不可变**：保存源 `.blend/.fbx` 和哈希；World 和 Firstperson 都从原始几何或已审定的修复副本分支。修复结果保存新副本，再复检，再重新导出；不能拿旧 FBX 部署。
7. **不能从离线测试推出引擎成功**。ModelDoc 编译、资源加载、动画、死亡布娃娃、第一人称手模显示、实际 Hitbox 需要各自证据。

## 1. 流程总图与强制顺序

| 阶段 | 执行工作 | 通过门禁/失败退回 |
| --- | --- | --- |
| **S00 类型与高度选择（最先）** | 先问是否人形；选默认探员同高、自定义主体高、整体缩放倍数或保持原高 | `height_choice.confirmed_by_user=true`；缺失直接停止，**不启动模型尺寸审计** |
| **S01 原档与参考冻结** | 复制未改动原档；记录 SHA256；记录原始 Rest 四肢骨长/上轴/单位；测原始主体高；需匹配探员时测当前默认探员**去装饰**主体高 | 原比例/源文件可追溯；参考值与模型使用同坐标单位 |
| **S02 主体/装饰分类** | 将 Mesh 分成 `body_mesh_objects` / `accessory_mesh_objects` / 带 FACE 属性的 `mixed_meshes`，处理未分类绑骨网格 | 无未分类几何；装饰物不会被算进身高；完整 Bounds 仍有装饰物 |
| **S03 身高与骨架布局审计** | 使用已选目标测主体静态高度；人形对比用户指定目标；非人形还检查主骨架上/下端与网格 | 目标高度满足配置容差；非人形骨架与主体高一致；只输出等比例缩放**建议**，不擅自修改 |
| **S04 World 源骨架/网格定位** | 检查 Rest Pose、骨长、父子关系、朝向、重复 Armature、权重、UV、法线、非流形/破口 | 不允许四肢被拉伸、原始比例失真、未经批准接缝焊接 |
| **S05 保比例绑定/修复** | 将目标 CS2 World/AG2 骨骼定位到原模型关节；调整动画约束/IK 目标和武器偏移；归一权重；修复经人工确认的裂缝 | 骨长相对比例不变；关节和接缝复检通过 |
| **S06 装饰物骨骼** | 刚性挂件单骨跟随；柔性头发、裙摆、披风等制作辅助骨链及权重；烘焙必要的次级动作 | 辅助骨层级与权重正确、运动时无拉长/穿模；不误计高度 |
| **S07 动画与关节极限测试** | idle、走跑、左右转身、蹲、跳、落地、持枪、开火、换弹、切枪、受击、死亡过渡、ragdoll、复活 | 每关节采样 Action/帧号；检查挤压塌陷、拉伸、破口、AABB；物理待游戏内确认 |
| **S08 从整模提取第一人称手臂** | 在完整人物的手臂/手指/手套/袖子绘制 `FP_KEEP` 标记；**非破坏性**裁剪副本并审核肩部切口 | 未误裁胸腿，手指完整，截断边已审核；此时**还不是可部署手模** |
| **S09 FP 独立 Rig 与动画** | 参考当前本机 `viewmodel` 骨架，独立重定向、Bake、蒙皮；保留原手臂比例 | 肘/腕/指/手套/衣袖、枪柄、开火、换弹、检视、刀具等变形通过 |
| **S10 两套导出与 ModelDoc** | 分别导出 World/Firstperson FBX；校验哈希、材质和两套资源引用；编译 `.vmdl` | `source.blend` 与已导出 FBX 对应，ModelDoc 引用无旧路径、编译产物存在 |
| **S11 私人 Addon 部署/启动** | 先 dry-run，再显式 `--execute`；部署到 `csgo_addons/<addon>`，备份/回滚；启动工具或私人服务器 | 不写游戏本体、不处理受保护匹配；资源挂载与连接单独验证 |
| **S12 游戏内双视角验收** | 世界模型外观/动作；第一人称真正显示新手模；受击/死亡/ragdoll/复活；截图/日志 | World 和 FP **分别 PASS**；Hitbox/Physics 需引擎证据；失败 `PENDING/FAIL` |
| **S13 证据报告与回退** | JSON、文件哈希、动作帧、截图、编译日志、失败原因；修复回退上游阶段重跑 | 不能把“进了游戏”或“截图保存成功”冒充模型通过 |

## 2. S00：真正的“尺寸检测之前询问”

Agent 必须用一段简单对话向用户提问（如果当前对话已明确选择，不再重复）：

> 请选择模型尺寸方案：
>
> **1. 与本机默认 CS2 探员的主体高度相同**（只适用于人形；保留原人物四肢和身体相对比例）。
>
> **2. 指定另一个目标主体高度**（用户填写真实目标数值与统一单位）。
>
> **3. 按原始模型整体等比例缩放**（例如全模型 X/Y/Z 均乘 0.90 或 1.15，不允许分别缩放四肢）。
>
> **4. 保持原始主体高度不变**。
>
> 请同时确认模型属于人形还是非人形。装饰物不计主体高度，但仍做完整包围盒和骨骼动态检查。

**人形**有 1–4；**非人形**有 2–4，不会以人类探员身高作为强制目标。选 1 需要同上轴、同单位、去掉装饰物的本机探员参考主体高；选 3/4 需要测量**未修改原模型**主体高度。没有可信参考值时明确 `PENDING`，不能猜一个 CS2 “官方身高”。

### 2.1 本地配置交互命令

```powershell
# 在 Skill 根目录运行；先把模板复制为本机本模型专用的 .local.json
Copy-Item config/height_profile.humanoid.example.json config/height_profile.humanoid.local.json
# 如果不是人形，则改用 height_profile.nonhumanoid.example.json

# 真正询问角色类别、目标方案、所需参考值并保存；自动备份原 JSON
python scripts/height_choice.py --profile config/height_profile.humanoid.local.json --save
```

**无交互工具 / CI / 远程 Agent**：不能自己选默认模式；由用户明确确认后，才可使用类似命令持久化其选择：

```powershell
# 例：用户明确选择“人形、全模型整体缩放 0.92 倍”，且原始主体高实测 170（仅为示例单位）
python scripts/height_choice.py --profile config/height_profile.humanoid.local.json --model-type humanoid --mode uniform_scale --original-body-height 170 --uniform-scale 0.92 --confirm --save

# 例：用户明确选择“人形目标主体高 165（同一标定单位）”；此值只作示例，绝非官方 CS2 身高
python scripts/height_choice.py --profile config/height_profile.humanoid.local.json --model-type humanoid --mode custom_target --target-height 165 --confirm --save
```

自动工作流在 S03 Blender 首次高度审计**之前**检查 `height_choice`：交互终端若还未选择，直接显示以上菜单；非交互环境输出 `NEEDS_HEIGHT_CHOICE` 并停止。选择保存在 `height_profile.*.local.json` 的 `height_choice`，而不是只写一个不持久的“提示文字”。

### 2.2 先取得可信参考高度（仅当相应选项需要）

在 Blender 中导入当前游戏版本**有权使用**的标准探员参考资源，先分离/标记主体与饰件。复制 `config/height_reference_agent.example.json` 为 `config/height_reference_agent.local.json`，把其中 Armature、网格对象名改为该参考模型的真实名字。然后使用：

```powershell
# 测量默认探员主体参考，不把帽子、背包等装饰物算入
& 'C:\Path\To\blender.exe' -b 'D:\models\agent_reference.blend' --python scripts/blender_body_height_audit.py -- --config config/height_reference_agent.local.json --out reports/agent_reference.json --capture-reference

# 从完全未改动的原始模型抓取主体基准，供“整体倍率 / 保持原高”选择使用
& 'C:\Path\To\blender.exe' -b 'D:\models\original_fullbody.blend' --python scripts/blender_body_height_audit.py -- --config config/height_profile.humanoid.local.json --out reports/original_body.json --capture-original
```

两种捕获都不会修改几何。`--capture-reference` 输出 `agent_reference_body_height`，`--capture-original` 输出 `original_body_height`。没有上述模型/参考资源时，就让对应目标保持 `PENDING`，**不准臆造数值或默默取现有默认探员的四肢长度**。

### 2.3 实际等比例缩放（严格区分“计划”和“应用”）

`scripts/height_choice.py` **只记录选择**，`blender_body_height_audit.py` **只检测/建议倍数**，它们都**不会自动缩放**。计算公式：

`整体统一缩放倍数 = 用户目标主体高度 ÷ 当前去装饰主体高度`。

在经过备份的 Blender 工作副本中：检查 Scene Unit Scale 与模型上轴 → 识别完整角色根节点、Armature、所有受其驱动的主体网格/装饰物/挂点 → 在**同一个公共父级或成组对象变换层级**施加 XYZ 相同的缩放（避免父子重复缩放）→ 不单独编辑任何骨骼长度，也不修改单个肢体网格 → 审查导出时 FBX 变换/单位，确保不会双重缩放 → 将 World 与从原人物提取的 FP 手模保持同样的原始比例规范。

如果缩放后骨骼长度/权重/关节或第一人称握枪偏移出错，**回退至 S04/S09 修动画或挂点**，不要对四肢再做第二次局部拉伸。缩放后必须重新测主体高度，并复查静态/动态包围盒、碰撞、Hitbox、关节、衣袖、武器握持。

## 3. S01–S03：几何主体分类与高度检测

`height_profile.*.local.json` 必须写明：`model_type`、`armature`、`up_axis`、`body_mesh_objects`、`accessory_mesh_objects`、`mixed_meshes`（若合并网格）、`ignored_mesh_objects`、`exclude_accessories_from_height=true`、`height_choice`。对混合网格在 Blender Mesh Attributes 创建 **FACE 域** `BOOLEAN/INT` 属性 `cs2_height_body`；属于主体的面标 1，装饰物面标 0；不能把整张头发/帽子误标主体。装饰物顶部与主体边界共享顶点时检查分类边界是否合理。

脚本会对绑定在主体骨架上的未分类 Mesh 报错，避免漏算或错算。输出三个不同值：`body_bounds_excluding_accessories`、`accessory_bounds_excluded_from_height`、`full_visual_bounds_including_accessories`。后者用于完整 AABB/物理安全检查，但**不参与缩放目标**。

非人形需要额外配置 `primary_height_bones`（至少两个不同的真实主体骨骼，上下端覆盖主体垂直跨度）。装饰骨、武器骨等不得纳入该列表。对四足、爬行、漂浮、特殊多关节模型，必须手工校准哪些骨骼表示“主体顶/底”，必要时增加非变形测量辅助骨，不可用人形骨名硬套。

**通过标准**：用户已选目标；相同单位/上轴；主体尺寸落在配置阈值内；非人形主骨架与主体高度差落在单独阈值内；四肢相对比例依然通过原档骨长比对。状态 `WARN` 必须记录差异与建议，接近阈值时建议修复后再交付。

## 4. S04–S07：世界模型保比例绑定、裂缝与动作

1. **骨架**：先检测 Rest Pose 下原始和目标骨骼关节位置、旋转、局部缩放；禁止把源人物缩成默认探员的四肢长度。调整 CS2 目标骨架的节点空间/动画重定向、IK 目标、武器偏移，不动原模型人体比例。参考 `references/rigging-and-driving.md` 与 `references/v6-stretch-crack-recovery.md`。
2. **顶点组与蒙皮**：校验无效骨名、零权重点、未归一化、影响数、错误的左右权重；检查重复 Armature Modifier、双重父级蒙皮、Shape Key 与其它变形修改器组合。自动修复仅限安全的权重归一、人工指定接缝对。
3. **拓扑破口**：分开诊断原始真正缺面、未焊接接缝、角色衣领等合法开口、动画把缝拉开、背面剔除/法线假破洞。报告 Mesh、Vertex、Action、Frame；不做全网格 `Fill Holes`，不无差别 `Merge by Distance`。
4. **装饰骨**：头发/裙摆/披风/挂件等给单独权重与辅助骨，严格区分刚性随动与柔性链，审查与身体的穿模和极限动作；装饰物不参与身高，却必须参与全部动态渲染包围盒。Source 2 运行时是否支持某条次级动作，需要具体资源/服务器验证。
5. **极限动作**：肩、肘、腕、颈、髋、膝、踝、手指重点逐帧检查；对网格边长、面积、接缝距离采样。关节压缩不能简单当破洞，必须结合绑定姿势、权重和法线判断。对跑、转、蹲、跳、落地、举枪、射击、换弹、受击、死亡过渡、复活单独生成异常清单。
6. **死亡/Ragdoll**：动画触发、倒地物理、地面穿插、肢体刚体配置和复活恢复分别验收；Blender 播放通过不代表引擎布娃娃正常。
7. **修复再审**：保存新 `.blend`，计算哈希，重新运行全量审计，任一 FAIL 或关键 PENDING 阻止部署；修改几何后重算 AABB 和身高策略（装饰物仍排除）。

## 5. S08–S09：完整人物裁剪第一人称手模

- 首先完成世界主体比例确定，才从**未拉伸的完整原人物或同源已审修复副本**分支提取手臂、手掌、手指、手套、衣袖。复制原 `.blend`，在网格上以 `FP_KEEP_L/FP_KEEP_R` 人工选面/顶点组掩码标记，保留 UV/材质/初始权重，检查合法肩口。**不能根据身高自动估算手臂裁剪位置**。
- `--extract-viewmodel` 只生成手模候选副本，初步肩部边界须人工审核；从源图直接拆网格**不等于**已经完成第一人称骨架绑定。
- 单独使用本机当前 `viewmodel` 骨架，保留被裁剪手臂的原长、独立蒙皮和重定向、烘焙和检查持枪动作；不能把世界模型 Armature 直接当第一人称驱动。手腕/肘/肩口/手指/袖口接缝都要用动作逐帧查。
- FP 与 World 使用不同 `.blend` 和 `.fbx`、各自 SHA256；World 的全身缩放策略与 FP 的骨长/纹理兼容，但 FPS 手模本身**不按完整人体身高单独执行目标高度比较**。
- 第一人称检查开火、后坐力、换弹、检视、切枪、刀具、枪械握持；死亡时 FPS 手模隐藏、复活时正确恢复。完整步骤见 `references/v7-dual-viewmodel-extraction.md`。

## 6. S10–S13：编译、部署、启动、游戏内验收

- 单独导出 `character_world.fbx` / `character_firstperson.fbx`。在 ModelDoc 里核对两套实际引用、Skeleton、BodyGroup 或独立资源方案以及当前 AG2。不同视角**能不能在客户端实际切换**取决于当前资源加载方式，光编译成功不证明 FP 已替换。
- 将两份 FBX 和合法 `.vmdl` 放进**已有的** Workshop Tools Addon `content/csgo_addons/<addon>/`；用 ModelDoc/编译器得到相应 `game/csgo_addons/<addon>/` 资源。不修改受保护游戏本体/反作弊，不盲改 `gameinfo.gi`。
- 首先运行 `--deploy --compile --launch --game-test` **不加** `--execute`，检查计划和目标路径；确认私人环境可访问后才 `--execute`。脚本对部署文件备份、复制失败回滚；不会自行创建官方地图中的玩家模型替换能力。
- 本地 `sv_cheats 1` 只在你可控制的私人环境下开启且不替代正常资源挂载；自动操作前检查游戏就绪、窗口前台、仅本地服务器连接目标。死亡命令需要单独授权和观察者视角证据。
- 游戏验收将每个动作的 World/FPS 截图、动作时间点、编译日志、加载日志、异常诊断分开保存。静态/动态 Bounds 与 Hitbox/Physics 不可混为一谈；无实际引擎证据则 `PENDING`。

### 一键命令顺序（手动确认节点不能跳过）

```powershell
# 01 已准备好所有 .local.json 配置和源模型后，先问用户选择主体尺寸策略（或由 run 在交互终端自动问）
python scripts/height_choice.py --profile config/height_profile.humanoid.local.json --save

# 02 预检（只读）
python scripts/validate_skill.py
python scripts/auto_workflow.py doctor --config config/workflow.local.json

# 03 只有 P0 身高选择完整，才开始 Blender 源模型/高度/骨骼/权重/装饰物/关节/破口审计
python scripts/auto_workflow.py run --config config/workflow.local.json

# 04 人工确认接缝目标后，先模拟安全纠错（不会擅自补孔）
python scripts/auto_workflow.py run --config config/workflow.local.json --repair-seams --fix

# 05 确认修复和新导出条件后执行，得到新的 .blend / FBX；更新工作流输入路径
python scripts/auto_workflow.py run --config config/workflow.local.json --repair-seams --fix --execute

# 06 FP 裁剪必须单独一轮；先 dry-run 再执行提取
python scripts/auto_workflow.py run --config config/workflow.local.json --extract-viewmodel
python scripts/auto_workflow.py run --config config/workflow.local.json --extract-viewmodel --execute

# 07 人工在 Blender 完成第一人称 viewmodel 独立骨架、动作、蒙皮与导出
# 08 将新 FP 源文件/FBX 哈希写进双视角配置，并检查 ModelDoc 两个引用
python scripts/pin_viewmodel_export.py --dual config/dual_viewmodel.local.json --workflow config/workflow.local.json --execute

# 09 World + FPS 全量二次审计；不得用旧审计报告部署不同目标高度
python scripts/auto_workflow.py run --config config/workflow.local.json

# 10 模拟部署/编译/启动/游戏动作，确保无挡板/未确认操作
python scripts/auto_workflow.py run --config config/workflow.local.json --deploy --compile --launch --game-test

# 11 有明确本机专用服授权、所有门禁通过后正式执行
python scripts/auto_workflow.py run --config config/workflow.local.json --deploy --compile --launch --game-test --execute

# 12 检查 reports/run_*/workflow_result.json、各项审计、编译日志、截图及待人工复核项
```

**缺少第一人称重定向或独立 ModelDoc 引用时，不能用 `--execute` 跳过审核。** 如果后续更改用户高度策略，必须从 S03 重新跑尺寸/比例/动态 AABB 和所有受影响的导出/引擎检查。

## 7. 典型故障和正确回退

| 现象 | 高概率原因 | 应回退到哪一步 |
| --- | --- | --- |
| 选择默认探员等高后手臂拉长 | 把人体高度目标误当作四肢骨长目标；IK Stretch/约束/重复蒙皮 | S04–S05，保留人体比例，用统一缩放和目标偏移 |
| 头发太高导致检测身体“超高” | 头发/帽子仍标为主体面/Body Mesh | S02 重新分类装饰物；完整视觉 Bounds 仍计入 |
| 非人形骨架高度与身体不符 | 主骨架/关节定位、参考姿势/单位不匹配 | S03/S04 校准主骨架，不用扯长身体构件 |
| 用户更改目标身高后旧报告还显示通过 | 审计报告引用旧 `height_choice` 与目标高度 | S00 更新配置后 S03 完整重测；程序会阻止旧报告部署 |
| 膝盖弯曲时网格破口 | 动态接缝脱离、权重分裂或原网格未焊接 | S04–S07 逐动作定位顶点与 UV/法线；仅审查后局部修 |
| FP 手模还是默认的 | 插件只替换 World；FP BodyGroup/资源加载未接管 | S09–S12 检查实际 viewmodel 资源与挂载，不改世界手臂长度 |
| 死亡变形/布娃娃穿地 | ragdoll 物理、Hitbox、动画过渡不同步 | S07/引擎物理验证，不能靠截图直接 PASS |
| 编译成功但游戏模型仍旧 | FBX 旧版、ModelDoc 引用旧路径、编译缓存/Addon 挂载错误 | S10–S11 比对 Hash、编译输出和游戏实际加载证据 |

## 8. 推荐的输出证据与验收含义

输出应该包含 `height_choice.json`（或在 height profile 中保存）、`original_body.json`、`agent_reference.json`（仅选默认探员时）、`source_proportions.json`、`source_height`、`body_bounds_excluding_accessories`、`full_visual_bounds_including_accessories`、`joint_deformation.json`、`mesh_gap_audit.json`、`firstperson_extraction.json`、`firstperson_final_audit.json`、双 FBX SHA256、ModelDoc/编译日志、World/FPS 游戏截图、死亡/ragdoll/复活观察证据和最终 `workflow_result.json`。

`PASS_PRELIMINARY` 只说明离线几何/权重检查通过；`PENDING_RUNTIME` 表示尚未用当前游戏真实资源验证；`FAIL` 阻止部署。对视觉问题允许人工复核，但不能未经解释强行自动将 FAIL 改为 PASS。

## 9. 外部工具链说明

- [Source 2 Wiki — ModelDoc](https://www.source2.wiki/EngineTools/ModelDoc) 提供资源编辑工具概述；模型/材质与骨架资源的细节以用户当前 CS2 Workshop Tools 版本为准。
- [Valve Workshop Tools 索引](https://developer.valvesoftware.com/wiki/Counter-Strike_2_Workshop_Tools) 解释 Addon/工作流；CS2 引擎与社区插件更新很快。
- [CS2 AG2 模型转移社区工具](https://github.com/SergeantCS2/CS2-AG2-Model-Porter) 可作为当前迁移问题的参考，但不保证所有第一人称替换插件兼容。
- Blender 的 Armature、Skin/Weight、Mesh Cleanup 与动作 Bake 版本差异应在本机检验；本 Skill 不会静默改源档。

# v6：CS2 转模后「四肢被拉长 / 网格破口」故障定位与可回滚修复 SOP

> 本文为处理**已经发生的实际问题**编写。**优先保留原始人物身材比例**，而不是强制靠齐 CS2 默认探员的 Rest 长度。所有更改只写入副本，完成 Blender、ModelDoc、游戏内三级验收后才交付。没有源文件和原始比例基准时不可声称修好。

## 一、不要先动骨头：冻结 4 份证据

1. 保存 `01_original_unmodified.blend`：下载/导入后尚未绑定 CS2 骨架的原版，**只读**。
2. 保存 `02_imported_fbx.blend`：导入后尚未打权重的版本。记录单位、世界/局部坐标、X/Y/Z 轴向、FPS、FBX 导入参数。
3. 保存 `03_before_fix.blend`：正在出错的模型，包含实际 Armature 修改器、骨骼、Action、顶点组、所有其他修改器、材质、形态键。
4. 保存错误截图：Rest Pose 正面/侧面、左/右手臂和双腿、破口近景、同一位置弯曲前后 2 帧；记录 Action 名、帧号、对象名、网格顶点/面索引。不要先执行 Apply Pose as Rest Pose、自动统一长度或全模型 Merge by Distance。

**先归因再修复：**破口可能是网格拓扑开边、UV/法线/透明材质假象、接缝顶点未连接、相邻顶点权重不一致，或者肩/肘/膝变形塌陷；这些需要不同处理。

## 二、按顺序排查骨骼拉伸（绝不能直接对齐默认探员骨长）

### 2.1 在原模型捕获骨长基准

1. 在 Blender 打开 `01_original_unmodified.blend`，Object Mode 选源 Armature，检查没有额外 Transform、Armature 尺度造成的比例污染。源骨架可能叫 `mixamorig:`、`J_Bip`、`Armature`，逐项校准源关节名。
2. 编辑 `config/proportions.local.json`：每个上臂、前臂、大腿、小腿测量在**源模型**和**目标骨架**的对应关节；躯干/肩宽/骨盆宽指定可信的整体比例 anchor。不能把 Valve 探员写进 `source`。记录左/右骨骼是否真正对称。
3. 按命令捕获原版：

```powershell
blender -b "D:\models\01_original_unmodified.blend" --python scripts/blender_proportion_audit.py -- --mode capture --config config/proportions.local.json --out config/original_proportions.local.json
```

4. 不得在之后重新捕获变形后的模型覆盖这份基准。如果源 Armature 不可用，先人工建立关节位置标记及可信的尺度参考；缺失时判 `PENDING`，停止自动部署。

### 2.2 先排除对象变换和重复蒙皮

1. 打开 `03_before_fix.blend`，分别选 Armature 和身体 Mesh，`N → Item → Scale`。检查 X/Y/Z 是否为统一比例；有非均匀缩放先查明导入与绑定历史，不得直接对已蒙皮骨架按 `Ctrl+A → Scale` 盲目应用。
2. `Modifiers` 查看身体 Mesh：应只存在一个启用的、指向目标 CS2 Armature 的 `Armature` 修改器；检查是否存在其他 Armature、Mesh Deform、Lattice、Surface Deform、Hook、Geometry Nodes、Shape Keys 与父级 Bone Parenting 导致重复变形。
3. Armature → Pose Mode → 选 `arm_upper_L/arm_lower_L/leg_upper_L/leg_lower_L` 及 R 侧，检查 `Transform → Scale` / `Constraints`；特别找 `Stretch To`、`Copy Scale`、`Maintain Volume`、IK `Stretch`、`Spline IK`、复制了源骨架缩放的 `Copy Transforms`。记录控制器而不是盲删。
4. 逐个隔离临时约束/修改器的副本测试：只要关闭某项后四肢长度恢复，就定位到了可疑的**驱动链**，而不是网格拓扑。
5. 检查骨骼 `Inherit Scale`、父骨骼缩放与世界/局部矩阵的关系；Edit Mode Rest 长度和 Pose Mode 各帧头尾距离应分别验证。

### 2.3 确认是 Rest 长度错误还是动画引起的伸长

- **Rest 已经偏离原角色**：目标骨头被拖成默认探员尺寸，根因在转换/重新绑定。恢复原模型比例，按源身体关节布局建立目标 Rest 骨架；保持必要的 CS2 名称/父级/朝向映射，但不要假定此骨架必然与当前 AG2 可兼容。需要为新 Rest 布局配置合适的重定向、动画重烘焙或 IK 目标。
- **Rest 正确，动作才变长**：检查复制平移/缩放、IK 拉伸以及 Blender Action 是否给骨骼打了 Scale/Location 曲线。改用已校准的局部旋转重定向（如 Copy Rotation），必要的 IK 只改变**关节角度**，不通过拉长骨骼去够目标。未能到达武器握点时调整挂点/姿势或标记动作不兼容，不许挪长手臂。
- **骨长正确但皮肤被拉长**：检测胳膊/腿的权重分配、错误骨骼映射、父子层级、Bind Matrix 和多个 Armature 修改器；排查网格上次导出是否仍关联**旧**骨架。
- **Blender 正常，Source 2 里才拉长**：在 ModelDoc 对比 Skeleton、Rest、导入单位、引擎骨架引用、AG2 动画/IK；重新检查 `.vmdl` 使用的 FBX、FBX 骨骼名与实际编译产物路径。不能简单使用 `root_motion` 命名就认定所有动画可用。

### 2.4 恢复比例并重新绑定的推荐操作顺序

1. 从 `01_original_unmodified.blend` 复制原始网格和骨骼参考数据，作为视觉/数值基准。
2. 从**当前实际需要的 CS2 AG2 资源**读取目标骨骼命名、关键父级和控制接口（仅合法获得、同版本）。**骨骼名字/动画接口兼容**与**肢体长度相同**是两个不同要求。
3. 将目标骨架的肘、腕、膝、踝、肩、髋位置**按原人物的关节位置**调整。对比躯干、骨盆/肩宽；全身只允许已确认的统一等比例尺度，禁止按轴对四肢拉长。保存为另一个新的 Rest 骨架副本。
4. A/T pose 校准：源和目标姿态必须一致，再重新建立 Armature Modifier；最好先建立低风险的整体蒙皮，之后分别手工调肩膀、腋下、肘、膝、髋和手指。不要拿旧顶点组无条件套在结构变化很大的新骨架上。
5. 将动作从源骨架驱动目标骨架，先用 Copy Rotation（核对轴/空间）等约束，Bake Action 后关闭临时约束及源骨架，确保动作仍能独立播放。必要时采用适配该骨架的独立动画而不是强用不匹配的官方动作。
6. 在每个动作的每帧采样 Rest/Pose 长度，发现伸长超限则停止；再运行网格关节形变扫描，测试没有骨伸长但网格仍破开的情况。
7. `Preserve Volume` 可作为**某些旋转关节体积塌陷**的对照试验，但不会修复断开的拓扑、错误骨架映射或拉伸约束；记录打开前后对比，并以导出到 Source 2 后的实际结果为准。

## 三、网格破口：先找「真的缺面」还是「动态接缝」

### 3.1 Rest Pose 静态检查

1. Armature 切 `Rest Position`，身体 Mesh → Edit Mode，`A` 全选；`Select → Select All by Trait → Non Manifold`。注意服装袖口、领口、裤脚、发片、分层眼睛等**可能合法开放**，不能见边就补。
2. 检查边界边 `boundary_edges`、非流形内部边、孤立边、零面积面、孤岛。记录具体对象+索引。对多对象相接的胸甲/皮肤/衣袖，应比较两个对象边缘是否在参考姿态重合。
3. 开启 `Overlays → Face Orientation` 查看法线方向；`Shift+N` 重新计算法线只解决朝向，**不会填几何缺口**。关闭背面剔除或透明材质做对照，排除材质表现误判。
4. 如果是明确缺失面且应闭合：仅选择目标边界，按情况 `F` / `Grid Fill` 手动补，检查新面法线、材质、UV、顶点组以及动画下的连贯性。不要对整个身体执行无限制 Fill Holes。
5. 如果是重复、靠近的本应焊接顶点：先观察 UV/材质/权重是否必须分开（例如服装分层或硬边）。能确认属于同一表面且 UV/材质/权重一致才焊接；否则需要人工重建拓扑或重涂权重。

### 3.2 只在动的时候裂开（肘/膝/肩最常见）

1. 录下**动作、帧号和哪个关节**：例如 `run, f=34, elbow_L`；把同一处在 Rest / 45° / 90° / 极限姿势的顶点高亮。
2. 如果边界本就有两个几乎重合但不相连的顶点，给它们在 `mesh_integrity.local.json` 的 `reviewed_seam_pairs` 填真实对象名与顶点索引。扫描各动作中 `rest_gap → pose_gap` 的增长，区分有问题的动态裂缝与设计中的衣服开边。
3. 两侧顶点的蒙皮组不同（如一边 80% 前臂、一边 80% 上臂）：先重新分配两侧一致的骨骼影响；绘制平滑的过渡带而不是给整圈一个骨骼。注意左右骨名、Twist 骨、手套袖口的权重分布。
4. 皮肤关节挤压/三角面拉长：用 `joint_deformation.local.json` 设置关节中心、半径、采样动作和阈值；重点看 max edge change / area collapse、受影响面，不要靠自动挪长肢体解决。
5. 两个原本独立的对象因动画分开：比较是否应该共用相近的权重或通过同一根辅助骨跟随，而不是**盲目将衣服直接焊到皮肤上**。
6. 关节处少环线导致弯折裂形：保留原身体比例，增加合理环线、改拓扑走向、必要时修剪局部网格或添加**经过 CS2 导出验证**的辅助 Twist 骨。只在新副本修改并重新烘焙相关动作。
7. 用第一人称手模独立重复腕部、手指、握把、开火、换弹、检视检查；第三人称世界模型通过不代表第一人称也正确。

### 3.3 经人工审核后的限定自动焊接（可选）

先填写 `config/seam_repair.local.json`：`source_blend_sha256` 是**即将修的那个 .blend 的 SHA256**；`user_approved_exact_pairs=true`；每项写 `mesh`、`keep_vertex`、`merge_vertex` 和校准的 rest 距离、权重、UV 容差。默认模板中的索引只是示例，绝不能直接照抄。

```powershell
# 先仅验证；不会修改源文件
blender -b "D:\models\03_before_fix.blend" --python scripts/blender_seam_repair.py -- --config config/seam_repair.local.json --out "D:\models\04_seam_fixed.blend" --report reports/seam_fix_preview.json

# 明确审核后才保存新副本（不覆盖输入）
blender -b "D:\models\03_before_fix.blend" --python scripts/blender_seam_repair.py -- --config config/seam_repair.local.json --out "D:\models\04_seam_fixed.blend" --report reports/seam_fix_applied.json --apply
```

**自动焊接拒绝条件：**哈希不一致、顶点不是指定索引、存在 Shape Keys、多用户网格、两点已经共面/直接相邻、Rest 坐标不靠近、权重/UV/材质有明显差异、存在改变拓扑的修改器、输出文件已存在。*此工具不会补缺面、改顶点权重或自动猜测裂口的位置。* 应用后**必须在新 .blend 中重新检查 UV、权重、关节形变和包围盒**。修错就丢弃副本回到原始文件。

## 四、自动检查配置与命令

### 4.1 必需的 3 份新文件

- `config/rig_stretch.local.json`：`monitored_bones`（四肢原骨名，必要时含手模）、容许 Pose 骨长变化、采样率。会扫描 Stretch/Scale 控制器与重复变形修改器。
- `config/mesh_integrity.local.json`：`approved_open_meshes`（人工确认的合法开放**整个网格**）、自动近邻候选、`reviewed_seam_pairs`（人工审查过的疑似开裂顶点对），按自己的长度单位校准阈值。旧版网格破口检测只发现非流形边，新版另提供显式接缝逐帧证据。
- `config/seam_repair.local.json`：仅在确信顶点应焊接、且满足前述限制时使用；否则不需要配置 `--repair-seams`。

### 4.2 推荐顺序（使用实际模型时）

```powershell
# 0. 原始模型捕获，写入原始比例基准；基准只做一次并保持不可变
blender -b "D:\models\original.blend" --python scripts/blender_proportion_audit.py -- --mode capture --config config/proportions.local.json --out config/original_proportions.local.json

# 1. 配置完成后检查环境；扫描 Rest / Action / 模型完整性（默认不修改）
python scripts/auto_workflow.py doctor --config config/workflow.local.json
python scripts/auto_workflow.py run --config config/workflow.local.json

# 2. 审查报告；如果确实是焊接两点且通过限制，先 dry-run
python scripts/auto_workflow.py run --config config/workflow.local.json --repair-seams

# 3. 显式执行已批准接缝操作，另存后做全量复检（不会部署）
python scripts/auto_workflow.py run --config config/workflow.local.json --repair-seams --execute

# 4. 确定身体及装饰物对齐、保比例、所有关节动作通过后才开始部署演练
python scripts/auto_workflow.py run --config config/workflow.local.json --fix --deploy --compile --launch --game-test

# 5. 真实部署：须预先配置 Blender/CS2/FBX/ModelDoc 和本地服务，且获得设备授权
python scripts/auto_workflow.py run --config config/workflow.local.json --fix --deploy --compile --launch --game-test --execute
```

注意第 3 步产出的是新 `.blend`；第 4/5 步必须把 `workflow.local.json` 中的 `blend_file` 改成审核通过的**新副本**，并复核 FBX 文件来源。也可在同一流程使用 `--repair-seams --fix --deploy --compile --launch --game-test --execute`，但必须确认源哈希对应当前输入，并启用配置中的安全导出及 ModelDoc 实际 FBX 引用；若含装饰骨骼创建，建议分开运行、重新记录哈希。

### 4.3 期望的 JSON 结果

`reports/run_*/blender_audit_before.json`（或实际生成的 `_before` 后缀）应包含：

```json
{
  "checks": {
    "source_proportions": {"status": "PASS"},
    "rig_stretch": {"status": "PASS_PRELIMINARY"},
    "mesh_integrity": {"status": "PASS_PRELIMINARY"},
    "joint_deformation": {"status": "PASS_PRELIMINARY"}
  }
}
```

上面只是**字段和目标状态示例**，不是实际已通过的报告。具体不合格项见 `findings`、`issues_prioritized.json`、`mesh_integrity.topology`、`rig_stretch.stretch_samples`、`joint_deformation.joints`，检查 Action+帧+索引即可定位。

## 五、全流程交付门禁与顺序

| 阶段 | 必须确认 | 失败处理 |
| --- | --- | --- |
| 0 冻结源文件 | 原版不变 + 当前错误文件 + 来源 hash | 缺失 PENDING，不准无基准「修复」 |
| 1 源骨架比例 | 原始骨长、全身等比、Rest 坐标 | 比例不对，先重新绑定 |
| 2 静态网格 | 开边、非流形、丢面、法线、UV、材质 | 只修确认错误的局部网格 |
| 3 目标绑定 | 骨骼父级、变形骨、单一 Armature、原始肢体长度 | 重定向/权重重新制作，禁止骨拉伸 |
| 4 关节动态 | Rest 和跑步/蹲伏/跳跃/换弹/转身/极限弯曲每帧 | 记录骨、顶点、面、帧，局部修复重测 |
| 5 动态接缝 | 经过人工确认的 seam pair 增长不超阈值 | 调权重或局部焊接，重新审计 |
| 6 装饰物/手模 | 独立骨、权重、弯曲、不穿模 | 独立修，不能改身体比例 |
| 7 导出 | FBX 对应**当前复检通过**的 blend，Rest/材质/动画记录 | 阻止使用旧 FBX |
| 8 ModelDoc | 正确 skeleton、mesh、AG2 资源引用及编译日志 | 清理引用、重新编译 |
| 9 私人服游戏 | 第一/第三人称、武器、死亡/布娃娃、Hitbox、物理 | 未获真实证据 `PENDING` |

**动画清单最少包括** idle、walk、run、turn、crouch、crouch_move、jump_start、airborne、land、aim、fire、reload、weapon_swap、knife、hit_react、death_transition、ragdoll_fall、ragdoll_rest、respawn；第一人称 hands 独立检查。`runtime_only` 状态由 CS2 引擎实测，不能凭 Blender Action 名下结论。

**特别说明：**Blender 的变形算法（如双四元数体积保持）与 CS2 AG2、IK、布娃娃碰撞、Hitbox 并非同一个运行系统。即使 `PASS_PRELIMINARY`，依然需要 ModelDoc 与 CS2 **私有测试环境**实证；不能在官方对战环境通过注入或绕过反作弊实现模型替换。

## 六、故障快速判断表

| 现象 | 优先定位 | 不应该做的事 |
| --- | --- | --- |
| T pose 就已比原版长 | 目标 Rest 骨长、导入尺度、错误默认骨架映射 | 直接让 Mesh 跟默认探员变长 |
| Rest 正常，IK 动作变长 | Stretch To / IK stretch / Scale 曲线 / Copy Transforms | 盲目 Scale Apply、仅重涂权重 |
| 骨头没变长，皮肤像橡皮筋 | 双重 Armature / 骨名映射 / 权重过渡 | 调骨长掩盖坏蒙皮 |
| 静止就见到孔 | Non Manifold / 丢面 / 法线、Alpha 材质 | 全网格 Fill Holes |
| 只在肘、膝弯折时裂开 | 相邻接缝顶点权重不同 / 分离网格 / 细分不足 | 用全身缩放把孔挡住 |
| Blender 正常，游戏中裂开 | FBX 源文件错误 / ModelDoc 编译旧资源 / 引擎蒙皮与约束差异 | 直接宣布 Blender 通过=游戏通过 |
| 第一人称手指异常 | 独立 hands skeleton、手腕权重、武器挂点 | 以第三人称测试替代 hands 验收 |

## 七、依据与边界资料

- Blender 官方：<https://docs.blender.org/manual/en/5.2/modeling/modifiers/deform/armature.html>（Armature / Preserve Volume）。
- Blender 官方：<https://docs.blender.org/manual/en/5.3/modeling/meshes/editing/mesh/cleanup.html>（Merge by Distance / Fill Holes）。
- Source 2 addon 与编译：<https://www.source2.wiki/Basics/working-on-content/addons> 与 <https://www.source2.wiki/Basics/installS2Sdk?game=cs2>。
- Source 2 compiled/runtime 与源文件区别：<https://www.source2.wiki/Basics/content-mounting>。

# v7：从完整人物裁剪第一人称手模 → 独立绑定 → 双视角编译与实机验收

> 适用 CS2 玩家模型（不是普通展示 prop）。此手册是操作 SOP。**原完整人物的四肢比例是几何基准**；不得拉长四肢以配合 Valve 探员。第一人称模型从同一原始全身人物取几何，和第三人称使用**不同的蒙皮与动画驱动**。

## A. 为什么不可以“复制世界模型手臂直接部署”

CS2 参考探员的完整模型资源可包含不同 Mesh Group 与第一人称手臂；手套可能独立。当前运行时需要区分 `worldmodel`、`viewmodel` 和 `uimodel` 的 AG2 资源。**同一角色的外观来源可以相同，运行时骨架/手臂资源不一定相同**。`viewmodel.vnmskel`、`worldmodel.vnmskel`、BodyGroup、AnimGraph2List 等需以当前游戏资源实际导出的可用参考为准。社区教程里展示的 `first_or_third_person`、`firstperson_default_gloves_arms` 等是**版本相关的模板例子**，不可保证对每一个角色、服务器插件和游戏版本无需调整。

参考：
- [Source 2 Viewer CS2 文件位置](https://s2v.app/ValveResourceFormat/games/counter-strike-2.html)
- [Source 2 Viewer 导出和额外网格](https://s2v.app/ValveResourceFormat/guides/exporting-models)
- [CS2 AG2 模型迁移社区报告](https://github.com/SergeantCS2/CS2-AG2-Model-Porter)
- [社区 AG2 手模 + BodyGroup 更新教程](https://steamcommunity.com/sharedfiles/filedetails/?id=3196629717)

## B. 方案与产物（先冻结，再加工）

| 名称 | 来源 | 用途 | 禁止 |
| --- | --- | --- | --- |
| `original_fullbody.blend` | 未修改的原模型 | 四肢骨长/网格/衣服真实性来源 | 直接覆盖或拉伸 |
| `world_final.blend` | 世界模型的修复副本 | 其他玩家所见的完整身体 + 装饰骨 + 死亡物理 | 以 Valve 身材为基准改长度 |
| `firstperson_cut_preview.blend` | 对全身模型中手臂/手掌/衣袖/护具的**非破坏性复制裁切** | 第一人称几何候选 | 以此作为已绑定可部署模型 |
| `fp_final_rigged.blend` | 手工换绑并烘焙到 viewmodel rig | 玩家自己视角里的手模 | 直接复用世界模型 Armature |
| `character_world.fbx` + `character_firstperson.fbx` | 两套单独导出 | ModelDoc 网格源 | 冷不防导出旧文件 |
| `character.vmdl`（或两个 `.vmdl`） | ModelDoc 检查引用 | BodyGroup、AG2、编译源 | 把编译成功当加载成功 |

## C. 可照做的 Blender 裁剪步骤（一次性）

1. **原始模型留档**：在 Blender 打开完整源 `original_fullbody.blend`，先备份并做 SHA256，然后**另存为 `fullbody_extraction_source.blend` 工作副本**，原始文件设为只读。此后所有手臂选择掩码都画在这个工作副本上，绝不可修改原档。不得先把人物拉到 CS2 探员四肢比例。运行 v6 的 `blender_proportion_audit.py --mode capture` 建立原始四肢长度基准。
2. **确定第一人称可见范围**：在第一人称透视测试姿势下标记左右肩部以下的外露上臂、前臂、手掌、各手指、手套（若原模包含）和衣袖。截断点应在相机不可见处，不能在肘/腕附近随意断开；保留与手背、袖口、护腕衔接的完整环。若是独立 Sleeve/Glove 物体，按对象分别制作掩码。**不是所有模型都需要复制整个肩膀或上半身。**
3. **创建人工区域掩码**：选中 `Body`，进入 `Edit Mode`，在 Mesh 顶点/面选择模式选择左右手臂全套面（包括相应衣袖，但不要误选胸、头、腰、腿）。切到 `Object Data Properties → Vertex Groups`，新建 `FP_KEEP_L`、`FP_KEEP_R`，给相应选中顶点设置 Weight=1.0，再按 Assign。若袖子是独立 Mesh，在袖子网格上也各自建组。检查 Mask 不带到躯干，左右手指都完整；重叠的顶点可按需要同时在两组中，但要避免意外融合。**可另建单独的 `FP_KEEP_GLOVE`/`FP_KEEP_ACCESSORY`，相应加入配置。**
4. **检查截断边**：以 Mesh 编辑模式查看预期的肩部面环和 UV 分界。先不要 `Fill Holes`、`Merge by Distance`。原先本来开放的袖口需要与手模相连或正确遮盖；真正的缺面需在副本上局部补面并检查法线、权重、UV。记下合法肩截断边的位置和截图。仅当人工确认后才将配置项 `approved_shoulder_cut` 置为 `true`。
5. **配置裁剪**：复制 `config/viewmodel_extraction.example.json` 为 `config/viewmodel_extraction.local.json`。把 `workflow.local.json` 的 `firstperson_source_blend_file` 指向**带掩码的全身工作副本**，而 `blend_file` 继续指向独立世界模型。填写真实的 `source_armature`、每个 `parts[].source_object` 和 `output_object`。如果源模型没有独立 Sleeves 物体，从模板中删掉对应条目，改成单个 Body 条目即可。`min_face_fraction=1.0` 默认要求三角/多边形所有顶点都已被掩码标记；默认不会猜手臂在何处。
6. **先试运行**：

```powershell
python scripts/auto_workflow.py run --config config/workflow.local.json --extract-viewmodel
```

   检查 `firstperson_extraction.json` 里的 `selected_faces` 与 `open_boundary_edges`，避免几乎整个 Body 被选中，或没选到手指。退出码非零必须先修人工掩码。
7. **确认后单独执行提取**：

```powershell
python scripts/auto_workflow.py run --config config/workflow.local.json --extract-viewmodel --execute
```

   输出 `reports/run_*/firstperson_cut_preview.blend` 和提取报告。原始 `.blend` 不被覆盖。新 `.blend` 仍包含完整世界模型对象，裁剪出的第一人称 Mesh 单独放在 `CS2_FP_EXTRACTION_PREVIEW` 集合下。这个脚本只复制 Mesh、UV、材质、原始蒙皮、形态信息中安全支持的部分；包含 Shape Keys 的网格会拒绝自动裁剪，避免误破坏。
8. **只在新的 FP 工作副本中继续制作**：将上述预览另存为 `fp_final_rigged.blend`，在这个新文件里把源世界模型隐藏或放入不导出集合（必要时手动清理），但不要修改原全身文件。验证裁剪后肩截断确实位于摄像机视野外。**脚本没有自动封闭肩口，这属于有意保留的边界，必须人工审查。**

## D. 单独绑定第一人称骨架（真正解决“握枪时拉伸”）

1. 从你本机当前 CS2 安装中的可信角色参考资源导出 **viewmodel 骨架**，检查它的骨名、层级、Rest Matrix 和 AG2 使用方式；不要用旧 CS:GO `ValveBiped` 名称强推。只为本地自建资源和允许的开发环境工作。
2. 在 `fp_final_rigged.blend` 内保留裁剪手臂，导入或创建**独立**目标 Viewmodel Armature。世界模型骨架只用于计算源骨骼和比对原始长度，最终不应驱动 FPS 手臂。
3. 建立 `config/firstperson_bone_map.local.json`，填写从源骨骼到目标骨骼的实际映射。必须包含左右上臂、前臂、手、手指；武器/握持相关挂点按当前 viewmodel 参考配置。手臂仍应使用**原人物上臂/前臂长度**，而不是拉长到默认探员的手部位置。
4. 建立源-目标参考姿势，用关节**旋转**、目标定位、IK 目标调整和持枪 Offset 来使握枪合理。约束转移动画时禁用 IK Stretch、Stretch To、意外 Copy Scale、非均匀 Object Scale；约束在 Blender 内用于制作，完成后 `Pose → Animation → Bake Action`（启用 Visual Keying、Clear Constraints 的选择需根据工程备份决定），检查烘焙后单独驱动仍正确。
5. 将网格变形权重归到 Viewmodel 骨骼：为每个变形骨骼对应顶点组，按手腕/肘/手指调整权重，确认每顶点有效权重归一、没有原世界骨骼组错误影响。新 Mesh 的 `Armature` 修改器**只能指向独立 Viewmodel Armature**；检查父级不会再次二次变形。重定向骨架的某些辅助骨骼名会不同，不能只做“重命名顶点组”而忽略 Rest Matrix。
6. 沿用原模型四肢基准做静态与逐帧比例检查。对肩、肘、腕、指根分别摆动 0°/45°/90°/极限姿势，截图检查塌陷、突刺、拉长、袖口与手腕分离、手套穿模；检查手指与枪柄/扳机/弹匣接触。任何被拉长的情况先修驱动或权重，不允许修成默认探员比例。
7. 第一人称动作至少采样 `draw / idle / fire / reload / inspect / switch / knife`，并补上急停、蹲伏、视角转动、开火后坐力。**死亡**属于第三人称死亡/布娃娃物理链路；第一人称主要检查死亡瞬间手模隐藏、复活后重新出现与武器状态，不应对 FPS 手臂强行运行世界模型布娃娃。
8. 将已在各关节测试通过的模型另存为独立 `fp_final_rigged.blend`，在 `dual_viewmodel.local.json` 填真实对象名、原始提取报告路径、骨骼映射路径、逐动作验证标志和肩截断审核标志。审计脚本若未通过这些门禁不能进入自动部署。

## E. 双视角模型导出、ModelDoc / AG2 配置

1. 世界模型单独导出 `character_world.fbx`，只包含 World Armature、Body、World Accessories。第一人称单独导出 `character_firstperson.fbx`，只包含 FP Viewmodel Armature、FP Arms、FP Sleeves、FP Gloves；**不要全场景导出**。这一步的 FBX 由用户在 Blender/可信导出工具中明确执行并验证；`--extract-viewmodel` 只输出几何预览 `.blend`，不会假装已经生成可运行 FBX。
2. 在 ModelDoc 中可选择：**共享角色 `.vmdl` + BodyGroup**（推荐先研究当前参考探员），或 **独立 `.vmdl`**。若共享，参考你目前游戏资源的 `first_or_third_person` mesh groups、`worldmodel.vnmskel` / `viewmodel.vnmskel` 与 `AnimGraph2List`。只在可运行参考验证后才把这些名填入配置；不要把社区示例当绝对官方 API。
3. 在 `dual_viewmodel.local.json` 选择 `packaging_mode = "shared_bodygroup"` 或 `"separate_vmdl"`，为前者提供 `shared_modeldoc_vmdl`、`compiled_shared_model`、`bodygroup_verified`、`ag2_viewmodel_skeleton_verified`；为后者提供单独 FP 的 `.vmdl`/`.vmdl_c` 路径。两种方式都需独立第一人称 `.fbx` 和明确的 `modeldoc_viewmodel_fbx_reference_verified`。
4. 在 `workflow.local.json` 的 `deploy_files` 明确列出**两套 FBX**、ModelDoc 源；`compile_sources` 与 `required_compiled_files` 列出所有必需资源。计算 `fp_final_rigged.blend` 和 `character_firstperson.fbx` 的 SHA256，分别填进 `dual_viewmodel.local.json` 的 `firstperson_blend_sha256`、`firstperson_fbx_sha256`；只要文件再变动，旧哈希会阻止部署。Windows 示例：

```powershell
(Get-FileHash 'D:\models\fp_final_rigged.blend' -Algorithm SHA256).Hash.ToLower()
(Get-FileHash 'D:\models\export\character_firstperson.fbx' -Algorithm SHA256).Hash.ToLower()
```

5. 对 World 与 Firstperson 两份 `.blend` 分别配置 AG2 检查、原始比例、关节变形、破口与静态/动态 AABB 审计。注意裁剪肩口是**人工作出许可的例外**：不能通过把整个 FP Mesh 加入无条件白名单来掩盖其他手套/袖口破口。

## F. 优化后的“一键检查与双模型部署”

```powershell
# S0 检查工具、路径与源模型（不写入游戏）
python scripts/auto_workflow.py doctor --config config/workflow.local.json

# S1 完整世界模型修复完成后，单独裁剪（先 dry-run）
python scripts/auto_workflow.py run --config config/workflow.local.json --extract-viewmodel
python scripts/auto_workflow.py run --config config/workflow.local.json --extract-viewmodel --execute

# S2 人工完成独立 Viewmodel Rig、权重与动画；录入 FP 骨架、源基准、Hash、ModelDoc 引用
# S3 重新扫描世界/第一人称（默认只读）
python scripts/auto_workflow.py run --config config/workflow.local.json

# S4 双资源部署/编译/本地私人服测试预演
python scripts/auto_workflow.py run --config config/workflow.local.json --deploy --compile --launch --game-test

# S5 具备真实 CS2、本机专用服务器及桌面控制授权后，再真实执行
python scripts/auto_workflow.py run --config config/workflow.local.json --deploy --compile --launch --game-test --execute
```

**注意**：本版工作流仍不会替你自动重定向第一人称骨骼，因为参考姿势、骨骼名、原人物比例和武器驱动没有通用可靠映射。`--fix` 对世界模型执行保守权重归一并重新导出，但**不会自动重新导出 FP FBX**。任何改变第一人称 `.blend` 后必须重新手动导出 FP FBX、更新两个 Hash、复检，才能继续部署。

## G. 游戏内双视角验收矩阵

| 场景 | 第三人称 World | 第一人称 FPS | 不通过症状 |
| --- | --- | --- | --- |
| idle/跑/停/转/蹲/跳/落地 | 身体网格/骨骼/包围盒/装饰骨 | 持枪手模是否存在、位置 | T-pose、手模是默认的、手臂被拉长 |
| 手枪/步枪/刀具切换 | 世界模型右左手持武器 | 独立手腕/手指握持 | 手穿枪、枪飘、套默认手臂 |
| fire/recoil/reload/inspect | 手、肩、枪口位置、关节裂口 | 枪械后坐力、弹匣操作、袖口接缝 | 动作拉伸、分离、权重飞点 |
| 第一人称转第三人称（受控观察） | 仍是完整角色 | 自己看到独立 FP 手臂 | 双模型同时显示、手模丢失 |
| 受击/死亡/布娃娃 | 世界模型死亡动作与 ragdoll | 手模隐藏 | 断肢、死后 FPS 手还悬浮 |
| 复活/重新装备 | 世界模型比例恢复 | 手模恢复且武器握持不偏 | 变形残留、第一人称没加载 |

1. 保存每个动作的多帧截图、视角及时间点；与校准的同视角基准比对。截图只能提供视觉异常线索，不是精确 Hitbox 或骨骼物理测量。
2. 需要分别记录 `worldmodel_loaded` 和 `firstperson_loaded`，而不是只检测世界模型成功。私人服务器插件可能只实现世界模型替换而不接管 FP 手臂。未确认 FPS 模型资源实际切换之前，最终状态始终 `PENDING_RUNTIME_VIEWMODEL`。
3. `sv_cheats 1` 只限本地私人测试；它不会让任何未挂载的第一人称资源自动生效。禁止在 Valve 匹配/受保护服务器上测试可疑替换方案。
4. 若编译成功但 FP 仍为默认手臂：核对 `viewmodel` Mesh Group、骨架引用、游戏资源挂载、第一人称插件能力以及是否编译到正在加载的 Addon。**不要通过拉长世界模型手臂凑合。**

## H. 故障诊断（直接跳转）

- **提取了躯干**：Mask 画到胸口/肩带 → 重画 `FP_KEEP`，提高 `min_face_fraction`，勿默认自动按顶点高度裁剪。
- **肘部破口**：裁剪恰好在关节/网格已有分离 → 移肩截断到不可见位置，重新权重与动态 seam audit；不能全局 Fill Holes。
- **手腕与袖口分离**：保留原版间距、检查两物体动作为同一 viewmodel 骨架，必要时局部焊接/遮盖并复核 UV 与权重。
- **握枪时手臂伸长**：IK Stretch/错误 Rest/双 Armature/ Copy Scale；调武器/手的目标偏移或动画旋转，不拉长原模型骨长。
- **新 FBX 游戏仍显示旧手模**：ModelDoc 实际引用、Hash、compile_sources、插件是否只替换 worldmodel、客户端是否加载 FP meshgroup；必须按证据阻断发布。

## I. 各阶段门禁

| 阶段 | PASS 必须满足 | 未通过时 |
| --- | --- | --- |
| 裁剪 | 源 hash 不变；区域经人工掩码；左右手指、衣袖完整；合法肩截断已审核 | 不能申请视角绑定 |
| FP 绑定 | 独立 viewmodel rig、无伸长/非均匀缩放、原四肢比例通过 | 停止动画导出 |
| 动作与拓扑 | 手腕肘指关节动作、握枪、枪械开火换弹、袖口接缝通过 | 记录 Action/帧号/顶点 |
| ModelDoc | 两套 FBX 引用与 AG2 匹配，bodygroup/独立路径已核验 | 禁止编译发布 |
| 部署 | FBX/Blend Hash 固定；两套部署清单齐备；编译输出真实存在 | 停止启动 |
| 运行时 | 世界/第一人称均成功显示、完整动作无裂口、死亡复活正确 | `PENDING_RUNTIME` 或 `FAIL`，不得宣称成功 |

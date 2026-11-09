# v5 装饰物独立骨骼、自然次级动作与关节变形验收

> 面向 CS2 AG2 的第三人称 worldmodel，以及独立 first-person viewmodel/arms；运行阶段只在经过授权的本机私人环境中测试。
> 核心不可破坏约束：**原始人物的手臂、腿部、躯干长度比例不变**。装饰物骨骼不得反向重构人物主骨架，也不得为追随标准探员骨架去拉长四肢。根骨骼/肩膀/髋部等原模型结构是锚点；辅助骨骼仅添加子节点，不覆盖关键 AG2 骨名。

## 1. 分层绑定：不同装饰物选不同链路

| 装饰物 | 推荐源文件建模 | 骨骼锚点（示意，需校准） | 驱动方案 | v5 能自动做什么 |
| --- | --- | --- | --- | --- |
| 刚性胸针/腰带扣/硬壳挂件 | 单独 Mesh | `spine_3` / `pelvis` | 随父骨骼刚性跟随 | 创建单根辅助骨；明确授权时自动赋单骨权重 |
| 发辫/长发束 | 一根或多根可弯曲 Mesh | `head_0` | 多节骨骼，权重渐变；Bake 关键帧或经 CS2 验证的运行时约束 | 创建 2-4 根以上链；用户授权可生成线性初稿权重；检查每节覆盖及摆动 |
| 围巾/衣摆/背包带 | 分件、顶点分段 | `neck_0` / `spine_3` / `pelvis` | 多节骨骼 + 动作驱动；必要时独立布料/物理资源 | 创建骨链、检查权重、关节动态形变与源动画摆动 |
| 披风/裙摆/宽布片 | 多根横向/纵向辅助骨链或布料系统 | `spine_2` / `pelvis` | 优先专门布料设置；单链不足以保证二维布料自然 | 检查显式骨链；运行时布料、碰撞需 ModelDoc 和游戏复核 |
| 第一人称袖口/手表/饰品 | 独立 viewmodel 配件 | `hand_L` / `hand_R` 等 | 单骨跟手或局部摆动骨 | 单独 audit，检测持枪、换弹、检视时的摆动与穿模线索 |

不要认为 Blender 的 `Cloth`、`Spring`、`Rigid Body`、`Driver`、`Damped Track`、`Child Of` 可以原样成为 CS2 运行时系统。Source 2 资源有骨骼约束、物理关节和布料/次级骨骼等概念，但不同游戏和资源通道兼容性不同；需要在当前 CS2 ModelDoc 编译资源中查看能否导出，并以私人服实测为准。推荐先尝试 **Blender 内模拟/手工制作次级动作 → Bake Action → 再检查 Source 2 引用与游戏驱动**。如果 AG2 不读取自定义装饰骨的动作，就必须另外设计可用的 Source 2 驱动，不应隐藏为 PASS。

### 1.1 安全创建步骤

1. **备份源模型**，保存原始 `.blend`、骨骼比例 JSON（v4）。区分世界模型和第一人称手模的独立源文件。
2. Blender 中将头发、手链、围巾等分成**独立网格对象**，名称稳定，标记自定义属性 `cs2_accessory=true`；不可把该对象混入普通身体网格从而整件覆盖错权重。
3. 复制 `config/accessories.example.json` → `config/accessories.local.json`。填写当前 Armature、每个 `mesh_objects`、`anchor_bone`、每根新骨的 `head/tail` **骨架对象局部坐标**。这些位置必须从原始模型量取，不是默认探员身高数据。
4. 每根装饰骨维持有长度、明确的父子链：锚点 → `acc_hair_L_01` → `acc_hair_L_02` → ...；建议使用 `acc_` 前缀并避免覆盖游戏关键骨名称。新增 `use_deform=true`；头发/布料要逐节权重过渡，挂件可纯单骨跟随。
5. 验证图形和层级后，才将 `rest_positions_approved=true`。未人工核对时自动创建脚本会拒绝真正修改。
6. 以下命令先预演，再保存**新文件**（原始模型不覆盖）：

```powershell
blender -b "D:\models\character.blend" --python scripts/blender_accessory_setup.py -- --config config/accessories.local.json --out reports/character_with_acc.blend --report reports/accessory_setup.json
blender -b "D:\models\character.blend" --python scripts/blender_accessory_setup.py -- --config config/accessories.local.json --out reports/character_with_acc.blend --report reports/accessory_setup.json --apply
```

7. 默认 `weight_mode=manual`，需要在 Weight Paint 里完成根部固定、节点间渐变、避免配件脱离的权重。若要自动生成**初始权重**（**仍要逐关节审阅**），仅对指定的独立配件 Mesh 设置：

```json
{
  "mode": "secondary_baked",
  "weight_mode": "chain_linear_auto",
  "allow_replace_weights": true,
  "approved_chain_skinning": true
}
```

它以用户指定的相邻骨骼线段做最近距离投影、两骨线性混合（最多两根辅助骨影响每顶点）。会**清除该装饰物网格原顶点组**以避免叠加权重，绝不操作身体网格；所以必须单独保存副本、按需使用，并通过蒙皮/形变复检。刚性配件只允许单骨 `rigid_auto + allow_replace_weights=true`，不要用到柔性布料。某些精细披风、双层衣摆仍需人工权重、碰撞代理或真正的布料工具。

8. 通过 `blender_audit.py --accessories ...` 核验骨骼链、亲子关系、每个装饰骨是否有顶点权重、配件网格覆盖率。`cs2_accessory=true` 但未出现在清单中的网格应 FAIL；名字含 hair/scarf/cape/pendant/围巾/发辫等明显配件线索的**未分类网格**会触发待核对警告（仅启发式，可能漏报/误报，`inventory_name_hints` 可配置）。没有配件则显式写 `accessories=[]` 和 `no_accessories_confirmed=true`，不可让程序“猜测没有”。

### 1.2 次级动作与抗拉伸

- `rigid`：一根子骨刚性跟随锚点即可；不要求摆动。
- `secondary_baked`：至少 2 根辅助骨，在 Blender Action 关键帧中独立摆动；检查相对父节点的局部旋转是否变化，骨骼真实长度是否增长。缺少实际摆动、动作 Action、配件权重时只能 `PENDING/FAIL`。
- `runtime_secondary_candidate`：仅表示计划在 Source 2 运行时通过真实支持的骨约束/布料配置驱动；源骨架合格 ≠ 运行时驱动有效。
- **运动测试**：待机、起步、跑步/停止、急转、蹲伏/起立、跳跃/落地、开枪后坐、武器切换、受击、死亡、布娃娃、复活。披风和头发应回归稳定、无持续无限摆动、无穿透身体/地面；动画极端姿态必须检验动态 AABB。
- 不允许骨骼被拉伸、无意缩放或因父骨缩放继承而尺寸漂移；第一人称腕部/袖口特别关注换弹、检视。`blender_proportion_audit.py` 仍优先保护原人物身体，不得将装饰骨检查作为放宽身体四肢比例的理由。

## 2. 逐关节动态网格变形验收

### 2.1 准备条件

1. `config/joint_deformation.example.json` → `config/joint_deformation.local.json`，校准每个骨骼对和关节半径。示例 `radius=0` **故意阻止直接假通过**；半径以**原模型的 Armature 局部坐标单位**填写（不要把整个人物坐标系错当某一骨骼局部空间）。
2. 用 `ag2_profile.local.json` 的 `actions` 指定经过确认的源动画动作名字；理想情况至少采样 walk/run/crouch/jump/fire/reload 等使关节弯曲的 Action。未包含游戏专用 AG2 状态应留在运行时待检查项。
3. 在 `joint_deformation.local.json` 对每个关节可设置 `mesh_objects`，以排除不相关服饰；默认扫描所有与目标骨架绑定、并且未声明为装饰物的网格。不要把帽子拉扯导致的异常误记为肘部。
4. **装饰物自身的弯曲节点也可加入关节检测**：在 `joint_deformation.local.json` 追加 `parent_bone=acc_hair_L_01`、`child_bone=acc_hair_L_02`、`mesh_objects=["Hair_Strand_L"]` 的检测项，配合标定后的 `radius`。默认自动扫描排除装饰网格，但明确指定 `mesh_objects` 时可以单独检测辅助骨骼关节。
5. 关节采样需要保持拓扑和顶点顺序：含改变拓扑的 modifier 时返回 `PENDING_TOPOLOGY_CHANGED`，不能与另一网格的顶点索引直接比较。

### 2.2 算法与阈值

脚本使用 **经修改器求值的 Rest Pose 网格**作为基准。在目标关节中心的球形区域内，筛选对 `parent_bone/child_bone` 有有效蒙皮权重的顶点、边与三角面，然后逐 Action 采样。

- **边长度比**：`current_edge_length / rest_edge_length`。例如默认最大变化 45%，比值 >1.45 或 <0.55 报异常（这是工具阈值，不是 CS2 官方限制）。
- **三角面面积比**：`current_area / rest_area`，默认最大变化 70%；面积压缩到 0.3 以下或增大到 1.7 以上报异常。用于找挤扁、塌陷和异常拉丝。
- **证据粒度**：记录 `joint`、`mesh`、`action`、`frame`、问题边/三角形对应顶点索引、比值、错误数量及采样范围。
- **易误判项**：肘膝弯曲、皱褶、夸张卡通造型等本来就有面积压缩；应据实际模型试动作调校半径和阈值，不要直接自动修改骨长或通过加缩放掩盖问题。
- **尚未自动证明**：自相交、衣服穿皮肤、真实体积保持、法线朝向拓扑反转、游戏内 ragdoll/碰撞；这些要用同视角截图、慢动作录像、Mesh 自交检测或引擎调试补齐。

检查命令：

```powershell
blender -b "D:\models\character.blend" --python scripts/blender_audit.py -- --config config/ag2_profile.local.json --bbox config/bbox_rules.local.json --proportions config/proportions.local.json --baseline config/original_proportions.local.json --animation-suite config/animation_suite.local.json --accessories config/accessories.local.json --joint-deformation config/joint_deformation.local.json --out reports/character_source_v5.json
```

第一人称手模使用 **另一组** `viewmodel_*` 配置进行审计，尤其包括手指、手背、手腕和袖子区域；`viewmodel_joint_deformation.local.json` 可专门增加拇指屈伸与握枪相关关节。模型合并为单独的 FBX 时也要保持原资源引用和预期骨骼命名。

## 3. 一键全流程 v5（优化）

`config/auto_workflow.example.json` 复制为 `config/workflow.local.json`，新填 `accessories`、`joint_deformation`，若有独立手模填 `viewmodel_accessories`、`viewmodel_joint_deformation`。

```powershell
# 只生成部署/纠错计划；不修改游戏/模型
python scripts/auto_workflow.py run --config config/workflow.local.json --rig-accessories --fix --deploy --compile --launch --game-test

# 用户确认在自己的 Windows 本地环境实际写入/启动后
python scripts/auto_workflow.py run --config config/workflow.local.json --rig-accessories --fix --deploy --compile --launch --game-test --execute
```

新增自动防护和速度优化：

1. **强制门禁**：玩家模型若缺配件清单、关节半径无效、关节异常、配件权重不足或骨骼映射不一致，不得自动部署；第一人称独立源模型若被提供，也需要单独通过同级审计。
2. **先建立可回滚副本**：`--rig-accessories` 只依据经批准的坐标新增骨链并保存新 `.blend`；原文件不覆盖。`--fix` 是既有安全权重归一化，**不修复形变拉丝/塌陷**；若执行游戏部署，必须重新导出 FBX 并由用户确认 `.vmdl` 引用该 FBX。
3. **去除重复 Blender 审计**：没真正修改 `.blend` 时复用已有审计，不再无意义重复跑同一动作的几何计算；后处理生效时仍强制重检。
4. **跳过相同文件复制**：按 SHA256 判断目标 Addon 文件完全一致时跳过写入；任何需写入文件都走备份/事务回滚。
5. **优先级问题清单**：`reports/run_*/issues_prioritized.json` 将问题按 BLOCKER/REVIEW/INFO 分类、去重，并列出可安全自动处理的问题（仅权重归一化）。
6. **分阶段证据等级**：`source PASS_PRELIMINARY`、`compile artifacts present`、`client screenshots captured`、`engine/player observed` 四种证据独立；死亡/布娃娃、Hitbox、动态配件、关节穿模没有实际游戏证据一律 PENDING。

注意：如果 `--rig-accessories` 给柔性配件新建了骨链但还未手绘权重，后续审计将中止部署，这是正确行为，不是功能故障。自动生成的初始权重也可能需要手工改正。没有带可导出驱动的 AG2/ModelDoc 资源时，本 Skill 不保证次级摆动实际进入游戏。

## 4. 游戏内检查顺序

- 第三人称：角色静止 5 秒 → 往返移动 → 冲刺/急停 → 蹲伏切换 → 跳跃落地 → 90°/180° 转向 → 持枪/射击/换弹 → 受击（观察者）→ 死亡转布娃娃 → 复活。
- 第一人称：手模待机/持枪、武器切换、开火、换弹、检视、持刀、投掷；检查袖口与手腕是否割裂、手链是否穿手指、饰物是否被 FOV 裁剪。
- 对有意义的运动步骤在 `config/game_test.local.json` 中设置 `"captures": 3`，脚本会在按键动作持续期间**分三次截取同一游戏窗口**（整段最多 90 张截图）；建议另由观察者录制第三人称真实视频。这样的离散截图不能保证 FPS 或动画同步，自动化截图只形成证据待验，不能证明装饰物运动自然、关节没有自交。
- 在 `templates/engine_validation.template.json` 填写 `accessory_motion_live`、`joint_deformation_live` 证据。`finalize_report.py` 将二者纳入玩家模型最终必选门禁。

## 5. 项目维护与版本边界

- Source 2 Viewer 能解析骨骼约束、物理关节与 `FeModel` cloth 相关数据，但其文档明确提示布料重建尚有实验限制；它并不意味着 CS2 中任意新加的 `jiggle`/cloth 资源必定能自动编译运行。
- s&box 的 jiggle bone 教程可用于理解**次级骨骼**和骨骼物理的概念，不应复制成“CS2 已提供完全相同的编辑器入口”的承诺。
- CS2 AnimGraph 2 当前资源、服务器插件和模型导入路径可能随更新变化，必须在目标安装版本里实际验证。

资料：
- https://s2v.app/ValveResourceFormat/guides/format-support.html
- https://s2v.app/ValveResourceFormat/api/ValveResourceFormat.ResourceTypes.ModelAnimation.html
- https://s2v.app/ValveResourceFormat/api/ValveResourceFormat.ModelSkeletonBoneFlags.html
- https://github.com/SergeantCS2/CS2-AG2-Model-Porter
- https://sbox.game/learn/shadb/jiggle-101 （**不同游戏**的示范，只参考概念）

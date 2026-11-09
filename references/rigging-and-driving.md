# CS2 AG2 骨骼绑定、权重与驱动操作手册

## 1. 版本和坐标先决条件

CS2 在 2026-04-20 将 AG2 从 beta 推至主版本。不要将旧 CS:GO 的 ValveBiped 或 CS2 旧的 AG1 `.vanmgrph` 作为当前角色直接驱动依据。为目标**世界模型**获取与本机游戏版本对应的合法参考资源（例如可使用 Source2Viewer 查看当前安装的角色）；另行核对视角手臂 `viewmodel`。对齐时把**导入物体、Armature、Rest Bone 和 mesh**分别检查，不可仅移动网格“看起来对齐”。

社区实际测试证实常用 AG2 世界骨架是以 `root_motion` 为根，`pelvis` 为子；`wpnPivot` 与 `wpn` 作为武器驱动链重要节点。其 74 骨数据是该社区样本，并不保证各角色/版本都必须 74 骨（参考样本可少于 74）。默认 profile 只包含一组关键骨骼，并需用户校准。

## 2. 原生 CS2 骨架蒙皮（推荐）

1. 新建备份 `character_before_rig.blend`。保留两个 Collection：`REF_CS2`（参考、不改动）、`OUTPUT`（拟导出的自制资产）。
2. 导入原生骨架，设定统一的场景单位/比例/轴向。分别检查 `root_motion` 是否位于预期位置、`pelvis` 的 Rest Matrix 和层级；若原模型沿 Y 高而 Blender 沿 Z 高，应**变换到一致的局部坐标系**后再对比尺寸。
3. 清理旧网格权重和旧 `Armature` 修改器（若已有合理权重先备份不要覆盖）；对齐网格到目标骨架的 Rest Pose。衣服/配件要确定是否独立 skinned mesh 或 parent attachment。
4. 给网格添加新的 `Armature` 修改器，目标指向输出骨架；首轮使用自动权重，再在 Weight Paint 做局部修正。权重组名称应严格匹配真正用于变形的骨骼名，大小写敏感。
5. 用 Pose Mode 测试：肩膀外展 60°、肘屈曲 90°、手腕扭转、骨盆转向、膝屈曲 90°、脚踝旋转、颈部低头。观察断裂、塌陷、衣袖穿模和权重拉丝。
6. 配置每顶点权重检查；特别检查微小浮点残余影响（非常小的权重可能影响导出限制）、非变形骨骼权重、未被目标骨架接收的顶点组。
7. 若有前臂/大腿 Twist 辅助骨骼，依角色几何建立正确约束或烘焙旋转；**不复制不同体型角色的骨骼局部驱动值**。
8. 执行 Blender 审计并导出 FBX/DMX；在 ModelDoc 中核对输出骨骼、蒙皮和 Rest Pose 是否改变。

## 3. 已有角色骨架重定向

**不要将 `retarget_map.example.json` 直接视为可用映射**。例如 Mixamo 通常只有 3 节 Spine，而某些 CS2 骨架有 `spine_0..3`：需要按躯干比例补足一节或重映射分布，不能一对一照抄。

1. 保留 Source Rig 和 CS2 Target Rig。动作来源导入 Source Rig，不改变源骨骼命名。
2. 统一参考姿势（A/T pose、肩膀角度、手掌朝向、脚底基准）。检查目标父子链、髋部朝向、Root Motion 节点和脚底投影。
3. 建立 `source -> target` 映射；手动解决骨骼数量/长度不同、命名/轴向不同和多根的问题。不要删除 CS2 必需的 `root_motion`。
4. 在目标的 Pose Bone 上创建 `Copy Rotation` 或 `Copy Transforms` 约束，针对 IK 末端可用 IK/Copy Location。可运行 `blender -b scene.blend --python scripts/blender_retarget_setup.py -- --source MixamoRig --target CS2_Rig --mapping config/retarget_map.example.json` 预检映射；确认并修正 Rest Pose 后加 `--apply` 才创建临时约束。检查 `Owner Space`、`Target Space`，避免把世界变换误当作本地空间。
5. 每个动作做逐帧采样，若左右手/脚方向相反，修正映射与 Rest Pose，不能用仅仅负向缩放掩盖问题。
6. 在 Blender 对目标骨架执行 Bake Action / Visual Keying（每帧、清除临时约束后仍能复现动作）。依实际 Blender 版本选择关键帧通道。
7. 将最终网格绑定到目标骨架，去掉对 Source Rig 的依赖；验证关节变形、动作极值 AABB 和权重异常。
8. Blender Action 适合作为离线制作、模型展示或对应能被导入的自定义动画输入；**游戏内玩家行为驱动必须依赖 CS2 当前 AG2 图/状态链路，不会自动执行 Blender 约束**。

## 4. 驱动链路与验收

| 链路 | Blender 侧制作 | CS2 内需要的验证 |
| --- | --- | --- |
| root_motion / pelvis | 根部位置/转向和骨盆继承 | idle/walk/run/转身/楼梯斜面 |
| 脊柱颈头 | FK/旋转约束、头部朝向 | 上下瞄准、蹲伏、投掷 |
| 左右腿 | IK/FK、脚底接触 | 跑步/急停/跳跃/蹲伏/落地 |
| 左右手臂 | FK/IK，握枪姿势 | 主武器/手枪/刀的持握与换弹 |
| `wpnPivot` / `wpn` | 按当前参考姿势校准武器挂点 | 射击、切枪、上下左右 Aim |
| twist 辅助关节 | Twist 分配及局部约束 | 前臂扭转、手腕/肘外观 |
| 第一人称手臂 | 独立 arms/viewmodel 蒙皮 | 独立检查持枪视角；不等同世界模型 |

### 重定位失败的高风险细节

- `root_motion` 为父、`pelvis` 子时，若父骨骼具有非零局部旋转/平移，重父级必须进行矩阵空间换算，不能只把 `parent` 名字改了。这样可能在 ModelDoc 编译通过而角色横倒。
- `_L/_R` 大小写对世界骨架和**DMX jointList** 必须同时匹配；只重命名骨骼而不重映射蒙皮会脱骨。
- `wpnPivot` / `wpn` 不只是“有两个骨名”。武器相对骨骼的初始变换和 AG2 动画变换必须配套，需拿当前真实参考样本验证。
- `AnimGraph2List`/`NmSkeletonList`/`DefaultAnimGraph2` 是需要检查的资源概念；如果没有可用的同版本示范模型，不能自动凭空生成准确的完整 `.vmdl` KV3 节点。
- 编译好的显示模型和玩家 **Hitbox**、Physics 约束和 server-side 碰撞是独立项目；视觉正确不意味着游戏命中正确。

## 5. 自动修复边界

允许在**明确保存备份且获得许可**后做权重 normalize、清零和手动确定的骨骼名修复。脚本默认只读、不给模型自动加骨骼、不会自动改别人的游戏包。复杂的 Twist、肩膀/手腕错位或缺失骨骼需以源体型/参考动作反复验收。

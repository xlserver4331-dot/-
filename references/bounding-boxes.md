# 包围盒、碰撞与 Hitbox 完整检查标准

## 1. 分清至少六个边界

1. **网格 Rest AABB**：所有目标渲染网格在 Armature Rest Pose 下、Armature 局部空间合并包围盒；来自 Blender `bpy` 顶点变换。
2. **变形动作 AABB**：逐动作逐帧，在网格变形后采样求最小/最大顶点位置；必须记录 Action、帧范围、步长（离散采样可能遗漏动作间极值）。
3. **渲染裁剪/可见性 Bounds**：引擎对渲染组件的裁剪范围，可能与源模型 AABB 不同；在 ModelDoc 和游戏内验证，不可仅靠 Blender 推断。
4. **物理 Physics Collision**：静态/动态物理碰撞形状（刚体、mesh/convex 等），必须在 ModelDoc 配置、编译并本地验证。
5. **玩家移动碰撞体**：由游戏玩家实体控制器或服务端逻辑决定，不一定读取模型渲染 AABB。
6. **Hitbox / 命中判定盒**：和骨骼、动画姿态、服务端命中链有关，不能简单以 AABB 代替。

## 2. 静态 AABB 计算

对变形前 Rest Pose 的所有用于导出的**渲染网格**顶点，在相同空间计算：

```text
P_armature = inverse(armature.matrix_world) * evaluated_mesh.matrix_world * P_mesh
min_axis = min(P_armature.axis)
max_axis = max(P_armature.axis)
size = max - min
center = (min + max) / 2
```

注意：`Object.bound_box` 八个角只能表示局部原始对象 bbox，不足以直接获取随骨架变形的每帧精确顶点极值；应使用依赖图 Evaluated Mesh。不要把 Collision-only meshes 误合并进去；项目可标记 `cs2_collision_only = true`。

## 3. 动态 AABB

对 `idle`、`walk`、`run`、`turn`、`jump_start`、`air`、`land`、`crouch`、`aim_high/low`、`reload`、`knife` 及用户特有披风/发饰动画逐个检查；同一 Action 按 `sample_step_frames` 采样（建议关键动作每帧抽样或追加峰值帧）。记录：

- `action`, `frame_range`, `sampled_frame_count`, `min/max/center/size`。
- 变形的顶点最大极值；左右移动、抬手、换弹、跳跃期间额外延伸量。
- 单独识别 Root Motion 位移。如果该 Action 是往前走 20 米，则整段 `dynamic_union` 合并了移动轨迹，不能用于角色原地碰撞体大小判断；应另算逐帧相对角色根坐标/原地化动作边界，必要时在引擎里检验。
- 带有 NLA/约束/程序化布料的场景需要针对**最终导出链路**验证，默认脚本采样指定 Action / 当前 Action，不能凭它证明所有 NLA 层或 AG2 过程性姿态已覆盖。

## 4. 参考标准和比较

`config/bbox_rules.example.json` 默认 `reference=null`，这表示**不可判定是否合规**，而非放行。用户必须以同版本、同用途角色确定边界和单位，把数值写入：

```json
{
  "reference": {"min": [-20.0, -20.0, 0.0], "max": [20.0, 20.0, 78.0]},
  "axis_absolute_margin": [1.0, 1.0, 2.0]
}
```

上面数字**只是演示配置格式，绝非官方 CS2 人物尺寸**。当边界已经校准为同坐标系/同单位时，比较 `actual.min >= reference.min - margin` 且 `actual.max <= reference.max + margin`。否则结果 `PENDING`。

## 5. ModelDoc/游戏实测流程

1. ModelDoc 查看模型包围范围与 Mesh 对齐，确保骨骼运动时不会被错误裁剪。
2. 逐 Physics 物理体确认是否与骨架/体型一致；检查衣服、头部、手部多余物理碰撞是否影响游戏行为。
3. Hitbox 按骨骼和伤害区域检查位置、朝向、尺寸以及动作同步；不可以使用整人体一个大 AABB 冒充。
4. 在 Hammer 把 prop 放到地面：检查真实物理接触、穿墙/地面、可见性和碰撞行为。
5. 玩家替换则需要在**本地私人服务器**观察和记录游戏实际站立/蹲伏、跳跃、射击命中；不能仅从视觉表现判断命中区域正确。
6. 保存关键姿态截图/录屏、ModelDoc 编译日志、CS2 版本、参考模型 ID 及最终验收人的结论。

## 6. 常见故障

| 现象 | 可能根因 |
| --- | --- |
| 模型原地正确、跑起来消失 | 动态姿态超出渲染裁剪边界/动画骨骼坐标或资源引用问题 |
| 阴影不合理 | 光照/渲染 bounds/材质/阴影设置（非 Hitbox） |
| 脚落在地下 | 角色原点、骨盆静止位置、游戏胶盒/坐标系不符 |
| 视觉命中但服务器不计伤害 | Hitbox/服务器玩家命中链错误 |
| 武器大幅拉长 BBox | 挂点/武器附件被错误混入角色 skinned mesh 或姿势错误 |
| 胸口/脸部包围盒异常 | 姿态骨骼旋转、错误权重、极远离群顶点 |

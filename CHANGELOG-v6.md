# v6 更新说明

## 实际增加

- 原模型比例优先。`rig_stretch` 针对实际动画逐帧检测上臂、前臂、大腿、小腿的骨长变化、复制缩放和 Stretch 约束，并发现双重 Armature/变形修改器。
- `mesh_integrity`：逐网格统计静态 open boundary / non-manifold / loose edges / zero-area faces，支持经人工标记的动态接缝两顶点在 Action 中计算 `rest_gap`、`pose_gap`、`gap_increase`。
- `--repair-seams`：仅允许人工确认、与原 `.blend` SHA256 完全匹配、Rest 位置/权重/UV/材质一致的指定顶点对，非破坏性另存新文件。不会全自动乱补缺面。
- 新诊断结果成为 `player_runtime` 部署硬门禁；第一人称独立模型也必须单独配置相同检查。
- `finalize_report.py` 与 `engine_validation.template.json` 新增 `mesh_cracks_live`、`rig_stretch_live`，截图只做待验证证据。
- 新 SOP `references/v6-stretch-crack-recovery.md`：完整保比例绑定、分辨静态孔/动态接缝、权重重画、关节变形修复、游戏引擎复验。
- `SKILL.md` 重排为九阶段单路径流程，保留 v4/v5 动画、手模、死亡/布娃娃、装饰物骨、ModelDoc 部署能力。

## 自动修复边界

无源模型、骨骼 Rest 基准、动作或用户确认的接缝索引时不会“保证成功修复”。Blender GUI、ModelDoc/CS2 引擎的真实测试仍需要在用户提供的环境中运行。自动 seam 焊接可能因合法 UV、材质或变形权重差异而拒绝，这是预期的安全行为；应手工修复/重画权重后再审计。

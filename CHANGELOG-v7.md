# v7 · 双视角手模全流程升级

- 新增 `--extract-viewmodel`：从原完整角色按手工标定的 `FP_KEEP` 掩码提取双臂、手指、衣袖和配件到**新的** `.blend`，保留 UV、材质和原有蒙皮几何，不碰原模型；删除只用于选区的非变形 Mask 顶点组。
- 新增 `blender_viewmodel_final_audit.py`：手模来源 SHA、独立 viewmodel 骨架、目标骨骼权重、肩口与袖口开边、非均匀缩放、Stretch 等检查。
- 新增 `dual_viewmodel_gate.py`：只有 World 与 FP 两份来源、ModelDoc 配置及哈希明确通过，才能部署/编译/启动或运行本地游戏验证。支持 `shared_bodygroup` 和 `separate_vmdl`。
- 新增 `pin_viewmodel_export.py`：明确批准后备份并固化 `.blend` + `.fbx` SHA256，防止发布旧手模。
- 重排 `SKILL.md` 为 P0–P9 阶段，新增按用途路由；增加分步 Blender UI 的 `references/v7-dual-viewmodel-extraction.md` 和配置模板。
- 原有 v4-v6 的原比例保护、网格破口、装饰物骨骼、第一/第三人称动画、死亡/布娃娃、包围盒以及私人服务器游戏自检保留。
- 裁剪、重绑、ModelDoc、CS2 运行时是四种独立状态：**裁剪成功不代表手模已可在游戏里驱动**。
- 开发环境无 `bpy`/真实 CS2 时，离线测试只校验流程/逻辑；真实模型与引擎加载保持 `PENDING`。

# CS2 模型转模 / 双视角 / 本地部署 Skill v8

这是一个适用于支持 `SKILL.md` 的 Agent 的可安装技能包。包含模型检查、保守修复、模型尺寸选择、装饰物骨骼、运动关节形变与破口、第一人称从完整人物裁剪、独立 viewmodel 绑定指引、Source 2 编译和私人本地测试的完整工作流。

## v8 重点更新

**先问后检**：在任何主体高度检测前，用户先确认人形或非人形及身高方案。可选“匹配本机默认探员**主体**高度”“自定义主体目标高度”“全身统一倍数缩放”“保持原始主体高度”；非人形不强制与默认探员等高，但主骨架垂直跨度必须与主体网格相符。**装饰物不计高度**，但仍纳入完整渲染 AABB、动态碰撞/权重及动画检查。

此前出现的手脚拉长、肘膝裂缝、衣袖/手套错位、FPS 手模仍然显示默认手、死亡 ragdoll 错乱，都有独立门禁。**Skill 不会自行修改比例或自动替你生成已验证的第一人称动画。**

## 从哪里开始

先读：`SKILL.md`（Agent 入口）及 `references/v8-height-and-complete-workflow.md`（可直接照做的完整流程）。

```powershell
# 复制本地配置示例，绝不要直接覆盖 .example.json
Copy-Item config/height_profile.humanoid.example.json config/height_profile.humanoid.local.json
Copy-Item config/workflow.player_dual.example.json config/workflow.local.json

# 修改这两份 .local.json 的真实路径、人体/装饰物对象、CS2 参考值和本机工具路径
# 在模型身高审计之前必须询问尺寸策略并保存，命令会显示可选项
python scripts/height_choice.py --profile config/height_profile.humanoid.local.json --save

# 检查与只读扫描
python scripts/validate_skill.py
python scripts/auto_workflow.py doctor --config config/workflow.local.json
python scripts/auto_workflow.py run --config config/workflow.local.json
```

**注意：** 只有完整配置的 Blender、真实角色源 `.blend`、本机当前 CS2 参考资源与私人 Addon 才能执行真正的编译和游戏自检。执行前先 dry-run；`--execute` 写文件/启动进程时要明确授权。第一人称手臂裁剪后还需独立 viewmodel Rig、蒙皮/动画制作、ModelDoc 引用检查，不能直接拿预览裁剪文件部署。

## 重要文件

- `scripts/height_choice.py`：互动询问模式并写入带备份的 `*.local.json`，无交互必须明确 `--confirm`。
- `scripts/height_policy_core.py`：纯 Python 检查所选高度目标与非人形骨架跨度，不修改模型。
- `scripts/blender_body_height_audit.py`：分主体/装饰、计算主体与全部视觉 Bounds，支持原模型/默认探员参考捕获。
- `scripts/auto_workflow.py`：预检、审计、保守修复、导出、部署、编译、启动与本机取证统一调度，并阻止新高度方案复用旧审计报告。
- `references/v8-height-and-complete-workflow.md`：**从零开始的 S00–S13 完整工作步骤与失败回退**。
- `references/v4-*` / `v5-*` / `v6-*` / `v7-*`：原始四肢比例、死亡、装饰骨、动态接缝及第一人称制作详细技术手册。

**真实验证范围：** 可在普通 Python 环境完成的测试只覆盖逻辑与模拟工作流；真实 Blender 与 CS2 仍需用户实际文件和本地引擎验证。

## 使用原则与高度选择

运行主体高度检查前，先确认模型类型和用户选择：人形可以选择匹配本机当前默认探员的主体高度、指定目标高度、整体等比例缩放或保持原高；非人形选择后三种，并另外检查主体网格与主骨架的垂直跨度。目标高度、单位和参考来源必须真实测量或由用户提供，不预设官方身高数值。

头发、帽子、翅膀、背包等装饰物不计入主体高度，但仍须计入完整渲染边界和相关动态检查；身体结构与装饰的分类由使用者确认。调整尺寸只采用整个角色的 XYZ 统一比例，不单独拉长四肢。高度工具记录选择和提供测量建议，不会自动对模型施加缩放。

原始模型应归档并保留哈希。所有修复在副本上进行，重新审计后再导出；不要覆盖 CS2 本体或在官方匹配中使用替换模型。

## 环境和目录

| 项目 | 说明 |
| --- | --- |
| Python 3.10+ | 运行离线工具、配置与测试 |
| Blender | 需要支持 Python、bmesh、FBX 导出，按本机路径配置 |
| CS2 Workshop Tools / ModelDoc | 编译和核对与本机版本匹配的资源 |
| 私人 Addon 和测试环境 | 仅在实际部署和游戏验收时需要 |
| `requirements-game.txt` | 游戏界面自动化和截图的可选依赖 |

| 目录或文件 | 用途 |
| --- | --- |
| `SKILL.md` | Agent 工作入口、阶段门禁和操作范围 |
| `config/` | 高度、模型、双视角与工作流示例配置；复制后填写本机数据 |
| `scripts/` | 选择高度、Blender 审计、工作流、导出检查和取证脚本 |
| `references/` | v4–v8 详细技术手册与 ModelDoc、游戏自测说明 |
| `tests/` | 离线逻辑和模拟工作流测试 |
| `templates/` | 引擎验证报告模板 |
| `MANIFEST.sha256.json` | 文件 SHA-256 清单 |
| `run_skill.ps1` | PowerShell 工作流入口 |

## 从完整模型到游戏验收

1. 确认高度方案、备份源模型并测量原始骨长；按需要测量本机默认探员主体参考。
2. 人工分类主体与装饰物，测量主体高度，检查世界模型骨架、权重、关节和裂口；需要修复时先预演，在副本上操作后复检。
3. 在完整人物工作副本中人工标记 `FP_KEEP` 手臂区域，先预演、再单独提取。预览结果尚未绑定第一人称骨架。
4. 在 Blender 中人工完成独立 Viewmodel 骨架、蒙皮和动作；分别导出 World 与 Firstperson FBX，核对哈希、ModelDoc 和 AG2 资源引用。
5. 在授权的私人 Addon 中先预演部署、编译和启动；确认目标后才使用 `--execute`。分别记录 World 和第一人称的加载与动作结果；没有运行时证据时保持 `PENDING`。

完整配置字段、命令与回退步骤见 [v8 完整工作流](references/v8-height-and-complete-workflow.md)，第一人称制作见 [v7 手模指南](references/v7-dual-viewmodel-extraction.md)。

## 离线测试和已知限制

```powershell
python scripts/validate_skill.py
python -m unittest discover -s tests -v
```

本次 Windows 环境中，结构校验通过。将临时目录设为可写并启用 Python UTF-8 模式后，115 项离线测试中 108 项通过、7 项模拟集成测试失败；失败涉及 Unix 风格模拟可执行文件在 Windows 下无法直接启动。部分测试还可能受 Windows 默认文本编码影响。这些兼容问题尚未修复；离线测试不代表真实 Blender、ModelDoc 或 CS2 运行通过。

公开上传前，请检查文件清单，不要上传个人路径、本地配置、原始模型、游戏资源或测试报告。`.gitignore` 只影响未被 Git 跟踪的文件，不替代人工检查；确保使用的模型和资源具有适当授权。

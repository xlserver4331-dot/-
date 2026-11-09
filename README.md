# CS2 人物模型双视角转模与部署工具 · v7

本项目是一套面向 CS2 Source 2 / AG2 自定义人物的工作流程、Blender 审计脚本、配置模板和测试。它以**原人物比例**为基准，分别处理第三人称完整人物和第一人称手臂，协助检查蒙皮、关节、裂口、动画、资源引用与私人环境部署。

> **当前状态：v7 工作流程与离线工具。** 提取脚本生成的是待绑定的手臂几何预览，不是可直接部署的第一人称手模。编译成功也不等于游戏已加载。真实 Blender、ModelDoc 和游戏结果必须由对应的实际测试确认。

## 能做什么

- 从原始人物副本中，根据人工标记的区域提取左右手臂、手掌、手指和衣袖，保留支持的数据作为第一人称几何基础。
- 分别检查世界模型与第一人称模型的骨架、权重、原始比例、关节变形、网格裂口和动画采样。
- 对符合条件的问题进行保守处理，例如有效权重归一化，以及经人工指定并校验的局部接缝修复；结果写入新副本。
- 协助检查双资源导出、ModelDoc 引用、文件哈希、部署清单与编译产物，并记录报告。
- 在具备实际环境和授权时，辅助私人服务器的双视角验收；世界模型和第一人称手模分别记录结果。

**不自动完成**第一人称骨架重定向、可靠的手部权重调整、武器握持动画或游戏运行时的手模接管。不同 CS2 版本和服务器插件的资源结构、加载能力可能不同，必须依据本机可运行的参考资源验证。

## 使用原则

1. 保留未经修改的原始模型与备份，以原模型 Rest 骨长为比例基准；不要为了匹配默认探员而拉长四肢。
2. 世界模型使用完整人物；第一人称几何从同一原人物的工作副本裁剪，再绑定**独立的 Viewmodel 骨架**并单独导出。
3. 默认运行是只读检查或预演；需要写入新模型、部署、编译或启动的步骤使用 `--execute`，并先检查配置、路径与备份。
4. 只在获授权的副本和私人 Addon 环境中操作；不要覆盖游戏本体、规避反作弊或在官方匹配中部署替换模型。
5. 使用真实引擎和观察证据判断运行时结果；没有足够证据时应记录待验证，而不是标记通过。

## 环境要求

| 组件 | 用途 |
| --- | --- |
| Python 3.10 或更高版本 | 运行工作流、离线检查与测试 |
| 支持 Python、bmesh 和 FBX 导出的 Blender | 处理与审计模型；使用本机实际可执行文件路径 |
| CS2 Workshop Tools 和本机当前版本的参考资源 | ModelDoc、AG2 资源核对与编译 |
| 已配置的私人 Addon / 测试环境 | 需要实际部署和游戏验收时使用 |

核心脚本主要依赖 Python 标准库与 Blender 自带 Python。`requirements-game.txt` 列出游戏界面自动化及截图所需的可选依赖；只有需要该功能时才安装，并参照 `references/game-self-test.md` 配置。

## 目录说明

| 路径 | 内容 |
| --- | --- |
| `SKILL.md` | 技能入口、任务路由、阶段顺序和门禁 |
| `config/` | 示例配置；复制为 `.local.json` 后填写本机路径和模型数据 |
| `scripts/` | Blender 审计、提取、工作流、部署检查与报告脚本 |
| `references/` | 绑定、比例、裂口、双视角、部署和游戏验收指南 |
| `tests/` | 离线单元测试与模拟工作流测试，不代表实机验收 |
| `templates/` | 引擎验证报告模板 |
| `run_skill.ps1` | PowerShell 工作流入口，参数说明见脚本与自动化指南 |
| `MANIFEST.sha256.json` | 包内文件的大小和 SHA-256 清单 |
| `.gitignore` | 排除本地配置、报告、缓存和常见模型文件 |

重点阅读 [`references/v7-dual-viewmodel-extraction.md`](references/v7-dual-viewmodel-extraction.md)、[`references/automation-and-launch.md`](references/automation-and-launch.md) 和 [`references/game-self-test.md`](references/game-self-test.md)。骨骼拉伸与裂口问题另见 [`references/v6-stretch-crack-recovery.md`](references/v6-stretch-crack-recovery.md)。

## 配置与工作流程

以下命令在本项目根目录的 PowerShell 中运行。示例路径仅作说明，必须替换为实际文件；不要直接把示例阈值当作模型验收标准。

### 1. 归档与准备

备份原始全身模型，记录 SHA-256、原始骨长和问题动作帧。世界模型修复、第一人称提取均在独立工作副本上进行。先完成世界模型的比例、蒙皮、裂口和动作检查。

复制 `config/workflow.player_dual.example.json` 为 `config/workflow.local.json`；同样复制 `viewmodel_extraction.example.json`、`dual_viewmodel.example.json`、`firstperson_bone_map.example.json` 和所需的其他配置模板为 `.local.json`。填写真实 Blender、CS2、模型、Addon 和审计配置路径。配置字段和阶段要求详见 `SKILL.md`。

在从原全身模型另存的提取工作副本中，人工标记 `FP_KEEP_L`、`FP_KEEP_R` 等顶点组；保留所需手指、手套和衣袖，人工审核位于相机视野外的肩部截断。将 `firstperson_source_blend_file` 指向该工作副本，世界模型仍由 `blend_file` 单独指定。

### 2. 预检和提取

```powershell
python scripts/validate_skill.py
python scripts/auto_workflow.py doctor --config config/workflow.local.json
python scripts/auto_workflow.py run --config config/workflow.local.json
python scripts/auto_workflow.py run --config config/workflow.local.json --extract-viewmodel
```

检查提取报告中的选中面和边界；确认掩码与截断后，再单独执行：

```powershell
python scripts/auto_workflow.py run --config config/workflow.local.json --extract-viewmodel --execute
```

提取结果是 `firstperson_cut_preview.blend` 和报告。它仍需人工换绑、校准 Rest 姿势、调整权重及动作；不应直接作为可部署手模。含 Shape Keys 的网格可能被拒绝自动裁剪，具体以提取报告为准。

### 3. 独立绑定、导出和检查

从当前可运行的 CS2 参考资源确认 Viewmodel 骨架、层级和 AG2 关系。在新副本中完成独立骨架绑定、权重与动作，检查肘、腕、手指、袖口和持枪姿势，保持原人物肢体比例。分别导出世界模型与第一人称 FBX，检查 ModelDoc 对两套资源的实际引用。

对最终第一人称 `.blend` 和 `.fbx` 固定 SHA-256，并在修改后重新导出、更新哈希和复检：

```powershell
python scripts/pin_viewmodel_export.py --dual config/dual_viewmodel.local.json --workflow config/workflow.local.json
python scripts/pin_viewmodel_export.py --dual config/dual_viewmodel.local.json --workflow config/workflow.local.json --execute
python scripts/auto_workflow.py run --config config/workflow.local.json
```

### 4. 私人环境部署和验收

确认部署清单、备份、资源引用、编译目标和环境授权后，先预演：

```powershell
python scripts/auto_workflow.py run --config config/workflow.local.json --deploy --compile --launch --game-test
```

检查计划和阻断原因后，才按实际需要追加 `--execute`。游戏内分别检查世界模型与第一人称的显示、移动、持枪、开火、换弹、检视、死亡与复活；记录日志和截图。若插件只支持世界模型替换，第一人称应保持 `PENDING_RUNTIME_VIEWMODEL`。

## 测试与已知限制

```powershell
python scripts/validate_skill.py
python -m unittest discover -s tests -v
```

结构校验已通过。在一次 Windows 环境的离线测试中，使用项目内可写临时目录并启用 Python UTF-8 模式后，85 项中 78 项通过，7 项模拟集成测试失败：测试使用的 Unix 风格模拟可执行文件无法由 Windows 直接运行。部分测试还依赖系统默认文本编码，中文 Windows 下可能产生解码错误。上述问题尚未修复；离线结果不能证明 Blender、ModelDoc 或 CS2 实机通过。

若系统临时目录不可写，可在运行测试前将 `TEMP` 和 `TMP` 指向有写权限的临时目录；这只能处理临时目录权限，不会修复上述测试兼容问题。

## 数据与发布

示例配置中的路径、骨骼名称、阈值和资源引用都必须按实际工程核对。不要将个人机器路径、本地配置、模型素材、游戏资源或报告无意上传至公开仓库；`.gitignore` 只影响尚未被 Git 跟踪的文件，上传前仍应检查文件列表及内容。使用模型和游戏资源时，确认其来源及适用授权。

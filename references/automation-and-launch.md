# 自动检查、自动纠错、Addon 部署及启动 — 操作手册

版本：3（包含游戏内自动 QA 集成）。核心命令：`scripts/auto_workflow.py`（Python 标准库）＋ Blender 内部 `blender_audit.py` / `blender_auto_fix.py`。

## 0. 支持边界

支持：自制或获授权模型；Windows Blender 与 CS2 Workshop Tools 环境；Source 2 当前版本可用的用户自有 `.vmdl` 等源文件；本机 Addon；本机/私人专用服务器。

**不支持一键自动生成正确的 AG2 动画图、标准玩家命中箱或自动替换官方匹配玩家模型。** 不自动安装 Metamod、CounterStrikeSharp、MultiAddonManager 等服务端扩展，不修改 `gameinfo.gi`，不关闭反作弊。普通 CS2 游戏客户端不会直接加载 Workshop Tools 的松散模型文件，需要编译与目标环境能实际挂载资源（如打包的 Workshop/VPK、兼容的服务器插件），后续仍需引擎人工验证。

## 1. 准备安装与模型

1. 先在 Steam 安装/启用 `Counter-Strike 2 Workshop Tools`。
2. 在 Workshop Tools 的 Addon Launcher 里 **Create New Addon**，例如 `my_model_addon`。请不要让本 Skill 自动创建假 Addon 或覆盖原版 CS2 资源。
3. 打开 `.blend`，检查 armature 和变形网格；从当前兼容版本准备真实参考骨架与边界，更新 `config/ag2_profile.example.json` 与 `config/bbox_rules.example.json`（或各复制到项目专用配置）。
4. 用 ModelDoc GUI 生成正确引用模型/材质/骨架的 `.vmdl`，并把 FBX/DMX、材质源文件准备好。仅有 FBX 不足以通过 ModelDoc 编译验证。
5. 复制 `config/auto_workflow.example.json` 为私人项目的 `config/workflow.local.json`；逐一修改 `blender_executable`、`blend_file`、`cs2_root`、`addon_name`、`ag2_profile`、`bbox_rules`、`deploy_files`、`compile_sources`、`required_compiled_files`。
6. 若计划把**自动修复的新 FBX**直接编译到游戏：在 ModelDoc 中确认 `.vmdl` 实际引用 `models/custom/character.fbx`（以你的实际路径为准）。随后设 `auto_export_fbx.enabled=true` 和 `modeldoc_fbx_reference_verified=true`，确保 `auto_export_fbx.relative_path` 与 `deploy_files` 的某个 `content` FBX 目标完全一致。程序会把刚导出的修复 FBX 覆盖到这一项的部署源，避免拿旧 FBX 编译。不确认引用就会停止一键修复+部署。
7. `deploy_files` 清单每项必须是要复制到自己 Addon 的**明确源路径**、`area`（`content` 或 `game`）和 `relative_path`（相对 Addon 的目标路径）。`content` 放源码，`game` 仅允许编译产物；不覆盖库存游戏。`compile_sources` 填源文件的 **Addon 内相对路径**，例 `models/custom/character.vmdl`。

**提示：** `auto_workflow.example.json` 中的 Windows 路径只是占位，`modeldoc_fbx_reference_verified` 默认 `false`，不能不修改直接执行；`bbox_rules.example.json` 参考盒为 `null` 时比较 `PENDING`，模型不会被错误宣称通过。

## 2. 一键工作流命令

在技能目录执行，Python 3.10+：

```powershell
# 只诊断环境，不修改游戏或模型
python scripts/auto_workflow.py doctor --config config/workflow.local.json

# 先全程模拟：读取 Blender、生成诊断/纠错预案、部署计划、编译命令和启动计划
python scripts/auto_workflow.py run --config config/workflow.local.json --fix --deploy --compile --launch

# 对当前 .blend 自动审计 -> 安全自动纠错 -> 复检 -> 本地部署 -> 编译 -> 启动 Workshop Tools
python scripts/auto_workflow.py run --config config/workflow.local.json --fix --deploy --compile --launch --execute
```

`--execute` 才允许生成修复后的新 `.blend`、写入已创建的 Addon、调用编译器或启动进程。即使没有 `--execute`，检查产生的 JSON/日志仍然写入 `reports/run_*/`，便于审核。

### 拆分运行

```powershell
# 仅扫描 + 制定自动纠错建议（不修改 .blend）
python scripts/auto_workflow.py run --config config/workflow.local.json --fix

# 实际自动纠错（只生成新的修复副本，不修改原文件）
python scripts/auto_workflow.py run --config config/workflow.local.json --fix --execute

# 在已有审计证据下部署，以下输出仅表明复制成功
python scripts/auto_workflow.py deploy --config config/workflow.local.json --audit reports/run_XXXX/blender_audit_after.json --execute

# 编译模型资源，要求上一步的当前模型检查能通过部署门槛
python scripts/auto_workflow.py compile --config config/workflow.local.json --audit reports/run_XXXX/blender_audit_after.json --execute

# 启动工具或专用服，要求具备当前审计证据
python scripts/auto_workflow.py launch --config config/workflow.local.json --audit reports/run_XXXX/blender_audit_after.json --execute
```

示例中 `reports/run_XXXX` 换成真实报告目录，不要复制字面占位路径。

## 3. 自动检查的范围与阻断规则

- Blender 模型：Armature、必需骨骼层级、对象姿势校准声明、Armature Modifier、变形顶点权重、未知/非变形顶点组、UV/材质、网格拓扑问题、对象缩放/镜像。
- 包围盒：静态 Rest AABB、每个选定 Action 的采样 AABB、动画合并 AABB、参考边界比较。
- 部署门禁：出现 Blender 致命错误或包围盒 `FAIL` 即禁止；缺可信包围盒参考时 `PENDING`，默认禁止；仅 `prop_preview` 可通过 `--allow-pending-preview` **显式允许本地道具实验预览**，不会使 PENDING 变 PASS。
- 玩家用途 `player_runtime`：还必须验证 Rest Pose 且具有动态边界比较；未经确认一律拒绝全自动部署/启动。即便文件复制/编译/服务器进程启动成功，AG2/Hitbox/武器/走跑蹲动作仍然是 `PENDING`。
- `modeldoc_reference_audit.py` 只能找文本可疑标记，不是游戏编译验证。

**若被门禁阻断：** 查看 `workflow_result.json` 的 `error`，随后修正模型/参考数据。不得用 `--allow-pending-preview` 规避玩家模型的骨骼或边界错误。

## 4. 自动纠错清单

| 错误类型 | 处理方式 | 原因 |
| --- | --- | --- |
| 有有效变形骨骼权重但总和不为 1 | **自动按比例归一化**；另存新 `.blend` | 可以保留已有骨骼分配比例 |
| 原模型 `.blend` | **永不覆盖** | 可回退、可对比 |
| 零权重顶点或组名缺失 | **人工处理** | 无法可靠推断骨骼 |
| 错误父级 / Rest / 单位 | **人工处理** | 自动重父级易破坏动画 |
| 权重越过 4 骨骼建议 | **警告**，不自动删影响 | 容易损坏关节形变 |
| 包围盒越界 | **阻断**，不能自动缩放角色 | 可能源自合法披风/动作/武器 |
| 残留 AG1 引用/AG2 错误 | **人工 ModelDoc 验证** | 源文件和目标 graph 可能跨版本 |
| Hitbox / Physics / Server plugin | **引擎验证** | Blender 静态数据无法代表运行期 |

修复报告是 `auto_fix_report.json`，包含顶点 ID、修复候选、因缺权重被跳过的顶点、输出副本和修复版 FBX（启用 `auto_export_fbx` 时）；审计前后报告分别是 `blender_audit_before.json` / `blender_audit_after.json`。若开启 `--fix` 而未 `--execute`，只会预演，不修改输入模型。

## 5. 部署过程及回滚

1. 仅接受 `deploy_files` 列出的文件；校验 Addon 名、合法后缀、目标路径，拒绝 `..`、绝对路径、符号链接逃逸和游戏本体路径。
2. 要求 Workshop Tools 已创建同名 Addon（`content/csgo_addons/名字/` 与 `game/csgo_addons/名字/` 均存在）。
3. 文件覆盖前，在每次运行目录 `backups/` 保存旧文件。复制失败时自动回滚本次已经更改的目标；部署成功的备份也保留供手动恢复。
4. 若配置了 `compile_sources`，程序逐个调用 `game/bin/win64/resourcecompiler.exe -i <实际 addon 源路径>`；检查 `required_compiled_files` 每项是否存在。**不负责自动生成 `.vmdl` 的节点、地图照明或 Hammer 地图编译。**
5. `deploy_result.json` / `compile_result.json` 保留哈希、命令、产物存在性和日志；若手动回滚，用 `backups/` 中的对应文件恢复（部署首次创建的新文件可删除，但先确认未被其他用户修改）。

注意：编译器输出可能部分更新。如果编译中断，复制事务的回滚不等于编译资源的全面回滚；请保存源模型/Addon 的版本控制或快照。

## 6. 启动方式

`config/auto_workflow.example.json` 中的 `launch_mode`：

- `tools`：启动 `game/bin/win64/csgocfg.exe`，进入官方 Addon Launcher；**手动选中自己的 addon** 并按 `Launch Tools`，再用 ModelDoc/Hammer 测试。程序能证明的仅是启动进程，不是工具里的模型成功加载。
- `dedicated_server`：启动已配置的 `server_executable`（默认本机 CS2 的 `game/bin/win64/cs2.exe`）加 `-dedicated -console -port <端口> +map <地图>`。会先检查必需编译产物存在；不会替你安装服务端插件/生成 Workshop VPK/发布资源/修改服务器 ACL。

专用服正常启动后，客户端在自己的 CS2 控制台按实际监听端口输入：

```text
connect 127.0.0.1:27015
```

**只有本机专用服时用 `127.0.0.1`**；如果服务器不在本机，连接方式应由服务器管理员明确提供。假如插件需要 Workshop 挂载，管理员还需确认客户端已取得资源，之后按插件说明切换角色。普通好友大厅不是等价的插件专用服务器。

## 7. 验收状态解释

`DRY_RUN_COMPLETE`：已完成模拟/报告，未部署。`STEPS_EXECUTED_RUNTIME_PENDING`：所请求的本机操作已调用，**运行时验证未完成**。`PROCESS_STARTED_UNVERIFIED`：启动器/服务器进程创建，尚未确认游戏加载成功。`BLOCKED`：检查失败，中止部署和启动。

真正结束前，还需填写 `templates/engine_validation.template.json` 并执行 `scripts/finalize_report.py`。任何 `PENDING` 都不能作为运行时成功。


## 8. v3：游戏内自动测试（仅本地私人服务器）

升级后 `auto_workflow.py run` 新增 `--game-test` 选项。先配置 `game_test_config`，并按 `references/game-self-test.md` 安装可选 GUI 依赖、配置模型插件、客户端挂载与就绪模板。`--game-test` 与 `--launch` 同用时，只允许 `launch_mode=dedicated_server`。没有 `--execute` 只生成计划。成功采集截图仍为 `CAPTURED_PENDING_VISUAL_REVIEW`，不能用来替代必须的 AG2、Hitbox、Physics、碰撞实测。

```powershell
python scripts/auto_workflow.py run --config config/workflow.local.json --fix --deploy --compile --launch --game-test
python scripts/auto_workflow.py run --config config/workflow.local.json --fix --deploy --compile --launch --game-test --execute
```

如需复用已运行的私人服，请**不要**加 `--launch`，独立运行 `scripts/game_qa.py` 或在 `game_test_config` 中设置 `client_launch=false`（已在游戏里时）。报告保留在本轮 `reports/run_*/game_qa/`。失败/失焦将标 `BLOCKED`；不进行无限自动重试、不改游戏本体或关闭反作弊。

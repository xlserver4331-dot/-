> **v4 更新：** 游戏测试增加第一人称视角步进 `view=firstperson`、检视/刀攻击/出枪动作，以及用户明确授权的 `death` 触发。死亡必须为最后一个步骤，必须配置 `death_test.enabled=true`、`allow_self_kill=true`、`sv_cheats_confirmed=true`。正确本地服务端命令 `sv_cheats 1`。自身 `kill` 截图无法观察自己的第三人称 ragdoll；需第二观察者录像、演示或可信服务端物理证据。第一人称手模源资产请独立审计。详见 `references/v4-proportions-animation-death.md`。

# CS2 v3 · 自动进入本地测试服务器 / 模型动作采样 / 屏幕与日志验收

## 1. 功能与边界

**真实可执行功能**（Windows 交互式桌面，已授权、已安装依赖且用户已建好私人服务器）：

1. 由 Python 以 `cs2.exe -console -condebug +connect 127.0.0.1:27015` 启动游戏客户端，尝试连接本地私人服；也可连接已经打开的客户端（`client_launch=false`，但需用户已经进入测试服务器）。Steam 需要预先正常登录并运行。
2. **必须证实窗口就绪**：使用用户提供的独特游戏中模板图匹配，或只读取本轮新增的本地日志标记；不靠固定等待时间假装进入地图。
3. 确认前台窗口标题属于 CS2，才用开发者控制台发送 `say !model MODELNAME all`。`MODELNAME` 必须事先在已安装的 PlayerModelChanger 配置中登记；命令**发出≠插件已执行成功**。
4. 可选通过兼容的服务器插件 `say !tp` 切第三人称，或使用已授权练习服的 `thirdperson` 控制台命令；不同环境可能不生效。
5. 测试 `idle/walk/run/crouch/jump/aim/fire/reload/weapon_swap/turn` 等键鼠动作。关键姿态期间保存截图及哈希；中途失焦、截图异常或就绪超时立即停止。
6. 对当前采集的截图执行低细节/纯色报警；可用用户提供的**同地图、同机位、同分辨率**基准图做逐动作像素差异告警。扫描本次追加的用户指定本地日志中的模型/材质/AG2 失败线索。
7. 输出 `game_qa_report.json` 和 `engine_validation.pending.json`，将截图路径回填到引擎清单，但仍保持 Hitbox、Physics、AG2 实际驱动等项目 `PENDING`，需要经验证的运行时证据与人工复核。

**不具备/不声称**：游戏内存读取、网络作弊或绕过反作弊、无需插件改变官方匹配角色、自动生成真实 Hitbox、可靠的图片 AI 穿模识别、从图片证明骨骼权重正确、在所有显卡/键鼠驱动下控制 Raw Input、自动从游戏结果修好 AG2 graph。部分外部服务器插件有 Valve 服务器令牌风险，具体取决于当前政策和插件实现。禁止用于官方匹配或未获允许的服务器。

## 2. 准备本地环境

- Windows 10/11（真实 GUI 键鼠自动化仅支持 Windows），Python 3.10+，Blender 和 CS2 Workshop Tools。
- 在 **用户自己控制的** CS2 私人专用服内提前安装当前版本兼容的 Metamod / CounterStrikeSharp / 模型切换插件，按需要挂载 Workshop VPK。工具不会安装这些插件，不修改游戏本体、不修改 `gameinfo.gi`、不私自发布内容。
- 在模型插件配置中登记已**编译并被客户端挂载**的逻辑模型路径，例如 `characters/.../name.vmdl`；`model_name` 使用插件真正接受的短名称。插件项目文档常用 `!model <name> all`，请先手工验证。
- 在 CS2 中启用开发者控制台，确认 `console_key` 与本人键盘布局一致（默认 `` ` ``）。检查射击、换弹、行走按键是否与配置一致。CS2 默认按住 Shift 是慢走，W 是正常跑；配置可更改。
- 只在 localhost / 127.0.0.1 上测试。v3 默认拒绝远程 IP、域名和非回环服务器。与其他人联网测试不在此功能范围。
- 安装可选 GUI 依赖：`python -m pip install -r requirements-game.txt`；需要图像模板匹配时使用 `opencv-python`。脚本使用的是截图和 Windows 前台键鼠事件，不是对游戏进程注入。
- 使用窗口化或无边框窗口模式更利于截图采集。部分游戏版本/图形设置阻止截图和合成输入，遇到不能自动输入时转为人工操作，不能自动判定成功。

## 3. 复制并校准配置

1. 从 `config/game_test.example.json` 复制到 `config/game_test.local.json`。
2. 填写 `server_endpoint`、`model_name`、`readiness`、`log_files` 和 `visual_baseline`；确保 `client_launch=true` 适用于当前 Steam 启动环境。`game_test.local.json` 的路径是相对该 JSON 所在目录解析的。
3. 用**自己 CS2 已进入测试地图后的一张局部清晰截图**裁出独特、稳定、不会在主菜单出现的就绪标记，保存为 `readiness.image_path`。它是“画面疑似就绪”的证据，不是插件工作成功的证据。无需动态 OCR。
4. 想使用日志信号时把 `readiness.strategy` 改为 `log_regex`，设置本地 `log_path` 和已在真实游戏里观测到的稳定**字面标记** `pattern`。工具只读取本轮启动后新增字节，防止历史日志误触发。注意游戏/插件更新可能使该标记失效。
5. 对当前版本已能正常运行的角色，保持测试地图位置、镜头/分辨率/皮肤状态不变，分别截取参考动作画面；填入 `visual_baseline.local.json`。像素差异较大只是**回归线索**（摄像机移动和时间光照变化同样影响结果），不可当作骨骼故障的确定诊断。
6. `allow_desktop_control` 默认 `false`。**仅在已确认要自动接管当前本机游戏时**改为 `true`；执行必须同时带 `--execute`。
7. 在 `config/workflow.local.json` 配置 `game_test_config: "game_test.local.json"`，`target: "player_runtime"`，及已校准的骨骼/包围盒规则。要一条命令启动私人服和客户端，配置 `launch_mode: "dedicated_server"`。

## 4. 单独运行游戏内检查

在 Skill 根目录执行：

```powershell
# 首次：检查参数、动作计划，不触碰游戏窗口、不启动客户端
python scripts/game_qa.py --config config/game_test.local.json --cs2-root "C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive" --out-dir reports/game_test_plan

# 已有本地私人服，并明确授权操作当前桌面后
python scripts/game_qa.py --config config/game_test.local.json --cs2-root "C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive" --out-dir reports/game_test_actual --execute
```

它**不会自动启动服务器**。如果使用 `client_launch=true` 则启动游戏客户端并以 `+connect` 连接 `server_endpoint`，若为 false 则要求你先自己打开客户端并进入地图；前台窗口、就绪标记及权限检查始终必须通过。

## 5. 接入原有一键流程

```powershell
# 仅全流程计划，不操作桌面
python scripts/auto_workflow.py run --config config/workflow.local.json --fix --deploy --compile --launch --game-test

# 本机授权：Blender 预检/安全纠错/复检 → Addon 部署 → 编译 → 启动私人服 → 客户端连本机服 → 动作 → 截图与日志
python scripts/auto_workflow.py run --config config/workflow.local.json --fix --deploy --compile --launch --game-test --execute
```

PowerShell 入口增加 `-GameTest` 参数。注意：

- `--game-test` 仅用于 `player_runtime`，当与 `--launch` 联用时必须是 `dedicated_server`，不能把 Workshop Tools GUI 当作玩家实体已加载。
- 原有严格部署门禁继续生效：骨骼父子关系、Rest Pose、有效权重、参考静态/动态边界有 FAIL 或强制 PENDING 时阻断。`--fix` 同时部署需要实测的导出 FBX 和 `.vmdl` 引用确认。
- **Windows 游戏进程可能比专用服启动得更快**。第一次运行请先独立启动专用服并确认地图/插件/资源挂载成功，再运行 `game_qa.py`。连服失败/超时会中断，而不是尝试关闭安全机制。
- 单独执行 `game_qa.py` 会生成新的图像证据，但不做 Blender 前置模型修复；要保证测试是这轮刚部署的模型，优先使用联动流程并核对模型资源哈希。

## 6. 自动测试时会发生什么

| 阶段 | 自动动作 | 判断证据 | 不足以证明 |
| --- | --- | --- | --- |
| 进程 | 启动或复用 CS2 客户端 | PID / 游戏窗口 | 已进地图、模型已加载 |
| 就绪 | 匹配独特地图模板 / 新日志字面标记 | 模板命中/日志新字节 | 服务器插件生效 |
| 选模 | 在游戏控制台发送 `say !model <name> all` | 已发送命令记录 | 实际切换成功 |
| 第三人称 | `say !tp` 或用户已启用的 `thirdperson` | 已发送命令 | 第三人称真正打开 |
| 动作 | 发送键鼠并在动作保持期间截图 | PNG、SHA-256、动作 ID/时长 | Raw Input 一定识别了合成事件 |
| 图像 | 低细节/可选基线像素差 | `visual_audit` | Hitbox、骨骼正确或模型身份 |
| 日志 | 扫描用户指定日志的本轮新字节 | `log_audit` 匹配线索 | 日志没有错误即一切正确 |
| 终验 | 输出待复核证据清单 | JSON、截图 | 引擎物理/动画全部通过 |

## 7. 自我检查输出与下一步

每次执行至少输出：

```text
reports/run_.../game_qa/
├── game_qa_report.json            # 进程/就绪/发命令/动作/截图及告警
├── engine_validation.pending.json # 预填证据，不自动标记 PASS
└── screenshots/
    ├── idle.png
    ├── walk.png
    ├── run.png
    ├── crouch.png
    ├── jump.png
    └── ...
```

检查每步截图是否包含**真正测试角色**、手臂/腿部有无错位、武器与手部是否正确、跑跳是否 T-pose、披风/头发是否穿透、裁剪、空白贴图等。像素基线报告若为 `WARN_VISUAL_REGRESSION`，先排除位置/镜头变化；日志出现 `MISSING_MODEL`、`MISSING_MATERIAL`、`ANIMGRAPH_WARNING` 等应先检查 Addon 资源与插件映射，再考虑骨骼重建。

`engine_validation.pending.json` 中的 Hitbox/Physics/AG2 仍为 `PENDING`，因纯屏幕输入没有这些游戏内部数据；补上 ModelDoc、专用服日志、第三人称录像与人工确认后，按原 `finalize_report.py` 生成最终验收。只要存在强制 PENDING/FAIL，不能报告完整模型通过。

## 8. 安全与故障处理

- 每步动作前都检查当前前台窗口是否为 CS2；失焦时停止，模拟键盘输入不会继续作用到聊天、浏览器或其他应用。`pyautogui.FAILSAFE=True`，把鼠标移动到屏幕左上角可以中止自动动作。
- 输入白名单不接受任意控制台命令/自定义 Python 宏，网络只允许回环接口。自动图像采集只截取当前游戏窗口，证据只保存本地，工具不会上传截图。
- `model_name` 不允许空格、分号、换行或任意命令拼接；第三人称命令仅 `say !tp`、`thirdperson`、`none`。
- 不会静默修改官方游戏或服务器 ACL，不会启动自动循环重试攻击，不关闭 VAC、不使用进程注入；测试脚本没有访问官方匹配的逻辑。
- **截图可能意外包含聊天或账户信息**，请在演示用私人地图中测试，不要未经检查上传公开服务器、仓库或分享报告。
- “找不到窗口”：请确认已进入 CS2 且前台标题符合配置，使用无边框窗口、显示器缩放适配。
- “无法自动匹配模板”：确认 OpenCV、模板是当前分辨率的游戏内稳定图形、游戏视窗没有遮挡；优先重新截模板。
- “已输入但游戏不执行”：核对控制台键和用户键位；某些 CS2 版本会拦截合成键鼠或第三人称命令；可人工操作并保留截图，不得伪造自动结果。
- “模型依然默认/紫色错误模型”：检查私人服模型插件实际配置、Addon / VPK 挂载、客户端取得资源、插件版本与逻辑路径。普通零散 Addon 复制到硬盘不等于游戏中加载。

## 9. 公开参考

- Steam 官方开发者控制台：https://help.steampowered.com/en/faqs/view/4700-D10E-26BE-DDDD
- Source2 Wiki Addon 挂载限制：https://www.source2.wiki/Basics/content-mounting
- CS2 PlayerModelChanger 的 `!model` / `!models` 约定：https://github.com/samyycX/CS2-PlayerModelChanger
- CS2 AG2 迁移社区案例：https://github.com/SergeantCS2/CS2-AG2-Model-Porter

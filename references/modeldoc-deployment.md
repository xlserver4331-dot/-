# ModelDoc、Hammer 与 CS2 本地房间部署指南

## 前提条件

- 仅针对本机用户可控制、可获授权的内容；不含覆盖 Valve 官方素材包或线上公开匹配的流程。
- Steam 中 CS2 的 DLC 里启用 `Counter-Strike 2 Workshop Tools`，从游戏的工具启动入口运行，创建自己的 Addon。
- 使用 Asset Browser / ModelDoc / Hammer 时以安装版本实际菜单和界面为准；CLI 资源编译参数可能变更，Skill 不提供未经当前机测试的“保证可用”编译命令。
- 建议首选**原生自制网格 + CS2 同版本合法参考骨架**，或在官方示例能正确运行的样板上校准。

## 1. 源和编译资源布局

以 addon `model_test` 示范（根据资源类别调整模型位置）：

```text
Counter-Strike Global Offensive/
  content/
    csgo_addons/model_test/
      models/custom/character.fbx
      models/custom/character.vmdl
      materials/custom/...
      maps/model_test.vmap
  game/
    csgo_addons/model_test/
      models/custom/character.vmdl_c
      materials/custom/...
      maps/...
```

这里的路径仅示意。ModelDoc 建立资源依赖和编译输出后，使用 Asset Browser 检查实际产物，不能靠目录外观认定已经被服务器加载。

## 2. 模型转换步骤

1. 从 Blender 导出与目标 Source 2 工具链兼容的 FBX 或 DMX；确认模型单位、骨架、顶点组、材质路径和绑定姿势。
2. Workshop Tools -> 创建 addon -> Launch Tools -> Asset Browser -> ModelDoc 创建 `.vmdl`；导入网格、骨架、材质、LOD 和动画资源。
3. 对模型用途确定 physics: 静态道具碰撞、动态道具碰撞和角色实体命中箱不是相同配置。需按对应模板建立与调试。
4. 以当前 CS2 工作的 AG2 玩家样本核对 `AnimGraph2List`、`NmSkeletonList`、`DefaultAnimGraph2`、`worldmodel.vnmgraph`、`worldmodel.vnmskel` 等引用；不要把旧 `.vanmgrph` 当成新版替代品。
5. 检查导入网格 `jointList` 与骨骼名严格一致，尤其大小写；检查 `pelvis` 重父级后的世界 Rest Transform 没有改变。
6. 执行 ModelDoc GUI 编译；根据控制台错误逐项处理材质/资源依赖；记录 `.vmdl_c` 和相关编译产物的准确路径。
7. 可使用 Source2Viewer 检查编译产物存在及几何/材料/骨架，但**仅源文件/视图器正常不说明 AG2 运行期正确**。

## 3. 路线 A：本地地图道具预览

1. Hammer 创建 `model_test.vmap`，设置地面、灯光和玩家出生点。
2. 添加 `prop_static`，指定自制编译模型逻辑路径，检查站位/朝向/阴影。需要动态可控模型则使用合适的 `prop_dynamic` 并设置被支持的动作/输入。
3. 编译地图，在 CS2 本地测试地图里观察模型、材质、裁剪、碰撞、是否被地面遮挡。
4. 将 `hammer_local_preview` 和 `physics_collision_reviewed` 的证据填入人工验收 JSON。
5. 此方法不能证明玩家换模后的 Hitbox、AG2 与手部武器姿态。若目标只是 prop，`engine_validation.target` 设为 `prop_preview`。

## 4. 路线 B：本地服务器玩家实体

**依赖不是 Skill 包内安装内容：**Metamod:Source、CounterStrikeSharp、MultiAddonManager（用于 Workshop 挂载）、PlayerModelChanger（用于切换玩家模型）等，版本必须与当前 CS2 兼容。插件有专用安装文档，不能假定路径/ABI 永久不变。

1. 建立**私人专用服务器**，先用原生地图、原生角色验证它能在本地正常运行；更新与游戏同构建版本。
2. 按当前版本文档安装各插件并在启动日志确认加载；备份所有服务器文件。不在官方比赛/匹配中使用定制角色替换。
3. 发布/挂载自己的 addon，核对资源 `*.vmdl_c` 真正打包进 VPK。若使用 Workshop/ MultiAddonManager，需记录 Workshop ID、挂载清单和客户端获取状态。
4. 在 PlayerModelChanger 中以**逻辑资源路径 `.vmdl`**（非 `.vmdl_c` 的磁盘后缀）配置模型条目；具体配置结构以插件对应版本为准。
5. 客户端用正常 CS2 游戏运行（不是保持 Workshop Tools 工具模式），打开开发者控制台，输入 `connect 127.0.0.1`，服务器的实际监听端口若非默认需加 `:port`。
6. 先切一次地图/重新加入（部分资源挂载流程需通过换图触发下载），用 `!models` 或 `!model <name> all`（若该版本 PlayerModelChanger 支持）切换模型。
7. 第三人称检查角色站立、走、跑、蹲、跳、落地、换枪、射击、换弹、投掷和持刀；再独立评估第一人称手臂。记录 T-pose/横倒/肘膝穿模/武器对不准/头发异常/裁剪消失。
8. 查看服务端和客户端日志中的资源未找到、AG1 残留、骨骼引用和插件加载错误；重新进游戏确保客户端也获得正确材质和模型。
9. 以本地可控环境和可接受的安全规则测量/核对 Hitbox 与 Physics；保存测试数据与证据。不要仅凭显示的美观程度声称命中正确。

### 运营与合规风险

PlayerModelChanger README 明确警告有 GSLT 禁用风险。只在用户自主控制并明确允许插件/素材使用的测试服务器上尝试；不应提供“保证不会被封”之类承诺。再发布非自制模型之前必须具有相关授权。官方游戏更新可能导致插件暂时失效。

## 5. 故障树

- **错误模型 / 没加载材质**：先检查 Workshop 审核/下载、打包目录包含 model 和 materials、服务器资源挂载、客户端资源缓存；再查编译引用。
- **T-pose**：若资源已经能正确加载，检查 AG1 残余 `.vanmgrph`、AG2 模型引用、角色 `root_motion`/`pelvis` 层级、模型骨名、绑定 Rest、DMX jointList；仅脚本扫描出现 token 不足以判定。
- **角色横倒**：检查 `pelvis` 重新设置父级后局部矩阵是否做了正确逆变换以及轴向错配。
- **手部武器错位**：`wpnPivot`/`wpn`、attachment、IK/AnimGraph 与角色参考姿态。
- **材质显示对但碰撞错**：Physics / Hitbox 的独立内容，不是渲染模型 AABB。
- **部分动作失败**：观察是否所有 Action 能对应至运行时 Graph；检查特定武器行为和根/辅助骨骼。
- **视角手臂与世界模型不同**：视角手臂单独构建/绑定/验收，AG2 下不等于第三人称世界模型的手臂。

## 6. 可复核证据

填写 `templates/engine_validation.template.json`，所有 `PASS` 必须有路径或日志索引（例如本地保存的截图、录像、编译日志、服务器日志）。测试记录包含：CS2 build、Workshop Tools 版本、Blender 版本、ModelDoc 资源、addon 名、Map、插件版本/仓库链接、测试人和日期。`finalize_report.py` 只对填入的证据做格式门控，**无法替你验证证据是否真实**。

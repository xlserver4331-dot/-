# 核实来源与版本注意

以下是公开参考资料，不包含或复制任何 Valve 模型/第三方资产、没有替用户获得重新分发许可。2026-11-06 起使用本 Skill 时建议核对其最新版本。

1. **Valve Steam News** — 2026-04-20：`All changes from the animgraph_2_beta build are now live`。https://store.steampowered.com/news/posts/?appids=730&enddate=1777070707
2. **ValveResourceFormat / Source2Viewer** — 当前 CS2 `pak01_dir.vpk`、角色、材料等资源位置介绍。https://s2v.app/ValveResourceFormat/games/counter-strike-2.html
3. **SergeantCS2 / CS2-AG2-Model-Porter** — 社区 AG2 兼容案例、Graph/Skeleton 资源引用、骨名大小写与换装本地服工作流。https://github.com/SergeantCS2/CS2-AG2-Model-Porter
4. **Technical NOTES** — 74 骨样本、`root_motion -> pelvis`、`wpnPivot/wpn`、`jointList`、Twist 限制和 Physics 未证实项。https://github.com/SergeantCS2/CS2-AG2-Model-Porter/blob/main/NOTES.md
5. **samyycX / CS2-PlayerModelChanger** — 服务端插件、`!models`/`!model` 命令、`.vmdl` 路径、GSLT 风险声明。https://github.com/samyycX/CS2-PlayerModelChanger
6. **Steam Support** — CS2 游戏内打开开发者控制台。https://help.steampowered.com/en/faqs/view/4700-D10E-26BE-DDDD
7. **CS2Fixes releases** — 第三方插件对 2026 年版本/AG2 迁移的适配情况，说明插件必须持续跟随版本。https://github.com/Source2ZE/CS2Fixes/releases

## 证据等级

- 官方更新能证明 **AG2 已上正式版本**，不能证明某个第三方模型节点可以通用。
- 社区 AG2 Porter 的技术笔记是特定样本的真实实测，不是 Valve 公开的稳定 ABI 或全面的骨骼规格。
- PlayerModelChanger 文档是第三方插件约定，与 Valve 官方模式不同。
- `AG2 graph`、Physics、Hitbox 和服务器运行实测需要用户在自己的安装上进行。任何自动静态分析都不能代表全部运行时正确。

## 一键部署/编译/启动参考

8. **Source2Wiki — Addons**：Addon Launcher、`content/csgo_addons/<addon>` 和 `game/csgo_addons/<addon>`、工具模式与挂载。https://www.source2.wiki/Basics/working-on-content/addons
9. **Source2Wiki — Resource Compiler**：`resourcecompiler.exe -i <源文件>` 与源/产物对应。https://www.source2.wiki/EngineTools/ResourceCompiler/
10. **Steam/Valve CS2 Dedicated Server Release Notes（2023-09-29）**：参考 `cs2 -dedicated +map de_dust2`。https://store.steampowered.com/news/posts/?appids=730&enddate=1696549240
11. **Source2Wiki — Content Mounting**：零散 Addon 与 Retail 客户端的打包限制，不可假定复制到 Addon 就能在普通房间加载。https://www.source2.wiki/Basics/content-mounting


## v3 自动客户端与视觉证据

12. **Steam Support — Developer console**：CS2 启用开发者控制台。https://help.steampowered.com/en/faqs/view/4700-D10E-26BE-DDDD
13. **CS2-PlayerModelChanger README**：私人服务器 `!model <name> all` / `!models` 等命令，另有 GSLT 风险提示。https://github.com/samyycX/CS2-PlayerModelChanger
14. **Source2Wiki — Content Mounting**：Retail 客户端与 Tools Addon 挂载方式不同，不能假设复制文件后普通客户端即可使用。https://www.source2.wiki/Basics/content-mounting
15. **Steam Support — Launch Options**：`-console`、`-condebug` 等基础选项。https://help.steampowered.com/en/faqs/view/7D01-D2DD-D75E-2955

自动化脚本尝试以 `+connect 127.0.0.1:<port>` 加入本地私人服。该路径的有效性依赖客户端启动状态、Steam 与服务器版本；**必须通过本地实际就绪信号核验**。控制台第三人称/插件命令、合成键鼠是否生效依赖私人服、插件版本、键盘布局和图形环境，不能在缺少游戏实测时宣称可靠。

## v4 补充（2026-11-06 核对）

- Valve AnimGraph 2 beta 官方公告（2026-04-01，第三人称动画重制）: https://www.counter-strike.net/newsentry/528750051218948816
- AG2 正式版新闻（2026-04-21）: https://www.hltv.org/news/44430/animgraph2-goes-live-in-latest-cs2-update
- ValveResourceFormat/S2 Viewer CS2 模型与第一人称手臂目录: https://s2v.app/ValveResourceFormat/games/counter-strike-2.html
- AG2 Viewmodel 资源/动画接口: https://s2v.app/ValveResourceFormat/api/ValveResourceFormat.Renderer.SceneNodes.ViewmodelSceneNode.html
- 本地控制台 `sv_cheats 1` 和 `kill` 命令参考（需按本机当前版本和权限校准）: https://nodecs.net/wiki/cs2-sv-cheats-commands?lang=en

这些来源只支持相应资源/动画系统或本地测试命令的存在；不构成特定自定义模型能够自动支持死亡/ragdoll、第一人称手模替换或官方服务器使用的保证。

## v5 配件骨骼与关节形变资料（2026-11-08）

- ValveResourceFormat Source2Viewer 模型格式支持，包括约束、物理关节、布料结构；布料反编译仍有局限：https://s2v.app/ValveResourceFormat/guides/format-support.html
- Source2Viewer 的 ModelAnimation 结构（父子约束、骨骼动作、Twist、死亡时层级转换）：https://s2v.app/ValveResourceFormat/api/ValveResourceFormat.ResourceTypes.ModelAnimation.html
- Source2Viewer 解析的骨骼用途标识，`Cloth`、`Physics`、`RigidLength` 等表示**可被解析的格式字段**，不等于所有 CS2 自定义模型都能直接使用：https://s2v.app/ValveResourceFormat/api/ValveResourceFormat.ModelSkeletonBoneFlags.html
- 不同 Source2 游戏 s&box 的 jiggle bones 饰品教程，仅供骨骼链设计参考，不可当作 CS2 的相同工具/API 承诺：https://sbox.game/learn/shadb/jiggle-101


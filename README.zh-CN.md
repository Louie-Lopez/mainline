# Mainline · 项目主线轴

**和 AI 工作时，始终看得见整个项目。**

[English](README.md) · [下载版本](https://github.com/Louie-Lopez/mainline/releases) · [反馈问题](https://github.com/Louie-Lopez/mainline/issues)

长对话会不断累积修改、实验和临时插问。最新任务容易取代整个项目，已经完成的工作难以找回，“本轮做完了”也容易被误当成“项目完成了”。Mainline 用**一句项目主线和一条稳定的全生命周期阶段轴**，让你直接看到：当前工作属于哪里、哪些环节正在推进、还有哪些没有完成，减少反复翻阅对话的负担。

![Mainline 的项目全景与两个同时活动的阶段](docs/overview.png)

它定位为图形化 AI 工作环境中的本地可视化辅助工具，首先面向 Codex 桌面端，已在 Windows 上验证。AI 通过 skill 和 Python 工具维护记录，你在浏览器面板中看进展。命令行是 AI 更新状态的接口，日常使用只需说：

> 用 Mainline 跟踪这个项目的全生命周期，把当前任务放到对应环节，只在进展有意义地变化时更新。

## 核心能力

- **保留项目全景。** 阶段从已约定的起点覆盖到最终成果，除非项目范围有重大变化，否则保持稳定。
- **明确当前位置。** 支持多个环节同时活动，可用“修复错误”“验证结果”等短标签表达工作性质。
- **按需查看细节。** 点击环节切换到它的一句话目标、可选说明与一层子环节，总览不堆积细节。
- **跨对话恢复。** 同项目沿用同一份本地状态，避免每次从聊天记录重建进度。
- **保持低负担。** 浏览、点击、刷新都不调用模型；页面每 30 秒读取本地状态，隐藏后暂停。AI 只记录有意义的变化。

进展来自 AI 的明确记录。Mainline 不会独立监听所有对话、证明任务已完成或保证 AI 不跑偏。这条轴表示项目阶段，不表示真实耗时，也不承担任务看板或聊天归档的功能。

<details>
<summary>查看展开环节和窄窗口效果</summary>

![选中环节后切换目标并显示内容](docs/expanded.png)

<img src="docs/vertical.png" alt="窄窗口下自动变为竖轴" width="300">

</details>

## 在 Codex 中安装

运行需要 **Python 3.10+** 和现代浏览器。Mainline 本身不需要额外 Python 包、API 密钥、账号或云服务。当前版本是公开测试版。

让 Codex 从本仓库安装插件，或注册仓库插件源并安装：

```sh
codex plugin marketplace add Louie-Lopez/mainline
codex plugin add mainline@mainline-tools
```

之后开启新对话，选择 Mainline 或调用 `$mainline`，要求它跟踪项目。图形化宿主支持时，AI 会将返回的地址打开到浏览器面板；其他环境可直接打开链接。这里是仓库提供的插件源，**不等于已上架 OpenAI 公共插件目录**；本项目尚未提交目录审核。

如果当前 Codex 版本不支持这些插件命令，也可以安装独立 skill：

```text
用 $skill-installer 安装以下目录中的技能：
https://github.com/Louie-Lopez/mainline/tree/main/plugin/skills/mainline
```

两种形式选择一种，避免重复加载。已有自定义技能目录可继续使用。安装机制参见官方的[技能路径说明](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)与[插件分发说明](https://developers.openai.com/plugins/build/plugins)。

## 多语言

界面内置英文和简体中文，跟随浏览器语言，未匹配时使用英文。在返回的地址后加 `?lang=zh` 或 `?lang=en` 可指定语言，不额外增加界面控件。

主线、阶段名、说明和自定义标签保留用户编写的语言，让 AI 按你的语言填写即可。没有后台翻译或额外模型调用。命令名和诊断信息使用英文，使用说明提供中英文。其他界面语言可扩展 `card.html` 中的小型 `messages` 字典。

## 为什么 skill 和插件都有？

**Skill** 告诉 AI 如何界定项目、何时更新；**Python 工具**负责校验和保存；**网页**负责呈现；**插件**把这三者打包，方便安装和分发。插件封装不会自动把网页变为原生工具栏，也不会因此持续监听其他对话。

当前发布同时提供 Codex 仓库插件源和 Releases 中的标准插件 ZIP。以后如果更深的界面集成确实能减少操作，可以再考虑 MCP 或宿主 Extension；现阶段保留本地架构，避免为相同能力增加云服务和运行成本。

## 其他 AI 能否使用？

| 环境 | 当前情况 |
| --- | --- |
| Codex 桌面端、本地执行 | 主要使用方式，已在 Windows 验证。 |
| 其他本地图形化 AI 工具 | 能读取技能规则、执行 Python、访问同一状态文件时，可以复用核心；指令发现与面板打开方式仍需逐个验证。 |
| CLI Agent | 可维护状态，用户通过独立浏览器查看。 |
| 远程 Agent、纯云端聊天 | 不能直接访问用户机器的回环地址，需要明确的本地执行或端口转发，目前未提供。 |

核心数据和展示不绑定模型，但接入取决于宿主能力，不能笼统承诺“所有 AI 开箱即用”。本版尚未验证 macOS、Linux 与其他宿主。

## 本地运行与开发

在仓库目录执行以下命令。将 `STATE` 替换为项目中的**绝对路径**，例如 `.mainline/demo/` 下的状态文件，并放在插件安装目录之外：

```sh
python mainline.py init --state STATE --task-id demo --mainline "交付经过验证、满足目标的成果。" --stage 定义目标 --stage 实现 --stage 验证 --stage 交付
python mainline.py status --state STATE --done 定义目标 --active 实现 --active 验证
python mainline.py start --state STATE
```

打开返回的链接即可。每个项目使用独立状态，同一文件由一个协调代理写入。更新、细分、描述和恢复规则见 [SKILL.md](SKILL.md)。你自己的公开仓库也应忽略 `.mainline/`，它可能包含私人项目内容和机器路径。服务仅监听 `127.0.0.1`，网页接口只读，无遥测和外部 API 请求；本地文件及 AI 宿主取得的访问权限仍由宿主管理。

更新 `mainline.py` 后需要重启原服务；只改网页时刷新即可。轴变淡表示连接或读取失败，当前保留的是上次成功读取的画面。

```sh
python -m unittest -q test_mainline
npm install --no-save --package-lock=false playwright
npx playwright install chromium
node test_browser.cjs
node test_languages.cjs
python build_plugin.py
```

Node 和 Playwright 仅用于浏览器测试。可用 `MAINLINE_PYTHON`、`MAINLINE_PLAYWRIGHT`、`MAINLINE_BROWSER_CHANNEL` 指定已有运行环境。测试数据保留在被忽略的 `.test-runs/`。编辑根目录源码后运行 `build_plugin.py`，按明确清单生成仓库中的 `plugin/` 分发目录及 `dist/mainline-<版本>.zip`。两者均排除实际项目数据，`skills/mainline/` 使用同一份技能和运行代码。

最有帮助的反馈来自实际项目：主线是否缩窄、活动阶段是否清楚、更新是否打扰对话。请在 [Issues](https://github.com/Louie-Lopez/mainline/issues) 中附上宿主、系统、期望行为和不含私人内容的最小示例。

采用 [MIT 许可证](LICENSE)。

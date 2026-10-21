# Mainline

**Keep the whole project in view while you work with AI.**

[Try the demo](https://louie-lopez.github.io/mainline/?lang=en) · [简体中文](README.zh-CN.md) · [Releases](https://github.com/Louie-Lopez/mainline/releases) · [Report an issue](https://github.com/Louie-Lopez/mainline/issues)

Long AI conversations accumulate fixes, experiments, and side questions. The latest request can take over the plan, completed work becomes hard to recover, and “this task is done” gets confused with “the project is done.” Mainline keeps one project goal and a small, stable axis of stages from project start to completion beside the conversation, so you can see **where the work belongs, what is active, and what remains** without rereading the chat.

![Mainline showing a project lifecycle with two active stages](docs/overview.png)

The [interactive demo](https://louie-lopez.github.io/mainline/?lang=en) needs no installation. Explore a sample project, expand a stage, or switch between parallel work, fixing, and delivery. It uses the same renderer as the installed tool, with fictional data and no AI connection.

Mainline is a local project view that you use alongside an AI assistant. You ask the assistant to record the project's goal, stages, and progress; it saves those records on your machine, and you view them in a browser. After installation, start with a request such as:

> Use Mainline to track this project's full lifecycle. Put our current work in the corresponding stage and update it only when progress meaningfully changes.

## What it does

- **Preserves the project view.** Stages cover the agreed project from start to outcome and stay fixed unless its scope materially changes.
- **Shows current work.** Multiple stages can be active, with short labels such as “Fixing” or “Verifying.”
- **Reveals detail on demand.** Select a stage for its goal, optional description, and one level of substages. The overview remains small.
- **Resumes across chats.** Reuse the same project's local state file instead of reconstructing progress from every message.
- **Keeps overhead small.** No model calls for viewing, clicking, or refreshing. The page checks local state every 30 seconds and pauses while hidden; the agent writes only meaningful changes.

The axis shows the order of project stages, rather than time spent. Progress comes from explicit updates by the assistant, so its accuracy depends on those updates. Mainline helps you spot drift and resume work; it does not independently monitor conversations or verify completion. Reading its instructions and making updates still use the assistant's normal context and tool calls.

<details>
<summary>Expanded stage and narrow-window view</summary>

![Expanded stage with its own goal](docs/expanded.png)

<img src="docs/vertical.png" alt="The same project displayed vertically in a narrow window" width="300">

</details>

## Where it works

Mainline's records and browser view do not depend on a particular model provider. What matters is whether the AI application can read its operating instructions, run Python, and access the project's local files.

| Environment | Current support |
| --- | --- |
| Codex desktop with local execution | Primary workflow; installation and use tested on Windows. The view can open beside the chat. |
| Other AI assistants with local execution | Can reuse the same instructions and runtime files. Installation and opening the view need verification in each application. |
| Assistants used in a terminal | Can update the record; you view it in a separate browser. |
| Remote agents or cloud-only chat | Need a way for your browser to reach the machine running Mainline. No remote connection setup is included. |

The current release is a public beta. Other AI applications and macOS/Linux have not yet been tested.

## Install

Requires **Python 3.10+** and a modern browser. Mainline itself needs no additional Python packages, API key, account, or hosted service.

There are two ways to install the same functionality:

- A **skill** is a folder containing instructions for the assistant and supporting files. Mainline's folder includes `SKILL.md` (when and how to update), `mainline.py` (saving and serving the record), and `card.html` (the browser view). It uses the open [Agent Skills format](https://agentskills.io/home).
- A **plugin** packages that folder so an AI application can install and manage it. This repository provides a tested Codex installation route.

Choose one form. Installing both adds no functionality and can load the skill twice. Either way, the view runs in a browser; packaging it as a plugin does not add a native toolbar or automatic conversation monitoring.

### Codex: plugin installation

Ask Codex to install Mainline from this repository, or run:

```sh
codex plugin marketplace add Louie-Lopez/mainline
codex plugin add mainline@mainline-tools
```

These commands register this repository as an installation source and install Mainline. Then start a new chat, select Mainline or mention `$mainline`, and ask it to track the project. The assistant can open the view in a browser panel when supported, or give you a link.

This repository source is separate from OpenAI's public plugin directory. Mainline has not been submitted to that directory. A plugin ZIP is also available on the [Releases page](https://github.com/Louie-Lopez/mainline/releases); compatible import support depends on the application. See the official [plugin documentation](https://developers.openai.com/plugins/build/plugins).

### Codex or another assistant: standalone skill

The complete skill folder is [`plugin/skills/mainline`](plugin/skills/mainline). Install that folder using your application's skill installation mechanism. Keep all three files together; copying only `SKILL.md` will not provide the running tool. Avoid installing the whole repository as a skill, because it also contains a development copy.

With Node.js 22.20 or later, you can use the community [skills installer](https://github.com/vercel-labs/skills) and choose your AI application:

```sh
npx skills add https://github.com/Louie-Lopez/mainline/tree/main/plugin/skills/mainline --skill mainline
```

This installation route has been checked for Codex on Windows. Node.js is only needed for this installer. Its anonymous installation telemetry supports discovery on [skills.sh](https://www.skills.sh/docs/faq); you can disable it with `DISABLE_TELEMETRY=1`. Mainline itself does not collect telemetry.

In Codex, you can ask its built-in skill installer:

```text
Use $skill-installer to install the skill from:
https://github.com/Louie-Lopez/mainline/tree/main/plugin/skills/mainline
```

Existing standalone installations can keep using this form, with the same features as the plugin. For other applications, check how they load Agent Skills and allow local Python execution. A shared skill format makes reuse possible; it does not mean this release has been tested in every compatible application.

## Languages

Built-in interface text supports English and Simplified Chinese. It follows browser language preferences, with English as fallback. Add `?lang=en` or `?lang=zh` to the returned URL to override it without adding controls to the page.

Project goals, stage names, descriptions, and custom labels stay in the language you author them in. Ask the agent to use your language. There is no background translation or associated model call. CLI command names and diagnostics are English; both user guides are maintained. Add further UI languages to the small `messages` dictionary in `card.html`.

## Local use and development

Run these from the repository. Replace `STATE` with an **absolute path** in your project, such as a file under `.mainline/demo/`; keep it outside the installed plugin directory.

```sh
python mainline.py init --state STATE --task-id demo --mainline "Deliver a useful, verified result." --stage Define --stage Build --stage Validate --stage Deliver
python mainline.py status --state STATE --done Define --active Build --active Validate
python mainline.py start --state STATE
```

Open the returned URL. Each project uses a separate state file, with one coordinating writer. See [SKILL.md](SKILL.md) for updates, substages, descriptions, and recovery. Keep `.mainline/` out of your own public repositories: it may contain private project details and machine paths. The service binds to `127.0.0.1`, exposes read-only routes, and makes no telemetry or outbound API calls. Local files and access granted to your AI host remain under that host's controls.

After changing `mainline.py`, restart its existing server; refreshing the browser is sufficient only for HTML changes. A dimmed axis means the last known view is being retained after a connection or read failure.

```sh
python -m unittest -q test_mainline
npm install --no-save --package-lock=false playwright
npx playwright install chromium
node test_browser.cjs
node test_languages.cjs
python build_plugin.py
python build_demo.py
node test_demo.cjs
```

Node/Playwright are only for browser tests. `MAINLINE_PYTHON`, `MAINLINE_PLAYWRIGHT`, and `MAINLINE_BROWSER_CHANNEL` can select an existing runtime/module/browser channel. Tests retain isolated fixtures under ignored `.test-runs/`. Edit the root sources; `build_plugin.py` regenerates the tracked `plugin/` distribution and `dist/mainline-<version>.zip` from an explicit file list. Both exclude runtime data and contain the same skill/runtime sources under `skills/mainline/`.

Feedback is most useful after trying a real project: did the scope stay correct, were active stages clear, and did updates become intrusive? Open an [issue](https://github.com/Louie-Lopez/mainline/issues) with the host, operating system, expected behavior, and a minimal example without private data.

The public demo is generated from `card.html` and the small `demo/` wrapper. Run `build_demo.py` after either changes. GitHub Pages serves the tracked `docs/` directory; the demo has no backend, dependencies, or connection to real project records.

[MIT license](LICENSE).

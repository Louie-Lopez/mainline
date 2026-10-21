# Mainline

**Keep the whole project in view while you work with AI.**

[Try the demo](https://louie-lopez.github.io/mainline/?lang=en) · [简体中文](README.zh-CN.md) · [Releases](https://github.com/Louie-Lopez/mainline/releases) · [Report an issue](https://github.com/Louie-Lopez/mainline/issues)

When you build a product or run a project with AI, the conversation gives you plenty of detail about individual tasks. Keeping a clear picture of the whole project takes more effort: which stage are we in, where does this change belong, and what is still ahead? Even when the assistant retains the context, you may need to reread messages or ask for another summary just to get your bearings.

Mainline keeps **one project goal and a stable axis covering the full lifecycle** beside the conversation. You can see the current position, active work, and remaining stages at a glance, then open a stage for detail. The aim is to reduce the effort of remembering and looking up progress, so you can follow the project as a whole.

![Mainline showing a project lifecycle with two active stages](docs/overview.png)

The [interactive demo](https://louie-lopez.github.io/mainline/?lang=en) needs no installation. Explore a sample project, expand a stage, or switch between parallel work, fixing, and delivery. It uses the same renderer as the installed tool, with fictional data and no AI connection.

Mainline is a local project view that you use alongside an AI assistant. You ask the assistant to record the project's goal, stages, and progress; it saves those records on your machine, and you view them in a browser. After installation, start with a request such as:

> Use Mainline to track this project's full lifecycle. Put our current work in the corresponding stage and update it only when progress meaningfully changes.

## What it does

- **Preserves the project view.** Stages cover the agreed project from start to outcome and stay fixed unless its scope materially changes.
- **Shows current work.** Multiple stages can be active, with short labels such as “Fixing” or “Verifying.”
- **Reveals detail on demand.** Select a stage for its goal, optional description, and one level of substages. The overview remains small. Descriptions can use short paragraphs, ordered steps, or parallel items, with indentation for genuine child points.
- **Resumes across chats.** Reuse the same project's local state file instead of reconstructing progress from every message.
- **Keeps overhead small.** No model calls for viewing, clicking, or refreshing. The page checks local state every 30 seconds and pauses while hidden; the agent writes only meaningful changes.

The axis shows the order of project stages, rather than time spent. Progress comes from explicit updates by the assistant, so its accuracy depends on those updates. Mainline provides a shared view of progress that can also help you notice scope drift and resume work. It does not independently monitor conversations or verify completion. Reading its instructions and making updates still use the assistant's normal context and tool calls.

<details>
<summary>Expanded stage and narrow-window view</summary>

![Expanded stage with its own goal](docs/expanded.png)

<img src="docs/vertical.png" alt="The same project displayed vertically in a narrow window" width="300">

</details>

For projects with distinct possible directions, try the [branch experiment](https://louie-lopez.github.io/mainline/branches.html?lang=en). It keeps alternative routes under the stage where they diverge, with a separate view for each. This is an early interaction demo with sample data; branch creation and progress updates are not part of the installed tool yet.

## Where it works

This beta is mainly for Codex desktop. Plugin installation and use have been tested on Windows. The same package is checked on Windows, macOS, and Linux for local startup, progress updates, and browser interaction. See the [automated test results](https://github.com/Louie-Lopez/mainline/actions/workflows/compatibility.yml).

The runtime uses Python and a browser, so other AI assistants can reuse the standalone skill if they can run local commands and access project files. In a terminal, open the view in your usual browser. With a remote agent, the browser needs access to the machine running Mainline.

## Install

Requires **Python 3.10+** and a modern browser. Mainline itself needs no additional Python packages, API key, account, or hosted service.

If your system uses the command `python3`, use it in place of `python` in the examples below.

Choose the Codex plugin or the standalone [Agent Skills](https://agentskills.io/home) package. Both provide the same functionality; install only one to avoid duplicate loading. Mainline opens in a browser panel or separate browser, with progress explicitly updated by the assistant.

### Codex: plugin installation

Ask Codex to install Mainline from this repository, or run:

```sh
codex plugin marketplace add Louie-Lopez/mainline
codex plugin add mainline@mainline-tools
```

These commands register this repository as an installation source and install Mainline. Then start a new chat, select Mainline or mention `$mainline`, and ask it to track the project. The assistant can open the view in a browser panel when supported, or give you a link.

This repository source is separate from OpenAI's public plugin directory. Mainline has not been submitted to that directory. A plugin ZIP is also available on the [Releases page](https://github.com/Louie-Lopez/mainline/releases); compatible import support depends on the application. See the official [plugin documentation](https://developers.openai.com/plugins/build/plugins).

### Codex or another assistant: standalone skill

The complete skill folder is [`plugin/skills/mainline`](plugin/skills/mainline). Install that folder using your application's skill installation mechanism. Keep all three files together; copying only `SKILL.md` will not provide the running tool. The installer discovers this folder automatically from the repository.

With Node.js 22.20 or later, you can use the community [skills installer](https://github.com/vercel-labs/skills) and choose your AI application:

```sh
npx skills add Louie-Lopez/mainline --skill mainline
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

Open the returned URL. Each project uses a separate state file, with one coordinating writer. See [SKILL.md](plugin/skills/mainline/SKILL.md) for updates, substages, descriptions, and recovery. Keep `.mainline/` out of your own public repositories: it may contain private project details and machine paths. The service binds to `127.0.0.1`, exposes read-only routes, and makes no telemetry or outbound API calls. Local files and access granted to your AI host remain under that host's controls.

After changing `mainline.py`, restart its existing server; refreshing the browser is sufficient only for HTML changes. A dimmed axis means the last known view is being retained after a connection or read failure.

```sh
python -m unittest -q test_mainline
python test_package_runtime.py
npm install --no-save --package-lock=false playwright
npx playwright install chromium
node test_browser.cjs
node test_languages.cjs
python build_plugin.py
python build_demo.py
node test_demo.cjs
```

Node/Playwright are only for browser tests. `MAINLINE_PYTHON`, `MAINLINE_PLAYWRIGHT`, and `MAINLINE_BROWSER_CHANNEL` can select an existing runtime/module/browser channel. Tests retain isolated fixtures under ignored `.test-runs/`. Edit `mainline.py`, `card.html`, and `packaging/mainline-skill.md`; `build_plugin.py` regenerates the tracked `plugin/` distribution and `dist/mainline-<version>.zip` from an explicit file list. Both exclude runtime data and contain the same skill/runtime sources under `skills/mainline/`.

With Codex CLI installed, `python test_plugin.py --browser` also tests installation in a separate Codex profile, skill discovery, and the runtime and views loaded from the installed plugin cache. It leaves your existing Codex configuration and Mainline service alone. [Cross-platform checks](https://github.com/Louie-Lopez/mainline/actions/workflows/compatibility.yml) test the packaged runtime and browser views on Windows, macOS, and Linux.

Feedback is most useful after trying a real project: could you tell where the project stood, did you need to reread the conversation less, and did updates become intrusive? Open an [issue](https://github.com/Louie-Lopez/mainline/issues) with the host, operating system, expected behavior, and a minimal example without private data.

The public demo is generated from `card.html` and the small `demo/` wrapper. Run `build_demo.py` after either changes. GitHub Pages serves the tracked `docs/` directory; the demo has no backend, dependencies, or connection to real project records.

[MIT license](LICENSE).

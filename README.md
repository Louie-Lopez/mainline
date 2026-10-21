# Mainline

**Keep the whole project in view while you work with AI.**

[简体中文](README.zh-CN.md) · [Releases](https://github.com/Louie-Lopez/mainline/releases) · [Report an issue](https://github.com/Louie-Lopez/mainline/issues)

Long AI conversations accumulate fixes, experiments, and side questions. The latest request can take over the plan, completed work becomes hard to recover, and “this task is done” gets confused with “the project is done.” Mainline keeps one project goal and a small, stable lifecycle axis beside the conversation, so you can see **where the work belongs, what is active, and what remains** without rereading the chat.

![Mainline showing a project lifecycle with two active stages](docs/overview.png)

Mainline is a local visual companion for graphical AI workspaces, initially tested in Codex desktop on Windows. The agent maintains the record through a skill and a small Python tool; you read it in a browser panel. The command line is the update interface for the agent. Normal use starts with a request such as:

> Use Mainline to track this project's full lifecycle. Put our current work in the corresponding stage and update it only when progress meaningfully changes.

## What it does

- **Preserves the project view.** Stages cover the agreed project from start to outcome and stay fixed unless its scope materially changes.
- **Shows current work.** Multiple stages can be active, with short labels such as “Fixing” or “Verifying.”
- **Reveals detail on demand.** Select a stage for its goal, optional description, and one level of substages. The overview remains small.
- **Resumes across chats.** Reuse the same project's local state file instead of reconstructing progress from every message.
- **Keeps overhead small.** No model calls for viewing, clicking, or refreshing. The page checks local state every 30 seconds and pauses while hidden; the agent writes only meaningful changes.

Mainline records progress reported by the agent. It does not independently monitor conversations, prove completion, or guarantee that an agent stays on track. It is a stage axis, not an elapsed-time chart, task board, or transcript archive.

<details>
<summary>Expanded stage and narrow-window view</summary>

![Expanded stage with its own goal](docs/expanded.png)

<img src="docs/vertical.png" alt="The same project displayed vertically in a narrow window" width="300">

</details>

## Install in Codex

Requires **Python 3.10+** and a modern browser on the machine running the agent. No Python packages, API key, account, or hosted service are needed by Mainline. The current release is a public beta.

Ask Codex to install the plugin from this repository, or register its repository marketplace and install it:

```sh
codex plugin marketplace add Louie-Lopez/mainline
codex plugin add mainline@mainline-tools
```

Then start a new chat, select Mainline or mention `$mainline`, and ask it to track the project. In a graphical host the agent can open the returned URL in a browser panel; other hosts can show a normal browser link. This repository marketplace is separate from OpenAI's public plugin directory. Mainline has not been submitted to that directory.

If your Codex version does not support these commands, use the standalone skill:

```text
Use $skill-installer to install the skill from:
https://github.com/Louie-Lopez/mainline/tree/main/plugin/skills/mainline
```

Install one form to avoid duplicate skills. Existing installations in a custom skills directory can continue using it. See the official [skill locations](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills) and [plugin distribution documentation](https://developers.openai.com/plugins/build/plugins).

## Languages

Built-in interface text supports English and Simplified Chinese. It follows browser language preferences, with English as fallback. Add `?lang=en` or `?lang=zh` to the returned URL to override it without adding controls to the page.

Project goals, stage names, descriptions, and custom labels stay in the language you author them in. Ask the agent to use your language. There is no background translation or associated model call. CLI command names and diagnostics are English; both user guides are maintained. Add further UI languages to the small `messages` dictionary in `card.html`.

## Why a skill inside a plugin?

The **skill** teaches the agent what the project scope means and when to update. The **Python tool** validates and saves state. The **web view** presents it. The **plugin** bundles these pieces for installation and distribution. Packaging it as a plugin does not turn the page into a native toolbar or make it automatically observe other chats.

This release includes a Codex repository marketplace and a portable plugin ZIP on the Releases page. A hosted MCP service or deeper host Extension could improve access in other environments, but would add runtime and integration work. Mainline keeps the local architecture because it meets the core need with little machinery.

## Other AI environments

| Environment | Current fit |
| --- | --- |
| Codex desktop with local execution | Primary workflow; tested on Windows. |
| Other local graphical agents | Can reuse the skill, tool, and browser view if they can read instructions, run Python, and access the same state file. Host-specific instruction discovery and panel opening still need verification. |
| CLI agents | Can maintain state; view it in a separate browser. |
| Remote agents or cloud-only chat | Not directly compatible with the user's loopback address. Requires deliberate local execution or port forwarding; not included. |

State and rendering are model-independent. Integration depends on the host's file, process, and browser capabilities; this is not a claim that every AI product works out of the box. macOS/Linux and other hosts remain unverified in this release.

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
```

Node/Playwright are only for browser tests. `MAINLINE_PYTHON`, `MAINLINE_PLAYWRIGHT`, and `MAINLINE_BROWSER_CHANNEL` can select an existing runtime/module/browser channel. Tests retain isolated fixtures under ignored `.test-runs/`. Edit the root sources; `build_plugin.py` regenerates the tracked `plugin/` distribution and `dist/mainline-<version>.zip` from an explicit file list. Both exclude runtime data and contain the same skill/runtime sources under `skills/mainline/`.

Feedback is most useful after trying a real project: did the scope stay correct, were active stages clear, and did updates become intrusive? Open an [issue](https://github.com/Louie-Lopez/mainline/issues) with the host, operating system, expected behavior, and a minimal example without private data.

[MIT license](LICENSE).

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Skill optimizer** — `/optimize-skill` command that iteratively improves SKILL.md files by running test cases, scoring results (completion, errors, geometric correctness, efficiency, visual similarity), and using the LLM to modify instructions. Includes PySide2 configuration dialog, version history with original backup, three optimization strategies (conservative, balanced, aggressive), and configurable network retry with exponential backoff. Inspired by [autoresearch](https://github.com/karpathy/autoresearch).
- **Built-in skills auto-discovery** — SkillsRegistry now scans both the repo's `skills/` directory and the user's `~/.config/FreeCAD/FreeCADAI/skills/`. User skills override built-in skills with the same name. No more manual copying of built-in skills.
- **Hooks system** — user-defined Python hooks that fire on lifecycle events (`pre_tool_use`, `post_tool_use`, `user_prompt_submit`, `post_response`). Hooks can block actions, modify input, or log activity. Directory-based discovery at `~/.config/FreeCAD/FreeCADAI/hooks/`. Includes built-in `log-tool-calls` hook and Settings UI for managing hooks.
- **Configurable context window** — new "Context Window" setting controls when automatic conversation compaction triggers. Set to your model's context limit or lower to control API costs.

## [0.4.0-alpha] - 2026-03-26

Multi-provider support and tool calling reliability.

### Added

- **16 new LLM providers** — DeepSeek, Qwen (DashScope), Groq, Mistral, Together AI, Fireworks AI, xAI (Grok), Cohere, SambaNova, MiniMax, Llama (Meta), GitHub Models, HuggingFace, Zhipu (GLM), Moonshot (Kimi). All OpenAI-compatible with tool calling support. Total: 22 providers + custom.
- **Dynamic API key resolution** — API keys support `file:/path/to/token` (re-read each call) and `cmd:command` (run command, use stdout) prefixes to avoid storing keys in plaintext.
- **Smart object name resolution** — `_get_object()` auto-resolves common LLM naming mistakes (`Sketch0`→`Sketch`, `Sketch1`→`Sketch001`, `Body1`→`Body001`). Error messages now list available objects via `_suggest_similar()` for LLM self-correction.

### Fixed

- **Streaming `finish_reason` handling** — tool calls no longer silently dropped when providers return `"stop"` instead of `"tool_calls"` as the finish reason.
- **`tool_choice="auto"` now explicit** — some providers (e.g. Moonshot/Kimi-K2.5) require this to be set explicitly or they ignore tools entirely. Now sent with every OpenAI-compatible tool-calling request.
- **`reasoning_content` preservation** — thinking models (e.g. Kimi-K2.5) that return `reasoning_content` in assistant messages now have it preserved across agentic loop turns. Without this, multi-turn tool chaining broke after the first turn.
- **Moonshot parameter constraints** — temperature, top_p, and penalty values are automatically overridden to Kimi-K2.5's required fixed values. Temperature field is greyed out in Settings when Moonshot is selected.
- **Non-streaming `stop_reason` detection** — now correctly sets `stop_reason="tool_use"` when tool calls are present regardless of the provider's `finish_reason` value.

### Changed

- **Snap tabs as PartDesign features** — `create_snap_tabs` now creates `PartDesign::AdditiveBox` features inside the lid body instead of a standalone `Part::Feature`. Tabs are individually editable and compatible with fillet, chamfer, pattern, and other PartDesign tools.
- **Better tool success messages** — `create_sketch`, `create_body`, `pad_sketch`, and `pocket_sketch` now include explicit naming hints (e.g., "Use sketch_name='Sketch001' in pad_sketch/pocket_sketch").

## [0.3.0-alpha] - 2026-03-14

Vision routing, image support, user extension tools, and deferred MCP tool loading.

### Added

- **Vision routing** — automatically detect whether the LLM supports vision via a probe image during Test Connection. Vision-capable models receive images inline; non-vision models get images auto-described via an MCP `describe_image` tool (e.g., [llm-vision-mcp](https://github.com/ghbalf/llm-vision-mcp)). When no vision path exists, image controls (Capture, Attach, drag-drop, paste) are disabled. Includes a manual override checkbox in Settings.
- **Image support** — attach viewport screenshots and images to chat messages (Capture button, Attach button, drag-drop, paste)
- **User extension tools** — register custom Python functions (`.py` / `.FCMacro`) as LLM-callable tools. Functions with type hints are auto-discovered from `~/.config/FreeCAD/FreeCADAI/tools/`, validated via AST, and registered into the tool registry. Includes Settings UI for managing tools and optional FreeCAD macro directory scanning.
- **Deferred MCP tool loading** — tool schemas are loaded lazily on first use instead of eagerly on connect, configurable per-server via the `deferred` setting (default: `true`)
- **Tool search** — `MCPClient.search_tools()`, `MCPManager.search_tools()`, and `ToolRegistry.search_tools()` for keyword-based tool discovery across all registered tools
- **Lazy parameter resolution** — `ToolDefinition.lazy_params` callable and `resolve_params()` method for on-demand schema loading
- **Settings UI** — "Deferred tool loading" checkbox in the Add MCP Server dialog; server list shows `(deferred)` / `(disabled)` tags
- **24 new unit tests** for deferred loading, lazy params, tool search, and MCP manager integration

## [0.2.0-alpha] - 2026-02-24

PartDesign-native primitives, patterns, and multi-transform.

### Changed

- **`create_primitive` converted to PartDesign** — creates AdditiveBox, SubtractiveCylinder, etc. inside a Body instead of Part::Box/Part::Cylinder. Supports `operation="additive"|"subtractive"` and `body_name` for adding to existing bodies.
- **`create_wedge` converted to PartDesign** — now uses a loft-based approach instead of Part::Wedge
- **`shell_object` defaults to `reversed=True`** — inward shelling preserves outer dimensions (more intuitive default)
- **`multi_transform` accepts multiple features** — can chain linear pattern + polar pattern + mirror in one operation

### Added

- **`mirror_feature` tool** — mirror a PartDesign feature across XY, XZ, or YZ plane (`PartDesign::Mirrored`)
- **`multi_transform` tool** — chain multiple transformation patterns (linear, polar, mirror) in a single PartDesign::MultiTransform feature
- Integration tests for PartDesign `create_primitive` and `create_wedge`

### Fixed

- LLM stringified-list bug in `shell_object`, `fillet_edges`, `chamfer_edges` — handle `"['Face1']"` strings from some LLMs
- `multi_transform` visibility — ensure intermediate features are hidden after transform
- Added missing tools to system prompt strategy list and stop-when-done instruction

## [0.1.0] - 2026-02-23

Initial alpha release.

### Added

- **Chat interface** with streaming LLM responses in a FreeCAD dock widget
- **Plan / Act modes** — review code before execution or auto-execute
- **Tool calling system** with 21 structured tools:
  - Primitives: `create_primitive`, `create_body`, `create_wedge`
  - Sketching: `create_sketch` (lines, circles, arcs, rectangles, constraints, plane offset)
  - PartDesign: `pad_sketch`, `pocket_sketch`, `revolve_sketch`, `loft_sketches`, `sweep_sketch`
  - Booleans: `boolean_operation` (fuse, cut, common)
  - Transforms: `transform_object`, `scale_object`
  - Edge ops: `fillet_edges`, `chamfer_edges`, `shell_object`
  - Patterns: `linear_pattern`, `polar_pattern`
  - Enclosure helpers: `create_inner_ridge`, `create_snap_tabs`, `create_enclosure_lid`
  - Cross-sections: `section_object`
  - Query: `measure`, `get_document_state`
  - Utility: `modify_property`, `export_model`, `execute_code`, `undo`
  - Interactive: `select_geometry` (viewport picking)
  - View: `capture_viewport`, `set_view`, `zoom_object`
- **Skills system** — reusable instruction sets invoked via `/command`:
  - `/enclosure` — parametric electronics enclosure with snap-fit lid
  - `/gear` — involute spur gear from module and tooth count
  - `/fastener-hole` — clearance, counterbore, countersink holes (ISO dims)
  - `/thread-insert` — heat-set thread insert holes (M2-M5)
  - `/lattice` — grid, honeycomb, diagonal infill patterns
  - `/skill-creator` — create new skills interactively
- **Multiple LLM providers** — Anthropic, OpenAI, Ollama, Gemini, OpenRouter, custom endpoints
- **Thinking mode** — Off / On / Extended reasoning for complex tasks
- **Context compacting** — auto-summarize older messages near context limits
- **Session resume** — auto-save conversations, load from last 20 sessions
- **AGENTS.md support** — project-level instructions with includes and variable substitution
- **MCP support** — STDIO transport, JSON-RPC 2.0, client + server, tool namespacing
- **German translation** (i18n via Qt .ts/.qm)
- **Safety features:**
  - Undo transactions wrapping all tool operations
  - Subprocess sandbox for code execution
  - Sketcher constraint validation to prevent segfaults
  - Pocket auto-direction detection
  - Auto-hide sketches after pad/pocket
- **Test suite** — 243 unit tests
- **Dual licensing** — LGPL-2.1 (code) + CC0-1.0 (icons)
- **Zero external dependencies** — uses only Python stdlib

[0.3.0-alpha]: https://github.com/ghbalf/freecad-ai/releases/tag/v0.3.0-alpha
[0.2.0-alpha]: https://github.com/ghbalf/freecad-ai/releases/tag/v0.2.0-alpha
[0.1.0]: https://github.com/ghbalf/freecad-ai/releases/tag/v0.1.0

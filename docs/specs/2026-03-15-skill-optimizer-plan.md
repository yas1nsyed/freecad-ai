# Skill Optimizer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automated skill optimization loop that iteratively improves SKILL.md files by running them against test cases, scoring results, and using the LLM to modify instructions.

**Architecture:** A `/optimize-skill` skill shows a config dialog, then injects an optimizer prompt. The LLM calls an `optimize_iteration` tool that runs a headless agentic loop (with main-thread tool dispatch), collects metrics, scores the result, and manages version history. The LLM analyzes failures and modifies the SKILL.md, repeating until convergence.

**Tech Stack:** Python 3.11, PySide2, FreeCAD API, zero external dependencies.

**Spec:** `docs/specs/2026-03-15-skill-optimizer-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `freecad_ai/tools/executor_utils.py` | **NEW** -- `MainThreadToolExecutor`: shared QObject that dispatches tool calls to the main thread via signal/mutex/QWaitCondition |
| `freecad_ai/extensions/skill_evaluator.py` | **NEW** -- `EvalResult`, `OptimizationState`, `SkillEvaluator`: run skills headless, collect metrics, compute scores, manage version history |
| `freecad_ai/tools/optimize_tools.py` | **NEW** -- `optimize_iteration` tool definition and handler, `register_optimize_tools()` |
| `freecad_ai/ui/optimize_dialog.py` | **NEW** -- `OptimizeSkillDialog`: PySide2 config dialog |
| `skills/optimize-skill/SKILL.md` | **NEW** -- skill description |
| `skills/optimize-skill/handler.py` | **NEW** -- dialog launcher, inject_prompt builder |
| `freecad_ai/tools/setup.py` | **MODIFY** -- add `extra_tools` parameter to `create_default_registry()` |
| `freecad_ai/ui/chat_widget.py` | **MODIFY** -- refactor `_LLMWorker` to use `MainThreadToolExecutor` |
| `freecad_ai/core/conversation.py` | **MODIFY** -- add `compaction_enabled` flag |
| `tests/unit/test_skill_evaluator.py` | **NEW** -- tests for scoring, state management, headless loop |
| `tests/unit/test_optimize_tools.py` | **NEW** -- tests for optimize_iteration tool |
| `tests/unit/test_executor_utils.py` | **NEW** -- tests for MainThreadToolExecutor |

---

## Chunk 1: Foundation -- MainThreadToolExecutor and Conversation Flag

### Task 1: Add `compaction_enabled` flag to Conversation

**Files:**
- Modify: `freecad_ai/core/conversation.py:314-316`
- Test: `tests/unit/test_conversation.py`

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_conversation.py`, add:

```python
class TestCompactionEnabled:
    def test_compaction_enabled_default_true(self):
        from freecad_ai.core.conversation import Conversation
        conv = Conversation()
        assert conv.compaction_enabled is True

    def test_compaction_disabled_prevents_needs_compaction(self):
        from freecad_ai.core.conversation import Conversation
        conv = Conversation()
        for i in range(20):
            conv.add_user_message("x" * 5000)
            conv.add_assistant_message("y" * 5000)
        assert conv.needs_compaction() is True
        conv.compaction_enabled = False
        assert conv.needs_compaction() is False

    def test_compaction_reenabled(self):
        from freecad_ai.core.conversation import Conversation
        conv = Conversation()
        conv.compaction_enabled = False
        for i in range(20):
            conv.add_user_message("x" * 5000)
            conv.add_assistant_message("y" * 5000)
        assert conv.needs_compaction() is False
        conv.compaction_enabled = True
        assert conv.needs_compaction() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_conversation.py::TestCompactionEnabled -v`
Expected: FAIL -- `compaction_enabled` attribute does not exist

- [ ] **Step 3: Implement compaction_enabled**

In `freecad_ai/core/conversation.py`, add to `__init__`:

```python
self.compaction_enabled = True
```

Modify `needs_compaction`:

```python
def needs_compaction(self, threshold_tokens: int = 20000) -> bool:
    if not self.compaction_enabled:
        return False
    return self.estimated_tokens() > threshold_tokens and len(self.messages) > 6
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_conversation.py::TestCompactionEnabled -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/unit/ -q`
Expected: All tests pass (360+)

- [ ] **Step 6: Commit**

```
git add freecad_ai/core/conversation.py tests/unit/test_conversation.py
git commit -m "feat: add compaction_enabled flag to Conversation"
```

---

### Task 2: Create MainThreadToolExecutor

**Files:**
- Create: `freecad_ai/tools/executor_utils.py`
- Test: `tests/unit/test_executor_utils.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_executor_utils.py`:

```python
"""Tests for MainThreadToolExecutor."""
from unittest.mock import MagicMock
from freecad_ai.tools.executor_utils import MainThreadToolExecutor
from freecad_ai.tools.registry import ToolResult


class TestMainThreadToolExecutor:
    def test_init(self):
        executor = MainThreadToolExecutor()
        assert executor._registry is None

    def test_set_registry(self):
        executor = MainThreadToolExecutor()
        mock_registry = MagicMock()
        executor.set_registry(mock_registry)
        assert executor._registry is mock_registry

    def test_do_execute_success(self):
        executor = MainThreadToolExecutor()
        mock_registry = MagicMock()
        expected = ToolResult(success=True, output="ok")
        mock_registry.execute.return_value = expected
        executor.set_registry(mock_registry)

        holder = {"result": None}
        executor._do_execute_sync("test_tool", {"arg": "val"}, holder)
        assert holder["result"] is expected
        mock_registry.execute.assert_called_once_with("test_tool", {"arg": "val"})

    def test_do_execute_exception_returns_error_result(self):
        executor = MainThreadToolExecutor()
        mock_registry = MagicMock()
        mock_registry.execute.side_effect = RuntimeError("FreeCAD crashed")
        executor.set_registry(mock_registry)

        holder = {"result": None}
        executor._do_execute_sync("bad_tool", {}, holder)
        assert holder["result"].success is False
        assert "FreeCAD crashed" in holder["result"].error

    def test_execute_direct_when_no_qt(self):
        """Without Qt, execute() runs directly on calling thread."""
        executor = MainThreadToolExecutor()
        mock_registry = MagicMock()
        expected = ToolResult(success=True, output="ok")
        mock_registry.execute.return_value = expected
        executor.set_registry(mock_registry)

        result = executor.execute("tool", {"x": 1})
        assert result is expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_executor_utils.py -v`
Expected: FAIL -- module does not exist

- [ ] **Step 3: Implement MainThreadToolExecutor**

Create `freecad_ai/tools/executor_utils.py`:

```python
"""Main-thread tool execution dispatcher.

FreeCAD's C++ layer is not thread-safe -- tool calls that use App.ActiveDocument
or FreeCADGui must run on the main (GUI) thread. This module provides a shared
utility for dispatching tool calls from worker threads to the main thread.

Used by both _LLMWorker (chat agentic loop) and SkillEvaluator (headless
evaluation runs).
"""
import logging

logger = logging.getLogger(__name__)

try:
    from ..ui.compat import QtCore, Signal
    QObject = QtCore.QObject
    QMutex = QtCore.QMutex
    QWaitCondition = QtCore.QWaitCondition
    Qt = QtCore.Qt
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

from .registry import ToolResult


class MainThreadToolExecutor:
    """Dispatches tool calls to the main thread and waits for results.

    When Qt is available, uses Signal/QWaitCondition for cross-thread dispatch.
    Without Qt (unit tests), executes directly on the calling thread.
    """

    def __init__(self):
        self._registry = None

    def set_registry(self, registry):
        self._registry = registry

    def execute(self, tool_name: str, args: dict) -> ToolResult:
        """Execute a tool. Thread-safe -- dispatches to main thread if Qt available."""
        holder = {"result": None}
        self._do_execute_sync(tool_name, args, holder)
        return holder["result"]

    def _do_execute_sync(self, tool_name, args, holder):
        """Execute tool and store result. Always succeeds (no exceptions leak)."""
        try:
            holder["result"] = self._registry.execute(tool_name, args)
        except Exception as e:
            logger.error("Tool execution failed: %s -- %s", tool_name, e)
            holder["result"] = ToolResult(success=False, output="", error=str(e))


if _HAS_QT:
    class QtMainThreadToolExecutor(MainThreadToolExecutor, QObject):
        """Qt-aware version that dispatches tool calls to the main thread.

        Call execute() from any thread -- it blocks until the main thread
        completes execution and returns the result.
        """
        _execute_signal = Signal(str, str, object)  # tool_name, args_json, holder

        def __init__(self):
            QObject.__init__(self)
            MainThreadToolExecutor.__init__(self)
            self._execute_signal.connect(self._on_execute, Qt.QueuedConnection)
            self._mutex = QMutex()
            self._condition = QWaitCondition()

        def execute(self, tool_name: str, args: dict) -> ToolResult:
            """Call from any thread. Blocks until main thread completes.

            If already on the main thread (e.g., called from optimize_iteration
            handler), executes directly to avoid deadlock.
            """
            import json
            app = QtCore.QCoreApplication.instance()
            if app and QtCore.QThread.currentThread() == app.thread():
                # Already on main thread -- execute directly (avoids deadlock)
                holder = {"result": None}
                self._do_execute_sync(tool_name, args, holder)
                return holder["result"]
            # Cross-thread dispatch
            holder = {"result": None}
            args_json = json.dumps(args)
            self._mutex.lock()
            self._execute_signal.emit(tool_name, args_json, holder)
            self._condition.wait(self._mutex)
            self._mutex.unlock()
            return holder["result"]

        def _on_execute(self, tool_name, args_json, holder):
            """Runs on main thread via queued signal connection."""
            import json
            args = json.loads(args_json)
            try:
                self._do_execute_sync(tool_name, args, holder)
            finally:
                self._mutex.lock()
                self._condition.wakeAll()
                self._mutex.unlock()
```

Note: `str` (JSON) used instead of `dict` for signal parameter because PySide2's `Signal(dict)` can be unreliable with `QueuedConnection`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_executor_utils.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/unit/ -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```
git add freecad_ai/tools/executor_utils.py tests/unit/test_executor_utils.py
git commit -m "feat: add MainThreadToolExecutor for cross-thread tool dispatch"
```

---

### Task 3: Add `extra_tools` parameter to `create_default_registry`

**Files:**
- Modify: `freecad_ai/tools/setup.py:13-53`
- Test: `tests/unit/test_tools.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_tools.py`:

```python
class TestCreateDefaultRegistryExtraTools:
    def test_extra_tools_empty_by_default(self):
        from freecad_ai.tools.setup import create_default_registry
        registry = create_default_registry(include_mcp=False)
        assert registry is not None

    def test_extra_tools_registered(self):
        from freecad_ai.tools.setup import create_default_registry
        from freecad_ai.tools.registry import ToolDefinition, ToolParam, ToolResult
        extra = ToolDefinition(
            name="test_extra_tool",
            description="A test tool",
            parameters=[],
            handler=lambda: ToolResult(success=True, output="ok"),
        )
        registry = create_default_registry(include_mcp=False, extra_tools=[extra])
        tool = registry.get("test_extra_tool")
        assert tool is not None
        assert tool.name == "test_extra_tool"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tools.py::TestCreateDefaultRegistryExtraTools -v`
Expected: FAIL -- `extra_tools` parameter not accepted

- [ ] **Step 3: Implement extra_tools parameter**

In `freecad_ai/tools/setup.py`, modify signature:

```python
def create_default_registry(include_mcp: bool = True,
                            extra_tools: list | None = None) -> ToolRegistry:
```

At the end of the function, before `return registry`:

```python
    # Register extra tools (e.g., optimize_iteration during optimization)
    if extra_tools:
        for tool in extra_tools:
            registry.register(tool)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tools.py::TestCreateDefaultRegistryExtraTools -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/unit/ -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```
git add freecad_ai/tools/setup.py tests/unit/test_tools.py
git commit -m "feat: add extra_tools parameter to create_default_registry"
```

---

## Chunk 2: Evaluation Engine -- EvalResult, OptimizationState, SkillEvaluator

### Task 4: Create EvalResult and OptimizationState

**Files:**
- Create: `freecad_ai/extensions/skill_evaluator.py`
- Test: `tests/unit/test_skill_evaluator.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_skill_evaluator.py`:

```python
"""Tests for skill evaluation framework."""
import json
import os
from freecad_ai.extensions.skill_evaluator import EvalResult, OptimizationState


class TestEvalResult:
    def test_defaults(self):
        r = EvalResult(test_case="test")
        assert r.tool_calls == 0
        assert r.errors == 0
        assert r.retries == 0
        assert r.completed is False
        assert r.error_messages == []
        assert r.measurements == {}
        assert r.visual_score is None
        assert r.run_scores == []

    def test_with_values(self):
        r = EvalResult(
            test_case="100x60x40",
            tool_calls=12,
            errors=2,
            completed=True,
            error_messages=["Sketch not found"],
        )
        assert r.tool_calls == 12
        assert r.errors == 2
        assert len(r.error_messages) == 1


class TestOptimizationState:
    def test_init_creates_directory(self, tmp_path):
        state = OptimizationState("test-skill", base_dir=str(tmp_path))
        assert os.path.isdir(tmp_path / "test-skill" / ".optimize")

    def test_save_and_get_original(self, tmp_path):
        state = OptimizationState("test-skill", base_dir=str(tmp_path))
        state.save_original("# Original content")
        orig_path = tmp_path / "test-skill" / "SKILL.md.original"
        assert orig_path.read_text() == "# Original content"

    def test_save_original_not_overwritten(self, tmp_path):
        state = OptimizationState("test-skill", base_dir=str(tmp_path))
        state.save_original("# First")
        state.save_original("# Second")
        orig_path = tmp_path / "test-skill" / "SKILL.md.original"
        assert orig_path.read_text() == "# First"

    def test_save_version(self, tmp_path):
        state = OptimizationState("test-skill", base_dir=str(tmp_path))
        state.save_version(1, "# V1 content", score=0.65, kept=True)
        v1 = tmp_path / "test-skill" / ".optimize" / "v1.md"
        assert v1.read_text() == "# V1 content"

    def test_get_best_initial(self, tmp_path):
        state = OptimizationState("test-skill", base_dir=str(tmp_path))
        content, score = state.get_best()
        assert content == ""
        assert score == 0.0

    def test_get_best_after_saves(self, tmp_path):
        state = OptimizationState("test-skill", base_dir=str(tmp_path))
        state.save_version(1, "# V1", score=0.65, kept=True)
        state.save_version(2, "# V2", score=0.82, kept=True)
        state.save_version(3, "# V3", score=0.71, kept=False)
        content, score = state.get_best()
        assert content == "# V2"
        assert score == 0.82

    def test_history_persists(self, tmp_path):
        state = OptimizationState("test-skill", base_dir=str(tmp_path))
        state.save_version(1, "# V1", score=0.65, kept=True)
        state.save_version(2, "# V2", score=0.82, kept=True)
        history = state.get_history()
        assert len(history) == 2
        assert history[0]["iteration"] == 1
        assert history[1]["score"] == 0.82

    def test_history_reload(self, tmp_path):
        state1 = OptimizationState("test-skill", base_dir=str(tmp_path))
        state1.save_version(1, "# V1", score=0.65, kept=True)
        state2 = OptimizationState("test-skill", base_dir=str(tmp_path))
        assert len(state2.get_history()) == 1

    def test_restore_best(self, tmp_path):
        state = OptimizationState("test-skill", base_dir=str(tmp_path))
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text("# Current")
        state.save_version(1, "# V1 best", score=0.90, kept=True)
        state.restore_best()
        assert (skill_dir / "SKILL.md").read_text() == "# V1 best"

    def test_is_config_stale(self, tmp_path):
        state = OptimizationState("test-skill", base_dir=str(tmp_path))
        config = {"model": "gpt-4o", "provider": "openai"}
        state.save_version(1, "# V1", score=0.65, kept=True, config=config)
        assert state.is_config_stale(config) is False
        assert state.is_config_stale({"model": "llama3", "provider": "ollama"}) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_skill_evaluator.py -v`
Expected: FAIL -- module does not exist

- [ ] **Step 3: Implement EvalResult and OptimizationState**

Create `freecad_ai/extensions/skill_evaluator.py` with the `EvalResult` dataclass and `OptimizationState` class as specified in the design spec. Key implementation details:

- `EvalResult`: dataclass with fields for test_case, tool_calls, errors, retries, error_messages, measurements, completed, visual_score, visual_assessment, run_scores
- `OptimizationState.__init__`: creates `.optimize/` directory, loads `history.json` if exists
- `save_original`: writes `SKILL.md.original`, skips if already exists
- `save_version`: writes `vN.md`, appends to history with timestamp and optional config
- `get_best`: scans history for highest-scoring kept entry, reads its version file
- `restore_best`: writes best version content to `SKILL.md`
- `is_config_stale`: compares model/provider in last history entry with current config

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_skill_evaluator.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```
git add freecad_ai/extensions/skill_evaluator.py tests/unit/test_skill_evaluator.py
git commit -m "feat: add EvalResult and OptimizationState for skill optimizer"
```

---

### Task 5: Add scoring system

**Files:**
- Modify: `freecad_ai/extensions/skill_evaluator.py`
- Test: `tests/unit/test_skill_evaluator.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_skill_evaluator.py`:

```python
from freecad_ai.extensions.skill_evaluator import compute_composite_score


class TestScoring:
    def test_perfect_score(self):
        results = [EvalResult(
            test_case="test", tool_calls=10, errors=0, retries=0, completed=True,
        )]
        config = {
            "metrics": ["completion", "error_rate", "retries", "efficiency"],
            "weights": {"completion": 0.30, "error_rate": 0.25, "retries": 0.10, "efficiency": 0.10},
            "budget": 30,
        }
        score = compute_composite_score(results, config)
        assert score > 0.9

    def test_zero_score_not_completed(self):
        results = [EvalResult(test_case="test", completed=False, tool_calls=30)]
        config = {"metrics": ["completion"], "weights": {"completion": 1.0}, "budget": 30}
        score = compute_composite_score(results, config)
        assert score == 0.0

    def test_error_rate_reduces_score(self):
        results = [EvalResult(test_case="test", tool_calls=10, errors=5, completed=True)]
        config = {"metrics": ["error_rate"], "weights": {"error_rate": 1.0}, "budget": 30}
        score = compute_composite_score(results, config)
        assert abs(score - 0.5) < 0.01

    def test_geometric_correctness(self):
        results = [EvalResult(
            test_case="test", completed=True, tool_calls=10,
            measurements={"bbox": [100, 60, 40]},
        )]
        config = {
            "metrics": ["correctness"], "weights": {"correctness": 1.0}, "budget": 30,
            "test_cases": [{"args": "test", "expected_bbox": [100, 60, 40]}],
        }
        assert compute_composite_score(results, config) == 1.0

    def test_geometric_correctness_partial(self):
        results = [EvalResult(
            test_case="test", completed=True, tool_calls=10,
            measurements={"bbox": [110, 60, 40]},
        )]
        config = {
            "metrics": ["correctness"], "weights": {"correctness": 1.0}, "budget": 30,
            "test_cases": [{"args": "test", "expected_bbox": [100, 60, 40]}],
        }
        score = compute_composite_score(results, config)
        assert 0.9 < score < 1.0

    def test_missing_metric_weight_redistributed(self):
        results = [EvalResult(test_case="test", completed=True, tool_calls=10, errors=0)]
        config = {
            "metrics": ["completion", "correctness"],
            "weights": {"completion": 0.5, "correctness": 0.5},
            "budget": 30, "test_cases": [{"args": "test"}],
        }
        assert compute_composite_score(results, config) == 1.0

    def test_multiple_test_cases_averaged(self):
        results = [
            EvalResult(test_case="a", completed=True, tool_calls=10, errors=0),
            EvalResult(test_case="b", completed=False, tool_calls=30, errors=10),
        ]
        config = {"metrics": ["completion"], "weights": {"completion": 1.0}, "budget": 30}
        score = compute_composite_score(results, config)
        assert abs(score - 0.5) < 0.01
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_skill_evaluator.py::TestScoring -v`
Expected: FAIL -- `compute_composite_score` does not exist

- [ ] **Step 3: Implement scoring**

Add `DEFAULT_WEIGHTS`, `_score_single()`, and `compute_composite_score()` to `skill_evaluator.py` as specified in the design spec.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_skill_evaluator.py::TestScoring -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```
git add freecad_ai/extensions/skill_evaluator.py tests/unit/test_skill_evaluator.py
git commit -m "feat: add composite scoring system for skill evaluation"
```

---

### Task 6: Add headless agentic loop to SkillEvaluator

**Files:**
- Modify: `freecad_ai/extensions/skill_evaluator.py`
- Test: `tests/unit/test_skill_evaluator.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_skill_evaluator.py`:

```python
from unittest.mock import MagicMock
from freecad_ai.extensions.skill_evaluator import SkillEvaluator


class TestSkillEvaluator:
    def _make_config(self, **overrides):
        config = {
            "metrics": ["completion", "error_rate", "efficiency"],
            "weights": {"completion": 0.4, "error_rate": 0.4, "efficiency": 0.2},
            "budget": 10, "timeout": 60,
            "test_cases": [{"args": "50x30x20mm"}],
        }
        config.update(overrides)
        return config

    def test_init(self):
        evaluator = SkillEvaluator(self._make_config(), tool_executor=MagicMock())
        assert evaluator._config is not None

    def test_run_skill_headless_completes(self):
        """LLM returns no tool calls -- skill completes immediately."""
        evaluator = SkillEvaluator(self._make_config(), tool_executor=MagicMock())
        mock_client = MagicMock()
        resp = MagicMock()
        resp.tool_calls = []
        resp.text = "Done"
        mock_client.send_with_tools.return_value = resp
        result = evaluator._run_skill_headless(
            "# Test", "50x30x20mm", mock_client, [], "system")
        assert result.completed is True
        assert result.tool_calls == 0

    def test_run_skill_headless_counts_tool_calls(self):
        """LLM makes one tool call then stops."""
        from freecad_ai.tools.registry import ToolResult
        executor = MagicMock()
        executor.execute.return_value = ToolResult(success=True, output="Created box")
        evaluator = SkillEvaluator(self._make_config(), tool_executor=executor)
        mock_client = MagicMock()

        call1 = MagicMock()
        tc = MagicMock(); tc.name = "create_primitive"; tc.id = "tc1"; tc.arguments = {}
        call1.tool_calls = [tc]; call1.text = ""
        call2 = MagicMock(); call2.tool_calls = []; call2.text = "Done"
        mock_client.send_with_tools.side_effect = [call1, call2]

        result = evaluator._run_skill_headless(
            "# Test", "50x30x20mm", mock_client, [], "system")
        assert result.completed is True
        assert result.tool_calls == 1
        assert result.errors == 0

    def test_run_skill_headless_counts_errors(self):
        """Failed tool calls increment error count."""
        from freecad_ai.tools.registry import ToolResult
        executor = MagicMock()
        executor.execute.return_value = ToolResult(
            success=False, error="Sketch not found", output="")
        evaluator = SkillEvaluator(self._make_config(), tool_executor=executor)
        mock_client = MagicMock()

        call1 = MagicMock()
        tc = MagicMock(); tc.name = "pad_sketch"; tc.id = "tc1"; tc.arguments = {}
        call1.tool_calls = [tc]; call1.text = ""
        call2 = MagicMock(); call2.tool_calls = []; call2.text = "Failed"
        mock_client.send_with_tools.side_effect = [call1, call2]

        result = evaluator._run_skill_headless(
            "# Test", "50x30x20mm", mock_client, [], "system")
        assert result.errors == 1
        assert "Sketch not found" in result.error_messages

    def test_run_skill_headless_budget_exceeded(self):
        """Loop stops at budget limit."""
        from freecad_ai.tools.registry import ToolResult
        executor = MagicMock()
        executor.execute.return_value = ToolResult(success=True, output="ok")
        evaluator = SkillEvaluator(self._make_config(budget=2), tool_executor=executor)
        mock_client = MagicMock()

        def make_response(*a, **kw):
            r = MagicMock()
            tc = MagicMock(); tc.name = "tool"; tc.id = f"tc{make_response.n}"; tc.arguments = {}
            r.tool_calls = [tc]; r.text = ""
            make_response.n += 1; return r
        make_response.n = 0
        mock_client.send_with_tools.side_effect = make_response

        result = evaluator._run_skill_headless(
            "# Test", "test", mock_client, [], "system")
        assert result.completed is False
        assert result.tool_calls == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_skill_evaluator.py::TestSkillEvaluator -v`
Expected: FAIL -- `SkillEvaluator` does not exist

- [ ] **Step 3: Implement SkillEvaluator**

Add `SkillEvaluator` class to `skill_evaluator.py` with:
- `__init__(config, tool_executor)`: stores config and executor, sets `_cancelled = False`
- `cancel()`: sets `_cancelled = True`
- `evaluate(skill_name, skill_content, test_cases, runs_per_test)`: creates fresh LLMClient, runs `_run_skill_headless` for each test case x runs, averages results
- `_run_skill_headless(skill_content, test_args, client, tools_schema, system_prompt)`: the core loop -- creates Conversation (with compaction disabled), injects skill, loops: send_with_tools -> process tool calls via executor -> repeat until done/budget/timeout
- `_average_results(run_results, test_case)`: averages metrics across runs, computes per-run scores for variance

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_skill_evaluator.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/unit/ -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```
git add freecad_ai/extensions/skill_evaluator.py tests/unit/test_skill_evaluator.py
git commit -m "feat: add SkillEvaluator with headless agentic loop"
```

---

## Chunk 3: Tool and Skill Entry Point

### Task 7: Create optimize_iteration tool

**Files:**
- Create: `freecad_ai/tools/optimize_tools.py`
- Test: `tests/unit/test_optimize_tools.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_optimize_tools.py`:

```python
"""Tests for optimize_iteration tool."""
from freecad_ai.tools.optimize_tools import (
    get_optimize_iteration_tool, OPTIMIZATION_PROMPT_TEMPLATE, STRATEGY_INSTRUCTIONS,
)
from freecad_ai.tools.registry import ToolDefinition


class TestOptimizeIterationTool:
    def test_tool_definition(self):
        tool = get_optimize_iteration_tool()
        assert isinstance(tool, ToolDefinition)
        assert tool.name == "optimize_iteration"
        assert len(tool.parameters) >= 3

    def test_prompt_templates_exist(self):
        assert "SKILL.md" in OPTIMIZATION_PROMPT_TEMPLATE
        assert "conservative" in STRATEGY_INSTRUCTIONS
        assert "balanced" in STRATEGY_INSTRUCTIONS
        assert "aggressive" in STRATEGY_INSTRUCTIONS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_optimize_tools.py -v`
Expected: FAIL -- module does not exist

- [ ] **Step 3: Implement optimize_tools.py**

Create `freecad_ai/tools/optimize_tools.py` with:
- `get_optimize_iteration_tool()`: returns `ToolDefinition` with name, description, parameters (skill_name, skill_content, test_cases, runs_per_test), handler
- `_handle_optimize_iteration()`: handler function that runs SkillEvaluator, scores results, manages keep/discard via OptimizationState
- `start_optimization(state, config)`: initializes global session state
- `stop_optimization()`: clears global session state
- `OPTIMIZATION_PROMPT_TEMPLATE`: the inject_prompt template
- `STRATEGY_INSTRUCTIONS`: dict of strategy-specific instruction strings

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_optimize_tools.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```
git add freecad_ai/tools/optimize_tools.py tests/unit/test_optimize_tools.py
git commit -m "feat: add optimize_iteration tool with scoring and version management"
```

---

### Task 8: Create OptimizeSkillDialog

**Files:**
- Create: `freecad_ai/ui/optimize_dialog.py`

- [ ] **Step 1: Create the dialog**

Create `freecad_ai/ui/optimize_dialog.py` with `OptimizeSkillDialog` class:
- Skill dropdown (QComboBox populated from SkillsRegistry)
- Test cases list (QListWidget + QLineEdit + Add/Remove)
- Settings: iterations (QSpinBox 1-50, default 10), runs per test (1-5, default 2), strategy (QComboBox)
- Metrics checkboxes: completion, error rate, geometric checks, efficiency, visual similarity
- Visual similarity enables reference image file picker
- Advanced section (collapsed): tool call budget, run timeout, keep tolerance
- Start button validates (at least 1 test case, at least 2 metrics)
- `get_config()` method returns structured dict
- `result_config` property for access after dialog closes

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/unit/ -q`
Expected: All tests pass (no new tests for UI, verify no import errors)

- [ ] **Step 3: Commit**

```
git add freecad_ai/ui/optimize_dialog.py
git commit -m "feat: add OptimizeSkillDialog for skill optimizer configuration"
```

---

### Task 9: Create `/optimize-skill` skill with handler

**Files:**
- Create: `skills/optimize-skill/SKILL.md`
- Create: `skills/optimize-skill/handler.py`

- [ ] **Step 1: Create SKILL.md**

Create `skills/optimize-skill/SKILL.md` with YAML frontmatter (name, description) and usage instructions.

- [ ] **Step 2: Create handler.py**

Create `skills/optimize-skill/handler.py` with `execute(args)` function:
- Discover available skills via SkillsRegistry
- Show OptimizeSkillDialog (pre-select if args provided)
- On Start: load current SKILL.md, save original, check for stale config
- Initialize optimization session via `start_optimization()`
- Build inject_prompt from OPTIMIZATION_PROMPT_TEMPLATE
- Return `{"inject_prompt": prompt}`

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/unit/ -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```
git add skills/optimize-skill/SKILL.md skills/optimize-skill/handler.py
git commit -m "feat: add /optimize-skill skill with dialog handler"
```

---

## Chunk 4: Integration -- Wire Everything Together

### Task 10: Refactor chat_widget.py to use MainThreadToolExecutor

**Files:**
- Modify: `freecad_ai/ui/chat_widget.py`

Pure refactor -- behavior must be identical.

- [ ] **Step 1: Run full test suite to establish baseline**

Run: `pytest tests/unit/ -q`
Expected: All tests pass (note the count)

- [ ] **Step 2: Refactor _LLMWorker**

In `freecad_ai/ui/chat_widget.py`:
1. Import `QtMainThreadToolExecutor` from `executor_utils`
2. Create shared executor in `ChatDockWidget.__init__`
3. In `_continue_send`, set executor's registry
4. In `_LLMWorker`, replace `_execute_tool_on_main_thread` with executor's `execute()`
5. Remove old `tool_exec_requested` signal and `_on_tool_exec` slot

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/unit/ -q`
Expected: All tests pass (same count as baseline)

- [ ] **Step 4: Commit**

```
git add freecad_ai/ui/chat_widget.py
git commit -m "refactor: use MainThreadToolExecutor in _LLMWorker"
```

---

### Task 11: Wire optimize_iteration into the chat flow

**Files:**
- Modify: `freecad_ai/ui/chat_widget.py`

- [ ] **Step 1: Add optimization flag and extra_tools logic**

In `ChatDockWidget.__init__`: add `self._optimization_active = False`

In `_continue_send`: build `extra_tools` list when optimization is active, pass to `create_default_registry(extra_tools=extra)`

In `_handle_skill_command`: set `self._optimization_active = True` when `optimize-skill` is invoked

In `_new_chat`: call `stop_optimization()` and reset flag

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/unit/ -q`
Expected: All tests pass

- [ ] **Step 3: Test manually in FreeCAD**

1. Start FreeCAD with the workbench
2. Type `/optimize-skill`
3. Verify dialog opens with skill list
4. Add a test case, click Start
5. Verify optimization loop runs (LLM calls optimize_iteration)

- [ ] **Step 4: Commit**

```
git add freecad_ai/ui/chat_widget.py
git commit -m "feat: wire optimize_iteration into chat flow with conditional registration"
```

---

### Task 12: Documentation

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md`

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/unit/ -v`
Expected: All tests pass

- [ ] **Step 2: Update CHANGELOG.md**

Add under `[Unreleased]`:

```markdown
- **Skill optimizer** -- `/optimize-skill` command that iteratively improves SKILL.md files by running test cases, scoring results (completion, errors, geometric correctness, efficiency, visual similarity), and using the LLM to modify instructions. Includes PySide2 configuration dialog, version history with original backup, and three optimization strategies (conservative, balanced, aggressive). Inspired by [autoresearch](https://github.com/karpathy/autoresearch).
```

- [ ] **Step 3: Update README.md**

Add to features list:

```markdown
- **Skill optimizer** -- automatically improve skill instructions via iterative test-evaluate-modify loop (`/optimize-skill`)
```

- [ ] **Step 4: Commit**

```
git add CHANGELOG.md README.md
git commit -m "docs: add skill optimizer to changelog and readme"
```

---

## Summary

| Chunk | Tasks | What it delivers |
|-------|-------|-----------------|
| **1: Foundation** | 1--3 | `compaction_enabled`, `MainThreadToolExecutor`, `extra_tools` param |
| **2: Evaluation** | 4--6 | `EvalResult`, `OptimizationState`, `SkillEvaluator` with headless loop and scoring |
| **3: Tool and Skill** | 7--9 | `optimize_iteration` tool, `OptimizeSkillDialog`, `/optimize-skill` handler |
| **4: Integration** | 10--12 | Refactor chat_widget, wire everything together, docs |

Total: 12 tasks across 4 chunks. Each chunk produces testable, committable code.

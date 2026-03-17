# Geometry Validation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add declarative geometry validation to the skill optimizer so it can measure whether generated geometry is actually correct, not just whether the LLM completed without errors.

**Architecture:** A `VALIDATION.md` file per skill declares expected geometry properties (bbox, volume, solid count, etc.) using safe arithmetic expressions. A generic validation engine parses these rules, evaluates them against the FreeCAD document after skill execution, and feeds the pass/fail ratio into the optimizer's correctness metric. A `report_skill_params` tool lets the LLM report which parameters it used, enabling validation during normal `--validate` use.

**Tech Stack:** Python 3.11, FreeCAD API (Shape, BoundBox, Volume, Solids), Python `ast` module for safe expression parsing, PySide2 for dialog changes.

**Spec:** `docs/specs/2026-03-17-geometry-validation-design.md`

---

## Chunk 1: Core Validation Engine

### Task 1: Safe Expression Evaluator

**Files:**
- Create: `freecad_ai/extensions/skill_validator.py`
- Create: `tests/unit/test_skill_validator.py`

- [ ] **Step 1: Write failing tests for expression evaluator**

Create `tests/unit/test_skill_validator.py` with `TestSafeEval` class testing:
- Simple arithmetic (`2 + 3`)
- Variable substitution (`L * W * H`)
- Complex expressions (`L*W*H - (L-2*T)*(W-2*T)*(H-T)`)
- Power operator (`3**2`)
- `pi` constant (`pi * R**2`)
- Functions: `sqrt(16)`, `abs(-5)`, `min(3,7)`, `max(3,7)`
- Division, modulo, nested parentheses
- Rejection of: attribute access, imports, unknown functions, unknown variables
- Empty expression

All tests import `safe_arithmetic` from `freecad_ai.extensions.skill_validator`.

NOTE: The function is named `safe_arithmetic` (not `safe_eval`) to make clear it does NOT use Python's dangerous built-in `eval()`. It uses `ast.parse()` + a custom `NodeVisitor` to walk the syntax tree safely.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/alf/Projects/programming/misc/freecad-ai && .venv/bin/pytest tests/unit/test_skill_validator.py -v`
Expected: FAIL with `ImportError: cannot import name 'safe_arithmetic'`

- [ ] **Step 3: Implement safe expression evaluator**

Create `freecad_ai/extensions/skill_validator.py` with:

```python
"""Skill geometry validation engine.

Parses VALIDATION.md files, evaluates arithmetic expressions safely
via ast (no dangerous code execution), and checks geometry properties
against the FreeCAD document.
"""
import ast
import math
import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_SAFE_FUNCTIONS = {"sqrt": math.sqrt, "abs": abs, "min": min, "max": max}
_SAFE_CONSTANTS = {"pi": math.pi}


class _ExprEvaluator(ast.NodeVisitor):
    """Walk an AST and compute arithmetic. No code execution."""

    def __init__(self, variables: dict):
        self._vars = variables

    def visit_Expression(self, node):
        return self.visit(node.body)

    def visit_Constant(self, node):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError(f"Non-numeric constant not allowed: {node.value!r}")

    def visit_Num(self, node):
        return float(node.n)

    def visit_Name(self, node):
        name = node.id
        if name in self._vars:
            return float(self._vars[name])
        if name in _SAFE_CONSTANTS:
            return _SAFE_CONSTANTS[name]
        raise ValueError(f"Unknown variable: '{name}'")

    def visit_BinOp(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        ops = {
            ast.Add: lambda a, b: a + b,
            ast.Sub: lambda a, b: a - b,
            ast.Mult: lambda a, b: a * b,
            ast.Div: lambda a, b: a / b if b != 0 else (_ for _ in ()).throw(ValueError("Division by zero")),
            ast.Pow: lambda a, b: a ** b,
            ast.Mod: lambda a, b: a % b,
        }
        op_func = ops.get(type(node.op))
        if op_func is None:
            raise ValueError(f"Operator not allowed: {type(node.op).__name__}")
        return op_func(left, right)

    def visit_UnaryOp(self, node):
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return operand
        raise ValueError(f"Unary operator not allowed: {type(node.op).__name__}")

    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only sqrt, abs, min, max calls are allowed")
        name = node.func.id
        if name not in _SAFE_FUNCTIONS:
            raise ValueError(f"Function not allowed: '{name}'")
        args = [self.visit(a) for a in node.args]
        return _SAFE_FUNCTIONS[name](*args)

    def generic_visit(self, node):
        raise ValueError(f"Expression node not allowed: {type(node).__name__}")


def safe_arithmetic(expression: str, variables: dict) -> float:
    """Evaluate an arithmetic expression safely via ast. No code execution.

    Supports: +, -, *, /, **, %, parentheses, pi, sqrt, abs, min, max.
    Variables are substituted from the provided dict.
    Raises ValueError for unsafe or malformed expressions.
    """
    tree = ast.parse(expression.strip(), mode="eval")
    return float(_ExprEvaluator(variables).visit(tree))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_skill_validator.py::TestSafeEval -v`
Expected: All 17 tests PASS

- [ ] **Step 5: Commit**

```bash
git add freecad_ai/extensions/skill_validator.py tests/unit/test_skill_validator.py
git commit -m "feat: add safe arithmetic expression evaluator for geometry validation"
```

---

### Task 2: VALIDATION.md Parser

**Files:**
- Modify: `freecad_ai/extensions/skill_validator.py`
- Modify: `tests/unit/test_skill_validator.py`

- [ ] **Step 1: Write failing tests for parser**

Add `TestParseValidationMd` class with a `SAMPLE_VALIDATION_MD` fixture. Tests:
- Parses parameters (name, type, default)
- Parses unconditional rules (target `_document` for doc-level checks like `total_bodies`)
- Parses object-scoped rules (exists, bbox, solid_count, valid_solid under `### EnclosureBase`)
- Parses conditional rules (`#### when lid_type == "screw"` scoped to parent h3)
- Conditional scoping (when blocks under EnclosureBase don't leak to EnclosureLid)
- Absolute tolerance parsing (`(tolerance 0.5)`)
- Relative tolerance parsing (`(tolerance 5%)`)
- Empty input returns `({}, [])`
- Malformed parameter lines are skipped with warning

Import `parse_validation_md`, `ParamDef`, `ValidationRule` from `skill_validator`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_skill_validator.py::TestParseValidationMd -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement parser**

Add to `skill_validator.py`:

Data classes:
- `ParamDef(name, type, default)` — parameter definition
- `ValidationRule(target, check, expected, tolerance, tolerance_type, condition)` — single check
- `CheckResult(target, check, passed, expected, actual, message)` — check result

Parser `parse_validation_md(content) -> (dict[str, ParamDef], list[ValidationRule])`:
- Regex patterns for parameter lines, check lines, tolerance suffixes, `when` conditions
- Tracks current section (`parameters` / `checks`), current target (from h3), current condition (from h4)
- h3 headings with spaces (like "Body count") use target `_document`
- h4 `when` blocks set condition scoped to current h3 target
- New h3 resets condition to `None`

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_skill_validator.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add freecad_ai/extensions/skill_validator.py tests/unit/test_skill_validator.py
git commit -m "feat: add VALIDATION.md parser with conditional rules and tolerance"
```

---

### Task 3: Check Runner (Mock-Based)

**Files:**
- Modify: `freecad_ai/extensions/skill_validator.py`
- Modify: `tests/unit/test_skill_validator.py`

- [ ] **Step 1: Write failing tests for check runner**

Add `TestRunChecks` class using mock FreeCAD objects. Helper functions:
- `_mock_shape(volume, xlen, ylen, zlen, is_valid, num_solids)` — mock Shape
- `_mock_doc(objects_dict)` — mock Document with `getObjectsByLabel()` and `Objects`

Tests for each check type:
- `exists` pass/fail
- `bbox` pass/fail (with tolerance)
- `volume` pass within relative tolerance, fail outside
- `solid_count` pass
- `valid_solid` pass, fail (invalid shape), fail (no solids)
- `total_bodies` document-level check
- Conditional rules: matches, skipped, not-equals
- Unknown check type returns failed result

Import `run_checks` from `skill_validator`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_skill_validator.py::TestRunChecks -v`
Expected: FAIL with `ImportError: cannot import name 'run_checks'`

- [ ] **Step 3: Implement check runner**

Add to `skill_validator.py`:

- `_check_condition(condition, params) -> bool` — evaluate `when` condition
- `_resolve_params(params, param_defs) -> dict` — fill in defaults from ParamDef
- `run_checks(doc, params, rules) -> list[CheckResult]` — iterate rules, skip non-matching conditions, dispatch to `_run_single_check()`
- `_run_single_check(doc, params, rule) -> CheckResult` — switch on `rule.check`:
  - `total_bodies`: count objects with `TypeId == "PartDesign::Body"`
  - `exists`: `doc.getObjectsByLabel(target)`
  - `bbox`: parse 3 comma-separated expressions, compare to `Shape.BoundBox.XLength/YLength/ZLength`
  - `volume`: evaluate expression, compare to `Shape.Volume` with relative or absolute tolerance
  - `solid_count`: `len(Shape.Solids)`
  - `valid_solid`: `Shape.isValid() and len(Shape.Solids) >= 1`
  - `has_holes`: count Pocket features with `Type == "ThroughAll"` in body group
  - `has_feature`: check body group for matching label
  - `min_children`: `len(body.Group) >= expected`
  - Default: return failed result with "Unknown check type"

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_skill_validator.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add freecad_ai/extensions/skill_validator.py tests/unit/test_skill_validator.py
git commit -m "feat: add geometry check runner with mock-based tests"
```

---

### Task 4: Top-level `validate_skill()` Function

**Files:**
- Modify: `freecad_ai/extensions/skill_validator.py`
- Modify: `tests/unit/test_skill_validator.py`

- [ ] **Step 1: Write failing tests**

Add `TestValidateSkill` class testing:
- Full flow: parse + resolve params + run checks in one call
- Pass rate calculation
- Empty VALIDATION.md returns `[]`
- Malformed VALIDATION.md returns `[]` (graceful degradation)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_skill_validator.py::TestValidateSkill -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement**

Add to `skill_validator.py`:

```python
def validate_skill(doc, params: dict, validation_content: str) -> list[CheckResult]:
    """Validate a FreeCAD document against VALIDATION.md rules."""
    try:
        param_defs, rules = parse_validation_md(validation_content)
    except Exception as e:
        logger.error("VALIDATION.md parse error: %s", e)
        return []
    if not rules:
        return []
    resolved = _resolve_params(params, param_defs)
    return run_checks(doc, resolved, rules)


def compute_pass_rate(results: list[CheckResult]) -> float:
    """Compute pass rate from check results. Returns 0.0-1.0."""
    if not results:
        return 0.0
    return sum(1 for r in results if r.passed) / len(results)
```

- [ ] **Step 4: Run all validator tests**

Run: `.venv/bin/pytest tests/unit/test_skill_validator.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add freecad_ai/extensions/skill_validator.py tests/unit/test_skill_validator.py
git commit -m "feat: add validate_skill() top-level API with param resolution"
```

---

## Chunk 2: Integration with Optimizer and Skills

### Task 5: Skill Registry -- Discover VALIDATION.md

**Files:**
- Modify: `freecad_ai/extensions/skills.py:25-33` (Skill dataclass)
- Modify: `freecad_ai/extensions/skills.py:54-100` (_scan_skills_dir)
- Modify: `tests/unit/test_skill_validator.py`

- [ ] **Step 1: Write failing test**

Add `TestSkillValidationDiscovery` class:
- `Skill` dataclass accepts `validation_path` field
- Default value is `""`
- `SkillsRegistry` finds VALIDATION.md alongside SKILL.md in a temp directory

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_skill_validator.py::TestSkillValidationDiscovery -v`
Expected: FAIL (Skill has no `validation_path` field)

- [ ] **Step 3: Add `validation_path` to Skill dataclass and discovery**

In `freecad_ai/extensions/skills.py`:
- Add `validation_path: str = ""` to `Skill` dataclass (around line 33)
- In `_scan_skills_dir()`, check for `VALIDATION.md` alongside `SKILL.md`, set `validation_path` if found

- [ ] **Step 4: Run full test suite**

Run: `.venv/bin/pytest tests/unit/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add freecad_ai/extensions/skills.py tests/unit/test_skill_validator.py
git commit -m "feat: discover VALIDATION.md alongside SKILL.md in skill registry"
```

---

### Task 6: `report_skill_params` Tool

**Files:**
- Modify: `freecad_ai/tools/freecad_tools.py:2746-2780` (ALL_TOOLS list)
- Create: `tests/unit/test_report_skill_params.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_report_skill_params.py` testing:
- `_handle_report_skill_params(params={"L": 100, ...})` stores params
- `get_reported_skill_params()` returns stored dict
- `clear_reported_skill_params()` resets to None
- Overwrites previous params on second call

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_report_skill_params.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement tool**

Add to `freecad_ai/tools/freecad_tools.py` before `ALL_TOOLS`:
- Module-level `_reported_skill_params: Optional[dict] = None`
- `get_reported_skill_params()` getter
- `clear_reported_skill_params()` clear function
- `_handle_report_skill_params(params: dict) -> ToolResult` handler
- `REPORT_SKILL_PARAMS` ToolDefinition with `params` as `object` type parameter
- Add `REPORT_SKILL_PARAMS` to `ALL_TOOLS` list

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_report_skill_params.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add freecad_ai/tools/freecad_tools.py tests/unit/test_report_skill_params.py
git commit -m "feat: add report_skill_params tool for geometry validation"
```

---

### Task 7: Update Scoring -- Correctness from Validation

**Files:**
- Modify: `freecad_ai/extensions/skill_evaluator.py:123-188` (weights and _score_single)
- Modify: `tests/unit/test_skill_evaluator.py`

- [ ] **Step 1: Write failing tests**

Add `TestScoringWithValidation` class:
- When `measurements["pass_rate"]` exists, correctness metric fires with that value
- Without `pass_rate`, correctness metric does not contribute to score

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_skill_evaluator.py::TestScoringWithValidation -v`
Expected: FAIL (correctness still uses old bbox logic)

- [ ] **Step 3: Update `_score_single()` and add `VALIDATED_WEIGHTS`**

In `skill_evaluator.py`:
- Add `VALIDATED_WEIGHTS` dict (completion=0.15, error_rate=0.15, correctness=0.45, efficiency=0.10, retries=0.10, visual=0.05)
- Replace old correctness block (checking `expected_bbox`) with: check `result.measurements.get("pass_rate") is not None`

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/unit/test_skill_evaluator.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add freecad_ai/extensions/skill_evaluator.py tests/unit/test_skill_evaluator.py
git commit -m "feat: correctness metric uses validation pass_rate"
```

---

### Task 8: Run Validation After Headless Skill Execution

**Files:**
- Modify: `freecad_ai/extensions/skill_evaluator.py:202-283` (evaluate method)
- Modify: `freecad_ai/tools/optimize_tools.py:122-152` (_evaluate_once)
- Modify: `freecad_ai/tools/optimize_tools.py:198-317` (_handle_optimize_iteration)

- [ ] **Step 1: Add `validation_content` parameter to `evaluate()`**

Add `validation_content: str = ""` parameter. After each headless run, if validation_content is set and run didn't have llm_error:
- Get params from `tc.get("params", {})`, falling back to `get_reported_skill_params()`
- Get FreeCAD document by name
- Call `validate_skill()`, store results in `result.measurements`

- [ ] **Step 2: Update `_evaluate_once()` to pass validation content**

Add `validation_content` parameter, pass through to `evaluator.evaluate()`.

- [ ] **Step 3: Load VALIDATION.md in `_handle_optimize_iteration()`**

At the start of the function, load validation content from the skill's `validation_path`. If found, use `VALIDATED_WEIGHTS` as default weights. Pass to `_evaluate_once()`.

- [ ] **Step 4: Run full test suite**

Run: `.venv/bin/pytest tests/unit/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add freecad_ai/extensions/skill_evaluator.py freecad_ai/tools/optimize_tools.py
git commit -m "feat: run geometry validation after headless skill execution in optimizer"
```

---

### Task 9: Enclosure VALIDATION.md and SKILL.md Update

**Files:**
- Create: `skills/enclosure/VALIDATION.md`
- Modify: `skills/enclosure/SKILL.md:90-101`

- [ ] **Step 1: Create enclosure VALIDATION.md**

Create `skills/enclosure/VALIDATION.md` with:
- Parameters: L, W, H, T (default 2), PR (default 3), lid_type (default screw)
- Checks: total_bodies=2
- EnclosureBase: exists, bbox, solid_count, valid_solid, conditional volume formulas per lid_type, min_children for screw
- EnclosureLid: exists, solid_count, valid_solid, conditional bbox per lid_type, has_holes=4 for screw

- [ ] **Step 2: Update enclosure SKILL.md**

Add to Critical rules section (after line 100):
```
- After completing ALL construction steps (including positioning), call `report_skill_params` with the parameters used: L, W, H, T, PR (for screw), and lid_type.
```

- [ ] **Step 3: Commit**

```bash
git add skills/enclosure/VALIDATION.md skills/enclosure/SKILL.md
git commit -m "feat: add enclosure VALIDATION.md and report_skill_params instruction"
```

---

## Chunk 3: UI Integration

### Task 10: Optimizer Dialog -- Structured Test Case Input

**Files:**
- Modify: `freecad_ai/ui/optimize_dialog.py:53-75` (test case section)
- Modify: `freecad_ai/ui/optimize_dialog.py:108-114` (metrics checkboxes)
- Modify: `freecad_ai/ui/optimize_dialog.py:268-295` (get_config)

- [ ] **Step 1: Add skill change handler that reads VALIDATION.md**

Connect `_skill_combo.currentIndexChanged` to `_on_skill_changed()`. On change:
- Load VALIDATION.md via SkillsRegistry
- Parse parameters with `parse_validation_md()`
- Store `self._validation_content` and `self._param_defs`
- Call `_build_param_fields()` to update UI

- [ ] **Step 2: Build structured parameter input fields**

`_build_param_fields(param_defs)`:
- Create labeled input widgets per parameter in a grid layout
- `float`/`int` params: `QDoubleSpinBox`/`QSpinBox`, pre-filled with default
- `str` params: `QComboBox` if known values (from `when` conditions), else `QLineEdit`
- `bool` params: `QCheckBox`
- Store widgets in `self._param_widgets: dict[str, QWidget]`
- Show/hide structured section vs plain text input based on whether VALIDATION.md exists

- [ ] **Step 3: Add quick-add field**

Below the structured fields, add:
- `QLineEdit` with placeholder showing parameter names with defaults
- "Add" button that parses `key=value` pairs, fills missing from defaults

- [ ] **Step 4: Update "Add Test Case" button**

Read values from `self._param_widgets`, build params dict, format display string, add to list widget. Store full dict on the list item (via `setData()`).

- [ ] **Step 5: Update `get_config()` for structured test cases**

Change from `{"args": text}` to `{"args": "L=100, ...", "params": {"L": 100, ...}}`.

- [ ] **Step 6: Rename `geometric_checks` metric to `correctness`**

Change metric checkbox name from `"geometric_checks"` to `"correctness"` and label to `"Correctness (geometry validation)"`.

- [ ] **Step 7: Run full test suite**

Run: `.venv/bin/pytest tests/unit/ -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add freecad_ai/ui/optimize_dialog.py
git commit -m "feat: structured test case input from VALIDATION.md parameters"
```

---

### Task 11: `--validate` Flag in Chat Widget

**Files:**
- Modify: `freecad_ai/ui/chat_widget.py`

- [ ] **Step 1: Strip `--validate` from user text**

In `_send_message()`, before sending to LLM, check for `--validate` in text. Strip it and set `self._validate_pending = True`.

- [ ] **Step 2: Track active skill name**

In `_handle_skill_command()` (around line 1550), store `self._active_skill_name = skill_name` when a skill is invoked. Clear it at the start of `_send_message()`.

- [ ] **Step 3: Run validation after response finishes**

In `_on_response_finished()` (around line 1313), if `self._validate_pending`:
- Load VALIDATION.md from `self._active_skill_name`
- Get params from `get_reported_skill_params()` (+ clear)
- If no params and no skill, show "No skill detected" message
- Call `validate_skill()` on active document
- Format and display results with OK/FAIL per check

- [ ] **Step 4: Run full test suite**

Run: `.venv/bin/pytest tests/unit/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add freecad_ai/ui/chat_widget.py
git commit -m "feat: --validate flag runs geometry validation after skill completes"
```

---

### Task 12: Documentation and Final Cleanup

**Files:**
- Modify: wiki Tool-Reference.md (add report_skill_params)
- Modify: wiki Skills.md or new page (document VALIDATION.md format)

- [ ] **Step 1: Document `report_skill_params` in Tool Reference**

Add entry with description, parameters, and usage example.

- [ ] **Step 2: Document VALIDATION.md format**

Add section covering: purpose, file location, parameter syntax, check types table, conditional `when` blocks, expression syntax, tolerance format.

- [ ] **Step 3: Run full test suite one final time**

Run: `.venv/bin/pytest tests/unit/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit and push**

```bash
# Wiki repo
cd /home/alf/Projects/programming/misc/freecad-ai-wiki
git add -A && git commit -m "docs: add geometry validation and report_skill_params documentation"
git push

# Main repo
cd /home/alf/Projects/programming/misc/freecad-ai
git push
```

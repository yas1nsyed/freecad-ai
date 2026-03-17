# Geometry Validation for Skill Optimizer — Design Spec

**Date**: 2026-03-17
**Status**: Draft

## Problem

The skill optimizer scores defective geometry highly (>0.9) because it only measures whether the LLM completed without errors — not whether the resulting geometry is correct. An enclosure missing its bottom or screw posts scores nearly as well as a perfect one because the "correctness" metric is never populated.

## Solution

A declarative validation system: each skill defines expected geometry properties in a `VALIDATION.md` file, and a generic validation engine checks them against the FreeCAD document after the skill runs.

- **Generic engine** — knows how to check bbox, volume, solid count, etc.
- **Skill-specific rules** — each SKILL.md author declares what to check
- **Conditional rules** — `when` blocks handle variant geometry (screw vs snap-fit lid)
- **Safe expressions** — arithmetic formulas parsed via `ast` (NOT via dangerous eval/exec)

## VALIDATION.md Format

Lives alongside SKILL.md in the skill directory:

```
skills/enclosure/
├── SKILL.md
├── VALIDATION.md
└── handler.py
```

### Structure

```markdown
# Validation Rules

## Parameters
L: float              # outer length
W: float              # outer width
H: float              # outer height
T: float = 2          # wall thickness
PR: float = 3         # post radius
lid_type: str = screw  # screw | press-fit | snap-fit

## Checks

### Body count
- total_bodies: 2

### EnclosureBase
- exists: true
- bbox: L, W, H (tolerance 0.5)
- solid_count: 1
- valid_solid: true

#### when lid_type == "screw"
- volume: L*W*H - (L-2*T)*(W-2*T)*(H-T) + 4*pi*PR**2*(H-T) (tolerance 5%)

#### when lid_type == "press-fit"
- volume: L*W*H - (L-2*T)*(W-2*T)*(H-T) (tolerance 5%)

#### when lid_type == "snap-fit"
- volume: L*W*H - (L-2*T)*(W-2*T)*(H-T) (tolerance 5%)

### EnclosureLid
- exists: true
- solid_count: 1
- valid_solid: true

#### when lid_type == "screw"
- bbox: L, W, T (tolerance 0.5)
- has_holes: 4

#### when lid_type == "press-fit"
- bbox: L, W, T+3 (tolerance 0.5)

#### when lid_type == "snap-fit"
- bbox: L, W, T+3 (tolerance 0.5)
```

### Parameter Section

Declares typed parameters with optional defaults:

```
name: type = default   # comment
```

- Types: `float`, `int`, `str`, `bool`
- Defaults: used when not provided (in optimizer quick-add, or for `--validate`)
- String params with known values (inferred from `when` conditions) become dropdowns in the optimizer dialog

### Check Types

| Check | What it validates | FreeCAD API | Value format |
|-------|-------------------|-------------|--------------|
| `exists` | Object with this label exists | `doc.getObjectsByLabel()` | `true` |
| `bbox` | Bounding box dimensions | `Shape.BoundBox.XLength/YLength/ZLength` | `X, Y, Z (tolerance N)` — absolute mm |
| `volume` | Volume matches formula | `Shape.Volume` | `expression (tolerance N%)` — relative % |
| `solid_count` | Number of solids | `len(Shape.Solids)` | integer |
| `valid_solid` | Shape is valid with >=1 solid | `Shape.isValid()` and `len(Shape.Solids) >= 1` | `true` |
| `total_bodies` | PartDesign body count in doc | Filter `TypeId == "PartDesign::Body"` | integer |
| `has_holes` | Through-hole count (Pocket features with `through_all`) | Count Pocket features where `Type == "ThroughAll"` in body | integer |
| `has_feature` | Named feature in body | `body.getObject(name)` | `"FeatureName"` |
| `min_children` | Minimum features in body | `len(body.Group)` | integer |

### Conditional Rules

`#### when param == "value"` blocks apply only when the condition matches. The engine evaluates the condition against the params dict. Only `==` and `!=` operators are supported (sufficient for variant selection).

**Scoping**: `when` blocks (h4) are always scoped to their parent object section (h3). A `#### when` under `### EnclosureBase` only affects EnclosureBase checks. Multiple `when` blocks under the same h3 are independent — each applies its own condition. Checks before any `when` block are unconditional (always checked).

### Expression Evaluator

Arithmetic expressions in `volume` and `bbox` checks are evaluated safely using Python's `ast` module. This is NOT code execution — the `ast` module is used purely to parse arithmetic into a syntax tree, which is then walked by a custom `NodeVisitor` that only allows safe operations:

- **Allowed**: `+`, `-`, `*`, `/`, `**` (power), `%`, parentheses
- **Constants**: `pi`
- **Functions**: `sqrt`, `abs`, `min`, `max`
- **Variables**: parameter names from `## Parameters`
- **Rejected**: attribute access, arbitrary function calls, imports, string operations, anything else

~50-60 lines — an `ast.NodeVisitor` that walks the parsed tree and computes the result. No code is ever executed — only arithmetic is evaluated from the parsed AST nodes.

## Parameter Passing

### How the validator gets parameter values

| Context | Source |
|---------|--------|
| Optimizer | Structured fields in dialog, or quick-add `key=value` string |
| `--validate` | LLM calls `report_skill_params` tool at end of skill execution |

### `report_skill_params` Tool

A new tool that the LLM calls at the end of a skill run to report the parameters it used:

```python
report_skill_params(L=100, W=80, H=40, T=2, lid_type="screw")
```

- Stores the params dict in module-level state
- The validator reads it after the skill completes
- SKILL.md instructs the LLM: "After completing all steps, call `report_skill_params` with ..."
- Simple tool: receives a dict, stores it, returns confirmation

This approach works regardless of how the user phrased their request ("make me a 100x80x40 box" vs "/enclosure 100 80 40").

**Fallback**: If the LLM forgets to call `report_skill_params` (common with smaller models), and the skill was invoked via a `/command` with arguments, the system can parse the command args using the VALIDATION.md parameter definitions as a fallback. If neither source provides params, validation is skipped.

**Optimizer path**: The optimizer does NOT rely on `report_skill_params` — it has the params dict from the structured test case input and passes them directly to `validate_skill()`.

## Optimizer Dialog Changes

### When a skill with VALIDATION.md is selected

The test case section generates structured input fields from the parameter definitions:

```
+-  Test Cases -----------------------------------------------+
|  L: [100    ]  W: [80     ]  H: [40     ]                  |
|  T: [2      ]  PR: [3      ]                                |
|  lid_type: [screw     v]                                    |
|  [Add Test Case]                                            |
|                                                             |
|  Quick add: [L=120, W=90, H=50, lid_type=press-fit     ]   |
|             [Add]                                           |
|                                                             |
|  +------------------------------------------------+        |
|  | 1. L=100, W=80, H=40, T=2, PR=3, screw         |        |
|  | 2. L=120, W=90, H=50, T=2, PR=3, press-fit     |        |
|  +------------------------------------------------+        |
|  [Remove]                                                   |
+-------------------------------------------------------------+
```

- Defaults pre-filled from VALIDATION.md
- String params with known values (from `when` conditions) shown as dropdowns
- Quick-add parses `key=value` pairs, missing keys use defaults
- Test cases stored as dicts, not strings

### When a skill without VALIDATION.md is selected

Falls back to current behavior — free text input. Correctness metric unavailable.

### Optimizer param flow

Test cases are stored as dicts (e.g., `{"L": 100, "W": 80, "H": 40, "T": 2, "lid_type": "screw"}`). The existing `test_cases: list[dict]` structure in `SkillEvaluator.evaluate()` is extended: each dict gains a `"params"` key alongside the existing `"args"` key. The `"args"` string is built from the params for the LLM prompt (e.g., `"L=100, W=80, H=40, T=2, lid_type=screw"`). The evaluator passes `params` to `validate_skill()` after the headless run — no dependency on `report_skill_params` in the optimizer path.

## Scoring Changes

### Weight adjustment when VALIDATION.md exists

| Metric | Without VALIDATION.md | With VALIDATION.md |
|--------|-----------------------|--------------------|
| completion | 0.30 | 0.15 |
| error_rate | 0.25 | 0.15 |
| **correctness** | disabled | **0.45** |
| efficiency | 0.10 | 0.10 |
| retries | 0.10 | 0.10 |
| visual | 0.05 | 0.05 |

Correctness becomes the dominant score. A broken enclosure that "completes" with 3/9 checks passed would get:
- completion: 1.0 x 0.15 = 0.15
- error_rate: 0.93 x 0.15 = 0.14
- **correctness: 0.33 x 0.45 = 0.15**
- efficiency: 0.50 x 0.10 = 0.05

Total: **~0.52** instead of the previous 0.91.

### Correctness metric implementation

Replaces the dead `expected_bbox` code in `_score_single()`:

```python
if "correctness" in metrics and result.measurements.get("pass_rate") is not None:
    scores["correctness"] = result.measurements["pass_rate"]
    active_weights["correctness"] = weights.get("correctness", 0.45)
```

## `--validate` Flow

### User types: `make me an enclosure 100 80 40 snap-fit --validate`

1. `ChatDockWidget` strips `--validate` from text, sets `validate_pending = True`
2. LLM processes the request, calls tools (create_body, create_sketch, etc.)
3. LLM calls `report_skill_params(L=100, W=80, H=40, T=2, lid_type="snap-fit")`
4. LLM finishes (no more tool calls)
5. System detects `validate_pending`, reads stored params
6. Determines which skill was used (from skill invocation or system prompt context)
7. Loads VALIDATION.md, runs `validate_skill()`
8. Displays results in chat:

```
Validation: 8/9 checks passed
  OK  total_bodies: 2
  OK  EnclosureBase exists
  OK  EnclosureBase bbox: 100.0 x 80.0 x 40.0
  OK  EnclosureBase volume: 38847.3 (expected 38400.0 +/-5%)
  OK  EnclosureBase solid_count: 1
  OK  EnclosureBase valid_solid
  FAIL  EnclosureLid bbox: expected 100.0 x 80.0 x 5.0, got 100.0 x 80.0 x 2.0
  OK  EnclosureLid solid_count: 1
  OK  EnclosureLid valid_solid
```

### Determining which skill was used

When `--validate` is present, `ChatDockWidget` stores the skill name in an instance variable `self._active_skill_name` whenever a skill is invoked (via `/command` or auto-detection). After the LLM finishes, validation looks up the VALIDATION.md using this stored name. If no skill was detected (free-form request without skill invocation), validation is skipped with a message: "No skill detected — cannot validate without VALIDATION.md."

### Error handling for malformed VALIDATION.md

If VALIDATION.md has syntax errors (unknown check types, malformed expressions, missing parameters), the parser logs a warning to the FreeCAD console and returns an empty rule set. Validation is skipped with a message: "VALIDATION.md parse error: {details}. Skipping validation." This prevents broken validation files from crashing the skill or the optimizer.

## File Layout

### New Files

| File | Purpose |
|------|---------|
| `freecad_ai/extensions/skill_validator.py` | VALIDATION.md parser, safe expression evaluator, check runner |
| `skills/enclosure/VALIDATION.md` | Validation rules for the enclosure skill |
| `tests/unit/test_skill_validator.py` | Tests for parser, expression evaluator, check logic |

### Modified Files

| File | Change |
|------|--------|
| `freecad_ai/extensions/skill_evaluator.py` | After headless run, call `validate_skill()` and populate `measurements["pass_rate"]`. Update `_score_single()` correctness metric. Adjust default weights when VALIDATION.md present. |
| `freecad_ai/tools/freecad_tools.py` | Add `report_skill_params` tool |
| `freecad_ai/ui/chat_widget.py` | Strip `--validate`, run validation after skill completes, display results |
| `freecad_ai/ui/optimize_dialog.py` | Read VALIDATION.md params on skill selection, generate structured fields + quick-add. Rename metric checkbox from `"geometric_checks"` to `"correctness"` to match `_score_single()`. |
| `freecad_ai/extensions/skills.py` | `Skill` dataclass gets `validation_path` field, `_scan_skills_dir()` discovers VALIDATION.md alongside SKILL.md |
| `skills/enclosure/SKILL.md` | Add `report_skill_params` instruction at end |

## Key Design Decisions

1. **Declarative over imperative** — VALIDATION.md is Markdown with simple rules, not Python code. Skill authors don't need programming skills.
2. **Safe expression evaluator** — `ast`-based tree walker, no code execution. Only arithmetic and basic math functions.
3. **`valid_solid` over `watertight`** — Watertight fails on intentional openings (cooling slits). `valid_solid` checks topology without assuming closed shells.
4. **`report_skill_params` tool** — LLM reports what parameters it used, so validation works regardless of how the user phrased the request.
5. **Conditional `when` blocks** — Handle variant geometry (screw/press-fit/snap-fit) in one file.
6. **Validate is opt-in** — `--validate` flag for manual use, `validate=True` for optimizer. Not a persistent setting.
7. **Weight shift with VALIDATION.md** — Correctness becomes 0.45 (dominant) when validation rules exist, so broken geometry can no longer score 0.9.
8. **Structured test case input** — Fields generated from VALIDATION.md parameters, with quick-add shortcut. No parsing ambiguity.

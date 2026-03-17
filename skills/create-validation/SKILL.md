---
name: create-validation
description: Generate a draft VALIDATION.md for a skill by analyzing its SKILL.md construction steps
---

# Create Validation Rules

Generate a draft VALIDATION.md file for a skill by analyzing its SKILL.md.

## WARNING — READ THIS FIRST

**This skill generates a DRAFT, not a finished product.** The generated VALIDATION.md will likely contain errors, especially in volume formulas. You MUST:

1. **Review every check** — does it match what the skill actually builds?
2. **Verify all volume formulas by hand** — volume calculations for complex geometry (shells with posts, lips, ridges) are easy to get wrong. Calculate the expected volume for one set of dimensions and compare with the formula.
3. **Test with `--validate`** — run the skill with known-good parameters and `--validate` to see if the checks pass on correct geometry.
4. **Adjust tolerances** — the defaults (0.5mm for bbox, 5% for volume) may be too tight or too loose for your skill.
5. **Check conditional rules** — if your skill has variants, verify each `when` block covers the right checks.

**Common errors in generated VALIDATION.md:**
- Volume formulas that forget to add/subtract features (posts, holes, lips, ridges)
- Wrong body labels (FreeCAD may rename bodies)
- Missing conditional branches for skill variants
- Tolerances that are too tight for the geometry complexity

## How to use

```
/create-validation skill-name
```

Where `skill-name` is the name of an existing skill (e.g., `enclosure`, `gear`).

## What to do

1. Read the specified skill's SKILL.md using `execute_code`:
   ```python
   import os
   skills_dirs = [
       os.path.expanduser("~/.config/FreeCAD/FreeCADAI/skills"),
   ]
   # Also check built-in skills
   builtin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills") if '__file__' in dir() else ""
   ```
   Or use `get_document_state` context to find the skill path.

2. Analyze the SKILL.md to extract:
   - **Parameters**: from the "Parameters to extract" section. Note types and defaults.
   - **Bodies**: from `create_body` instructions. Note their labels.
   - **Geometry steps**: pad dimensions, pocket depths, post positions, etc.
   - **Variants**: different lid types, optional features, conditional construction steps.

3. Generate VALIDATION.md with this structure:

```markdown
# Validation Rules

## Parameters
(one line per parameter: name: type = default)

## Checks

### Body count
- total_bodies: N

### BodyLabel
- exists: true
- bbox: X_expr, Y_expr, Z_expr (tolerance 0.5)
- volume: formula (tolerance 5%)
- solid_count: 1
- valid_solid: true

#### when variant_param == "value"
- (variant-specific checks)
```

4. Write the file to the skill directory as VALIDATION.md.

5. **IMPORTANT**: After writing, display this message to the user:

> **Draft VALIDATION.md created.** This is a starting point, NOT a finished file.
>
> **You must verify:**
> - All volume formulas — calculate expected values by hand for at least one set of dimensions
> - Body labels match what FreeCAD actually creates (use `get_document_state` after running the skill)
> - Conditional `when` blocks cover all variants
> - Tolerances are appropriate (0.5mm bbox, 5% volume are defaults)
>
> **Test it:** Run `/skill-name args --validate` to check against actual geometry.
>
> **Fix it:** Edit the VALIDATION.md directly if checks fail on correct geometry.

## Rules for generating volume formulas

- **Rectangular shell** (box with hollow interior): `L*W*H - (L-2*T)*(W-2*T)*(H-T)`
  - This gives 4 walls + floor, open top
- **Cylindrical posts** added to interior: `+ N * pi * R**2 * post_height`
  - N = number of posts, R = post radius
- **Cylindrical holes** subtracted: `- N * pi * R**2 * depth`
- **Solid slab** (lid): `L * W * T`
- **Lid with lip**: lip volume + slab volume
- **Use `pi` constant**, not 3.14159 (the expression evaluator supports `pi`)
- **Use `**` for power**, not `^` (the evaluator uses Python's `ast` module)

## Available check types

| Check | Value format | When to use |
|-------|-------------|-------------|
| `exists: true` | — | Always, for each body |
| `bbox: X, Y, Z (tolerance 0.5)` | Expressions, absolute mm | Always, for each body |
| `volume: expr (tolerance 5%)` | Expression, relative % | When geometry has calculable volume |
| `solid_count: N` | Integer | Always (usually 1 per body) |
| `valid_solid: true` | — | Always, for each body |
| `total_bodies: N` | Integer | Once, at document level |
| `has_holes: N` | Integer | When through-all pockets expected |
| `has_feature: "Name"` | String | When specific named features expected |
| `min_children: N` | Integer | When minimum feature count matters |

## Parameter type reference

| Type | Default syntax | Example |
|------|---------------|---------|
| `float` | `= 2.5` | `T: float = 2` |
| `int` | `= 4` | `count: int = 4` |
| `str` | `= value` | `lid_type: str = screw` |
| `bool` | `= false` | `add_vents: bool = false` |

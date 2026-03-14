"""Optimize iteration tool for the skill optimizer.

Provides the optimize_iteration tool that evaluates a SKILL.md by running
the skill with test cases, collecting metrics, and computing composite scores.
Also manages optimization session state (start/stop, iteration tracking,
best-score comparison).
"""

import json
import logging
from typing import Optional

from .registry import ToolDefinition, ToolParam, ToolResult

logger = logging.getLogger(__name__)

# ── Module-level optimization session state ──────────────────────────────

_active_state = None  # OptimizationState
_active_config: Optional[dict] = None
_iteration: int = 0


def start_optimization(state, config: dict) -> None:
    """Activate optimization session globals."""
    global _active_state, _active_config, _iteration
    _active_state = state
    _active_config = config
    _iteration = 0


def stop_optimization() -> None:
    """Clear optimization session globals."""
    global _active_state, _active_config, _iteration
    _active_state = None
    _active_config = None
    _iteration = 0


# ── Strategy instructions ────────────────────────────────────────────────

STRATEGY_INSTRUCTIONS = {
    "conservative": (
        "Make only small, targeted changes to the SKILL.md. Focus on fixing "
        "the single lowest-scoring metric without altering parts that already "
        "score well. Prefer adding clarifying instructions over rewriting "
        "existing ones. Avoid restructuring the overall approach."
    ),
    "balanced": (
        "Make moderate changes to improve the weakest metrics while preserving "
        "strengths. You may restructure sections that are underperforming, but "
        "keep the overall strategy intact. Consider adjusting tool call "
        "sequences, adding error-handling hints, and refining geometry "
        "parameters."
    ),
    "aggressive": (
        "You are free to make significant changes including restructuring the "
        "entire SKILL.md approach. Consider alternative geometry strategies, "
        "different tool call orderings, and fundamentally different ways to "
        "achieve the desired result. Preserve only what is clearly working."
    ),
}

# ── Prompt template ──────────────────────────────────────────────────────

OPTIMIZATION_PROMPT_TEMPLATE = """\
# Skill Optimization Task

You are an optimization agent. Your ONLY job is to iteratively improve a SKILL.md file by calling the `optimize_iteration` tool repeatedly. You MUST run {iterations} iterations.

## Skill: {skill_name}

## Current SKILL.md

```skill
{current_skill_md}
```

## Test Cases

{test_cases_formatted}

## Configuration

- Iterations: {iterations}
- Runs per test: {runs_per_test}
- Strategy: {strategy}
- Enabled metrics: {enabled_metrics}
- Tool-call budget per run: {budget}

## MANDATORY WORKFLOW — Follow these steps exactly:

**Step 1 — Baseline:** Call `optimize_iteration` with the current SKILL.md exactly as shown above. This establishes the baseline score.

**Step 2 — Analyze:** Read the results carefully. Look at:
- Which test cases had errors? What were the specific error messages?
- Common patterns: "Sketch not found" means FreeCAD renamed the sketch. "not found" means wrong object name.
- FreeCAD naming: sketches are named "Sketch", "Sketch001", "Sketch002" etc. (NOT "Sketch0", "Sketch1"). Bodies may be renamed too.

**Step 3 — Modify:** Edit the SKILL.md to fix the errors. Common fixes:
- Tell the LLM to use `get_document_state` to check actual object names before referencing them
- Add explicit naming instructions ("name the sketch 'OuterSketch'" in create_sketch)
- Add warnings about FreeCAD renaming objects
- Simplify complex multi-step sequences that are error-prone

**Step 4 — Re-evaluate:** Call `optimize_iteration` again with your MODIFIED SKILL.md (the complete text, not a diff).

**Step 5 — Repeat:** Go back to Step 2. Keep iterating until you have done {iterations} iterations total.

## CRITICAL RULES

- You MUST call `optimize_iteration` at least {iterations} times total.
- Each call MUST include the COMPLETE SKILL.md as `skill_content` (not a summary or diff).
- After seeing results, you MUST modify the SKILL.md and call again. Do NOT just report the results.
- The `test_cases` parameter must be the same list every time: {test_cases_json}
- If score plateaus for 3 iterations, try a fundamentally different approach.
- When all iterations are done, summarize what you changed and the score progression.

## Strategy

{strategy_instruction}
"""


# ── Handler ──────────────────────────────────────────────────────────────

def _handle_optimize_iteration(
    skill_name: str,
    skill_content: str,
    test_cases: list,
    runs_per_test: int = 2,
) -> ToolResult:
    """Evaluate a SKILL.md by running the skill with test cases."""
    global _iteration

    if _active_config is None:
        return ToolResult(
            success=False,
            output="No active optimization session. Call start_optimization first.",
            error="No active optimization session",
        )

    _iteration += 1
    iteration = _iteration

    # Parse test_cases: accept JSON strings or plain strings
    parsed_cases = []
    for tc in test_cases:
        if isinstance(tc, str):
            try:
                parsed = json.loads(tc)
                if isinstance(parsed, dict):
                    parsed_cases.append(parsed)
                else:
                    parsed_cases.append({"args": tc})
            except (json.JSONDecodeError, ValueError):
                parsed_cases.append({"args": tc})
        elif isinstance(tc, dict):
            parsed_cases.append(tc)
        else:
            parsed_cases.append({"args": str(tc)})

    # Run evaluation
    from ..extensions.skill_evaluator import SkillEvaluator, compute_composite_score

    evaluator = SkillEvaluator(
        config=_active_config,
        tool_executor=_active_config.get("_tool_executor"),
    )
    results = evaluator.evaluate(
        skill_name=skill_name,
        skill_content=skill_content,
        test_cases=parsed_cases,
        runs_per_test=runs_per_test,
    )

    # Compute composite score
    score = compute_composite_score(results, _active_config)

    # Compare against best
    best_content, best_score = _active_state.get_best()
    tolerance = _active_config.get("tolerance", 0.01)

    if best_score == 0.0 or score >= best_score - tolerance:
        kept = True
        comparison = "new_best" if score > best_score else "within_tolerance"
    else:
        kept = False
        comparison = "discarded"

    # Save version
    _active_state.save_version(
        iteration=iteration,
        content=skill_content,
        score=score,
        kept=kept,
        config=_active_config.get("model_config", {}),
    )

    # Determine strategy based on iteration count
    total_iterations = _active_config.get("iterations", 5)
    if iteration <= 2:
        strategy = "failure_driven"
    else:
        strategy = "holistic"

    # Build per-test-case details
    case_details = []
    for r in results:
        detail = {
            "test_case": r.test_case,
            "completed": r.completed,
            "tool_calls": r.tool_calls,
            "errors": r.errors,
            "retries": r.retries,
        }
        if r.error_messages:
            detail["error_messages"] = r.error_messages
        if r.visual_score is not None:
            detail["visual_score"] = r.visual_score
        if r.run_scores:
            detail["run_scores"] = r.run_scores
        case_details.append(detail)

    output_data = {
        "iteration": iteration,
        "composite_score": round(score, 4),
        "best_score": round(max(score, best_score), 4),
        "comparison": comparison,
        "kept": kept,
        "strategy": strategy,
        "results": case_details,
    }

    # Build detailed output for the LLM (it needs to see errors to fix them)
    output_lines = [
        f"Iteration {iteration}: score={score:.4f} "
        f"(best={max(score, best_score):.4f}, {comparison})",
        "",
    ]
    for detail in case_details:
        output_lines.append(f"Test case: {detail['test_case']}")
        output_lines.append(f"  completed={detail['completed']}, "
                           f"tool_calls={detail['tool_calls']}, "
                           f"errors={detail['errors']}")
        if detail.get("error_messages"):
            for msg in detail["error_messages"][:10]:  # cap at 10
                output_lines.append(f"  ERROR: {msg}")
        if detail.get("run_scores"):
            output_lines.append(f"  run_scores={detail['run_scores']}")

    return ToolResult(
        success=True,
        output="\n".join(output_lines),
        data=output_data,
    )


# ── Tool definition factory ─────────────────────────────────────────────

def get_optimize_iteration_tool() -> ToolDefinition:
    """Return the optimize_iteration tool definition."""
    return ToolDefinition(
        name="optimize_iteration",
        description=(
            "Evaluate a SKILL.md by running the skill with test cases and "
            "collecting metrics. Returns composite score and detailed results."
        ),
        parameters=[
            ToolParam(
                name="skill_name",
                type="string",
                description="Name of the skill being optimized.",
                required=True,
            ),
            ToolParam(
                name="skill_content",
                type="string",
                description="Complete SKILL.md content to evaluate.",
                required=True,
            ),
            ToolParam(
                name="test_cases",
                type="array",
                description="List of test case strings or JSON objects to run.",
                required=True,
                items={"type": "string"},
            ),
            ToolParam(
                name="runs_per_test",
                type="integer",
                description="Number of runs per test case for averaging.",
                required=False,
                default=2,
            ),
        ],
        handler=_handle_optimize_iteration,
        category="optimization",
    )


# ── Internal eval tools (document management, not exposed to LLM) ─────

def _handle_eval_create_doc(name: str) -> ToolResult:
    """Create a fresh FreeCAD document for evaluation."""
    import FreeCAD as App
    doc = App.newDocument(name)
    App.setActiveDocument(name)
    return ToolResult(success=True, output=f"Created document: {doc.Name}")


def _handle_eval_close_doc(name: str) -> ToolResult:
    """Close an evaluation document."""
    import FreeCAD as App
    docs = App.listDocuments()
    if name in [d.Name for d in docs.values()]:
        App.closeDocument(name)
        return ToolResult(success=True, output=f"Closed document: {name}")
    return ToolResult(success=True, output=f"Document {name} not found (already closed)")


def get_eval_tools() -> list[ToolDefinition]:
    """Return internal tools for evaluation document management.

    These are registered in the evaluator's registry but NOT exposed to the
    LLM (they have no schema in the tools list sent to the LLM).
    """
    return [
        ToolDefinition(
            name="_eval_create_doc",
            description="(internal) Create evaluation document",
            parameters=[ToolParam("name", "string", "Document name")],
            handler=_handle_eval_create_doc,
            category="_internal",
        ),
        ToolDefinition(
            name="_eval_close_doc",
            description="(internal) Close evaluation document",
            parameters=[ToolParam("name", "string", "Document name")],
            handler=_handle_eval_close_doc,
            category="_internal",
        ),
    ]

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

You are optimizing the SKILL.md for skill **{skill_name}**.

## Current SKILL.md

```skill
{current_skill_md}
```

## Test Cases

{test_cases_formatted}

## Configuration

- Iterations remaining: {iterations}
- Runs per test: {runs_per_test}
- Strategy: {strategy}
- Enabled metrics: {enabled_metrics}
- Tool-call budget per run: {budget}

## Workflow

1. Call the `optimize_iteration` tool with the current SKILL.md and test cases to get a baseline score.
2. Analyze the results — identify the lowest-scoring metrics and error patterns.
3. Modify the SKILL.md to address weaknesses.
4. Call `optimize_iteration` again with the updated SKILL.md.
5. Repeat until iterations are exhausted or the score plateaus.

## Rules

- Always provide the **complete** SKILL.md content (not a diff) when calling optimize_iteration.
- Focus improvement efforts on the **lowest-scoring metric** first.
- If the score does not improve for 3 consecutive iterations, try a different approach or stop early.

## Strategy Instruction

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
        config={
            "provider": _active_config.get("provider", ""),
            "model": _active_config.get("model", ""),
        },
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

    summary = (
        f"Iteration {iteration}: score={score:.4f} "
        f"(best={max(score, best_score):.4f}, {comparison})"
    )

    return ToolResult(
        success=True,
        output=summary,
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

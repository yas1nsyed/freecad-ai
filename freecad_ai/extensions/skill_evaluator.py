"""Skill evaluation framework for the skill optimizer."""
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    """Result of evaluating a skill on a single test case."""

    test_case: str
    tool_calls: int = 0
    errors: int = 0
    retries: int = 0
    error_messages: list[str] = field(default_factory=list)
    measurements: dict = field(default_factory=dict)
    completed: bool = False
    visual_score: Optional[float] = None
    visual_assessment: str = ""
    run_scores: list[float] = field(default_factory=list)


class OptimizationState:
    """Manages the .optimize/ directory, history.json, and version files for a skill."""

    def __init__(self, skill_name: str, base_dir: str = ""):
        if not base_dir:
            from ..config import SKILLS_DIR
            base_dir = SKILLS_DIR
        self._skill_dir = os.path.join(base_dir, skill_name)
        self._opt_dir = os.path.join(self._skill_dir, ".optimize")
        self._history_path = os.path.join(self._opt_dir, "history.json")
        self._original_path = os.path.join(self._skill_dir, "SKILL.md.original")
        self._skill_path = os.path.join(self._skill_dir, "SKILL.md")

        os.makedirs(self._opt_dir, exist_ok=True)

        # Load existing history
        self._history: list[dict] = []
        if os.path.isfile(self._history_path):
            with open(self._history_path, "r") as f:
                self._history = json.load(f)

    def save_original(self, content: str) -> None:
        """Save original SKILL.md content. Does not overwrite if already exists."""
        if os.path.isfile(self._original_path):
            return
        with open(self._original_path, "w") as f:
            f.write(content)

    def save_version(
        self,
        iteration: int,
        content: str,
        score: float,
        kept: bool,
        config: Optional[dict] = None,
    ) -> None:
        """Save a versioned SKILL.md and append to history."""
        version_path = os.path.join(self._opt_dir, f"v{iteration}.md")
        with open(version_path, "w") as f:
            f.write(content)

        entry = {
            "iteration": iteration,
            "score": score,
            "kept": kept,
            "timestamp": time.time(),
            "file": f"v{iteration}.md",
        }
        if config is not None:
            entry["config"] = config

        self._history.append(entry)
        self._save_history()

    def get_best(self) -> tuple[str, float]:
        """Return (content, score) of the highest-scoring kept version."""
        best_entry = None
        for entry in self._history:
            if entry.get("kept", False):
                if best_entry is None or entry["score"] > best_entry["score"]:
                    best_entry = entry

        if best_entry is None:
            return "", 0.0

        version_path = os.path.join(self._opt_dir, best_entry["file"])
        with open(version_path, "r") as f:
            content = f.read()
        return content, best_entry["score"]

    def get_history(self) -> list[dict]:
        """Return the full history list."""
        return list(self._history)

    def restore_best(self) -> None:
        """Write the best version content to SKILL.md."""
        content, score = self.get_best()
        if content:
            with open(self._skill_path, "w") as f:
                f.write(content)

    def is_config_stale(self, current_config: dict) -> bool:
        """Check if the model/provider changed since the last recorded version."""
        for entry in reversed(self._history):
            if "config" in entry:
                return entry["config"] != current_config
        # No config recorded yet — treat as stale
        return True

    def _save_history(self) -> None:
        with open(self._history_path, "w") as f:
            json.dump(self._history, f, indent=2)

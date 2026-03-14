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

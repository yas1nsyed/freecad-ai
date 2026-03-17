"""Tests for report_skill_params tool."""
from freecad_ai.tools.freecad_tools import (
    _handle_report_skill_params, get_reported_skill_params,
    clear_reported_skill_params,
)


class TestReportSkillParams:
    def test_stores_params(self):
        clear_reported_skill_params()
        result = _handle_report_skill_params(
            params={"L": 100, "W": 80, "H": 40, "T": 2})
        assert result.success
        assert get_reported_skill_params() == {"L": 100, "W": 80, "H": 40, "T": 2}

    def test_clear(self):
        _handle_report_skill_params(params={"L": 50})
        clear_reported_skill_params()
        assert get_reported_skill_params() is None

    def test_overwrites_previous(self):
        _handle_report_skill_params(params={"L": 50})
        _handle_report_skill_params(params={"L": 100})
        assert get_reported_skill_params() == {"L": 100}

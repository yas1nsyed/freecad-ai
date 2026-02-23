"""Integration test fixtures — runs FreeCAD scripts via AppImage subprocess."""

import json
import os
import subprocess
import textwrap

import pytest

# Find FreeCAD AppImage
FREECAD_CMD = None
_candidates = [
    os.path.expanduser("~/bin/FreeCAD_1.0.2-conda-Linux-x86_64-py311.AppImage"),
]
# Also check for any AppImage in ~/bin
import glob
_candidates += sorted(glob.glob(os.path.expanduser("~/bin/FreeCAD*.AppImage")), reverse=True)
for _c in _candidates:
    if os.path.isfile(_c) and os.access(_c, os.X_OK):
        FREECAD_CMD = _c
        break


def pytest_collection_modifyitems(config, items):
    """Skip integration tests if FreeCAD is not available."""
    if FREECAD_CMD is None:
        skip = pytest.mark.skip(reason="FreeCAD AppImage not found")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)


@pytest.fixture
def run_freecad_script(tmp_path):
    """Fixture that runs a Python script in FreeCAD console mode.

    Returns a function that accepts script content and returns parsed
    JSON results from the script's output file.
    """
    def _run(script_content, timeout=60):
        script_file = tmp_path / "test_script.py"
        result_file = tmp_path / "result.json"

        # Wrapper that sets up the environment and captures results
        wrapper = textwrap.dedent(f"""\
            import sys, json, traceback
            RESULT_FILE = {str(result_file)!r}
            results = {{"ok": False, "error": "", "data": {{}}}}
            try:
                import FreeCAD as App
                import Part
                import PartDesign
                import Sketcher

                # Add project root to path for tool imports
                sys.path.insert(0, {os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))!r})

                doc = App.newDocument("TestDoc")

        """)

        footer = textwrap.dedent(f"""\

                doc.recompute()
                results["ok"] = True
            except Exception as e:
                results["error"] = traceback.format_exc()
            finally:
                with open(RESULT_FILE, "w") as f:
                    json.dump(results, f, indent=2, default=str)
                sys.exit(0)
        """)

        # Indent user script to be inside the try block
        indented = textwrap.indent(script_content, "    ")
        full_script = wrapper + indented + footer
        script_file.write_text(full_script)

        proc = subprocess.run(
            [FREECAD_CMD, "-c", str(script_file)],
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            timeout=timeout,
            capture_output=True,
        )

        if not result_file.exists():
            stderr = proc.stderr.decode(errors="replace")[-1000:]
            raise RuntimeError(
                f"FreeCAD script failed (rc={proc.returncode}).\n"
                f"stderr: {stderr}"
            )

        return json.loads(result_file.read_text())

    return _run

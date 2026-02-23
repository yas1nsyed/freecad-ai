"""Tests for code execution engine — extract, validate, and safety checks."""

import pytest

from freecad_ai.core.executor import extract_code_blocks, _validate_code


class TestExtractCodeBlocks:
    def test_single_block(self):
        text = "Here's code:\n```python\nprint('hello')\n```\nDone."
        blocks = extract_code_blocks(text)
        assert len(blocks) == 1
        assert "print('hello')" in blocks[0]

    def test_multiple_blocks(self):
        text = (
            "First:\n```python\na = 1\n```\n"
            "Second:\n```python\nb = 2\n```\n"
        )
        blocks = extract_code_blocks(text)
        assert len(blocks) == 2

    def test_no_blocks(self):
        text = "No code here, just text."
        blocks = extract_code_blocks(text)
        assert blocks == []

    def test_non_python_block_ignored(self):
        text = "```javascript\nconsole.log('hi')\n```"
        blocks = extract_code_blocks(text)
        assert blocks == []

    def test_multiline_code(self):
        text = "```python\ndef foo():\n    return 42\n\nresult = foo()\n```"
        blocks = extract_code_blocks(text)
        assert len(blocks) == 1
        assert "def foo():" in blocks[0]
        assert "result = foo()" in blocks[0]

    def test_empty_block(self):
        text = "```python\n```"
        blocks = extract_code_blocks(text)
        # Empty match
        assert len(blocks) == 1
        assert blocks[0].strip() == ""

    def test_nested_backticks_in_string(self):
        text = '```python\nx = "```"\n```'
        blocks = extract_code_blocks(text)
        # Regex matches greedily but should get at least one block
        assert len(blocks) >= 1


class TestValidateCode:
    # ── Dangerous patterns ──

    def test_blocks_os_system(self):
        warnings = _validate_code("os.system('rm -rf /')")
        assert any("os.system" in w for w in warnings)

    def test_blocks_subprocess(self):
        warnings = _validate_code("import subprocess\nsubprocess.run(['ls'])")
        assert any("subprocess" in w for w in warnings)

    def test_blocks_shutil_rmtree(self):
        warnings = _validate_code("shutil.rmtree('/home')")
        assert any("shutil.rmtree" in w for w in warnings)

    def test_blocks_dynamic_os_import(self):
        warnings = _validate_code("__import__('os').system('ls')")
        assert any("Dynamic import" in w for w in warnings)

    def test_safe_code_passes(self):
        warnings = _validate_code(
            "import FreeCAD as App\n"
            "doc = App.newDocument('Test')\n"
            "box = doc.addObject('Part::Box', 'Box')\n"
        )
        assert warnings == []

    # ── Revolution crash patterns ──

    def test_blocks_revolution_with_full_circle(self):
        code = (
            "import Part\n"
            "circle = Part.Circle()\n"
            "feat = body.newObject('PartDesign::Revolution', 'Rev')\n"
        )
        warnings = _validate_code(code)
        assert any("Revolution" in w or "crash" in w.lower() for w in warnings)

    def test_allows_revolution_with_arc(self):
        code = (
            "arc = Part.ArcOfCircle(circ, 0, 3.14)\n"
            "feat = body.newObject('PartDesign::Revolution', 'Rev')\n"
        )
        warnings = _validate_code(code)
        # ArcOfCircle should NOT trigger the revolution warning
        assert not any("crash" in w.lower() for w in warnings)

    def test_blocks_360_degree_revolution(self):
        code = (
            "feat = body.newObject('PartDesign::Revolution', 'Rev')\n"
            "feat.Angle = 360\n"
        )
        warnings = _validate_code(code)
        assert any("360" in w for w in warnings)

    def test_allows_partial_revolution(self):
        code = (
            "feat = body.newObject('PartDesign::Revolution', 'Rev')\n"
            "feat.Angle = 180\n"
        )
        warnings = _validate_code(code)
        assert not any("360" in w for w in warnings)

    # ── False positive checks ──

    def test_subprocess_in_comment_still_blocked(self):
        # The validator does simple regex matching, not AST — it blocks
        # "subprocess" anywhere in code text. This is intentional.
        code = "# We could use subprocess but we don't\nsubprocess.call(['ls'])"
        warnings = _validate_code(code)
        assert any("subprocess" in w for w in warnings)

    def test_os_in_variable_name_ok(self):
        # "os_path" should NOT trigger os.system warning
        warnings = _validate_code("os_path = '/tmp/test'")
        assert warnings == []

    def test_safe_revolution_mention_in_string(self):
        # "Revolution" in a string without Part.Circle should be fine
        code = "name = 'Revolution'\nprint(name)"
        warnings = _validate_code(code)
        assert warnings == []

"""Tests for the main CLI dispatch (argparse + run/run_from_text routing)."""
import sys
from unittest.mock import patch

import pytest


@pytest.fixture
def fresh_main():
    """Import main fresh each test to reset argv handling."""
    if "main" in sys.modules:
        del sys.modules["main"]
    # Patch agent.run/run_from_text BEFORE main imports them
    with patch.dict("sys.modules"):
        import main
        yield main


class TestTextMode:
    def test_text_mode_calls_run_from_text(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(sys, "argv", ["main.py", "--text", "fix the naming", "--dir", str(tmp_path)])
        with patch("agent.run_from_text", return_value=["did the thing"]) as mock_run, \
             patch("agent.run") as mock_run_screenshot:
            if "main" in sys.modules:
                del sys.modules["main"]
            import main
            main.main()
        mock_run.assert_called_once()
        args, _ = mock_run.call_args
        assert args[0] == "fix the naming"
        assert args[1] == str(tmp_path.resolve())
        mock_run_screenshot.assert_not_called()
        out = capsys.readouterr().out
        assert "Mode       : text" in out
        assert "did the thing" in out

    def test_short_text_flag(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "argv", ["main.py", "-t", "rename x", "--dir", str(tmp_path)])
        with patch("agent.run_from_text", return_value=[]) as mock_run, \
             patch("agent.run"):
            if "main" in sys.modules:
                del sys.modules["main"]
            import main
            main.main()
        mock_run.assert_called_once()


class TestScreenshotMode:
    def test_screenshot_mode_calls_run(self, monkeypatch, tmp_path, capsys):
        screenshot = tmp_path / "shot.png"
        screenshot.write_bytes(b"\x89PNG")
        monkeypatch.setattr(sys, "argv", ["main.py", str(screenshot), "--dir", str(tmp_path)])
        with patch("agent.run", return_value=["extracted 2 issues"]) as mock_run, \
             patch("agent.run_from_text") as mock_run_text:
            if "main" in sys.modules:
                del sys.modules["main"]
            import main
            main.main()
        mock_run.assert_called_once()
        mock_run_text.assert_not_called()
        out = capsys.readouterr().out
        assert "Screenshot : shot.png" in out

    def test_missing_screenshot_exits(self, monkeypatch, tmp_path, capsys):
        nonexistent = tmp_path / "missing.png"
        monkeypatch.setattr(sys, "argv", ["main.py", str(nonexistent)])
        with patch("agent.run"), patch("agent.run_from_text"):
            if "main" in sys.modules:
                del sys.modules["main"]
            import main
            with pytest.raises(SystemExit) as exc:
                main.main()
            assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "not found" in err

    def test_no_input_at_all_exits(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["main.py"])
        with patch("agent.run"), patch("agent.run_from_text"):
            if "main" in sys.modules:
                del sys.modules["main"]
            import main
            with pytest.raises(SystemExit) as exc:
                main.main()
            assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "either a screenshot path or --text" in err


class TestDefaultDir:
    def test_dir_defaults_to_cwd(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["main.py", "--text", "x"])
        with patch("agent.run_from_text", return_value=[]) as mock_run, \
             patch("agent.run"):
            if "main" in sys.modules:
                del sys.modules["main"]
            import main
            main.main()
        # second arg is the resolved target_dir
        args, _ = mock_run.call_args
        assert args[1] == str(tmp_path.resolve())

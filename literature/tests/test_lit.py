"""Tests for the lit unified CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from literature.scripts.lit import run


class TestLitCLI:
    """Test the lit CLI entrypoint."""

    def test_no_args_prints_help(self, capsys):
        """Test that running with no args prints help and exits 0."""
        exit_code = run([])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower() or "lit" in captured.out.lower()

    def test_help_flag(self, capsys):
        """Test that --help flag works."""
        with pytest.raises(SystemExit) as exc_info:
            run(["--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "rebuild" in captured.out
        assert "search" in captured.out

    def test_all_subcommands_in_help(self, capsys):
        """Test that all 12 subcommands appear in help output."""
        with pytest.raises(SystemExit) as exc_info:
            run(["--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        help_text = captured.out

        subcommands = [
            "rebuild",
            "search",
            "paper",
            "recommend",
            "discover",
            "ask",
            "stats",
            "generate",
            "migrate",
            "add",
            "status",
            "ingest",
            "inbox",
        ]
        for cmd in subcommands:
            assert cmd in help_text, f"Subcommand '{cmd}' not found in help"

    def test_rebuild_stub(self, capsys, tmp_path):
        lit_dir = tmp_path / "literature"
        (lit_dir / "papers").mkdir(parents=True)
        (lit_dir / "resources").mkdir()
        (lit_dir / "AGENTS.md").write_text("# Test")
        exit_code = run(["rebuild"], root=lit_dir)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Rebuilt" in captured.out

    def test_search_runs(self, capsys):
        """Test that search subcommand returns 0."""
        exit_code = run(["search", "transformers"])
        assert exit_code == 0

    def test_paper_stub(self, capsys):
        """Test that paper subcommand returns 0 and prints stub message."""
        exit_code = run(["paper", "vaswani2017attention"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Not yet implemented" in captured.out

    def test_recommend_runs(self, capsys):
        exit_code = run(["recommend", "5"])
        assert exit_code == 0

    def test_ask_runs(self, capsys):
        exit_code = run(["ask", "what is attention?"])
        assert exit_code == 0

    def test_stats_stub(self, capsys):
        """Test that stats subcommand returns 0 and prints stub message."""
        exit_code = run(["stats"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Not yet implemented" in captured.out

    def test_generate_runs(self, capsys, tmp_path):
        """Test that generate subcommand returns 0 and generates LaTeX."""
        lit_dir = tmp_path / "literature"
        (lit_dir / "papers").mkdir(parents=True)
        (lit_dir / "themes").mkdir()
        (lit_dir / "output").mkdir()
        (lit_dir / "index").mkdir()
        (lit_dir / "templates").mkdir()
        (lit_dir / "AGENTS.md").write_text("# Test")
        
        # Copy templates
        import shutil
        src_templates = Path(__file__).parents[2] / "literature" / "templates"
        if (src_templates / "review_template.tex.j2").exists():
            shutil.copy2(src_templates / "review_template.tex.j2", lit_dir / "templates" / "review_template.tex.j2")
        if (src_templates / "neurips_2025.sty").exists():
            shutil.copy2(src_templates / "neurips_2025.sty", lit_dir / "templates" / "neurips_2025.sty")
        
        # Create empty bib file
        (lit_dir / "index" / "references.bib").write_text("% Empty\n")
        
        exit_code = run(["generate", "--title", "Test Survey", "--authors", "Test Author"], root=lit_dir)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Generated" in captured.out

    def test_unknown_subcommand_exits_nonzero(self, capsys):
        """Test that unknown subcommand raises SystemExit with nonzero code."""
        with pytest.raises(SystemExit) as exc_info:
            run(["invalid_cmd"])
        assert exc_info.value.code != 0

    def test_run_accepts_root_kwarg(self, tmp_path):
        """Test that run() accepts root kwarg without crashing."""
        # Create a minimal literature directory structure
        lit_dir = tmp_path / "literature"
        lit_dir.mkdir()
        (lit_dir / "AGENTS.md").write_text("# Test")

        # Should not crash when passing root
        exit_code = run(["stats"], root=lit_dir)
        assert exit_code == 0

    def test_discover_runs(self, capsys, tmp_path):
        """Test that discover subcommand runs and reports results."""
        lit_dir = tmp_path / "literature"
        (lit_dir / "papers").mkdir(parents=True)
        (lit_dir / "AGENTS.md").write_text("# Test")
        exit_code = run(["discover", "--source", "s2"], root=lit_dir)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Discovered" in captured.out

    def test_migrate_runs(self, capsys):
        """Test that migrate subcommand returns 0 and prints migration result."""
        exit_code = run(["migrate", "--from-v1"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Migration complete" in captured.out

    def test_add_stub(self, capsys):
        """Test that add subcommand returns 0 and prints stub message."""
        exit_code = run(["add", "https://arxiv.org/abs/1706.03762"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Not yet implemented" in captured.out

    def test_status_stub(self, capsys):
        """Test that status subcommand returns 0 and prints stub message."""
        exit_code = run(["status"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Not yet implemented" in captured.out

    def test_ingest_runs(self, capsys):
        exit_code = run(["ingest"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "papers need L4 summarization" in captured.out or "0 papers" in captured.out

    def test_inbox_runs(self, capsys, tmp_path):
        """Test that inbox subcommand runs and reports results."""
        lit_dir = tmp_path / "literature"
        (lit_dir / "papers").mkdir(parents=True)
        (lit_dir / "AGENTS.md").write_text("# Test")
        exit_code = run(["inbox"], root=lit_dir)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "No pending" in captured.out or "inbox" in captured.out.lower()

    def test_json_flag_accepted(self, capsys):
        """Test that --json flag is accepted without error."""
        exit_code = run(["--json", "stats"])
        assert exit_code == 0

    def test_root_flag_accepted(self, tmp_path, capsys):
        """Test that --root flag is accepted without error."""
        lit_dir = tmp_path / "literature"
        lit_dir.mkdir()
        (lit_dir / "AGENTS.md").write_text("# Test")

        exit_code = run(["--root", str(lit_dir), "stats"])
        assert exit_code == 0

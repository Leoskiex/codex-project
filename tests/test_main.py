from pathlib import Path

from scanner.main import read_symbols_file


def test_read_symbols_file_deduplicates_and_ignores_comments(tmp_path: Path) -> None:
    symbols_file = tmp_path / "symbols.txt"
    symbols_file.write_text("2330\n# comment\n2454\n2330\n\n2303\n", encoding="utf-8")

    assert read_symbols_file(str(symbols_file)) == ["2330", "2454", "2303"]

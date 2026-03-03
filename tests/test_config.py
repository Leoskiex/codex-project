from scanner.config import load_settings


def test_load_settings_parses_top_symbols(monkeypatch):
    monkeypatch.setenv("TOP_SYMBOLS", "2330.TW, 2317.TW,2330.TW")
    settings = load_settings()
    assert settings.top_symbols == ("2330.TW", "2317.TW")

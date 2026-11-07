from pathlib import Path


STATIC_DIR = Path(__file__).parents[1] / "app" / "static"


def test_frontend_uses_only_local_runtime_assets():
    index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert "https://" not in index
    assert '/static/vendor/chart.umd.min.js' in index
    assert (STATIC_DIR / "vendor" / "chart.umd.min.js").is_file()

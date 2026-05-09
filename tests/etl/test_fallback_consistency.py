"""
Test that all ETLs with fallback mechanisms have consistent, safe defaults.

This test enforces production safety by ensuring:
1. All ETLs default to ALLOW_FALLBACK_DATA=false
2. Fallback behavior is consistent across sources
3. Silent data degradation is prevented

Reference: CODEX_VALIDATION_FIX_REQUIRED.md (2025-11-29)
"""
import os


def test_strikes_etl_fallback_default_is_false():
    """Strikes ETL must default to ALLOW_FALLBACK_DATA=false for production safety."""
    # Remove env var to test default
    original = os.environ.pop("ALLOW_FALLBACK_DATA", None)

    try:
        # Force re-import to pick up env change
        import importlib
        import etl.public.strikes.strikes_etl

        importlib.reload(etl.public.strikes.strikes_etl)

        from etl.public.strikes.strikes_etl import ALLOW_FALLBACK_DATA

        assert ALLOW_FALLBACK_DATA is False, (
            "Strikes ETL must default to ALLOW_FALLBACK_DATA=false. "
            "Silent fallback to synthetic data in production is a safety violation."
        )
    finally:
        # Restore original env var
        if original is not None:
            os.environ["ALLOW_FALLBACK_DATA"] = original


def test_weather_etl_fallback_default_is_false():
    """Weather ETL must default to ALLOW_FALLBACK_DATA=false for production safety."""
    original = os.environ.pop("ALLOW_FALLBACK_DATA", None)

    try:
        import importlib
        import etl.public.weather.weather_etl

        importlib.reload(etl.public.weather.weather_etl)

        from etl.public.weather.weather_etl import ALLOW_FALLBACK_DATA

        assert (
            ALLOW_FALLBACK_DATA is False
        ), "Weather ETL must default to ALLOW_FALLBACK_DATA=false."
    finally:
        if original is not None:
            os.environ["ALLOW_FALLBACK_DATA"] = original


def test_fallback_defaults_are_consistent():
    """All ETLs with fallback must have consistent defaults."""
    original = os.environ.pop("ALLOW_FALLBACK_DATA", None)

    try:
        import importlib
        import etl.public.strikes.strikes_etl
        import etl.public.weather.weather_etl

        importlib.reload(etl.public.strikes.strikes_etl)
        importlib.reload(etl.public.weather.weather_etl)

        from etl.public.strikes.strikes_etl import ALLOW_FALLBACK_DATA as strikes_default
        from etl.public.weather.weather_etl import ALLOW_FALLBACK_DATA as weather_default

        assert strikes_default == weather_default, (
            f"Inconsistent fallback defaults: Strikes={strikes_default}, Weather={weather_default}. "
            "All ETLs must default to false for production safety."
        )
    finally:
        if original is not None:
            os.environ["ALLOW_FALLBACK_DATA"] = original


def test_fallback_explicit_false():
    """Test that ALLOW_FALLBACK_DATA=false is correctly parsed."""
    original = os.environ.get("ALLOW_FALLBACK_DATA")

    try:
        os.environ["ALLOW_FALLBACK_DATA"] = "false"

        import importlib
        import etl.public.strikes.strikes_etl

        importlib.reload(etl.public.strikes.strikes_etl)

        from etl.public.strikes.strikes_etl import ALLOW_FALLBACK_DATA

        assert (
            ALLOW_FALLBACK_DATA is False
        ), "ALLOW_FALLBACK_DATA='false' should result in False boolean"
    finally:
        if original is not None:
            os.environ["ALLOW_FALLBACK_DATA"] = original
        elif "ALLOW_FALLBACK_DATA" in os.environ:
            del os.environ["ALLOW_FALLBACK_DATA"]


def test_fallback_explicit_true():
    """Test that ALLOW_FALLBACK_DATA=true is correctly parsed (for development/testing)."""
    original = os.environ.get("ALLOW_FALLBACK_DATA")

    try:
        os.environ["ALLOW_FALLBACK_DATA"] = "true"

        import importlib
        import etl.public.strikes.strikes_etl

        importlib.reload(etl.public.strikes.strikes_etl)

        from etl.public.strikes.strikes_etl import ALLOW_FALLBACK_DATA

        assert (
            ALLOW_FALLBACK_DATA is True
        ), "ALLOW_FALLBACK_DATA='true' should result in True boolean"
    finally:
        if original is not None:
            os.environ["ALLOW_FALLBACK_DATA"] = original
        elif "ALLOW_FALLBACK_DATA" in os.environ:
            del os.environ["ALLOW_FALLBACK_DATA"]


def test_fallback_case_insensitive():
    """Test that ALLOW_FALLBACK_DATA parsing is case-insensitive."""
    original = os.environ.get("ALLOW_FALLBACK_DATA")

    test_cases = [
        ("True", True),
        ("TRUE", True),
        ("true", True),
        ("False", False),
        ("FALSE", False),
        ("false", False),
    ]

    try:
        for value, expected in test_cases:
            os.environ["ALLOW_FALLBACK_DATA"] = value

            import importlib
            import etl.public.strikes.strikes_etl

            importlib.reload(etl.public.strikes.strikes_etl)

            from etl.public.strikes.strikes_etl import ALLOW_FALLBACK_DATA

            assert (
                ALLOW_FALLBACK_DATA == expected
            ), f"ALLOW_FALLBACK_DATA='{value}' should result in {expected}"
    finally:
        if original is not None:
            os.environ["ALLOW_FALLBACK_DATA"] = original
        elif "ALLOW_FALLBACK_DATA" in os.environ:
            del os.environ["ALLOW_FALLBACK_DATA"]

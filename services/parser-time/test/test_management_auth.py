from lib.app import STATIC_DIR
from lib.interactor.use_cases import management_auth
from lib.interactor.use_cases.management_auth import management_auth_status


def test_missing_management_token_fails_closed_except_for_health() -> None:
    assert management_auth_status("/health", None, "") is None
    assert management_auth_status("/health/healthz", None, "") is None
    assert management_auth_status("/", None, "") == 503
    assert management_auth_status("/channels", None, "") == 503


def test_management_bearer_token_is_required_for_private_routes() -> None:
    assert management_auth_status("/channels", None, "admin-secret") == 401
    assert management_auth_status("/channels", "Basic admin-secret", "admin-secret") == 401
    assert management_auth_status("/channels", "Bearer wrong", "admin-secret") == 401
    assert management_auth_status("/channels", "Bearer admin-secret", "admin-secret") is None


def test_management_secret_uses_constant_time_comparison(monkeypatch) -> None:
    compared: list[tuple[str, str]] = []

    def compare(left: str, right: str) -> bool:
        compared.append((left, right))
        return left == right

    monkeypatch.setattr(management_auth.secrets, "compare_digest", compare)
    assert management_auth_status("/channels", "Bearer candidate", "configured") == 401
    assert compared == [("candidate", "configured")]


def test_ui_is_only_available_after_management_is_configured() -> None:
    assert management_auth_status("/", None, "") == 503
    assert management_auth_status("/", None, "admin-secret") is None
    assert management_auth_status("/docs", None, "admin-secret") is None
    assert management_auth_status("/static/app.js", None, "admin-secret") is None


def test_ui_does_not_persist_tokens_or_render_server_values_as_html() -> None:
    script = (STATIC_DIR / "app.js").read_text()
    assert "localStorage" not in script
    assert "innerHTML" not in script
    assert ".textContent" in script

import secrets

HEALTH_PATHS = frozenset({"/health", "/health/healthz"})
PUBLIC_UI_PATHS = frozenset(
    {"/", "/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
)


def management_auth_status(path: str, authorization: str | None, token: str) -> int | None:
    if path in HEALTH_PATHS:
        return None
    if not token:
        return 503
    if path in PUBLIC_UI_PATHS or path.startswith("/static/"):
        return None
    scheme, separator, supplied = (authorization or "").partition(" ")
    if not separator or scheme.lower() != "bearer":
        return 401
    return None if secrets.compare_digest(supplied.strip(), token) else 401

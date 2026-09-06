from lib.interactor.errors.base import BaseInteractorError


class SsrfBlockedError(BaseInteractorError, ValueError):
    status_code = 422
    code = "ssrf_blocked"

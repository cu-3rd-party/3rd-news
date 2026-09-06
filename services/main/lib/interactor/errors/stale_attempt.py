from lib.interactor.errors.base import BaseInteractorError


class StaleAttemptError(BaseInteractorError):
    status_code = 409
    code = "stale_attempt"

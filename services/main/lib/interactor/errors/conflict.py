from lib.interactor.errors.base import BaseInteractorError


class ConflictError(BaseInteractorError):
    status_code = 409
    code = "conflict"

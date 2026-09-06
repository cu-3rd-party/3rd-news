from lib.interactor.errors.base import BaseInteractorError


class ValidationError(BaseInteractorError):
    status_code = 422
    code = "validation_error"

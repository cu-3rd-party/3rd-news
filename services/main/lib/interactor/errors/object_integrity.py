from lib.interactor.errors.base import BaseInteractorError


class ObjectIntegrityError(BaseInteractorError, ValueError):
    status_code = 422
    code = "object_integrity_error"

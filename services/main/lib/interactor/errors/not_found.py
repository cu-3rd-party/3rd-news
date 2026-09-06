from lib.interactor.errors.base import BaseInteractorError


class NotFoundError(BaseInteractorError):
    status_code = 404
    code = "not_found"

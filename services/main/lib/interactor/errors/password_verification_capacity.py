from lib.interactor.errors.base import BaseInteractorError


class PasswordVerificationCapacityError(BaseInteractorError, RuntimeError):
    status_code = 503
    code = "password_verification_capacity"

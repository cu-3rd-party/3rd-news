from lib.interactor.errors.base import BaseInteractorError


class ClassifierProtocolError(BaseInteractorError):
    status_code = 502
    code = "classifier_protocol_error"

    def __init__(self, message: str, *, raw_body: bytes | None = None) -> None:
        self.raw_body = raw_body
        super().__init__(message)

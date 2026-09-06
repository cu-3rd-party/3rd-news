class BaseInteractorError(Exception):
    status_code = 500
    code = "service_error"

    def __init__(self, message: str = "service error") -> None:
        self.message = message
        super().__init__(message)

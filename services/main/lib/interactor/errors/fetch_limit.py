from lib.interactor.errors.base import BaseInteractorError


class FetchLimitError(BaseInteractorError, ValueError):
    status_code = 413
    code = "fetch_limit"

from lib.interactor.errors.base import BaseInteractorError


class SearchError(BaseInteractorError):
    status_code = 503
    code = "search_error"

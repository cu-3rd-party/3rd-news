from lib.interactor.errors.search import SearchError


class SearchNotReady(SearchError):
    code = "search_not_ready"

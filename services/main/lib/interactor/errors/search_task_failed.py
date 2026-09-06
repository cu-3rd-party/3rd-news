from lib.interactor.errors.search import SearchError


class SearchTaskFailed(SearchError):
    code = "search_task_failed"

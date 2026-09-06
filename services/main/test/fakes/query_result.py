from .scalar_rows import ScalarRows


class QueryResult:
    def __init__(self, values=()) -> None:
        self._values = values

    def scalars(self):
        return ScalarRows(self._values)

class ScalarRows:
    def __init__(self, values) -> None:
        self._values = list(values)

    def __iter__(self):
        return iter(self._values)

    def all(self):
        return list(self._values)

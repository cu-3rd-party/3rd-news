from .query_result import QueryResult


class FeedSession:
    async def scalar(self, statement):
        del statement
        return 0

    async def execute(self, statement):
        rendered = str(statement)
        if "FROM facets" in rendered:
            return QueryResult(["topic"])
        return QueryResult()

from types import SimpleNamespace


class SyntheticFetcher:
    async def fetch_bytes(self, url):
        del url
        return SimpleNamespace(body=b"Synthetic remote attachment", content_type="text/plain")

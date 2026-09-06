from urllib.request import urlopen

from ..core.config import get_settings


def main() -> None:
    port = get_settings().port
    with urlopen(f"http://127.0.0.1:{port}/health/healthz", timeout=3) as response:
        if response.status != 200:
            raise RuntimeError("parser is not healthy")

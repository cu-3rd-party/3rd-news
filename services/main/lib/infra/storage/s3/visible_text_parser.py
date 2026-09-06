from html.parser import HTMLParser

from lib.core.config import HTML_IGNORED_ELEMENTS


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in HTML_IGNORED_ELEMENTS:
            self.ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in HTML_IGNORED_ELEMENTS and self.ignored:
            self.ignored -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)

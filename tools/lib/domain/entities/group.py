from dataclasses import dataclass

from .post import Post


@dataclass
class Group:
    origin: Post
    copies: list[tuple[Post, float]]

    @property
    def channels(self) -> list[str]:
        return sorted(
            {post.source_key for post in [self.origin, *(item for item, _ in self.copies)]}
        )

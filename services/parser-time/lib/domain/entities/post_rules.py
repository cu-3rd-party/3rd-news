import re

SYSTEM_POST_PREFIX = "system_"
NEWS_CHANNEL_TYPES = frozenset({"O", "P"})
MAX_TITLE_LEN = 150
EMOJI_SHORTCODE = re.compile(r":[a-z][a-z0-9_+-]*:", re.IGNORECASE)
EMPHASIS = re.compile(r"[*_`~]+")
LEADING_NOISE = re.compile(r"^[\s>#\-–—•·]+")
EMPTY_MARKDOWN = re.compile(r"^[\s>#*_`~\-–—•·]*$")

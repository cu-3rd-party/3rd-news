PLAIN_MEMBER_ROLES = frozenset({"channel_user", "channel_guest"})


def has_posting_privileges(roles: set[str]) -> bool:
    return bool(roles - PLAIN_MEMBER_ROLES)

from lib.core.config import Settings


def main() -> None:
    password = Settings().bootstrap_admin_password
    if not password:
        raise SystemExit(1)
    print(password)

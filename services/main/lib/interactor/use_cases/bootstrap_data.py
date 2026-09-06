from __future__ import annotations

from lib.core.config import Settings
from lib.interactor.interfaces.clients.authentication import AuthenticationClient
from lib.interactor.interfaces.storage.bootstrap import BootstrapStorage


class BootstrapData:
    def __init__(
        self, settings: Settings, auth: AuthenticationClient, storage: BootstrapStorage
    ) -> None:
        self.settings = settings
        self.auth = auth
        self.storage = storage

    async def execute(self) -> None:
        password_hash = None
        if self.settings.bootstrap_admin_password:
            password_hash = self.auth.hash_password(self.settings.bootstrap_admin_password)
        elif self.settings.environment == "production":
            raise RuntimeError("bootstrap admin password is required in production")
        classifiers = []
        for raw in self.settings.bootstrap_classifiers:
            slug = str(raw.get("slug", "")).strip()
            endpoint = str(raw.get("endpoint", "")).rstrip("/")
            axes = raw.get("allowed_axes", [])
            config = raw.get("config", {})
            if not slug or not endpoint:
                raise RuntimeError("each bootstrap classifier needs slug and endpoint")
            if not isinstance(axes, list) or not all(isinstance(axis, str) for axis in axes):
                raise RuntimeError(f"bootstrap classifier {slug} has invalid allowed_axes")
            if not isinstance(config, dict):
                raise RuntimeError(f"bootstrap classifier {slug} has invalid config")
            classifiers.append(
                {
                    "slug": slug,
                    "name": str(raw.get("name") or slug),
                    "endpoint": endpoint,
                    "allowed_axes": axes,
                    "config": {str(key): value for key, value in config.items()},
                    "signing_public_key": str(raw["signing_public_key"])
                    if raw.get("signing_public_key")
                    else None,
                    "enabled": bool(raw.get("enabled", True)),
                    "shadow": bool(raw.get("shadow", False)),
                    "priority": int(str(raw.get("priority", 100))),
                    "min_confidence": float(str(raw.get("min_confidence", 0.5))),
                    "timeout_seconds": float(str(raw.get("timeout_seconds", 30))),
                }
            )
        await self.storage.initialize(
            admin_email=self.settings.bootstrap_admin_email,
            admin_password_hash=password_hash,
            classifiers=classifiers,
        )

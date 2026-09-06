import ipaddress
import socket

from aiohttp.abc import AbstractResolver, ResolveResult
from lib.dto.resolved_target import ResolvedTarget


class PinnedResolver(AbstractResolver):
    def __init__(self, target: ResolvedTarget) -> None:
        self.target = target

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        if host.rstrip(".").lower() != self.target.host:
            raise OSError("resolver was asked for an unvalidated host")
        result = []
        for address in self.target.addresses:
            ip = ipaddress.ip_address(address)
            result.append(
                ResolveResult(
                    hostname=host,
                    host=address,
                    port=port or self.target.port,
                    family=socket.AF_INET6 if ip.version == 6 else socket.AF_INET,
                    proto=0,
                    flags=socket.AI_NUMERICHOST,
                )
            )
        return result

    async def close(self) -> None:
        return None

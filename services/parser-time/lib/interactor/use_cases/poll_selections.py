import logging
from typing import Any

from ...domain.entities.channel_ref import ChannelRef
from ...domain.entities.run_result import RunResult
from ..errors.time_auth import TimeAuthError
from ..interfaces.clients.ingest import IngestGateway
from ..interfaces.clients.time import TimeGateway
from ..interfaces.storage.selection import SelectionStorage
from .channel_catalog import ChannelCatalog
from .poll_channel import PollPolicy, poll_channel

logger = logging.getLogger("thirdnews.parser.time")


class PollSelections:
    def __init__(
        self,
        storage: SelectionStorage,
        catalog: ChannelCatalog,
        policy: PollPolicy,
    ) -> None:
        self._storage = storage
        self._catalog = catalog
        self._policy = policy

    async def execute(
        self,
        time_client: TimeGateway,
        ingest_client: IngestGateway,
        only: ChannelRef | None = None,
        max_age_days: int | None = None,
        max_pages: int | None = None,
    ) -> dict[str, dict[str, Any]]:
        selections = self._storage.selected()
        if only is not None:
            selections = [selection for selection in selections if selection.key == only_key(only)]
        if not selections:
            return {}
        if any(selection.display_name is None for selection in selections):
            try:
                known = {
                    (channel["_team_name"], channel["name"]): channel
                    for channel in await self._catalog.fetch(time_client)
                }
                for selection in selections:
                    channel = known.get((selection.team, selection.channel))
                    if selection.display_name is None and channel:
                        self._storage.set_display_name(
                            selection.team,
                            selection.channel,
                            channel.get("display_name") or selection.channel,
                        )
            except Exception:
                logger.warning("не смог подставить названия каналов")
            selections = self._storage.selected() if only is None else selections
        results: dict[str, dict[str, Any]] = {}
        for selection in selections:
            ref = ChannelRef(team=selection.team, channel=selection.channel)
            try:
                created, duplicates, skipped = await poll_channel(
                    time_client,
                    ingest_client,
                    ref,
                    self._policy,
                    max_age_days=max_age_days,
                    max_pages=max_pages,
                    authors=selection.authors,
                )
                result = RunResult(created=created, duplicates=duplicates, skipped=skipped)
            except TimeAuthError as exc:
                self._storage.record_run(
                    selection.team,
                    selection.channel,
                    RunResult(error=str(exc)),
                )
                raise
            except Exception as exc:
                result = RunResult(error=str(exc)[:500])
            self._storage.record_run(selection.team, selection.channel, result)
            results[selection.key] = {
                "created": result.created,
                "duplicates": result.duplicates,
                "skipped": result.skipped,
                "error": result.error,
            }
        return results


def only_key(ref: ChannelRef) -> str:
    return f"{ref.team}/{ref.channel}"

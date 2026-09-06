from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..domain.entities.selection import Selection
from ..dto.select_in import SelectIn
from ..dto.selection_out import SelectionOut
from ..infra.resources import AppResources
from .common import parse_ref, resources_from


def selected_output(resources: AppResources) -> list[SelectionOut]:
    runs = resources.storage.runs()
    return [
        SelectionOut(
            team=selection.team,
            channel=selection.channel,
            display_name=selection.display_name,
            slug=selection.slug,
            added_at=selection.added_at,
            authors=selection.authors,
            last_run=run_output(runs[selection.key]) if selection.key in runs else None,
        )
        for selection in resources.storage.selected()
    ]


def run_output(result: Any) -> dict[str, Any]:
    return {
        "created": result.created,
        "duplicates": result.duplicates,
        "skipped": result.skipped,
        "error": result.error,
        "finished_at": result.finished_at,
    }


def create_router(holder: list[AppResources]) -> APIRouter:
    router = APIRouter(prefix="/channels/selected")

    @router.get("", response_model=list[SelectionOut])
    async def get_selected() -> list[SelectionOut]:
        return selected_output(resources_from(holder))

    @router.post("", response_model=list[SelectionOut])
    async def add_selected(payload: SelectIn) -> list[SelectionOut]:
        resources = resources_from(holder)
        async with resources.time_client() as client:
            known = {
                (channel["_team_name"], channel["name"]): channel
                for channel in await resources.catalog.fetch(client)
            }
        for value in payload.channels:
            ref = parse_ref(value)
            channel = known.get((ref.team, ref.channel))
            if channel is None:
                raise HTTPException(status_code=404, detail="канал не найден")
            resources.storage.add(
                Selection(
                    team=ref.team,
                    channel=ref.channel,
                    display_name=channel.get("display_name") or ref.channel,
                )
            )
        return selected_output(resources)

    @router.put("", response_model=list[SelectionOut])
    async def replace_selected(payload: SelectIn) -> list[SelectionOut]:
        resources = resources_from(holder)
        async with resources.time_client() as client:
            known = {
                (channel["_team_name"], channel["name"]): channel
                for channel in await resources.catalog.fetch(client)
            }
        selections: list[Selection] = []
        for value in payload.channels:
            ref = parse_ref(value)
            channel = known.get((ref.team, ref.channel))
            if channel is None:
                raise HTTPException(status_code=404, detail="канал не найден")
            selections.append(
                Selection(
                    team=ref.team,
                    channel=ref.channel,
                    display_name=channel.get("display_name") or ref.channel,
                )
            )
        resources.storage.replace_all(selections)
        return selected_output(resources)

    @router.delete("", status_code=204, response_model=None)
    async def remove_selected(channel: str = Query()) -> None:
        resources = resources_from(holder)
        ref = parse_ref(channel)
        if not resources.storage.remove(ref.team, ref.channel):
            raise HTTPException(status_code=404, detail="этот канал не выбран")

    @router.patch("", response_model=list[SelectionOut])
    async def set_authors(
        channel: str = Query(),
        authors: str = Query(pattern="^(privileged|all)$"),
    ) -> list[SelectionOut]:
        resources = resources_from(holder)
        ref = parse_ref(channel)
        if not resources.storage.set_authors(ref.team, ref.channel, authors):
            raise HTTPException(status_code=404, detail="этот канал не выбран")
        return selected_output(resources)

    return router

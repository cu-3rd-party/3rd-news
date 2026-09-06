from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query

from ..dto.channel_out import ChannelOut
from ..dto.channel_page import ChannelPage
from ..dto.team_out import TeamOut
from ..interactor.interfaces.clients.parser_application import ParserApplication
from .common import resources_from


def channel_out(channel: dict[str, Any], resources: ParserApplication) -> ChannelOut:
    team = str(channel["_team_name"])
    last_post = channel.get("last_post_at") or 0
    return ChannelOut(
        id=str(channel["id"]),
        team=team,
        name=str(channel["name"]),
        display_name=str(channel.get("display_name") or channel["name"]),
        purpose=channel.get("purpose") or None,
        header=channel.get("header") or None,
        type=str(channel.get("type", "O")),
        total_msg_count=int(channel.get("total_msg_count") or 0),
        last_post_at=datetime.fromtimestamp(last_post / 1000, tz=UTC) if last_post else None,
        selected=resources.selections().is_selected(team, str(channel["name"])),
        url=resources.channel_url(team, str(channel["name"])),
    )


def create_router(holder: list[ParserApplication]) -> APIRouter:
    router = APIRouter()

    @router.get("/teams", response_model=list[TeamOut])
    async def get_teams() -> list[TeamOut]:
        resources = resources_from(holder)
        return [
            TeamOut(
                id=str(team["id"]),
                name=str(team["name"]),
                display_name=str(team.get("display_name") or team["name"]),
            )
            for team in await resources.list_teams()
        ]

    @router.get("/channels", response_model=ChannelPage)
    async def get_channels(
        q: str | None = None,
        team: str | None = None,
        only_selected: bool = False,
        only_joined: bool = False,
        only_with_posts: bool = True,
        active_within_days: int | None = Query(default=None, ge=1),
        sort: str = Query(default="activity", pattern="^(activity|messages|name)$"),
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        refresh: bool = False,
    ) -> ChannelPage:
        resources = resources_from(holder)
        channels = await resources.list_channels(refresh=refresh)
        if team:
            channels = [channel for channel in channels if channel["_team_name"] == team]
        if only_joined:
            channels = [channel for channel in channels if channel["_joined"]]
        if only_with_posts:
            channels = [
                channel for channel in channels if int(channel.get("total_msg_count") or 0) > 0
            ]
        if active_within_days:
            cutoff = (datetime.now(UTC) - timedelta(days=active_within_days)).timestamp() * 1000
            channels = [
                channel for channel in channels if int(channel.get("last_post_at") or 0) >= cutoff
            ]
        if q:
            needle = q.casefold()
            channels = [
                channel
                for channel in channels
                if needle in str(channel["name"]).casefold()
                or needle in str(channel.get("display_name") or "").casefold()
                or needle in str(channel.get("purpose") or "").casefold()
            ]
        if only_selected:
            channels = [
                channel
                for channel in channels
                if resources.selections().is_selected(
                    str(channel["_team_name"]), str(channel["name"])
                )
            ]
        if sort == "name":
            channels.sort(key=lambda item: str(item.get("display_name") or item["name"]).casefold())
        elif sort == "messages":
            channels.sort(key=lambda item: int(item.get("total_msg_count") or 0), reverse=True)
        else:
            channels.sort(key=lambda item: int(item.get("last_post_at") or 0), reverse=True)
        page = channels[offset : offset + limit]
        return ChannelPage(
            items=[channel_out(channel, resources) for channel in page],
            total=len(channels),
            limit=limit,
            offset=offset,
        )

    return router

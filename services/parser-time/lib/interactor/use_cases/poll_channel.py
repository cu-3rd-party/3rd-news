import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from thirdnews_contracts import AttachmentInput, IngestError

from ...domain.entities.channel_ref import ChannelRef
from ...domain.entities.poll_policy import PollPolicy
from ...domain.entities.roles import has_posting_privileges
from ..interfaces.clients.ingest import IngestGateway
from ..interfaces.clients.time import TimeGateway
from .post_conversion import attachment_kind, created_at, post_files, post_to_submission

logger = logging.getLogger("thirdnews.parser.time")


async def collect_files(
    time_client: TimeGateway,
    ingest_client: IngestGateway,
    post: dict[str, Any],
    max_attachment_bytes: int,
) -> list[AttachmentInput]:
    uploads: list[AttachmentInput] = []
    for item in post_files(post):
        file_id = item.get("id")
        if not file_id:
            continue
        if int(item.get("size") or 0) > max_attachment_bytes:
            continue
        data = await time_client.download_file(str(file_id), max_attachment_bytes)
        if data is None:
            continue
        filename = str(item.get("name") or file_id)
        mime = str(item.get("mime_type") or "application/octet-stream")
        completed = await ingest_client.upload(filename, mime, data)
        uploads.append(
            AttachmentInput(
                kind=attachment_kind(mime, item.get("extension")),
                upload_intent_id=completed.upload_id,
                filename=filename,
                mime=mime,
            )
        )
    return uploads


async def poll_channel(
    time_client: TimeGateway,
    ingest_client: IngestGateway,
    ref: ChannelRef,
    policy: PollPolicy,
    *,
    max_age_days: int | None = None,
    max_pages: int | None = None,
    authors: str | None = None,
) -> tuple[int, int, int]:
    channel = await time_client.resolve_channel(ref)
    channel_title = channel.get("display_name") or ref.channel
    posts = await time_client.fetch_posts(
        channel["id"],
        policy.posts_per_page,
        max_pages if max_pages is not None else policy.max_pages,
    )
    window = max_age_days if max_age_days is not None else policy.max_age_days
    cutoff = datetime.now(UTC) - timedelta(days=window)
    created = 0
    duplicates = 0
    skipped = 0
    author_names: dict[str, str | None] = {}
    privileged: dict[str, bool] = {}

    async def may_post(user_id: str) -> bool:
        if (authors if authors is not None else policy.authors) != "privileged":
            return True
        if user_id not in privileged:
            privileged[user_id] = has_posting_privileges(
                await time_client.channel_member_roles(channel["id"], user_id)
            )
        return privileged[user_id]

    for post in posts:
        published = created_at(post)
        if published and published < cutoff:
            skipped += 1
            continue
        user_id = post.get("user_id")
        if user_id and not await may_post(str(user_id)):
            skipped += 1
            continue
        if user_id and user_id not in author_names:
            author_names[str(user_id)] = await time_client.user_display_name(str(user_id))
        submission = post_to_submission(
            post,
            ref=ref,
            channel_title=str(channel_title),
            base_url=time_client.base_url,
            author=author_names.get(str(user_id or "")),
            include_replies=policy.include_replies,
        )
        if submission is None:
            skipped += 1
            continue
        if policy.download_attachments and post_files(post):
            submission.attachments = await collect_files(
                time_client,
                ingest_client,
                post,
                policy.max_attachment_bytes,
            )
        try:
            result = await ingest_client.submit(submission)
        except IngestError as exc:
            logger.warning("не смог отправить пост %s: HTTP %d", post.get("id"), exc.status_code)
            continue
        if result.status.value == "accepted":
            created += 1
        else:
            duplicates += 1
    return created, duplicates, skipped

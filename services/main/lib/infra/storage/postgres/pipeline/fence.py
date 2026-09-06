from lib.dto.claimed_attempt import ClaimedAttempt
from lib.infra.storage.postgres.models import Job, News


class PipelineFence:
    def matches(self, job: Job | None, claimed: ClaimedAttempt) -> bool:
        return bool(
            job is not None
            and job.current_attempt_id == claimed.attempt_id
            and job.generation == claimed.generation
            and job.status in {"running", "waiting_callback"}
        )

    def matches_news(self, news: News, job: Job) -> bool:
        expected = job.payload.get("pipeline_attempt_id")
        return expected is None or str(news.current_attempt_id) == str(expected)

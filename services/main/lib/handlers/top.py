from fastapi import APIRouter

from lib.handlers.admin_api_keys import router as admin_api_keys_router
from lib.handlers.admin_classifiers import router as admin_classifiers_router
from lib.handlers.admin_contexts import router as admin_contexts_router
from lib.handlers.admin_delivery import router as admin_delivery_router
from lib.handlers.admin_editorial_rules import router as admin_editorial_rules_router
from lib.handlers.admin_gold_export import router as admin_gold_export_router
from lib.handlers.admin_merge_split import router as admin_merge_split_router
from lib.handlers.admin_news_lifecycle import router as admin_news_lifecycle_router
from lib.handlers.admin_news_review import router as admin_news_review_router
from lib.handlers.admin_sources import router as admin_sources_router
from lib.handlers.admin_taxonomy import router as admin_taxonomy_router
from lib.handlers.auth import router as auth_router
from lib.handlers.batch import router as batch_router
from lib.handlers.callbacks import router as callbacks_router
from lib.handlers.feed import router as feed_router
from lib.handlers.health import router as health_router
from lib.handlers.media import router as media_router
from lib.handlers.news_detail import router as news_detail_router
from lib.handlers.raw_audit import router as raw_audit_router
from lib.handlers.rss import router as rss_router
from lib.handlers.submissions import router as submissions_router
from lib.handlers.uploads import router as uploads_router

router = APIRouter()
for child in (
    auth_router,
    health_router,
    submissions_router,
    batch_router,
    uploads_router,
    feed_router,
    news_detail_router,
    rss_router,
    media_router,
    admin_news_lifecycle_router,
    admin_news_review_router,
    admin_merge_split_router,
    admin_gold_export_router,
    admin_taxonomy_router,
    admin_sources_router,
    admin_api_keys_router,
    admin_classifiers_router,
    admin_editorial_rules_router,
    admin_contexts_router,
    admin_delivery_router,
    callbacks_router,
    raw_audit_router,
):
    router.include_router(child)

# Resolution evidence for the second independent review

Date: 2026-09-06

This document records the disposition of the 20 findings in
[the immutable second-review report](review-second-independent.md). It describes the
post-review worktree; it does not rewrite the original findings.

| # | Severity | Result | Production change | Verification evidence |
| --- | --- | --- | --- | --- |
| 1 | Critical | Fixed | `IngestClient` sends issued credentials in `X-API-Key`, matching the main API dependency. | `test_ingest_client_uses_the_server_api_key_header`; contracts 16/16. A final-image live run issued a temporary key, submitted news, uploaded/attached a Garage object, revoked the key, and then observed denial. |
| 2 | High | Fixed | TiMe builds untrusted UI values with text nodes, keeps its token only in memory, and serves CSP, nosniff, and referrer protections. | `test_ui_does_not_persist_tokens_or_render_server_values_as_html`; TiMe 36/36. |
| 3 | High | Fixed | Successful remote fetches finish as `stored`; detail and the search attachment flag use the same available-object condition. | PostgreSQL `test_remote_attachment_is_stored_visible_and_indexed`. |
| 4 | High | Fixed | Classifier policy updates/deletion enqueue durable rematerialization, close the visibility barrier, recompute winners, and advance projections. | PostgreSQL `test_classifier_policy_change_closes_barrier_and_rematerializes_history` covers shadow, confidence, deletion, key preservation, and the barrier. |
| 5 | High | Fixed | Transient outbox failures retry indefinitely with bounded backoff; locally invalid payloads enter an explicit quarantine. Broker `ValueError` remains retryable. | PostgreSQL `test_outbox_recovers_automatically_after_more_than_old_retry_budget`, `test_invalid_outbox_is_visibly_quarantined_without_publishing`, and `test_broker_value_error_is_retried_instead_of_quarantined`. |
| 6 | High | Fixed | Taxonomy rematerialization discovers affected news from immutable opinions, so re-enabling a facet/value restores effective labels. | PostgreSQL `test_taxonomy_disable_enable_uses_immutable_opinions`. |
| 7 | High | Fixed | Manual set, explicit-empty, and release operations append `ManualLabelDecision` rows. Merge/split copies opinion and decision provenance. | PostgreSQL `test_empty_manual_axis_suppresses_automatic_values_until_released` and `test_merge_and_split_move_attachments_and_copy_opinion_provenance`; migration `d4a7c9e12b3f`. |
| 8 | High | Fixed | Production requires a public HTTPS file endpoint and rejects the localhost/insecure defaults. All four production roles receive the validated setting. | `test_production_settings.py`; the final settings group is 13/13. |
| 9 | High | Fixed | Login and token share durable HMAC-keyed account/IP buckets, atomic failure updates, exponential cooldown, threaded bounded Argon2, and a hard pending queue cap. Forwarded addresses are accepted only from exact configured proxy hosts. | Unit tests cover normalization, bounded concurrency, cancellation, queue capacity, and forged/trusted forwarding. PostgreSQL tests cover durable blocking, skipped Argon2 while blocked, and eight concurrent failures without lost updates. |
| 10 | High | Fixed | `api.setLabels` normalizes the mutation response before Review replaces its item. | Pinned Bun 1.4.2: three tests pass, including a direct mocked `api.setLabels` call and its rerender shape; `tsc` and Vite production build pass. |
| 11 | High | Fixed | Classifier PATCH uses only explicitly supplied fields; key removal/rotation is explicit, so ordinary toggles preserve the signing key. | `test_classifier_patch_omits_signing_key_and_unset_fields` and the stable-key assertion in the classifier-policy PostgreSQL test. |
| 12 | High | Fixed | The ingest contract recursively rejects NUL/unsafe control characters, SQLAlchemy hides bound values, and generic error logging omits exception text. | Contract malicious-control cases; `test_database_errors_hide_unique_bound_parameters`; `test_unhandled_exception_log_never_contains_exception_secret`. |
| 13 | Medium | Fixed | Presign quota uses an advisory lock; object GC removes expired unused intents and old orphan objects while retaining owned/current objects. | PostgreSQL `test_gc_removes_expired_and_orphan_objects_but_keeps_owned` and `test_upload_quota_is_enforced_before_s3_presign`. Real Garage also rejected a wrong signed content length with 403 and accepted the exact length with 200. |
| 14 | Medium | Fixed | Value changes advance one canonical monotonic taxonomy revision, used by delivery and classifier requests. | PostgreSQL `test_value_change_advances_one_canonical_taxonomy_revision` plus the disable/re-enable revision assertion. |
| 15 | Medium | Fixed | Classifier requests use a bounded database selection of non-gold manual examples with provenance/privacy eligibility; the admin context reports real settings and counts. | PostgreSQL `test_pipeline_uses_bounded_non_gold_manual_examples` and `test_gold_news_is_never_injected_as_a_classifier_example`. |
| 16 | Medium | Fixed | Pipeline dispatch applies `min(node timeout, global maximum)` around each classifier call. | `test_node_deadline_cancels_dispatch_and_records_retry`; the examples integration test also asserts the selected node timeout. |
| 17 | Medium | Fixed | Editorial-rule writes enqueue a durable global job; `RematerializationWorker` processes bounded chunks while the public visibility barrier remains closed. | PostgreSQL `test_rematerialization_advances_in_bounded_chunks` and `test_rule_revision_and_manual_empty_recalculate_scores`. |
| 18 | Medium | Fixed | API-key authentication touches `last_used_at` through a separate throttled atomic transaction and never commits unrelated request-session changes. | PostgreSQL `test_api_key_usage_is_committed_separately_and_throttled`. |
| 19 | Medium | Fixed | RSS startup fails on missing runtime configuration; the poller is supervised and readiness is 503 until a complete successful cycle. Compose checks `/health/ready`. | `test_ready_returns_503_before_a_successful_poll_cycle`, `test_missing_runtime_configuration_fails_startup`, and `test_readiness_tracks_the_last_complete_poll_cycle`; RSS 11/11. |
| 20 | Medium | Fixed | Production requires a valid high-entropy raw-audit key; the environment is a strict development/testing/production literal, so an unknown value cannot bypass production boundaries. | `test_production_settings.py`, including `test_unknown_environment_cannot_bypass_production_boundaries`; final group 13/13. |

## Independent post-fix gates

- The migration chain `bc8bbbb844d7 -> d4a7c9e12b3f -> e5b8c1d4f6a2` was applied to a
  freshly recreated isolated PostgreSQL 18 database. `alembic check` reported no model
  drift; Squawk reported no issues for the new upgrade and downgrade SQL.
- The final PostgreSQL run after the provenance, disabled-manual-facet, and outbox residual
  changes passed all 50 integration tests; 92 non-integration tests were deselected.
- The final repository unit gate passed all 258 selected Python tests across its seven
  independent locked environments.
- `make lint` initially exposed 37 unresolved `tools.*` imports in basedpyright when the
  project was checked from its own directory. Adding an explicit parent `extraPaths`
  repaired the gate; the repeated full Ruff, ty, and basedpyright run passed every project
  with zero type errors.

The final-image Compose smoke and authenticated shared-client replay passed. The in-app
browser could not open the localhost proxy (`ERR_BLOCKED_BY_CLIENT`), so only the
browser-driven UI replay remains a limitation; it is tracked in [the QA report](qa-report.md).

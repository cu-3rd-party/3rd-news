# QA report for the v2 rewrite

Date: 2026-09-06

This report covers independent verification of the rewritten services and migration of
valuable legacy tests. All database tests used only the isolated PostgreSQL instance at
`127.0.0.1:15432/news`. Live infrastructure checks used temporary QA subjects, objects,
and indexes in the `thirdnews-v2` Compose project and cleaned them afterwards.

## Automated results

| Scope | Command | Result |
| --- | --- | --- |
| Main unit and policy | `cd services/main && PYTHONPATH=. .venv/bin/pytest -m 'not integration and not e2e' -q` | 92 passed, 50 deselected |
| Main PostgreSQL integration | `cd services/main && TEST_DB_SCHEME=postgresql+asyncpg TEST_DB_HOST=127.0.0.1 TEST_DB_PORT=15432 TEST_DB_NAME=news TEST_DB_USER=news TEST_DB_PASSWORD=isolated-test-only PYTHONPATH=. .venv/bin/pytest -m integration -q` | 50 passed, 92 deselected |
| Domain mutation | `cd services/main && PYTHONPATH=. .venv/bin/pytest --gremlins --gremlin-targets=lib/domain --gremlin-report=json test/test_domain.py` | 20/20 killed |
| AI classifier | `cd services/classifier-ai && .venv/bin/pytest -q` | 15 passed |
| Regex classifier | `cd services/classifier-regex && .venv/bin/pytest -q` | 9 passed |
| RSS parser | `cd services/parser-rss && .venv/bin/pytest -q` | 12 passed |
| TiMe parser | `cd services/parser-time && .venv/bin/pytest -q` | 36 passed |
| Shared contracts | `cd packages/python/contracts && .venv/bin/pytest -q` | 16 passed |
| Corpus, evaluation, taxonomy tools | `cd tools && .venv/bin/pytest -q` | 78 passed |
| Tools lint and types | `cd tools && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/ty check && .venv/bin/basedpyright` | passed; 0 type errors |
| All lint and types | `make lint` | passed: Ruff format/check, ty, and basedpyright in every selected project |

The repository-level `make test` was exercised again after upgrading and regenerating the
changed lockfiles. It passed all 258 selected tests across the seven independent locked
environments on Python 3.14.7 and pytest 9.1.1.

## Live infrastructure evidence

- A temporary admin-issued ingest key authenticated the shared `IngestClient` with
  `X-API-Key`; real submit plus presign/PUT/complete stored and attached synthetic bytes.
  Revocation then made the same client receive HTTP 401. The script revoked the key in
  `finally` and emitted no credential or payload content.
- NATS JetStream deduplication returned the same stream sequence for two publishes with
  one message ID. A handler failure produced a NAK followed by redelivery counts `[1, 2]`.
- A second live JetStream run exhausted an application retry budget and simulated failure
  of the first DLQ publish. Deliveries were `[1, 2, 3, 4]`; the retry wrote exactly one
  identifiers-only DLQ record and only then acknowledged the original message
  (`ack_pending=0`). The server-side durable had unlimited delivery, so a broker cap could
  not strand the event before its failure record became durable. The final rebuilt image
  also unsubscribed and drained cleanly without the earlier shutdown timeout.
- Garage accepted a private 28-byte object, returned matching size and SHA-256 metadata,
  served the requested byte range as `b"garage"`, and deleted the object.
- The current Meilisearch client consumed an async document stream, atomically replaced a
  unique two-document QA index, and returned only `qa-visible` for the combined
  `status = published` and `source = qa-source` filters. The `source` facet count was one;
  the temporary index was deleted.
- Both rebuilt classifier containers returned HTTP 200 and `ready` through aiohttp on the
  internal Compose network.
- A real shared `IngestClient` used a temporary API key issued by the main service, submitted
  a news item, uploaded and attached a Garage object, and was denied after the key was
  revoked. The client sent the key through `X-API-Key`; no secret was printed.
- The final-image Compose smoke passed in 16.91 seconds: authenticated admin and taxonomy,
  signed AI and regex classification, presign/complete/promotion, idempotent replay and
  conflict, batch isolation, outbox/NATS/pipeline, Meilisearch projection, media GET/HEAD/
  Range, negative ACL cases, RSS, and session revocation. The evidence is retained in
  `docs/verification/compose-smoke.json`.
- SHA-256 hashes for the rebuilt API container exactly matched the workspace versions of
  `consumer.py`, `labels.py`, `coordinator.py`, `object_store.py`, `indexer.py`, and
  `workers.py`, excluding a stale local-wheel cache as the source of the final live result.

## Small queue load sample

Two Compose queue runs each accepted and published 20 of 20 items at ingest concurrency
10. With one pipeline worker, wall time was 11.199 seconds, throughput was 1.786 items/s,
and pipeline p95 was 11,196 ms. With four workers, the corresponding values were 11.265
seconds, 1.775 items/s, and 11,260 ms. This small sample demonstrates correctness under
concurrent submission but no scaling improvement; the configured pipeline cooldown
dominates its latency. Both samples deliberately used `skip_classification=true`, so these
numbers exclude classifier and AI latency and must not be presented as end-to-end model
capacity. A point-in-time four-worker snapshot showed 85.7–95.8 MiB per pipeline worker.

The same run rejected unauthenticated ingest with 401, a revoked API key with 401, and a
cookie-authenticated state change without CSRF with 403.

## Behaviors covered by the new main tests

- concurrent idempotent ingest creates one aggregate and returns accepted plus duplicate;
- inbox rollback permits safe redelivery and concurrent delivery applies a callback once;
- outbox leases prevent double publish and permit takeover after a failed publisher;
- exhausted consumer delivery writes an identifiers-only failure record, uses bounded NAK
  backoff, and leaves the original unacknowledged when the DLQ itself is unavailable;
- pipeline claims use `SKIP LOCKED`, stale generations are fenced, expired attempts are
  recorded, and exhausted jobs reach dead-letter state;
- bearer authentication uses current database activation and role scopes;
- login and token failures are durably limited by normalized account and client-IP
  identifiers; Argon2 runs outside the event loop with bounded concurrency and a hard
  queue cap, cancelled checks retain their slot until the thread exits, and blocked
  requests do not consume another Argon2 slot; forged forwarded IPs are ignored unless
  the immediate peer resolves from the configured proxy hostname;
- API-key `last_used_at` is committed in a separate throttled atomic transaction without
  committing unrelated handler state; browser login no longer persists unused raw client
  IP and User-Agent metadata;
- opinions remain auditable, source defaults outrank automatic labels, only the highest
  priority classifier wins a single facet, shadow opinions never materialise, a newer
  empty classifier result revokes its previous values, and an empty manual axis remains
  authoritative until released;
- failed attachment children end the parent in `needs_review` while preserving child and
  failure identifiers, and a source with `skip_classification` creates no classifier jobs;
- a visibility change during streamed full reindex leaves the projection pending and feed
  readiness fails closed; full reindex also creates checkpoints for previously unseen news;
- the inbox search-event path creates a fresh projection safely and never lowers its
  requested revision;
- gold export filtering, batch marking, and audit records work against PostgreSQL, while
  gold news is never inserted into classifier examples;
- classifier calls use the pinned, bounded `post_bytes` transport and propagate oversized
  response failures without a fallback client;
- upload completion rejects a same-size replacement made after the temporary object was
  hashed, re-hashes the final copy, and deletes that copy on mismatch;
- unsafe URL syntax, private or mixed DNS answers, chunked oversize bodies, non-finite
  outbox values, media range parsing, HTML text extraction, and authenticated media routes
  have focused regression coverage;
- DOCX extraction permits a normal bounded document but rejects excessive compression,
  forged oversized member declarations, and streams that exceed the extraction cap; the
  parser runs in a child process with memory/CPU limits and the Linux timeout/cancel smoke
  completed with zero event-loop exception-handler errors;
- ingest rejects NUL and unsafe control characters before PostgreSQL, SQLAlchemy hides
  bound parameters, and the generic exception logger never records exception text; unique
  secret markers were absent from both database exception strings and captured logs;
- repository policy verifies the required service layout, migration/table parity, and the
  global absence of `httpx`, `httpx2`, and `TestClient` in source and configuration files.

## Legacy coverage migration

The former root `tests/` suite was removed after its maintained scenarios moved to each
owner's singular test directory. Parser, classifier, and contract cases now live beside
their projects. Corpus, evaluation, and taxonomy tests plus their fixtures live under
`tools/test`. Obsolete v1 multipart and HTTP transport tests were replaced by v2 contract,
presigned-object, aiohttp boundary, and live infrastructure checks. The root `pytest.ini`
that selected the removed suite was deleted.

## Defects found during QA

The following defects were reproduced during the review and fixed in the shared working
tree before the green results above:

- concurrent ingest raised `IntegrityError` from an early flush outside its recovery path;
- JWT bearer scopes and activation could remain valid after a database role/state change;
- effective-label origin priorities were reversed;
- classifier POST used a separate unpinned HTTP connection after URL validation and read
  responses without a size limit;
- outbox validation accepted non-finite JSON numbers;
- Meilisearch omitted `source` from filterable attributes, causing live feed HTTP 500;
- full reindex accumulated every document in memory and lacked coherent visibility
  checkpoint behavior during concurrent changes;
- classifier containers requested unavailable uvloop and restarted continuously;
- the evaluation loader referenced deleted `services/classifier-*/app/main.py` paths;
- two classifier attempts for one news row each acquired a foreign-key key-share lock and
  then upgraded it with `FOR UPDATE`, causing a PostgreSQL deadlock that terminated the
  worker task group. The regression synchronizes both inserts and verifies both claims.
- classifier opinion keys did not resolve attempt-suffixed identities, shadow results could
  participate in materialization, ties could violate single-facet cardinality, and a newer
  empty response did not revoke the prior attempt's opinion;
- failed attachment children were discarded before finalization and could permit publish;
  `Source.skip_classification` was ignored;
- upload completion hashed the temporary object before a separate copy but checked only
  final size, allowing a same-size replacement between those operations;
- exhausted JetStream deliveries could become unavailable before any durable failure record;
- the first search event and full reindex checkpoint used an unmaterialized SQLAlchemy
  default as an integer, raising `TypeError` for news without a projection;
- AI provider failures were encoded as completed results instead of structured failed
  contract responses;
- TiMe management routes were accessible when its bearer token was empty.

## Remaining limitations

The in-app browser returned `ERR_BLOCKED_BY_CLIENT` for the localhost proxy, so a
browser-driven UI E2E remains unverified; the frontend mutation regression and production
build passed in the pinned Bun container. Large-volume performance and long-running lease
recovery were outside this run. The final Compose smoke did execute the complete
authenticated API path through real AI and regex classifiers, outbox, NATS, pipeline,
Meilisearch, Garage/media delivery, RSS, and revocation. This proves functional wiring on
the final images; it is not a quality measurement on a labelled corpus.

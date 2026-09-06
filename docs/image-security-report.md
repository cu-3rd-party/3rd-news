# Проверка безопасности core-образа

Дата проверки: 2026-09-06. Образ: `thirdnews-v2-core`, Debian 13.6
(`trixie`), arm64, image ID
`sha256:506340cc43fc2e783d3d6dc54922c01582c8ddc7212755971e611fabd1cb326f`.

## Воспроизводимость

Исходный отчёт Grype 0.116.1 находится в
`/private/tmp/thirdnews-core-image-audit.json`; SHA-256 файла:
`e4710bb187cb99f0ab0dcd75d901f3312f78512081c804959900b301f89791d1`.
База Grype валидна, собрана `2026-09-05T06:27:00Z`; Debian provider захвачен
`2026-09-05T00:32:09Z`. Скан выполнен `2026-09-06T02:13:43+03:00`.

Скан содержит 169 совпадений: 7 Critical, 57 High, 46 Medium, 7 Low,
44 Negligible и 8 Unknown. Это 84 уникальных CVE: 6 Critical, 20 High,
27 Medium, 4 Low, 23 Negligible и 4 Unknown. Разница объясняется тем, что одна
уязвимость исходного пакета сопоставляется нескольким бинарным Debian-пакетам.
Например, один util-linux CVE создаёт до девяти строк, а glibc CVE — две.

Эфемерная проверка `apt-get update; apt list --upgradable` от root внутри
образа не показала доступных обновлений. Установлены `libc6/libc-bin
2.41-12+deb13u3`, `perl-base 5.40.1-6`, `libsqlite3-0 3.46.1-7+deb13u1` и
`zlib1g 1:1.3.dfsg+really1.3.1-1+b1`.

## Critical

Все семь Critical-совпадений имеют Grype fix state `wont-fix`; доступной
исправленной версии для Trixie сейчас нет. `wont-fix` здесь не означает
ложное срабатывание: Debian считает версии уязвимыми, но откладывает исправление
или не выпускает DSA из-за собственной оценки срочности.

| CVE | Пакет | Debian | Применимость к сервису |
| --- | --- | --- | --- |
| [CVE-2026-5450](https://security-tracker.debian.org/tracker/CVE-2026-5450) | `libc6`, `libc-bin` | Trixie vulnerable, `<no-dsa>`, minor | Требует вызова scanf `%mc` с явной шириной больше 1024. Код и Python-зависимости сервиса не формируют такой формат из входных данных. Низкая достижимость, но библиотека загружена и CVE остаётся открытым. |
| [CVE-2026-8376](https://security-tracker.debian.org/tracker/CVE-2026-8376) | `perl-base` | Trixie vulnerable, `<no-dsa>`, minor | Переполнение существует только на 32-bit. Проверенный образ arm64; неприменимо к этой сборке. |
| [CVE-2026-13221](https://security-tracker.debian.org/tracker/CVE-2026-13221) | `perl-base` | Trixie vulnerable | Требует компиляции Perl-regex с более чем 65535 ветвями. Сервис не запускает Perl; внешний regex-классификатор использует Python `re`. Недостижимо в текущем runtime-пути. |
| [CVE-2026-42496](https://security-tracker.debian.org/tracker/CVE-2026-42496) | `perl-base` | Trixie vulnerable, postponed as minor | Требует распаковки недоверенного архива через Perl `Archive::Tar`. Сервис не запускает Perl и не использует `Archive::Tar`; недостижимо. |
| [CVE-2026-12087](https://security-tracker.debian.org/tracker/CVE-2026-12087) | `perl-base` | Trixie vulnerable | Требует прямого вызова уязвимой функции Perl Socket. Perl не входит в process tree приложения; недостижимо. |
| [CVE-2026-57433](https://security-tracker.debian.org/tracker/CVE-2026-57433) | `perl-base` | Trixie vulnerable, `<no-dsa>`, minor | Требует десериализации специально созданного Storable/SX_HOOK. Приложение не использует Perl Storable; недостижимо. |

## High

Из 57 High-совпадений 56 имеют `wont-fix`; единственное `not-fixed` —
[CVE-2026-85091](https://security-tracker.debian.org/tracker/CVE-2026-85091) в
zlib. Debian пока не имеет исправленной версии даже в unstable. Ошибка требует
неблокирующего `gzwrite()` с последующим `gzprintf()`/`gzvprintf()`. Приложение
не вызывает эти API: aiohttp использует zlib для HTTP compression, а обработчик
DOCX — Python `zipfile`. Поэтому известный trigger не достижим, но CVE нужно
оставить в реестре до обновления Debian/Python base.

Остальные High сгруппированы по одинаковой границе достижимости:

- `libsqlite3-0`: [CVE-2026-11822](https://security-tracker.debian.org/tracker/CVE-2026-11822)
  и [CVE-2026-11824](https://security-tracker.debian.org/tracker/CVE-2026-11824)
  требуют FTS5-запроса к недоверенной SQLite DB. Сервис использует PostgreSQL и
  Meilisearch, `sqlite3` не импортируется.
- `util-linux` и его бинарные пакеты: CVE-2026-76642, CVE-2026-78408,
  CVE-2026-78409, CVE-2026-78410. Это mount/post-mount сценарии. Контейнер
  работает как UID 10001, с `no-new-privileges`, `cap_drop: ALL`, read-only
  filesystem; приложение не запускает mount helpers. Debian также оценивает
  [CVE-2026-76642](https://security-tracker.debian.org/tracker/CVE-2026-76642)
  как minor/no-DSA.
- `perl-base`: CVE-2026-42497, CVE-2026-48959, CVE-2026-48961,
  CVE-2026-48962, CVE-2026-57432, CVE-2026-7017, CVE-2026-9538. Ни один
  production entrypoint не запускает Perl.
- `glibc`: CVE-2026-5435 и CVE-2026-5928; остаются загруженными системными
  рисками, но найденные trigger-пути отсутствуют в Python-сервисе.
- `ncurses`: CVE-2025-69720; runtime не обрабатывает terminal input.
- `gzip`: CVE-2026-41992; процесс не запускает CLI gzip.
- `libacl1`: CVE-2026-54369 и CVE-2026-54370; непривилегированный read-only
  runtime не выполняет ACL administration.

## Python runtime

Grype нашёл шесть CVE непосредственно в CPython 3.14.7. Единственный с
указанным fix — Medium
[CVE-2025-15367](https://security-tracker.debian.org/tracker/CVE-2025-15367),
но Grype предлагает только `3.15.0a6`, то есть pre-release другой ветки.
Проект не использует `poplib`, поэтому переход с требуемого Python 3.14 на alpha
неоправдан.

Другие Medium относятся к `urllib.request.HTTPPasswordMgr`, `stringprep` и
`tarfile`; эти API production-код не использует. Low CVE-2026-15310 относится
к распаковке crafted ZIP с bzip2/LZMA/Zstandard и потенциальной чрезмерной
предаллокации. DOCX extractor действительно читает недоверенный ZIP через
`zipfile`, поэтому это применимый DoS-класс. Применимость закрыта на уровне приложения: разрешены только STORE/DEFLATE,
размер XML ограничен 8 MiB, compression ratio — 200, чтение потоковое.
Парсинг вынесен в отдельный процесс с wall/CPU/memory лимитами; timeout
прерывает и убирает дочерний процесс. Это не исправляет сам Docker base.

## Решение

Базовый Python digest сохранён. Добавление `apt-get upgrade` ничего не закроет:
репозитории Trixie не предлагают обновлений для установленных пакетов. Такой RUN
также сделает содержимое сборки зависимым от времени при неизменном base digest.

Практические действия:

1. Сохранить Python 3.14 и текущий hardened runtime: непривилегированный UID,
   read-only filesystem, `no-new-privileges` и удалённые capabilities существенно
   ограничивают применимость системных CVE.
2. При каждом обновлении digest `python:3.14-slim` пересобирать все пять Python
   образов и повторять Grype. CI должен отдельно падать на fixable Critical/High,
   а no-fix находки публиковать полностью вместе с этим reachability register.
3. Не скрывать `wont-fix` через глобальный ignore. Когда Debian выпустит Trixie
   update или официальный Python image с ним, обновить общий digest во всех
   Dockerfiles и подтвердить уменьшение счётчика повторным JSON-сканом.
4. Bounded DOCX member extraction и изоляция процесса реализованы;
   регрессии охватывают запрещённые codecs, размеры, ratio и timeout.
5. Рассматривать distroless/minimal custom runtime отдельно: удаление
   `perl-base` вручную через `dpkg --force-depends` оставляет неподдерживаемую и
   трудно обновляемую файловую систему и не является приемлемым исправлением.

## Реестр решений

- **[Critical] Шесть Debian CVE дают семь строк →** пакеты формально уязвимы,
  но исправлений Trixie нет → сохранены platform hardening и полный реестр,
  `apt upgrade` не добавлен → официальный Debian tracker и пустой список
  upgradable packages подтверждают решение.
- **[High] zlib CVE-2026-85091 без fix →** библиотека присутствует, trigger API
  сервис не использует → мониторить Debian/Python base, не подменять исправление
  suppression → source scan и анализ imports/entrypoints фиксируют границу.
- **[Medium] CPython CVE предлагает только 3.15 alpha →** смена требуемой ветки
  создаёт больший риск, `poplib` отсутствует → остаться на 3.14 и обновиться при
  выпуске 3.14 patch → отсутствие import и версия образа проверены.
- **[Low] ZIP decompression DoS достижим через DOCX →** compressed upload limit
  сам по себе не ограничивает expanded member → добавлены bounded extraction
  и отдельный процесс → extractor regressions прошли; Linux runtime проверил
  успешный Unicode extract и три принудительных timeout без event-loop errors.

# Проверка безопасности Caddy-образа

Дата проверки: 2026-09-06. Проверен общий runtime target
`thirdnews-caddy-hardened:qa`, Alpine 3.23.5, arm64, image ID
`sha256:d3d23738ae88d08f3cf9def463736b221b31d32cb2b6afe650dcd0dd28b45238`.
Он собирает Caddy 2.11.4 статически с Go 1.26.7 и используется как базовый
слой proxy и web-образов.

Исходный отчёт Grype 0.116.1 находится в
`/private/tmp/thirdnews-caddy-hardened-audit.json`; SHA-256 файла:
`e36d3ec115a52dfff3533bcaa279e47e385308319eae1e8795aef66cccabb1bf`.
До замены официальный Caddy runtime из
`/private/tmp/thirdnews-web-final-image-audit.json` содержал 20 Critical,
48 High и 109 строк с доступным исправлением. После замены результат —
0 Critical, 0 High и 0 строк с доступным исправлением.

Остались три Medium-строки для CVE-2025-60876: Grype сопоставляет одну
уязвимость BusyBox трём package aliases (`busybox`, `busybox-binsh`,
`ssl_client`). Исправленной Alpine-версии в базе нет. Runtime содержит всего
17 APK-пакетов; `curl`, `libcurl`, `c-ares` и временно использованный для
сборки `libcap` отсутствуют. Установлены исправленные `libcrypto3` и
`libssl3` 3.5.8.

Build metadata подтвердили Go 1.26.7, gRPC 1.83.1, `x/text` 0.39.0 и core
OpenTelemetry 1.44.0. Контейнер работает как `caddy` UID 100/GID 101,
конфигурация валидируется, каталоги `/data` и `/config` доступны для записи,
а процесс успешно привязывается к порту 80 и отвечает HTTP `ok`. Возможность
привязки даёт file capability на бинарном файле; постоянный root entrypoint не
требуется.

Существующий `proxy-data`, созданный root-процессом официального образа, перед
первым запуском нового непривилегированного runtime нужно однократно передать
UID 100/GID 101. Команда миграции и reusable target strategy приведены в
`infra/caddy/README.md`. После сборки итоговых proxy/web targets их следует
повторно просканировать: добавление статических web assets не должно менять
набор runtime-пакетов, но это проверяется по конечным image IDs.


Итоговый target `thirdnews-v2-web` повторно просканирован Grype 0.116.1
2026-09-06: 3 Medium, 0 High, 0 Critical, 0 fixable. Все три строки относятся
к указанному BusyBox CVE; добавление собранного UI не изменило runtime findings.

# External classifier

Классификатор — отдельный сервис с тем же layout, собственным lockfile и
Granian factory `lib.app:create_app`. Он импортирует только
`thirdnews_contracts`, не главный сервис.

Используйте `build_classifier_router` и передайте node id, public key главного
сервиса, expected issuer `thirdnews`, audience `thirdnews-classifier`. Узел
фильтрует результат по присланной taxonomy и `options.allowed_axes`.

Для callback режима передайте per-node private key, signing issuer и
`supports_async=true`, а классификатор возвращает `DeferredClassification`.
Helper отвечает 202, соблюдает callback deadline и подписывает точное тело с
job/attempt/node binding. Синхронный результат возвращается как 200.

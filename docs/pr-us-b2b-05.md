## US-B2B-05 — просмотр карточки товара и причин блокировки

Реализация канон-flow `view-product` (`GET /api/v1/products/{id}`):

- MODERATED: полный seller payload, `skus[].cost_price` / `reserved_quantity`, `blocking_reason=null`, `blocked=false`
- BLOCKED: `blocking_reason.title` + `field_reports[]`, `blocked=true`
- чужой / несуществующий товар → **404** (IDOR)
- поддержка всех 5 статусов state machine

### DoD tests

- `get_moderated_product_returns_full_payload`
- `get_blocked_product_returns_blocking_reason_and_field_reports`
- `get_others_product_returns_404`
- `get_nonexistent_returns_404`

GHA: `b2b-tests`. Локально:

```
$ cd services/b2b && python3 -m pytest -q tests/test_us_b2b_05_get_product.py
.....                                                                    [100%]
5 passed
```

### ADR — seller vs inter-service GET

Рассматривались: (1) один handler с if по JWT/`X-Service-Key`, (2) два сериализатора/маршрута, (3) permission-класс. Выбраны **два сериализатора** (`serialize_product` для seller JWT и `serialize_public_product` для B2C): читаемее, чем ветвление в одном view, и снижает риск утечки `cost_price` / `reserved_quantity` / `blocking_reason` в витринный ответ — эти поля собираются только в seller-сериализаторе.

Подробнее: `docs/adr-us-b2b-05-get-modes.md`.

### OpenAPI

Соответствует `URFU2026-NeoMarket/neomarket-protocols` `b2b/openapi.yaml` → `ProductDetailResponse` (`blocking_reason` nullable с `title`, `field_reports`, `blocked`). Отдельный protocols-PR не нужен — схема GET `/products/{id}` уже опубликована.

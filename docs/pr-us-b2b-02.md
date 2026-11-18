## US-B2B-02 — добавление варианта товара (SKU)

Реализация канон-flow `add-sku` (`POST /api/v1/skus`):

- первый SKU: товар `CREATED` → `ON_MODERATION`, в outbox событие `CREATED` с `idempotency_key` и `X-Service-Key`
- второй и последующие SKU: статус не меняется, событие не отправляется
- `HARD_BLOCKED` → `403`
- пустые/отсутствующие `images` → `400 INVALID_REQUEST`

### DoD tests

- `first_sku_transitions_product_to_on_moderation`
- `first_sku_emits_created_event_to_moderation`
- `second_sku_no_state_change`
- `add_sku_to_hard_blocked_returns_403`
- `missing_image_returns_400`

GHA: workflow `b2b-tests`. Локальный pytest:

```
$ cd services/b2b && python3 -m pytest -q tests/test_us_b2b_02_create_sku.py
.....                                                                    [100%]
5 passed
```

### ADR — доставка CREATED в Moderation

Рассматривались: (1) синхронный POST в обработчике, (2) outbox-pattern, (3) fire-and-forget. Выбран **outbox**: если Moderation недоступна, создание SKU и переход статуса всё равно коммитятся, а доставка ретраится с тем же `idempotency_key`; для первой итерации достаточно одной таблицы и записи в той же транзакции, без блокировки кабинета продавца на сетевых сбоях. Синхронный POST отвергнут из‑за связанности availability; fire-and-forget — из‑за потери событий.

Критерии: поведение при недоступности Moderation; сложность реализации на первой итерации.

Подробнее: `docs/adr-us-b2b-02-moderation-event.md`.

### Формат события (fallback без US-MOD-01 protocols PR)

```json
{
  "event_type": "CREATED",
  "product_id": "<uuid>",
  "seller_id": "<uuid>",
  "idempotency_key": "<uuid>",
  "headers": { "X-Service-Key": "b2b-service-key" }
}
```

При появлении канона в `neomarket-protocols` — синхронизируем через PR.

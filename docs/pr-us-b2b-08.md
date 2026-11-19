## US-B2B-08 — резервирование и снятие резерва SKU

Реализация канон-flow `reserve-sku`:

- `POST /api/v1/inventory/reserve` — all-or-nothing, `idempotency_key`, `SELECT FOR UPDATE`
- `POST /api/v1/inventory/unreserve` — компенсация, восстанавливает active/reserved
- при `active_quantity → 0` — outbox `SKU_OUT_OF_STOCK` в B2C
- partial insufficient → `409 INSUFFICIENT_STOCK`, полный rollback

### DoD tests

- `reserve_all_skus_succeeds`
- `partial_insufficient_stock_returns_409_all_rollback`
- `idempotent_reserve_returns_200_without_double_deduction`
- `sku_out_of_stock_event_emitted`
- `unreserve_restores_quantities`

GHA: `b2b-tests`. Локально:

```
$ cd services/b2b && python3 -m pytest -q tests/test_us_b2b_08_inventory.py
......                                                                   [100%]
6 passed
```

### ADR — all-or-nothing

Рассматривались: (1) одна транзакция + `SELECT FOR UPDATE`, (2) оптимистическая блокировка с retry, (3) двухфазный commit. Выбрана **транзакция с FOR UPDATE**: при конкурентных checkout по одному SKU строки сериализуются и double-sell последнего остатка исключается; реализация проще 2PC/retry-оркестрации — validate всех позиций, затем apply, иначе 409 без частичных резервов. Идемпотентность — отдельно по `idempotency_key`.

Подробнее: `docs/adr-us-b2b-08-reserve-atomicity.md`.

### OpenAPI

Соответствует `neomarket-protocols` `b2b/openapi.yaml` → `/api/v1/inventory/reserve` и `/unreserve`. Отдельный protocols-PR не нужен.

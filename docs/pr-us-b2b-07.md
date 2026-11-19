## US-B2B-07 — каталог товаров для B2C (service-to-service)

Реализация канон-flow `catalog-for-b2c`:

- `GET /api/v1/public/products` + `X-Service-Key` — только `MODERATED`, `deleted=false`, in-stock
- `?ids=` / `POST /api/v1/public/products/batch` — видимый subset без 404 на скрытые
- ответ без `cost_price` и `reserved_quantity`
- без ключа → `401`

### DoD tests

- `catalog_returns_moderated_in_stock_products`
- `catalog_excludes_hard_blocked`
- `catalog_missing_service_key_returns_401`
- `catalog_response_has_no_cost_price`
- `batch_ids_returns_visible_subset`

GHA: `b2b-tests`. Локально:

```
$ cd services/b2b && python3 -m pytest -q tests/test_us_b2b_07_public_catalog.py
.....                                                                    [100%]
5 passed
```

### ADR — разграничение режимов

Рассматривались: (1) один URL с if по JWT/`X-Service-Key`, (2) два отдельных URL, (3) два view + permission на одном path. Выбраны **два URL** (`/api/v1/products` seller vs `/api/v1/public/products` B2C) и отдельные сериализаторы: минимальный риск утечки sensitive-полей в витрину и проще добавлять новый режим отдельным prefix, не раздувая общий handler.

Подробнее: `docs/adr-us-b2b-07-catalog-modes.md`.

### OpenAPI

Соответствует `neomarket-protocols` `b2b/openapi.yaml` (Public Catalog: list + batch). Отдельный protocols-PR не нужен.

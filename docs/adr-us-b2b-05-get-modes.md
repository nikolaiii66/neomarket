# ADR: два режима GET карточки (US-B2B-05)

## Контекст

`GET /api/v1/products/{id}` должен отдавать seller-view (с `cost_price` / `reserved_quantity`, `blocking_reason`, `field_reports`) и отдельно обслуживать inter-service/B2C без sensitive-полей.

## Альтернативы

1. **Один view/handler с if по auth** (JWT vs `X-Service-Key`) — меньше файлов, но легко смешать поля и случайно отдать `cost_price`.
2. **Два view / два сериализатора** (`serialize_product` + `serialize_public_product`, seller route vs `/public/products`) — явное разделение контрактов.
3. **Permission-класс / policy object** — гибко, но избыточно для первой итерации B2B.

## Решение

Выбраны **два сериализатора и раздельные маршруты** (seller JWT → `ProductOut` / `ProductDetailResponse`, B2C service-key → public payload без sensitive).

## Критерии

- **Читаемость**: seller и public контракты не пересекаются в одном if-лабиринте.
- **Риск утечки**: `cost_price` / `reserved_quantity` / `blocking_reason` собираются только в seller-сериализаторе; public path физически не включает эти поля.

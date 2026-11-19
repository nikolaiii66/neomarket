# ADR: разграничение seller vs B2C-каталога (US-B2B-07)

## Контекст

Нужен режим витрины с `X-Service-Key`, фильтрами видимости и без `cost_price` / `reserved_quantity`, рядом с seller JWT API.

## Альтернативы

1. **Один URL** (`GET /api/v1/products`) с ветвлением по заголовку JWT vs `X-Service-Key` — компактно, но высокий риск смешать поля ответа.
2. **Два отдельных URL** (`/api/v1/products` seller, `/api/v1/public/products` B2C) — явное разделение контрактов.
3. **Два view + роутер/permission** на одном path — гибко, но сложнее сопровождать на первой итерации.

## Решение

Выбраны **два отдельных URL + отдельные сериализаторы** (`serialize_public_product`, batch `?ids=` / `POST .../batch`).

## Критерии

- **Риск утечки**: public serializer физически не включает sensitive поля; seller route не обслуживает service-key каталог.
- **Удобство нового режима**: третий клиент (например internal analytics) добавляется новым prefix/view, не раздувая if в общем handler.

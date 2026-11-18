## US-B2B-01 — создание карточки товара

Реализация канон-flow `create-product` (`POST /api/v1/products`):

- happy: `201`, `status=CREATED`, `skus=[]`; `seller_id` только из JWT (защита от IDOR)
- unhappy: отсутствие `images` / `category_id` / несуществующий `category_id` → `400 INVALID_REQUEST`
- товар без SKU не уходит на модерацию (это US-B2B-02)

### DoD tests

Имена тестов из задания:

- `create_product_returns_201_with_created_status`
- `seller_id_taken_from_jwt`
- `missing_images_returns_400`
- `missing_category_returns_400`
- `invalid_category_id_returns_400`

GHA: workflow `b2b-tests` на push/PR по `services/b2b/**`.

Локальный pytest (доказательство на случай, если Actions ещё не зелёные):

```
$ cd services/b2b && python3 -m pytest -q tests/test_us_b2b_01_create_product.py
.....                                                                    [100%]
5 passed
$ python3 -m pytest -q
..............................                                           [100%]
30 passed
```

### ADR — хранение характеристик товара

Рассматривались три варианта: (1) JSON-поле в `products`, (2) отдельная таблица `product_characteristics (name, value, product_id)`, (3) полноценная EAV со справочником атрибутов. Выбрана **отдельная таблица**: фильтрация по характеристикам остаётся обычным SQL/`JOIN` без JSON-path и различий диалектов; новые характеристики продавца добавляются INSERT-ом без ALTER TABLE. EAV отложена до канонических фильтров витрины — на этапе CREATED она избыточно усложняет валидацию. JSON отвергнут из‑за слабой индексации и неудобных запросов при фильтрации.

Критерии выбора: сложность запросов при фильтрации по характеристикам; удобство добавления новых характеристик без миграций схемы.

Подробнее: `docs/adr-us-b2b-01-characteristics.md`.

### OpenAPI

Контракт эндпоинта согласован с ожидаемым `POST /products` B2B OpenAPI (валидация обязательных полей, `201` + объект товара, ошибки `400`).

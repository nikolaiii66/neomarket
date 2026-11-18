# NeoMarket — Clearance-40 milestone contracts

Реализация milestone-контрактов NeoMarket (УрФУ / Контракция) для Clearance-40.

## Оставшиеся US

### B2B CORE
- US-B2B-01 создание карточки товара
- US-B2B-02 добавление SKU
- US-B2B-05 просмотр карточки и причин блокировки
- US-B2B-07 каталог для B2C (S2S)
- US-B2B-08 reserve / unreserve
- US-B2B-09 применение решения модерации

### B2C CORE
- US-CART-03 корзина
- US-CAT-01 каталог с фильтрами и фасетами
- US-CAT-03 карточка товара
- US-ORD-01 checkout
- US-ORD-03 отмена заказа

### MODERATION
- US-MOD-03 одобрение товара
- US-MOD-05 жёсткая блокировка

## Стек
Python 3.12, FastAPI, SQLAlchemy 2, SQLite (dev/tests), pytest.

## Canon / Protocols
- https://github.com/URFU2026-NeoMarket/neomarket-canon
- https://github.com/URFU2026-NeoMarket/neomarket-protocols

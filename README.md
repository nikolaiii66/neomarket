# NeoMarket — Clearance-40

Реализация milestone-контрактов NeoMarket для Clearance-40.

**GitHub:** https://github.com/nikolaiii66/neomarket

## Сервисы

| Сервис | Контракты | Команда тестов |
|--------|-----------|----------------|
| `services/b2b` | US-B2B-01, 02, 05, 07, 08, 09 | `cd services/b2b && python3 -m pytest -q` |
| `services/moderation` | US-MOD-03, 05 | `cd services/moderation && python3 -m pytest -q` |
| `services/b2c` | US-CART-03, US-CAT-01, US-CAT-03, US-ORD-01, US-ORD-03 | `cd services/b2c && python3 -m pytest -q` |

```bash
make test
```

## Canon
- https://github.com/URFU2026-NeoMarket/neomarket-canon
- https://github.com/URFU2026-NeoMarket/neomarket-protocols

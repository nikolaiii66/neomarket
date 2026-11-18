# NeoMarket Moderation

FastAPI microservice covering US-MOD-03 (approve) and US-MOD-05 (hard block).

## Auth

Moderator identity is resolved from either:

1. `Authorization: Bearer <jwt>` — JWT `sub` claim is the moderator UUID
2. `X-Moderator-Id: <uuid>` — simple bearer-less identity for local/tests

Service-to-service calls use `X-Service-Key` (inbound B2B events).

## Key endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/events/product` | Canon inbound product events from B2B |
| POST | `/api/v1/b2b/events` | Protocol-shaped inbound B2B events |
| POST | `/api/v1/queue/claim` | Claim next PENDING ticket |
| GET | `/api/v1/tickets/{ticket_id}` | Ticket detail |
| POST | `/api/v1/products/{product_id}/approve` | Approve (canon) |
| POST | `/api/v1/tickets/{ticket_id}/approve` | Approve (protocol) |
| POST | `/api/v1/products/{product_id}/decline` | Soft/hard block (canon) |
| POST | `/api/v1/tickets/{ticket_id}/block` | Soft/hard block (protocol) |
| GET | `/api/v1/blocking-reasons` | Seeded blocking reasons |

Outbound decisions are stored in `outgoing_moderation_events` (outbox) and POSTed to
`{B2B_BASE_URL}/api/v1/moderation/events` when `B2B_BASE_URL` is set.

## Run tests

```bash
cd services/moderation
python3 -m pytest -q
```

## Config

| Env | Default | Meaning |
|-----|---------|---------|
| `SERVICE_KEY` | `dev-service-key` | Inbound B2B `X-Service-Key` |
| `B2B_BASE_URL` | _(empty)_ | Outbound B2B base URL |
| `B2B_SERVICE_KEY` | `dev-mod-to-b2b-key` | Outbound `X-Service-Key` |
| `JWT_SECRET` | `dev-secret-change-me` | Moderator JWT secret |

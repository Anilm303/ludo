# eSewa Payment Integration

End-to-end eSewa payment flow for tournaments in this backend.

## 1. Configure environment

Add these to your `.env` (use the sandbox values for local development):

```env
# UAT (sandbox) merchant id for local dev. Replace with your real merchant code in production.
ESEWA_MERCHANT_ID=EPAYTEST
ESEWA_SECRET=
# Public HTTPS URL that eSewa can reach. For local dev, use an ngrok URL.
ESEWA_SUCCESS_URL=https://your-ngrok-domain.ngrok.io/api/payments/esewa/callback
ESEWA_FAIL_URL=https://your-ngrok-domain.ngrok.io/api/payments/esewa/callback?status=failed
BASE_URL=https://your-ngrok-domain.ngrok.io
# Set to 'production' to disable the test_mark_paid endpoint.
ENV=development
```

## 2. Apply the database migration

Run `sql/payments_migration.sql` against your `chess_db` database to make sure the
indexes, columns and view are present.

```powershell
psql -U postgres -d chess_db -f sql/payments_migration.sql
```

## 3. Run the backend

```powershell
# from the chess_backend folder
uvicorn main:app --reload --port 8000

# in another terminal, expose it to the internet for eSewa to reach:
ngrok http 8000
```

Set the `ngrok` URL in `ESEWA_SUCCESS_URL`, `ESEWA_FAIL_URL` and `BASE_URL`.

## 4. Endpoints

All endpoints are mounted under `/api/payments/esewa/...`.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/create` | Create a payment. Body: `{user_id, tournament_id?, amount}`. Returns `{payment, esewa, payment_url, reused?}`. |
| POST | `/callback` | eSewa redirects the user's browser here. Server-side verifies with `/transrec`. |
| POST | `/verify` | Client-driven verification (kept for backwards compatibility). |
| GET  | `/status/{pid}` | Poll the current status of a payment (used by the Flutter app). |
| GET  | `/history` | Authenticated user's payment history. |
| POST | `/test_mark_paid` | Dev-only helper to simulate a successful eSewa payment (gated by `ENV`). |

### Idempotency

`POST /create` is idempotent per (user_id, tournament_id). If a `pending` or
`paid` payment already exists, the same `pid` is returned with `reused: true`.

### Authorization

When an `Authorization: Bearer <jwt>` header is present, the user id from the
token MUST match the `user_id` in the body (403 otherwise). History and status
endpoints are restricted to the token's user.

## 5. Flutter integration

Use `EsewaService.openPayment(...)` from `lib/services/esewa_service.dart`. It
opens the WebView, waits for the callback redirect, and then polls the status
endpoint to confirm the final state.

`TournamentPaymentButton` already wires this up — just pass your backend base
URL (without the `/api` suffix).

A `PaymentHistoryScreen` is also available at
`lib/features/tournament/presentation/screens/payment_history_screen.dart`.

## 6. Tests

```powershell
cd chess_backend
python -m unittest tests.test_esewa_payments -v
```

The tests use FastAPI's `TestClient` and exercise the in-memory fallback
(no database required). They cover create, validation, idempotency, status,
history, the dev-only test endpoint and the unknown-pid callback path.

## 7. Troubleshooting

- **Callback never received**: ensure `ESEWA_SUCCESS_URL` is publicly reachable
  (ngrok) and uses `https://`.
- **"user_id does not match authenticated user"**: the JWT in the request and
  the body disagree; the backend enforces they match.
- **Status stuck on `pending`**: eSewa's `/transrec` call may have failed; the
  raw response is stored in `payments.raw_response` for debugging.
- **Production deploy**: set `ENV=production` to disable `/test_mark_paid`.

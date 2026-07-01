from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, Field
import os
import uuid
import json
import logging
from datetime import datetime
from typing import Optional
from app.postgres_store import execute, execute_returning, fetch_one, is_database_url_configured
from app.auth_deps import get_current_user_id
from urllib import request as urlrequest, parse as urlparse

logger = logging.getLogger(__name__)

router = APIRouter()

ESEWA_MERCHANT_ID = os.getenv('ESEWA_MERCHANT_ID', 'EPAYTEST')
ESEWA_SECRET = os.getenv('ESEWA_SECRET', '')
ESEWA_SUCCESS_URL = os.getenv('ESEWA_SUCCESS_URL', '')
ESEWA_FAIL_URL = os.getenv('ESEWA_FAIL_URL', '')
BASE_URL = os.getenv('BASE_URL', 'http://10.0.2.2:7860')

# UAT (test) vs production URLs
ESEWA_UAT_BASE = 'https://uat.esewa.com.np/epay'
ESEWA_PROD_BASE = 'https://esewa.com.np/epay'


def _is_uat() -> bool:
    return ESEWA_MERCHANT_ID.upper() == 'EPAYTEST'


def _esewa_base() -> str:
    return ESEWA_UAT_BASE if _is_uat() else ESEWA_PROD_BASE


# ------------------------- Models -------------------------

class CreatePaymentRequest(BaseModel):
    user_id: str
    tournament_id: Optional[str] = None
    amount: float = Field(gt=0, description="Amount in NPR, must be > 0")


# ------------------------- Helpers -------------------------

def _find_payment(pid: str) -> Optional[dict]:
    if is_database_url_configured():
        return fetch_one('SELECT * FROM payments WHERE pid = %(pid)s', {'pid': pid})
    return _MEMORY_PAYMENTS.get(pid)


def _notify_tournament_payment(
    tournament_id: Optional[str],
    user_id: Optional[str],
    pid: str,
) -> None:
    """Notify the tournaments router that this user has paid for the tournament.

    In a single-process deployment we can call the helper directly (avoids an
    HTTP round-trip). For a multi-process deployment, replace this with an
    HTTP POST to the tournaments router. The function swallows errors so that
    payment confirmation is never blocked by tournament bookkeeping issues.
    """
    if not tournament_id or not user_id:
        return
    try:
        from app.routes.tournaments import _db_or_memory_update_participant_status, _db_or_memory_get_tournament, _count_paid_participants, _now
        t = _db_or_memory_get_tournament(tournament_id)
        if not t:
            return
        if t.get('status') == 'finished':
            return
        # Mark the participant as paid
        _db_or_memory_update_participant_status(tournament_id, user_id, 'paid', pid)
        # Increment the prize pool and transition state
        from app.routes.tournaments import _db_or_memory_update_tournament
        new_pool = float(t.get('prize_pool') or 0) + float(t.get('entry_fee') or 0)
        paid_count = _count_paid_participants(tournament_id)
        new_status = t.get('status') or 'open'
        started_at = t.get('started_at')
        if paid_count >= t.get('max_players', 2):
            new_status = 'in_progress'
            started_at = _now()
        elif new_status == 'open' and paid_count >= 1:
            new_status = 'waiting'
        _db_or_memory_update_tournament(
            tournament_id,
            {
                'prize_pool': new_pool,
                'status': new_status,
                'started_at': started_at,
            },
        )
    except Exception as e:
        logger.warning('Failed to notify tournament of payment: %s', e)


def _check_duplicate_pending(user_id: str, tournament_id: Optional[str]) -> Optional[dict]:
    """Return existing pending/paid record for the same user+tournament to prevent duplicates."""
    if not tournament_id:
        return None
    if is_database_url_configured():
        return fetch_one(
            """
            SELECT * FROM payments
            WHERE user_id = %(uid)s AND tournament_id = %(tid)s
              AND status IN ('pending','paid')
            ORDER BY created_at DESC LIMIT 1
            """,
            {'uid': user_id, 'tid': tournament_id},
        )
    for p in _MEMORY_PAYMENTS.values():
        if p.get('user_id') == user_id and p.get('tournament_id') == tournament_id \
                and p.get('status') in ('pending', 'paid'):
            return p
    return None


# ------------------------- Endpoints -------------------------

@router.post('/payments/esewa/create')
async def create_esewa_payment(
    req: CreatePaymentRequest,
    token_user: Optional[str] = Depends(get_current_user_id),
):
    # If a token is present, the user_id in the body must match the token's subject.
    if token_user and token_user != req.user_id:
        raise HTTPException(status_code=403, detail='user_id does not match authenticated user')

    # Idempotency: if a pending/paid payment already exists for this user+tournament, reuse it.
    existing = _check_duplicate_pending(req.user_id, req.tournament_id)
    if existing:
        pid = existing['pid']
        amt = float(existing.get('amount') or req.amount)
        esewa_params = _build_esewa_params(pid, amt)
        return {
            'success': True,
            'payment': existing,
            'esewa': esewa_params,
            'payment_url': _esewa_base() + '/main',
            'reused': True,
        }

    pid = uuid.uuid4().hex
    amt = float(req.amount)
    inserted = None

    if is_database_url_configured():
        q = """
        INSERT INTO payments (pid, user_id, tournament_id, amount, currency, status, created_at)
        VALUES (%(pid)s, %(user_id)s, %(tournament_id)s, %(amount)s, %(currency)s, 'pending', now())
        RETURNING id, pid, user_id, tournament_id, amount, currency, status, created_at
        """
        params = {
            'pid': pid,
            'user_id': req.user_id,
            'tournament_id': req.tournament_id,
            'amount': amt,
            'currency': 'NPR',
        }
        inserted = execute_returning(q, params)
    else:
        inserted = {
            'id': pid,
            'pid': pid,
            'user_id': req.user_id,
            'tournament_id': req.tournament_id,
            'amount': amt,
            'currency': 'NPR',
            'status': 'pending',
            'created_at': datetime.utcnow().isoformat(),
        }
        _MEMORY_PAYMENTS[pid] = inserted

    esewa_params = _build_esewa_params(pid, amt)

    return {
        'success': True,
        'payment': inserted,
        'esewa': esewa_params,
        'payment_url': _esewa_base() + '/main',
    }


def _build_esewa_params(pid: str, amt: float) -> dict:
    return {
        'tAmt': f"{amt:.2f}",
        'amt': f"{amt:.2f}",
        'txAmt': '0',
        'psc': '0',
        'pdc': '0',
        'scd': ESEWA_MERCHANT_ID,
        'pid': pid,
        'su': ESEWA_SUCCESS_URL or f"{BASE_URL}/api/payments/esewa/callback",
        'fu': ESEWA_FAIL_URL or f"{BASE_URL}/api/payments/esewa/callback?status=failed",
    }


@router.post('/payments/esewa/callback')
async def esewa_callback(request: Request):
    """eSewa POSTs form-encoded data back here after payment.
    eSewa callback params (form-encoded):
      - pid: product id (our uuid)
      - amt: amount
      - refId: eSewa reference id
      - qa, qty, etc. (legacy)
    """
    form = await request.form()
    data = {k: form.get(k) for k in form.keys()}
    pid = data.get('pid')
    amt = data.get('amt')
    ref_id = data.get('refId') or data.get('esewaRefId')

    if not pid:
        raise HTTPException(status_code=400, detail='Missing pid')

    rec = _find_payment(pid)
    if not rec:
        raise HTTPException(status_code=404, detail='Payment record not found')

    # If already paid, return idempotent success.
    if rec.get('status') == 'paid':
        return {'success': True, 'pid': pid, 'verified': True, 'note': 'already_paid'}

    import asyncio
    loop = asyncio.get_event_loop()
    verified, resp = await loop.run_in_executor(None, _verify_with_esewa, pid, rec.get('amount') or amt)

    _persist_payment_result(pid, ref_id, verified, resp)
    if verified:
        _notify_tournament_payment(rec.get('tournament_id'), rec.get('user_id'), pid)

    return {
        'success': verified,
        'pid': pid,
        'refId': ref_id,
        'verified': verified,
        'tournament_id': rec.get('tournament_id'),
    }


@router.post('/payments/esewa/verify')
async def esewa_verify(payload: dict):
    pid = payload.get('pid')
    if not pid:
        raise HTTPException(status_code=400, detail='Missing pid')

    rec = _find_payment(pid)
    if not rec:
        raise HTTPException(status_code=404, detail='Payment not found')

    if rec.get('status') == 'paid':
        return {'success': True, 'pid': pid, 'verified': True, 'note': 'already_paid'}

    import asyncio
    loop = asyncio.get_event_loop()
    verified, resp = await loop.run_in_executor(None, _verify_with_esewa, pid, rec.get('amount'))
    _persist_payment_result(pid, rec.get('esewa_ref_id'), verified, resp)
    if verified:
        _notify_tournament_payment(rec.get('tournament_id'), rec.get('user_id'), pid)

    return {
        'success': True,
        'pid': pid,
        'verified': verified,
        'response': resp,
        'tournament_id': rec.get('tournament_id'),
    }


@router.get('/payments/esewa/status/{pid}')
async def esewa_status(pid: str, token_user: Optional[str] = Depends(get_current_user_id)):
    """Return the current status of a payment. Used by the Flutter app to poll after WebView closes."""
    rec = _find_payment(pid)
    if not rec:
        raise HTTPException(status_code=404, detail='Payment not found')
    # If a token is present, restrict to the owner.
    if token_user and rec.get('user_id') != token_user:
        raise HTTPException(status_code=403, detail='Not allowed')
    return {
        'pid': pid,
        'status': rec.get('status'),
        'amount': rec.get('amount'),
        'tournament_id': rec.get('tournament_id'),
        'esewa_ref_id': rec.get('esewa_ref_id'),
        'verified_at': rec.get('verified_at'),
    }


@router.get('/payments/esewa/history')
async def esewa_history(token_user: Optional[str] = Depends(get_current_user_id)):
    """Return payment history for the authenticated user."""
    if not token_user:
        raise HTTPException(status_code=401, detail='Authentication required')
    if is_database_url_configured():
        from app.postgres_store import fetch_all as _fa
        rows = _fa(
            'SELECT pid, user_id, tournament_id, amount, currency, status, '
            '       esewa_ref_id, created_at, verified_at '
            'FROM payments WHERE user_id = %(uid)s ORDER BY created_at DESC',
            {'uid': token_user},
        ) or []
    else:
        rows = [p for p in _MEMORY_PAYMENTS.values() if p.get('user_id') == token_user]
    return {'success': True, 'payments': rows}


def _persist_payment_result(pid: str, ref_id: Optional[str], verified: bool, resp: Optional[dict]) -> None:
    status = 'paid' if verified else 'failed'
    if is_database_url_configured():
        try:
            execute(
                """
                UPDATE payments
                SET status = %(status)s,
                    esewa_ref_id = %(refId)s,
                    raw_response = %(raw)s::jsonb,
                    verified_at = now()
                WHERE pid = %(pid)s
                """,
                {
                    'status': status,
                    'refId': ref_id,
                    'raw': json.dumps(resp or {}),
                    'pid': pid,
                },
            )
        except Exception as e:
            logger.exception('Failed to persist payment result: %s', e)
    else:
        rec = _MEMORY_PAYMENTS.get(pid)
        if rec is not None:
            rec['status'] = status
            rec['esewa_ref_id'] = ref_id
            rec['raw_response'] = resp or {}
            rec['verified_at'] = datetime.utcnow().isoformat()


def _verify_with_esewa(pid: str, amt) -> tuple[bool, Optional[dict]]:
    """Call eSewa /epay/transrec to verify a transaction.

    Sandbox UAT doc: POST to https://uat.esewa.com.np/epay/transrec with
    amt, scd, pid (and optional rid). The response is plain text starting with
    'Success' on success or a `<response>` XML on failure.
    """
    try:
        amt_val = f"{float(amt):.2f}" if amt is not None else ''
    except Exception:
        amt_val = ''

    verify_url = _esewa_base() + '/transrec'
    post_data = {'amt': amt_val, 'scd': ESEWA_MERCHANT_ID, 'pid': pid}

    data = urlparse.urlencode(post_data).encode()
    try:
        req = urlrequest.Request(verify_url, data=data, method='POST')
        with urlrequest.urlopen(req, timeout=10) as resp:
            body = resp.read().decode('utf-8', errors='replace')
            body_lower = body.strip().lower()
            verified = body_lower.startswith('success') or '<response>success' in body_lower
            # Fallback: if the body mentions the same amount/pid, consider it verified.
            if not verified and amt_val and amt_val in body and pid in body:
                verified = True
            return verified, {'raw': body}
    except Exception as e:
        logger.warning('eSewa verify HTTP call failed: %s', e)
        return False, {'error': str(e)}


# In-memory store for local development when DB is not configured.
_MEMORY_PAYMENTS: dict[str, dict] = {}


@router.post('/payments/esewa/test_mark_paid')
async def esewa_test_mark_paid(payload: dict):
    """Test helper: mark a payment as paid (only enabled in non-production)."""
    if os.getenv('ENV', 'development').lower() == 'production':
        raise HTTPException(status_code=403, detail='Disabled in production')

    pid = payload.get('pid')
    if not pid:
        raise HTTPException(status_code=400, detail='Missing pid')

    rec = _find_payment(pid)
    if not rec:
        raise HTTPException(status_code=404, detail='Payment not found')

    _persist_payment_result(pid, rec.get('esewa_ref_id'), True, {'manual': True})
    _notify_tournament_payment(rec.get('tournament_id'), rec.get('user_id'), pid)
    return {
        'success': True,
        'pid': pid,
        'marked': 'paid',
        'tournament_id': rec.get('tournament_id'),
    }

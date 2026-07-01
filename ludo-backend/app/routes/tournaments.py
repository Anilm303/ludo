"""Tournament state machine + prize-pool management.

State transitions:
  open   -> waiting   : first player pays entry fee
  waiting -> in_progress : second player pays entry fee (both slots filled, prize pool = 2 * entry_fee)
  in_progress -> finished : declare_winner() called, prize pool credited to winner's wallet
  finished / cancelled are terminal states.

Backend storage:
  * DB configured -> rows in `tournaments` and `tournament_participants`
  * No DB        -> module-level _MEMORY_TOURNAMENTS / _MEMORY_PARTICIPANTS dicts
"""
from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.postgres_store import (
    execute,
    fetch_all,
    fetch_one,
    is_database_url_configured,
)
from app.auth_deps import get_current_user_id
from app.models.user import User

router = APIRouter()

# ----------------- In-memory fallback -----------------
_MEMORY_TOURNAMENTS: dict[str, dict] = {}
_MEMORY_PARTICIPANTS: dict[str, list] = {}

# Constants
ENTRY_FEE_DEFAULT = 10.0
PLATFORM_FEE_PCT = 0.10  # 10% platform fee (configurable)


# ----------------- Helpers -----------------
def _now() -> str:
    return datetime.utcnow().isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _db_or_memory_get_tournament(tid: str) -> Optional[dict]:
    if is_database_url_configured():
        return fetch_one(
            'SELECT * FROM tournaments WHERE id = %(id)s', {'id': tid}
        )
    return _MEMORY_TOURNAMENTS.get(tid)


def _db_or_memory_update_tournament(tid: str, fields: dict) -> None:
    if is_database_url_configured():
        # Build a dynamic SET clause for the columns that are actually changing
        set_clauses = []
        params = {'id': tid}
        for k, v in fields.items():
            set_clauses.append(f'{k} = %({k})s')
            params[k] = v
        if not set_clauses:
            return
        execute(
            f"UPDATE tournaments SET {', '.join(set_clauses)} WHERE id = %(id)s",
            params,
        )
    else:
        t = _MEMORY_TOURNAMENTS.get(tid)
        if t is not None:
            t.update(fields)


def _db_or_memory_get_participants(tid: str) -> list:
    if is_database_url_configured():
        return fetch_all(
            'SELECT * FROM tournament_participants WHERE tournament_id = %(tid)s ORDER BY joined_at ASC',
            {'tid': tid},
        ) or []
    return list(_MEMORY_PARTICIPANTS.get(tid, []))


def _db_or_memory_insert_participant(tid: str, user_id: str, status: str) -> None:
    if is_database_url_configured():
        try:
            execute(
                """
                INSERT INTO tournament_participants
                    (tournament_id, user_id, status, joined_at)
                VALUES (%(tid)s, %(uid)s, %(status)s, %(joined_at)s)
                ON CONFLICT (tournament_id, user_id) DO NOTHING
                """,
                {'tid': tid, 'uid': user_id, 'status': status, 'joined_at': _now()},
            )
        except Exception:
            pass
    else:
        _MEMORY_PARTICIPANTS.setdefault(tid, []).append({
            'tournament_id': tid,
            'user_id': user_id,
            'status': status,
            'joined_at': _now(),
        })


def _db_or_memory_update_participant_status(tid: str, user_id: str, status: str, pid: Optional[str] = None) -> None:
    if is_database_url_configured():
        try:
            execute(
                """
                UPDATE tournament_participants
                SET status = %(status)s,
                    payment_pid = COALESCE(%(pid)s, payment_pid)
                WHERE tournament_id = %(tid)s AND user_id = %(uid)s
                """,
                {'tid': tid, 'uid': user_id, 'status': status, 'pid': pid},
            )
        except Exception:
            pass
    else:
        for p in _MEMORY_PARTICIPANTS.get(tid, []):
            if p.get('user_id') == user_id:
                p['status'] = status
                if pid:
                    p['payment_pid'] = pid


def _count_paid_participants(tid: str) -> int:
    return sum(
        1 for p in _db_or_memory_get_participants(tid)
        if p.get('status') == 'paid'
    )


# ----------------- Schemas -----------------
class CreateTournamentRequest(BaseModel):
    title: str
    game_type: str = 'chess'
    entry_fee: float = ENTRY_FEE_DEFAULT
    max_players: int = 2


class JoinTournamentRequest(BaseModel):
    user_id: Optional[str] = None


class DeclareWinnerRequest(BaseModel):
    winner_user_id: str


# ----------------- Endpoints -----------------
@router.get('/tournaments')
async def list_tournaments(status: Optional[str] = None):
    """List tournaments, optionally filtered by status."""
    if is_database_url_configured():
        query = "SELECT * FROM tournaments"
        params = {}
        if status:
            query += " WHERE status = %(st)s"
            params['st'] = status
        query += " ORDER BY created_at DESC"
        rows = fetch_all(query, params) or []
    else:
        rows = list(_MEMORY_TOURNAMENTS.values())
        if status:
            rows = [r for r in rows if r.get('status') == status]
        rows.sort(key=lambda r: r.get('created_at', ''), reverse=True)

    # Ensure all required fields for UI are present
    for r in rows:
        if 'paid_players' not in r:
            r['paid_players'] = _count_paid_participants(r['id'])

    return {'tournaments': rows}


@router.post('/tournaments')
async def create_tournament(
    payload: CreateTournamentRequest,
    token_user: Optional[str] = Depends(get_current_user_id),
):
    """Create a new tournament. The creator is auto-joined (but not yet paid)."""
    if not token_user and is_database_url_configured():
        raise HTTPException(status_code=401, detail='Authentication required')
    if payload.max_players < 2:
        raise HTTPException(status_code=400, detail='max_players must be >= 2')
    if payload.entry_fee < 0:
        raise HTTPException(status_code=400, detail='entry_fee must be >= 0')

    tid = _new_id()
    owner = token_user or 'anonymous'
    now = _now()
    record = {
        'id': tid,
        'title': payload.title,
        'game_type': payload.game_type,
        'entry_fee': float(payload.entry_fee),
        'max_players': int(payload.max_players),
        'owner': owner,
        'status': 'open',  # open -> waiting -> in_progress -> finished
        'prize_pool': 0.0,
        'winner_user_id': None,
        'platform_fee_pct': PLATFORM_FEE_PCT,
        'created_at': now,
        'started_at': None,
        'finished_at': None,
        'metadata': {},
    }

    if is_database_url_configured():
        try:
            execute(
                """
                INSERT INTO tournaments
                    (id, title, game_type, entry_fee, max_players, owner, status,
                     prize_pool, winner_user_id, platform_fee_pct,
                     created_at, started_at, finished_at)
                VALUES
                    (%(id)s, %(title)s, %(game_type)s, %(entry_fee)s,
                     %(max_players)s, %(owner)s, 'open',
                     0, NULL, %(pct)s,
                     %(created_at)s, NULL, NULL)
                """,
                {
                    'id': tid,
                    'title': payload.title,
                    'game_type': payload.game_type,
                    'entry_fee': record['entry_fee'],
                    'max_players': record['max_players'],
                    'owner': owner,
                    'pct': PLATFORM_FEE_PCT,
                    'created_at': now,
                },
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        _MEMORY_TOURNAMENTS[tid] = record

    return {'success': True, 'tournament_id': tid, 'tournament': record}


@router.post('/tournaments/{tournament_id}/join')
async def join_tournament(
    tournament_id: str,
    payload: JoinTournamentRequest,
    token_user: Optional[str] = Depends(get_current_user_id),
):
    """Reserve a slot. Payment is still required to mark status='paid'."""
    user_id = payload.user_id or token_user
    if not user_id:
        raise HTTPException(status_code=400, detail='user_id required')
    if token_user and user_id != token_user:
        raise HTTPException(status_code=403, detail='user_id does not match authenticated user')

    tournament = _db_or_memory_get_tournament(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail='Tournament not found')
    if tournament['status'] in ('finished', 'cancelled'):
        raise HTTPException(status_code=400, detail=f'Tournament is {tournament["status"]}')

    existing = [p for p in _db_or_memory_get_participants(tournament_id) if p.get('user_id') == user_id]
    if existing:
        return {'success': True, 'message': 'Already joined', 'status': existing[0].get('status')}

    paid_count = _count_paid_participants(tournament_id)
    if paid_count >= tournament['max_players']:
        raise HTTPException(status_code=400, detail='Tournament is full')

    _db_or_memory_insert_participant(tournament_id, user_id, status='pending')
    return {'success': True, 'message': 'Joined. Pay to confirm.', 'status': 'pending'}


@router.post('/tournaments/{tournament_id}/confirm_payment')
async def confirm_payment(
    tournament_id: str,
    payload: dict,
    token_user: Optional[str] = Depends(get_current_user_id),
):
    """Called by the payments router after a successful eSewa verification.

    Marks this user as 'paid' in the tournament, increments the prize pool,
    and transitions the tournament state when both slots are paid.

    Body: {user_id, payment_pid}
    """
    user_id = payload.get('user_id') or token_user
    payment_pid = payload.get('payment_pid')
    if not user_id:
        raise HTTPException(status_code=400, detail='user_id required')
    if token_user and user_id != token_user:
        raise HTTPException(status_code=403, detail='user_id does not match authenticated user')

    tournament = _db_or_memory_get_tournament(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail='Tournament not found')
    if tournament['status'] == 'finished':
        raise HTTPException(status_code=400, detail='Tournament already finished')

    paid_count = _count_paid_participants(tournament_id)
    if paid_count >= tournament['max_players']:
        raise HTTPException(status_code=400, detail='Tournament is full')

    # Make sure participant row exists
    if not any(p.get('user_id') == user_id for p in _db_or_memory_get_participants(tournament_id)):
        _db_or_memory_insert_participant(tournament_id, user_id, status='pending')

    _db_or_memory_update_participant_status(tournament_id, user_id, 'paid', payment_pid)

    new_pool = float(tournament.get('prize_pool') or 0) + float(tournament['entry_fee'])
    new_paid_count = paid_count + 1
    new_status = tournament['status']
    started_at = tournament.get('started_at')
    if new_paid_count >= tournament['max_players']:
        new_status = 'in_progress'
        started_at = _now()
    elif new_status == 'open' and new_paid_count >= 1:
        new_status = 'waiting'

    _db_or_memory_update_tournament(
        tournament_id,
        {
            'prize_pool': new_pool,
            'status': new_status,
            'started_at': started_at,
        },
    )

    return {
        'success': True,
        'tournament_id': tournament_id,
        'status': new_status,
        'prize_pool': new_pool,
        'paid_players': new_paid_count,
        'max_players': tournament['max_players'],
    }


@router.post('/tournaments/{tournament_id}/declare_winner')
async def declare_winner(
    tournament_id: str,
    payload: DeclareWinnerRequest,
    token_user: Optional[str] = Depends(get_current_user_id),
):
    """End the tournament: mark it finished and credit the winner's wallet.

    For a 1v1 chess/ludo game, the prize pool is the sum of all entry fees.
    The platform keeps `platform_fee_pct` of the pool; the rest goes to winner.

    Authentication: in production this should be invoked by the game server
    (with a service token) once the chess engine reports a checkmate / resign.
    For dev, any authenticated participant can declare themselves the winner
    (it will be locked down by the game state in the next iteration).
    """
    winner = payload.winner_user_id
    if not winner:
        raise HTTPException(status_code=400, detail='winner_user_id required')

    tournament = _db_or_memory_get_tournament(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail='Tournament not found')
    if tournament['status'] != 'in_progress':
        raise HTTPException(
            status_code=400,
            detail=f'Tournament must be in_progress (currently {tournament["status"]})',
        )

    participants = _db_or_memory_get_participants(tournament_id)
    if not any(p.get('user_id') == winner and p.get('status') == 'paid' for p in participants):
        raise HTTPException(status_code=400, detail='Winner was not a paid participant')

    prize_pool = float(tournament.get('prize_pool') or 0)
    fee_pct = float(tournament.get('platform_fee_pct') or PLATFORM_FEE_PCT)
    platform_fee = round(prize_pool * fee_pct, 2)
    winner_prize = round(prize_pool - platform_fee, 2)

    if winner_prize > 0:
        new_balance = User.credit_wallet(winner, winner_prize)
    else:
        new_balance = User.get_wallet_balance(winner)

    _db_or_memory_update_tournament(
        tournament_id,
        {
            'status': 'finished',
            'winner_user_id': winner,
            'finished_at': _now(),
        },
    )

    return {
        'success': True,
        'tournament_id': tournament_id,
        'winner_user_id': winner,
        'prize_pool': prize_pool,
        'platform_fee': platform_fee,
        'winner_prize': winner_prize,
        'winner_wallet_balance': new_balance,
    }


@router.get('/tournaments/{tournament_id}')
async def get_tournament(tournament_id: str):
    """Return the current tournament state and its participants."""
    t = _db_or_memory_get_tournament(tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail='Tournament not found')

    # Add paid players count so the frontend can display (1/2 paid) correctly
    t_dict = dict(t)
    t_dict['paid_players'] = _count_paid_participants(tournament_id)

    participants = _db_or_memory_get_participants(tournament_id)
    return {'tournament': t_dict, 'participants': participants}


@router.get('/tournaments/{tournament_id}/participants')
async def list_participants(tournament_id: str):
    return {
        'tournament_id': tournament_id,
        'participants': _db_or_memory_get_participants(tournament_id),
    }


@router.get('/users/{username}/wallet')
async def get_wallet(username: str, token_user: Optional[str] = Depends(get_current_user_id)):
    if token_user and token_user != username:
        raise HTTPException(status_code=403, detail='Not allowed')
    balance = User.get_wallet_balance(username)
    return {'username': username, 'wallet_balance': balance}

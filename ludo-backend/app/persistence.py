from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
from app.game_engine import Player, PlayerColor, Token, GameState, GameStatus
from app.postgres_store import execute, fetch_all, fetch_one, json_value
# Import GameRoom inside functions to avoid circular import with room_manager

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "games"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_table() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS game_rooms (
          room_id TEXT PRIMARY KEY,
          room_data JSONB NOT NULL,
          created_at TIMESTAMPTZ DEFAULT now(),
          updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )


def _parse_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None


def _token_from_dict(token_data, color):
    return Token(
        id=int(token_data.get('id', 0)),
        color=color,
        position=int(token_data.get('position', -1)),
        is_killed=bool(token_data.get('isKilled', False)),
        is_in_home=bool(token_data.get('isInHome', False)),
    )


def _player_from_dict(player_data):
    color_value = player_data.get('color')
    if isinstance(color_value, int):
        color = list(PlayerColor)[color_value]
    else:
        color = PlayerColor(color_value or PlayerColor.RED.value)
    tokens = [_token_from_dict(token, color) for token in player_data.get('tokens', [])]
    player = Player(
        id=player_data.get('id'),
        name=player_data.get('name'),
        color=color,
        tokens=tokens,
    )
    player.is_current_turn = bool(player_data.get('isCurrentTurn', False))
    player.consecutive_sixes = int(player_data.get('consecutiveSixes', 0))
    player.tokens_reached_home = int(player_data.get('tokensReachedHome', 0))
    player.is_ai = bool(player_data.get('isAI', player_data.get('type', 0) == 1))
    return player


def _room_payload(room) -> dict:
    payload = room.to_dict()
    payload['players'] = [player.to_dict() for player in room.players.values()]
    payload['spectators'] = list(room.spectators)
    payload['lockedBy'] = room.locked_by
    payload['stateVersion'] = room.state_version
    payload['isStarted'] = room.is_started
    payload['startedAt'] = room.started_at.isoformat() if room.started_at else None
    payload['createdAt'] = room.created_at.isoformat() if room.created_at else None
    if room.game_state:
        payload['gameState'] = room.game_state.to_dict()
    return payload


def _room_from_payload(payload):
    from app.room_manager import GameRoom

    room = GameRoom(
        payload.get('roomId'),
        payload.get('name'),
        payload.get('creatorId'),
        payload.get('maxPlayers', 4),
    )
    room.state_version = int(payload.get('stateVersion', 0))
    room.is_started = bool(payload.get('isStarted', False))
    room.locked_by = payload.get('lockedBy')
    room.created_at = _parse_datetime(payload.get('createdAt')) or room.created_at
    room.started_at = _parse_datetime(payload.get('startedAt'))
    room.spectators = set(payload.get('spectators', []))

    players = payload.get('players') or []
    if players:
        for player_data in players:
            player = _player_from_dict(player_data)
            room.players[player.id] = player

    game_state_payload = payload.get('gameState')
    if game_state_payload:
        game_players = [_player_from_dict(player) for player in game_state_payload.get('players', [])]
        game_state = GameState(id=game_state_payload.get('id') or room.room_id, players=game_players)
        status_value = game_state_payload.get('status')
        if isinstance(status_value, int):
            game_state.status = list(GameStatus)[status_value]
        elif status_value:
            game_state.status = GameStatus(status_value)
        game_state.current_player_index = int(game_state_payload.get('currentPlayerIndex', 0))
        game_state.dice_value = int(game_state_payload.get('diceValue', 0))
        game_state.dice_rolled = bool(game_state_payload.get('diceRolled', False))
        game_state.can_move = bool(game_state_payload.get('canMove', False))
        game_state.rankings = game_state_payload.get('rankings', [])
        game_state.created_at = _parse_datetime(game_state_payload.get('createdAt')) or game_state.created_at
        game_state.started_at = _parse_datetime(game_state_payload.get('startedAt'))
        game_state.ended_at = _parse_datetime(game_state_payload.get('endedAt'))
        room.game_state = game_state

    return room


def save_room(room) -> None:
    """Save room metadata and game state to PostgreSQL."""
    _ensure_table()
    payload = _room_payload(room)
    execute(
        """
        INSERT INTO game_rooms (room_id, room_data, created_at, updated_at)
        VALUES (%(room_id)s, %(room_data)s, COALESCE(%(created_at)s, now()), now())
        ON CONFLICT (room_id) DO UPDATE SET
          room_data = EXCLUDED.room_data,
          updated_at = now()
        """,
        {
            'room_id': room.room_id,
            'room_data': json_value(payload),
            'created_at': room.created_at,
        },
    )


def delete_room(room_id: str) -> None:
    _ensure_table()
    execute('DELETE FROM game_rooms WHERE room_id = %(room_id)s', {'room_id': room_id})


def load_room(room_id: str) -> Optional[object]:
    _ensure_table()
    row = fetch_one('SELECT room_data FROM game_rooms WHERE room_id = %(room_id)s', {'room_id': room_id})
    if not row:
        return None
    return _room_from_payload(row.get('room_data') or {})


def load_all_rooms() -> Dict[str, object]:
    _ensure_table()
    rooms = {}
    for row in fetch_all('SELECT room_id, room_data FROM game_rooms ORDER BY updated_at DESC'):
        room = _room_from_payload(row.get('room_data') or {})
        if room:
            rooms[row['room_id']] = room
    return rooms

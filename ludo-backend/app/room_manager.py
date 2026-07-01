# Ludo Room Manager - Handle multiplayer rooms
import uuid
from typing import Dict, List, Optional
from datetime import datetime
from app.game_engine import GameState, Player, PlayerColor, GameStatus, GameEngine, BoardConfig
from app.persistence import save_room, delete_room, load_all_rooms
import logging
import threading
import time
import asyncio
from app.audit import audit_event

logger = logging.getLogger(__name__)
# Minimum seconds between bot action spawns per room
BOT_MIN_DELAY = 0.8
# Seconds to wait for human players before filling with bots
MATCH_FILL_TIMEOUT = 6.0

class GameRoom:
    """Represents a single multiplayer game room"""
    
    def __init__(
        self,
        room_id: str,
        name: str,
        creator_id: str,
        max_players: int = 4,
    ):
        self.room_id = room_id
        self.name = name
        self.creator_id = creator_id
        self.max_players = max_players
        self.players: Dict[str, Player] = {}
        self.game_state: Optional[GameState] = None
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.is_started = False
        self.spectators: set = set()
        self.locked_by: Optional[str] = None
        self.state_version = 0
        self.lock_acquired_at: Optional[datetime] = None
        # bot concurrency control
        self.bot_active: bool = False
        self.bot_last_action: Optional[float] = None

    @property
    def is_full(self) -> bool:
        return len(self.players) >= self.max_players

    @property
    def player_ids(self) -> List[str]:
        return list(self.players.keys())

    def add_player(self, player: Player) -> bool:
        """Add player to room"""
        if self.is_full:
            logger.warning(f"Room {self.room_id} is full")
            return False
        
        if player.id in self.players:
            logger.warning(f"Player {player.id} already in room {self.room_id}")
            return False
        
        self.players[player.id] = player
        logger.info(f"Player {player.name} added to room {self.room_id}")
        return True

    def remove_player(self, player_id: str) -> bool:
        """Remove player from room"""
        if player_id in self.players:
            del self.players[player_id]
            logger.info(f"Player {player_id} removed from room {self.room_id}")
            return True
        return False

    def add_spectator(self, spectator_id: str) -> None:
        """Add spectator"""
        self.spectators.add(spectator_id)

    def remove_spectator(self, spectator_id: str) -> None:
        """Remove spectator"""
        self.spectators.discard(spectator_id)

    def start_game(self) -> bool:
        """Start the game"""
        if len(self.players) < 2:
            logger.warning(f"Cannot start game in room {self.room_id}: not enough players")
            return False
        
        if self.is_started:
            logger.warning(f"Game in room {self.room_id} already started")
            return False
        
        # Create game state
        players = list(self.players.values())
        self.game_state = GameState(
            id=self.room_id,
            players=players,
            status=GameStatus.PLAYING,
        )
        self.game_state.started_at = datetime.now()
        self.is_started = True
        self.started_at = datetime.now()
        
        logger.info(f"Game started in room {self.room_id} with {len(players)} players")
        return True

    def acquire_lock(self, player_id: str) -> bool:
        """Try to acquire room lock for a player. Returns True on success."""
        LOCK_TIMEOUT = 5  # seconds
        now = datetime.now()
        # auto-release stale lock
        if self.locked_by is not None and self.lock_acquired_at is not None:
            age = (now - self.lock_acquired_at).total_seconds()
            if age > LOCK_TIMEOUT:
                # stale lock; release
                self.locked_by = None
                self.lock_acquired_at = None

        if self.locked_by is None or self.locked_by == player_id:
            self.locked_by = player_id
            self.lock_acquired_at = now
            return True
        return False

    def release_lock(self, player_id: str) -> None:
        """Release the lock if held by player."""
        if self.locked_by == player_id:
            self.locked_by = None
            self.lock_acquired_at = None

    def to_dict(self) -> dict:
        return {
            "roomId": self.room_id,
            "name": self.name,
            "creatorId": self.creator_id,
            "maxPlayers": self.max_players,
            "playerCount": len(self.players),
            "playerIds": self.player_ids,
            "players": [player.to_dict() for player in self.players.values()],
            "isStarted": self.is_started,
            "isFull": self.is_full,
            "createdAt": self.created_at.isoformat(),
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "spectators": list(self.spectators),
            "lockedBy": self.locked_by,
            "stateVersion": self.state_version,
        }

class RoomManager:
    """Manage all multiplayer game rooms"""
    
    def __init__(self):
        self.rooms: Dict[str, GameRoom] = {}
        self.player_rooms: Dict[str, str] = {}  # player_id -> room_id
        logger.info("RoomManager initialized")
        # track last action timestamps per player to prevent spamming
        self.player_action_timestamps: Dict[str, Dict[str, float]] = {}
        # track player violations for anti-cheat (e.g., rapid spam)
        self.player_violations: Dict[str, Dict[str, float]] = {}
        # violation threshold for automatic disconnect
        self.MAX_VIOLATIONS = 3
        # Load persisted rooms on startup
        try:
            persisted = load_all_rooms()
            for rid, room in persisted.items():
                self.rooms[rid] = room
                # populate player_rooms map
                for pid in room.player_ids:
                    self.player_rooms[pid] = rid
            logger.info(f"Loaded {len(persisted)} persisted rooms")
        except Exception:
            pass

    def create_room(
        self,
        room_name: str,
        creator_id: str,
        max_players: int = 4,
    ) -> GameRoom:
        """Create a new game room"""
        room_id = str(uuid.uuid4())[:8].upper()
        room = GameRoom(room_id, room_name, creator_id, max_players)
        self.rooms[room_id] = room
        logger.info(f"Room {room_id} created by {creator_id}")
        try:
            audit_event('room_created', {'roomId': room_id, 'creator': creator_id, 'maxPlayers': max_players})
        except Exception:
            pass
        try:
            save_room(room)
        except Exception:
            pass
        return room

    def find_or_join_match(self, player_id: str, player_name: str, max_players: int = 4) -> Optional[GameRoom]:
        """Find an open room and join the player, or create a new room and add the player.
        Returns the GameRoom the player was added to, or None on failure.
        """
        # Try to find an available room
        for room in self.rooms.values():
            if not room.is_started and not room.is_full:
                # pick a free color
                used_colors = {p.color for p in room.players.values()}
                available = [c for c in list(PlayerColor) if c not in used_colors]
                color = available[0] if available else list(PlayerColor)[0]
                player = Player(id=player_id, name=player_name, color=color)
                if room.add_player(player):
                    self.player_rooms[player.id] = room.room_id
                    try:
                        save_room(room)
                    except Exception:
                        pass
                    return room

        # No suitable room found — create one and add player
        room = self.create_room(room_name=f"QuickMatch_{int(time.time())}", creator_id=player_id, max_players=max_players)
        # assign a color
        color = list(PlayerColor)[0]
        player = Player(id=player_id, name=player_name, color=color)
        room.add_player(player)
        self.player_rooms[player.id] = room.room_id
        try:
            save_room(room)
        except Exception:
            pass
        try:
            audit_event('quickmatch_created', {'roomId': room.room_id, 'creator': player_id, 'maxPlayers': max_players})
        except Exception:
            pass
        # Start a background timer: if room doesn't fill within MATCH_FILL_TIMEOUT, add bots to fill and start
        def _start_fill_timer(rid: str, delay: float):
            time.sleep(delay)
            r = self.get_room(rid)
            if not r or r.is_started:
                return
            # Fill remaining slots with bots
            try:
                while len(r.players) < r.max_players:
                    bot = self.add_bot(rid, bot_name=f"Bot_{len(r.players)+1}")
                    try:
                        audit_event('match_fill_bot', {'roomId': rid, 'botId': bot.id if bot else None})
                    except Exception:
                        pass
                    time.sleep(0.15)
                # If at least two players now, start the game
                if len(r.players) >= 2:
                    self.start_room_game(rid)
                    try:
                        audit_event('match_auto_started', {'roomId': rid, 'filledWithBots': True})
                    except Exception:
                        pass
                    # broadcast match ready / game started
                    try:
                        from app.websocket_handler import connection_manager
                        import asyncio
                        asyncio.run(connection_manager.broadcast_to_room(
                                rid,
                                {
                                    "type": "game_started",
                                    "room": r.to_dict(),
                                    "gameState": r.game_state.to_dict() if r.game_state else None,
                                    "stateVersion": r.state_version,
                                }
                            ))
                    except Exception:
                        pass
            except Exception:
                pass

        threading.Thread(target=_start_fill_timer, args=(room.room_id, MATCH_FILL_TIMEOUT), daemon=True).start()
        return room

    def join_room(self, room_id: str, player: Player) -> bool:
        """Join existing room"""
        if room_id not in self.rooms:
            logger.warning(f"Room {room_id} not found")
            return False
        
        room = self.rooms[room_id]
        
        if room.is_started:
            # Can only watch if game started
            room.add_spectator(player.id)
            logger.info(f"Player {player.id} joined as spectator in room {room_id}")
            return True
        
        if room.is_full:
            logger.warning(f"Room {room_id} is full")
            return False
        
        if room.add_player(player):
            self.player_rooms[player.id] = room_id
            try:
                save_room(room)
            except Exception:
                pass
            return True
        
        return False

    def leave_room(self, room_id: str, player_id: str) -> None:
        """Leave room"""
        if room_id not in self.rooms:
            return
        
        room = self.rooms[room_id]
        room.remove_player(player_id)
        room.remove_spectator(player_id)
        
        if player_id in self.player_rooms:
            del self.player_rooms[player_id]
        
        # Delete room if empty
        if len(room.players) == 0 and len(room.spectators) == 0:
            del self.rooms[room_id]
            logger.info(f"Room {room_id} deleted (empty)")
            try:
                audit_event('room_deleted', {'roomId': room_id, 'by': player_id})
            except Exception:
                pass
            try:
                delete_room(room_id)
            except Exception:
                pass
            return
        else:
            try:
                save_room(room)
            except Exception:
                pass

    def get_room(self, room_id: str) -> Optional[GameRoom]:
        """Get room by ID"""
        return self.rooms.get(room_id)

    def get_player_room(self, player_id: str) -> Optional[GameRoom]:
        """Get room where player is playing"""
        room_id = self.player_rooms.get(player_id)
        if room_id:
            return self.rooms.get(room_id)
        return None

    def can_perform_action(self, player_id: str, action: str, min_interval: float) -> bool:
        """Return True if player can perform action (rate limited by min_interval seconds)."""
        now = time.time()
        if player_id not in self.player_action_timestamps:
            self.player_action_timestamps[player_id] = {}

        last = self.player_action_timestamps[player_id].get(action)
        if last is None or (now - last) >= min_interval:
            self.player_action_timestamps[player_id][action] = now
            return True
        return False

    def record_violation(self, player_id: str, reason: str = "") -> int:
        """Record a violation for a player and return current count."""
        now = time.time()
        if player_id not in self.player_violations:
            self.player_violations[player_id] = {"count": 0, "last": now, "reason": reason}

        v = self.player_violations[player_id]
        # simple increment and timestamp
        v["count"] = v.get("count", 0) + 1
        v["last"] = now
        v["reason"] = reason
        return v["count"]

    def clear_violations(self, player_id: str) -> None:
        if player_id in self.player_violations:
            del self.player_violations[player_id]

    def list_available_rooms(self) -> List[GameRoom]:
        """List all available rooms (not started or not full)"""
        return [
            room for room in self.rooms.values()
            if not room.is_started and not room.is_full
        ]

    def start_room_game(self, room_id: str) -> bool:
        """Start game in room"""
        room = self.get_room(room_id)
        if room:
            ok = room.start_game()
            try:
                save_room(room)
            except Exception:
                pass
            return ok
        return False

    # Undo / dispute support
    def request_undo(self, room_id: str, player_id: str) -> bool:
        room = self.get_room(room_id)
        if not room or not room.game_state:
            return False

        # Create undo ballot
        room.undo_request = {
            "requester": player_id,
            "votes": {player_id: True},
        }
        return True

    def vote_undo(self, room_id: str, voter_id: str, accept: bool) -> bool:
        room = self.get_room(room_id)
        if not room or not room.game_state or not hasattr(room, 'undo_request'):
            return False
        ballot = room.undo_request
        ballot['votes'][voter_id] = bool(accept)

        # evaluate votes: majority of active players (players in room.players)
        total = len([pid for pid in room.player_ids if pid in room.players])
        yes = sum(1 for v in ballot['votes'].values() if v)
        # accept if yes > total/2
        if yes > total / 2:
            # apply undo
            ok = False
            try:
                ok = GameEngine.undo_last_move(room.game_state)
                if ok:
                    save_room(room)
            except Exception:
                ok = False
            # clear ballot
            delattr(room, 'undo_request')
            return ok

        # not yet decided
        return True

    def validate_move(
        self,
        room_id: str,
        player_id: str,
        token_id: int,
        new_position: int,
        dice_value: int,
    ) -> bool:
        """Validate if move is legal"""
        room = self.get_room(room_id)
        if not room or not room.game_state:
            return False
        
        game_state = room.game_state
        
        # Check if it's player's turn
        if game_state.current_player.id != player_id:
            logger.warning(f"Not player {player_id}'s turn in room {room_id}")
            return False

        # Must have rolled dice before moving
        if not game_state.dice_rolled:
            logger.warning(f"Player {player_id} attempted to move without rolling in room {room_id}")
            return False
        
        # Get token
        player = room.players.get(player_id)
        if not player or token_id >= len(player.tokens):
            return False
        
        token = player.tokens[token_id]
        
        # Validate move (server authoritative)
        # Ensure dice_value matches current game state's dice
        if dice_value != game_state.dice_value:
            logger.warning(f"Dice value mismatch for player {player_id} in room {room_id}: client {dice_value} != server {game_state.dice_value}")
            return False

        # Calculate expected new position and compare
        expected_pos = GameEngine.calculate_new_position(token, dice_value, player.color)
        if expected_pos != new_position:
            logger.warning(f"Player {player_id} move position mismatch in room {room_id}: expected {expected_pos}, got {new_position}")
            return False

        is_valid = GameEngine.is_valid_move(token, dice_value, new_position)
        if not is_valid:
            logger.warning(f"Invalid move by player {player_id} in room {room_id}: token {token_id} -> {new_position} with dice {dice_value}")
        return is_valid

    def add_bot(self, room_id: str, bot_name: str = "Bot") -> Optional[Player]:
        """Add an AI bot to the room. Returns the created Player or None."""
        room = self.get_room(room_id)
        if not room:
            return None

        # Choose a free color
        used_colors = {p.color for p in room.players.values()}
        available = [c for c in list(PlayerColor) if c not in used_colors]
        if not available:
            return None

        color = available[0]
        bot_id = f"bot_{int(time.time()*1000)}"
        bot = Player(id=bot_id, name=bot_name, color=color)
        bot.is_ai = True

        if room.add_player(bot):
            self.player_rooms[bot.id] = room_id
            try:
                save_room(room)
            except Exception:
                pass
            try:
                audit_event('bot_added', {'roomId': room_id, 'botId': bot.id, 'botName': bot.name})
            except Exception:
                pass
            return bot
        return None

    def _bot_play_thread(self, room_id: str):
        """Thread target: run a single bot's turn loop until it's not the bot's turn or game ends."""
        room = self.get_room(room_id)
        if not room or not room.game_state:
            return

        # small delay to simulate thinking/animation
        time.sleep(0.6)
        gs = room.game_state
        current = gs.current_player
        # mark bot active and last action time
        room.bot_active = True
        room.bot_last_action = time.time()
        # roll dice
        if not gs.dice_rolled:
            dice_value = GameEngine.roll_dice()
            gs.dice_value = dice_value
            gs.dice_rolled = True
            gs.can_move = len(GameEngine.get_movable_tokens(current, dice_value)) > 0
            try:
                save_room(room)
            except Exception:
                pass
            # broadcast dice roll to room
            try:
                from app.websocket_handler import connection_manager
                asyncio.run(connection_manager.broadcast_to_room(
                    room_id,
                    {
                        "type": "dice_rolled",
                        "playerId": current.id,
                        "diceValue": dice_value,
                        "canMove": gs.can_move,
                        "gameState": gs.to_dict(),
                        "stateVersion": room.state_version,
                    },
                ))
            except Exception:
                pass

        # If can move, pick best move using heuristic
        movable = GameEngine.get_movable_tokens(current, gs.dice_value)
        if movable:
            best_token = None
            best_score = float('-inf')

            for t in movable:
                expected = GameEngine.calculate_new_position(t, gs.dice_value, current.color)
                score = 0.0

                # prefer opening tokens
                if t.position == -1:
                    score += 30.0

                # prefer moves that enter the home path
                if expected >= BoardConfig.TOTAL_POSITIONS:
                    score += 50.0

                # prefer captures
                opps = GameEngine.get_tokens_at_position(gs.players, expected, current.color)
                if opps and not GameEngine.is_safe_position(expected, current.color):
                    score += 100.0

                # progress: prefer tokens that advance farther
                progress = expected if expected >= 0 else 0
                score += progress * 0.05

                # penalize risky unsafe landings that don't capture
                if not GameEngine.is_safe_position(expected, current.color) and not opps:
                    score -= 40.0

                if score > best_score:
                    best_score = score
                    best_token = t

            pick = best_token if best_token is not None else movable[0]

            # find token index
            token_index = None
            for idx, tk in enumerate(current.tokens):
                if tk.id == pick.id:
                    token_index = idx
                    break

            if token_index is not None:
                # execute move
                self.execute_move(room_id, current.id, token_index)
                # broadcast token moved
                try:
                    from app.websocket_handler import connection_manager
                    asyncio.run(connection_manager.broadcast_to_room(
                        room_id,
                        {
                            "type": "token_moved",
                            "playerId": current.id,
                            "tokenId": token_index,
                            "newPosition": GameEngine.calculate_new_position(pick, gs.dice_value, current.color),
                            "gameState": gs.to_dict(),
                            "stateVersion": room.state_version,
                        },
                    ))
                except Exception:
                    pass

                # update last action timestamp to avoid immediate re-spawn
                room.bot_last_action = time.time()

        # handle extra rolls on 6
        if gs.dice_value == 6 and current.consecutive_sixes < 3 and gs.status == GameStatus.PLAYING and current.id in room.players:
            # schedule another bot action after brief pause
            time.sleep(0.4)
            # reset dice_rolled so bot can roll again
            gs.dice_rolled = False
            self._bot_play_thread(room_id)
            return
            return

        # finish bot turn
        current.consecutive_sixes = 0
        self.end_turn(room_id)
        # if game ended broadcast final state
        if gs.status == GameStatus.FINISHED or len(gs.rankings) >= len(gs.players):
            try:
                from app.websocket_handler import connection_manager
                asyncio.run(connection_manager.broadcast_to_room(
                    room_id,
                    {
                        "type": "game_ended",
                        "rankings": gs.rankings,
                        "gameState": gs.to_dict(),
                        "stateVersion": room.state_version,
                    }
                ))
            except Exception:
                pass
        # mark bot inactive so future triggers can run
        room.bot_active = False
        room.bot_last_action = time.time()

    def trigger_bot_if_needed(self, room_id: str) -> None:
        """If current player is AI, spawn a thread to process its turn."""
        room = self.get_room(room_id)
        if not room or not room.game_state:
            return
        current = room.game_state.current_player
        if current.is_ai:
            now = time.time()
            # avoid spawning if bot is already active
            if room.bot_active:
                return
            # enforce minimum delay between bot spawns
            if room.bot_last_action and (now - room.bot_last_action) < BOT_MIN_DELAY:
                return
            t = threading.Thread(target=self._bot_play_thread, args=(room_id,), daemon=True)
            t.start()

    def execute_move(
        self,
        room_id: str,
        player_id: str,
        token_id: int,
    ) -> bool:
        """Execute move in room (locked, saved, and bump state_version)."""
        room = self.get_room(room_id)
        if not room or not room.game_state:
            return False

        game_state = room.game_state
        player = room.players.get(player_id)

        if not player or token_id >= len(player.tokens):
            return False

        token = player.tokens[token_id]

        # Acquire lock to prevent concurrent modifications
        if not room.acquire_lock(player_id):
            logger.warning(f"Room {room_id} locked by {room.locked_by}, {player_id} cannot execute move now")
            return False

        try:
            result = GameEngine.execute_move(game_state, token, game_state.dice_value)
            # mark dice as consumed (move resolved)
            game_state.dice_rolled = False
            game_state.can_move = False

            # If player finished (all tokens home), record ranking
            if player.tokens_reached_home >= 4 and player.id not in game_state.rankings:
                game_state.rankings.append(player.id)
                # Set winner if first finisher
                if len(game_state.rankings) == 1:
                    game_state.winner = player

            # Bump state version centrally here to avoid races
            room.state_version += 1

            try:
                save_room(room)
            except Exception:
                pass

            return result
        finally:
            room.release_lock(player_id)

    def end_turn(self, room_id: str) -> None:
        """End current player's turn and advance to next eligible player."""
        room = self.get_room(room_id)
        if not room or not room.game_state:
            return
        game_state = room.game_state

        n = len(game_state.players)
        if n == 0:
            return

        start = game_state.current_player_index
        found = False

        # Advance to next eligible player (not finished and still present in room)
        for i in range(1, n + 1):
            next_index = (start + i) % n
            candidate = game_state.players[next_index]

            # Skip players who have finished
            if candidate.tokens_reached_home >= 4:
                continue

            # Skip players who are no longer in the room (disconnected/left)
            if candidate.id not in room.players:
                continue

            # Found next player
            game_state.current_player_index = next_index
            found = True
            break

        # If no eligible players found, finish game
        if not found:
            game_state.status = GameStatus.FINISHED
            room.state_version += 1
            logger.info(f"Game in room {room_id} ended: no eligible players remaining")
            try:
                save_room(room)
            except Exception:
                pass
            return

        # Reset dice and move flags for next player
        game_state.dice_value = 0
        game_state.dice_rolled = False
        game_state.can_move = False
        # Reset consecutive sixes for the new current player
        game_state.current_player.consecutive_sixes = 0

        room.state_version += 1
        try:
            save_room(room)
        except Exception:
            pass

        # If the new current player is an AI, trigger bot play
        if game_state.current_player.is_ai:
            # run bot in background
            threading.Thread(target=self._bot_play_thread, args=(room_id,), daemon=True).start()

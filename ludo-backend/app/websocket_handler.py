# Ludo WebSocket Handler - Real-time multiplayer communication
from fastapi import WebSocket
from typing import Dict, Set, List
import json
import logging
from app.game_engine import GameEngine, Player, PlayerColor, GameStatus
from app.audit import audit_event

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Manage WebSocket connections"""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}  # room_id -> set of websockets
        self.player_connections: Dict[str, WebSocket] = {}  # player_id -> websocket

    async def connect(self, websocket: WebSocket, room_id: str, player_id: str):
        """Add a new connection"""
        await websocket.accept()
        # Clean up previous connection for this player (reconnect case)
        if player_id in self.player_connections:
            old_ws = self.player_connections[player_id]
            # remove old websocket from any room sets
            for rid, conns in self.active_connections.items():
                if old_ws in conns:
                    conns.discard(old_ws)
        
        if room_id not in self.active_connections:
            self.active_connections[room_id] = set()

        self.active_connections[room_id].add(websocket)
        self.player_connections[player_id] = websocket

        logger.info(f"Player {player_id} connected to room {room_id}")

    def disconnect(self, room_id: str, player_id: str):
        """Remove a connection"""
        if room_id in self.active_connections:
            # Find and remove websocket
            for ws in list(self.active_connections[room_id]):
                try:
                    if self.player_connections.get(player_id) == ws:
                        self.active_connections[room_id].discard(ws)
                        break
                except:
                    pass
        
        if player_id in self.player_connections:
            del self.player_connections[player_id]
        
        logger.info(f"Player {player_id} disconnected from room {room_id}")

    async def broadcast_to_room(self, room_id: str, message: dict):
        """Send message to all players in room"""
        if room_id not in self.active_connections:
            return
        
        disconnected = set()
        for connection in self.active_connections[room_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected
        self.active_connections[room_id] -= disconnected

    async def send_personal_message(self, player_id: str, message: dict):
        """Send message to specific player"""
        if player_id in self.player_connections:
            try:
                await self.player_connections[player_id].send_json(message)
            except Exception as e:
                logger.error(f"Error sending personal message: {e}")

# Global connection manager
connection_manager = ConnectionManager()

def setup_websocket_handlers(app, room_manager, game_engine):
    """Setup WebSocket handlers for the app"""
    
    @app.websocket("/ws/{room_id}/{player_id}")
    async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):
        """Main WebSocket endpoint for multiplayer games"""
        
        await connection_manager.connect(websocket, room_id, player_id)
        
        try:
            # After connect, send current authoritative state to this player (in case of reconnect)
            room = room_manager.get_room(room_id)
            if room and room.game_state:
                await connection_manager.send_personal_message(
                    player_id,
                    {
                        "type": "game_state",
                        "gameState": room.game_state.to_dict(),
                        "stateVersion": room.state_version,
                    },
                )
                # announce reconnection to room
                await connection_manager.broadcast_to_room(
                    room_id,
                    {
                        "type": "player_reconnected",
                        "playerId": player_id,
                        "stateVersion": room.state_version,
                    },
                )
            while True:
                data = await websocket.receive_json()
                event_type = data.get("type")
                
                # Handle different event types
                if event_type == "join_room":
                    await handle_join_room(
                        websocket, room_id, player_id, data, room_manager
                    )

                elif event_type == "quick_match":
                    await handle_quick_match(websocket, room_id, player_id, data, room_manager)
                
                elif event_type == "start_game":
                    await handle_start_game(
                        websocket, room_id, player_id, data, room_manager
                    )
                
                elif event_type == "roll_dice":
                    await handle_roll_dice(
                        websocket, room_id, player_id, data, room_manager, game_engine
                    )
                
                elif event_type == "move_token":
                    await handle_move_token(
                        websocket, room_id, player_id, data, room_manager, game_engine
                    )

                elif event_type == "sync_state":
                    await handle_get_state(
                        websocket, room_id, player_id, data, room_manager
                    )
                
                elif event_type == "get_state":
                    await handle_get_state(
                        websocket, room_id, player_id, data, room_manager
                    )
                
                elif event_type == "chat":
                    await handle_chat(
                        websocket, room_id, player_id, data
                    )
                elif event_type == "request_undo":
                    await handle_request_undo(websocket, room_id, player_id, data, room_manager)
                elif event_type == "vote_undo":
                    await handle_vote_undo(websocket, room_id, player_id, data, room_manager)
                elif event_type == "cancel_quick_match" or event_type == "cancel_match":
                    await handle_cancel_quick_match(websocket, room_id, player_id, data, room_manager)
        
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        
        finally:
            connection_manager.disconnect(room_id, player_id)
            # Notify others that player left
            # room may not exist; fetch safely
            room = None
            try:
                room = room_manager.get_room(room_id)
            except Exception:
                room = None

            payload = {"type": "player_left", "playerId": player_id}
            if room:
                payload["stateVersion"] = room.state_version

            await connection_manager.broadcast_to_room(room_id, payload)

async def handle_join_room(websocket, room_id, player_id, data, room_manager):
    """Handle player joining room"""
    room = room_manager.get_room(room_id)
    if room:
        await connection_manager.broadcast_to_room(
            room_id,
            {
                "type": "player_joined",
                "room": room.to_dict(),
                "playerId": player_id,
                "playerName": data.get("playerName"),
                "stateVersion": room.state_version,
            }
        )
        logger.info(f"Player {player_id} joined room {room_id}")


    async def handle_quick_match(websocket, room_id, player_id, data, room_manager):
        """Find or create a quick match and join the player."""
        player_name = data.get('playerName') or player_id
        max_players = int(data.get('maxPlayers', 4))

        room = room_manager.find_or_join_match(player_id, player_name, max_players=max_players)
        if not room:
            await connection_manager.send_personal_message(player_id, {"type": "match_failed", "message": "Could not find or create match"})
            return

        # inform player of the room
        await connection_manager.send_personal_message(player_id, {"type": "match_found", "roomId": room.room_id, "stateVersion": room.state_version, "room": room.to_dict()})

        # broadcast player joined to room
        await connection_manager.broadcast_to_room(
            room.room_id,
            {
                "type": "player_joined",
                "room": room.to_dict(),
                "playerId": player_id,
                "playerName": player_name,
                "stateVersion": room.state_version,
            }
        )

async def handle_start_game(websocket, room_id, player_id, data, room_manager):
    """Handle game start"""
    if room_manager.start_room_game(room_id):
        room = room_manager.get_room(room_id)
        await connection_manager.broadcast_to_room(
            room_id,
            {
                "type": "game_started",
                "gameState": room.game_state.to_dict() if room.game_state else None,
                "stateVersion": room.state_version,
            }
        )
        # If first player is AI, trigger bot play
        try:
            room_manager.trigger_bot_if_needed(room_id)
        except Exception:
            logger.exception("Failed to trigger bot after game start")
        logger.info(f"Game started in room {room_id}")

async def handle_roll_dice(websocket, room_id, player_id, data, room_manager, game_engine):
    """Handle dice roll"""
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return
    
    game_state = room.game_state
    
    # Ensure player is part of the room
    if player_id not in room.players:
        await connection_manager.send_personal_message(
            player_id,
            {"type": "error", "message": "Player not in room"},
        )
        return

    # Only current player can roll
    if game_state.current_player.id != player_id:
        await connection_manager.send_personal_message(
            player_id,
            {"type": "error", "message": "Not your turn"},
        )
        return

    # Prevent rolling again if dice is not yet consumed
    if game_state.dice_rolled:
        await connection_manager.send_personal_message(
            player_id,
            {"type": "error", "message": "Dice already rolled"},
        )
        return

    # Rate limit dice rolls per player (prevent spam/flood)
    if not room_manager.can_perform_action(player_id, 'roll', 0.6):
        await connection_manager.send_personal_message(
            player_id,
            {"type": "error", "message": "Too many roll attempts"},
        )
        # record violation and possibly disconnect
        try:
            cnt = room_manager.record_violation(player_id, 'roll_spam')
            if cnt >= getattr(room_manager, 'MAX_VIOLATIONS', 3):
                await connection_manager.send_personal_message(player_id, {"type": "kicked", "reason": "too_many_violations"})
                connection_manager.disconnect(room_id, player_id)
                await connection_manager.broadcast_to_room(room_id, {"type": "player_kicked", "playerId": player_id, "reason": "too_many_violations"})
        except Exception:
            pass
        return

    # Roll dice server-side (authoritative)
    dice_value = GameEngine.roll_dice()
    game_state.dice_value = dice_value
    game_state.dice_rolled = True
    room.state_version += 1

    # Get movable tokens
    movable_tokens = GameEngine.get_movable_tokens(game_state.current_player, dice_value)
    game_state.can_move = len(movable_tokens) > 0

    # Broadcast dice roll
    await connection_manager.broadcast_to_room(
        room_id,
        {
            "type": "dice_rolled",
            "playerId": player_id,
            "diceValue": dice_value,
            "canMove": game_state.can_move,
            "gameState": game_state.to_dict(),
            "stateVersion": room.state_version,
        },
    )

async def handle_cancel_quick_match(websocket, room_id, player_id, data, room_manager):
    """Handle cancellation of a quick-match request by a player."""
    try:
        # Find the room where the player is currently waiting
        room = room_manager.get_player_room(player_id)
        if not room:
            # nothing to cancel
            await connection_manager.send_personal_message(player_id, {"type": "match_failed", "message": "No pending match to cancel"})
            return

        # Only allow cancellation if the game hasn't started yet
        if room.is_started:
            await connection_manager.send_personal_message(player_id, {"type": "match_failed", "message": "Game already started"})
            return

        # Remove player from room
        room_manager.leave_room(room.room_id, player_id)
        try:
            audit_event('match_cancelled', {'roomId': room.room_id, 'playerId': player_id})
        except Exception:
            pass

        # Notify the player that match was cancelled
        await connection_manager.send_personal_message(player_id, {"type": "match_failed", "message": "Match cancelled by player"})

        # Broadcast updated room info to remaining players (if any)
        try:
            await connection_manager.broadcast_to_room(
                room.room_id,
                {
                    "type": "player_left",
                    "playerId": player_id,
                    "room": room.to_dict(),
                },
            )
        except Exception:
            pass
    except Exception as e:
        logger.exception(f"Failed to cancel quick match for {player_id}: {e}")

async def handle_move_token(websocket, room_id, player_id, data, room_manager, game_engine):
    """Handle token move"""
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return
    
    game_state = room.game_state
    token_id = data.get("tokenId")
    new_position = data.get("newPosition")
    
    # Ensure player is part of the room
    if player_id not in room.players:
        await connection_manager.send_personal_message(
            player_id,
            {"type": "error", "message": "Player not in room"},
        )
        try:
            cnt = room_manager.record_violation(player_id, 'not_in_room')
            if cnt >= getattr(room_manager, 'MAX_VIOLATIONS', 3):
                await connection_manager.send_personal_message(player_id, {"type": "kicked", "reason": "too_many_violations"})
                connection_manager.disconnect(room_id, player_id)
                await connection_manager.broadcast_to_room(room_id, {"type": "player_kicked", "playerId": player_id, "reason": "too_many_violations"})
        except Exception:
            pass
        return

    # Rate limit moves per player
    if not room_manager.can_perform_action(player_id, 'move', 0.25):
        await connection_manager.send_personal_message(
            player_id,
            {"type": "error", "message": "Too many move attempts"},
        )
        try:
            cnt = room_manager.record_violation(player_id, 'move_spam')
            if cnt >= getattr(room_manager, 'MAX_VIOLATIONS', 3):
                await connection_manager.send_personal_message(player_id, {"type": "kicked", "reason": "too_many_violations"})
                connection_manager.disconnect(room_id, player_id)
                await connection_manager.broadcast_to_room(room_id, {"type": "player_kicked", "playerId": player_id, "reason": "too_many_violations"})
        except Exception:
            pass
        return

    # Validate move
    if not room_manager.validate_move(room_id, player_id, token_id, new_position, game_state.dice_value):
        await connection_manager.send_personal_message(
            player_id,
            {"type": "move_invalid", "message": "Invalid move"},
        )
        try:
            cnt = room_manager.record_violation(player_id, 'invalid_move')
            if cnt >= getattr(room_manager, 'MAX_VIOLATIONS', 3):
                await connection_manager.send_personal_message(player_id, {"type": "kicked", "reason": "too_many_violations"})
                connection_manager.disconnect(room_id, player_id)
                await connection_manager.broadcast_to_room(room_id, {"type": "player_kicked", "playerId": player_id, "reason": "too_many_violations"})
        except Exception:
            pass
        return

    # Execute move (RoomManager handles locking)
    success = room_manager.execute_move(room_id, player_id, token_id)
    if not success:
        await connection_manager.send_personal_message(
            player_id,
            {"type": "move_failed", "message": "Move could not be executed"},
        )
        return

    player = game_state.current_player

    # If player finished this move, broadcast finished event with rank
    if player.id in game_state.rankings:
        rank = game_state.rankings.index(player.id) + 1
        await connection_manager.broadcast_to_room(
            room_id,
            {
                "type": "player_finished",
                "playerId": player.id,
                "rank": rank,
                "gameState": game_state.to_dict(),
            },
        )

    # If first finisher, ensure winner is set
    if game_state.rankings:
        first_id = game_state.rankings[0]
        if game_state.winner is None or game_state.winner.id != first_id:
            # find player object
            for p in game_state.players:
                if p.id == first_id:
                    game_state.winner = p
                    break

    # Handle consecutive sixes and extra roll logic
    if game_state.dice_value == 6:
        player.consecutive_sixes += 1
        # After 3 consecutive sixes, cancel extra and end turn
        if player.consecutive_sixes >= 3:
            player.consecutive_sixes = 0
            room_manager.end_turn(room_id)
    else:
        player.consecutive_sixes = 0
        room_manager.end_turn(room_id)

    # Broadcast move
    await connection_manager.broadcast_to_room(
        room_id,
        {
            "type": "token_moved",
            "playerId": player_id,
            "tokenId": token_id,
            "newPosition": new_position,
            "gameState": game_state.to_dict(),
            "stateVersion": room.state_version,
        },
    )

    # If all players have finished or game marked finished, broadcast final rankings
    if game_state.status == GameStatus.FINISHED or len(game_state.rankings) >= len(game_state.players):
        await connection_manager.broadcast_to_room(
            room_id,
            {
                "type": "game_ended",
                "rankings": game_state.rankings,
                "gameState": game_state.to_dict(),
                "stateVersion": room.state_version,
            },
        )

async def handle_get_state(websocket, room_id, player_id, data, room_manager):
    """Handle get game state request"""
    room = room_manager.get_room(room_id)
    if room and room.game_state:
        await connection_manager.send_personal_message(
            player_id,
            {
                "type": "game_state",
                "gameState": room.game_state.to_dict(),
                "stateVersion": room.state_version,
            }
        )


async def handle_request_undo(websocket, room_id, player_id, data, room_manager):
    """Player requests undo of last move"""
    ok = room_manager.request_undo(room_id, player_id)
    if not ok:
        await connection_manager.send_personal_message(player_id, {"type": "undo_failed", "message": "Cannot request undo"})
        return

    # broadcast undo request
    await connection_manager.broadcast_to_room(room_id, {"type": "undo_requested", "playerId": player_id, "stateVersion": room_manager.get_room(room_id).state_version})


async def handle_vote_undo(websocket, room_id, player_id, data, room_manager):
    """Player votes on an undo request"""
    vote = bool(data.get("accept", False))
    result = room_manager.vote_undo(room_id, player_id, vote)
    if result is True:
        # vote recorded but not decided yet
        await connection_manager.broadcast_to_room(room_id, {"type": "undo_vote_recorded", "playerId": player_id})
        return

    if result is False:
        # undo rejected
        await connection_manager.broadcast_to_room(room_id, {"type": "undo_rejected", "playerId": player_id})
        return

    # if result is True-like but returned ok (i.e., undo applied), send updated state
    await connection_manager.broadcast_to_room(room_id, {"type": "undo_accepted", "gameState": room_manager.get_room(room_id).game_state.to_dict(), "stateVersion": room_manager.get_room(room_id).state_version})

async def handle_chat(websocket, room_id, player_id, data):
    """Handle chat message"""
    message = data.get("message")
    await connection_manager.broadcast_to_room(
        room_id,
        {
            "type": "chat",
            "playerId": player_id,
            "message": message,
        }
    )

# Ludo API Routes
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.game_engine import GameEngine, Player, PlayerColor
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get('/health')
async def health():
    return {'success': True, 'message': 'API is healthy'}

# Pydantic models for API
class PlayerRequest(BaseModel):
    id: str
    name: str
    color: str

class CreateRoomRequest(BaseModel):
    name: str
    creatorId: str
    maxPlayers: int = 4

class JoinRoomRequest(BaseModel):
    player: PlayerRequest

class MoveRequest(BaseModel):
    tokenId: int
    newPosition: int

class DiceRollRequest(BaseModel):
    pass

# Rooms endpoints
@router.post("/rooms")
async def create_room(request: CreateRoomRequest, room_manager):
    """Create a new game room"""
    try:
        room = room_manager.create_room(
            request.name,
            request.creatorId,
            request.maxPlayers,
        )
        return {
            "success": True,
            "room": room.to_dict(),
        }
    except Exception as e:
        logger.error(f"Error creating room: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/rooms")
async def list_rooms(room_manager):
    """List available rooms"""
    try:
        rooms = room_manager.list_available_rooms()
        return {
            "success": True,
            "rooms": [room.to_dict() for room in rooms],
            "count": len(rooms),
        }
    except Exception as e:
        logger.error(f"Error listing rooms: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/rooms/{room_id}")
async def get_room(room_id: str, room_manager):
    """Get room details"""
    try:
        room = room_manager.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        return {
            "success": True,
            "room": room.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting room: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/rooms/{room_id}/join")
async def join_room(room_id: str, request: JoinRoomRequest, room_manager):
    """Join a game room"""
    try:
        player_data = request.player
        player = Player(
            id=player_data.id,
            name=player_data.name,
            color=PlayerColor[player_data.color.upper()],
        )
        
        if room_manager.join_room(room_id, player):
            room = room_manager.get_room(room_id)
            return {
                "success": True,
                "room": room.to_dict() if room else None,
            }
        else:
            raise HTTPException(status_code=400, detail="Cannot join room")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error joining room: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/rooms/{room_id}/leave")
async def leave_room(room_id: str, player_id: str, room_manager):
    """Leave a game room"""
    try:
        room_manager.leave_room(room_id, player_id)
        return {
            "success": True,
            "message": "Left room successfully",
        }
    except Exception as e:
        logger.error(f"Error leaving room: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/rooms/{room_id}/start")
async def start_game(room_id: str, room_manager):
    """Start game in room"""
    try:
        if room_manager.start_room_game(room_id):
            room = room_manager.get_room(room_id)
            return {
                "success": True,
                "gameState": room.game_state.to_dict() if room and room.game_state else None,
            }
        else:
            raise HTTPException(status_code=400, detail="Cannot start game")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting game: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Game endpoints
@router.post("/games/{room_id}/dice")
async def roll_dice(room_id: str, room_manager):
    """Roll dice"""
    try:
        room = room_manager.get_room(room_id)
        if not room or not room.game_state:
            raise HTTPException(status_code=404, detail="Game not found")
        
        dice_value = GameEngine.roll_dice()
        game_state = room.game_state
        game_state.dice_value = dice_value
        game_state.dice_rolled = True
        
        return {
            "success": True,
            "diceValue": dice_value,
            "gameState": game_state.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rolling dice: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/games/{room_id}/state")
async def get_game_state(room_id: str, room_manager):
    """Get current game state"""
    try:
        room = room_manager.get_room(room_id)
        if not room or not room.game_state:
            raise HTTPException(status_code=404, detail="Game not found")
        
        return {
            "success": True,
            "gameState": room.game_state.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting game state: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Stats endpoints
@router.get("/stats/rooms")
async def get_rooms_stats(room_manager):
    """Get rooms statistics"""
    try:
        total_rooms = len(room_manager.rooms)
        active_games = sum(1 for r in room_manager.rooms.values() if r.is_started)
        total_players = sum(len(r.players) for r in room_manager.rooms.values())
        
        return {
            "success": True,
            "stats": {
                "totalRooms": total_rooms,
                "activeGames": active_games,
                "totalPlayers": total_players,
                "availableRooms": total_rooms - active_games,
            }
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats/player/{player_id}")
async def get_player_stats(player_id: str, room_manager):
    """Get player statistics"""
    try:
        room = room_manager.get_player_room(player_id)
        
        return {
            "success": True,
            "playerId": player_id,
            "currentRoom": room.room_id if room else None,
            "inGame": room is not None and room.is_started,
        }
    except Exception as e:
        logger.error(f"Error getting player stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

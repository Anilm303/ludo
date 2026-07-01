# 🌐 Ludo Game - API Documentation

## Base URL
```
Local: http://localhost:8000
Production: https://api.ludo-game.com (example)
```

## Authentication
Currently using `player_id` as identifier (no auth required for MVP)

Future: JWT token-based authentication

---

## 📡 REST API Endpoints

### Health & Status

#### ✅ Health Check
```http
GET /health
```

**Response (200 OK):**
```json
{
  "status": "ok",
  "timestamp": "2026-05-14T10:30:00Z",
  "version": "1.0.0"
}
```

---

### 🎮 Game Rooms

#### 1️⃣ Create Room
```http
POST /api/rooms/create
```

**Request Body:**
```json
{
  "name": "Play with friends",
  "creator_id": "player_123",
  "max_players": 4,
  "difficulty": "medium",
  "is_private": false,
  "password": "optional"
}
```

**Response (201 Created):**
```json
{
  "room_id": "room_abc123",
  "name": "Play with friends",
  "creator_id": "player_123",
  "max_players": 4,
  "current_players": 1,
  "difficulty": "medium",
  "is_private": false,
  "status": "waiting",
  "created_at": "2026-05-14T10:30:00Z",
  "players": [
    {
      "player_id": "player_123",
      "name": "John",
      "is_ready": false,
      "joined_at": "2026-05-14T10:30:00Z"
    }
  ]
}
```

**Errors:**
```json
{
  "detail": "Room name is required",
  "status_code": 400
}
```

---

#### 2️⃣ Join Room
```http
POST /api/rooms/{room_id}/join
```

**Request Body:**
```json
{
  "player_id": "player_456",
  "player_name": "Alice",
  "password": "optional_if_private"
}
```

**Response (200 OK):**
```json
{
  "room_id": "room_abc123",
  "players": [
    {
      "player_id": "player_123",
      "name": "John",
      "color": "red",
      "is_ready": false
    },
    {
      "player_id": "player_456",
      "name": "Alice",
      "color": "green",
      "is_ready": false
    }
  ],
  "game_state": {
    "current_turn": "player_123",
    "status": "waiting",
    "dice_value": null
  }
}
```

**Errors:**
```json
{
  "detail": "Room is full",
  "status_code": 400
}
```

---

#### 3️⃣ Get Available Rooms
```http
GET /api/rooms?difficulty=medium&is_private=false&page=1&limit=10
```

**Query Parameters:**
- `difficulty`: (optional) "easy", "medium", "hard"
- `is_private`: (optional) true/false
- `page`: (optional) default: 1
- `limit`: (optional) default: 10

**Response (200 OK):**
```json
{
  "total": 25,
  "page": 1,
  "limit": 10,
  "rooms": [
    {
      "room_id": "room_abc123",
      "name": "Play with friends",
      "current_players": 2,
      "max_players": 4,
      "difficulty": "medium",
      "is_private": false,
      "status": "waiting",
      "created_at": "2026-05-14T10:30:00Z"
    },
    {
      "room_id": "room_xyz789",
      "name": "Weekend Game",
      "current_players": 3,
      "max_players": 4,
      "difficulty": "hard",
      "is_private": false,
      "status": "in_progress",
      "created_at": "2026-05-14T09:15:00Z"
    }
  ]
}
```

---

#### 4️⃣ Get Room Details
```http
GET /api/rooms/{room_id}
```

**Response (200 OK):**
```json
{
  "room_id": "room_abc123",
  "name": "Play with friends",
  "creator_id": "player_123",
  "max_players": 4,
  "current_players": 2,
  "difficulty": "medium",
  "status": "waiting",
  "players": [
    {
      "player_id": "player_123",
      "name": "John",
      "color": "red",
      "is_ready": true,
      "score": 0
    },
    {
      "player_id": "player_456",
      "name": "Alice",
      "color": "green",
      "is_ready": false,
      "score": 0
    }
  ],
  "game_state": {
    "current_turn": "player_123",
    "dice_value": null,
    "board_state": {}
  },
  "created_at": "2026-05-14T10:30:00Z"
}
```

---

#### 5️⃣ Leave Room
```http
POST /api/rooms/{room_id}/leave
```

**Request Body:**
```json
{
  "player_id": "player_456"
}
```

**Response (200 OK):**
```json
{
  "message": "Player left room successfully",
  "room_id": "room_abc123",
  "remaining_players": 1
}
```

---

#### 6️⃣ Start Game
```http
POST /api/rooms/{room_id}/start
```

**Request Body:**
```json
{
  "creator_id": "player_123"
}
```

**Response (200 OK):**
```json
{
  "room_id": "room_abc123",
  "status": "in_progress",
  "game_id": "game_xyz789",
  "players": [
    {
      "player_id": "player_123",
      "name": "John",
      "color": "red",
      "tokens": [...]
    },
    {
      "player_id": "player_456",
      "name": "Alice",
      "color": "green",
      "tokens": [...]
    }
  ],
  "started_at": "2026-05-14T10:35:00Z"
}
```

**Errors:**
```json
{
  "detail": "Only room creator can start game",
  "status_code": 403
}
```

---

### 👤 Player & Statistics

#### 7️⃣ Get Player Stats
```http
GET /api/players/{player_id}/stats
```

**Response (200 OK):**
```json
{
  "player_id": "player_123",
  "player_name": "John",
  "total_games": 25,
  "total_wins": 12,
  "total_losses": 13,
  "win_percentage": 48.0,
  "current_rating": 1250,
  "rating_change": "+50",
  "average_game_duration": 1200,
  "tokens_killed": 45,
  "tokens_lost": 38,
  "total_dice_rolls": 230,
  "last_played": "2026-05-14T08:00:00Z",
  "account_created": "2026-01-15T10:00:00Z"
}
```

---

#### 8️⃣ Get Leaderboard
```http
GET /api/leaderboard?timeframe=all_time&limit=100&page=1
```

**Query Parameters:**
- `timeframe`: "all_time", "monthly", "weekly" (default: "all_time")
- `limit`: default: 100, max: 500
- `page`: default: 1

**Response (200 OK):**
```json
{
  "timeframe": "all_time",
  "total_players": 5432,
  "page": 1,
  "limit": 100,
  "leaderboard": [
    {
      "rank": 1,
      "player_id": "player_001",
      "player_name": "Pro Gamer",
      "rating": 2500,
      "wins": 450,
      "games": 500,
      "win_percentage": 90.0,
      "last_updated": "2026-05-14T10:00:00Z"
    },
    {
      "rank": 2,
      "player_id": "player_002",
      "player_name": "Strategy Master",
      "rating": 2480,
      "wins": 445,
      "games": 500,
      "win_percentage": 89.0,
      "last_updated": "2026-05-14T09:45:00Z"
    }
  ]
}
```

---

#### 9️⃣ Get Friend Rankings
```http
GET /api/players/{player_id}/friends/ranking
```

**Response (200 OK):**
```json
{
  "your_rank": 5,
  "your_rating": 1550,
  "friends": [
    {
      "rank": 1,
      "player_id": "friend_001",
      "name": "Alice",
      "rating": 1750,
      "wins": 50,
      "games": 65,
      "is_online": true
    },
    {
      "rank": 2,
      "player_id": "friend_002",
      "name": "Bob",
      "rating": 1650,
      "wins": 45,
      "games": 60,
      "is_online": false
    }
  ]
}
```

---

### 🎲 Game Management

#### 🔟 Get Game History
```http
GET /api/games/history/{player_id}?limit=20&offset=0
```

**Response (200 OK):**
```json
{
  "total_games": 128,
  "games": [
    {
      "game_id": "game_123",
      "opponent_names": ["Alice", "Bob"],
      "result": "won",
      "duration": 1200,
      "date": "2026-05-14T08:00:00Z",
      "rating_change": "+25"
    },
    {
      "game_id": "game_122",
      "opponent_names": ["Charlie"],
      "result": "lost",
      "duration": 900,
      "date": "2026-05-14T07:00:00Z",
      "rating_change": "-10"
    }
  ]
}
```

---

## 🔌 WebSocket Events

### Connection
```javascript
// Connect to WebSocket
ws = new WebSocket('ws://localhost:8000/ws/{player_id}/{room_id}')
```

---

### 📤 Client → Server Events

#### 1. Join Room (after connection)
```json
{
  "event": "join_room",
  "data": {
    "room_id": "room_abc123",
    "player_id": "player_123",
    "player_name": "John"
  }
}
```

---

#### 2. Ready (player ready to start)
```json
{
  "event": "ready",
  "data": {
    "room_id": "room_abc123",
    "player_id": "player_123",
    "is_ready": true
  }
}
```

---

#### 3. Roll Dice
```json
{
  "event": "roll_dice",
  "data": {
    "room_id": "room_abc123",
    "player_id": "player_123"
  }
}
```

---

#### 4. Move Token
```json
{
  "event": "move_token",
  "data": {
    "room_id": "room_abc123",
    "player_id": "player_123",
    "token_id": 0,
    "new_position": 5
  }
}
```

---

#### 5. Chat Message
```json
{
  "event": "chat",
  "data": {
    "room_id": "room_abc123",
    "player_id": "player_123",
    "message": "Good luck!",
    "emoji": "🎲"
  }
}
```

---

#### 6. Surrender/Leave Game
```json
{
  "event": "surrender",
  "data": {
    "room_id": "room_abc123",
    "player_id": "player_123"
  }
}
```

---

### 📥 Server → Client Events

#### 1. Game State Update
```json
{
  "event": "game_state",
  "data": {
    "current_turn": "player_123",
    "current_player_name": "John",
    "dice_value": 4,
    "game_status": "in_progress",
    "players": [
      {
        "player_id": "player_123",
        "name": "John",
        "color": "red",
        "tokens": [
          {"token_id": 0, "position": 12},
          {"token_id": 1, "position": -1},
          {"token_id": 2, "position": -1},
          {"token_id": 3, "position": -1}
        ],
        "score": 1
      }
    ]
  }
}
```

---

#### 2. Dice Roll Result
```json
{
  "event": "dice_rolled",
  "data": {
    "player_id": "player_123",
    "dice_value": 6,
    "extra_roll": true,
    "timestamp": "2026-05-14T10:35:15Z"
  }
}
```

---

#### 3. Token Moved
```json
{
  "event": "token_moved",
  "data": {
    "player_id": "player_123",
    "token_id": 0,
    "from_position": 12,
    "to_position": 16,
    "killed_opponent": false,
    "killed_opponent_token": null
  }
}
```

---

#### 4. Token Killed
```json
{
  "event": "token_killed",
  "data": {
    "attacker_id": "player_123",
    "attacker_name": "John",
    "attacker_color": "red",
    "victim_id": "player_456",
    "victim_name": "Alice",
    "victim_color": "green",
    "position": 16
  }
}
```

---

#### 5. Player Won
```json
{
  "event": "game_over",
  "data": {
    "winner_id": "player_123",
    "winner_name": "John",
    "winner_color": "red",
    "ranking": [
      {"position": 1, "player_id": "player_123", "player_name": "John"},
      {"position": 2, "player_id": "player_456", "player_name": "Alice"},
      {"position": 3, "player_id": "player_789", "player_name": "Bob"}
    ],
    "game_duration": 1200,
    "rating_changes": {
      "player_123": "+50",
      "player_456": "-20",
      "player_789": "-30"
    }
  }
}
```

---

#### 6. Chat Message Received
```json
{
  "event": "chat_message",
  "data": {
    "player_id": "player_456",
    "player_name": "Alice",
    "message": "Nice move!",
    "emoji": "👍",
    "timestamp": "2026-05-14T10:35:20Z"
  }
}
```

---

#### 7. Player Joined
```json
{
  "event": "player_joined",
  "data": {
    "player_id": "player_789",
    "player_name": "Bob",
    "player_color": "yellow",
    "current_players": 3
  }
}
```

---

#### 8. Player Left
```json
{
  "event": "player_left",
  "data": {
    "player_id": "player_789",
    "player_name": "Bob",
    "remaining_players": 2
  }
}
```

---

#### 9. Connection Error
```json
{
  "event": "error",
  "data": {
    "code": "INVALID_MOVE",
    "message": "Token cannot move to that position",
    "details": {
      "reason": "Position is occupied by your own token"
    }
  }
}
```

---

## 🔐 Error Responses

### 400 Bad Request
```json
{
  "detail": "Invalid request parameters",
  "status_code": 400,
  "error_code": "INVALID_REQUEST"
}
```

### 401 Unauthorized
```json
{
  "detail": "Authentication required",
  "status_code": 401,
  "error_code": "AUTH_REQUIRED"
}
```

### 403 Forbidden
```json
{
  "detail": "You do not have permission to perform this action",
  "status_code": 403,
  "error_code": "FORBIDDEN"
}
```

### 404 Not Found
```json
{
  "detail": "Room not found",
  "status_code": 404,
  "error_code": "NOT_FOUND"
}
```

### 409 Conflict
```json
{
  "detail": "Room is already full",
  "status_code": 409,
  "error_code": "ROOM_FULL"
}
```

### 500 Internal Server Error
```json
{
  "detail": "An unexpected error occurred",
  "status_code": 500,
  "error_code": "INTERNAL_ERROR"
}
```

---

## 📚 Testing with cURL

### Create a Room
```bash
curl -X POST http://localhost:8000/api/rooms/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Game",
    "creator_id": "player_123",
    "max_players": 4,
    "difficulty": "medium",
    "is_private": false
  }'
```

### Join Room
```bash
curl -X POST http://localhost:8000/api/rooms/room_abc123/join \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "player_456",
    "player_name": "Alice"
  }'
```

### Get Leaderboard
```bash
curl http://localhost:8000/api/leaderboard?timeframe=all_time&limit=10
```

### Get Player Stats
```bash
curl http://localhost:8000/api/players/player_123/stats
```

---

## 🔄 Rate Limiting
- REST API: 1000 requests per hour per IP
- WebSocket: Unlimited (server-side validation)

---

**Last Updated**: May 14, 2026
**API Version**: 1.0.0
**Status**: 🟢 Production Ready

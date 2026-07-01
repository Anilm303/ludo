# Ludo Game Engine - Server-side game logic
import random
from typing import List, Dict, Optional, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class PlayerColor(Enum):
    RED = "red"
    GREEN = "green"
    YELLOW = "yellow"
    BLUE = "blue"

class GameStatus(Enum):
    WAITING = "waiting"
    PLAYING = "playing"
    PAUSED = "paused"
    FINISHED = "finished"

@dataclass
class Token:
    id: int  # 0-3
    color: PlayerColor
    position: int = -1  # -1 = not opened, 0-51 = board, 52+ = home
    is_killed: bool = False
    is_in_home: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            # client expects playerColor as index
            "playerColor": list(PlayerColor).index(self.color),
            "position": self.position,
            "isKilled": self.is_killed,
            "isInHome": self.is_in_home,
        }

@dataclass
class Player:
    id: str
    name: str
    color: PlayerColor
    tokens: List[Token] = field(default_factory=list)
    is_current_turn: bool = False
    consecutive_sixes: int = 0
    tokens_reached_home: int = 0
    is_ai: bool = False

    def __post_init__(self):
        if not self.tokens:
            self.tokens = [Token(i, self.color) for i in range(4)]

    def has_won(self) -> bool:
        return self.tokens_reached_home == 4

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            # client expects color as index
            "color": list(PlayerColor).index(self.color),
                "tokens": [t.to_dict() for t in self.tokens],
                # client expects a 'type' field (0=human,1=ai)
                "type": 1 if self.is_ai else 0,
            "isCurrentTurn": self.is_current_turn,
            "consecutiveSixes": self.consecutive_sixes,
            "tokensReachedHome": self.tokens_reached_home,
            "isAI": self.is_ai,
        }

@dataclass
class GameState:
    id: str
    players: List[Player]
    status: GameStatus = GameStatus.WAITING
    current_player_index: int = 0
    dice_value: int = 0
    dice_rolled: bool = False
    can_move: bool = False
    winner: Optional[Player] = None
    rankings: List[str] = field(default_factory=list)  # list of player ids in finish order
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    move_history: List[dict] = field(default_factory=list)

    @property
    def current_player(self) -> Player:
        return self.players[self.current_player_index]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "players": [p.to_dict() for p in self.players],
            # status as index to match client GameStatus enum
            "status": list(GameStatus).index(self.status),
            "currentPlayerIndex": self.current_player_index,
            "diceValue": self.dice_value,
            "diceRolled": self.dice_rolled,
            "canMove": self.can_move,
            "winner": self.winner.to_dict() if self.winner else None,
            "rankings": self.rankings,
            "createdAt": self.created_at.isoformat(),
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "endedAt": self.ended_at.isoformat() if self.ended_at else None,
            # default to online mode for server-authoritative games
            "gameMode": 1,
        }

class BoardConfig:
    TOTAL_POSITIONS = 52
    HOME_POSITIONS = 6
    BOARD_SIZE = TOTAL_POSITIONS + HOME_POSITIONS
    
    PLAYER_START_POSITIONS = {
        PlayerColor.RED: 0,
        PlayerColor.GREEN: 13,
        PlayerColor.YELLOW: 26,
        PlayerColor.BLUE: 39,
    }
    
    SAFE_POSITIONS = [0, 8, 13, 21, 26, 34, 39, 47]
    
    HOME_ENTRY_POSITIONS = {
        PlayerColor.RED: 0,
        PlayerColor.GREEN: 13,
        PlayerColor.YELLOW: 26,
        PlayerColor.BLUE: 39,
    }

class GameEngine:
    """Server-side Ludo game logic"""

    @staticmethod
    def roll_dice() -> int:
        """Roll dice (1-6)"""
        return random.randint(1, 6)

    @staticmethod
    def can_token_be_moved(token: Token, dice_value: int) -> bool:
        """Check if token can be moved"""
        if token.is_killed:
            return False
        
        # Token must be opened first
        if token.position == -1:
            return dice_value == 6

        # Token in home path: allow moves that do not overshoot final cell
        if token.is_in_home:
            final_index = BoardConfig.TOTAL_POSITIONS + BoardConfig.HOME_POSITIONS - 1
            remaining_steps = final_index - token.position
            return remaining_steps > 0 and dice_value <= remaining_steps

        return True

    @staticmethod
    def calculate_new_position(token: Token, dice_value: int, player_color: PlayerColor) -> int:
        """Calculate new position after dice roll"""
        # Token opening
        if token.position == -1:
            if dice_value == 6:
                return BoardConfig.PLAYER_START_POSITIONS[player_color]
            return -1
        
        # Token in home path
        if token.is_in_home:
            final_index = BoardConfig.TOTAL_POSITIONS + BoardConfig.HOME_POSITIONS - 1
            new_pos = token.position + dice_value
            # cannot overshoot final cell
            if new_pos > final_index:
                return token.position
            return new_pos
        
        # Token in main board
        # Use relative steps from player's start to determine entering home path correctly
        start_pos = BoardConfig.PLAYER_START_POSITIONS[player_color]
        steps_from_start = (token.position - start_pos + BoardConfig.TOTAL_POSITIONS) % BoardConfig.TOTAL_POSITIONS
        total_steps = steps_from_start + dice_value

        # If total steps go beyond last board cell, move into home path
        if total_steps > BoardConfig.TOTAL_POSITIONS - 1:
            steps_into_home = total_steps - (BoardConfig.TOTAL_POSITIONS - 1)
            if steps_into_home <= BoardConfig.HOME_POSITIONS:
                return BoardConfig.TOTAL_POSITIONS + steps_into_home - 1
            # overshoot home -> invalid move (stay)
            return token.position

        # Normal move on main board
        return (token.position + dice_value) % BoardConfig.TOTAL_POSITIONS

    @staticmethod
    def is_safe_position(position: int, player_color: PlayerColor) -> bool:
        """Check if position is safe (cannot be killed)"""
        if position == -1 or position >= BoardConfig.BOARD_SIZE:
            return True  # Home is safe
        return position in BoardConfig.SAFE_POSITIONS

    @staticmethod
    def get_movable_tokens(player: Player, dice_value: int) -> List[Token]:
        """Get all movable tokens for current player"""
        return [
            token for token in player.tokens
            if GameEngine.can_token_be_moved(token, dice_value)
        ]

    @staticmethod
    def get_tokens_at_position(
        players: List[Player],
        position: int,
        exclude_color: PlayerColor,
    ) -> List[Token]:
        """Get opponent tokens at position to kill"""
        tokens = []
        for player in players:
            if player.color == exclude_color:
                continue
            for token in player.tokens:
                if token.position == position and not token.is_killed:
                    tokens.append(token)
        return tokens

    @staticmethod
    def kill_tokens_at_position(
        players: List[Player],
        position: int,
        exclude_color: PlayerColor,
    ) -> None:
        """Kill opponent tokens at position"""
        # Group tokens by owner color at the position to detect blocks
        color_groups = {}
        for player in players:
            if player.color == exclude_color:
                continue
            for token in player.tokens:
                if token.position == position and not token.is_killed:
                    color_groups.setdefault(player.color, []).append(token)

        killed_info = []
        # If a color has 2 or more tokens at this position, it's a block and cannot be killed
        for color, tokens in color_groups.items():
            if len(tokens) >= 2:
                # protected block, skip
                continue
            # kill solo tokens
            for t in tokens:
                killed_info.append({
                    "ownerColor": color.value,
                    "tokenId": t.id,
                    "oldPosition": t.position,
                })
                t.is_killed = True
                t.position = -1

        return killed_info

    @staticmethod
    def execute_move(
        game_state: GameState,
        token: Token,
        dice_value: int,
    ) -> bool:
        """Execute a move and return True if successful"""
        player = game_state.current_player
        
        if not GameEngine.can_token_be_moved(token, dice_value):
            return False
        
        old_position = token.position
        new_position = GameEngine.calculate_new_position(
            token, dice_value, player.color
        )
        
        token.position = new_position
        # Check if entered home
        final_index = BoardConfig.TOTAL_POSITIONS + BoardConfig.HOME_POSITIONS - 1
        if new_position >= BoardConfig.TOTAL_POSITIONS:
            token.is_in_home = True
            # if landed exactly on final home cell, mark as reached home
            if new_position == final_index:
                player.tokens_reached_home += 1
        
        # Check for kills
        killed = []
        if not token.is_in_home and not GameEngine.is_safe_position(new_position, player.color):
            killed = GameEngine.kill_tokens_at_position(
                game_state.players,
                new_position,
                player.color,
            )

        # Record move in history for possible undo
        move_record = {
            "playerId": player.id,
            "tokenId": token.id,
            "oldPosition": old_position,
            "newPosition": new_position,
            "diceValue": dice_value,
            "killed": killed,
        }
        game_state.move_history.append(move_record)
        
        return True

    @staticmethod
    def undo_last_move(game_state: GameState) -> bool:
        """Undo the last move if possible. Returns True if undone."""
        if not game_state.move_history:
            return False

        last = game_state.move_history.pop()
        # find player and token
        pid = last.get("playerId")
        token_id = last.get("tokenId")
        player = None
        for p in game_state.players:
            if p.id == pid:
                player = p
                break
        if not player:
            return False

        # revert token position
        for t in player.tokens:
            if t.id == token_id:
                t.position = last.get("oldPosition")
                # adjust home counters if needed
                final_index = BoardConfig.TOTAL_POSITIONS + BoardConfig.HOME_POSITIONS - 1
                if last.get("newPosition") >= BoardConfig.TOTAL_POSITIONS and last.get("oldPosition") < BoardConfig.TOTAL_POSITIONS:
                    # token had entered home; revert tokens_reached_home if it had reached final
                    if last.get("newPosition") == final_index:
                        player.tokens_reached_home = max(0, player.tokens_reached_home - 1)
                # reset in_home flag
                t.is_in_home = (t.position >= BoardConfig.TOTAL_POSITIONS)
                break

        # revive killed tokens
        for k in last.get("killed", []) or []:
            owner_color = PlayerColor(k.get("ownerColor"))
            token_id_k = k.get("tokenId")
            old_pos = k.get("oldPosition")
            # find owner player
            for p in game_state.players:
                if p.color == owner_color:
                    for tk in p.tokens:
                        if tk.id == token_id_k:
                            tk.is_killed = False
                            tk.position = old_pos
                            break
                    break

        return True

    @staticmethod
    def check_win(player: Player) -> bool:
        """Check if player has won"""
        return player.tokens_reached_home == 4

    @staticmethod
    def is_valid_move(
        token: Token,
        dice_value: int,
        expected_new_position: int,
    ) -> bool:
        """Validate if a move is legal"""
        if token.is_killed:
            return False
        
        if not GameEngine.can_token_be_moved(token, dice_value):
            return False
        
        calculated_pos = GameEngine.calculate_new_position(
            token, dice_value, token.color
        )
        
        return calculated_pos == expected_new_position

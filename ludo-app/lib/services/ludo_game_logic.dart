// Ludo Game Logic Engine
import 'dart:math';
import 'dart:ui' show Offset;
import 'package:uuid/uuid.dart';
import '../models/ludo_models.dart';

class LudoGameLogic {
  static final Random _random = Random();

  /// Roll dice (1-6)
  static int rollDice() => _random.nextInt(6) + 1;

  /// Convenience getters from BoardConfig
  static int get mainBoardSize => BoardConfig.totalPositions; // 52
  static int get homePathSize => BoardConfig.homePositions; // 6

  static bool canOpenTokenOnDice(int diceValue, LudoRuleSettings rules) {
    if (rules.startCoinsInBase) {
      return diceValue == 6; // Only 6 opens if Start at 6 is selected
    } else {
      return diceValue == 1; // Only 1 opens if Start at 1 is selected
    }
  }

  static int getPlayerStartPosition(PlayerColor color) {
    return BoardConfig.playerStartPositions[color] ?? 0;
  }

  static bool isSafePosition(int position, PlayerColor playerColor, {
    LudoRuleSettings rules = const LudoRuleSettings(),
  }) {
    if (position < 0) return true; // off-board/start is safe
    if (position >= mainBoardSize)
      return true; // any home-path position is safe
    // When showSafeCells is OFF, star positions are NOT safe (coins can be killed)
    if (!rules.showSafeCells) return false;
    return BoardConfig.safePositions.contains(position);
  }

  static int getHomeEntryPosition(PlayerColor color) {
    return BoardConfig.homeEntryPositions[color] ?? 0;
  }

  static Map<int, Offset> getBoardPositionCoordinates() {
    final Map<int, Offset> coords = {};
    const double centerX = 300;
    const double centerY = 300;
    const double radius = 250;

    for (int i = 0; i < mainBoardSize; i++) {
      final angle = (i * 360 / mainBoardSize - 90) * (pi / 180);
      coords[i] = Offset(
        centerX + radius * cos(angle),
        centerY + radius * sin(angle),
      );
    }

    return coords;
  }

  /// Check if token can be moved by given dice
  static bool canTokenBeMoved(
    Token token,
    int diceValue, {
    LudoRuleSettings rules = const LudoRuleSettings(),
  }) {
    // If token was killed (sent back to home), allow it to be moved out
    // when the player rolls an opening value so it can spawn back onto the board.
    if (token.isKilled) return canOpenTokenOnDice(diceValue, rules);

    // token not opened
    if (token.position == -1) {
      return canOpenTokenOnDice(diceValue, rules);
    }

    // token in home path: allow move only if it doesn't overshoot final cell
    if (token.isInHome) {
      final finalIndex = mainBoardSize + homePathSize - 1;
      final remainingSteps = finalIndex - token.position;
      return diceValue <= remainingSteps && remainingSteps > 0;
    }

    // on main board always allowed (subject to other game rules)
    return true;
  }

  /// Calculate new absolute position for a token, or return current position if move not allowed.
  static int calculateNewPosition(
    Token token,
    int diceValue,
    PlayerColor playerColor, {
    LudoRuleSettings rules = const LudoRuleSettings(),
    bool hasCaptured = true,
  }) {
    // opening token
    if (token.position == -1) {
      if (canOpenTokenOnDice(diceValue, rules)) {
        return getPlayerStartPosition(playerColor);
      }
      return -1;
    }

    // token already in home path
    if (token.isInHome) {
      final finalIndex = mainBoardSize + homePathSize - 1;
      final newPos = token.position + diceValue;
      if (newPos > finalIndex) return token.position; // cannot overshoot
      return newPos;
    }

    // token on main board
    final int startPos = getPlayerStartPosition(playerColor);
    final int stepsFromStart =
        (token.position - startPos + mainBoardSize) % mainBoardSize;
    final int totalSteps = stepsFromStart + diceValue;

    if (totalSteps > mainBoardSize - 2) {
      // RULE: Must capture to enter home lane
      // Check the rule from settings
      if (rules.mustCaptureToEnterHome && !hasCaptured) {
        // Player hasn't captured any coin yet, keep circling the board
        return (token.position + diceValue) % mainBoardSize;
      }

      final int stepsIntoHome = totalSteps - (mainBoardSize - 2);
      if (stepsIntoHome <= homePathSize) {
        return mainBoardSize +
            stepsIntoHome -
            1; // first home cell = mainBoardSize
      }
      return token.position; // overshoots home
    }

    return (token.position + diceValue) % mainBoardSize;
  }

  static bool canCaptureOnPosition(
    List<Player> players,
    int position,
    PlayerColor excludeColor, {
    LudoRuleSettings rules = const LudoRuleSettings(),
  }) {
    final tokens = getTokensAtPosition(players, position, excludeColor);
    if (tokens.isEmpty) return false;

    if (!rules.barrierEnabled) return true;

    final grouped = <PlayerColor, int>{};
    for (final player in players) {
      if (player.color == excludeColor) continue;
      final matching = player.tokens.where((token) {
        return !token.isKilled && token.position == position;
      }).length;
      if (matching > 0) {
        grouped[player.color] = matching;
      }
    }

    for (final count in grouped.values) {
      if (count >= 2) return false;
    }

    return true;
  }

  static bool canTokenCapture(
    Token token,
    int diceValue,
    List<Player> players, {
    LudoRuleSettings rules = const LudoRuleSettings(),
    bool hasCaptured = true,
  }) {
    final newPos = calculateNewPosition(
      token,
      diceValue,
      token.playerColor,
      rules: rules,
      hasCaptured: hasCaptured,
    );
    if (newPos < 0 || newPos >= mainBoardSize) return false;
    if (isSafePosition(newPos, token.playerColor, rules: rules)) return false;
    return canCaptureOnPosition(
      players,
      newPos,
      token.playerColor,
      rules: rules,
    );
  }

  static List<Token> getMovableTokens(
    Player player,
    int diceValue, {
    List<Player>? allPlayers,
    LudoRuleSettings rules = const LudoRuleSettings(),
  }) {
    final candidates = player.tokens
        .where((t) => canTokenBeMoved(t, diceValue, rules: rules))
        .toList();

    // RULE: Must bring a coin out on 1 or 6 based on rules
    if (LudoGameLogic.canOpenTokenOnDice(diceValue, rules)) {
      final baseTokens = candidates.where((t) => t.position == -1).toList();
      if (baseTokens.isNotEmpty) {
        return baseTokens; // Forced to move tokens out of base
      }
    }

    return candidates;
  }

  static List<Token> getTokensAtPosition(
    List<Player> players,
    int position,
    PlayerColor excludeColor,
  ) {
    final tokens = <Token>[];
    for (final player in players) {
      if (player.color == excludeColor) continue;
      for (final token in player.tokens) {
        if (!token.isKilled && token.position == position) tokens.add(token);
      }
    }
    return tokens;
  }

  static void killTokensAtPosition(
    List<Player> players,
    int position,
    PlayerColor excludeColor,
  ) {
    // Group tokens by player color to detect blocks
    final Map<PlayerColor, List<Token>> groups = {};
    for (final player in players) {
      if (player.color == excludeColor) continue;
      for (final token in player.tokens) {
        if (!token.isKilled && token.position == position) {
          groups.putIfAbsent(player.color, () => []).add(token);
        }
      }
    }

    // If a color has 2 or more tokens here, it's a block and is protected
    for (final entry in groups.entries) {
      if (entry.value.length >= 2) continue; // protected block
      for (final t in entry.value) {
        t.isKilled = true;
        t.position = -1;
        t.isInHome = false;
      }
    }
  }

  static MoveOutcome executeMove(
    GameState gameState,
    Token token,
    int diceValue,
  ) {
    final player = gameState.currentPlayer;
    final rules = gameState.rules;
    final oldPos = token.position;
    final newPos = calculateNewPosition(
      token,
      diceValue,
      player.color,
      rules: rules,
      hasCaptured: player.hasCaptured,
    );
    final outcome = MoveOutcome(
      moved: newPos != token.position,
      openedToken: oldPos < 0 && newPos >= 0,
    );

    // no-op if cannot move
    if (newPos == token.position) return outcome;

    token.position = newPos;
    token.isKilled = false; // revived by moving
    token.isInHome = newPos >= mainBoardSize;

    // check if token reached final home cell
    final finalIndex = mainBoardSize + homePathSize - 1;
    if (token.isInHome && token.position == finalIndex) {
      // increment finished counter for player
      player.tokensReachedHome++;
      outcome.reachedHome = true;
    }

    // handle kills: only on main board and only if landed on non-safe cell
    if (!token.isInHome && !isSafePosition(newPos, player.color, rules: rules)) {
      final victims = getTokensAtPosition(
        gameState.players,
        newPos,
        player.color,
      );
      
      // Auto-kill disabled. In Ludo, if you land on an opponent, you capture it.
      // If the user wants a choice, it would require a separate UI dialog.
      // For now, I will keep the kill logic but mark it clearly.
      if (victims.isNotEmpty &&
          canCaptureOnPosition(
            gameState.players,
            newPos,
            player.color,
            rules: rules,
          )) {
        killTokensAtPosition(gameState.players, newPos, player.color);
        outcome.captured = true;
        player.hasCaptured = true;
      }
    }

    return outcome;
  }

  static bool checkWin(Player player) => player.hasWon;

  static bool isBonusDice(int diceValue, LudoRuleSettings rules) =>
      diceValue == (rules.startCoinsInBase ? 6 : 1);

  static bool isPenaltyDice(int diceValue, LudoRuleSettings rules) =>
      diceValue == (rules.startCoinsInBase ? 1 : 6);

  static bool isMoveLegal(
    Token token,
    int diceValue,
    int fromPosition,
    int toPosition,
    bool hasCaptured,
  ) {
    if (!canTokenBeMoved(token, diceValue)) return false;
    final newPos = calculateNewPosition(token, diceValue, token.playerColor, hasCaptured: hasCaptured);
    return newPos == toPosition;
  }

  static int getRelativeProgress(Token token) {
    if (token.position == -1) return -1;
    if (token.position >= mainBoardSize)
      return mainBoardSize + (token.position - mainBoardSize);
    return token.position;
  }

  static int getProjectedProgress(Token token, int diceValue) {
    if (token.position == -1 && diceValue != 6) return -1;
    final projected = calculateNewPosition(token, diceValue, token.playerColor);
    if (token.position == -1 && diceValue == 6)
      return getPlayerStartPosition(token.playerColor);
    return projected;
  }

  static int getNextPosition(Token token, int diceValue) =>
      calculateNewPosition(token, diceValue, token.playerColor);

  /// Returns the list of absolute positions a token visits during a move.
  static List<int> calculateMovePath(
    Token token,
    int steps,
    PlayerColor color, {
    LudoRuleSettings rules = const LudoRuleSettings(),
    bool hasCaptured = true,
  }) {
    if (steps <= 0) return [];
    
    // If opening from base, path is just the start position
    if (token.position == -1) {
      if (canOpenTokenOnDice(steps, rules)) {
        return [getPlayerStartPosition(color)];
      }
      return [];
    }

    final List<int> path = [];
    int currentPos = token.position;
    bool currentInHome = token.isInHome;

    for (int i = 1; i <= steps; i++) {
      // Logic simplified: move one step at a time
      // This matches how calculateNewPosition works but step-by-step
      
      if (currentInHome) {
        final finalIndex = mainBoardSize + homePathSize - 1;
        if (currentPos < finalIndex) {
          currentPos++;
        } else {
          // overshot/reached end, stop path
          break;
        }
      } else {
        final int startPos = getPlayerStartPosition(color);
        final int stepsFromStart = (currentPos - startPos + mainBoardSize) % mainBoardSize;
        
        if (stepsFromStart == mainBoardSize - 2) {
          // At the entrance to home lane
          // Check the rule from settings
          if (rules.mustCaptureToEnterHome && !hasCaptured) {
            // Keep circling
            currentPos = (currentPos + 1) % mainBoardSize;
          } else {
            // Enter home path
            currentPos = mainBoardSize; // first home cell
            currentInHome = true;
          }
        } else {
          currentPos = (currentPos + 1) % mainBoardSize;
        }
      }
      path.add(currentPos);
    }
    
    return path;
  }

  static bool willEnterWinningPath(Token token, int diceValue) {
    final newPos = calculateNewPosition(token, diceValue, token.playerColor);
    return newPos >= mainBoardSize;
  }

  static List<int> get safePositions => BoardConfig.safePositions;
}

/// Game controller for managing game state
class GameController {
  late GameState gameState;
  Function? onGameStateChanged;
  Function? onTurnChanged;
  Function? onGameEnded;
  Function? onTokenMoved;

  void initializeGame({
    required List<Player> players,
    required GameMode gameMode,
    LudoRuleSettings rules = const LudoRuleSettings(),
  }) {
    // Sort players in the specific order: Yellow -> Green -> Red -> Blue (Clockwise)
    final order = [PlayerColor.yellow, PlayerColor.green, PlayerColor.red, PlayerColor.blue];
    final List<Player> sortedPlayers = [];
    
    for (final color in order) {
      final p = players.where((p) => p.color == color).toList();
      if (p.isNotEmpty) sortedPlayers.add(p.first);
    }
    
    // Add any remaining players not in the order list (fallback)
    for (final p in players) {
      if (!sortedPlayers.contains(p)) sortedPlayers.add(p);
    }

    gameState = GameState(
      id: const Uuid().v4(),
      players: sortedPlayers,
      createdAt: DateTime.now(),
      gameMode: gameMode,
      rules: rules,
      currentPlayerIndex: 0,
    );
  }

  void startGame() {
    gameState.status = GameStatus.playing;
    gameState.startedAt = DateTime.now();
    for (final player in gameState.players) {
      player.isCurrentTurn = false;
    }
    if (gameState.players.isNotEmpty) {
      gameState.players[gameState.currentPlayerIndex].isCurrentTurn = true;
      onTurnChanged?.call(gameState.currentPlayer);
    }
    onGameStateChanged?.call();
  }

  int rollDice() {
    if (!gameState.isPlaying) return 0;
    // Prevent rolling multiple times before resolving current roll
    if (gameState.diceRolled) return gameState.diceValue;

    gameState.diceValue = LudoGameLogic.rollDice();
    gameState.diceRolled = true;

    // Enable move if there are movable tokens
    final movableTokens = LudoGameLogic.getMovableTokens(
      gameState.currentPlayer,
      gameState.diceValue,
      allPlayers: gameState.players,
      rules: gameState.rules,
    );

    gameState.canMove = movableTokens.isNotEmpty;

    // If no movable tokens but dice is 6, allow extra roll later (UI/AI handles)
    onGameStateChanged?.call();
    return gameState.diceValue;
  }

  bool moveToken(Token token, int diceValue) {
    if (!gameState.isPlaying || !gameState.diceRolled) {
      return false;
    }

    if (!LudoGameLogic.canTokenBeMoved(
      token,
      diceValue,
      rules: gameState.rules,
    )) {
      return false;
    }

    // Execute move
    final outcome = LudoGameLogic.executeMove(gameState, token, diceValue);

    onTokenMoved?.call(token);

    final rules = gameState.rules;

    if (LudoGameLogic.isPenaltyDice(diceValue, rules)) {
      gameState.currentPlayer.consecutiveOnes++;
    } else {
      gameState.currentPlayer.consecutiveOnes = 0;
    }

    // Check for win
    if (LudoGameLogic.checkWin(gameState.currentPlayer)) {
      gameState.winner = gameState.currentPlayer;
      gameState.status = GameStatus.finished;
      gameState.endedAt = DateTime.now();
      onGameEnded?.call(gameState.winner);
      return true;
    }

    bool keepTurn = false;

    if (outcome.captured && rules.extraTurnOnCapture) {
      keepTurn = true;
    }

    if (outcome.reachedHome && rules.extraTurnOnHome) {
      keepTurn = true;
    }

    bool forceEndTurn = false;

    if (diceValue == 6 && rules.extraTurnOnSix) {
      keepTurn = true;
    }
    if (diceValue == 1 && rules.extraTurnOnOne) {
      keepTurn = true;
    }

    if (LudoGameLogic.canOpenTokenOnDice(diceValue, rules)) {
      gameState.currentPlayer.consecutiveSixes++;

      if (gameState.currentPlayer.consecutiveSixes >= 3) {
        if (rules.threeConsecutiveSixesBringCoinOut) {
          _bringCoinOutForPlayer(gameState.currentPlayer, diceValue);
        }
        gameState.currentPlayer.consecutiveSixes = 0;
        forceEndTurn = true;
        keepTurn = false;
      }
    } else {
      gameState.currentPlayer.consecutiveSixes = 0;
    }

    if (LudoGameLogic.isPenaltyDice(diceValue, rules) && gameState.currentPlayer.consecutiveOnes >= 3) {
      if (rules.threeConsecutiveOnesCutOwnCoin) {
        _cutOwnCoin(gameState.currentPlayer);
      }
      if (rules.skipTurnAfterThreeOnes) {
        gameState.currentPlayer.skipTurns += 1;
      }
      gameState.currentPlayer.consecutiveOnes = 0;
      forceEndTurn = true;
    }

    if (forceEndTurn) {
      keepTurn = false;
      endTurn();
    } else if (!keepTurn) {
      endTurn();
    }

    gameState.diceRolled = false;
    gameState.canMove = false;
    onGameStateChanged?.call();

    return true;
  }

  void endTurn() {
    gameState.currentPlayer.consecutiveSixes = 0;

    final n = gameState.players.length;
    if (n == 0) return;

    final start = gameState.currentPlayerIndex;
    bool found = false;

    for (int i = 1; i <= n; i++) {
      final nextIndex = (start + i) % n;
      final candidate = gameState.players[nextIndex];

      // skip players who already finished
      if (candidate.hasWon) continue;

      if (candidate.skipTurns > 0) {
        candidate.skipTurns -= 1;
        continue;
      }

      // found next player
      gameState.currentPlayerIndex = nextIndex;
      found = true;
      break;
    }

    if (!found) {
      // no eligible players left -> finish game
      gameState.status = GameStatus.finished;
      gameState.endedAt = DateTime.now();
      for (final player in gameState.players) {
        player.isCurrentTurn = false;
      }
      onGameEnded?.call(gameState.winner);
      onGameStateChanged?.call();
      return;
    }

    for (final player in gameState.players) {
      player.isCurrentTurn = false;
    }
    gameState.players[gameState.currentPlayerIndex].isCurrentTurn = true;
    gameState.diceValue = 0;
    gameState.diceRolled = false;
    gameState.canMove = false;

    onTurnChanged?.call(gameState.currentPlayer);
    onGameStateChanged?.call();
  }

  void pauseGame() {
    gameState.status = GameStatus.paused;
    onGameStateChanged?.call();
  }

  void resumeGame() {
    gameState.status = GameStatus.playing;
    onGameStateChanged?.call();
  }

  void resetGame() {
    gameState.status = GameStatus.waiting;
    gameState.diceValue = 0;
    gameState.diceRolled = false;
    gameState.canMove = false;
    gameState.winner = null;
    gameState.currentPlayerIndex = 0;

    for (final player in gameState.players) {
      player.isCurrentTurn = false;
      player.consecutiveSixes = 0;
      player.consecutiveOnes = 0;
      player.skipTurns = 0;
      player.tokensReachedHome = 0;

      for (final token in player.tokens) {
        token.position = -1;
        token.isKilled = false;
        token.isInHome = false;
      }
    }

    onGameStateChanged?.call();
  }

  /// Removes a player from the active game.
  /// If the current turn was theirs, moves to next player.
  void removePlayer(String playerId) {
    final players = gameState.players;
    final int indexToRemove = players.indexWhere((p) => p.id == playerId);
    
    if (indexToRemove == -1 || players.length <= 2) return;

    final bool isRemovingCurrentPlayer = gameState.currentPlayerIndex == indexToRemove;
    
    // Clear tokens of removed player
    for (final token in players[indexToRemove].tokens) {
      token.position = -1;
      token.isInHome = false;
    }
    
    players.removeAt(indexToRemove);
    
    // Adjust currentPlayerIndex
    if (isRemovingCurrentPlayer) {
      if (gameState.currentPlayerIndex >= players.length) {
        gameState.currentPlayerIndex = 0;
      }
      // Start next turn
      gameState.diceRolled = false;
      gameState.canMove = false;
      gameState.diceValue = 0;
      players[gameState.currentPlayerIndex].isCurrentTurn = true;
      onTurnChanged?.call(players[gameState.currentPlayerIndex]);
    } else if (indexToRemove < gameState.currentPlayerIndex) {
      gameState.currentPlayerIndex--;
    }

    onGameStateChanged?.call();
  }

  void _bringCoinOutForPlayer(Player player, int diceValue) {
    final token = player.tokens.firstWhere(
      (t) => t.position < 0,
      orElse: () => player.tokens.first,
    );
    if (token.position < 0) {
      token.position = LudoGameLogic.getPlayerStartPosition(player.color);
      token.isKilled = false;
      token.isInHome = false;
    }
  }

  void _cutOwnCoin(Player player) {
    final token =
        player.tokens
            .where(
              (t) =>
                  t.position >= 0 && t.position < LudoGameLogic.mainBoardSize,
            )
            .toList()
          ..sort((a, b) => b.position.compareTo(a.position));

    if (token.isNotEmpty) {
      token.first.position = -1;
      token.first.isKilled = false;
      token.first.isInHome = false;
    }
  }
}

class MoveOutcome {
  bool moved;
  bool openedToken;
  bool captured;
  bool reachedHome;

  MoveOutcome({
    this.moved = false,
    this.openedToken = false,
    this.captured = false,
    this.reachedHome = false,
  });
}

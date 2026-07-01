// Game State Provider
import 'package:flutter/material.dart';
import '../models/ludo_models.dart';
import '../services/ludo_game_logic.dart';
import '../services/ai_player.dart';
import '../services/ludo_socket_service.dart';

class GameProvider extends ChangeNotifier {
  GameController? _gameController;
  AIPlayer? _aiPlayer;
  LudoSocketService? _socketService;
  dynamic matchedRoom;
  String? _currentUserId;
  String? _currentUsername;
  bool isSearchingMatch = false;

  /// Pending undo request payload from server (if any)
  dynamic pendingUndoRequest;
  Map<String, dynamic>? lastMoveEvent;
  bool awaitingServer = false;
  bool _autoPlayScheduled = false;
  bool _isAutoPlaying = false;

  GameState? get gameState => _gameController?.gameState;
  bool get isGamePlaying => gameState?.isPlaying ?? false;
  bool get hasGameEnded => gameState?.hasGameEnded ?? false;
  Player? get currentPlayer => gameState?.currentPlayer;
  Player? get winner => gameState?.winner;
  int get diceValue => gameState?.diceValue ?? 0;
  bool get diceRolled => gameState?.diceRolled ?? false;
  bool get canMove => gameState?.canMove ?? false;
  DateTime? _lastRollRequestAt;

  /// Saved game state for resume feature
  GameState? _savedOfflineState;

  bool get hasSavedOfflineGame => _savedOfflineState != null;

  void saveCurrentOfflineGame() {
    if (_gameController != null && gameState != null && gameState!.gameMode == GameMode.offline) {
      _savedOfflineState = gameState!.copy();
    }
  }

  void resumeOfflineGame({LudoRuleSettings? newRules}) {
    if (_savedOfflineState != null) {
      if (newRules != null) {
        _savedOfflineState!.rules = newRules;
      }
      _gameController = GameController();
      _gameController!.gameState = _savedOfflineState!;
      _savedOfflineState = null;
      
      _gameController!.onGameStateChanged = () {
        notifyListeners();
        try {
          _scheduleAutoPlayIfNeeded(_gameController?.gameState.currentPlayer);
        } catch (e) {}
      };
      _gameController!.onTurnChanged = (player) {
        notifyListeners();
        try {
          final p = player as Player? ?? _gameController!.gameState.currentPlayer;
          _scheduleAutoPlayIfNeeded(p);
        } catch (e) {}
      };
      _gameController!.onTokenMoved = (_) => notifyListeners();
      _gameController!.onGameEnded = (_) => notifyListeners();
      
      notifyListeners();
      // Ensure AI continues if it was its turn
      _scheduleAutoPlayIfNeeded(gameState!.currentPlayer);
    }
  }

  /// Initialize offline game
  void initializeOfflineGame({
    required List<Player> players,
    required GameMode gameMode,
    LudoRuleSettings rules = const LudoRuleSettings(),
  }) {
    _gameController = GameController();
    _gameController!.initializeGame(
      players: players,
      gameMode: gameMode,
      rules: rules,
    );
    _gameController!.onGameStateChanged = () {
      notifyListeners();
      try {
        _scheduleAutoPlayIfNeeded(_gameController?.gameState.currentPlayer);
      } catch (e) {
        // ignore
      }
    };
    _gameController!.onTurnChanged = (player) {
      notifyListeners();
      try {
        final p = player as Player? ?? _gameController!.gameState.currentPlayer;
        _scheduleAutoPlayIfNeeded(p);
      } catch (e) {
        // ignore
      }
    };
    _gameController!.onTokenMoved = (_) => notifyListeners();
    _gameController!.onGameEnded = (_) => notifyListeners();

    // Initialize AI if needed
    if (players.any((p) => p.type == PlayerType.ai)) {
      _aiPlayer = AIPlayer(
        difficulty:
            players.firstWhere((p) => p.type == PlayerType.ai).difficulty ??
                DifficultyLevel.medium,
      );
    }

    notifyListeners();
  }

  /// Initialize online game
  void initializeOnlineGame({
    required List<Player> players,
    required String serverUrl,
    required String userId,
    LudoRuleSettings rules = const LudoRuleSettings(),
  }) {
    _gameController = GameController();
    _gameController!.initializeGame(
      players: players,
      gameMode: GameMode.online,
      rules: rules,
    );
    _gameController!.onGameStateChanged = () => notifyListeners();
    _gameController!.onTurnChanged = (_) => notifyListeners();
    _gameController!.onTokenMoved = (_) => notifyListeners();
    _gameController!.onGameEnded = (_) => notifyListeners();

    // Initialize socket service
    _socketService = LudoSocketService();
    _socketService!.onDiceRollReceived = _handleRemoteDiceRoll;
    _socketService!.onTokenMoveReceived = _handleRemoteTokenMove;
    _socketService!.onTurnChanged = _handleRemoteTurnChange;
    _socketService!.onStateSync = _handleRemoteStateSync;
    // Undo/dispute callbacks
    _socketService!.onUndoRequested = _handleUndoRequested;
    _socketService!.onUndoVoteRecorded = _handleUndoVoteRecorded;
    _socketService!.onUndoAccepted = _handleUndoAccepted;
    _socketService!.onUndoRejected = _handleUndoRejected;
    // Matchmaking
    _socketService!.onMatchFound = _handleMatchFound;
    _socketService!.onMatchFailed = (data) {
      // stop searching and notify UI
      isSearchingMatch = false;
      notifyListeners();
    };

    notifyListeners();
  }

  /// Start game
  void startGame() {
    _gameController?.startGame();
    notifyListeners();
    try {
      _scheduleAutoPlayIfNeeded(_gameController?.gameState.currentPlayer);
    } catch (e) {
      // ignore
    }
  }

  /// Roll dice
  int rollDice() {
    // If connected, ask server to roll (authoritative)
    if (_socketService != null &&
        _socketService!.isConnectedToServer() &&
        gameState != null) {
      // basic client-side rate limit to avoid accidental spam
      final now = DateTime.now();
      if (_lastRollRequestAt != null &&
          now.difference(_lastRollRequestAt!).inMilliseconds < 700) {
        // ignore rapid repeat
        return 0;
      }
      _lastRollRequestAt = now;
      awaitingServer = true;
      try {
        final dynamic playerId = _currentUserId ?? gameState!.currentPlayer.id;
        // prefer matchedRoom id when available
        String? roomId;
        if (matchedRoom != null)
          roomId = matchedRoom['roomId'] ?? matchedRoom['room']?['roomId'];
        roomId ??= gameState!.id;
        if (roomId != null) {
          _socketService!.sendDiceRollRequest(roomId, playerId);
        }
      } catch (e) {
        // ignore
      }
      notifyListeners();
      return 0;
    }

    final diceValue = _gameController?.rollDice() ?? 0;

    if (diceValue > 0) {
      // Capture dice roll for UI animation (even in local mode)
      lastMoveEvent = {
        'diceRoll': {
          'playerId': gameState!.currentPlayer.id,
          'diceValue': diceValue,
        },
      };
      
      // Auto-clear after animation duration
      Future.delayed(const Duration(milliseconds: 1400), () {
        if (lastMoveEvent != null && lastMoveEvent!['diceRoll'] != null) {
          lastMoveEvent = null;
          notifyListeners();
        }
      });
    }

    if (_socketService == null &&
        _gameController != null &&
        gameState != null &&
        diceValue > 0) {
      final movableTokens = LudoGameLogic.getMovableTokens(
        gameState!.currentPlayer,
        diceValue,
        allPlayers: gameState!.players,
        rules: gameState!.rules,
      );

      if (movableTokens.isEmpty) {
        if (gameState!.currentPlayer.type == PlayerType.human) {
          Future.delayed(const Duration(milliseconds: 1000), () {
            _gameController?.endTurn();
            notifyListeners();
          });
        }
        // AI handles its own delay in autoPlayAITurn
      } else if (gameState!.currentPlayer.type == PlayerType.ai) {
        _scheduleAutoPlayIfNeeded(gameState!.currentPlayer);
      }
    }

    notifyListeners();
    return diceValue;
  }

  /// Move token
  Future<bool> moveToken(Token token) async {
    if (_gameController == null) return false;

    // If connected to server, send authoritative move request instead of applying locally
    if (_socketService != null &&
        _socketService!.isConnectedToServer() &&
        gameState != null) {
      final int fromPos = token.position;
      final int dice = gameState!.diceValue;
      final int toPos = LudoGameLogic.calculateNewPosition(
        token,
        dice,
        token.playerColor,
        rules: gameState!.rules,
      );

      // prevent local double-moves until server responds
      gameState!.canMove = false;
      awaitingServer = true;
      notifyListeners();

      final dynamic playerId = _currentUserId ?? gameState!.currentPlayer.id;
      try {
        _socketService!.sendTokenMoveRequest(
          gameState!.id,
          playerId,
          token.id,
          fromPos,
          toPos,
          dice,
          toPos >= BoardConfig.boardSize,
          token.isInHome,
          LudoGameLogic.isSafePosition(toPos, token.playerColor),
        );
      } catch (e) {
        // ignore emit errors
      }

      return true;
    }

    // Offline/local mode: perform step-by-step animation before applying final logic
    if (gameState != null && !gameState!.canMove) return false;
    
    // Prevent interaction during animation
    gameState!.canMove = false;
    notifyListeners();
    
    final int dice = gameState!.diceValue;
    final List<int> path = LudoGameLogic.calculateMovePath(
      token,
      dice,
      token.playerColor,
      rules: gameState!.rules,
      hasCaptured: gameState!.currentPlayer.hasCaptured,
    );

    if (path.isNotEmpty) {
      // Signal UI to start step-by-step animation
      lastMoveEvent = {
        'movePath': {
          'playerId': gameState!.currentPlayer.id,
          'tokenId': token.id,
          'path': path,
          'from': token.position,
          'color': token.playerColor,
        }
      };
      
      notifyListeners();
      
      final int animationDurationMs = path.length * 300 + 400;
      await Future.delayed(Duration(milliseconds: animationDurationMs));
      
      // Check if token reached the final home cell (57)
      if (path.last == 57) {
        lastMoveEvent = {
          'reachedHome': {
            'playerId': gameState!.currentPlayer.id,
            'tokenId': token.id,
            'color': token.playerColor,
          }
        };
        notifyListeners();
        // Keep celebration visible for a moment
        await Future.delayed(const Duration(milliseconds: 2000));
      }

      // Clear event
      if (lastMoveEvent != null && (lastMoveEvent!['movePath'] != null || lastMoveEvent!['reachedHome'] != null)) {
        lastMoveEvent = null;
      }
    }

    final result = _gameController!.moveToken(
      token,
      dice,
    );

    notifyListeners();
    return result;
  }

  /// Get movable tokens
  List<Token> getMovableTokens() {
    if (gameState == null) return [];
    return LudoGameLogic.getMovableTokens(
      gameState!.currentPlayer,
      gameState!.diceValue,
      allPlayers: gameState!.players,
      rules: gameState!.rules,
    );
  }

  /// Auto play AI turn
  Future<void> autoPlayAITurn() async {
    if (_gameController == null || gameState == null) return;
    if (!isGamePlaying) return;
    if (_isAutoPlaying) return;

    _isAutoPlaying = true;
    try {
      // Fully resolve AI turns in sequence, including extra turns.
      while (isGamePlaying &&
          gameState != null &&
          gameState!.currentPlayer.type == PlayerType.ai) {
        final aiPlayer = gameState!.currentPlayer;
        final String aiTurnPlayerId = aiPlayer.id;
        final aiController = _aiPlayer ??
            AIPlayer(difficulty: aiPlayer.difficulty ?? DifficultyLevel.medium);

        // Roll when needed.
        if (!gameState!.diceRolled || gameState!.diceValue == 0) {
          await Future.delayed(const Duration(milliseconds: 550));
          if (!isGamePlaying ||
              gameState == null ||
              gameState!.currentPlayer.id != aiTurnPlayerId) {
            break;
          }

          rollDice();
          await Future.delayed(const Duration(milliseconds: 1500)); // Wait for dice roll animation
          if (!isGamePlaying ||
              gameState == null ||
              gameState!.currentPlayer.id != aiTurnPlayerId) {
            continue;
          }
        }

        final int currentDice = gameState!.diceValue;
        final movableTokens = LudoGameLogic.getMovableTokens(
          gameState!.currentPlayer,
          currentDice,
          allPlayers: gameState!.players,
          rules: gameState!.rules,
        );

        // Nothing to move: pass turn to avoid deadlock.
        if (movableTokens.isEmpty) {
          await Future.delayed(const Duration(milliseconds: 1000)); // Delay to show dice roll
          _gameController!.endTurn();
          notifyListeners();
          continue;
        }

        final selectedToken = aiController.getBestMove(
          gameState!.currentPlayer,
          currentDice,
          gameState!.players,
          rules: gameState!.rules,
        );
        final tokenToMove = selectedToken ?? movableTokens.first;

        await Future.delayed(const Duration(milliseconds: 450));
        final moved = await moveToken(tokenToMove);

        // Defensive recovery: never stay stuck on an unresolved AI roll.
        if (!moved &&
            gameState != null &&
            gameState!.currentPlayer.id == aiTurnPlayerId &&
            gameState!.diceRolled) {
          _gameController!.endTurn();
          notifyListeners();
        }

        await Future.delayed(const Duration(milliseconds: 250));
      }
    } finally {
      _isAutoPlaying = false;
      _autoPlayScheduled = false;
    }
  }

  void _scheduleAutoPlayIfNeeded(Player? player) {
    if (player == null) return;
    if (player.type != PlayerType.ai) return;
    if (_socketService != null && _socketService!.isConnectedToServer()) return;
    if (_autoPlayScheduled || _isAutoPlaying) return;

    _autoPlayScheduled = true;
    Future.delayed(const Duration(milliseconds: 180), () async {
      _autoPlayScheduled = false;
      try {
        await autoPlayAITurn();
      } finally {}
    });
  }

  /// Pause game
  void pauseGame() {
    _gameController?.pauseGame();
    notifyListeners();
  }

  /// Resume game
  void resumeGame() {
    _gameController?.resumeGame();
    notifyListeners();
  }

  /// Reset game
  void resetGame() {
    _gameController?.resetGame();
    _savedOfflineState = null; // Clear saved state
    notifyListeners();
  }

  /// Remove player from game
  void removePlayer(String playerId) {
    if (_gameController != null) {
      _gameController!.removePlayer(playerId);
      notifyListeners();
    }
  }

  /// Connect to online server
  Future<void> connectToServer(
    String serverUrl,
    String userId,
    String roomId,
    String username,
  ) async {
    if (_socketService == null) return;

    try {
      _currentUserId = userId;
      _currentUsername = username;
      await _socketService!.connect(serverUrl, userId);
      _socketService!.joinRoom(roomId, username);
    } catch (e) {
      print('Connection error: $e');
    }
  }

  /// Request authoritative game state from server for current room
  Future<void> requestAuthoritativeState() async {
    if (_socketService == null) return;

    try {
      // prefer matchedRoom.roomId -> fallback to gameState.id
      String? roomId;
      if (matchedRoom != null) {
        roomId = matchedRoom['roomId'] ?? matchedRoom['room']?['roomId'];
      }
      roomId ??= gameState?.id;
      if (roomId != null) {
        _socketService!.requestState(roomId);
      }
    } catch (e) {
      print('Failed to request authoritative state: $e');
    }
  }

  /// Disconnect from server
  void disconnectFromServer() {
    _socketService?.disconnect();
  }

  /// Request undo of last move (online)
  void requestUndo() {
    if (_socketService == null || gameState == null) return;
    _socketService!.requestUndo(gameState!.id, gameState!.currentPlayer.id);
  }

  /// Quick match: emit quick match request to server
  void quickMatch({int maxPlayers = 4}) {
    if (_socketService == null ||
        _currentUserId == null ||
        _currentUsername == null) return;
    isSearchingMatch = true;
    notifyListeners();
    _socketService!.quickMatch(
      _currentUserId!,
      _currentUsername!,
      maxPlayers: maxPlayers,
    );
  }

  /// Cancel quick match
  void cancelQuickMatch() {
    if (!isSearchingMatch) return;
    isSearchingMatch = false;
    try {
      if (_socketService != null && _currentUserId != null) {
        // emit cancel event to server
        try {
          _socketService!.socket.emit('cancel_quick_match', {
            'playerId': _currentUserId,
          });
        } catch (e) {
          // fallback: use quick match cancellation event name
          _socketService!.socket.emit('cancel_match', {
            'playerId': _currentUserId,
          });
        }
      }
    } catch (e) {
      // ignore
    }
    notifyListeners();
  }

  void _handleMatchFound(dynamic data) {
    // server returned match info (room)
    matchedRoom = data;
    isSearchingMatch = false;
    // auto-join the room via socket service
    try {
      final String roomId = data['roomId'] ?? data['room']?['roomId'];
      if (roomId != null &&
          _socketService != null &&
          _currentUsername != null) {
        _socketService!.joinRoom(roomId, _currentUsername!);
        // request authoritative state
        _socketService!.requestState(roomId);
      }
    } catch (e) {
      print('Error handling match found: $e');
    }
    notifyListeners();
  }

  /// Vote on pending undo request
  void voteUndo(bool accept) {
    if (_socketService == null || gameState == null) return;
    _socketService!.voteUndo(
      gameState!.id,
      gameState!.currentPlayer.id,
      accept,
    );
  }

  void _handleUndoRequested(dynamic data) {
    // Notify UI that someone requested an undo
    pendingUndoRequest = data;
    notifyListeners();
  }

  void _handleUndoVoteRecorded(dynamic data) {
    // UI can show vote tally/progress
    pendingUndoRequest = data ?? pendingUndoRequest;
    notifyListeners();
  }

  void _handleUndoAccepted(dynamic data) {
    // Update local state from authoritative gameState
    if (data != null && data['gameState'] != null) {
      _applyServerGameState(data['gameState']);
    }
    notifyListeners();
  }

  void _handleUndoRejected(dynamic data) {
    // Undo rejected - show notification
    pendingUndoRequest = null;
    notifyListeners();
  }

  // move emitting is now handled inline in moveToken() to ensure from/to are correct

  void _handleRemoteDiceRoll(dynamic data) {
    // Apply authoritative dice roll / state if provided by server
    try {
      if (data != null) {
        // capture dice roll event for UI animation
        try {
          if (data['diceValue'] != null) {
            lastMoveEvent = {
              'diceRoll': {
                'playerId': data['playerId'],
                'diceValue': data['diceValue'],
              },
            };
            Future.delayed(const Duration(milliseconds: 1400), () {
              lastMoveEvent = null;
              notifyListeners();
            });
          }
        } catch (e) {}

        if (data['gameState'] != null) {
          _applyServerGameState(data['gameState']);
          awaitingServer = false;
        }
      }
    } catch (e) {
      // ignore
    }
    notifyListeners();
  }

  void _handleRemoteTokenMove(dynamic data) {
    // Apply authoritative token move / state from server and capture for UI highlight
    try {
      // snapshot previous turn info for extra-turn detection
      final String? _prevCurrentPlayerId =
          _gameController?.gameState?.currentPlayer.id;
      final int _prevDice = _gameController?.gameState?.diceValue ?? 0;
      if (data != null && data['newPosition'] != null) {
        // prepare lastMoveEvent from incoming payload
        lastMoveEvent = Map<String, dynamic>.from(data as Map);

        // If server provided full gameState, detect which tokens were killed
        try {
          if (data['gameState'] != null && _gameController?.gameState != null) {
            final Map<String, dynamic> incoming = Map<String, dynamic>.from(
              data['gameState'],
            );
            final List<dynamic> incomingPlayers =
                incoming['players'] as List<dynamic>;
            // build lookup for new token positions by playerId -> tokenId -> pos
            final Map<String, Map<int, dynamic>> newTokenMap = {};
            final Map<String, int> newConsecutiveMap = {};
            for (final p in incomingPlayers) {
              try {
                final Map<String, dynamic> mp = Map<String, dynamic>.from(
                  p as Map,
                );
                final String pid = mp['id'];
                final int newConsec = mp['consecutiveSixes'] as int? ?? 0;
                final List<dynamic> toks = mp['tokens'] as List<dynamic>;
                newTokenMap[pid] = {};
                for (final t in toks) {
                  final Map<String, dynamic> tmap = Map<String, dynamic>.from(
                    t as Map,
                  );
                  newTokenMap[pid]![tmap['id'] as int] = tmap;
                }
                newConsecutiveMap[pid] = newConsec;
              } catch (e) {
                // ignore per-player parse errors
              }
            }

            final List<Map<String, dynamic>> killed = [];
            final List<Map<String, dynamic>> spawned = [];
            final oldState = _gameController!.gameState;
            for (final player in oldState!.players) {
              for (final token in player.tokens) {
                final newToken = newTokenMap[player.id]?[token.id];
                final int? newPos =
                    newToken != null ? (newToken['position'] as int?) : null;
                final bool newKilled = newToken != null
                    ? (newToken['isKilled'] as bool? ?? false)
                    : false;

                // detect kill: previously on-board, now removed/killed
                if (token.position >= 0 &&
                    (newPos == null || newPos < 0 || newKilled)) {
                  killed.add({
                    'playerId': player.id,
                    'tokenId': token.id,
                    'from': token.position,
                    'to': newPos ?? -1,
                  });
                }

                // detect spawn/opening: previously in home (-1) and now on board (>=0)
                if (token.position < 0 && (newPos != null && newPos >= 0)) {
                  spawned.add({
                    'playerId': player.id,
                    'tokenId': token.id,
                    'from': token.position,
                    'to': newPos,
                  });
                }
              }
            }

            if (killed.isNotEmpty) {
              lastMoveEvent!['killedTokens'] = killed;
            }
            if (spawned.isNotEmpty) {
              lastMoveEvent!['spawnedTokens'] = spawned;
            }

            // detect extra-turn: if prev current player stays same after server state
            try {
              final String? newCurrent = incoming['currentPlayerIndex'] != null
                  ? (incoming['players']
                      as List<dynamic>)[incoming['currentPlayerIndex']]['id']
                  : null;
              if (_prevCurrentPlayerId != null &&
                  newCurrent != null &&
                  _prevCurrentPlayerId == newCurrent &&
                  _prevDice == 6) {
                lastMoveEvent!['extraTurn'] = true;
              }
            } catch (e) {
              // ignore
            }

            // Detect three-consecutive-six penalty: if a player's consecutiveSixes
            // dropped from >=3 to 0 in the incoming state, mark a penalty.
            try {
              final List<Map<String, dynamic>> penalties = [];
              for (final player in oldState.players) {
                final int oldConsec = player.consecutiveSixes;
                final int newConsec = newConsecutiveMap[player.id] ?? oldConsec;
                if (oldConsec >= 3 && newConsec == 0) {
                  penalties.add({
                    'playerId': player.id,
                    'type': 'three_consecutive_sixes',
                  });
                }
              }
              if (penalties.isNotEmpty) {
                lastMoveEvent!['penalties'] = penalties;
              }
            } catch (e) {
              // ignore
            }
          }
        } catch (e) {
          // ignore detection errors
        }

        // clear after 2.5s
        Future.delayed(const Duration(milliseconds: 2500), () {
          lastMoveEvent = null;
          notifyListeners();
        });
      }

      if (data != null && data['gameState'] != null) {
        _applyServerGameState(data['gameState']);
        awaitingServer = false;
      } else if (data != null && data['roomId'] != null) {
        // server may only give room id -> request full state
        _socketService?.requestState(data['roomId']);
        // keep awaitingServer true until state arrives
      }
    } catch (e) {
      // ignore
    }
    notifyListeners();
  }

  void _handleRemoteTurnChange(dynamic data) {
    // Handle turn change from server
    notifyListeners();
  }

  void _handleRemoteStateSync(dynamic data) {
    // Sync game state from server
    if (data != null && data['state'] != null) {
      _applyServerGameState(data['state']);
    }
    notifyListeners();
  }

  void _applyServerGameState(dynamic stateJson) {
    if (_gameController == null) return;

    try {
      final Map<String, dynamic> m = Map<String, dynamic>.from(stateJson);
      final serverState = GameState.fromJson(m);
      _gameController!.gameState = serverState;
      // trigger any controller callbacks and update listeners
      _gameController!.onGameStateChanged?.call();
      notifyListeners();
    } catch (e) {
      print('Failed to apply server game state: $e');
    }
  }

  @override
  void dispose() {
    _socketService?.disconnect();
    super.dispose();
  }

  // Public getters for UI access
  String? get currentUserId => _currentUserId;
  String? get currentUsername => _currentUsername;
  LudoSocketService? get socketService => _socketService;
}

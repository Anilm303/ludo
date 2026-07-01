// Ludo Game Models
import 'package:flutter/material.dart';

enum PlayerColor { red, green, yellow, blue }

enum PlayerType { human, ai }

enum GameMode { offline, online, vsComputer }

enum DifficultyLevel { easy, medium, hard }

enum GameStatus { waiting, playing, paused, finished }

/// Toggleable rule set for different Ludo variants.
class LudoRuleSettings {
  final bool showSafeCells;
  final bool openTokenOnOne;
  final bool openTokenOnSix;
  final bool extraTurnOnOne;
  final bool extraTurnOnSix;
  final bool extraTurnOnCapture;
  final bool extraTurnOnHome;
  final bool mustCutIfCuttable;
  final bool mustCaptureToEnterHome;
  final bool barrierEnabled;
  final bool threeConsecutiveSixesBringCoinOut;
  final bool threeConsecutiveOnesCutOwnCoin;
  final bool skipTurnAfterThreeOnes;
  final bool startCoinsInBase;

  const LudoRuleSettings({
    this.showSafeCells = true,
    this.openTokenOnOne = false,
    this.openTokenOnSix = true,
    this.extraTurnOnOne = false,
    this.extraTurnOnSix = true,
    this.extraTurnOnCapture = true,
    this.extraTurnOnHome = true,
    this.mustCutIfCuttable = true,
    this.mustCaptureToEnterHome = true,
    this.barrierEnabled = true,
    this.threeConsecutiveSixesBringCoinOut = false,
    this.threeConsecutiveOnesCutOwnCoin = false,
    this.skipTurnAfterThreeOnes = false,
    this.startCoinsInBase = true,
  });

  LudoRuleSettings copyWith({
    bool? showSafeCells,
    bool? openTokenOnOne,
    bool? openTokenOnSix,
    bool? extraTurnOnOne,
    bool? extraTurnOnSix,
    bool? extraTurnOnCapture,
    bool? extraTurnOnHome,
    bool? mustCutIfCuttable,
    bool? mustCaptureToEnterHome,
    bool? barrierEnabled,
    bool? threeConsecutiveSixesBringCoinOut,
    bool? threeConsecutiveOnesCutOwnCoin,
    bool? skipTurnAfterThreeOnes,
    bool? startCoinsInBase,
  }) {
    return LudoRuleSettings(
      showSafeCells: showSafeCells ?? this.showSafeCells,
      openTokenOnOne: openTokenOnOne ?? this.openTokenOnOne,
      openTokenOnSix: openTokenOnSix ?? this.openTokenOnSix,
      extraTurnOnOne: extraTurnOnOne ?? this.extraTurnOnOne,
      extraTurnOnSix: extraTurnOnSix ?? this.extraTurnOnSix,
      extraTurnOnCapture: extraTurnOnCapture ?? this.extraTurnOnCapture,
      extraTurnOnHome: extraTurnOnHome ?? this.extraTurnOnHome,
      mustCutIfCuttable: mustCutIfCuttable ?? this.mustCutIfCuttable,
      mustCaptureToEnterHome: mustCaptureToEnterHome ?? this.mustCaptureToEnterHome,
      barrierEnabled: barrierEnabled ?? this.barrierEnabled,
      threeConsecutiveSixesBringCoinOut:
          threeConsecutiveSixesBringCoinOut ??
          this.threeConsecutiveSixesBringCoinOut,
      threeConsecutiveOnesCutOwnCoin:
          threeConsecutiveOnesCutOwnCoin ?? this.threeConsecutiveOnesCutOwnCoin,
      skipTurnAfterThreeOnes:
          skipTurnAfterThreeOnes ?? this.skipTurnAfterThreeOnes,
      startCoinsInBase: startCoinsInBase ?? this.startCoinsInBase,
    );
  }

  factory LudoRuleSettings.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const LudoRuleSettings();
    return LudoRuleSettings(
      showSafeCells: json['showSafeCells'] as bool? ?? true,
      openTokenOnOne: json['openTokenOnOne'] as bool? ?? false,
      openTokenOnSix: json['openTokenOnSix'] as bool? ?? true,
      extraTurnOnOne: json['extraTurnOnOne'] as bool? ?? false,
      extraTurnOnSix: json['extraTurnOnSix'] as bool? ?? true,
      extraTurnOnCapture: json['extraTurnOnCapture'] as bool? ?? true,
      extraTurnOnHome: json['extraTurnOnHome'] as bool? ?? true,
      mustCutIfCuttable: json['mustCutIfCuttable'] as bool? ?? true,
      mustCaptureToEnterHome: json['mustCaptureToEnterHome'] as bool? ?? true,
      barrierEnabled: json['barrierEnabled'] as bool? ?? true,
      threeConsecutiveSixesBringCoinOut:
          json['threeConsecutiveSixesBringCoinOut'] as bool? ?? false,
      threeConsecutiveOnesCutOwnCoin:
          json['threeConsecutiveOnesCutOwnCoin'] as bool? ?? false,
      skipTurnAfterThreeOnes: json['skipTurnAfterThreeOnes'] as bool? ?? false,
      startCoinsInBase: json['startCoinsInBase'] as bool? ?? true,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'showSafeCells': showSafeCells,
      'openTokenOnOne': openTokenOnOne,
      'openTokenOnSix': openTokenOnSix,
      'extraTurnOnOne': extraTurnOnOne,
      'extraTurnOnSix': extraTurnOnSix,
      'extraTurnOnCapture': extraTurnOnCapture,
      'extraTurnOnHome': extraTurnOnHome,
      'mustCutIfCuttable': mustCutIfCuttable,
      'mustCaptureToEnterHome': mustCaptureToEnterHome,
      'barrierEnabled': barrierEnabled,
      'threeConsecutiveSixesBringCoinOut': threeConsecutiveSixesBringCoinOut,
      'threeConsecutiveOnesCutOwnCoin': threeConsecutiveOnesCutOwnCoin,
      'skipTurnAfterThreeOnes': skipTurnAfterThreeOnes,
      'startCoinsInBase': startCoinsInBase,
    };
  }
}

/// Represents a single token in the game
class Token {
  int id; // 0-3 (4 tokens per player)
  PlayerColor playerColor;
  int position; // 0-51 (board positions)
  bool isInHome; // true when token is in home zone
  bool isKilled; // true when token is captured

  Token({
    required this.id,
    required this.playerColor,
    this.position = -1, // -1 means not yet opened
    this.isInHome = false,
    this.isKilled = false,
  });

  factory Token.fromJson(Map<String, dynamic> json) {
    return Token(
      id: json['id'],
      playerColor: PlayerColor.values[json['playerColor']],
      position: json['position'],
      isInHome: json['isInHome'],
      isKilled: json['isKilled'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'playerColor': playerColor.index,
      'position': position,
      'isInHome': isInHome,
      'isKilled': isKilled,
    };
  }

  Token copy() {
    return Token(
      id: id,
      playerColor: playerColor,
      position: position,
      isInHome: isInHome,
      isKilled: isKilled,
    );
  }
}

/// Represents a player in the game
class Player {
  String id;
  String name;
  PlayerColor color;
  PlayerType type;
  DifficultyLevel? difficulty;
  int tokenCount;
  List<Token> tokens;
  bool isCurrentTurn;
  int consecutiveSixes;
  int consecutiveOnes;
  int skipTurns;
  int tokensReachedHome;
  bool hasCaptured;

  Player({
    required this.id,
    required this.name,
    required this.color,
    this.type = PlayerType.human,
    this.difficulty,
    this.tokenCount = 4,
    List<Token>? tokens,
    this.isCurrentTurn = false,
    this.consecutiveSixes = 0,
    this.consecutiveOnes = 0,
    this.skipTurns = 0,
    this.tokensReachedHome = 0,
    this.hasCaptured = false,
  }) : tokens = tokens ?? _createTokens(color, tokenCount);

  static List<Token> _createTokens(PlayerColor color, int tokenCount) {
    return List.generate(
      tokenCount,
      (index) => Token(id: index, playerColor: color),
    );
  }

  bool get hasWon => tokensReachedHome == tokenCount;
  bool get hasOpenedToken => tokens.any((t) => t.position >= 0);

  factory Player.fromJson(Map<String, dynamic> json) {
    return Player(
      id: json['id'],
      name: json['name'],
      color: PlayerColor.values[json['color']],
      type: PlayerType.values[json['type']],
      difficulty: json['difficulty'] != null
          ? DifficultyLevel.values[json['difficulty']]
          : null,
      tokenCount: json['tokenCount'] as int? ?? 4,
      tokens: (json['tokens'] as List<dynamic>?)
          ?.map((t) => Token.fromJson(t as Map<String, dynamic>))
          .toList(),
      isCurrentTurn: json['isCurrentTurn'] as bool? ?? false,
      consecutiveSixes: json['consecutiveSixes'] as int? ?? 0,
      consecutiveOnes: json['consecutiveOnes'] as int? ?? 0,
      skipTurns: json['skipTurns'] as int? ?? 0,
      tokensReachedHome: json['tokensReachedHome'] as int? ?? 0,
      hasCaptured: json['hasCaptured'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'color': color.index,
      'type': type.index,
      'difficulty': difficulty?.index,
      'tokenCount': tokenCount,
      'tokens': tokens.map((t) => t.toJson()).toList(),
      'isCurrentTurn': isCurrentTurn,
      'consecutiveSixes': consecutiveSixes,
      'consecutiveOnes': consecutiveOnes,
      'skipTurns': skipTurns,
      'tokensReachedHome': tokensReachedHome,
      'hasCaptured': hasCaptured,
    };
  }

  Player copy() {
    return Player(
      id: id,
      name: name,
      color: color,
      type: type,
      difficulty: difficulty,
      tokenCount: tokenCount,
      tokens: tokens.map((t) => t.copy()).toList(),
      isCurrentTurn: isCurrentTurn,
      consecutiveSixes: consecutiveSixes,
      consecutiveOnes: consecutiveOnes,
      skipTurns: skipTurns,
      tokensReachedHome: tokensReachedHome,
      hasCaptured: hasCaptured,
    );
  }
}

/// Board configuration
class BoardConfig {
  static const int totalPositions = 52; // Main board positions
  static const int homePositions = 6; // Home path positions
  static const int boardSize = totalPositions + homePositions;

  // Starting positions for each player (Matching the "Select Players" buttons order)
  static const Map<PlayerColor, int> playerStartPositions = {
    PlayerColor.yellow: 13, // Top Left
    PlayerColor.green: 26,  // Top Right
    PlayerColor.red: 39,    // Bottom Right
    PlayerColor.blue: 0,    // Bottom Left
  };

  // Safe star positions (cannot be killed)
  static const List<int> safePositions = [0, 8, 13, 21, 26, 34, 39, 47];

  // Home entry positions (must have exact dice)
  static const Map<PlayerColor, int> homeEntryPositions = {
    PlayerColor.yellow: 13,
    PlayerColor.green: 26,
    PlayerColor.red: 39,
    PlayerColor.blue: 0,
  };

  // Home path start (after reaching position 51)
  static const int homePathStart = 52;
}

/// Game state
class GameState {
  String id;
  List<Player> players;
  int currentPlayerIndex;
  int diceValue;
  bool diceRolled;
  bool canMove;
  GameStatus status;
  List<String> winnerIds;
  DateTime createdAt;
  DateTime? startedAt;
  DateTime? endedAt;
  GameMode gameMode;
  LudoRuleSettings rules;
  int? selectedTokenId; // -1 if no token selected

  GameState({
    required this.id,
    required this.players,
    this.currentPlayerIndex = 0,
    this.diceValue = 0,
    this.diceRolled = false,
    this.canMove = false,
    this.status = GameStatus.waiting,
    List<String>? winnerIds,
    required this.createdAt,
    this.startedAt,
    this.endedAt,
    required this.gameMode,
    this.rules = const LudoRuleSettings(),
    this.selectedTokenId,
  }) : winnerIds = winnerIds ?? [];

  Player get currentPlayer => players[currentPlayerIndex];

  bool get hasGameEnded => status == GameStatus.finished;
  bool get isPlaying => status == GameStatus.playing;
  Player? get winner => winnerIds.isNotEmpty 
    ? players.firstWhere((p) => p.id == winnerIds.first, orElse: () => players.first) 
    : null;

  factory GameState.fromJson(Map<String, dynamic> json) {
    return GameState(
      id: json['id'],
      players: (json['players'] as List<dynamic>)
          .map((p) => Player.fromJson(p as Map<String, dynamic>))
          .toList(),
      currentPlayerIndex: json['currentPlayerIndex'],
      diceValue: json['diceValue'],
      diceRolled: json['diceRolled'],
      canMove: json['canMove'],
      status: GameStatus.values[json['status']],
      winnerIds: json['winnerIds'] != null
          ? List<String>.from(json['winnerIds'])
          : (json['winner'] != null ? [json['winner']['id']] : []),
      createdAt: DateTime.parse(json['createdAt']),
      startedAt: json['startedAt'] != null
          ? DateTime.parse(json['startedAt'])
          : null,
      endedAt: json['endedAt'] != null ? DateTime.parse(json['endedAt']) : null,
      gameMode: GameMode.values[json['gameMode']],
      rules: LudoRuleSettings.fromJson(json['rules'] as Map<String, dynamic>?),
      selectedTokenId: json['selectedTokenId'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'players': players.map((p) => p.toJson()).toList(),
      'currentPlayerIndex': currentPlayerIndex,
      'diceValue': diceValue,
      'diceRolled': diceRolled,
      'canMove': canMove,
      'status': status.index,
      'winnerIds': winnerIds,
      'createdAt': createdAt.toIso8601String(),
      'startedAt': startedAt?.toIso8601String(),
      'endedAt': endedAt?.toIso8601String(),
      'gameMode': gameMode.index,
      'rules': rules.toJson(),
      'selectedTokenId': selectedTokenId,
    };
  }

  GameState copy() {
    return GameState(
      id: id,
      players: players.map((p) => p.copy()).toList(),
      currentPlayerIndex: currentPlayerIndex,
      diceValue: diceValue,
      diceRolled: diceRolled,
      canMove: canMove,
      status: status,
      winnerIds: List.from(winnerIds),
      createdAt: createdAt,
      startedAt: startedAt,
      endedAt: endedAt,
      gameMode: gameMode,
      rules: rules,
      selectedTokenId: selectedTokenId,
    );
  }
}

/// Represents a move action
class Move {
  int tokenId;
  int fromPosition;
  int toPosition;
  int diceValue;
  bool killsOpponent;

  Move({
    required this.tokenId,
    required this.fromPosition,
    required this.toPosition,
    required this.diceValue,
    this.killsOpponent = false,
  });

  factory Move.fromJson(Map<String, dynamic> json) {
    return Move(
      tokenId: json['tokenId'],
      fromPosition: json['fromPosition'],
      toPosition: json['toPosition'],
      diceValue: json['diceValue'],
      killsOpponent: json['killsOpponent'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'tokenId': tokenId,
      'fromPosition': fromPosition,
      'toPosition': toPosition,
      'diceValue': diceValue,
      'killsOpponent': killsOpponent,
    };
  }
}

/// Room for online multiplayer
class GameRoom {
  String id;
  String name;
  String creatorId;
  List<String> playerIds;
  int maxPlayers;
  GameMode gameMode;
  bool isStarted;
  bool get isFull => playerIds.length >= maxPlayers;

  GameRoom({
    required this.id,
    required this.name,
    required this.creatorId,
    required this.playerIds,
    this.maxPlayers = 4,
    this.gameMode = GameMode.online,
    this.isStarted = false,
  });

  factory GameRoom.fromJson(Map<String, dynamic> json) {
    return GameRoom(
      id: json['id'],
      name: json['name'],
      creatorId: json['creatorId'],
      playerIds: List<String>.from(json['playerIds']),
      maxPlayers: json['maxPlayers'],
      gameMode: GameMode.values[json['gameMode']],
      isStarted: json['isStarted'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'creatorId': creatorId,
      'playerIds': playerIds,
      'maxPlayers': maxPlayers,
      'gameMode': gameMode.index,
      'isStarted': isStarted,
    };
  }
}

/// Player profile
class PlayerProfile {
  String id;
  String username;
  String? avatarUrl;
  int totalGamesPlayed;
  int totalWins;
  int totalLosses;
  double winRate;
  int ranking;

  PlayerProfile({
    required this.id,
    required this.username,
    this.avatarUrl,
    this.totalGamesPlayed = 0,
    this.totalWins = 0,
    this.totalLosses = 0,
    this.winRate = 0,
    this.ranking = 0,
  });

  factory PlayerProfile.fromJson(Map<String, dynamic> json) {
    return PlayerProfile(
      id: json['id'],
      username: json['username'],
      avatarUrl: json['avatarUrl'],
      totalGamesPlayed: json['totalGamesPlayed'],
      totalWins: json['totalWins'],
      totalLosses: json['totalLosses'],
      winRate: json['winRate'],
      ranking: json['ranking'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'username': username,
      'avatarUrl': avatarUrl,
      'totalGamesPlayed': totalGamesPlayed,
      'totalWins': totalWins,
      'totalLosses': totalLosses,
      'winRate': winRate,
      'ranking': ranking,
    };
  }
}

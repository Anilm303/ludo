// Ludo AI Player Logic
import 'dart:math';
import '../models/ludo_models.dart';
import 'ludo_game_logic.dart';

class AIPlayer {
  final DifficultyLevel difficulty;
  final Random _random = Random();

  AIPlayer({this.difficulty = DifficultyLevel.medium});

  /// Get best move for AI player
  Token? getBestMove(
    Player aiPlayer,
    int diceValue,
    List<Player> allPlayers, {
    LudoRuleSettings rules = const LudoRuleSettings(),
  }) {
    final movableTokens = LudoGameLogic.getMovableTokens(
      aiPlayer,
      diceValue,
      allPlayers: allPlayers,
      rules: rules,
    );

    if (movableTokens.isEmpty) {
      return null;
    }

    switch (difficulty) {
      case DifficultyLevel.easy:
        return _getEasyMove(
          aiPlayer,
          movableTokens,
          diceValue,
          allPlayers,
          rules,
        );
      case DifficultyLevel.medium:
        return _getMediumMove(
          aiPlayer,
          movableTokens,
          diceValue,
          allPlayers,
          rules,
        );
      case DifficultyLevel.hard:
        return _getHardMove(
          aiPlayer,
          movableTokens,
          diceValue,
          allPlayers,
          rules,
        );
    }
  }

  /// Easy AI: Random move
  Token? _getEasyMove(
    Player aiPlayer,
    List<Token> movableTokens,
    int diceValue,
    List<Player> allPlayers,
    LudoRuleSettings rules,
  ) {
    if (movableTokens.isEmpty) return null;
    return movableTokens[_random.nextInt(movableTokens.length)];
  }

  /// Medium AI: Balanced strategy
  Token? _getMediumMove(
    Player aiPlayer,
    List<Token> movableTokens,
    int diceValue,
    List<Player> allPlayers,
    LudoRuleSettings rules,
  ) {
    final Map<Token, int> scoredMoves = {};

    for (final token in movableTokens) {
      int score = 0;

      // Priority 1: Kill opponent token (high score)
      final newPos = LudoGameLogic.calculateNewPosition(
        token,
        diceValue,
        aiPlayer.color,
        rules: rules,
      );

      final tokensToKill = LudoGameLogic.getTokensAtPosition(
        allPlayers,
        newPos,
        aiPlayer.color,
      );

      if (tokensToKill.isNotEmpty) {
        score += 100;
      }

      // Priority 2: Protect token in safe zone
      if (LudoGameLogic.isSafePosition(newPos, aiPlayer.color)) {
        score += 50;
      }

      // Priority 3: Open new token
      if (token.position == -1 && diceValue == 6) {
        score += 30;
      }

      // Priority 4: Progress towards home
      if (token.position >= 0) {
        final currentProgress = LudoGameLogic.getRelativeProgress(token);
        final projectedProgress = LudoGameLogic.getProjectedProgress(
          token,
          diceValue,
        );
        if (projectedProgress > currentProgress) {
          score += (projectedProgress - currentProgress);
        }
      }

      // Add randomness for medium AI
      score += _random.nextInt(20);

      scoredMoves[token] = score;
    }

    return scoredMoves.entries.reduce((a, b) => a.value > b.value ? a : b).key;
  }

  /// Hard AI: Aggressive strategy
  Token? _getHardMove(
    Player aiPlayer,
    List<Token> movableTokens,
    int diceValue,
    List<Player> allPlayers,
    LudoRuleSettings rules,
  ) {
    final Map<Token, double> scoredMoves = {};

    for (final token in movableTokens) {
      double score = 0.0;

      final newPos = LudoGameLogic.calculateNewPosition(
        token,
        diceValue,
        aiPlayer.color,
        rules: rules,
      );

      // Priority 1: Kill opponent token (highest weight)
      final tokensToKill = LudoGameLogic.getTokensAtPosition(
        allPlayers,
        newPos,
        aiPlayer.color,
      );

      if (tokensToKill.isNotEmpty) {
        score += 500.0;

        // Bonus for killing high-progress tokens
        for (final killedToken in tokensToKill) {
          if (killedToken.position > 30) {
            score += 100.0;
          }
        }
      }

      // Priority 2: Reach home path or enter home
      if (token.isInHome) {
        score += 200.0;
        // The closer to final cell, the better
        score += (token.position - BoardConfig.totalPositions) * 20.0;
      } else if (newPos >= BoardConfig.totalPositions - 5) {
        score += 350.0;
      }

      // Priority 3: Safe zone protection
      if (LudoGameLogic.isSafePosition(newPos, aiPlayer.color, rules: rules)) {
        score += 180.0;
      }
      
      // Avoid leaving safe positions unless for a kill or home
      if (token.position >= 0 && LudoGameLogic.isSafePosition(token.position, aiPlayer.color, rules: rules)) {
        score -= 100.0;
      }

      // Priority 4: Block opponent or avoid being killed
      score += _evaluateBlockingOpponents(token, newPos, aiPlayer, allPlayers);
      score -= _evaluateDanger(newPos, aiPlayer, allPlayers, rules);

      // Priority 5: Overall progress
      if (token.position >= 0) {
        final currentProgress = LudoGameLogic.getRelativeProgress(token);
        final projectedProgress = LudoGameLogic.getProjectedProgress(
          token,
          diceValue,
        );
        if (projectedProgress > currentProgress) {
          score += (projectedProgress - currentProgress) * 2.5;
        }
      }

      // Priority 6: Open tokens strategically
      if (token.position == -1 && diceValue == 6) {
        // Check if opponent tokens are far
        final allTokensProgress = _getAverageOpponentProgress(
          allPlayers,
          aiPlayer,
        );
        if (allTokensProgress < 20) {
          score += 200.0;
        } else {
          score += 50.0;
        }
      }

      scoredMoves[token] = score;
    }

    return scoredMoves.entries.reduce((a, b) => a.value > b.value ? a : b).key;
  }

  /// Evaluate danger of being killed at a position
  double _evaluateDanger(int pos, Player aiPlayer, List<Player> allPlayers, LudoRuleSettings rules) {
    if (pos < 0 || pos >= BoardConfig.totalPositions) return 0.0;
    if (LudoGameLogic.isSafePosition(pos, aiPlayer.color, rules: rules)) return 0.0;
    
    double danger = 0.0;
    for (final opponent in allPlayers) {
      if (opponent.color == aiPlayer.color) continue;
      for (final oppToken in opponent.tokens) {
        if (oppToken.position >= 0 && oppToken.position < BoardConfig.totalPositions) {
          int dist = (pos - oppToken.position + BoardConfig.totalPositions) % BoardConfig.totalPositions;
          if (dist > 0 && dist <= 6) {
            danger += (7 - dist) * 20.0; // Very dangerous if opponent is right behind
          }
        }
      }
    }
    return danger;
  }

  /// Evaluate blocking opponent tokens
  double _evaluateBlockingOpponents(
    Token token,
    int newPos,
    Player aiPlayer,
    List<Player> allPlayers,
  ) {
    double addScore = 0.0;
    // Find if placing this token would block opponent advancement
    for (final opponent in allPlayers) {
      if (opponent.color == aiPlayer.color) continue;

      for (final oppToken in opponent.tokens) {
        if (oppToken.position >= 0 && oppToken.position + 6 == newPos) {
          // This position blocks opponent's max move
          addScore += 75.0;
        }
      }
    }
    return addScore;
  }

  /// Get average progress of opponent tokens
  double _getAverageOpponentProgress(List<Player> allPlayers, Player aiPlayer) {
    double totalProgress = 0;
    int tokenCount = 0;

    for (final player in allPlayers) {
      if (player.color == aiPlayer.color) continue;

      for (final token in player.tokens) {
        if (token.position >= 0) {
          totalProgress += token.position;
          tokenCount++;
        }
      }
    }

    return tokenCount == 0 ? 0 : totalProgress / tokenCount;
  }

  /// Predict best dice outcome (for decision making)
  List<Token> predictBestOutcome(
    Player aiPlayer,
    List<Player> allPlayers, {
    LudoRuleSettings rules = const LudoRuleSettings(),
  }) {
    final predictions = <Token>[];

    for (int dice = 1; dice <= 6; dice++) {
      final move = getBestMove(aiPlayer, dice, allPlayers, rules: rules);
      if (move != null) {
        predictions.add(move);
      }
    }

    return predictions;
  }
}

/// AI difficulty selector
class AIDifficultyFactory {
  static AIPlayer createAI(DifficultyLevel difficulty) {
    return AIPlayer(difficulty: difficulty);
  }

  static DifficultyLevel selectRandomDifficulty() {
    final random = Random();
    return DifficultyLevel.values[random.nextInt(
      DifficultyLevel.values.length,
    )];
  }
}

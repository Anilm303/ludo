import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

enum GameSound {
  diceRoll,
  tokenMove,
  tokenKill,
  playerWin,
  gameOver,
  buttonTap,
}

class SoundService extends ChangeNotifier {
  bool _soundEnabled = true;
  bool _musicEnabled = false;

  bool get soundEnabled => _soundEnabled;
  bool get musicEnabled => _musicEnabled;

  /// Toggle sound effects on/off
  void toggleSound() {
    _soundEnabled = !_soundEnabled;
    notifyListeners();
    _logSound('Sound effects ${_soundEnabled ? 'enabled' : 'disabled'}');
  }

  /// Toggle background music on/off
  void toggleMusic() {
    _musicEnabled = !_musicEnabled;
    notifyListeners();
    _logSound('Background music ${_musicEnabled ? 'enabled' : 'disabled'}');
  }

  /// Play a game sound effect
  Future<void> playSound(GameSound sound) async {
    if (!_soundEnabled) return;

    try {
      _logSound('Playing: ${_getSoundName(sound)}');
      switch (sound) {
        case GameSound.diceRoll:
          await SystemSound.play(SystemSoundType.click);
          await HapticFeedback.lightImpact();
          break;
        case GameSound.tokenMove:
          await SystemSound.play(SystemSoundType.click);
          await HapticFeedback.selectionClick();
          break;
        case GameSound.tokenKill:
          await SystemSound.play(SystemSoundType.alert);
          await HapticFeedback.mediumImpact();
          break;
        case GameSound.playerWin:
          await SystemSound.play(SystemSoundType.alert);
          await Future.delayed(const Duration(milliseconds: 80));
          await SystemSound.play(SystemSoundType.alert);
          await HapticFeedback.heavyImpact();
          break;
        case GameSound.gameOver:
          await SystemSound.play(SystemSoundType.alert);
          await HapticFeedback.heavyImpact();
          break;
        case GameSound.buttonTap:
          await SystemSound.play(SystemSoundType.click);
          await HapticFeedback.selectionClick();
          break;
      }
    } catch (e) {
      debugPrint('❌ Error playing sound: $e');
    }
  }

  /// Play background music
  Future<void> playBackgroundMusic() async {
    if (!_musicEnabled) return;

    try {
      _logSound('Starting background music');
    } catch (e) {
      debugPrint('❌ Error playing music: $e');
    }
  }

  /// Stop background music
  Future<void> stopBackgroundMusic() async {
    try {
      _logSound('Stopping background music');
    } catch (e) {
      debugPrint('❌ Error stopping music: $e');
    }
  }

  /// Get sound filename
  String _getSoundName(GameSound sound) {
    switch (sound) {
      case GameSound.diceRoll:
        return 'dice_roll';
      case GameSound.tokenMove:
        return 'token_move';
      case GameSound.tokenKill:
        return 'token_kill';
      case GameSound.playerWin:
        return 'player_win';
      case GameSound.gameOver:
        return 'game_over';
      case GameSound.buttonTap:
        return 'button_tap';
    }
  }

  /// Log sound activity
  void _logSound(String message) {
    debugPrint('🔊 Sound: $message');
  }

  /// Initialize sound service
  Future<void> initialize() async {
    _logSound('Initializing Sound Service');

    try {
      _logSound('Sound Service initialized');
    } catch (e) {
      debugPrint('❌ Error initializing sounds: $e');
    }
  }

  /// Dispose and cleanup
  Future<void> shutdown() async {
    try {
      await stopBackgroundMusic();
      _logSound('Sound Service disposed');
    } catch (e) {
      debugPrint('❌ Error disposing sounds: $e');
    }
  }
}

// Extension for easy sound playing
extension GameControllerSounds on GameSound {
  String getDisplayName() {
    switch (this) {
      case GameSound.diceRoll:
        return 'Dice Roll';
      case GameSound.tokenMove:
        return 'Token Move';
      case GameSound.tokenKill:
        return 'Token Kill';
      case GameSound.playerWin:
        return 'Player Win';
      case GameSound.gameOver:
        return 'Game Over';
      case GameSound.buttonTap:
        return 'Button Tap';
    }
  }
}

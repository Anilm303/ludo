// Ludo Board Painter - Square Bases and Winning Home Slots Version
import 'package:flutter/material.dart';
import 'dart:math';
import '../models/ludo_models.dart';

enum BoardStyle { modern, sketchy }

/// Defines the 4 selectable board color themes.
class LudoBoardTheme {
  final Color red;
  final Color green;
  final Color yellow;
  final Color blue;
  final Color boardBg;
  final Color pathBg;
  final BoardStyle style;

  const LudoBoardTheme({
    required this.red,
    required this.green,
    required this.yellow,
    required this.blue,
    required this.boardBg,
    required this.pathBg,
    this.style = BoardStyle.modern,
  });

  static const List<LudoBoardTheme> themes = [
    // Board 1: Sketchy + Wood
    LudoBoardTheme(
      red: Color(0xFFE24E44),
      green: Color(0xFF86D63B),
      yellow: Color(0xFFFFC233),
      blue: Color(0xFF3B73F2),
      boardBg: Color(0xFFDEB887), // BurlyWood
      pathBg: Color(0xFFF5F5DC),
      style: BoardStyle.sketchy,
    ),
    // Board 2: Sketchy + White
    LudoBoardTheme(
      red: Color(0xFFE24E44),
      green: Color(0xFF86D63B),
      yellow: Color(0xFFFFC233),
      blue: Color(0xFF3B73F2),
      boardBg: Colors.white,
      pathBg: Color(0xFFFAFAFA),
      style: BoardStyle.sketchy,
    ),
    // Board 3: Modern + White
    LudoBoardTheme(
      red: Color(0xFFE24E44),
      green: Color(0xFF86D63B),
      yellow: Color(0xFFFFC233),
      blue: Color(0xFF3B73F2),
      boardBg: Colors.white,
      pathBg: Color(0xFFF5F5F5),
      style: BoardStyle.modern,
    ),
    // Board 4: Modern + Wood
    LudoBoardTheme(
      red: Color(0xFFE24E44),
      green: Color(0xFF86D63B),
      yellow: Color(0xFFFFC233),
      blue: Color(0xFF3B73F2),
      boardBg: Color(0xFFE4D5B7),
      pathBg: Color(0xFFFDF8F0),
      style: BoardStyle.modern,
    ),
  ];
}

class LudoBoardPainter extends CustomPainter {
  final GameState gameState;
  final double boardSize;
  final Map<String, dynamic>? lastMove;
  final bool showSafeCells;
  final int boardIndex;
  final double turnHighlight;
  final String? movingPlayerId;
  final int? movingTokenId;

  LudoBoardPainter({
    required this.gameState,
    this.boardSize = 400,
    this.lastMove,
    this.showSafeCells = true,
    this.boardIndex = 0,
    this.turnHighlight = 0.0,
    this.movingPlayerId,
    this.movingTokenId,
  });

  LudoBoardTheme get _theme => LudoBoardTheme.themes[boardIndex % LudoBoardTheme.themes.length];

  static const List<Offset> _pathCoords = [
    Offset(6, 13), Offset(6, 12), Offset(6, 11), Offset(6, 10), Offset(6, 9),
    Offset(5, 8), Offset(4, 8), Offset(3, 8), Offset(2, 8), Offset(1, 8), Offset(0, 8),
    Offset(0, 7), Offset(0, 6), Offset(1, 6), Offset(2, 6), Offset(3, 6), Offset(4, 6), Offset(5, 6),
    Offset(6, 5), Offset(6, 4), Offset(6, 3), Offset(6, 2), Offset(6, 1), Offset(6, 0),
    Offset(7, 0), Offset(8, 0), Offset(8, 1), Offset(8, 2), Offset(8, 3), Offset(8, 4), Offset(8, 5),
    Offset(9, 6), Offset(10, 6), Offset(11, 6), Offset(12, 6), Offset(13, 6), Offset(14, 6),
    Offset(14, 7), Offset(14, 8), Offset(13, 8), Offset(12, 8), Offset(11, 8), Offset(10, 8), Offset(9, 8),
    Offset(8, 9), Offset(8, 10), Offset(8, 11), Offset(8, 12), Offset(8, 13), Offset(8, 14),
    Offset(7, 14), Offset(6, 14),
  ];

  @override
  void paint(Canvas canvas, Size size) {
    final double actualSize = min(size.width, size.height);
    final double cellSize = actualSize / 15;
    canvas.save();
    if (size.width > actualSize) canvas.translate((size.width - actualSize) / 2, 0);
    if (size.height > actualSize) canvas.translate(0, (size.height - actualSize) / 2);
    _drawBoard(canvas, cellSize);
    _drawTokens(canvas, cellSize);
    canvas.restore();
  }

  void _drawBoard(Canvas canvas, double cellSize) {
    final boardRect = Rect.fromLTWH(0, 0, 15 * cellSize, 15 * cellSize);
    canvas.drawRect(boardRect, Paint()..color = _theme.boardBg);

    // Subtle Wood Grain Effect for Wood Themes
    if (_theme.boardBg == const Color(0xFFDEB887) || _theme.boardBg == const Color(0xFFE4D5B7)) {
      final woodPaint = Paint()
        ..color = Colors.black.withOpacity(0.05)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.0;
      final rand = Random(42);
      for (int i = 0; i < 40; i++) {
        final y = rand.nextDouble() * 15 * cellSize;
        final path = Path()..moveTo(0, y);
        for (double x = 0; x < 15 * cellSize; x += 20) {
          path.lineTo(x, y + rand.nextDouble() * 10 - 5);
        }
        canvas.drawPath(path, woodPaint);
      }
    }

    final linePaint = Paint()..color = Colors.black.withOpacity(0.8)..style = PaintingStyle.stroke..strokeWidth = 1.2;
    for (int x = 0; x < 15; x++) {
      for (int y = 0; y < 15; y++) {
        if ((x < 6 && y < 6) || (x > 8 && y < 6) || (x < 6 && y > 8) || (x > 8 && y > 8)) continue;
        if (x >= 6 && x <= 8 && y >= 6 && y <= 8) continue;
        canvas.drawRect(Rect.fromLTWH(x * cellSize, y * cellSize, cellSize, cellSize), linePaint);
      }
    }

    _colorSpecialCells(canvas, cellSize);
    _drawHomeBase(canvas, cellSize, 0, 0, PlayerColor.yellow); // TL: Yellow
    _drawHomeBase(canvas, cellSize, 9, 0, PlayerColor.green);  // TR: Green
    _drawHomeBase(canvas, cellSize, 0, 9, PlayerColor.blue);   // BL: Blue
    _drawHomeBase(canvas, cellSize, 9, 9, PlayerColor.red);    // BR: Red
    
    _drawHomeLockIcons(canvas, cellSize);
    _drawCenter(canvas, cellSize);
  }

  void _drawHomeLockIcons(Canvas canvas, double cellSize) {
    // Only show icons if the rule "Must cut a coin to enter home lane" is ON
    // We check BOTH the rule and that the player hasn't captured yet
    if (!gameState.rules.mustCaptureToEnterHome) return;

    void drawLock(Offset pos, bool isLocked) {
      if (!isLocked) return; 
      
      final center = (pos + const Offset(0.5, 0.5)) * cellSize;
      final radius = cellSize * 0.45;
      
      // Draw background circle
      canvas.drawCircle(center, radius, Paint()..color = Colors.white.withOpacity(0.9));
      canvas.drawCircle(center, radius, Paint()..color = Colors.black..style = PaintingStyle.stroke..strokeWidth = 1.0);
      
      const icon = Icons.lock;
      final textPainter = TextPainter(
        text: TextSpan(
          text: String.fromCharCode(icon.codePoint),
          style: TextStyle(
            fontSize: radius * 1.4,
            fontFamily: icon.fontFamily,
            package: icon.fontPackage,
            color: Colors.red,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      
      textPainter.paint(canvas, center - Offset(textPainter.width / 2, textPainter.height / 2));
    }

    for (final player in gameState.players) {
      // Icon only shows if:
      // 1. Rule is ON (checked above)
      // 2. Player has NOT captured (hasCaptured is false)
      if (player.hasCaptured) continue;

      Offset entryPos;
      switch (player.color) {
        case PlayerColor.yellow: entryPos = const Offset(1, 7); break;
        case PlayerColor.green: entryPos = const Offset(7, 1); break;
        case PlayerColor.red: entryPos = const Offset(13, 7); break;
        case PlayerColor.blue: entryPos = const Offset(7, 13); break;
      }
      drawLock(entryPos, true);
    }
  }

  void _drawHomeBase(Canvas canvas, double cellSize, int col, int row, PlayerColor pColor) {
    final Color color = _getPlayerColor(pColor);
    final rect = Rect.fromLTWH(col * cellSize, row * cellSize, 6 * cellSize, 6 * cellSize);
    
    // Highlight base if it's player's turn (Using clock-wise blink from LudoGameScreen)
    bool isTurn = false;
    try {
      isTurn = gameState.players.firstWhere((p) => p.color == pColor).isCurrentTurn;
    } catch (_) {}

    if (isTurn) {
      // 1. Strong Outer Glow (using player color for richness)
      final double glowRadius = (boardSize < 150 ? 2.0 : 5.0) + (boardSize < 150 ? 4.0 : 10.0) * turnHighlight;
      canvas.drawRect(
        rect.inflate(glowRadius),
        Paint()
          ..color = color.withOpacity(0.5 * turnHighlight)
          ..maskFilter = MaskFilter.blur(BlurStyle.normal, boardSize < 150 ? 6 : 12),
      );
    }

    // Base Shadow
    if (_theme.style == BoardStyle.modern) {
      canvas.drawRect(rect.shift(Offset(0, boardSize < 150 ? 1 : 3)), Paint()..color = Colors.black26..maskFilter = MaskFilter.blur(BlurStyle.normal, boardSize < 150 ? 2 : 4));
    }
    
    // Base Main Color
    if (_theme.style == BoardStyle.sketchy) {
      _drawSketchyRect(canvas, rect, Paint()..color = color);
    } else {
      canvas.drawRect(rect, Paint()..color = color);
    }
    
    if (isTurn) {
      // 2. Inner "Flash" Overlay (White)
      canvas.drawRect(
        rect,
        Paint()..color = Colors.white.withOpacity(0.25 * turnHighlight),
      );
    }

    if (_theme.style == BoardStyle.sketchy) {
      _drawSketchyRect(canvas, rect, Paint()..color = Colors.black87..style = PaintingStyle.stroke..strokeWidth = 2.0);
    } else {
      canvas.drawRect(rect, Paint()..color = Colors.black87..style = PaintingStyle.stroke..strokeWidth = 2.0);
    }

    if (isTurn) {
      // 3. Bright Pulsing Border on Top
      canvas.drawRect(
        rect,
        Paint()
          ..color = Colors.white.withOpacity(0.5 + 0.5 * turnHighlight)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 3.0 + 3.0 * turnHighlight,
      );
    }

    final innerRect = Rect.fromLTWH((col + 0.6) * cellSize, (row + 0.8) * cellSize, 4.8 * cellSize, 4.4 * cellSize);
    
    if (_theme.style == BoardStyle.sketchy) {
      _drawSketchyRect(canvas, innerRect, Paint()..color = Colors.white.withOpacity(0.8));
    } else {
      canvas.drawRect(innerRect, Paint()..color = Colors.white);
    }
    canvas.drawRect(innerRect, Paint()..color = Colors.black12..style = PaintingStyle.stroke..strokeWidth = 1.0);

    for (int i = 0; i < 4; i++) {
      final dx = (i % 2 == 0) ? 1.5 : 3.5;
      final dy = (i < 2) ? 1.8 : 3.8;
      final center = Offset((col + dx + 0.5) * cellSize, (row + dy + 0.5) * cellSize);
      
      if (_theme.style == BoardStyle.sketchy) {
        _drawSketchyCircle(canvas, center, cellSize * 0.72, Paint()..color = color);
        _drawSketchyCircle(canvas, center, cellSize * 0.48, Paint()..color = Colors.white);
      } else {
        canvas.drawCircle(center, cellSize * 0.72, Paint()..color = color);
        canvas.drawCircle(center, cellSize * 0.48, Paint()..color = Colors.white);
      }
    }
    
    Player? p;
    try { p = gameState.players.firstWhere((element) => element.color == pColor); } catch (_) {}
    if (p != null) {
      // Calculate real progress percentage
      double progress = 0;
      int totalSteps = 0;
      final int startPos = BoardConfig.playerStartPositions[pColor] ?? 0;
      
      for (var t in p.tokens) {
        if (t.position == -1) {
          totalSteps += 0;
        } else if (t.position >= 52) {
          totalSteps += t.position; // 52 to 57 steps
        } else {
          totalSteps += (t.position - startPos + 52) % 52;
        }
      }
      // Max possible steps = 4 tokens * 57 steps = 228
      progress = (totalSteps / 228.0) * 100;
      
      _drawText(canvas, rect.center.dx, rect.top + cellSize * 0.15, "${progress.toStringAsFixed(1)}%", cellSize * 0.55);
      final String name = p.type == PlayerType.ai ? 'Computer ${p.id.split('_').last}' : p.name;
      _drawText(canvas, rect.center.dx, rect.bottom - cellSize * 0.85, name, cellSize * 0.75);
    }
  }

  void _drawSketchyRect(Canvas canvas, Rect rect, Paint paint) {
    if (paint.style == PaintingStyle.fill) {
      // Draw hatching for fill
      final hatchPaint = Paint()
        ..color = paint.color.withOpacity(0.6)
        ..strokeWidth = 1.0
        ..style = PaintingStyle.stroke;
      
      for (double i = rect.left; i < rect.right; i += 4) {
        canvas.drawLine(Offset(i, rect.top), Offset(i + 4, rect.bottom), hatchPaint);
      }
      canvas.drawRect(rect, Paint()..color = paint.color.withOpacity(0.3));
    } else {
      // Draw multiple slightly offset rectangles for sketchy look
      for (int i = 0; i < 2; i++) {
        final offset = i * 0.5;
        canvas.drawRect(rect.inflate(offset), paint);
      }
    }
  }

  void _drawSketchyCircle(Canvas canvas, Offset center, double radius, Paint paint) {
    if (paint.style == PaintingStyle.fill) {
      // Draw sketchy fill with spirals/hatching
      final hatchPaint = Paint()
        ..color = paint.color.withOpacity(0.6)
        ..strokeWidth = 1.0
        ..style = PaintingStyle.stroke;
      
      for (double r = 2; r < radius; r += 4) {
        canvas.drawCircle(center, r, hatchPaint);
      }
      canvas.drawCircle(center, radius, Paint()..color = paint.color.withOpacity(0.3));
    } else {
      // Draw multiple slightly offset circles
      for (int i = 0; i < 2; i++) {
        canvas.drawCircle(center + Offset(i * 0.5, i * 0.2), radius + (i * 0.2), paint);
      }
    }
  }

  void _drawText(Canvas canvas, double x, double y, String text, double size) {
    if (boardSize < 150 && text.length > 5) return; // Hide long names on mini preview
    final p = TextPainter(text: TextSpan(text: text, style: TextStyle(color: Colors.white, fontWeight: FontWeight.w900, fontSize: size)), textDirection: TextDirection.ltr)..layout();
    p.paint(canvas, Offset(x - p.width / 2, y));
  }

  void _colorSpecialCells(Canvas canvas, double cellSize) {
    void paint(Offset c, Color clr, {bool isStar = false}) {
      final r = Rect.fromLTWH(c.dx * cellSize, c.dy * cellSize, cellSize, cellSize);
      canvas.drawRect(r, Paint()..color = clr);
      canvas.drawRect(r, Paint()..color = Colors.black.withOpacity(0.8)..style = PaintingStyle.stroke);
      if (isStar) _drawStarIcon(canvas, r.center, cellSize * 0.35);
    }
    BoardConfig.playerStartPositions.forEach((color, startIdx) {
      paint(gridCoordinateForToken(Token(id: 0, playerColor: color, position: startIdx)), _getPlayerColor(color), isStar: true);
    });
    if (showSafeCells) {
      final stars = [Offset(2, 8), Offset(6, 2), Offset(12, 6), Offset(8, 12)];
      for (final s in stars) paint(s, Colors.transparent, isStar: true);
    }
    for (final color in PlayerColor.values) {
      for (int step = 1; step <= 5; step++) {
        final coord = gridCoordinateForToken(Token(id: 0, playerColor: color, position: 51 + step));
        final rect = Rect.fromLTWH(coord.dx * cellSize, coord.dy * cellSize, cellSize, cellSize);
        
        // Home stretch cells (the path to the center) should be SOLID COLOR
        canvas.drawRect(rect, Paint()..color = _getPlayerColor(color));
        
        // Draw cell border
        canvas.drawRect(rect, Paint()..color = Colors.black.withOpacity(0.8)..style = PaintingStyle.stroke..strokeWidth = 1.0);
      }
    }
    _drawHomeStartLines(canvas, cellSize);
  }

  void _drawHomeStartLines(Canvas canvas, double cellSize) {
    // This draws the line at the very beginning of the home stretch
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;

    void drawLine(Offset start, Offset end, Color color) {
      paint.color = color;
      canvas.drawLine(start * cellSize, end * cellSize, paint);
    }

    // Drawing a start line for each player's home entry
    drawLine(const Offset(6, 7), const Offset(6, 8), _getPlayerColor(PlayerColor.green));
    drawLine(const Offset(7, 6), const Offset(8, 6), _getPlayerColor(PlayerColor.red));
    drawLine(const Offset(9, 7), const Offset(9, 8), _getPlayerColor(PlayerColor.yellow));
    drawLine(const Offset(7, 9), const Offset(8, 9), _getPlayerColor(PlayerColor.blue));
    
    _drawHomeLockIcons(canvas, cellSize);
  }

  void _drawStarIcon(Canvas canvas, Offset center, double size) {
    canvas.drawCircle(center, size * 1.3, Paint()..color = const Color(0xFFE4D2A0));
    final path = Path();
    for (int i = 0; i < 5; i++) {
      final a = (i * 144 - 90) * (pi / 180);
      final p = Offset(center.dx + size * cos(a), center.dy + size * sin(a));
      if (i == 0) path.moveTo(p.dx, p.dy); else path.lineTo(p.dx, p.dy);
    }
    path.close();
    canvas.drawPath(path, Paint()..color = Colors.white);
    canvas.drawPath(path, Paint()..color = Colors.black45..style = PaintingStyle.stroke);
  }

  void _drawCenter(Canvas canvas, double cellSize) {
    final c = Offset(7.5 * cellSize, 7.5 * cellSize);
    final s = 6 * cellSize, e = 9 * cellSize;
    final strokeP = Paint()..color = Colors.black87..style = PaintingStyle.stroke..strokeWidth = 1.5;

    void tri(List<Offset> pts, Color clr, PlayerColor pc) {
      final p = Path()..moveTo(pts[0].dx, pts[0].dy)..lineTo(pts[1].dx, pts[1].dy)..lineTo(pts[2].dx, pts[2].dy)..close();
      canvas.drawPath(p, Paint()..color = clr);
      canvas.drawPath(p, strokeP);
      
      // Draw Win Home circle slot for each triangle (Final mapping matching buttons)
      Offset slot;
      switch(pc) {
        case PlayerColor.yellow: // Left triangle
          slot = Offset(6.8 * cellSize, 7.5 * cellSize); 
          break;
        case PlayerColor.green: // Top triangle
          slot = Offset(7.5 * cellSize, 6.8 * cellSize); 
          break;
        case PlayerColor.blue: // Bottom triangle
          slot = Offset(7.5 * cellSize, 8.2 * cellSize); 
          break;
        case PlayerColor.red: // Right triangle
          slot = Offset(8.2 * cellSize, 7.5 * cellSize); 
          break;
      }
      // Drawing white circle with border for better visibility in center
      canvas.drawCircle(slot, cellSize * 0.38, Paint()..color = Colors.white.withOpacity(0.3));
      canvas.drawCircle(slot, cellSize * 0.38, Paint()..color = Colors.black.withOpacity(0.4)..style = PaintingStyle.stroke..strokeWidth = 1.5);
    }

    tri([Offset(s,s), c, Offset(s,e)], _getPlayerColor(PlayerColor.yellow), PlayerColor.yellow); // Left
    tri([Offset(s,s), Offset(e,s), c], _getPlayerColor(PlayerColor.green), PlayerColor.green);   // Top
    tri([c, Offset(e,e), Offset(s,e)], _getPlayerColor(PlayerColor.blue), PlayerColor.blue);    // Bottom
    tri([Offset(e,s), Offset(e,e), c], _getPlayerColor(PlayerColor.red), PlayerColor.red);      // Right
  }

  static Offset gridCoordinateForToken(Token token) {
    if (token.position == -1) {
      double bx=0, by=0;
      switch(token.playerColor){
        case PlayerColor.yellow:bx=0;by=0;break; // Top Left
        case PlayerColor.green:bx=9;by=0;break;  // Top Right
        case PlayerColor.blue:bx=0;by=9;break;   // Bottom Left
        case PlayerColor.red:bx=9;by=9;break;    // Bottom Right
      }
      return Offset(bx + (token.id%2==0?1.5:3.5), by + (token.id<2?1.8:3.8));
    } else if (token.position == 57) {
      // Coordinates for winning center slots (Final matching buttons UI)
      switch(token.playerColor) {
        case PlayerColor.yellow: return Offset(6.3, 7.0);
        case PlayerColor.green: return Offset(7.0, 6.3);
        case PlayerColor.blue: return Offset(7.0, 7.7);
        case PlayerColor.red: return Offset(7.7, 7.0);
      }
    } else if (token.position >= 52) {
      int st = token.position - 51;
      switch(token.playerColor){
        case PlayerColor.yellow:return Offset(0.0+st, 7);
        case PlayerColor.green:return Offset(7, 0.0+st);
        case PlayerColor.red:return Offset(14.0-st, 7);
        case PlayerColor.blue:return Offset(7, 14.0-st);
      }
    }
    return _pathCoords[token.position];
  }

  Color _getPlayerColor(PlayerColor color) {
    switch (color) {
      case PlayerColor.red: return _theme.red;
      case PlayerColor.green: return _theme.green;
      case PlayerColor.yellow: return _theme.yellow;
      case PlayerColor.blue: return _theme.blue;
    }
  }

  void _drawTokens(Canvas canvas, double cellSize) {
    // Group tokens by their position to handle multiple tokens in one cell
    final Map<int, List<Token>> groupedTokens = {};
    for (final player in gameState.players) {
      for (final token in player.tokens) {
        if (player.id == movingPlayerId && token.id == movingTokenId) continue;
        if (token.position == -1) {
          // Home base tokens are drawn separately in _drawHomeBase logic 
          // or we can handle them here by using a unique key for each base.
          // For now, let's only group tokens that are on the board (pos >= 0).
          final coord = gridCoordinateForToken(token);
          _drawToken(canvas, cellSize, token, coord);
          continue;
        }
        groupedTokens.putIfAbsent(token.position, () => []).add(token);
      }
    }

    // Draw grouped tokens
    groupedTokens.forEach((position, tokens) {
      final baseCoord = gridCoordinateForToken(tokens.first);
      
      if (tokens.length == 1) {
        _drawToken(canvas, cellSize, tokens.first, baseCoord);
      } else {
        // Multiple tokens in one cell (like stars or safe zones)
        // Spread them out slightly so all are visible
        for (int i = 0; i < tokens.length; i++) {
          final double angle = (2 * pi * i) / tokens.length;
          final double offsetDist = cellSize * 0.22;
          final offset = Offset(cos(angle) * offsetDist, sin(angle) * offsetDist);
          
          final pos = Offset(
            (baseCoord.dx + 0.5) * cellSize + offset.dx,
            (baseCoord.dy + 0.5) * cellSize + offset.dy,
          );
          
          // Draw smaller tokens when grouped
          _drawSingleToken(canvas, cellSize * 0.75, tokens[i], pos);
        }
      }
    });
  }

  void _drawToken(Canvas canvas, double cellSize, Token token, Offset gridCoord) {
    final pos = Offset((gridCoord.dx + 0.5) * cellSize, (gridCoord.dy + 0.5) * cellSize);
    _drawSingleToken(canvas, cellSize, token, pos);
  }

  void _drawSingleToken(Canvas canvas, double cellSize, Token token, Offset pos) {
    final r = cellSize * 0.42;
    canvas.drawCircle(pos + const Offset(1, 2), r, Paint()..color = Colors.black26..maskFilter = const MaskFilter.blur(BlurStyle.normal, 2));
    canvas.drawCircle(pos, r, Paint()..color = _getPlayerColor(token.playerColor));
    canvas.drawCircle(pos, r, Paint()..color = Colors.black87..style = PaintingStyle.stroke..strokeWidth = 1.2);
    canvas.drawCircle(pos, r * 0.7, Paint()..color = Colors.white..style = PaintingStyle.stroke..strokeWidth = 2);
    canvas.drawCircle(pos, r * 0.35, Paint()..color = _getPlayerColor(token.playerColor));
    
    // Numbers removed as per user request for a cleaner look
  }

  @override bool shouldRepaint(LudoBoardPainter old) => true;
}

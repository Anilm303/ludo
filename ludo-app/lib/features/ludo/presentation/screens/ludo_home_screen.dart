// Ludo Home Screen - Main Menu
import 'package:flutter/material.dart';
import '../../../../models/ludo_models.dart';
import 'package:provider/provider.dart';
import '../../../../providers/game_provider.dart';
import '../screens/ludo_game_screen.dart';
import '../screens/ludo_lobby_screen.dart';
import '../../../../widgets/cancel_match_button.dart';
import '../../../../widgets/ludo_painters.dart';

enum _PlayerSlotType { none, human, computer }

class LudoHomeScreen extends StatefulWidget {
  const LudoHomeScreen({Key? key}) : super(key: key);

  @override
  State<LudoHomeScreen> createState() => _LudoHomeScreenState();
}

class _LudoHomeScreenState extends State<LudoHomeScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  bool _navigating = false;
  final List<PlayerColor> _slotColors = const [
    PlayerColor.yellow, // Top Left (matching board image)
    PlayerColor.green,  // Top Right
    PlayerColor.blue,   // Bottom Left
    PlayerColor.red,    // Bottom Right
  ];
  late List<_PlayerSlotType> _playerSlots;
  late List<String> _playerNames;
  LudoRuleSettings _rules = const LudoRuleSettings();
  int _selectedBoardIndex = 0;
  int _selectedCoins = 4;
  bool _continuousRolling = false;
  bool _diceRollingFling = true;
  DifficultyLevel _difficulty = DifficultyLevel.hard;
  double _moveSpeed = 0.82;

  @override
  void initState() {
    super.initState();
    _playerSlots = [
      _PlayerSlotType.human,
      _PlayerSlotType.none,
      _PlayerSlotType.computer,
      _PlayerSlotType.none,
    ];
    _playerNames = ['Player 1', 'Player 2', 'Player 3', 'Player 4'];
    _animationController = AnimationController(
      duration: const Duration(seconds: 2),
      vsync: this,
    )..repeat();
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Consumer<GameProvider>(
        builder: (context, gp, child) {
          // if matchmaking produced a room, navigate to game screen once
          if (gp.matchedRoom != null && !_navigating) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              _navigating = true;
              try {
                // extract players if provided, otherwise navigate with empty list
                final data = gp.matchedRoom as Map<String, dynamic>;
                final playersData = data['players'] as List<dynamic>?;
                List<Player> players = [];
                if (playersData != null) {
                  players = playersData.map((p) {
                    return Player(
                      id: p['id'] ?? p['playerId'] ?? UniqueKey().toString(),
                      name: p['name'] ?? 'Player',
                      color: PlayerColor.values[
                          (p['colorIndex'] ?? 0) % PlayerColor.values.length],
                      type: PlayerType.human,
                      tokenCount: _selectedCoins,
                    );
                  }).toList();
                }

                Navigator.pushReplacement(
                  context,
                  MaterialPageRoute(
                    builder: (context) => LudoGameScreen(
                      players: players,
                      gameMode: GameMode.online,
                      ruleSettings: _rules,
                      initialDiceFling: _diceRollingFling,
                      boardIndex: _selectedBoardIndex,
                      continuousRolling: _continuousRolling,
                      moveSpeed: _moveSpeed,
                    ),
                  ),
                );
              } catch (e) {
                // fallback: open empty online game screen
                Navigator.pushReplacement(
                  context,
                  MaterialPageRoute(
                    builder: (context) => LudoGameScreen(
                      players: [],
                      gameMode: GameMode.online,
                      ruleSettings: _rules,
                      initialDiceFling: _diceRollingFling,
                      boardIndex: _selectedBoardIndex,
                      continuousRolling: _continuousRolling,
                      moveSpeed: _moveSpeed,
                    ),
                  ),
                );
              }
            });
          }

          final children = <Widget>[
            Container(
              color: Colors.white,
              child: SafeArea(
                child: SingleChildScrollView(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(12, 10, 12, 18),
                    child: Center(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 400),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            _buildHeader(context),
                            const SizedBox(height: 10),
                            _buildSetupPanel(),
                            const SizedBox(height: 16),
                            _buildPrimaryActions(context),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ];

          if (gp.isSearchingMatch) {
            children.add(
              Positioned.fill(
                child: Container(
                  color: Colors.black45,
                  child: Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const CircularProgressIndicator(),
                        const SizedBox(height: 12),
                        const Text(
                          'Searching for match...',
                          style: TextStyle(color: Colors.white),
                        ),
                        const SizedBox(height: 12),
                        CancelMatchButton(),
                      ],
                    ),
                  ),
                ),
              ),
            );
          }

          return Stack(children: children);
        },
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        const SizedBox(width: 48), // Spacer to center logo
        Expanded(
          child: Column(
            children: [
              RichText(
                text: const TextSpan(
                  children: [
                    TextSpan(
                      text: 'L',
                      style: TextStyle(color: Color(0xFFE24E44)),
                    ),
                    TextSpan(
                      text: 'U',
                      style: TextStyle(color: Color(0xFF86D63B)),
                    ),
                    TextSpan(
                      text: 'D',
                      style: TextStyle(color: Color(0xFF3B73F2)),
                    ),
                    TextSpan(
                      text: 'O',
                      style: TextStyle(color: Color(0xFFFFC233)),
                    ),
                  ],
                  style: TextStyle(
                    fontSize: 48,
                    fontWeight: FontWeight.w900,
                    letterSpacing: -2,
                    fontFamily: 'Roboto', // Or similar bold font
                  ),
                ),
              ),
              const Text(
                'Neo-Classic',
                style: TextStyle(
                  color: Colors.black,
                  fontSize: 12,
                  fontWeight: FontWeight.w900,
                  height: 0.8,
                ),
              ),
            ],
          ),
        ),
        Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            color: const Color(0xFFFFC233),
            shape: BoxShape.circle,
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.2),
                blurRadius: 4,
                offset: const Offset(0, 2),
              ),
            ],
            border: Border.all(color: Colors.white, width: 2),
          ),
          child: IconButton(
            onPressed: () => _showSettings(context),
            icon: const Icon(Icons.settings, color: Colors.white, size: 24),
            padding: EdgeInsets.zero,
          ),
        ),
      ],
    );
  }

  Widget _buildSetupPanel() {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: const Color(0xFFFFC233), width: 2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Select Players Section
                Expanded(
                  flex: 3,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _sectionHeader('Select Players:'),
                      const SizedBox(height: 8),
                      Stack(
                        alignment: Alignment.center,
                        children: [
                          Column(
                            children: [
                              Row(
                                children: [
                                  Expanded(child: _buildPlayerSlotCard(0)),
                                  const SizedBox(width: 4),
                                  Expanded(child: _buildPlayerSlotCard(1)),
                                ],
                              ),
                              const SizedBox(height: 4),
                              Row(
                                children: [
                                  Expanded(child: _buildPlayerSlotCard(2)),
                                  const SizedBox(width: 4),
                                  Expanded(child: _buildPlayerSlotCard(3)),
                                ],
                              ),
                            ],
                          ),
                          GestureDetector(
                            onTap: _showAllHumanNamesEditDialog,
                            child: Container(
                              padding: const EdgeInsets.all(4),
                              decoration: BoxDecoration(
                                color: const Color(0xFFFFC233),
                                shape: BoxShape.circle,
                                border: Border.all(color: Colors.white, width: 2),
                                boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 4)],
                              ),
                              child: const Icon(Icons.edit, color: Colors.white, size: 16),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                // Select Board Section
                Expanded(
                  flex: 2,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _sectionHeader('Select Board:'),
                      const SizedBox(height: 8),
                      _buildBoardPreviewForHomeMini(),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const Divider(color: Color(0xFFFFC233), thickness: 2, height: 2),
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _sectionHeader('Options:'),
                const SizedBox(height: 10),
                _buildOptionRow(),
                const SizedBox(height: 12),
                _buildSpeedRow(),
              ],
            ),
          ),
          const Divider(color: Color(0xFFFFC233), thickness: 2, height: 2),
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _sectionHeader('Game Rules:'),
                const SizedBox(height: 8),
                _buildStartCoinsRow(),
                _buildRuleRow(
                  '1 also gives another turn',
                  _rules.extraTurnOnOne,
                  onTap: () => _setRules(
                    _rules.copyWith(extraTurnOnOne: !_rules.extraTurnOnOne),
                  ),
                ),
                _buildRuleRow(
                  '6 also gives another turn',
                  _rules.extraTurnOnSix,
                  onTap: () => _setRules(
                    _rules.copyWith(extraTurnOnSix: !_rules.extraTurnOnSix),
                  ),
                ),
                _buildRuleRow(
                  '6 also brings a coin out',
                  _rules.openTokenOnSix,
                  onTap: () => _setRules(
                    _rules.copyWith(openTokenOnSix: !_rules.openTokenOnSix),
                  ),
                ),
                _buildRuleRow(
                  'Show safe cells (stars)',
                  _rules.showSafeCells,
                  onTap: () => _setRules(
                    _rules.copyWith(showSafeCells: !_rules.showSafeCells),
                  ),
                ),
                _buildRuleRow(
                  '3 consecutive rolls of 1 cuts one own coin',
                  _rules.threeConsecutiveOnesCutOwnCoin,
                  onTap: () => _setRules(
                    _rules.copyWith(
                      threeConsecutiveOnesCutOwnCoin:
                          !_rules.threeConsecutiveOnesCutOwnCoin,
                    ),
                  ),
                ),
                _buildRuleRow(
                  'Skip a turn on 3 consecutive rolls of 1',
                  _rules.skipTurnAfterThreeOnes,
                  onTap: () => _setRules(
                    _rules.copyWith(
                      skipTurnAfterThreeOnes: !_rules.skipTurnAfterThreeOnes,
                    ),
                  ),
                ),
                _buildRuleRow(
                  '3 consecutive rolls of 6 brings a coin out',
                  _rules.threeConsecutiveSixesBringCoinOut,
                  onTap: () => _setRules(
                    _rules.copyWith(
                      threeConsecutiveSixesBringCoinOut:
                          !_rules.threeConsecutiveSixesBringCoinOut,
                    ),
                  ),
                ),
                _buildRuleRow(
                  'Gains another turn on cutting a coin',
                  _rules.extraTurnOnCapture,
                  onTap: () => _setRules(
                    _rules.copyWith(extraTurnOnCapture: !_rules.extraTurnOnCapture),
                  ),
                ),
                _buildRuleRow(
                  'Gains another turn on reaching home',
                  _rules.extraTurnOnHome,
                  onTap: () => _setRules(
                    _rules.copyWith(extraTurnOnHome: !_rules.extraTurnOnHome),
                  ),
                ),
                _buildRuleRow(
                  'Must cut a coin to enter home lane',
                  _rules.mustCaptureToEnterHome,
                  showHelp: true,
                  onTap: () => _setRules(
                    _rules.copyWith(mustCaptureToEnterHome: !_rules.mustCaptureToEnterHome),
                  ),
                ),
                _buildRuleRow(
                  'Must cut the coin if it\'s cuttable',
                  _rules.mustCutIfCuttable,
                  showHelp: true,
                  onTap: () => _setRules(
                    _rules.copyWith(mustCutIfCuttable: !_rules.mustCutIfCuttable),
                  ),
                ),
                _buildRuleRow(
                  'Must bring a coin out on 1',
                  _rules.openTokenOnOne,
                  showHelp: true,
                  onTap: () => _setRules(
                    _rules.copyWith(openTokenOnOne: !_rules.openTokenOnOne),
                  ),
                ),
                _buildRuleRow(
                  '2 coins of same colour form a barrier',
                  _rules.barrierEnabled,
                  showHelp: true,
                  onTap: () => _setRules(
                    _rules.copyWith(barrierEnabled: !_rules.barrierEnabled),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBoardPreviewForHome() {
    return SizedBox(
      height: 90, // Slightly taller for more detail
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        physics: const BouncingScrollPhysics(),
        itemCount: LudoBoardTheme.themes.length,
        itemBuilder: (context, index) {
          final isSelected = _selectedBoardIndex == index;
          final theme = LudoBoardTheme.themes[index];
          
          // Create a dummy game state for the painter to show base UI with current rules
          final dummyGameState = GameState(
            id: 'preview',
            players: [
              Player(id: '1', name: 'P1', color: PlayerColor.yellow),
              Player(id: '2', name: 'P2', color: PlayerColor.green),
              Player(id: '3', name: 'P3', color: PlayerColor.blue),
              Player(id: '4', name: 'P4', color: PlayerColor.red),
            ],
            createdAt: DateTime.now(),
            gameMode: GameMode.offline,
            rules: _rules,
          );

          return GestureDetector(
            onTap: () => setState(() => _selectedBoardIndex = index),
            child: Container(
              width: 90,
              margin: const EdgeInsets.only(right: 12),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(12),
                boxShadow: [
                  BoxShadow(
                    color: isSelected ? const Color(0xFFFFC233).withOpacity(0.4) : Colors.black.withOpacity(0.1),
                    blurRadius: isSelected ? 8 : 4,
                    offset: const Offset(0, 2),
                  )
                ],
              ),
              child: Stack(
                children: [
                  // Real Board Painter for Preview with Error Handling
                  ClipRRect(
                    borderRadius: BorderRadius.circular(12),
                    child: Container(
                      color: theme.boardBg,
                      child: IgnorePointer(
                        child: CustomPaint(
                          size: const Size(90, 90),
                          painter: LudoBoardPainter(
                            gameState: dummyGameState,
                            boardSize: 90,
                            boardIndex: index,
                          ),
                        ),
                      ),
                    ),
                  ),
                  
                  // Selection Overlay
                  if (isSelected)
                    Container(
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: const Color(0xFFFFC233), width: 3),
                        color: Colors.white.withOpacity(0.1),
                      ),
                    ),
                  
                  // Board Style Icon Overlay
                  Positioned(
                    top: 4,
                    right: 4,
                    child: Container(
                      padding: const EdgeInsets.all(3),
                      decoration: BoxDecoration(
                        color: isSelected ? const Color(0xFFFFC233) : Colors.black54,
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 1),
                      ),
                      child: Icon(
                        theme.style == BoardStyle.sketchy ? Icons.brush : Icons.grid_view,
                        color: Colors.white,
                        size: 10,
                      ),
                    ),
                  ),
                  
                  // Bottom Label
                  Positioned(
                    bottom: 0,
                    left: 0,
                    right: 0,
                    child: Container(
                      decoration: BoxDecoration(
                        color: isSelected ? const Color(0xFFFFC233) : Colors.black45,
                        borderRadius: const BorderRadius.only(
                          bottomLeft: Radius.circular(12),
                          bottomRight: Radius.circular(12),
                        ),
                      ),
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Text(
                        theme.style == BoardStyle.sketchy ? 'Sketchy' : 'Modern',
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 9,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildBoardPreviewForHomeMini() {
    final theme = LudoBoardTheme.themes[_selectedBoardIndex];
    final dummyGameState = GameState(
      id: 'preview',
      players: [
        Player(id: '1', name: 'P1', color: PlayerColor.yellow),
        Player(id: '2', name: 'P2', color: PlayerColor.green),
        Player(id: '3', name: 'P3', color: PlayerColor.blue),
        Player(id: '4', name: 'P4', color: PlayerColor.red),
      ],
      createdAt: DateTime.now(),
      gameMode: GameMode.offline,
      rules: _rules,
    );

    return GestureDetector(
      onTap: () {
        setState(() {
          _selectedBoardIndex = (_selectedBoardIndex + 1) % LudoBoardTheme.themes.length;
        });
      },
      child: Stack(
        children: [
          Container(
            height: 68,
            width: 68,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFFFFC233), width: 2),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: CustomPaint(
                painter: LudoBoardPainter(
                  gameState: dummyGameState,
                  boardSize: 64,
                  boardIndex: _selectedBoardIndex,
                ),
              ),
            ),
          ),
          Positioned(
            right: 0,
            bottom: 0,
            child: Container(
              padding: const EdgeInsets.all(2),
              decoration: const BoxDecoration(
                color: Colors.white,
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.touch_app, size: 16, color: Color(0xFFFFC233)),
            ),
          ),
        ],
      ),
    );
  }

  void _showAllHumanNamesEditDialog() {
    final List<int> humanIndices = [];
    for (int i = 0; i < _playerSlots.length; i++) {
      if (_playerSlots[i] == _PlayerSlotType.human) {
        humanIndices.add(i);
      }
    }

    if (humanIndices.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No human players to edit names')),
      );
      return;
    }

    final List<TextEditingController> controllers = humanIndices
        .map((idx) => TextEditingController(text: _playerNames[idx]))
        .toList();

    showDialog(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          title: const Text('Edit Human Player Names'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: List.generate(humanIndices.length, (i) {
                final idx = humanIndices[i];
                final color = _slotColors[idx];
                final colorName = color.toString().split('.').last;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: TextField(
                    controller: controllers[i],
                    decoration: InputDecoration(
                      labelText: '${colorName[0].toUpperCase()}${colorName.substring(1)} Player Name',
                      border: const OutlineInputBorder(),
                      prefixIcon: Icon(Icons.person, color: _getThemeColor(color)),
                    ),
                  ),
                );
              }),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () {
                setState(() {
                  for (int i = 0; i < humanIndices.length; i++) {
                    final newName = controllers[i].text.trim();
                    if (newName.isNotEmpty) {
                      _playerNames[humanIndices[i]] = newName;
                    }
                  }
                });
                Navigator.pop(ctx);
              },
              child: const Text('Save All'),
            ),
          ],
        );
      },
    );
  }

  Color _getThemeColor(PlayerColor color) {
    return switch (color) {
      PlayerColor.red => const Color(0xFFE24E44),
      PlayerColor.green => const Color(0xFF86D63B),
      PlayerColor.yellow => const Color(0xFFFFC233),
      PlayerColor.blue => const Color(0xFF3B73F2),
    };
  }

  void _showNameEditDialog(int index) {
    final controller = TextEditingController(text: _playerNames[index]);
    final colorName = _slotColors[index].toString().split('.').last;
    showDialog(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          title: Text('Edit ${colorName[0].toUpperCase()}${colorName.substring(1)} Player Name'),
          content: TextField(
            controller: controller,
            autofocus: true,
            decoration: const InputDecoration(
              hintText: 'Enter name',
              border: OutlineInputBorder(),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () {
                setState(() {
                  _playerNames[index] = controller.text.trim().isNotEmpty
                      ? controller.text.trim()
                      : 'Player ${index + 1}';
                });
                Navigator.pop(ctx);
              },
              child: const Text('Save'),
            ),
          ],
        );
      },
    );
  }

  Widget _buildPlayerSlotCard(int index) {
    final color = _slotColors[index];
    final slotType = _playerSlots[index];

    final fillColor = switch (color) {
      PlayerColor.red => const Color(0xFFE24E44),
      PlayerColor.green => const Color(0xFF86D63B),
      PlayerColor.yellow => const Color(0xFFFFC233),
      PlayerColor.blue => const Color(0xFF3B73F2),
    };

    final String typeLabel;
    switch (slotType) {
      case _PlayerSlotType.none:
        typeLabel = 'None';
        break;
      case _PlayerSlotType.human:
        typeLabel = 'Human ${index + 1}';
        break;
      case _PlayerSlotType.computer:
        typeLabel = 'Computer ${index + 1}';
        break;
    }

    return GestureDetector(
      onTap: () {
        setState(() {
          _playerSlots[index] = switch (slotType) {
            _PlayerSlotType.none => _PlayerSlotType.human,
            _PlayerSlotType.human => _PlayerSlotType.computer,
            _PlayerSlotType.computer => _PlayerSlotType.none,
          };
        });
      },
      child: Container(
        height: 32,
        decoration: BoxDecoration(
          color: fillColor,
          borderRadius: BorderRadius.circular(6),
          boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 2, offset: Offset(0, 2))],
        ),
        child: Center(
          child: Text(
            typeLabel,
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w900,
              fontSize: 14,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildBoardSelector() {
    return Row(
      children: List.generate(4, (index) {
        final theme = LudoBoardTheme.themes[index];
        final isSelected = _selectedBoardIndex == index;
        return Expanded(
          child: GestureDetector(
            onTap: () => setState(() => _selectedBoardIndex = index),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              curve: Curves.easeInOut,
              margin: EdgeInsets.only(right: index < 3 ? 6 : 0),
              padding: const EdgeInsets.all(3),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(10),
                border: Border.all(
                  color: isSelected ? const Color(0xFFFFC233) : Colors.transparent,
                  width: 2.5,
                ),
                boxShadow: isSelected
                    ? [const BoxShadow(color: Color(0x55FFC233), blurRadius: 8, spreadRadius: 1)]
                    : [],
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(7),
                child: AspectRatio(
                  aspectRatio: 1,
                  child: Column(
                    children: [
                      Expanded(
                        child: Row(
                          children: [
                            Expanded(child: Container(color: theme.green)),
                            Expanded(child: Container(color: theme.red)),
                          ],
                        ),
                      ),
                      Expanded(
                        child: Row(
                          children: [
                            Expanded(child: Container(color: theme.blue)),
                            Expanded(child: Container(color: theme.yellow)),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      }),
    );
  }

  Widget _buildBoardPreview() {
    return Container(
      width: 92,
      height: 92,
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFFFC233), width: 2),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(10),
        child: Column(
          children: [
            Expanded(
              child: Row(
                children: [
                  Expanded(child: Container(color: const Color(0xFFF0D63D))), // TL Yellow
                  Expanded(child: Container(color: const Color(0xFF59A95A))), // TR Green
                ],
              ),
            ),
            Expanded(
              child: Row(
                children: [
                  Expanded(child: Container(color: const Color(0xFF3B73F2))), // BL Blue
                  Expanded(child: Container(color: const Color(0xFFF1463A))), // BR Red
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildOptionRow() {
    return Column(
      children: [
        Row(
          children: [
            const Text('Coins:', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 13)),
            const SizedBox(width: 8),
            ...List.generate(4, (index) {
              final val = index + 1;
              final isSelected = _selectedCoins == val;
              return Padding(
                padding: const EdgeInsets.only(right: 6),
                child: GestureDetector(
                  onTap: () => setState(() => _selectedCoins = val),
                  child: Stack(
                    children: [
                      Container(
                        width: 22,
                        height: 22,
                        decoration: BoxDecoration(
                          color: const Color(0xFFFFC233),
                          shape: BoxShape.circle,
                          border: Border.all(color: Colors.black26),
                        ),
                        child: Center(
                          child: Text(
                            '$val',
                            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w900),
                          ),
                        ),
                      ),
                      if (isSelected)
                        Positioned(
                          right: -2,
                          bottom: -2,
                          child: Container(
                            decoration: const BoxDecoration(color: Color(0xFF86D63B), shape: BoxShape.circle),
                            child: const Icon(Icons.check, size: 10, color: Colors.white),
                          ),
                        ),
                    ],
                  ),
                ),
              );
            }),
            const Spacer(),
            const Text('Cont. Rolling:', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 13)),
            const SizedBox(width: 4),
            _buildClassicToggleButton(
              _continuousRolling ? 'On' : 'Off',
              onTap: () => setState(() => _continuousRolling = !_continuousRolling),
            ),
            const SizedBox(width: 4),
            const Icon(Icons.help_outline, color: Color(0xFFFFC233), size: 18),
          ],
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            const Text('Diff. Level:', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 13)),
            const SizedBox(width: 4),
            _buildClassicToggleButton(
              _difficulty.name[0].toUpperCase() + _difficulty.name.substring(1),
              onTap: () {
                setState(() {
                  _difficulty = switch (_difficulty) {
                    DifficultyLevel.easy => DifficultyLevel.medium,
                    DifficultyLevel.medium => DifficultyLevel.hard,
                    DifficultyLevel.hard => DifficultyLevel.easy,
                  };
                });
              },
            ),
            const Spacer(),
            const Text('Dice Rolling:', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 13)),
            const SizedBox(width: 4),
            _buildClassicToggleButton(
              _diceRollingFling ? 'Fling' : 'Tap',
              onTap: () => setState(() => _diceRollingFling = !_diceRollingFling),
            ),
            const SizedBox(width: 4),
            const Icon(Icons.help_outline, color: Color(0xFFFFC233), size: 18),
          ],
        ),
      ],
    );
  }

  Widget _buildClassicToggleButton(String label, {required VoidCallback onTap}) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: const Color(0xFF86D63B), width: 1.5),
        ),
        child: Text(
          label,
          style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 13),
        ),
      ),
    );
  }

  Widget _buildSpeedRow() {
    return Row(
      children: [
        const Text('Coin moving speed:', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 13)),
        Expanded(
          child: SliderTheme(
            data: SliderTheme.of(context).copyWith(
              trackHeight: 12,
              thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 10),
              overlayShape: const RoundSliderOverlayShape(overlayRadius: 16),
            ),
            child: Slider(
              value: _moveSpeed,
              min: 0.2,
              max: 1.0,
              activeColor: const Color(0xFF86D63B),
              inactiveColor: const Color(0xFFE0E0E0),
              onChanged: (value) => setState(() => _moveSpeed = value),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildRuleRow(
    String label,
    bool enabled, {
    required VoidCallback onTap,
    bool showHelp = false,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: const BoxDecoration(
          border: Border(bottom: BorderSide(color: Color(0xFFFFC233), width: 0.5)),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ),
            if (showHelp)
              Padding(
                padding: const EdgeInsets.only(right: 8),
                child: Container(
                  width: 20,
                  height: 20,
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFC233),
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white, width: 1),
                  ),
                  child: const Center(
                    child: Text(
                      '?',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ),
              ),
            GestureDetector(
              onTap: onTap,
              child: Container(
                width: 22,
                height: 22,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: enabled ? const Color(0xFF86D63B) : const Color(0xFFE24E44),
                  border: Border.all(color: Colors.white, width: 1),
                  boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 2)],
                ),
                child: Icon(
                  enabled ? Icons.check : Icons.close,
                  color: Colors.white,
                  size: 14,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStartCoinsRow() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: Row(
        children: [
          const Expanded(
            child: Text(
              'Start coins at:',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
          _buildStartCoinsIcon(
            isBase: false, // 1 icon
            isSelected: !_rules.startCoinsInBase,
            onTap: () => _setRules(_rules.copyWith(startCoinsInBase: false)),
          ),
          const SizedBox(width: 12),
          _buildStartCoinsIcon(
            isBase: true, // 6 icon
            isSelected: _rules.startCoinsInBase,
            onTap: () => _setRules(_rules.copyWith(startCoinsInBase: true)),
          ),
        ],
      ),
    );
  }

  Widget _buildStartCoinsIcon({
    required bool isBase,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: const Color(0xFF86D63B),
              borderRadius: BorderRadius.circular(6),
              border: Border.all(
                color: isSelected ? const Color(0xFFFFC233) : Colors.transparent,
                width: 2,
              ),
            ),
            child: Container(
              margin: const EdgeInsets.all(2),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(4),
              ),
              child: isBase
                  ? Column(
                      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                          children: [_buildCoinDot(5), _buildCoinDot(5)],
                        ),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                          children: [_buildCoinDot(5), _buildCoinDot(5)],
                        ),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                          children: [_buildCoinDot(5), _buildCoinDot(5)],
                        ),
                      ],
                    )
                  : Center(child: _buildCoinDot(12)),
            ),
          ),
          if (isSelected)
            Positioned(
              right: -4,
              bottom: -4,
              child: Container(
                decoration: const BoxDecoration(
                  color: Color(0xFF86D63B),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.check, color: Colors.white, size: 12),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildCoinDot(double size) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: Colors.white,
        shape: BoxShape.circle,
        border: Border.all(color: Colors.black26, width: 0.5),
      ),
      child: Center(
        child: Container(
          width: size * 0.5,
          height: size * 0.5,
          decoration: const BoxDecoration(
            color: Color(0xFFFFC233),
            shape: BoxShape.circle,
          ),
        ),
      ),
    );
  }

  Widget _buildPrimaryActions(BuildContext context) {
    final prov = context.watch<GameProvider>();
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (prov.hasSavedOfflineGame) ...[
            _classicActionButton(
              'Resume Game',
              const Color(0xFF2196F3),
              () {
                prov.resumeOfflineGame(newRules: _rules);
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => LudoGameScreen(
                      players: prov.gameState!.players,
                      gameMode: prov.gameState!.gameMode,
                      ruleSettings: prov.gameState!.rules,
                      boardIndex: _selectedBoardIndex,
                      continuousRolling: _continuousRolling,
                      initialDiceFling: _diceRollingFling,
                      moveSpeed: _moveSpeed,
                    ),
                  ),
                );
              },
            ),
            const SizedBox(height: 12),
          ],
          Row(
            children: [
              Expanded(
                child: _classicActionButton(
                  'Exit',
                  const Color(0xFFE24E44),
                  () => Navigator.maybePop(context),
                ),
              ),
              const SizedBox(width: 30),
              Expanded(
                child: _classicActionButton(
                  'Play',
                  const Color(0xFF86D63B),
                  () => _startSelectedGame(context),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _classicActionButton(String label, Color color, VoidCallback onPressed) {
    return GestureDetector(
      onTap: onPressed,
      child: Container(
        height: 48,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: Colors.white, width: 2),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.3),
              offset: const Offset(0, 4),
              blurRadius: 4,
            ),
            BoxShadow(
              color: color.withOpacity(0.5),
              offset: const Offset(0, -4),
              blurRadius: 0,
            ),
          ],
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              color.withOpacity(0.8),
              color,
            ],
          ),
        ),
        child: Center(
          child: Text(
            label,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w900,
              fontStyle: FontStyle.italic,
              shadows: [Shadow(color: Colors.black45, blurRadius: 2, offset: Offset(1, 1))],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSecondaryActions(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        TextButton(
          onPressed: () => _showOnlineOptions(context),
          child: const Text('Online'),
        ),
        TextButton(
          onPressed: () {
            final gpLocal = context.read<GameProvider>();
            gpLocal.quickMatch();
          },
          child: const Text('Quick Match'),
        ),
        TextButton(
          onPressed: () => _showLeaderboard(context),
          child: const Text('Leaderboard'),
        ),
      ],
    );
  }

  Widget _actionButton(String label, Color color, VoidCallback onPressed) {
    return InkWell(
      onTap: onPressed,
      borderRadius: BorderRadius.circular(18),
      child: Container(
        height: 46,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [color, color.withAlpha(217)],
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
          ),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: Colors.white.withAlpha(128)),
          boxShadow: [
            BoxShadow(
              color: color.withAlpha(89),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Center(
          child: Text(
            label,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.w900,
              fontStyle: FontStyle.italic,
            ),
          ),
        ),
      ),
    );
  }

  Widget _sectionHeader(String title) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: const Color(0xFFFFC233),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        title,
        style: const TextStyle(
          color: Colors.black,
          fontWeight: FontWeight.w900,
          fontSize: 14,
        ),
      ),
    );
  }

  Widget _pillChoice(
    String label,
    bool selected, {
    required VoidCallback onTap,
    required Color selectedColor,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: selected ? selectedColor : Colors.white,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: selectedColor),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? Colors.black : Colors.black87,
            fontWeight: FontWeight.w800,
          ),
        ),
      ),
    );
  }

  Widget _glowBlob(Color color, double size) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(shape: BoxShape.circle, color: color),
    );
  }

  void _setRules(LudoRuleSettings settings) {
    setState(() {
      _rules = settings;
    });
  }

  Widget _buildGameModeButton(
    BuildContext context,
    String title,
    IconData icon,
    Color color,
    VoidCallback onPressed,
  ) {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: color.withAlpha(102),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(16),
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 16),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [color, color.withAlpha(179)],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, color: Colors.white, size: 28),
                const SizedBox(width: 12),
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                    letterSpacing: 1,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _showOfflineOptions(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Offline Mode'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              title: const Text('2 Players'),
              onTap: () {
                Navigator.pop(context);
                _startOfflineGame(context, 2);
              },
            ),
            ListTile(
              title: const Text('4 Players'),
              onTap: () {
                Navigator.pop(context);
                _startOfflineGame(context, 4);
              },
            ),
          ],
        ),
      ),
    );
  }

  void _showOnlineOptions(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Online Mode'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              title: const Text('Create Room'),
              onTap: () {
                Navigator.pop(context);
                // TODO: Implement create room
              },
            ),
            ListTile(
              title: const Text('Join Room'),
              onTap: () {
                Navigator.pop(context);
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const LudoLobbyScreen()),
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  void _startVsComputer(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('VS Computer'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              title: const Text('Easy'),
              onTap: () {
                Navigator.pop(context);
                _startVsComputerGame(context, DifficultyLevel.easy);
              },
            ),
            ListTile(
              title: const Text('Medium'),
              onTap: () {
                Navigator.pop(context);
                _startVsComputerGame(context, DifficultyLevel.medium);
              },
            ),
            ListTile(
              title: const Text('Hard'),
              onTap: () {
                Navigator.pop(context);
                _startVsComputerGame(context, DifficultyLevel.hard);
              },
            ),
          ],
        ),
      ),
    );
  }

  void _startOfflineGame(BuildContext context, int playerCount) {
    _launchOfflineGame(context, playerCount);
  }

  void _launchOfflineGame(BuildContext context, int playerCount) {
    final players = <Player>[];

    for (int i = 0; i < playerCount && i < _slotColors.length; i++) {
      final slotType =
          i < _playerSlots.length ? _playerSlots[i] : _PlayerSlotType.human;
      players.add(
        Player(
          id: 'player_$i',
          name: _playerNames[i],
          color: _slotColors[i],
          type: slotType == _PlayerSlotType.computer
              ? PlayerType.ai
              : PlayerType.human,
          difficulty: slotType == _PlayerSlotType.computer ? _difficulty : null,
          tokenCount: _selectedCoins,
        ),
      );
    }

    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => LudoGameScreen(
          players: players,
          gameMode: GameMode.offline,
          ruleSettings: _rules,
          initialDiceFling: _diceRollingFling,
          boardIndex: _selectedBoardIndex,
          continuousRolling: _continuousRolling,
          moveSpeed: _moveSpeed,
        ),
      ),
    );
  }

  void _startSelectedGame(BuildContext context) {
    final players = <Player>[];

    for (int i = 0; i < _playerSlots.length; i++) {
      final slot = _playerSlots[i];
      if (slot == _PlayerSlotType.none) continue;

      players.add(
        Player(
          id: 'player_$i',
          name: _playerNames[i],
          color: _slotColors[i],
          type:
              slot == _PlayerSlotType.human ? PlayerType.human : PlayerType.ai,
          difficulty: slot == _PlayerSlotType.computer ? _difficulty : null,
          tokenCount: _selectedCoins,
        ),
      );
    }

    if (players.length < 2) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Select at least 2 players')),
      );
      return;
    }

    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => LudoGameScreen(
          players: players,
          gameMode: GameMode.offline,
          ruleSettings: _rules,
          initialDiceFling: _diceRollingFling,
          boardIndex: _selectedBoardIndex,
          continuousRolling: _continuousRolling,
          moveSpeed: _moveSpeed,
        ),
      ),
    );
  }

  void _startVsComputerGame(BuildContext context, DifficultyLevel difficulty) {
    final players = [
      Player(
        id: 'player_human',
        name: 'You',
        color: PlayerColor.red,
        type: PlayerType.human,
        tokenCount: _selectedCoins,
      ),
      Player(
        id: 'player_ai',
        name: 'Computer',
        color: PlayerColor.blue,
        type: PlayerType.ai,
        difficulty: difficulty,
        tokenCount: _selectedCoins,
      ),
    ];

    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => LudoGameScreen(
          players: players,
          gameMode: GameMode.vsComputer,
          ruleSettings: _rules,
          initialDiceFling: _diceRollingFling,
          boardIndex: _selectedBoardIndex,
          continuousRolling: _continuousRolling,
          moveSpeed: _moveSpeed,
        ),
      ),
    );
  }

  void _showSettings(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => Dialog(
        backgroundColor: Colors.transparent,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Container(
              width: 320,
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFFF9F5E8),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: const Color(0xFFFFC233), width: 3),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const SizedBox(height: 10),
                  _sectionHeader('SETTINGS'),
                  const SizedBox(height: 20),
                  _settingsRow('Sounds', true, onTap: () {}),
                  const SizedBox(height: 8),
                  _settingsRow('Music', true, onTap: () {}),
                  const SizedBox(height: 8),
                  _settingsRow('Vibration', true, onTap: () {}),
                  const SizedBox(height: 16),
                  const Divider(color: Color(0xFFFFC233), thickness: 1),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Expanded(child: _settingsMinorButton('Policy')),
                      const SizedBox(width: 8),
                      Expanded(child: _settingsMinorButton('Terms')),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(child: _settingsMinorButton('Credits')),
                      const SizedBox(width: 8),
                      Expanded(child: _settingsMinorButton('Rate Us')),
                    ],
                  ),
                  const SizedBox(height: 10),
                ],
              ),
            ),
            Positioned(
              right: -10,
              top: -10,
              child: GestureDetector(
                onTap: () => Navigator.pop(context),
                child: Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFFE24E44),
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white, width: 2),
                    boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 4)],
                  ),
                  child: const Icon(Icons.close, color: Colors.white, size: 28),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _settingsRow(String label, bool enabled, {required VoidCallback onTap}) {
    return Container(
      height: 44,
      decoration: BoxDecoration(
        color: const Color(0xFFFFC233).withOpacity(0.3),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: const Color(0xFFFFC233), width: 1.5),
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Colors.white, const Color(0xFFFFC233).withOpacity(0.2)],
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              label,
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900),
            ),
            Container(
              width: 24,
              height: 24,
              decoration: const BoxDecoration(
                color: Color(0xFF86D63B),
                shape: BoxShape.circle,
                boxShadow: [BoxShadow(color: Colors.black12, blurRadius: 2)],
              ),
              child: const Icon(Icons.check, color: Colors.white, size: 16),
            ),
          ],
        ),
      ),
    );
  }

  Widget _settingsMinorButton(String label) {
    return Container(
      height: 36,
      decoration: BoxDecoration(
        color: const Color(0xFFFFC233),
        borderRadius: BorderRadius.circular(10),
        boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 2, offset: Offset(0, 2))],
      ),
      child: Center(
        child: Text(
          label,
          style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 14),
        ),
      ),
    );
  }

  void _showLeaderboard(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Leaderboard'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: const [
            ListTile(title: Text('1. Player Name'), trailing: Text('1500 pts')),
            ListTile(title: Text('2. Player Name'), trailing: Text('1200 pts')),
            ListTile(title: Text('3. Player Name'), trailing: Text('900 pts')),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }
}

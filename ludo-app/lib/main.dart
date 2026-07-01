import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'services/sound_service.dart';
import 'providers/game_provider.dart';
import 'features/ludo/presentation/screens/ludo_home_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const LudoApp());
}

class LudoApp extends StatelessWidget {
  const LudoApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (context) => SoundService()),
        ChangeNotifierProvider(create: (context) => GameProvider()),
      ],
      child: Builder(
        builder: (builderContext) {
          return MaterialApp(
            title: 'Ludo Game',
            debugShowCheckedModeBanner: false,
            theme: ThemeData(
              colorScheme:
                  ColorScheme.fromSeed(seedColor: const Color(0xFFFFC233)),
              useMaterial3: true,
            ),
            home: const LudoHomeScreen(),
          );
        },
      ),
    );
  }
}

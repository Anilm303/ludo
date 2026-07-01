import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/game_provider.dart';

class CancelMatchButton extends StatelessWidget {
  const CancelMatchButton({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: () {
        final gp = context.read<GameProvider>();
        gp.cancelQuickMatch();
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Cancelled quick match')));
      },
      style: ElevatedButton.styleFrom(backgroundColor: Colors.redAccent),
      child: const Text('Cancel'),
    );
  }
}

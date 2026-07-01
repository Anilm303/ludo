import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

import '../../../../models/ludo_models.dart';
import '../../../../providers/game_provider.dart';
import 'package:provider/provider.dart';
import 'ludo_game_screen.dart';

class LudoLobbyScreen extends StatefulWidget {
  const LudoLobbyScreen({Key? key}) : super(key: key);

  @override
  State<LudoLobbyScreen> createState() => _LudoLobbyScreenState();
}

class _LudoLobbyScreenState extends State<LudoLobbyScreen> {
  Future<List<Map<String, dynamic>>> _fetchRooms() async {
    try {
      final res = await http.get(Uri.parse('http://127.0.0.1:8000/rooms'));
      if (res.statusCode == 200) {
        final data = json.decode(res.body) as Map<String, dynamic>;
        final rooms = (data['rooms'] as List<dynamic>?) ?? [];
        return rooms.map((r) => Map<String, dynamic>.from(r)).toList();
      }
    } catch (e) {
      // ignore
    }
    return [];
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Lobby')),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: _fetchRooms(),
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          final rooms = snap.data ?? [];
          if (rooms.isEmpty) {
            return Center(
              child: Text(
                'No available rooms. Try Quick Match or create a room.',
              ),
            );
          }

          return ListView.separated(
            itemCount: rooms.length,
            separatorBuilder: (_, __) => const Divider(height: 1),
            itemBuilder: (context, idx) {
              final r = rooms[idx];
              Future<void> _showRoomDetails(String roomId) async {
                try {
                  final res = await http.get(
                    Uri.parse('http://127.0.0.1:8000/rooms/$roomId'),
                  );
                  if (res.statusCode == 200) {
                    final data = json.decode(res.body) as Map<String, dynamic>;
                    final room = data['room'] as Map<String, dynamic>?;
                    final players = room?['playerIds'] as List<dynamic>? ?? [];
                    showDialog(
                      context: context,
                      builder: (_) => AlertDialog(
                        title: Text(room?['name'] ?? 'Room Details'),
                        content: Column(
                          mainAxisSize: MainAxisSize.min,
                          children:
                              players.map((p) => Text(p.toString())).toList(),
                        ),
                        actions: [
                          TextButton(
                            onPressed: () => Navigator.pop(context),
                            child: const Text('Close'),
                          ),
                        ],
                      ),
                    );
                    return;
                  }
                } catch (e) {
                  // ignore
                }
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Could not fetch room details')),
                );
              }

              return ListTile(
                title: Text(r['name'] ?? r['roomId'] ?? 'Room'),
                subtitle: Text(
                  '${r['playerCount'] ?? 0}/${r['maxPlayers'] ?? 4} players',
                ),
                trailing: ElevatedButton(
                  onPressed: () {
                    // Join room via provider's socket if connected
                    final gp = context.read<GameProvider>();
                    final username = gp.currentUsername ?? 'Player';
                    final userId = gp.currentUserId ?? UniqueKey().toString();
                    // instruct provider/socket to join room
                    if (gp.socketService != null && r['roomId'] != null) {
                      gp.socketService!.joinRoom(r['roomId'], username);
                      gp.socketService!.requestState(r['roomId']);
                      Navigator.pushReplacement(
                        context,
                        MaterialPageRoute(
                          builder: (_) => LudoGameScreen(
                            players: [],
                            gameMode: GameMode.online,
                          ),
                        ),
                      );
                    } else {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('Not connected to server'),
                        ),
                      );
                    }
                  },
                  child: const Text('Join'),
                ),
              );
            },
          );
        },
      ),
    );
  }
}

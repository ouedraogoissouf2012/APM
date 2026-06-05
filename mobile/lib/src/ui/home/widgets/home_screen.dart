import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../auth/view_model/auth_view_model.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authViewModelProvider).value;
    return Scaffold(
      appBar: AppBar(
        title: const Text('APM'),
        actions: [
          IconButton(
            key: const Key('logout_button'),
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(authViewModelProvider.notifier).logout(),
          ),
        ],
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              user == null ? 'Welcome' : 'Hello, ${user.email} (${user.cefrLevel})',
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              key: const Key('start_conversation_button'),
              onPressed: () => context.go('/conversation'),
              icon: const Icon(Icons.mic),
              label: const Text('Start a conversation'),
            ),
          ],
        ),
      ),
    );
  }
}

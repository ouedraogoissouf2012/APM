import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../view_model/conversation_state.dart';
import '../view_model/conversation_view_model.dart';

class ConversationScreen extends ConsumerStatefulWidget {
  const ConversationScreen({super.key});

  @override
  ConsumerState<ConversationScreen> createState() => _ConversationScreenState();
}

class _ConversationScreenState extends ConsumerState<ConversationScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(conversationViewModelProvider.notifier).start();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(conversationViewModelProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Conversation'),
        actions: [
          IconButton(
            key: const Key('end_button'),
            icon: const Icon(Icons.call_end),
            onPressed: () async {
              final sessionId = ref.read(conversationViewModelProvider).sessionId;
              await ref.read(conversationViewModelProvider.notifier).end();
              if (!context.mounted) return;
              context.go(sessionId != null ? '/debrief/$sessionId' : '/home');
            },
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: state.turns.length,
              itemBuilder: (_, i) {
                final turn = state.turns[i];
                final isUser = turn.role == 'user';
                return Align(
                  alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    margin: const EdgeInsets.symmetric(vertical: 4),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: isUser
                          ? Theme.of(context).colorScheme.primaryContainer
                          : Theme.of(context).colorScheme.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(turn.content),
                  ),
                );
              },
            ),
          ),
          if (state.error != null)
            Padding(
              padding: const EdgeInsets.all(8),
              child: Text(
                state.error!,
                key: const Key('conversation_error'),
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: _MicButton(status: state.status),
          ),
        ],
      ),
    );
  }
}

class _MicButton extends ConsumerWidget {
  const _MicButton({required this.status});

  final ConversationStatus status;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final label = switch (status) {
      ConversationStatus.idle => 'Tap to speak',
      ConversationStatus.listening => 'Listening…',
      ConversationStatus.thinking => 'Thinking…',
      ConversationStatus.speaking => 'Speaking…',
    };
    final busy = status != ConversationStatus.idle;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        FloatingActionButton.large(
          key: const Key('mic_button'),
          onPressed:
              busy ? null : () => ref.read(conversationViewModelProvider.notifier).listenAndRespond(),
          child: Icon(busy ? Icons.hourglass_empty : Icons.mic),
        ),
        const SizedBox(height: 8),
        Text(label),
      ],
    );
  }
}

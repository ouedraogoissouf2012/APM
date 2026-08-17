import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/ui/app_back_leading.dart';
import '../../../data/models/profile.dart';
import '../view_model/profile_view_model.dart';

/// « Ce que je sais de toi » — surfaces the memory the assistant keeps about the
/// learner (written by the debrief after each session, and injected into every
/// prompt). The learner can read it, edit it, or clear it entirely: transparency
/// and control over a value the app already uses silently.
class MemoryScreen extends ConsumerStatefulWidget {
  const MemoryScreen({super.key});

  @override
  ConsumerState<MemoryScreen> createState() => _MemoryScreenState();
}

class _MemoryScreenState extends ConsumerState<MemoryScreen> {
  final _memory = TextEditingController();
  bool _initialized = false;
  bool _saving = false;

  @override
  void dispose() {
    _memory.dispose();
    super.dispose();
  }

  void _initFrom(Profile profile) {
    _memory.text = profile.memorySummary;
    _initialized = true;
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final ok = await ref
        .read(profileViewModelProvider.notifier)
        .saveMemory(_memory.text.trim());
    if (!mounted) return;
    setState(() => _saving = false);
    _snack(ok ? 'Mémoire enregistrée' : 'Échec de l’enregistrement — réessaie');
  }

  Future<void> _clear() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Tout oublier ?'),
        content: const Text(
          'L’assistant oubliera ce qu’il sait de toi. Cette action est '
          'irréversible.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Annuler'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Tout oublier'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    setState(() => _saving = true);
    final ok = await ref.read(profileViewModelProvider.notifier).clearMemory();
    if (!mounted) return;
    setState(() {
      _saving = false;
      if (ok) _memory.clear();
    });
    _snack(ok ? 'Mémoire effacée' : 'Échec de l’effacement — réessaie');
  }

  void _snack(String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(profileViewModelProvider);
    return Scaffold(
      appBar: AppBar(
        leading: const AppBackLeading(),
        title: const Text('Ce que je sais de toi'),
      ),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => const Center(
          child: Text(
            'Impossible de charger ta mémoire.',
            key: Key('memory_error'),
          ),
        ),
        data: (profile) {
          if (!_initialized) _initFrom(profile);
          final empty = profile.memorySummary.trim().isEmpty;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                'Après chaque session, l’assistant note ce qu’il retient de toi '
                'pour mieux t’aider. Tu peux le corriger ou tout effacer.',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: 16),
              if (empty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: Text(
                    'Rien pour l’instant — parle un peu et je commencerai à te '
                    'connaître.',
                    key: Key('memory_empty_hint'),
                  ),
                ),
              TextField(
                key: const Key('memory_field'),
                controller: _memory,
                maxLines: 6,
                minLines: 3,
                decoration: const InputDecoration(
                  labelText: 'Ce que l’assistant sait',
                  alignLabelWithHint: true,
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 20),
              FilledButton(
                key: const Key('save_memory_button'),
                onPressed: _saving ? null : _save,
                child: const Text('Enregistrer'),
              ),
              const SizedBox(height: 8),
              TextButton(
                key: const Key('clear_memory_button'),
                onPressed: _saving || empty ? null : _clear,
                child: const Text('Tout oublier'),
              ),
            ],
          );
        },
      ),
    );
  }
}

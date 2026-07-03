import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../data/models/profile.dart';
import '../view_model/profile_view_model.dart';

class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  final _interests = TextEditingController();
  final _goal = TextEditingController();
  String _accent = 'us';
  String _intensity = 'gentle';
  bool _initialized = false;

  @override
  void dispose() {
    _interests.dispose();
    _goal.dispose();
    super.dispose();
  }

  void _initFrom(Profile profile) {
    _interests.text = profile.interests.join(', ');
    _goal.text = profile.goal ?? '';
    _accent = profile.accent;
    _intensity = profile.correctionIntensity;
    _initialized = true;
  }

  Future<void> _save() async {
    final interests = _interests.text
        .split(',')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toList();
    await ref
        .read(profileViewModelProvider.notifier)
        .save(
          interests: interests,
          goal: _goal.text.trim(),
          correctionIntensity: _intensity,
          accent: _accent,
        );
    if (mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Profile saved')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(profileViewModelProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => const Center(
          child: Text(
            'Could not load your profile.',
            key: Key('profile_error'),
          ),
        ),
        data: (profile) {
          if (!_initialized) _initFrom(profile);
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              TextField(
                key: const Key('interests_field'),
                controller: _interests,
                decoration: const InputDecoration(
                  labelText: 'Interests (comma-separated)',
                  helperText: 'e.g. football, cooking, travel',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                key: const Key('goal_field'),
                controller: _goal,
                decoration: const InputDecoration(labelText: 'Goal'),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  const Text('Accent'),
                  const Spacer(),
                  DropdownButton<String>(
                    key: const Key('accent_dropdown'),
                    value: _accent,
                    items: const [
                      DropdownMenuItem(
                        value: 'us',
                        child: Text('American (US)'),
                      ),
                      DropdownMenuItem(
                        value: 'uk',
                        child: Text('British (UK)'),
                      ),
                    ],
                    onChanged: (v) => setState(() => _accent = v ?? _accent),
                  ),
                ],
              ),
              Row(
                children: [
                  const Text('Correction style'),
                  const Spacer(),
                  DropdownButton<String>(
                    key: const Key('intensity_dropdown'),
                    value: _intensity,
                    items: const [
                      DropdownMenuItem(value: 'gentle', child: Text('Gentle')),
                      DropdownMenuItem(
                        value: 'detailed',
                        child: Text('Detailed'),
                      ),
                    ],
                    onChanged: (v) =>
                        setState(() => _intensity = v ?? _intensity),
                  ),
                ],
              ),
              const SizedBox(height: 24),
              FilledButton(
                key: const Key('save_profile_button'),
                onPressed: _save,
                child: const Text('Save'),
              ),
            ],
          );
        },
      ),
    );
  }
}

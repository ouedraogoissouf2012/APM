import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/router/debounced_push.dart';
import '../../../core/ui/app_back_leading.dart';
import '../../../core/router/routes.dart';
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
  bool _saving = false;

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
    setState(() => _saving = true);
    final saved = await ref
        .read(profileViewModelProvider.notifier)
        .save(
          interestsText: _interests.text,
          goal: _goal.text.trim(),
          correctionIntensity: _intensity,
          accent: _accent,
        );
    if (!mounted) return;
    setState(() => _saving = false);
    // Honest feedback: only claim success when the save actually succeeded.
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          saved
              ? 'Profil enregistré'
              : 'Impossible d’enregistrer ton profil — réessaie',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(profileViewModelProvider);
    return Scaffold(
      appBar: AppBar(
        leading: const AppBackLeading(),
        title: const Text('Profil'),
      ),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => const Center(
          child: Text(
            'Impossible de charger ton profil.',
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
                  labelText: 'Centres d’intérêt (séparés par des virgules)',
                  helperText: 'ex. football, cuisine, voyage',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                key: const Key('goal_field'),
                controller: _goal,
                decoration: const InputDecoration(labelText: 'Objectif'),
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
                        child: Text('Américain (US)'),
                      ),
                      DropdownMenuItem(
                        value: 'uk',
                        child: Text('Britannique (UK)'),
                      ),
                    ],
                    onChanged: (v) => setState(() => _accent = v ?? _accent),
                  ),
                ],
              ),
              Row(
                children: [
                  const Text('Style de correction'),
                  const Spacer(),
                  DropdownButton<String>(
                    key: const Key('intensity_dropdown'),
                    value: _intensity,
                    items: const [
                      DropdownMenuItem(value: 'gentle', child: Text('Doux')),
                      DropdownMenuItem(
                        value: 'detailed',
                        child: Text('Détaillé'),
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
                // Gated on _saving (#352), mirroring memory_screen.dart's
                // _save button: without it, a rapid double-tap fires two
                // concurrent save() calls — the slower response can land
                // last and overwrite the faster one's result.
                onPressed: _saving ? null : _save,
                child: const Text('Enregistrer'),
              ),
              const SizedBox(height: 8),
              // Voice consent/privacy is genuinely account-adjacent, so it stays
              // with the profile settings. The learning zones that used to pile up
              // here (memory, notebook, review) — the tracked "dumping ground"
              // debt (#189, first #166) — now live in the "Apprendre" hub (#194).
              ListTile(
                key: const Key('voice_privacy_link'),
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.privacy_tip_outlined),
                title: const Text('Ma voix & confidentialité'),
                subtitle: const Text('Consentements, export, effacement'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => context.debouncedPush(Routes.voicePrivacy),
              ),
            ],
          );
        },
      ),
    );
  }
}

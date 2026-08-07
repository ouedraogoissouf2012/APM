import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

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
    final saved = await ref
        .read(profileViewModelProvider.notifier)
        .save(
          interestsText: _interests.text,
          goal: _goal.text.trim(),
          correctionIntensity: _intensity,
          accent: _accent,
        );
    if (!mounted) return;
    // Honest feedback: only claim success when the save actually succeeded.
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          saved ? 'Profil enregistré' : 'Impossible d’enregistrer ton profil — réessaie',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(profileViewModelProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Profil')),
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
                onPressed: _save,
                child: const Text('Enregistrer'),
              ),
              const SizedBox(height: 8),
              // TRACKED DEBT (#189, first declared #166, recurred #164/#170/#175):
              // these four product areas (memory, vocabulary, review, proof) are
              // parked here as list tiles under the settings form — a "dumping
              // ground", not a real information architecture. They ARE reachable
              // (fixing the earlier dead-ends), but the proper nav belongs to the
              // design window; re-declared here so the debt is not repeated in
              // silence again.
              ListTile(
                key: const Key('memory_link'),
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.psychology_outlined),
                title: const Text('Ce que je sais de toi'),
                subtitle: const Text('Voir et éditer la mémoire de l’assistant'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => context.push(Routes.memory),
              ),
              ListTile(
                key: const Key('vocabulary_link'),
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.menu_book_outlined),
                title: const Text('Mon carnet'),
                subtitle: const Text('Les mots vus en session, à réviser'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => context.push(Routes.vocabulary),
              ),
              ListTile(
                key: const Key('review_link'),
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.repeat),
                title: const Text('À réviser'),
                subtitle: const Text('Tes fautes récurrentes, au bon moment'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => context.push(Routes.review),
              ),
              ListTile(
                key: const Key('voice_privacy_link'),
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.privacy_tip_outlined),
                title: const Text('Ma voix & confidentialité'),
                subtitle: const Text('Consentements, export, effacement'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => context.push(Routes.voicePrivacy),
              ),
            ],
          );
        },
      ),
    );
  }
}

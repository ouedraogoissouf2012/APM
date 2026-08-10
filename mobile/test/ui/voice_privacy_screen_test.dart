import 'dart:typed_data';

import 'package:apm/src/core/audio/providers.dart';
import 'package:apm/src/core/audio/voice_take_store.dart';
import 'package:apm/src/data/models/voice_consent.dart';
import 'package:apm/src/data/repositories/voice_privacy_repository.dart';
import 'package:apm/src/ui/privacy/view_model/voice_privacy_view_model.dart';
import 'package:apm/src/ui/privacy/widgets/voice_privacy_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockRepo extends Mock implements VoicePrivacyRepository {}

/// Spy for the on-device take store: records whether the local raw audio was
/// actually wiped by the erase action (#219).
class _SpyVoiceTakeStore implements VoiceTakeStore {
  bool erased = false;
  @override
  Future<void> eraseAll() async => erased = true;
  @override
  Future<void> saveTake(String skill, Uint8List bytes) async {}
  @override
  Future<VoiceTakes?> takesFor(String skill) async => null;
}

VoiceConsent _consent({bool transcription = true}) => VoiceConsent(
  transcription: transcription,
  scoring: false,
  b2bShare: false,
  modelTraining: false,
);

Future<void> _pump(
  WidgetTester tester,
  VoicePrivacyRepository repo, {
  VoiceTakeStore? store,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        voicePrivacyRepositoryProvider.overrideWithValue(repo),
        // Override the on-device store so tests never touch path_provider /
        // IndexedDB and can assert the local wipe happens.
        voiceTakeStoreProvider.overrideWithValue(store ?? _SpyVoiceTakeStore()),
      ],
      child: const MaterialApp(home: VoicePrivacyScreen()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows the four consent switches', (tester) async {
    final repo = _MockRepo();
    when(repo.getConsent).thenAnswer((_) async => _consent());

    await _pump(tester, repo);

    expect(find.byKey(const Key('consent_transcription')), findsOneWidget);
    expect(find.byKey(const Key('consent_scoring')), findsOneWidget);
    expect(find.byKey(const Key('consent_b2b_share')), findsOneWidget);
    expect(find.byKey(const Key('consent_model_training')), findsOneWidget);
    // Honest statement that raw audio is not kept.
    expect(find.textContaining('jamais'), findsWidgets);
  });

  testWidgets('toggling a consent calls the repository', (tester) async {
    final repo = _MockRepo();
    when(repo.getConsent).thenAnswer((_) async => _consent(transcription: true));
    when(
      () => repo.setConsent(any(), any()),
    ).thenAnswer((_) async => _consent(transcription: false));

    await _pump(tester, repo);
    await tester.tap(find.byKey(const Key('consent_transcription')));
    await tester.pumpAndSettle();

    verify(() => repo.setConsent('transcription', false)).called(1);
  });

  testWidgets('erase asks for confirmation before deleting', (tester) async {
    final repo = _MockRepo();
    when(repo.getConsent).thenAnswer((_) async => _consent());
    when(repo.eraseData).thenAnswer((_) async => {'transcripts': 1});

    await _pump(tester, repo);
    await tester.tap(find.byKey(const Key('erase_voice_data')));
    await tester.pumpAndSettle();

    // Confirmation dialog shown; nothing deleted yet, and it is HONEST about the
    // on-device recordings that will be wiped (#219).
    verifyNever(repo.eraseData);
    expect(find.textContaining('sur cet appareil'), findsOneWidget);
    await tester.tap(find.text('Effacer').last);
    await tester.pumpAndSettle();
    verify(repo.eraseData).called(1);
  });

  testWidgets('erase wipes the on-device voice takes, not just the server (#219)',
      (tester) async {
    final repo = _MockRepo();
    when(repo.getConsent).thenAnswer((_) async => _consent());
    when(repo.eraseData).thenAnswer((_) async => {'transcripts': 1});
    final store = _SpyVoiceTakeStore();

    await _pump(tester, repo, store: store);
    await tester.tap(find.byKey(const Key('erase_voice_data')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Effacer').last);
    await tester.pumpAndSettle();

    // The raw local takes are actually deleted...
    expect(store.erased, isTrue);
    // ...AND the server data...
    verify(repo.eraseData).called(1);
    // ...and only then does the UI claim success (no longer a lie).
    expect(find.text('Tes données voix ont été effacées'), findsOneWidget);
  });

  testWidgets('error state shows a message', (tester) async {
    final repo = _MockRepo();
    when(repo.getConsent).thenThrow(Exception('down'));

    await _pump(tester, repo);

    expect(find.byKey(const Key('privacy_error')), findsOneWidget);
  });
}

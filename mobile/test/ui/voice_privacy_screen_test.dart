import 'package:apm/src/data/models/voice_consent.dart';
import 'package:apm/src/data/repositories/voice_privacy_repository.dart';
import 'package:apm/src/ui/privacy/view_model/voice_privacy_view_model.dart';
import 'package:apm/src/ui/privacy/widgets/voice_privacy_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockRepo extends Mock implements VoicePrivacyRepository {}

VoiceConsent _consent({bool transcription = true}) => VoiceConsent(
  transcription: transcription,
  scoring: false,
  b2bShare: false,
  modelTraining: false,
);

Future<void> _pump(WidgetTester tester, VoicePrivacyRepository repo) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [voicePrivacyRepositoryProvider.overrideWithValue(repo)],
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

    // Confirmation dialog shown; nothing deleted yet.
    verifyNever(repo.eraseData);
    await tester.tap(find.text('Effacer').last);
    await tester.pumpAndSettle();
    verify(repo.eraseData).called(1);
  });

  testWidgets('error state shows a message', (tester) async {
    final repo = _MockRepo();
    when(repo.getConsent).thenThrow(Exception('down'));

    await _pump(tester, repo);

    expect(find.byKey(const Key('privacy_error')), findsOneWidget);
  });
}

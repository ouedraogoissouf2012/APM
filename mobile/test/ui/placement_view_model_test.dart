import 'dart:typed_data';

import 'package:apm/src/core/audio/audio_recording_service.dart';
import 'package:apm/src/core/audio/providers.dart';
import 'package:apm/src/data/repositories/conversation_repository.dart';
import 'package:apm/src/data/repositories/onboarding_repository.dart';
import 'package:apm/src/ui/conversation/view_model/conversation_providers.dart';
import 'package:apm/src/ui/onboarding/view_model/placement_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockConversationRepository extends Mock
    implements ConversationRepository {}

class _MockOnboardingRepository extends Mock implements OnboardingRepository {}

class _FakeRecorder implements AudioRecordingService {
  bool startResult = true;

  @override
  Future<bool> start() async => startResult;

  @override
  Future<Uint8List?> stop() async => Uint8List.fromList(const [1, 2, 3]);

  @override
  Future<void> cancel() async {}
}

ProviderContainer _container({
  required ConversationRepository conv,
  required OnboardingRepository onboarding,
  AudioRecordingService? recorder,
}) {
  final c = ProviderContainer(
    overrides: [
      conversationRepositoryProvider.overrideWithValue(conv),
      onboardingRepositoryProvider.overrideWithValue(onboarding),
      audioRecordingProvider.overrideWithValue(recorder ?? _FakeRecorder()),
    ],
  );
  addTearDown(c.dispose);
  return c;
}

void main() {
  setUpAll(() {
    registerFallbackValue(Uint8List(0));
  });

  test('records and transcribes an answer, then advances the question', () async {
    final conv = _MockConversationRepository();
    when(() => conv.transcribe(any())).thenAnswer((_) async => 'my answer');
    final c = _container(conv: conv, onboarding: _MockOnboardingRepository());
    final vm = c.read(placementViewModelProvider.notifier);

    await vm.startRecording();
    expect(
      c.read(placementViewModelProvider).status,
      PlacementStatus.recording,
    );

    await vm.stopAndTranscribe();
    final state = c.read(placementViewModelProvider);
    expect(state.answers, ['my answer']);
    expect(state.questionIndex, 1); // advanced to the next question
    expect(state.status, PlacementStatus.idle);
  });

  test('a failed transcription still advances with an empty answer', () async {
    final conv = _MockConversationRepository();
    when(() => conv.transcribe(any())).thenThrow(Exception('stt down'));
    final c = _container(conv: conv, onboarding: _MockOnboardingRepository());
    final vm = c.read(placementViewModelProvider.notifier);

    await vm.startRecording();
    await vm.stopAndTranscribe();

    final state = c.read(placementViewModelProvider);
    expect(state.answers, ['']); // never traps the learner on a question
    expect(state.questionIndex, 1);
  });

  test('the last question does not advance past the end', () async {
    final conv = _MockConversationRepository();
    when(() => conv.transcribe(any())).thenAnswer((_) async => 'a');
    final c = _container(conv: conv, onboarding: _MockOnboardingRepository());
    final vm = c.read(placementViewModelProvider.notifier);

    for (var i = 0; i < kPlacementQuestions.length; i++) {
      await vm.startRecording();
      await vm.stopAndTranscribe();
    }

    final state = c.read(placementViewModelProvider);
    expect(state.answers.length, kPlacementQuestions.length);
    expect(state.questionIndex, kPlacementQuestions.length - 1); // capped
  });

  test('submit sends answers + interests/goal and reports success', () async {
    final conv = _MockConversationRepository();
    when(() => conv.transcribe(any())).thenAnswer((_) async => 'answer');
    final onboarding = _MockOnboardingRepository();
    when(
      () => onboarding.submitPlacement(
        answers: any(named: 'answers'),
        interests: any(named: 'interests'),
        goal: any(named: 'goal'),
      ),
    ).thenAnswer(
      (_) async => const PlacementResult(
        cefrLevel: 'B1',
        interests: ['football'],
        goal: 'travel',
      ),
    );
    final c = _container(conv: conv, onboarding: onboarding);
    final vm = c.read(placementViewModelProvider.notifier);

    await vm.startRecording();
    await vm.stopAndTranscribe();
    final ok = await vm.submit(interests: ['football'], goal: 'travel');

    expect(ok, isTrue);
    expect(c.read(placementViewModelProvider).status, PlacementStatus.done);
    expect(c.read(placementViewModelProvider).resultLevel, 'B1');
    verify(
      () => onboarding.submitPlacement(
        answers: ['answer'],
        interests: ['football'],
        goal: 'travel',
      ),
    ).called(1);
  });

  test('submit reports failure without throwing (placement is optional)', () async {
    final onboarding = _MockOnboardingRepository();
    when(
      () => onboarding.submitPlacement(
        answers: any(named: 'answers'),
        interests: any(named: 'interests'),
        goal: any(named: 'goal'),
      ),
    ).thenThrow(Exception('network down'));
    final c = _container(
      conv: _MockConversationRepository(),
      onboarding: onboarding,
    );
    final vm = c.read(placementViewModelProvider.notifier);

    final ok = await vm.submit(interests: const [], goal: '');

    expect(ok, isFalse);
    expect(c.read(placementViewModelProvider).status, PlacementStatus.failed);
  });

  test('a failed mic start surfaces a failed status', () async {
    final recorder = _FakeRecorder()..startResult = false;
    final c = _container(
      conv: _MockConversationRepository(),
      onboarding: _MockOnboardingRepository(),
      recorder: recorder,
    );
    final vm = c.read(placementViewModelProvider.notifier);

    await vm.startRecording();

    expect(c.read(placementViewModelProvider).status, PlacementStatus.failed);
  });
}

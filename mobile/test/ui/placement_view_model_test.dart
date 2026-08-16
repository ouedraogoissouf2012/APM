import 'dart:typed_data';

import 'package:apm/src/core/audio/audio_recording_service.dart';
import 'package:apm/src/core/audio/providers.dart';
import 'package:apm/src/core/observability/crash_reporter.dart';
import 'package:apm/src/core/observability/providers.dart';
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

class _MockCrashReporter extends Mock implements CrashReporter {}

class _FakeRecorder implements AudioRecordingService {
  bool startResult = true;
  int cancels = 0;

  @override
  Future<bool> start() async => startResult;

  @override
  Future<Uint8List?> stop() async => Uint8List.fromList(const [1, 2, 3]);

  @override
  Future<void> cancel() async {
    cancels++;
  }
}

ProviderContainer _container({
  required ConversationRepository conv,
  required OnboardingRepository onboarding,
  AudioRecordingService? recorder,
  CrashReporter? crashReporter,
}) {
  final c = ProviderContainer(
    overrides: [
      conversationRepositoryProvider.overrideWithValue(conv),
      onboardingRepositoryProvider.overrideWithValue(onboarding),
      audioRecordingProvider.overrideWithValue(recorder ?? _FakeRecorder()),
      if (crashReporter != null)
        crashReporterProvider.overrideWithValue(crashReporter),
    ],
  );
  addTearDown(c.dispose);
  return c;
}

void main() {
  setUpAll(() {
    registerFallbackValue(Uint8List(0));
    registerFallbackValue(StackTrace.empty);
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

  test('#351: a failed transcription is reported via CrashReporter, not '
      'silently swallowed', () async {
    final conv = _MockConversationRepository();
    when(() => conv.transcribe(any())).thenThrow(Exception('stt down'));
    final reporter = _MockCrashReporter();
    final c = _container(
      conv: conv,
      onboarding: _MockOnboardingRepository(),
      crashReporter: reporter,
    );
    final vm = c.read(placementViewModelProvider.notifier);

    await vm.startRecording();
    await vm.stopAndTranscribe();

    verify(
      () => reporter.captureError(
        any(),
        any(),
        context: any(named: 'context'),
      ),
    ).called(1);
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

  test('submit reports a network failure without throwing (placement is optional)', () async {
    final conv = _MockConversationRepository();
    when(() => conv.transcribe(any())).thenAnswer((_) async => 'answer');
    final onboarding = _MockOnboardingRepository();
    when(
      () => onboarding.submitPlacement(
        answers: any(named: 'answers'),
        interests: any(named: 'interests'),
        goal: any(named: 'goal'),
      ),
    ).thenThrow(Exception('network down'));
    final c = _container(conv: conv, onboarding: onboarding);
    final vm = c.read(placementViewModelProvider.notifier);

    // Record a real answer first, so submit actually hits the network path.
    await vm.startRecording();
    await vm.stopAndTranscribe();
    final ok = await vm.submit(interests: const [], goal: '');

    expect(ok, isFalse);
    expect(c.read(placementViewModelProvider).status, PlacementStatus.failed);
    verify(
      () => onboarding.submitPlacement(
        answers: any(named: 'answers'),
        interests: any(named: 'interests'),
        goal: any(named: 'goal'),
      ),
    ).called(1);
  });

  test('#351: a failed submit is reported via CrashReporter, not silently '
      'swallowed', () async {
    final conv = _MockConversationRepository();
    when(() => conv.transcribe(any())).thenAnswer((_) async => 'answer');
    final onboarding = _MockOnboardingRepository();
    when(
      () => onboarding.submitPlacement(
        answers: any(named: 'answers'),
        interests: any(named: 'interests'),
        goal: any(named: 'goal'),
      ),
    ).thenThrow(Exception('network down'));
    final reporter = _MockCrashReporter();
    final c = _container(
      conv: conv,
      onboarding: onboarding,
      crashReporter: reporter,
    );
    final vm = c.read(placementViewModelProvider.notifier);

    await vm.startRecording();
    await vm.stopAndTranscribe();
    await vm.submit(interests: const [], goal: '');

    verify(
      () => reporter.captureError(
        any(),
        any(),
        context: any(named: 'context'),
      ),
    ).called(1);
  });

  test('submit is skipped when nothing was heard (no bogus beginner level)', () async {
    final onboarding = _MockOnboardingRepository();
    final c = _container(
      conv: _MockConversationRepository(),
      onboarding: onboarding,
    );
    final vm = c.read(placementViewModelProvider.notifier);

    // No answers recorded at all -> must NOT submit a placement the backend would
    // score as a real (beginner) level (#189: STT failure != a real level).
    final ok = await vm.submit(interests: const [], goal: '');

    expect(ok, isFalse);
    expect(c.read(placementViewModelProvider).status, PlacementStatus.failed);
    verifyNever(
      () => onboarding.submitPlacement(
        answers: any(named: 'answers'),
        interests: any(named: 'interests'),
        goal: any(named: 'goal'),
      ),
    );
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

  test('a failed mic start can be retried (not a permanent dead-end)', () async {
    final recorder = _FakeRecorder()..startResult = false;
    final c = _container(
      conv: _MockConversationRepository(),
      onboarding: _MockOnboardingRepository(),
      recorder: recorder,
    );
    final vm = c.read(placementViewModelProvider.notifier);

    await vm.startRecording();
    expect(c.read(placementViewModelProvider).status, PlacementStatus.failed);

    // The learner grants permission and tries again — `failed` must not trap them.
    recorder.startResult = true;
    await vm.startRecording();
    expect(c.read(placementViewModelProvider).status, PlacementStatus.recording);
  });

  test('#425: cancel stops an in-progress recording and frees the mic', () async {
    final recorder = _FakeRecorder();
    final c = _container(
      conv: _MockConversationRepository(),
      onboarding: _MockOnboardingRepository(),
      recorder: recorder,
    );
    final vm = c.read(placementViewModelProvider.notifier);

    await vm.startRecording();
    await vm.cancel();

    expect(recorder.cancels, 1);
    expect(c.read(placementViewModelProvider).status, PlacementStatus.idle);
  });
}

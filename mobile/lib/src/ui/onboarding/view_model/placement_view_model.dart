import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/audio/providers.dart';
import '../../../core/network/providers.dart';
import '../../../core/observability/ref_report_error.dart';
import '../../../data/repositories/onboarding_repository.dart';
import '../../conversation/view_model/conversation_providers.dart';
import '../../profile/view_model/profile_view_model.dart';

final onboardingRepositoryProvider = Provider<OnboardingRepository>(
  (ref) => OnboardingRepository(ref.watch(authenticatedApiClientProvider)),
);

final placementViewModelProvider =
    NotifierProvider<PlacementViewModel, PlacementState>(PlacementViewModel.new);

/// The guided placement questions the learner answers by voice (~60 s total).
/// Kept short and everyday so the analyzer gets a representative speech sample
/// without turning onboarding into a test.
const kPlacementQuestions = <String>[
  'Tell me a bit about yourself and your day.',
  'What did you do last weekend?',
  'Why do you want to improve your English?',
];

enum PlacementStatus { idle, recording, transcribing, submitting, done, failed }

class PlacementState {
  const PlacementState({
    this.questionIndex = 0,
    this.answers = const [],
    this.status = PlacementStatus.idle,
    this.resultLevel,
  });

  final int questionIndex;
  final List<String> answers;
  final PlacementStatus status;
  final String? resultLevel;

  bool get isLastQuestion => questionIndex >= kPlacementQuestions.length - 1;
  String get currentQuestion => kPlacementQuestions[questionIndex];

  PlacementState copyWith({
    int? questionIndex,
    List<String>? answers,
    PlacementStatus? status,
    String? resultLevel,
  }) => PlacementState(
    questionIndex: questionIndex ?? this.questionIndex,
    answers: answers ?? this.answers,
    status: status ?? this.status,
    resultLevel: resultLevel ?? this.resultLevel,
  );
}

/// Drives the spoken placement: record an answer per question, transcribe it,
/// advance; on the last question, submit everything so the backend estimates the
/// starting CEFR and pre-fills the profile. Reuses the conversation's recording
/// and transcription infrastructure — no new audio stack.
class PlacementViewModel extends Notifier<PlacementState> {
  @override
  PlacementState build() => const PlacementState();

  /// Whether any answer captured real speech. Used to avoid submitting a placement
  /// where the mic/STT never produced anything — which would otherwise be scored as
  /// a genuine (bottom) level, indistinguishable from a real beginner.
  bool get hasAnySpeech => state.answers.any((a) => a.trim().isNotEmpty);

  Future<void> startRecording() async {
    // Allow a retry from `failed`: a microphone permission/hardware error must not
    // be a permanent dead-end — the learner can grant access and try again.
    if (state.status != PlacementStatus.idle && state.status != PlacementStatus.failed) {
      return;
    }
    final recorder = ref.read(audioRecordingProvider);
    final started = await recorder.start();
    if (!started) {
      if (ref.mounted) state = state.copyWith(status: PlacementStatus.failed);
      return;
    }
    if (!ref.mounted) {
      // #425: the screen left while start() was in flight.
      await recorder.cancel();
      return;
    }
    state = state.copyWith(status: PlacementStatus.recording);
  }

  /// Stops (discarding) an in-progress recording when the learner leaves or
  /// backgrounds the placement (#425). Idempotent.
  Future<void> cancel() async {
    if (!ref.mounted) return;
    if (state.status == PlacementStatus.recording) {
      await ref.read(audioRecordingProvider).cancel();
      if (ref.mounted) state = state.copyWith(status: PlacementStatus.idle);
    }
  }

  /// Stops recording, transcribes the answer, and advances to the next question
  /// (or leaves the caller to submit when it was the last one). A failed/empty
  /// transcription still advances with an empty answer — the placement is not a
  /// test and must never trap the learner on a question.
  Future<void> stopAndTranscribe() async {
    if (state.status != PlacementStatus.recording) return;
    state = state.copyWith(status: PlacementStatus.transcribing);
    final bytes = await ref.read(audioRecordingProvider).stop();

    String heard = '';
    if (bytes != null && bytes.isNotEmpty) {
      try {
        heard = (await ref
                .read(conversationRepositoryProvider)
                .transcribe(bytes))
            .trim();
      } catch (e, s) {
        // (#351) The placement must never trap the learner on a question
        // (an empty answer just advances, honestly scored as "no speech"
        // heard), but a silent STT failure would otherwise hide a
        // recurring transcription outage from anyone.
        ref.reportError(
          e,
          s,
          context: 'PlacementViewModel.stopAndTranscribe: transcription failed',
        );
        heard = '';
      }
    }

    final answers = [...state.answers, heard];
    if (state.isLastQuestion) {
      state = state.copyWith(answers: answers, status: PlacementStatus.idle);
    } else {
      state = state.copyWith(
        answers: answers,
        questionIndex: state.questionIndex + 1,
        status: PlacementStatus.idle,
      );
    }
  }

  /// Submits the placement with the collected answers plus interests/goal.
  /// Returns true on success. On failure the state reports it and the caller can
  /// still let the learner continue (the placement is optional).
  Future<bool> submit({
    required List<String> interests,
    required String goal,
  }) async {
    // If NOTHING was heard across all questions, don't submit a placement the
    // backend would score as a real (beginner) level — a silent mic/STT failure is
    // not evidence of the learner's English. Surface it so the UI can offer retry
    // or an honest skip instead of silently pinning them at the bottom.
    if (!hasAnySpeech) {
      state = state.copyWith(status: PlacementStatus.failed);
      return false;
    }
    state = state.copyWith(status: PlacementStatus.submitting);
    try {
      final result = await ref
          .read(onboardingRepositoryProvider)
          .submitPlacement(
            answers: state.answers,
            interests: interests,
            goal: goal,
          );
      // Refresh the profile so the app picks up the pre-filled interests/goal.
      ref.invalidate(profileViewModelProvider);
      state = state.copyWith(
        status: PlacementStatus.done,
        resultLevel: result.cefrLevel,
      );
      return true;
    } catch (e, s) {
      // (#351) see the matching comment in stopAndTranscribe() above.
      ref.reportError(e, s, context: 'PlacementViewModel.submit');
      state = state.copyWith(status: PlacementStatus.failed);
      return false;
    }
  }
}

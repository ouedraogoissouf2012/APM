import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/audio/providers.dart';
import '../../../core/network/providers.dart';
import '../../../core/observability/ref_report_error.dart';
import '../../../data/models/vocabulary_entry.dart';
import '../../../data/repositories/vocabulary_repository.dart';
import '../../echo/view_model/echo_view_model.dart';

final vocabularyRepositoryProvider = Provider<VocabularyRepository>(
  (ref) => VocabularyRepository(ref.watch(authenticatedApiClientProvider)),
);

final vocabularyViewModelProvider =
    AsyncNotifierProvider<VocabularyViewModel, List<VocabularyEntry>>(
      VocabularyViewModel.new,
    );

/// Drives the vocabulary notebook: loads the cards, plays a card's audio
/// (reuses the /tts synth + playback), and marks a card known / to-review.
class VocabularyViewModel extends AsyncNotifier<List<VocabularyEntry>> {
  @override
  Future<List<VocabularyEntry>> build() =>
      ref.read(vocabularyRepositoryProvider).list();

  /// Speaks the word aloud with the neural voice (reuses /tts). Returns true
  /// on success so the caller can surface a message on failure — previously
  /// fire-and-forget (#353), so a network/playback error left the speaker
  /// icon looking dead with no feedback, especially offline.
  Future<bool> speak(VocabularyEntry entry) async {
    try {
      final clip = await ref
          .read(echoRepositoryProvider)
          .synthesize(entry.word);
      if (clip.audioB64.isEmpty) return false;
      await ref.read(audioPlaybackProvider).playClip(clip.audioB64, clip.mime);
      return true;
    } catch (e, s) {
      ref.reportError(
        e,
        s,
        context: 'VocabularyViewModel.speak',
        data: {'word': entry.word},
      );
      return false;
    }
  }

  /// Marks a card known ("Je le sais") or back to review ("Encore"). Optimistic:
  /// updates the local list immediately; on failure the previous state is kept
  /// (the list is reloaded so it can never show a wrong status).
  Future<bool> mark(VocabularyEntry entry, {required bool known}) async {
    final status = known ? 'known' : 'review';
    final previous = state.value;
    // Optimistic local update for a snappy swipe.
    if (previous != null) {
      state = AsyncData([
        for (final e in previous)
          e.id == entry.id ? e.copyWith(status: status) : e,
      ]);
    }
    try {
      await ref.read(vocabularyRepositoryProvider).setStatus(entry.id, status);
      return true;
    } catch (e, s) {
      // (#351) An unexpected failure here would otherwise vanish silently —
      // report it so a recurring cause is visible instead of just a rolled
      // back optimistic update with no trail.
      ref.reportError(
        e,
        s,
        context: 'VocabularyViewModel.mark',
        data: {'entryId': entry.id, 'status': status},
      );
      if (previous != null) state = AsyncData(previous);
      return false;
    }
  }
}

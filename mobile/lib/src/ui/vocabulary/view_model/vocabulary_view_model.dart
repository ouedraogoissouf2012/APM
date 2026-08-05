import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/audio/providers.dart';
import '../../../core/network/providers.dart';
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

  /// Speaks the word aloud with the neural voice (reuses /tts).
  Future<void> speak(VocabularyEntry entry) async {
    final clip = await ref.read(echoRepositoryProvider).synthesize(entry.word);
    if (clip.audioB64.isEmpty) return;
    await ref.read(audioPlaybackProvider).playClip(clip.audioB64, clip.mime);
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
    } catch (_) {
      if (previous != null) state = AsyncData(previous);
      return false;
    }
  }
}

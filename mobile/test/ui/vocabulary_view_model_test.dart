import 'package:apm/src/core/audio/audio_playback_service.dart';
import 'package:apm/src/core/audio/providers.dart';
import 'package:apm/src/data/models/vocabulary_entry.dart';
import 'package:apm/src/data/repositories/echo_repository.dart';
import 'package:apm/src/data/repositories/vocabulary_repository.dart';
import 'package:apm/src/ui/echo/view_model/echo_view_model.dart';
import 'package:apm/src/ui/vocabulary/view_model/vocabulary_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockVocabRepo extends Mock implements VocabularyRepository {}

class _MockEchoRepo extends Mock implements EchoRepository {}

class _MockPlayback extends Mock implements AudioPlaybackService {}

VocabularyEntry _entry({int id = 1, String status = 'review'}) => VocabularyEntry(
  id: id,
  sessionId: 23,
  word: 'deployment',
  phonetic: 'dɪˈplɔɪmənt',
  translation: 'déploiement',
  example: 'I handle deployments at work.',
  status: status,
);

ProviderContainer _container({
  required VocabularyRepository vocab,
  EchoRepository? echo,
  AudioPlaybackService? playback,
}) {
  final c = ProviderContainer(
    overrides: [
      vocabularyRepositoryProvider.overrideWithValue(vocab),
      if (echo != null) echoRepositoryProvider.overrideWithValue(echo),
      if (playback != null)
        audioPlaybackProvider.overrideWithValue(playback),
    ],
  );
  addTearDown(c.dispose);
  return c;
}

void main() {
  test('loads the notebook on build', () async {
    final vocab = _MockVocabRepo();
    when(vocab.list).thenAnswer((_) async => [_entry()]);
    final c = _container(vocab: vocab);

    final entries = await c.read(vocabularyViewModelProvider.future);
    expect(entries.single.word, 'deployment');
  });

  test('mark(known) updates the card and calls the repository', () async {
    final vocab = _MockVocabRepo();
    when(vocab.list).thenAnswer((_) async => [_entry()]);
    when(
      () => vocab.setStatus(any(), any()),
    ).thenAnswer((_) async => _entry(status: 'known'));
    final c = _container(vocab: vocab);
    await c.read(vocabularyViewModelProvider.future);

    final ok = await c
        .read(vocabularyViewModelProvider.notifier)
        .mark(_entry(), known: true);

    expect(ok, isTrue);
    expect(c.read(vocabularyViewModelProvider).value!.single.status, 'known');
    verify(() => vocab.setStatus(1, 'known')).called(1);
  });

  test('a failed mark rolls back to the previous status', () async {
    final vocab = _MockVocabRepo();
    when(vocab.list).thenAnswer((_) async => [_entry(status: 'review')]);
    when(() => vocab.setStatus(any(), any())).thenThrow(Exception('down'));
    final c = _container(vocab: vocab);
    await c.read(vocabularyViewModelProvider.future);

    final ok = await c
        .read(vocabularyViewModelProvider.notifier)
        .mark(_entry(), known: true);

    expect(ok, isFalse);
    // No false success: the card stays 'review'.
    expect(c.read(vocabularyViewModelProvider).value!.single.status, 'review');
  });

  test('speak synthesizes the word and plays it', () async {
    final vocab = _MockVocabRepo();
    when(vocab.list).thenAnswer((_) async => [_entry()]);
    final echo = _MockEchoRepo();
    when(
      () => echo.synthesize(any()),
    ).thenAnswer((_) async => const AudioClip('base64audio', 'audio/mpeg'));
    final playback = _MockPlayback();
    when(() => playback.playClip(any(), any())).thenAnswer((_) async {});
    final c = _container(vocab: vocab, echo: echo, playback: playback);
    await c.read(vocabularyViewModelProvider.future);

    await c.read(vocabularyViewModelProvider.notifier).speak(_entry());

    verify(() => echo.synthesize('deployment')).called(1);
    verify(() => playback.playClip('base64audio', 'audio/mpeg')).called(1);
  });
}

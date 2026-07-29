import 'dart:typed_data';

import 'package:apm/src/core/audio/audio_playback_service.dart';
import 'package:apm/src/core/audio/audio_recording_service.dart';
import 'package:apm/src/core/audio/providers.dart';
import 'package:apm/src/data/repositories/echo_repository.dart';
import 'package:apm/src/data/repositories/minimal_pairs_repository.dart';
import 'package:apm/src/ui/minimal_pairs/view_model/minimal_pairs_state.dart';
import 'package:apm/src/ui/minimal_pairs/view_model/minimal_pairs_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockRepo extends Mock implements MinimalPairsRepository {}

class _FakeAudio implements AudioPlaybackService {
  final List<String> played = [];
  @override
  Future<void> playClip(String audioB64, String mime) async => played.add(audioB64);
  @override
  Future<void> playBytes(Uint8List bytes, String mime) async => played.add('MINE');
  @override
  Future<void> stop() async {}
}

class _FakeRecorder implements AudioRecordingService {
  @override
  Future<bool> start() async => true;
  @override
  Future<Uint8List?> stop() async => Uint8List.fromList(const [1, 2, 3]);
  @override
  Future<void> cancel() async {}
}

MinimalPairsViewModel _vm(ProviderContainer c) =>
    c.read(minimalPairsViewModelProvider.notifier);
MinimalPairsState _state(ProviderContainer c) => c.read(minimalPairsViewModelProvider);

ProviderContainer _container(MinimalPairsRepository repo, {_FakeAudio? audio}) {
  final c = ProviderContainer(
    overrides: [
      minimalPairsRepositoryProvider.overrideWithValue(repo),
      audioPlaybackProvider.overrideWithValue(audio ?? _FakeAudio()),
      audioRecordingProvider.overrideWithValue(_FakeRecorder()),
    ],
  );
  addTearDown(c.dispose);
  return c;
}

void main() {
  test('loadPair draws a pair, a spoken word, and synthesizes it', () async {
    final repo = _MockRepo();
    when(() => repo.synthesize(any()))
        .thenAnswer((_) async => const AudioClip('WORDB64', 'audio/mpeg'));
    final c = _container(repo);

    await _vm(c).loadPair();

    final s = _state(c);
    expect(s.hasPair, isTrue);
    // The spoken word is one of the pair's two words.
    expect([s.pair!.wordA, s.pair!.wordB], contains(s.spokenWord));
    expect(s.spokenAudioB64, 'WORDB64');
    expect(s.phase, PairPhase.guessing);
  });

  test('a correct guess is marked correct', () async {
    final repo = _MockRepo();
    when(() => repo.synthesize(any()))
        .thenAnswer((_) async => const AudioClip('WORDB64', 'audio/mpeg'));
    final c = _container(repo);
    await _vm(c).loadPair();
    final spoken = _state(c).spokenWord!;

    _vm(c).guess(spoken); // guess exactly what Ava said

    expect(_state(c).guessedCorrectly, isTrue);
    expect(_state(c).phase, PairPhase.guessed);
  });

  test('an incorrect guess is marked incorrect', () async {
    final repo = _MockRepo();
    when(() => repo.synthesize(any()))
        .thenAnswer((_) async => const AudioClip('WORDB64', 'audio/mpeg'));
    final c = _container(repo);
    await _vm(c).loadPair();
    final s = _state(c);
    final wrong = s.spokenWord == s.pair!.wordA ? s.pair!.wordB : s.pair!.wordA;

    _vm(c).guess(wrong);

    expect(_state(c).guessedCorrectly, isFalse);
    expect(_state(c).phase, PairPhase.guessed);
  });

  test('playWord plays the synthesized word clip', () async {
    final repo = _MockRepo();
    when(() => repo.synthesize(any()))
        .thenAnswer((_) async => const AudioClip('WORDB64', 'audio/mpeg'));
    final audio = _FakeAudio();
    final c = _container(repo, audio: audio);
    await _vm(c).loadPair();
    audio.played.clear();

    await _vm(c).playWord();

    expect(audio.played, contains('WORDB64'));
  });

  test('record then stopAndScore scores the production', () async {
    final repo = _MockRepo();
    when(() => repo.synthesize(any()))
        .thenAnswer((_) async => const AudioClip('WORDB64', 'audio/mpeg'));
    when(() => repo.scoreAttempt(
          audioBytes: any(named: 'audioBytes'),
          target: any(named: 'target'),
          other: any(named: 'other'),
        )).thenAnswer((_) async => const PairAttempt(
          transcript: 'ship',
          saidTarget: false,
          saidOther: true,
          coaching: 'Long ee for sheep.',
        ));
    final c = _container(repo);
    await _vm(c).loadPair();
    _vm(c).guess(_state(c).spokenWord!);

    await _vm(c).record();
    await _vm(c).stopAndScore();

    expect(_state(c).attempt?.saidOther, isTrue);
    expect(_state(c).phase, PairPhase.reviewing);
  });

  test('a repository error surfaces as state.error', () async {
    final repo = _MockRepo();
    when(() => repo.synthesize(any())).thenThrow(Exception('boom'));
    final c = _container(repo);

    await _vm(c).loadPair();

    expect(_state(c).error, isNotNull);
  });
}

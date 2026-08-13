import 'dart:async';
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

/// playClip always throws — to prove playWord still restores the phase (#343).
class _ThrowingAudio extends _FakeAudio {
  @override
  Future<void> playClip(String audioB64, String mime) async =>
      throw Exception('playback failed');
}

/// playClip blocks until [release], so a test can fire a second (guarded) call
/// while the first is genuinely in flight (#343).
class _GatedAudio extends _FakeAudio {
  final Completer<void> _gate = Completer<void>();
  int playClipCalls = 0;
  void release() => _gate.complete();
  @override
  Future<void> playClip(String audioB64, String mime) async {
    playClipCalls++;
    await _gate.future;
  }
}

class _FakeRecorder implements AudioRecordingService {
  bool cancelled = false;
  @override
  Future<bool> start() async => true;
  @override
  Future<Uint8List?> stop() async => Uint8List.fromList(const [1, 2, 3]);
  @override
  Future<void> cancel() async {
    cancelled = true;
  }
}

MinimalPairsViewModel _vm(ProviderContainer c) =>
    c.read(minimalPairsViewModelProvider.notifier);
MinimalPairsState _state(ProviderContainer c) => c.read(minimalPairsViewModelProvider);

ProviderContainer _container(
  MinimalPairsRepository repo, {
  _FakeAudio? audio,
  _FakeRecorder? recorder,
}) {
  final c = ProviderContainer(
    overrides: [
      minimalPairsRepositoryProvider.overrideWithValue(repo),
      audioPlaybackProvider.overrideWithValue(audio ?? _FakeAudio()),
      audioRecordingProvider.overrideWithValue(recorder ?? _FakeRecorder()),
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

  test('#343: playWord restores the phase and reports an error if playback throws', () async {
    final repo = _MockRepo();
    when(() => repo.synthesize(any()))
        .thenAnswer((_) async => const AudioClip('WORDB64', 'audio/mpeg'));
    final c = _container(repo, audio: _ThrowingAudio());
    await _vm(c).loadPair();
    expect(_state(c).phase, PairPhase.guessing);

    await _vm(c).playWord(); // playClip throws inside

    // Without the try/catch the exception would leak and strand the orb at
    // `playing` forever; it must return to the pre-playback phase + surface it.
    expect(_state(c).phase, PairPhase.guessing);
    expect(_state(c).error, isNotNull);
  });

  test('#343: a rapid double-tap on playWord plays the clip once (busy guard)', () async {
    final repo = _MockRepo();
    when(() => repo.synthesize(any()))
        .thenAnswer((_) async => const AudioClip('WORDB64', 'audio/mpeg'));
    final audio = _GatedAudio();
    final c = _container(repo, audio: audio);
    await _vm(c).loadPair();

    final first = _vm(c).playWord(); // starts, blocks on the gate
    final second = _vm(c).playWord(); // guarded -> immediate no-op
    expect(_state(c).phase, PairPhase.playing);

    audio.release();
    await Future.wait([first, second]);
    expect(audio.playClipCalls, 1); // only one real playback, no concurrent race
    expect(_state(c).phase, PairPhase.guessing);
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

  test('cancel discards an in-progress recording and frees the mic (#222)', () async {
    final repo = _MockRepo();
    when(() => repo.synthesize(any()))
        .thenAnswer((_) async => const AudioClip('WORDB64', 'audio/mpeg'));
    final recorder = _FakeRecorder();
    final c = _container(repo, recorder: recorder);
    await _vm(c).loadPair();
    _vm(c).guess(_state(c).spokenWord!);
    await _vm(c).record();
    expect(_state(c).phase, PairPhase.recording);

    await _vm(c).cancel();

    expect(recorder.cancelled, isTrue); // the mic recording was cancelled
    expect(_state(c).phase, PairPhase.guessed); // resumable at the produce step
  });

  test('a repository error surfaces as state.error', () async {
    final repo = _MockRepo();
    when(() => repo.synthesize(any())).thenThrow(Exception('boom'));
    final c = _container(repo);

    await _vm(c).loadPair();

    expect(_state(c).error, isNotNull);
  });
}

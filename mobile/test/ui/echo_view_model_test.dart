import 'dart:typed_data';

import 'package:apm/src/core/audio/audio_playback_service.dart';
import 'package:apm/src/core/audio/audio_recording_service.dart';
import 'package:apm/src/core/audio/providers.dart';
import 'package:apm/src/data/models/echo.dart';
import 'package:apm/src/data/repositories/echo_repository.dart';
import 'package:apm/src/ui/echo/view_model/echo_state.dart';
import 'package:apm/src/ui/echo/view_model/echo_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockEchoRepository extends Mock implements EchoRepository {}

/// Records what was played, so A/B can be asserted: model clips by their base64,
/// the learner's own recording as the marker 'MINE'.
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
  bool started = false;
  @override
  Future<bool> start() async {
    started = true;
    return true;
  }

  @override
  Future<Uint8List?> stop() async => Uint8List.fromList(const [9, 9, 9]);
  @override
  Future<void> cancel() async {}
}

EchoViewModel _vm(ProviderContainer c) => c.read(echoViewModelProvider.notifier);
EchoState _state(ProviderContainer c) => c.read(echoViewModelProvider);

ProviderContainer _container({
  required EchoRepository repo,
  _FakeAudio? audio,
  _FakeRecorder? recorder,
}) {
  final c = ProviderContainer(
    overrides: [
      echoRepositoryProvider.overrideWithValue(repo),
      audioPlaybackProvider.overrideWithValue(audio ?? _FakeAudio()),
      audioRecordingProvider.overrideWithValue(recorder ?? _FakeRecorder()),
    ],
  );
  addTearDown(c.dispose);
  return c;
}

void main() {
  const phrase = ShadowingPhrase(text: 'The ship is sinking', focus: 'ship_sheep', tip: 'short i');

  test('loadPhrase fetches a phrase and synthesizes the model voice', () async {
    final repo = _MockEchoRepository();
    when(repo.nextPhrase).thenAnswer((_) async => phrase);
    when(() => repo.synthesize(any())).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
    final c = _container(repo: repo);

    await _vm(c).loadPhrase();

    expect(_state(c).phrase?.text, 'The ship is sinking');
    expect(_state(c).modelAudioB64, 'MODELB64');
    expect(_state(c).phase, EchoPhase.idle);
  });

  test('playModel plays the synthesized model clip', () async {
    final repo = _MockEchoRepository();
    when(repo.nextPhrase).thenAnswer((_) async => phrase);
    when(() => repo.synthesize(any())).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
    final audio = _FakeAudio();
    final c = _container(repo: repo, audio: audio);
    await _vm(c).loadPhrase();

    await _vm(c).playModel();

    expect(audio.played, contains('MODELB64'));
  });

  test('record then stopAndScore uploads the attempt and stores the result', () async {
    final repo = _MockEchoRepository();
    when(repo.nextPhrase).thenAnswer((_) async => phrase);
    when(() => repo.synthesize(any())).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
    when(() => repo.scoreAttempt(audioBytes: any(named: 'audioBytes'), targetText: any(named: 'targetText')))
        .thenAnswer((_) async => const AttemptResult(
              transcript: 'the sheep is sinking',
              missedWords: ['ship'],
              coaching: 'Short i in ship.',
            ));
    final c = _container(repo: repo);
    await _vm(c).loadPhrase();

    await _vm(c).record();
    await _vm(c).stopAndScore();

    expect(_state(c).result?.missedWords, ['ship']);
    expect(_state(c).phase, EchoPhase.reviewing);
    expect(_state(c).canReplayMine, isTrue); // recording kept for A/B
  });

  test('playMine replays the learner recording, not the model', () async {
    final repo = _MockEchoRepository();
    when(repo.nextPhrase).thenAnswer((_) async => phrase);
    when(() => repo.synthesize(any())).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
    when(() => repo.scoreAttempt(audioBytes: any(named: 'audioBytes'), targetText: any(named: 'targetText')))
        .thenAnswer((_) async => const AttemptResult(transcript: 'x'));
    final audio = _FakeAudio();
    final c = _container(repo: repo, audio: audio);
    await _vm(c).loadPhrase();
    await _vm(c).record();
    await _vm(c).stopAndScore();
    audio.played.clear();

    await _vm(c).playMine();

    // The learner's own recording is played via playBytes ('MINE'), not the model clip.
    expect(audio.played, contains('MINE'));
    expect(audio.played, isNot(contains('MODELB64')));
  });

  test('nextRound advances the round and loads a new phrase', () async {
    final repo = _MockEchoRepository();
    when(repo.nextPhrase).thenAnswer((_) async => phrase);
    when(() => repo.synthesize(any())).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
    final c = _container(repo: repo);
    await _vm(c).loadPhrase();

    await _vm(c).nextRound();

    expect(_state(c).round, 2);
    expect(_state(c).phase, EchoPhase.idle);
  });

  test('a repository error surfaces as state.error, not a thrown exception', () async {
    final repo = _MockEchoRepository();
    when(repo.nextPhrase).thenThrow(Exception('boom'));
    final c = _container(repo: repo);

    await _vm(c).loadPhrase();

    expect(_state(c).error, isNotNull);
  });
}

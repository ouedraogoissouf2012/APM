import 'dart:async';
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
  Future<void> playClip(String audioB64, String mime) async =>
      played.add(audioB64);
  @override
  Future<void> playBytes(Uint8List bytes, String mime) async =>
      played.add('MINE');
  @override
  Future<void> stop() async {}
}

/// Lets a test control exactly when playClip()/playBytes() resolve, so it
/// can prove something (like a re-entrancy or cross-method guard) about
/// behavior WHILE playback is still in flight, not just its final outcome.
class _GatedAudio implements AudioPlaybackService {
  _GatedAudio(this._gate);
  final Future<void> _gate;
  final List<String> played = [];
  @override
  Future<void> playClip(String audioB64, String mime) async {
    played.add(audioB64);
    await _gate;
  }

  @override
  Future<void> playBytes(Uint8List bytes, String mime) async {
    played.add('MINE');
    await _gate;
  }

  @override
  Future<void> stop() async {}
}

/// Always fails, so a test can prove the caller recovers instead of getting
/// stuck (#330 followup: playModel()/playMine() must restore the phase even
/// when playback itself throws). Counts calls so a test can also prove a
/// guard (like [EchoViewModel._busy]) was released after the failure, not
/// left stuck — a second call that silently no-ops would leave the count
/// unchanged.
class _ThrowingAudio implements AudioPlaybackService {
  int playClipCalls = 0;
  @override
  Future<void> playClip(String audioB64, String mime) async {
    playClipCalls++;
    throw Exception('playback failed');
  }

  @override
  Future<void> playBytes(Uint8List bytes, String mime) async =>
      throw Exception('playback failed');
  @override
  Future<void> stop() async {}
}

/// Fails or succeeds on demand (toggle [shouldFail] between calls), so a
/// test can prove behavior across a fail-then-succeed sequence on the SAME
/// view-model/state — a fresh fake per call can't do that, since it can't
/// carry over state.error from a prior failure.
class _FlakyAudio implements AudioPlaybackService {
  bool shouldFail = true;
  @override
  Future<void> playClip(String audioB64, String mime) async {
    if (shouldFail) throw Exception('playback failed');
  }

  @override
  Future<void> playBytes(Uint8List bytes, String mime) async {
    if (shouldFail) throw Exception('playback failed');
  }

  @override
  Future<void> stop() async {}
}

class _FakeRecorder implements AudioRecordingService {
  bool started = false;
  bool cancelled = false;
  @override
  Future<bool> start() async {
    started = true;
    return true;
  }

  @override
  Future<Uint8List?> stop() async => Uint8List.fromList(const [9, 9, 9]);
  @override
  Future<void> cancel() async {
    cancelled = true;
  }
}

EchoViewModel _vm(ProviderContainer c) =>
    c.read(echoViewModelProvider.notifier);
EchoState _state(ProviderContainer c) => c.read(echoViewModelProvider);

ProviderContainer _container({
  required EchoRepository repo,
  AudioPlaybackService? audio,
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
  const phrase = ShadowingPhrase(
    text: 'The ship is sinking',
    focus: 'ship_sheep',
    tip: 'short i',
  );

  test('loadPhrase fetches a phrase and synthesizes the model voice', () async {
    final repo = _MockEchoRepository();
    when(repo.nextPhrase).thenAnswer((_) async => phrase);
    when(
      () => repo.synthesize(any()),
    ).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
    final c = _container(repo: repo);

    await _vm(c).loadPhrase();

    expect(_state(c).phrase?.text, 'The ship is sinking');
    expect(_state(c).modelAudioB64, 'MODELB64');
    expect(_state(c).phase, EchoPhase.idle);
  });

  test('#342: phase is loadingPhrase while the fetch is in flight, then idle', () async {
    final repo = _MockEchoRepository();
    final gate = Completer<ShadowingPhrase>();
    when(repo.nextPhrase).thenAnswer((_) => gate.future); // blocks mid-load
    when(
      () => repo.synthesize(any()),
    ).thenAnswer((_) async => const AudioClip('B64', 'audio/mpeg'));
    final c = _container(repo: repo);

    final pending = _vm(c).loadPhrase();
    // The previous round's orb is on screen during a reload; while loading it
    // must read as busy (disabled), not idle (an enabled dead tap) — #342.
    expect(_state(c).phase, EchoPhase.loadingPhrase);

    gate.complete(const ShadowingPhrase(text: 'x', focus: 'f', tip: 't'));
    await pending;
    expect(_state(c).phase, EchoPhase.idle);
  });

  test(
    'playModel plays the synthesized model clip and restores the idle phase',
    () async {
      final repo = _MockEchoRepository();
      when(repo.nextPhrase).thenAnswer((_) async => phrase);
      when(
        () => repo.synthesize(any()),
      ).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
      final audio = _FakeAudio();
      final c = _container(repo: repo, audio: audio);
      await _vm(c).loadPhrase();
      expect(_state(c).phase, EchoPhase.idle);

      await _vm(c).playModel();

      expect(audio.played, contains('MODELB64'));
      expect(
        _state(c).phase,
        EchoPhase.idle,
      ); // restored, not left mid-playback
    },
  );

  test(
    'playModel restores the reviewing phase afterwards, not idle (#330)',
    () async {
      final repo = _MockEchoRepository();
      when(repo.nextPhrase).thenAnswer((_) async => phrase);
      when(
        () => repo.synthesize(any()),
      ).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
      when(
        () => repo.scoreAttempt(
          audioBytes: any(named: 'audioBytes'),
          targetText: any(named: 'targetText'),
        ),
      ).thenAnswer(
        (_) async => const AttemptResult(transcript: 'the ship is sinking'),
      );
      final audio = _FakeAudio();
      final c = _container(repo: repo, audio: audio);
      await _vm(c).loadPhrase();
      await _vm(c).record();
      await _vm(c).stopAndScore();
      expect(_state(c).phase, EchoPhase.reviewing); // sanity: mid-review

      await _vm(c).playModel();

      // Re-listening to the model from the review screen ("Modèle" A/B
      // button) must NOT re-arm the orb for a fresh recording while the
      // score/coaching panel is still shown — the OLD behaviour forced
      // phase back to idle regardless of where playModel() was called from.
      expect(_state(c).phase, EchoPhase.reviewing);
      expect(audio.played, contains('MODELB64'));
    },
  );

  test(
    'a re-entrant playModel call while one is already playing is a no-op — '
    'it must not strand the phase at playingModel forever (#330 code review)',
    () async {
      // The exact regression the capture-and-restore fix (#330) can
      // introduce on its own: without a guard, a second call landing before
      // the first resolves would capture restore == playingModel (the
      // first call's own transient phase), and whichever call's restore
      // writes LAST permanently strands the orb — non-interactive, no
      // self-recovery (the UI's "Modèle" button used to allow exactly this
      // via a rapid double-tap).
      final repo = _MockEchoRepository();
      when(repo.nextPhrase).thenAnswer((_) async => phrase);
      when(
        () => repo.synthesize(any()),
      ).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
      when(
        () => repo.scoreAttempt(
          audioBytes: any(named: 'audioBytes'),
          targetText: any(named: 'targetText'),
        ),
      ).thenAnswer(
        (_) async => const AttemptResult(transcript: 'the ship is sinking'),
      );
      final playGate = Completer<void>();
      final audio = _GatedAudio(playGate.future);
      final c = _container(repo: repo, audio: audio);
      await _vm(c).loadPhrase();
      await _vm(c).record();
      await _vm(c).stopAndScore();
      expect(_state(c).phase, EchoPhase.reviewing);

      // playModel()'s synchronous prefix (up to its first real `await`, on
      // the still-open gate) runs before the call even returns a Future — no
      // extra pump/delay needed to observe its effect.
      final first = _vm(c).playModel();
      expect(_state(c).phase, EchoPhase.playingModel);

      // Bounded: without the guard this call would itself await the SAME
      // still-open gate as `first` — a regression here hangs instead of
      // failing an assertion, so time it out fast rather than relying on the
      // suite's default (and much longer) test timeout.
      await _vm(c).playModel().timeout(const Duration(seconds: 2));
      expect(audio.played, hasLength(1)); // only the first call ever played

      playGate.complete();
      await first;

      expect(_state(c).phase, EchoPhase.reviewing); // restored, not stranded
    },
  );

  test('playModel restores the phase even when playback throws, instead of '
      'stranding the orb forever (#330 followup)', () async {
    // Before this fix, a throwing playClip() propagated straight out of
    // playModel() (the try/finally had no catch) — the phase restore on
    // the line after the try block never ran, so the orb (and every A/B
    // control gated on `phase == reviewing`) stayed disabled permanently.
    final repo = _MockEchoRepository();
    when(repo.nextPhrase).thenAnswer((_) async => phrase);
    when(
      () => repo.synthesize(any()),
    ).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
    final audio = _ThrowingAudio();
    final c = _container(repo: repo, audio: audio);
    await _vm(c).loadPhrase();
    expect(_state(c).phase, EchoPhase.idle);

    await _vm(c).playModel();

    expect(_state(c).phase, EchoPhase.idle); // restored, not stuck playing
    expect(_state(c).error, isNotNull); // the failure is surfaced, not silent
    expect(audio.playClipCalls, 1);

    // The guard must also have been released — a second call must still
    // reach playClip(), not silently no-op on a `_busy` stuck true.
    await _vm(c).playModel();
    expect(audio.playClipCalls, 2);
  });

  test('playModel and playMine share the busy guard — one cannot interrupt the '
      'other mid-playback, since both go through the same speaker (#330 '
      'followup)', () async {
    final repo = _MockEchoRepository();
    when(repo.nextPhrase).thenAnswer((_) async => phrase);
    when(
      () => repo.synthesize(any()),
    ).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
    when(
      () => repo.scoreAttempt(
        audioBytes: any(named: 'audioBytes'),
        targetText: any(named: 'targetText'),
      ),
    ).thenAnswer(
      (_) async => const AttemptResult(transcript: 'the ship is sinking'),
    );
    final playGate = Completer<void>();
    final audio = _GatedAudio(playGate.future);
    final c = _container(repo: repo, audio: audio);
    await _vm(c).loadPhrase();
    await _vm(c).record();
    await _vm(c).stopAndScore();
    expect(_state(c).phase, EchoPhase.reviewing);

    final mine = _vm(c).playMine();
    expect(_state(c).phase, EchoPhase.playingMine);

    // Bounded for the same reason as the playModel/playModel race above:
    // without the shared guard this would itself await the same open gate.
    await _vm(c).playModel().timeout(const Duration(seconds: 2));
    expect(audio.played, ['MINE']); // playModel() never actually played

    playGate.complete();
    await mine;

    expect(_state(c).phase, EchoPhase.reviewing); // restored, not stranded
  });

  test('nextRound while a play call is still in flight is a no-op, instead of '
      'advancing the round over stale content (final review sweep)', () async {
    // Before this guard: nextRound() set phase: idle + round: next
    // unconditionally, then called loadPhrase() — which itself silently
    // no-ops on the SAME _busy guard playModel()/playMine() hold during
    // playback. The round counter would advance while phrase/result stay
    // the previous round's, and the in-flight call's own phase restore
    // would later overwrite nextRound()'s `idle` back to `reviewing`.
    final repo = _MockEchoRepository();
    when(repo.nextPhrase).thenAnswer((_) async => phrase);
    when(
      () => repo.synthesize(any()),
    ).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
    when(
      () => repo.scoreAttempt(
        audioBytes: any(named: 'audioBytes'),
        targetText: any(named: 'targetText'),
      ),
    ).thenAnswer(
      (_) async => const AttemptResult(transcript: 'the ship is sinking'),
    );
    final playGate = Completer<void>();
    final audio = _GatedAudio(playGate.future);
    final c = _container(repo: repo, audio: audio);
    await _vm(c).loadPhrase();
    await _vm(c).record();
    await _vm(c).stopAndScore();
    final roundBefore = _state(c).round;
    final resultBefore = _state(c).result;

    final play = _vm(c).playModel();
    expect(_state(c).phase, EchoPhase.playingModel);

    await _vm(c).nextRound();

    // Untouched — the tap was swallowed cleanly, not left half-applied.
    expect(_state(c).round, roundBefore);
    expect(_state(c).result, resultBefore);

    playGate.complete();
    await play;

    expect(_state(c).phase, EchoPhase.reviewing);
  });

  test('a successful playModel clears a stale error left over from a previous '
      'failed attempt (final review sweep)', () async {
    // copyWith keeps `this.error` by default when no `error` argument is
    // passed — so the success branch MUST pass `clearError: true`, or a
    // message from an earlier failed playback keeps showing next to A/B
    // controls the learner just successfully replayed.
    final repo = _MockEchoRepository();
    when(repo.nextPhrase).thenAnswer((_) async => phrase);
    when(
      () => repo.synthesize(any()),
    ).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
    final audio = _FlakyAudio();
    final c = _container(repo: repo, audio: audio);
    await _vm(c).loadPhrase();

    await _vm(c).playModel(); // fails — audio starts in failing mode
    expect(_state(c).error, isNotNull);

    audio.shouldFail = false;
    await _vm(c).playModel(); // succeeds

    expect(_state(c).error, isNull); // stale message cleared, not stuck
  });

  test(
    'record then stopAndScore uploads the attempt and stores the result',
    () async {
      final repo = _MockEchoRepository();
      when(repo.nextPhrase).thenAnswer((_) async => phrase);
      when(
        () => repo.synthesize(any()),
      ).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
      when(
        () => repo.scoreAttempt(
          audioBytes: any(named: 'audioBytes'),
          targetText: any(named: 'targetText'),
        ),
      ).thenAnswer(
        (_) async => const AttemptResult(
          transcript: 'the sheep is sinking',
          missedWords: ['ship'],
          coaching: 'Short i in ship.',
        ),
      );
      final c = _container(repo: repo);
      await _vm(c).loadPhrase();

      await _vm(c).record();
      await _vm(c).stopAndScore();

      expect(_state(c).result?.missedWords, ['ship']);
      expect(_state(c).phase, EchoPhase.reviewing);
      expect(_state(c).canReplayMine, isTrue); // recording kept for A/B
    },
  );

  test('playMine replays the learner recording, not the model', () async {
    final repo = _MockEchoRepository();
    when(repo.nextPhrase).thenAnswer((_) async => phrase);
    when(
      () => repo.synthesize(any()),
    ).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
    when(
      () => repo.scoreAttempt(
        audioBytes: any(named: 'audioBytes'),
        targetText: any(named: 'targetText'),
      ),
    ).thenAnswer((_) async => const AttemptResult(transcript: 'x'));
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
    when(
      () => repo.synthesize(any()),
    ).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
    final c = _container(repo: repo);
    await _vm(c).loadPhrase();

    await _vm(c).nextRound();

    expect(_state(c).round, 2);
    expect(_state(c).phase, EchoPhase.idle);
  });

  test(
    'cancel discards an in-progress recording and frees the mic (#222)',
    () async {
      final repo = _MockEchoRepository();
      when(repo.nextPhrase).thenAnswer((_) async => phrase);
      when(
        () => repo.synthesize(any()),
      ).thenAnswer((_) async => const AudioClip('MODELB64', 'audio/mpeg'));
      final recorder = _FakeRecorder();
      final c = _container(repo: repo, recorder: recorder);
      await _vm(c).loadPhrase();
      await _vm(c).record();
      expect(_state(c).phase, EchoPhase.recording);

      await _vm(c).cancel();

      expect(recorder.cancelled, isTrue); // the mic recording was cancelled
      expect(_state(c).phase, EchoPhase.idle); // back to a resumable idle state
    },
  );

  test(
    'a repository error surfaces as state.error, not a thrown exception',
    () async {
      final repo = _MockEchoRepository();
      when(repo.nextPhrase).thenThrow(Exception('boom'));
      final c = _container(repo: repo);

      await _vm(c).loadPhrase();

      expect(_state(c).error, isNotNull);
    },
  );
}

import 'dart:async';

import 'dart:typed_data';

import 'package:apm/src/core/audio/audio_playback_service.dart';
import 'package:apm/src/core/audio/audio_recording_service.dart';
import 'package:apm/src/core/audio/providers.dart';
import 'package:apm/src/core/audio/voice_take_store.dart';
import 'package:apm/src/core/network/api_exception.dart';
import 'package:apm/src/core/network/providers.dart';
import 'package:apm/src/core/observability/crash_reporter.dart';
import 'package:apm/src/core/observability/providers.dart';
import 'package:apm/src/core/offline/connectivity_controller.dart';
import 'package:apm/src/core/offline/connectivity_monitor.dart';
import 'package:apm/src/core/offline/offline_turn_queue.dart';
import 'package:apm/src/core/offline/pending_turn.dart';
import 'package:apm/src/core/offline/providers.dart';
import 'package:apm/src/core/speech/speech_service.dart';
import 'package:apm/src/data/models/profile.dart';
import 'package:apm/src/data/models/progress_snapshot.dart';
import 'package:apm/src/data/models/streak.dart';
import 'package:apm/src/data/models/turn_correction.dart';
import 'package:apm/src/data/models/voice_consent.dart';
import 'package:apm/src/data/repositories/conversation_repository.dart';
import 'package:apm/src/data/repositories/profile_repository.dart';
import 'package:apm/src/data/repositories/progress_repository.dart';
import 'package:apm/src/data/repositories/review_repository.dart';
import 'package:apm/src/data/repositories/runtime_config_repository.dart';
import 'package:apm/src/data/repositories/streak_repository.dart';
import 'package:apm/src/ui/conversation/view_model/conversation_state.dart';
import 'package:apm/src/ui/conversation/view_model/conversation_view_model.dart';
import 'package:apm/src/ui/history/view_model/progress_view_model.dart';
import 'package:apm/src/ui/home/view_model/streak_view_model.dart';
import 'package:apm/src/ui/privacy/view_model/voice_privacy_view_model.dart';
import 'package:apm/src/ui/profile/view_model/profile_view_model.dart';
import 'package:apm/src/ui/review/view_model/review_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockConversationRepository extends Mock
    implements ConversationRepository {}

class _MockCrashReporter extends Mock implements CrashReporter {}

class _MockStreakRepository extends Mock implements StreakRepository {}

class _MockReviewRepository extends Mock implements ReviewRepository {}

class _MockProgressRepository extends Mock implements ProgressRepository {}

/// In-memory offline queue — overridden by default in [_container] so
/// ConversationViewModel.start()'s new connectivity refresh() (#311) never
/// touches the real secure-storage-backed queue in tests.
class _InMemoryOfflineQueue implements OfflineTurnQueue {
  final List<PendingTurn> _turns = [];

  @override
  Future<void> enqueue(PendingTurn turn) async => _turns.add(turn);

  @override
  Future<List<PendingTurn>> pending() async => List.of(_turns);

  @override
  Future<void> remove(String idempotencyKey) async =>
      _turns.removeWhere((t) => t.idempotencyKey == idempotencyKey);
}

/// Records which audio clips were played, so tests can assert the server voice
/// is used (and the on-device voice is not).
class _FakeAudio implements AudioPlaybackService {
  final List<String> played = [];
  @override
  Future<void> playClip(String audioB64, String mime) async {
    played.add(audioB64);
  }

  @override
  Future<void> playBytes(Uint8List bytes, String mime) async {
    played.add('bytes');
  }

  @override
  Future<void> stop() async {}
}

/// A playback service whose [playClip] blocks until [release] is called for that
/// clip, so a test can assert the text stream is not held up waiting for audio.
/// [release] is level-triggered: clips that arrive after it are let through too,
/// so there is no race with the background player creating gates lazily.
class _SlowAudio implements AudioPlaybackService {
  final List<String> played = [];
  final List<Completer<void>> _gates = [];
  bool _released = false;

  @override
  Future<void> playClip(String audioB64, String mime) async {
    if (!_released) {
      final gate = Completer<void>();
      _gates.add(gate);
      await gate.future;
    }
    played.add(audioB64);
  }

  void release() {
    _released = true;
    for (final g in _gates) {
      if (!g.isCompleted) g.complete();
    }
  }

  @override
  Future<void> playBytes(Uint8List bytes, String mime) async {}

  @override
  Future<void> stop() async {}
}

/// Neural-audio player a test can drive: [playClip] blocks until [release] (or
/// [stop]) so a clip can be held "playing", records [stopCalls], and signals
/// [firstPlayStarted] when the first clip begins.
class _ControllableAudio implements AudioPlaybackService {
  final List<String> played = [];
  int stopCalls = 0;
  final firstPlayStarted = Completer<void>();
  final List<Completer<void>> _gates = [];
  bool _open = false;

  @override
  Future<void> playClip(String audioB64, String mime) async {
    if (!firstPlayStarted.isCompleted) firstPlayStarted.complete();
    if (!_open) {
      final gate = Completer<void>();
      _gates.add(gate);
      await gate.future;
    }
    played.add(audioB64);
  }

  void release() {
    _open = true;
    for (final g in _gates) {
      if (!g.isCompleted) g.complete();
    }
  }

  @override
  Future<void> playBytes(Uint8List bytes, String mime) async {}

  @override
  Future<void> stop() async {
    stopCalls++;
    release();
  }
}

/// A neural-audio player whose [stop] deliberately does NOT unblock an
/// in-flight [playClip] (unlike every other fake here) — simulating what
/// native_player.dart/web_player.dart's stop() used to do before #314. Proves
/// that ReplyPlayback.cancel() unblocks awaitPlayback via its OWN bookkeeping
/// (`_playbackTask = null`), not by depending on the player to cooperate.
class _StubbornAudio implements AudioPlaybackService {
  final firstPlayStarted = Completer<void>();
  final Completer<void> _gate = Completer<void>();
  int stopCalls = 0;

  @override
  Future<void> playClip(String audioB64, String mime) async {
    if (!firstPlayStarted.isCompleted) firstPlayStarted.complete();
    await _gate.future;
  }

  @override
  Future<void> playBytes(Uint8List bytes, String mime) async {}

  @override
  Future<void> stop() async {
    stopCalls++; // deliberately does not complete _gate
  }

  /// Lets the orphaned clip unwind so nothing is left hanging after the test.
  void release() {
    if (!_gate.isCompleted) _gate.complete();
  }
}

/// Fake recorder that yields fixed bytes on stop, for the push-to-talk path.
class _FakeRecorder implements AudioRecordingService {
  bool started = false;
  bool cancelled = false;

  @override
  Future<bool> start() async {
    started = true;
    return true;
  }

  @override
  Future<Uint8List?> stop() async => Uint8List.fromList(const [1, 2, 3]);

  @override
  Future<void> cancel() async {
    cancelled = true;
  }
}

class _MockProfileRepository extends Mock implements ProfileRepository {}

/// Connectivity monitor that never emits — most tests here don't exercise the
/// OS-level reconnect signal (#404); connectivity_controller_test.dart covers
/// that behavior directly. Keeps ConnectivityController.build() from touching
/// the real connectivity_plus platform channel in these unit tests.
class _NoopConnectivityMonitor implements ConnectivityMonitor {
  @override
  Stream<bool> get onConnectivityChanged => const Stream.empty();
}

class _FakeSpeech implements SpeechService {
  /// [recognized] is heard on the first turn; [thenSilence] makes every later
  /// turn return empty (so an auto-chaining loop terminates naturally).
  _FakeSpeech(this.recognized, {this.ready = true, this.thenSilence = true});

  final String recognized;
  final bool ready;
  final bool thenSilence;

  int listenCalls = 0;
  final List<String> spoken = [];
  String? spokenText;
  String? languageTag;
  bool stopped = false;

  /// Simulates a recognizer error: when set, [listenOnce] returns empty (as the
  /// real service does on failure) and exposes this via [lastError].
  String? errorOnListen;

  @override
  String? get lastError => errorOnListen;

  @override
  Future<bool> initialize() async => ready;
  @override
  Future<void> setLanguage(String languageTag) async {
    this.languageTag = languageTag;
  }

  @override
  Future<String> listenOnce({void Function(String words)? onPartial}) async {
    listenCalls++;
    if (errorOnListen != null) return '';
    if (listenCalls == 1) return recognized;
    return thenSilence ? '' : recognized;
  }

  @override
  Future<void> speak(String text) async {
    spokenText = text;
    spoken.add(text);
  }

  @override
  Future<void> stopListening() async {
    stopped = true;
  }
}

/// Speech fake whose [listenOnce] blocks until the test releases it, so the
/// view model can be observed mid-turn (e.g. to test stop/interrupt).
class _BlockingSpeech implements SpeechService {
  _BlockingSpeech(this.firstText);

  final String firstText;
  final listenStarted = Completer<void>();
  Completer<String>? _pending;
  int _liveListens = 0;
  int maxConcurrentListens = 0;
  bool stopped = false;

  @override
  String? get lastError => null;

  @override
  Future<bool> initialize() async => true;
  @override
  Future<void> setLanguage(String languageTag) async {}

  @override
  Future<String> listenOnce({void Function(String words)? onPartial}) {
    _liveListens++;
    if (_liveListens > maxConcurrentListens) {
      maxConcurrentListens = _liveListens;
    }
    _pending = Completer<String>();
    if (!listenStarted.isCompleted) listenStarted.complete();
    return _pending!.future.whenComplete(() => _liveListens--);
  }

  void releaseListen(String text) {
    if (_pending != null && !_pending!.isCompleted) _pending!.complete(text);
  }

  @override
  Future<void> speak(String text) async {}

  @override
  Future<void> stopListening() async {
    stopped = true;
  }
}

/// Records which spoken takes were captured on-device, to assert the audible
/// before/after capture (#199).
class _SpyTakeStore implements VoiceTakeStore {
  final List<({String skill, int len})> saved = [];
  final List<String> erasedCalls = [];
  Object? throwOnSave;
  @override
  Future<void> saveTake(String skill, Uint8List bytes) async {
    final err = throwOnSave;
    if (err != null) throw err;
    saved.add((skill: skill, len: bytes.length));
  }

  @override
  Future<VoiceTakes?> takesFor(String skill) async => null;
  @override
  Future<void> eraseAll() async => erasedCalls.add('eraseAll');
  @override
  Future<void> deleteSkill(String skill) async {}
}

ProviderContainer _container(
  ConversationRepository repo,
  SpeechService speech, {
  bool serverTts = false,
  bool serverStt = false,
  AudioPlaybackService? audio,
  AudioRecordingService? recorder,
  VoiceTakeStore? takeStore,
  CrashReporter? crashReporter,
  OfflineTurnQueue? offlineQueue,
}) {
  final c = ProviderContainer(
    overrides: [
      conversationRepositoryProvider.overrideWithValue(repo),
      speechServiceProvider.overrideWithValue(speech),
      audioPlaybackProvider.overrideWithValue(audio ?? _FakeAudio()),
      audioRecordingProvider.overrideWithValue(recorder ?? _FakeRecorder()),
      // start() now calls connectivityControllerProvider.notifier.refresh()
      // (#311), which reads this — default to an in-memory fake so tests
      // never hit the real secure-storage-backed queue.
      offlineTurnQueueProvider.overrideWithValue(offlineQueue ?? _InMemoryOfflineQueue()),
      // #404: ConnectivityController.build() now subscribes to this — override
      // with a fake so tests never touch the real connectivity_plus platform
      // channel (unavailable/unmocked here).
      connectivityMonitorProvider.overrideWithValue(_NoopConnectivityMonitor()),
      if (takeStore != null) voiceTakeStoreProvider.overrideWithValue(takeStore),
      if (crashReporter != null) crashReporterProvider.overrideWithValue(crashReporter),
      // Avoid any real /config network fetch in tests.
      runtimeConfigProvider.overrideWith(
        (ref) async => RuntimeConfig(
          demoMode: false,
          serverTts: serverTts,
          serverStt: serverStt,
        ),
      ),
      // effectiveServerSttProvider (#225) also watches consent; default to the
      // protective consent (transcription on) so the STT path behaves as before
      // unless a test overrides it. Without this the provider fetches for real.
      voiceConsentProvider.overrideWith(
        (ref) async => const VoiceConsent(
          transcription: true,
          scoring: false,
          b2bShare: false,
          modelTraining: false,
        ),
      ),
    ],
  );
  addTearDown(c.dispose);
  return c;
}

ConversationRepository _repoReturning(int sessionId, {String? reply}) {
  final repo = _MockConversationRepository();
  when(
    () => repo.startSession(
      mode: any(named: 'mode'),
      scenarioId: any(named: 'scenarioId'),
    ),
  ).thenAnswer((_) async => sessionId);
  if (reply != null) {
    // The VM consumes the streaming path; yield the reply as one sentence.
    when(() => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey')))
        .thenAnswer((_) => Stream.value(ReplySentence(reply)));
  }
  return repo;
}

void main() {
  setUpAll(() => registerFallbackValue(StackTrace.empty));

  test('start opens a session and stores its id', () async {
    final c = _container(_repoReturning(42), _FakeSpeech(''));
    await c.read(conversationViewModelProvider.notifier).start();
    expect(c.read(conversationViewModelProvider).sessionId, 42);
    expect(
      c.read(conversationViewModelProvider).turns.single.role,
      'assistant',
    );
  });

  test('start resumes the active session when start returns 409', () async {
    final repo = _MockConversationRepository();
    when(
      () => repo.startSession(
        mode: any(named: 'mode'),
        scenarioId: any(named: 'scenarioId'),
      ),
    ).thenThrow(
      const ApiException(
        statusCode: 409,
        code: 'ActiveSessionExistsError',
        message: 'A session is already in progress',
      ),
    );
    when(() => repo.getActiveSession()).thenAnswer(
      (_) async => const ActiveSessionData(
        sessionId: 77,
        mode: 'free',
        scenarioId: null,
        turns: [
          (role: 'user', content: 'hi'),
          (role: 'assistant', content: 'Hello again!'),
        ],
      ),
    );
    final c = _container(repo, _FakeSpeech(''));

    await c.read(conversationViewModelProvider.notifier).start();

    final state = c.read(conversationViewModelProvider);
    expect(state.sessionId, 77);
    expect(state.turns.map((t) => t.content).toList(), ['hi', 'Hello again!']);
  });

  test('launching a specific mission on 409 ends the unrelated active session '
      'and starts the mission (does not resume the old chat)', () async {
    // #196: a mission the learner just prepared must not be swallowed by an
    // unrelated active session — end that one and start the requested mission.
    final repo = _MockConversationRepository();
    var startCalls = 0;
    when(
      () => repo.startSession(
        mode: any(named: 'mode'),
        scenarioId: any(named: 'scenarioId'),
        missionId: any(named: 'missionId'),
      ),
    ).thenAnswer((_) async {
      startCalls++;
      if (startCalls == 1) {
        throw const ApiException(
          statusCode: 409,
          code: 'ActiveSessionExistsError',
          message: 'A session is already in progress',
        );
      }
      return 88; // the fresh mission session
    });
    when(() => repo.getActiveSession()).thenAnswer(
      (_) async => const ActiveSessionData(
        sessionId: 59, // an old, unrelated free chat
        mode: 'free',
        scenarioId: null,
        turns: [(role: 'assistant', content: 'old chat')],
      ),
    );
    when(() => repo.endSession(any())).thenAnswer((_) async {});
    final c = _container(repo, _FakeSpeech(''));

    await c
        .read(conversationViewModelProvider.notifier)
        .start(mode: 'mission', missionId: 7);

    verify(() => repo.endSession(59)).called(1); // old session ended
    final state = c.read(conversationViewModelProvider);
    expect(state.sessionId, 88); // the mission started, NOT the old chat resumed
    expect(state.turns.map((t) => t.content).toList(), isNot(contains('old chat')));
  });

  test('start surfaces a quota-exhausted state on 402 (no uncaught error)',
      () async {
    final repo = _MockConversationRepository();
    when(
      () => repo.startSession(
        mode: any(named: 'mode'),
        scenarioId: any(named: 'scenarioId'),
      ),
    ).thenThrow(
      const ApiException(
        statusCode: 402,
        code: 'QuotaExhaustedError',
        message: 'Daily free quota exhausted',
      ),
    );
    final c = _container(repo, _FakeSpeech(''));

    // Must NOT throw — the learner sees a friendly paywall state instead.
    await c.read(conversationViewModelProvider.notifier).start();

    final state = c.read(conversationViewModelProvider);
    expect(state.quotaExhausted, isTrue);
    expect(state.sessionId, isNull);
    verifyNever(() => repo.getActiveSession());
  });

  test('#437: start surfaces a 500 as state.error instead of throwing', () async {
    final repo = _MockConversationRepository();
    when(
      () => repo.startSession(
        mode: any(named: 'mode'),
        scenarioId: any(named: 'scenarioId'),
      ),
    ).thenThrow(
      const ApiException(
        statusCode: 500,
        code: 'InternalError',
        message: 'boom',
      ),
    );
    final reporter = _MockCrashReporter();
    final c = _container(repo, _FakeSpeech(''), crashReporter: reporter);

    await c.read(conversationViewModelProvider.notifier).start();
    final state = c.read(conversationViewModelProvider);
    expect(state.sessionId, isNull);
    expect(state.error, 'boom');
    verify(
      () => reporter.captureError(
        any(),
        any(),
        context: any(named: 'context'),
      ),
    ).called(1);
  });

  test("start applies the learner's accent to the speech service", () async {
    final profileRepo = _MockProfileRepository();
    when(profileRepo.getProfile).thenAnswer(
      (_) async => const Profile(
        interests: [],
        goal: null,
        correctionIntensity: 'gentle',
        accent: 'uk',
      ),
    );
    final speech = _FakeSpeech('');
    final c = ProviderContainer(
      overrides: [
        conversationRepositoryProvider.overrideWithValue(_repoReturning(3)),
        speechServiceProvider.overrideWithValue(speech),
        profileRepositoryProvider.overrideWithValue(profileRepo),
        offlineTurnQueueProvider.overrideWithValue(_InMemoryOfflineQueue()),
        connectivityMonitorProvider.overrideWithValue(_NoopConnectivityMonitor()),
      ],
    );
    addTearDown(c.dispose);

    await c.read(conversationViewModelProvider.notifier).start();

    expect(speech.languageTag, 'en-GB');
  });

  test('start falls back to US English when the profile fails to load', () async {
    final profileRepo = _MockProfileRepository();
    when(
      profileRepo.getProfile,
    ).thenAnswer((_) async => throw Exception('offline'));
    final speech = _FakeSpeech('');
    final c = ProviderContainer(
      overrides: [
        conversationRepositoryProvider.overrideWithValue(_repoReturning(3)),
        speechServiceProvider.overrideWithValue(speech),
        profileRepositoryProvider.overrideWithValue(profileRepo),
        offlineTurnQueueProvider.overrideWithValue(_InMemoryOfflineQueue()),
        connectivityMonitorProvider.overrideWithValue(_NoopConnectivityMonitor()),
      ],
    );
    addTearDown(c.dispose);

    await c.read(conversationViewModelProvider.notifier).start();

    expect(speech.languageTag, 'en-US');
  });

  test('start reports when microphone is unavailable', () async {
    final c = _container(_repoReturning(42), _FakeSpeech('', ready: false));
    await c.read(conversationViewModelProvider.notifier).start();
    expect(
      c.read(conversationViewModelProvider).error,
      'Microphone is not available',
    );
  });

  test(
    'listenAndRespond adds user + assistant turns and speaks the reply',
    () async {
      final speech = _FakeSpeech('i is happy');
      final c = _container(_repoReturning(1, reply: 'You are happy!'), speech);
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      await vm.listenAndRespond();

      final state = c.read(conversationViewModelProvider);
      expect(state.turns.map((t) => t.content).toList(), [
        "Hi, let's practise English. What would you like to talk about today?",
        'i is happy',
        'You are happy!',
      ]);
      expect(state.status, ConversationStatus.idle);
      expect(speech.spokenText, 'You are happy!');
    },
  );

  test('speaks each streamed sentence as it arrives (not one block)',
      () async {
    // The reply streams as two sentences; both must be spoken, in order, and
    // the transcript shows them joined as one growing assistant turn.
    final repo = _MockConversationRepository();
    when(
      () => repo.startSession(
        mode: any(named: 'mode'),
        scenarioId: any(named: 'scenarioId'),
      ),
    ).thenAnswer((_) async => 1);
    when(() => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey'))).thenAnswer(
      (_) => Stream.fromIterable(const [
        ReplySentence('Nice weekend?'),
        ReplySentence('What did you do?'),
      ]),
    );
    final speech = _FakeSpeech('i went out');
    final c = _container(repo, speech);
    final vm = c.read(conversationViewModelProvider.notifier);

    await vm.start();
    await vm.listenAndRespond();

    // Each sentence was spoken separately, in order.
    expect(speech.spoken, ['Nice weekend?', 'What did you do?']);
    // The transcript shows the full reply joined.
    final last = c.read(conversationViewModelProvider).turns.last;
    expect(last.role, 'assistant');
    expect(last.content, 'Nice weekend? What did you do?');
  });

  test('server STT: records, transcribes via /transcribe, then responds',
      () async {
    final repo = _MockConversationRepository();
    when(
      () => repo.startSession(
        mode: any(named: 'mode'),
        scenarioId: any(named: 'scenarioId'),
      ),
    ).thenAnswer((_) async => 1);
    when(() => repo.transcribe(any())).thenAnswer((_) async => 'hello how are you');
    when(() => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey'))).thenAnswer(
      (_) => Stream.value(const ReplySentence('I am well, thank you.')),
    );
    final recorder = _FakeRecorder();
    final c = _container(
      repo,
      _FakeSpeech(''),
      serverStt: true,
      recorder: recorder,
    );
    final vm = c.read(conversationViewModelProvider.notifier);

    await vm.start();
    // First tap: start recording (push-to-talk).
    await vm.listenAndRespond();
    expect(recorder.started, isTrue);
    expect(c.read(conversationViewModelProvider).status,
        ConversationStatus.listening);
    // Second tap: stop -> transcribe -> respond.
    await vm.stopConversation();

    verify(() => repo.transcribe(any())).called(1);
    final turns = c.read(conversationViewModelProvider).turns;
    expect(turns.any((t) => t.role == 'user' && t.content == 'hello how are you'),
        isTrue);
    expect(
      turns.any((t) => t.role == 'assistant' && t.content == 'I am well, thank you.'),
      isTrue,
    );
  });

  test('a scenario take is captured on-device for the audible before/after (#199)',
      () async {
    final repo = _MockConversationRepository();
    when(
      () => repo.startSession(
        mode: any(named: 'mode'),
        scenarioId: any(named: 'scenarioId'),
        missionId: any(named: 'missionId'),
      ),
    ).thenAnswer((_) async => 1);
    when(() => repo.transcribe(any())).thenAnswer((_) async => 'hello');
    when(() => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey')))
        .thenAnswer((_) => Stream.value(const ReplySentence('hi')));
    final store = _SpyTakeStore();
    final c = _container(repo, _FakeSpeech(''), serverStt: true, takeStore: store);
    final vm = c.read(conversationViewModelProvider.notifier);

    await vm.start(mode: 'scenario', scenarioId: 'job_interview');
    await vm.listenAndRespond(); // push-to-talk: start recording
    await vm.stopConversation(); // stop -> transcribe -> capture the take

    // The _FakeRecorder yields 3 bytes; keyed by the scenario skill.
    expect(store.saved, [(skill: 'job_interview', len: 3)]);
  });

  test('a free session captures no take — there is no skill to key it (#199)',
      () async {
    final repo = _MockConversationRepository();
    when(
      () => repo.startSession(
        mode: any(named: 'mode'),
        scenarioId: any(named: 'scenarioId'),
        missionId: any(named: 'missionId'),
      ),
    ).thenAnswer((_) async => 1);
    when(() => repo.transcribe(any())).thenAnswer((_) async => 'hello');
    when(() => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey')))
        .thenAnswer((_) => Stream.value(const ReplySentence('hi')));
    final store = _SpyTakeStore();
    final c = _container(repo, _FakeSpeech(''), serverStt: true, takeStore: store);
    final vm = c.read(conversationViewModelProvider.notifier);

    await vm.start(); // free mode, no scenario
    await vm.listenAndRespond();
    await vm.stopConversation();

    expect(store.saved, isEmpty);
  });

  test('a voice take capture failure is reported, not silently swallowed (#236)',
      () async {
    final repo = _MockConversationRepository();
    when(
      () => repo.startSession(
        mode: any(named: 'mode'),
        scenarioId: any(named: 'scenarioId'),
        missionId: any(named: 'missionId'),
      ),
    ).thenAnswer((_) async => 1);
    when(() => repo.transcribe(any())).thenAnswer((_) async => 'hello');
    when(() => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey')))
        .thenAnswer((_) => Stream.value(const ReplySentence('hi')));
    final store = _SpyTakeStore()..throwOnSave = StateError('encryption key unreadable');
    final reporter = _MockCrashReporter();
    final c = _container(
      repo,
      _FakeSpeech(''),
      serverStt: true,
      takeStore: store,
      crashReporter: reporter,
    );
    final vm = c.read(conversationViewModelProvider.notifier);

    await vm.start(mode: 'scenario', scenarioId: 'job_interview');
    await vm.listenAndRespond();
    await vm.stopConversation(); // capture fails, but the turn must still proceed

    verify(
      () => reporter.captureError(
        any(),
        any(),
        context: any(named: 'context'),
        data: {'skill': 'job_interview'},
      ),
    ).called(1);
    // Best-effort (#199): a capture failure never breaks the conversation turn.
    expect(c.read(conversationViewModelProvider).turns, isNotEmpty);
  });

  test('plays server audio and skips the on-device voice when serverTts is on',
      () async {
    final repo = _MockConversationRepository();
    when(
      () => repo.startSession(
        mode: any(named: 'mode'),
        scenarioId: any(named: 'scenarioId'),
      ),
    ).thenAnswer((_) async => 1);
    when(() => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey'))).thenAnswer(
      (_) => Stream.fromIterable(const [
        ReplySentence('Good.'),
        AudioClip('QUJD', 'audio/mpeg'), // "ABC" in base64
      ]),
    );
    final speech = _FakeSpeech('i went out');
    final audio = _FakeAudio();
    final c = _container(repo, speech, serverTts: true, audio: audio);
    final vm = c.read(conversationViewModelProvider.notifier);

    await vm.start();
    await vm.listenAndRespond();
    await vm.awaitPlaybackForTest();

    // The neural clip was played, and the robotic on-device voice was NOT used.
    expect(audio.played, ['QUJD']);
    expect(speech.spoken, isEmpty);
    // The transcript still shows the reply text.
    expect(
      c.read(conversationViewModelProvider).turns.last.content,
      'Good.',
    );
  });

  test('slow per-sentence audio does not block the text stream (#100 regression)',
      () async {
    // The bug: awaiting each clip's playback INSIDE the SSE loop froze the text —
    // sentence 2 only appeared after sentence 1's audio finished playing, and a
    // stuck clip hung the whole turn. Audio must play in the background while the
    // text keeps streaming.
    final repo = _MockConversationRepository();
    when(
      () => repo.startSession(mode: any(named: 'mode'), scenarioId: any(named: 'scenarioId')),
    ).thenAnswer((_) async => 1);
    when(() => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey'))).thenAnswer(
      (_) => Stream.fromIterable(const [
        ReplySentence('First.'),
        AudioClip('QQ==', 'audio/mpeg'),
        ReplySentence('Second.'),
        AudioClip('Qg==', 'audio/mpeg'),
      ]),
    );
    final speech = _FakeSpeech('hi');
    final audio = _SlowAudio(); // each playClip blocks until released
    final c = _container(repo, speech, serverTts: true, audio: audio);
    final vm = c.read(conversationViewModelProvider.notifier);

    await vm.start();
    final loop = vm.listenAndRespond();

    // The FULL text is shown even though NO clip has finished playing yet — the
    // stream was not blocked by playback (the clips are still gated here).
    await pumpEventQueue();
    expect(c.read(conversationViewModelProvider).turns.last.content, 'First. Second.');

    // Now let the clips finish: both play, in order, and the loop completes.
    audio.release();
    await loop;
    expect(audio.played, ['QQ==', 'Qg==']);
  });

  test('stopConversation stops in-flight neural reply audio', () async {
    // With server TTS, the reply plays as neural clips in the background. Tapping
    // stop must actually silence them — not leave the assistant talking after the
    // learner ended the turn.
    final repo = _MockConversationRepository();
    when(
      () => repo.startSession(
        mode: any(named: 'mode'),
        scenarioId: any(named: 'scenarioId'),
      ),
    ).thenAnswer((_) async => 1);
    when(() => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey'))).thenAnswer(
      (_) => Stream.fromIterable(const [
        ReplySentence('Bye.'),
        AudioClip('QUJD', 'audio/mpeg'),
      ]),
    );
    final audio = _ControllableAudio(); // the clip stays "playing"
    final c = _container(repo, _FakeSpeech('hi'), serverTts: true, audio: audio);
    final vm = c.read(conversationViewModelProvider.notifier);

    await vm.start();
    final loop = vm.listenAndRespond();
    await audio.firstPlayStarted.future; // the neural clip is now playing

    await vm.stopConversation();
    expect(audio.stopCalls, 1); // the voice was actually stopped

    audio.release(); // let anything still pending unwind
    await loop;
  });

  test('hands-free loop waits for neural audio to finish before listening '
      'again (no mic-during-audio echo)', () async {
    // The bug: with server TTS the neural clip plays in the background; the loop
    // must NOT reopen the mic while it is still playing, or the device recognizer
    // captures the assistant's own voice.
    final repo = _MockConversationRepository();
    when(
      () => repo.startSession(
        mode: any(named: 'mode'),
        scenarioId: any(named: 'scenarioId'),
      ),
    ).thenAnswer((_) async => 1);
    when(() => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey'))).thenAnswer(
      (_) => Stream.fromIterable(const [
        ReplySentence('More?'),
        AudioClip('QQ==', 'audio/mpeg'),
      ]),
    );
    final audio = _ControllableAudio(); // clip blocks until released
    final speech = _FakeSpeech('hi', thenSilence: true);
    final c = _container(repo, speech, serverTts: true, audio: audio);
    final vm = c.read(conversationViewModelProvider.notifier);

    await vm.start();
    final loop = vm.listenAndRespond();
    await audio.firstPlayStarted.future; // reply produced; clip now playing
    await pumpEventQueue();

    // The mic was NOT reopened while the clip is still playing.
    expect(speech.listenCalls, 1);

    audio.release(); // clip finishes -> the loop may continue
    await loop;

    // Only after the audio finished did the loop listen again.
    expect(speech.listenCalls, greaterThanOrEqualTo(2));
    expect(audio.played, ['QQ==']);
  });

  test('attaches a streamed correction to the learner turn', () async {
    final repo = _MockConversationRepository();
    when(
      () => repo.startSession(
        mode: any(named: 'mode'),
        scenarioId: any(named: 'scenarioId'),
      ),
    ).thenAnswer((_) async => 1);
    when(() => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey'))).thenAnswer(
      (_) => Stream.fromIterable(const [
        ReplySentence('Good.'),
        CorrectionEvent(
          TurnCorrection(
            original: 'i is happy',
            correction: 'I am happy',
            rule: "Use 'am' with 'I'.",
            alternatives: ["I'm happy"],
          ),
        ),
      ]),
    );
    final c = _container(repo, _FakeSpeech('i is happy'));
    final vm = c.read(conversationViewModelProvider.notifier);

    await vm.start();
    await vm.listenAndRespond();

    final userTurn = c
        .read(conversationViewModelProvider)
        .turns
        .firstWhere((t) => t.role == 'user');
    expect(userTurn.correction, isNotNull);
    expect(userTurn.correction!.correction, 'I am happy');
    expect(userTurn.correction!.alternatives, ["I'm happy"]);
  });

  test('empty recognized speech stays idle and sends nothing', () async {
    final repo = _repoReturning(1, reply: 'unused');
    final c = _container(repo, _FakeSpeech('   '));
    final vm = c.read(conversationViewModelProvider.notifier);

    await vm.start();
    await vm.listenAndRespond();

    final state = c.read(conversationViewModelProvider);
    expect(state.turns.length, 1);
    expect(state.turns.single.role, 'assistant');
    expect(state.status, ConversationStatus.idle);
    verifyNever(() => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey')));
  });

  test('end closes the session and resets state', () async {
    final repo = _repoReturning(9);
    when(() => repo.endSession(any())).thenAnswer((_) async {});
    final c = _container(repo, _FakeSpeech(''));
    final vm = c.read(conversationViewModelProvider.notifier);

    await vm.start();
    await vm.end();

    expect(c.read(conversationViewModelProvider).sessionId, isNull);
    verify(() => repo.endSession(9)).called(1);
  });

  test('end() invalidates the streak/review/progress providers', () async {
    // After ending a session, the cached streak/review/progress data must be
    // cleared so the home/history/review screens show fresh data, not stale
    // cached values (#237).
    var streakCallCount = 0;
    var reviewCallCount = 0;
    var progressCallCount = 0;

    final streakRepo = _MockStreakRepository();
    final reviewRepo = _MockReviewRepository();
    final progressRepo = _MockProgressRepository();

    when(() => streakRepo.load()).thenAnswer((_) async {
      streakCallCount++;
      return const Streak(
        currentStreak: 5,
        longestStreak: 10,
        weeklyGoalMinutes: 60,
        minutesThisWeek: 30,
      );
    });
    when(() => reviewRepo.dueItems()).thenAnswer((_) async {
      reviewCallCount++;
      return [];
    });
    when(() => progressRepo.load()).thenAnswer((_) async {
      progressCallCount++;
      return const ProgressSnapshot(
        sessions: [],
        cefrTrend: [],
        recurringErrors: [],
      );
    });

    final conversationRepo = _repoReturning(9);
    when(() => conversationRepo.endSession(any())).thenAnswer((_) async {});

    final c = ProviderContainer(
      overrides: [
        conversationRepositoryProvider.overrideWithValue(conversationRepo),
        speechServiceProvider.overrideWithValue(_FakeSpeech('')),
        audioPlaybackProvider.overrideWithValue(_FakeAudio()),
        audioRecordingProvider.overrideWithValue(_FakeRecorder()),
        streakRepositoryProvider.overrideWithValue(streakRepo),
        reviewRepositoryProvider.overrideWithValue(reviewRepo),
        progressRepositoryProvider.overrideWithValue(progressRepo),
        offlineTurnQueueProvider.overrideWithValue(_InMemoryOfflineQueue()),
        connectivityMonitorProvider.overrideWithValue(_NoopConnectivityMonitor()),
        runtimeConfigProvider.overrideWith(
          (ref) async => const RuntimeConfig(
            demoMode: false,
            serverTts: false,
            serverStt: false,
          ),
        ),
      ],
    );
    addTearDown(c.dispose);

    final vm = c.read(conversationViewModelProvider.notifier);
    await vm.start();

    // Load the providers to populate the cache
    await c.read(streakProvider.future);
    await c.read(reviewProvider.future);
    await c.read(progressProvider.future);

    expect(streakCallCount, 1);
    expect(reviewCallCount, 1);
    expect(progressCallCount, 1);

    // Call end() which should invalidate all three providers
    await vm.end();

    // Reading them again should trigger fresh fetches
    await c.read(streakProvider.future);
    await c.read(reviewProvider.future);
    await c.read(progressProvider.future);

    // Each provider should have been evaluated twice
    expect(streakCallCount, 2);
    expect(reviewCallCount, 2);
    expect(progressCallCount, 2);
  });

  test('cancel stops the mic but keeps the session open (#222)', () async {
    // Leaving the screen / backgrounding must silence the mic WITHOUT ending the
    // session server-side (so it can resume) — unlike end().
    final repo = _repoReturning(9);
    // Deliberately do NOT stub endSession: cancel must never call it.
    final speech = _FakeSpeech('');
    final c = _container(repo, speech);
    final vm = c.read(conversationViewModelProvider.notifier);

    await vm.start();
    await vm.cancel();

    expect(speech.stopped, isTrue); // the recognizer was stopped
    expect(c.read(conversationViewModelProvider).sessionId, 9); // session kept
    expect(c.read(conversationViewModelProvider).status, ConversationStatus.idle);
    verifyNever(() => repo.endSession(any())); // NOT finalized
  });

  test('cancel halts an in-progress hands-free loop without ending it (#222)',
      () async {
    // The acute case: a hands-free loop is listening when the learner backgrounds
    // the app. cancel() must stop the recognizer and the loop, leaving the session
    // open — the mic cannot keep running off-screen.
    final repo = _repoReturning(5, reply: 'Go on');
    final speech = _BlockingSpeech('more');
    final c = _container(repo, speech);
    final vm = c.read(conversationViewModelProvider.notifier);

    await vm.start();
    unawaited(vm.listenAndRespond());
    await speech.listenStarted.future; // a turn is genuinely listening

    await vm.cancel();
    speech.releaseListen(''); // the recognizer returns empty after the stop

    expect(speech.stopped, isTrue);
    expect(c.read(conversationViewModelProvider).sessionId, 5); // kept, not ended
    expect(c.read(conversationViewModelProvider).status, ConversationStatus.idle);
    verifyNever(() => repo.endSession(any()));
  });

  group('automatic turn chaining', () {
    test('after the assistant replies, it listens again without a new tap',
        () async {
      // First turn is heard, later turns are silent so the loop terminates.
      final speech = _FakeSpeech('hello there');
      final c = _container(_repoReturning(1, reply: 'Hi back!'), speech);
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      await vm.listenAndRespond();

      // One tap -> at least a second listen was started automatically.
      expect(speech.listenCalls, greaterThanOrEqualTo(2));
      expect(c.read(conversationViewModelProvider).status,
          ConversationStatus.idle);
    });

    test('silence ends the loop back to idle (no infinite listening)',
        () async {
      final speech = _FakeSpeech('', thenSilence: true);
      final c = _container(_repoReturning(1, reply: 'unused'), speech);
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      await vm.listenAndRespond();

      final state = c.read(conversationViewModelProvider);
      expect(state.status, ConversationStatus.idle);
      expect(state.turns.length, 1); // only the opening assistant line
    });

    test('stopConversation halts the loop and stops the recognizer', () async {
      // Blocking fake: listen() waits until the test releases it, so
      // stopConversation runs while a turn is genuinely in flight.
      final speech = _BlockingSpeech('keep going');
      final c = _container(_repoReturning(1, reply: 'And then?'), speech);
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      unawaited(vm.listenAndRespond());
      await speech.listenStarted.future; // a turn is now listening

      await vm.stopConversation();
      speech.releaseListen(''); // recognizer returns empty after stop

      expect(speech.stopped, isTrue);
      expect(c.read(conversationViewModelProvider).status,
          ConversationStatus.idle);
    });

    test('end() also stops an in-progress conversation loop', () async {
      final repo = _repoReturning(5, reply: 'Go on');
      when(() => repo.endSession(any())).thenAnswer((_) async {});
      final speech = _BlockingSpeech('more');
      final c = _container(repo, speech);
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      unawaited(vm.listenAndRespond());
      await speech.listenStarted.future;

      await vm.end();
      speech.releaseListen('');

      expect(speech.stopped, isTrue);
      expect(c.read(conversationViewModelProvider).sessionId, isNull);
    });

    test('a backend failure surfaces an error and the loop stops', () async {
      final repo = _MockConversationRepository();
      when(
        () => repo.startSession(
          mode: any(named: 'mode'),
          scenarioId: any(named: 'scenarioId'),
        ),
      ).thenAnswer((_) async => 1);
      when(() => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey')))
          .thenAnswer((_) => Stream.error(Exception('network down')));
      final c = _container(repo, _FakeSpeech('hello'));
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      await vm.listenAndRespond();

      final state = c.read(conversationViewModelProvider);
      // The error the loop set must survive its finally clause (not be reset).
      expect(state.error, 'Could not get a reply');
      expect(state.status, ConversationStatus.idle);
    });

    test('a recognizer error surfaces a helpful message and returns to idle',
        () async {
      final speech = _FakeSpeech('')..errorOnListen = 'no-speech';
      final c = _container(_repoReturning(1, reply: 'unused'), speech);
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      await vm.listenAndRespond();

      final state = c.read(conversationViewModelProvider);
      expect(state.status, ConversationStatus.idle);
      expect(state.error, isNotNull);
      expect(state.error!.toLowerCase(), contains('entendu'));
    });

    test('silence with no recognizer error shows no error (just idle)',
        () async {
      // Plain silence (learner said nothing) must NOT look like a failure.
      final speech = _FakeSpeech('', thenSilence: true);
      final c = _container(_repoReturning(1, reply: 'unused'), speech);
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      await vm.listenAndRespond();

      final state = c.read(conversationViewModelProvider);
      expect(state.status, ConversationStatus.idle);
      expect(state.error, isNull);
    });

    test('a re-tap while a loop is already running is ignored (re-entrancy)',
        () async {
      // The _loopRunning guard: calling listenAndRespond again while a loop is
      // in flight must be a no-op, never a second concurrent loop.
      final speech = _BlockingSpeech('hi');
      final c = _container(_repoReturning(1, reply: 'reply'), speech);
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      unawaited(vm.listenAndRespond());
      await speech.listenStarted.future;

      // Second call while the first loop is mid-listen: must not start a turn.
      await vm.listenAndRespond();

      // Exactly one listen was ever started by the single running loop.
      expect(speech.maxConcurrentListens, 1);
    });

    test(
        'a turn from a stopped loop cannot overwrite the state of a new session',
        () async {
      // Fragility guard: an in-flight turn that resolves AFTER the loop was
      // stopped must not append turns or flip status — otherwise a stale loop
      // races a freshly restarted session. The _active guard prevents this.
      final repo = _repoReturning(1, reply: 'stale reply');
      final speech = _BlockingSpeech('stale words');
      final c = _container(repo, speech);
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      unawaited(vm.listenAndRespond());
      await speech.listenStarted.future;

      // Stop while the turn is still listening, then let it resolve late.
      await vm.stopConversation();
      final turnsAfterStop =
          c.read(conversationViewModelProvider).turns.length;
      speech.releaseListen('stale words');
      await Future<void>.delayed(const Duration(milliseconds: 10));

      // The late turn was ignored: no user turn appended, still idle.
      expect(c.read(conversationViewModelProvider).turns.length,
          turnsAfterStop);
      expect(c.read(conversationViewModelProvider).status,
          ConversationStatus.idle);
      verifyNever(() => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey')));
    });
  });

  group('non-network failures are reported, not swallowed (#403)', () {
    test('a non-network failure while streaming the reply is reported',
        () async {
      // Before #403 the conversation feature — the app's central flow — was
      // the ONLY feature view-model with zero reportError calls: a backend
      // 502 or a malformed stream event here vanished without a trace.
      final repo = _MockConversationRepository();
      when(
        () => repo.startSession(
          mode: any(named: 'mode'),
          scenarioId: any(named: 'scenarioId'),
        ),
      ).thenAnswer((_) async => 1);
      when(
        () => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey')),
      ).thenAnswer(
        (_) => Stream<TurnEvent>.error(
          const ApiException(statusCode: 502, code: 'BadGateway', message: 'boom'),
        ),
      );
      final reporter = _MockCrashReporter();
      final c = _container(repo, _FakeSpeech('hello'), crashReporter: reporter);
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      await vm.listenAndRespond();

      verify(
        () => reporter.captureError(
          any(),
          any(),
          context: 'ReplyPlayback.stream',
          data: any(named: 'data'),
        ),
      ).called(1);
      expect(c.read(conversationViewModelProvider).error, 'Could not get a reply');
    });

    test('a NETWORK failure while streaming the reply is queued for replay, '
        'not reported — it is an expected, already-handled condition',
        () async {
      final repo = _MockConversationRepository();
      when(
        () => repo.startSession(
          mode: any(named: 'mode'),
          scenarioId: any(named: 'scenarioId'),
        ),
      ).thenAnswer((_) async => 1);
      when(
        () => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey')),
      ).thenAnswer(
        (_) => Stream<TurnEvent>.error(
          const ApiException(statusCode: 0, code: 'network', message: 'offline'),
        ),
      );
      final reporter = _MockCrashReporter();
      final c = _container(repo, _FakeSpeech('hello'), crashReporter: reporter);
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      await vm.listenAndRespond();

      verifyNever(
        () => reporter.captureError(
          any(),
          any(),
          context: any(named: 'context'),
          data: any(named: 'data'),
        ),
      );
      expect(c.read(connectivityControllerProvider).pendingCount, 1);
    });

    test('a non-network transcribe failure in push-to-talk is reported '
        '(previously accused the learner\'s pronunciation with no trace of '
        'the real cause)', () async {
      final repo = _MockConversationRepository();
      when(
        () => repo.startSession(
          mode: any(named: 'mode'),
          scenarioId: any(named: 'scenarioId'),
        ),
      ).thenAnswer((_) async => 1);
      when(() => repo.transcribe(any())).thenThrow(
        const ApiException(statusCode: 503, code: 'ServiceUnavailable', message: 'stt down'),
      );
      final reporter = _MockCrashReporter();
      final c = _container(
        repo,
        _FakeSpeech(''),
        serverStt: true,
        crashReporter: reporter,
      );
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      await vm.listenAndRespond(); // push-to-talk: start recording
      await vm.stopConversation(); // stop -> transcribe (fails)

      verify(
        () => reporter.captureError(
          any(),
          any(),
          context: 'PushToTalkController.stopAndRespond: transcribe failed',
          data: any(named: 'data'),
        ),
      ).called(1);
      expect(
        c.read(conversationViewModelProvider).error,
        'Could not understand you — try again',
      );
    });

    test('a NETWORK transcribe failure in push-to-talk is NOT reported',
        () async {
      final repo = _MockConversationRepository();
      when(
        () => repo.startSession(
          mode: any(named: 'mode'),
          scenarioId: any(named: 'scenarioId'),
        ),
      ).thenAnswer((_) async => 1);
      when(() => repo.transcribe(any())).thenThrow(
        const ApiException(statusCode: 0, code: 'network', message: 'offline'),
      );
      final reporter = _MockCrashReporter();
      final c = _container(
        repo,
        _FakeSpeech(''),
        serverStt: true,
        crashReporter: reporter,
      );
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      await vm.listenAndRespond();
      await vm.stopConversation();

      verifyNever(
        () => reporter.captureError(
          any(),
          any(),
          context: any(named: 'context'),
          data: any(named: 'data'),
        ),
      );
    });
  });

  group('offline turn replay (#311, #312, #313)', () {
    test('start() rehydrates the pending-turn count from the offline queue '
        '(#311)', () async {
      // Before the fix, pendingCount always started at 0 regardless of what
      // was actually queued from a previous run — an offline turn stayed
      // invisible (no banner, no retry) until something else happened to
      // touch connectivity state.
      final queue = _InMemoryOfflineQueue()
        ..enqueue(
          const PendingTurn(sessionId: 1, text: 'queued', idempotencyKey: 'k1'),
        );
      final c = _container(_repoReturning(1), _FakeSpeech(''), offlineQueue: queue);

      await c.read(conversationViewModelProvider.notifier).start();

      final connectivity = c.read(connectivityControllerProvider);
      expect(connectivity.pendingCount, 1);
      expect(connectivity.hasPending, isTrue);
    });

    test("a replayed offline turn's reply is fetched into the transcript "
        'once the queue drains (#312)', () async {
      // Before the fix, OfflineTurnSync.sync() sent the queued turn and threw
      // away its reply (only a count was returned) — the reply was NEVER
      // shown anywhere, even though the server had it.
      final queue = _InMemoryOfflineQueue()
        ..enqueue(
          const PendingTurn(sessionId: 1, text: 'queued', idempotencyKey: 'k1'),
        );
      final repo = _repoReturning(1);
      when(
        () => repo.sendTurn(1, 'queued', idempotencyKey: 'k1'),
      ).thenAnswer((_) async => 'Nice to hear from you again!');
      when(() => repo.getActiveSession()).thenAnswer(
        (_) async => const ActiveSessionData(
          sessionId: 1,
          mode: 'free',
          scenarioId: null,
          turns: [
            (
              role: 'assistant',
              content:
                  "Hi, let's practise English. What would you like to talk about today?",
            ),
            (role: 'user', content: 'queued'),
            (role: 'assistant', content: 'Nice to hear from you again!'),
          ],
        ),
      );
      final c = _container(repo, _FakeSpeech(''), offlineQueue: queue);
      final vm = c.read(conversationViewModelProvider.notifier);
      await vm.start(); // rehydrates pendingCount=1; turns = [opening line]

      // The real replay path: syncPending() -> OfflineTurnSync.sync() sends
      // the queued turn and drains the queue, which fires the ref.listen in
      // build() and triggers the re-fetch. The refresh itself is
      // unawaited() by design (a background reaction to the state change,
      // not something syncPending's caller should block on) — pumpEventQueue
      // lets it finish before asserting.
      await c.read(connectivityControllerProvider.notifier).syncPending();
      await pumpEventQueue();

      final state = c.read(conversationViewModelProvider);
      expect(state.turns.map((t) => t.content).toList(), [
        "Hi, let's practise English. What would you like to talk about today?",
        'queued',
        'Nice to hear from you again!',
      ]);
      expect(c.read(connectivityControllerProvider).pendingCount, 0);
    });

    test('a correction chip already attached locally survives a #312 '
        'refresh (the server snapshot carries no correction data)', () async {
      final queue = _InMemoryOfflineQueue();
      final repo = _MockConversationRepository();
      when(
        () => repo.startSession(
          mode: any(named: 'mode'),
          scenarioId: any(named: 'scenarioId'),
        ),
      ).thenAnswer((_) async => 1);
      when(
        () => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey')),
      ).thenAnswer(
        (_) => Stream.fromIterable(const [
          ReplySentence('Good.'),
          CorrectionEvent(
            TurnCorrection(
              original: 'i is happy',
              correction: 'I am happy',
              rule: "Use 'am' with 'I'.",
              alternatives: ["I'm happy"],
            ),
          ),
        ]),
      );
      when(() => repo.getActiveSession()).thenAnswer(
        (_) async => const ActiveSessionData(
          sessionId: 1,
          mode: 'free',
          scenarioId: null,
          turns: [
            (
              role: 'assistant',
              content:
                  "Hi, let's practise English. What would you like to talk about today?",
            ),
            (role: 'user', content: 'i is happy'),
            (role: 'assistant', content: 'Good.'),
          ],
        ),
      );
      final c = _container(repo, _FakeSpeech('i is happy'), offlineQueue: queue);
      final vm = c.read(conversationViewModelProvider.notifier);
      await vm.start();
      await vm.listenAndRespond(); // attaches the correction to the user turn

      // A queue drain (unrelated to this turn) still fires the refresh.
      await queue.enqueue(
        const PendingTurn(sessionId: 1, text: 'x', idempotencyKey: 'other'),
      );
      await c.read(connectivityControllerProvider.notifier).refresh();
      await queue.remove('other');
      await c.read(connectivityControllerProvider.notifier).refresh();
      await pumpEventQueue(); // let the unawaited() refresh finish

      final userTurn = c
          .read(conversationViewModelProvider)
          .turns
          .firstWhere((t) => t.role == kRoleUser);
      expect(userTurn.correction?.correction, 'I am happy');
    });

    test(
      'a #312 refresh reconciles corrections by POSITION, not by identical '
      'text — two turns that both said "yes" are not conflated (#390)',
      () async {
        final queue = _InMemoryOfflineQueue();
        final repo = _MockConversationRepository();
        when(
          () => repo.startSession(
            mode: any(named: 'mode'),
            scenarioId: any(named: 'scenarioId'),
          ),
        ).thenAnswer((_) async => 1);
        // The server's authoritative transcript: identical content ("yes")
        // at two DIFFERENT positions; getActiveSession never carries
        // correction data.
        when(() => repo.getActiveSession()).thenAnswer(
          (_) async => const ActiveSessionData(
            sessionId: 1,
            mode: 'free',
            scenarioId: null,
            turns: [
              (
                role: 'assistant',
                content: 'Hi, what would you like to talk about?',
              ),
              (role: 'user', content: 'yes'),
              (role: 'assistant', content: 'OK, tell me more.'),
              (role: 'user', content: 'yes'),
              (role: 'assistant', content: 'Great!'),
            ],
          ),
        );
        final c = _container(repo, _FakeSpeech(''), offlineQueue: queue);
        final vm = c.read(conversationViewModelProvider.notifier);
        await vm.start(); // sessionId=1, opening turn only

        // Seed the LOCAL state as the precondition #390 describes: the
        // FIRST "yes" (index 1) never got a correction, the SECOND "yes"
        // (index 3) already carries one.
        const correction = TurnCorrection(
          original: 'yes',
          correction: 'Yes.',
          rule: 'Capitalize the start of a sentence.',
          alternatives: [],
        );
        vm.state = const ConversationState(
          sessionId: 1,
          turns: [
            ConversationTurn(
              kRoleAssistant,
              'Hi, what would you like to talk about?',
            ),
            ConversationTurn(kRoleUser, 'yes'), // NOT corrected
            ConversationTurn(kRoleAssistant, 'OK, tell me more.'),
            ConversationTurn(kRoleUser, 'yes', correction: correction),
            ConversationTurn(kRoleAssistant, 'Great!'),
          ],
        );

        // Trigger the #312 refresh via a real queue-drain, matching
        // production (build()'s ref.listen on connectivityControllerProvider).
        await queue.enqueue(
          const PendingTurn(sessionId: 1, text: 'x', idempotencyKey: 'other'),
        );
        await c.read(connectivityControllerProvider.notifier).refresh();
        await queue.remove('other');
        await c.read(connectivityControllerProvider.notifier).refresh();
        await pumpEventQueue(); // let the unawaited() refresh finish

        final userTurns = c
            .read(conversationViewModelProvider)
            .turns
            .where((t) => t.role == kRoleUser)
            .toList();
        expect(userTurns, hasLength(2));
        expect(
          userTurns[0].correction,
          isNull,
          reason: 'the FIRST "yes" was never corrected — must not gain a '
              'spurious chip from the second, identical-text turn',
        );
        expect(
          userTurns[1].correction?.correction,
          'Yes.',
          reason: 'the SECOND "yes" keeps its own correction',
        );
      },
    );

    test(
      'a #312 refresh preserves the client-only opening bubble AND the '
      'correction chips when the server transcript omits the opening (#400)',
      () async {
        final queue = _InMemoryOfflineQueue();
        final repo = _MockConversationRepository();
        when(
          () => repo.startSession(
            mode: any(named: 'mode'),
            scenarioId: any(named: 'scenarioId'),
          ),
        ).thenAnswer((_) async => 1);
        // Realistic server transcript: the opening bubble is synthesized
        // client-side and never persisted, so getActiveSession starts at the
        // first USER turn — NOT at the opening.
        when(() => repo.getActiveSession()).thenAnswer(
          (_) async => const ActiveSessionData(
            sessionId: 1,
            mode: 'free',
            scenarioId: null,
            turns: [
              (role: 'user', content: 'i is happy'),
              (role: 'assistant', content: 'Good.'),
            ],
          ),
        );
        final c = _container(repo, _FakeSpeech(''), offlineQueue: queue);
        final vm = c.read(conversationViewModelProvider.notifier);
        await vm.start();

        // Local state: the client-synthesized opening at index 0, then a user
        // turn that already carries a correction chip.
        const correction = TurnCorrection(
          original: 'i is happy',
          correction: 'I am happy',
          rule: "Use 'am' with 'I'.",
          alternatives: ["I'm happy"],
        );
        vm.state = const ConversationState(
          sessionId: 1,
          turns: [
            ConversationTurn(
              kRoleAssistant,
              'Welcome! What shall we talk about?',
            ),
            ConversationTurn(kRoleUser, 'i is happy', correction: correction),
            ConversationTurn(kRoleAssistant, 'Good.'),
          ],
        );

        await queue.enqueue(
          const PendingTurn(sessionId: 1, text: 'x', idempotencyKey: 'other'),
        );
        await c.read(connectivityControllerProvider.notifier).refresh();
        await queue.remove('other');
        await c.read(connectivityControllerProvider.notifier).refresh();
        await pumpEventQueue();

        final turns = c.read(conversationViewModelProvider).turns;
        // The opening bubble survives at the head — the server never has it.
        expect(turns.first.role, kRoleAssistant);
        expect(turns.first.content, 'Welcome! What shall we talk about?');
        // The correction stays on its own user turn (not shifted off by the
        // one-position opening offset, which the old left-index code dropped).
        final userTurn = turns.firstWhere((t) => t.role == kRoleUser);
        expect(
          userTurn.correction?.correction,
          'I am happy',
          reason: 'the opening offset must not drop the correction (#400)',
        );
        expect(turns, hasLength(3), reason: 'no turn duplicated or lost');
      },
    );

    test('a turn that fails on the network is queued under the SAME '
        'idempotency key it was sent with, not a freshly generated one '
        '(#313)', () async {
      final repo = _MockConversationRepository();
      when(
        () => repo.startSession(
          mode: any(named: 'mode'),
          scenarioId: any(named: 'scenarioId'),
        ),
      ).thenAnswer((_) async => 1);
      String? sentKey;
      when(
        () => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey')),
      ).thenAnswer((invocation) {
        sentKey = invocation.namedArguments[#idempotencyKey] as String;
        return Stream<TurnEvent>.error(
          const ApiException(statusCode: 0, code: 'network', message: 'offline'),
        );
      });
      final queue = _InMemoryOfflineQueue();
      final c = _container(repo, _FakeSpeech('hello'), offlineQueue: queue);
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      await vm.listenAndRespond();

      final queued = await queue.pending();
      expect(queued, hasLength(1));
      expect(sentKey, isNotNull);
      expect(queued.single.idempotencyKey, sentKey);
      expect(c.read(connectivityControllerProvider).pendingCount, 1);
    });
  });

  group('reply audio cancellation (#314)', () {
    test(
        'cancel unblocks awaitPlayback immediately via its own bookkeeping, '
        'even when the underlying player.stop() does not itself unblock '
        'playback', () async {
      final repo = _MockConversationRepository();
      when(
        () => repo.startSession(
          mode: any(named: 'mode'),
          scenarioId: any(named: 'scenarioId'),
        ),
      ).thenAnswer((_) async => 1);
      when(
        () => repo.streamTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey')),
      ).thenAnswer(
        (_) => Stream.fromIterable(const [
          ReplySentence('Bye.'),
          AudioClip('QUJD', 'audio/mpeg'),
        ]),
      );
      final audio = _StubbornAudio();
      final c = _container(repo, _FakeSpeech('hi'), serverTts: true, audio: audio);
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      final loop = vm.listenAndRespond();
      await audio.firstPlayStarted.future; // the clip is now "playing"

      // Before #314, this could hang up to 20s waiting for a player that
      // never unblocks on its own; reply_playback.dart's cancel() now clears
      // its own bookkeeping instead of depending on the player to cooperate.
      await vm.stopConversation().timeout(const Duration(seconds: 2));
      await vm.awaitPlaybackForTest().timeout(const Duration(seconds: 2));

      expect(audio.stopCalls, 1);
      audio.release(); // let the orphaned clip unwind so nothing leaks
      await loop;
    });
  });
}

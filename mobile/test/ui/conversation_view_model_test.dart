import 'dart:async';

import 'package:apm/src/core/network/api_exception.dart';
import 'package:apm/src/core/speech/speech_service.dart';
import 'package:apm/src/data/models/profile.dart';
import 'package:apm/src/data/repositories/conversation_repository.dart';
import 'package:apm/src/data/repositories/profile_repository.dart';
import 'package:apm/src/ui/conversation/view_model/conversation_state.dart';
import 'package:apm/src/ui/conversation/view_model/conversation_view_model.dart';
import 'package:apm/src/ui/profile/view_model/profile_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockConversationRepository extends Mock
    implements ConversationRepository {}

class _MockProfileRepository extends Mock implements ProfileRepository {}

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

  @override
  String? get lastError => null;

  @override
  Future<bool> initialize() async => ready;
  @override
  Future<void> setLanguage(String languageTag) async {
    this.languageTag = languageTag;
  }

  @override
  Future<String> listenOnce({void Function(String words)? onPartial}) async {
    listenCalls++;
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

ProviderContainer _container(
  ConversationRepository repo,
  SpeechService speech,
) {
  final c = ProviderContainer(
    overrides: [
      conversationRepositoryProvider.overrideWithValue(repo),
      speechServiceProvider.overrideWithValue(speech),
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
    when(() => repo.sendTurn(any(), any())).thenAnswer((_) async => reply);
  }
  return repo;
}

void main() {
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

  test('start rethrows non-409 errors instead of swallowing them', () async {
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

    await expectLater(
      c.read(conversationViewModelProvider.notifier).start(),
      throwsA(isA<ApiException>()),
    );
    verifyNever(() => repo.getActiveSession());
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
    verifyNever(() => repo.sendTurn(any(), any()));
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
      when(() => repo.sendTurn(any(), any()))
          .thenThrow(Exception('network down'));
      final c = _container(repo, _FakeSpeech('hello'));
      final vm = c.read(conversationViewModelProvider.notifier);

      await vm.start();
      await vm.listenAndRespond();

      final state = c.read(conversationViewModelProvider);
      // The error the loop set must survive its finally clause (not be reset).
      expect(state.error, 'Could not get a reply');
      expect(state.status, ConversationStatus.idle);
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
      verifyNever(() => repo.sendTurn(any(), any()));
    });
  });
}

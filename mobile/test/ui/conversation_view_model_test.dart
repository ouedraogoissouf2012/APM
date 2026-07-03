import 'package:apm/src/core/speech/speech_service.dart';
import 'package:apm/src/data/repositories/conversation_repository.dart';
import 'package:apm/src/ui/conversation/view_model/conversation_state.dart';
import 'package:apm/src/ui/conversation/view_model/conversation_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockConversationRepository extends Mock
    implements ConversationRepository {}

class _FakeSpeech implements SpeechService {
  _FakeSpeech(this.recognized, {this.ready = true});

  final String recognized;
  final bool ready;
  String? spokenText;

  @override
  Future<bool> initialize() async => ready;
  @override
  Future<String> listenOnce() async => recognized;
  @override
  Future<void> speak(String text) async {
    spokenText = text;
  }

  @override
  Future<void> stopListening() async {}
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
}

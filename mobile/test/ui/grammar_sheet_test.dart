import 'dart:typed_data';

import 'package:apm/src/core/audio/audio_recording_service.dart';
import 'package:apm/src/core/audio/providers.dart';
import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/data/models/turn_correction.dart';
import 'package:apm/src/data/repositories/conversation_repository.dart';
import 'package:apm/src/ui/conversation/view_model/conversation_providers.dart';
import 'package:apm/src/ui/conversation/widgets/grammar_sheet.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockConv extends Mock implements ConversationRepository {}

class _FakeRecorder implements AudioRecordingService {
  @override
  Future<bool> start() async => true;
  @override
  Future<Uint8List?> stop() async => Uint8List.fromList(const [1, 2, 3]);
  @override
  Future<void> cancel() async {}
}

const _correction = TurnCorrection(
  original: 'i is happy',
  correction: 'I am happy',
  rule: "Use 'am' with 'I'.",
);

Future<void> _openSheet(WidgetTester tester, ConversationRepository conv) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        audioRecordingProvider.overrideWithValue(_FakeRecorder()),
        conversationRepositoryProvider.overrideWithValue(conv),
      ],
      child: MaterialApp(
        theme: AppTheme.dark(),
        home: Scaffold(
          body: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () => showGrammarSheet(context, _correction),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

Future<void> _reformulate(WidgetTester tester) async {
  await tester.tap(find.byKey(const Key('reformulation_button'))); // start recording
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('reformulation_button'))); // stop -> transcribe
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(() => registerFallbackValue(Uint8List(0)));

  testWidgets('reformulation: re-saying the corrected sentence is confirmed (#200)',
      (tester) async {
    final conv = _MockConv();
    when(() => conv.transcribe(any())).thenAnswer((_) async => 'I am happy');
    await _openSheet(tester, conv);

    await _reformulate(tester);

    expect(find.byKey(const Key('reformulation_ok')), findsOneWidget);
  });

  testWidgets('reformulation: a wrong re-say asks to try again (#200)', (tester) async {
    final conv = _MockConv();
    when(() => conv.transcribe(any())).thenAnswer((_) async => 'I happy'); // "am" dropped
    await _openSheet(tester, conv);

    await _reformulate(tester);

    expect(find.byKey(const Key('reformulation_retry')), findsOneWidget);
  });
}

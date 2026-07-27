import 'package:apm/src/core/network/sse.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('parseSse — turns a raw SSE line stream into events', () {
    test('parses event/data frames separated by blank lines', () async {
      final lines = Stream.fromIterable([
        'event: chunk',
        'data: {"text":"Hi there."}',
        '',
        'event: chunk',
        'data: {"text":"How are you?"}',
        '',
        'event: done',
        'data: {}',
        '',
      ]);

      final events = await parseSse(lines).toList();

      expect(events.map((e) => e.event), ['chunk', 'chunk', 'done']);
      expect(events[0].data, '{"text":"Hi there."}');
      expect(events[2].event, 'done');
    });

    test('handles a frame split so data arrives before its blank line',
        () async {
      final lines = Stream.fromIterable([
        'event: chunk',
        'data: {"text":"partial"}',
        '', // flush
      ]);
      final events = await parseSse(lines).toList();
      expect(events.single.event, 'chunk');
      expect(events.single.data, '{"text":"partial"}');
    });

    test('ignores comment lines and stray blank lines', () async {
      final lines = Stream.fromIterable([
        ': keep-alive comment',
        '',
        'event: done',
        'data: {}',
        '',
      ]);
      final events = await parseSse(lines).toList();
      expect(events.single.event, 'done');
    });

    test('a frame without an explicit event defaults to "message"', () async {
      final lines = Stream.fromIterable(['data: hello', '']);
      final events = await parseSse(lines).toList();
      expect(events.single.event, 'message');
      expect(events.single.data, 'hello');
    });
  });

  group('sseChunkText — extracts the sentence from a chunk event', () {
    test('reads the text field', () {
      expect(sseChunkText('{"text":"Bonjour."}'), 'Bonjour.');
    });

    test('returns null for malformed or empty payloads', () {
      expect(sseChunkText('{}'), isNull);
      expect(sseChunkText('not json'), isNull);
      expect(sseChunkText(''), isNull);
    });
  });
}

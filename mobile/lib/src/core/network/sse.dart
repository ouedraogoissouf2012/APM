import 'dart:convert';

/// One decoded Server-Sent Event: its [event] name and raw [data] payload.
class SseEvent {
  const SseEvent(this.event, this.data);

  final String event;
  final String data;
}

/// Turns a stream of SSE text *lines* into a stream of [SseEvent]s. A frame is
/// accumulated line by line and emitted on the blank line that terminates it
/// (per the SSE spec). Comment lines (starting with `:`) are ignored. A frame
/// with data but no explicit `event:` field defaults to `message`.
///
/// Pure and transport-agnostic — the HTTP client only has to hand it lines,
/// which makes the parsing fully unit-testable without a socket.
Stream<SseEvent> parseSse(Stream<String> lines) async* {
  String? event;
  final data = <String>[];

  await for (final line in lines) {
    if (line.isEmpty) {
      // Blank line = dispatch the buffered frame, if any.
      if (data.isNotEmpty || event != null) {
        yield SseEvent(event ?? 'message', data.join('\n'));
        event = null;
        data.clear();
      }
      continue;
    }
    if (line.startsWith(':')) continue; // comment / keep-alive
    if (line.startsWith('event:')) {
      event = line.substring('event:'.length).trim();
    } else if (line.startsWith('data:')) {
      data.add(line.substring('data:'.length).trim());
    }
  }
  // Flush a trailing frame that was not followed by a blank line.
  if (data.isNotEmpty || event != null) {
    yield SseEvent(event ?? 'message', data.join('\n'));
  }
}

/// Extracts the `text` field from a `chunk` event's JSON payload, or null when
/// the payload is missing, empty, or malformed.
String? sseChunkText(String data) {
  if (data.isEmpty) return null;
  try {
    final decoded = jsonDecode(data);
    if (decoded is Map && decoded['text'] is String) {
      return decoded['text'] as String;
    }
  } catch (_) {
    // Malformed JSON — treat as no text.
  }
  return null;
}

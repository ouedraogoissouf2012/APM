import 'dart:typed_data';

import 'package:apm/src/core/audio/audio_recording_service.dart';
import 'package:flutter_test/flutter_test.dart';

/// Reads a little-endian ASCII tag / integer out of a WAV header, so the tests
/// assert the real bytes rather than trusting the writer.
String _ascii(Uint8List b, int offset, int len) =>
    String.fromCharCodes(b.sublist(offset, offset + len));
int _u32(Uint8List b, int o) =>
    b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24);
int _u16(Uint8List b, int o) => b[o] | (b[o + 1] << 8);

void main() {
  group('wrapPcmInWav', () {
    final pcm = Uint8List.fromList(List<int>.generate(1000, (i) => i % 256));

    test('produces a valid RIFF/WAVE container around the PCM payload', () {
      final wav = wrapPcmInWav(pcm, sampleRate: 16000, numChannels: 1);

      expect(_ascii(wav, 0, 4), 'RIFF');
      expect(_ascii(wav, 8, 4), 'WAVE');
      expect(_ascii(wav, 12, 4), 'fmt ');
      expect(_ascii(wav, 36, 4), 'data');
      // Header is 44 bytes; total length = header + payload.
      expect(wav.length, 44 + pcm.length);
    });

    test('header sizes match the payload exactly (no truncation)', () {
      final wav = wrapPcmInWav(pcm, sampleRate: 16000, numChannels: 1);

      // RIFF size = everything after the first 8 bytes.
      expect(_u32(wav, 4), 36 + pcm.length);
      // data size = the payload length precisely — the field Whisper reads to
      // know how much audio to decode. A wrong value here is the truncation bug.
      expect(_u32(wav, 40), pcm.length);
    });

    test('encodes the declared PCM format (mono, 16 kHz, 16-bit)', () {
      final wav = wrapPcmInWav(pcm, sampleRate: 16000, numChannels: 1);

      expect(_u16(wav, 20), 1); // PCM
      expect(_u16(wav, 22), 1); // mono
      expect(_u32(wav, 24), 16000); // sample rate
      expect(_u16(wav, 34), 16); // bits per sample
      expect(_u32(wav, 28), 16000 * 1 * 16 ~/ 8); // byte rate
      expect(_u16(wav, 32), 1 * 16 ~/ 8); // block align
    });

    test('appends the PCM bytes unchanged after the header', () {
      final wav = wrapPcmInWav(pcm, sampleRate: 16000, numChannels: 1);
      expect(wav.sublist(44), pcm);
    });

    test('honours stereo / other sample rates', () {
      final wav = wrapPcmInWav(pcm, sampleRate: 44100, numChannels: 2);
      expect(_u16(wav, 22), 2);
      expect(_u32(wav, 24), 44100);
      expect(_u32(wav, 28), 44100 * 2 * 16 ~/ 8);
      expect(_u16(wav, 32), 2 * 16 ~/ 8);
    });
  });
}

import 'dart:typed_data';

import 'voice_take_store.dart';

/// Wraps any [VoiceTakeStore] to bound how long the raw, PLAINTEXT audio it
/// holds stays readable (#226): the learner's spoken takes are stored
/// unencrypted (a file on native, IndexedDB on web), so anyone with DevTools
/// access or a stolen/shared device could read them indefinitely. This caps
/// their retention instead of leaving them to live forever.
///
/// Implementation: [saveTake] prepends an 8-byte big-endian epoch-millis
/// header to the bytes before forwarding to [_inner]; [takesFor] strips it and
/// treats a take older than [ttl] as ABSENT (returns null for it), so a stale
/// take can no longer be read or exposed even though its bytes still
/// physically sit in [_inner] until the next write or an explicit
/// [eraseAll]  — there is no background sweep on this platform. This works
/// uniformly over ANY inner store (file, IndexedDB, in-memory) without each
/// one needing its own timestamp persistence.
///
/// Consequence, by design: the BASELINE (the learner's first-ever take on a
/// skill, written once) is subject to the same TTL as latest. Once it goes
/// stale, the audible before/after for that skill resets — the next take
/// becomes a fresh baseline. This is the intended effect of bounding raw
/// audio retention, not a bug: an unbounded "before" would be exactly the
/// oldest, most sensitive data a retention limit exists to age out.
class TtlVoiceTakeStore implements VoiceTakeStore {
  TtlVoiceTakeStore(this._inner, {this.ttl = _defaultTtl, DateTime Function()? now})
      : _now = now ?? DateTime.now;

  final VoiceTakeStore _inner;
  final Duration ttl;
  final DateTime Function() _now;

  static const Duration _defaultTtl = Duration(days: 30);
  static const int _headerBytes = 8;

  @override
  Future<void> saveTake(String skill, Uint8List bytes) =>
      _inner.saveTake(skill, _stamp(bytes, _now()));

  @override
  Future<VoiceTakes?> takesFor(String skill) async {
    final takes = await _inner.takesFor(skill);
    if (takes == null) return null;
    final baseline = _freshBytesOrNull(takes.baseline);
    final latest = _freshBytesOrNull(takes.latest);
    // Both are required for a before/after; a stale (or malformed/legacy,
    // pre-TTL) take is treated the same as absent.
    if (baseline == null || latest == null) return null;
    return VoiceTakes(baseline: baseline, latest: latest);
  }

  @override
  Future<void> eraseAll() => _inner.eraseAll();

  Uint8List _stamp(Uint8List bytes, DateTime at) {
    final out = Uint8List(_headerBytes + bytes.length);
    ByteData.view(out.buffer).setInt64(0, at.toUtc().millisecondsSinceEpoch, Endian.big);
    out.setRange(_headerBytes, out.length, bytes);
    return out;
  }

  Uint8List? _freshBytesOrNull(Uint8List stamped) {
    if (stamped.length < _headerBytes) return null; // too short to carry our header
    final DateTime saved;
    try {
      final millis = ByteData.sublistView(stamped, 0, _headerBytes).getInt64(0, Endian.big);
      saved = DateTime.fromMillisecondsSinceEpoch(millis, isUtc: true);
    } catch (_) {
      // A malformed header — e.g. a take saved by a PRE-#226 app version, whose
      // raw WAV bytes happen to start with something our header parser can't
      // read as a sane timestamp — is treated as stale rather than crashing.
      return null;
    }
    if (_now().toUtc().difference(saved) > ttl) return null;
    return stamped.sublist(_headerBytes);
  }
}

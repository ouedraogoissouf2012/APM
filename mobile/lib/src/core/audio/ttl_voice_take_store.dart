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
/// treats a take older than [ttl] as ABSENT (returns null for it), AND
/// physically deletes it from [_inner] via [VoiceTakeStore.deleteSkill] — so a
/// stale take's bytes stop existing on the next read that notices them, not
/// just on the next write or an explicit [eraseAll]. There is still no
/// background sweep (a skill nobody re-reads keeps its stale bytes until the
/// next [takesFor] call for it), but retention is no longer merely logical.
/// This works uniformly over ANY inner store (file, IndexedDB, in-memory)
/// without each one needing its own timestamp persistence.
///
/// Consequence, by design: the BASELINE (the learner's first-ever take on a
/// skill, written once) is subject to the same TTL as latest. Once it goes
/// stale, the audible before/after for that skill resets and its bytes are
/// purged — the next take becomes a fresh baseline (the physical purge is
/// what makes this true: [_inner]'s own "write baseline only if absent" rule
/// would otherwise keep refusing to replace a baseline file/key that still
/// physically exists, stale or not). This is the intended effect of bounding
/// raw audio retention, not a bug: an unbounded "before" would be exactly the
/// oldest, most sensitive data a retention limit exists to age out.
class TtlVoiceTakeStore implements VoiceTakeStore {
  TtlVoiceTakeStore(this._inner, {this.ttl = _defaultTtl, DateTime Function()? now})
      : _now = now ?? DateTime.now;

  final VoiceTakeStore _inner;
  final Duration ttl;
  final DateTime Function() _now;

  static const Duration _defaultTtl = Duration(days: 30);
  static const int _headerBytes = 8;
  // 2^32. The 8-byte timestamp is stored as two big-endian uint32 (high, low)
  // instead of one int64 because ByteData.setInt64/getInt64 throw
  // UnsupportedError on the web build (JS has no 64-bit int) — which would
  // otherwise break saving/reading takes on web. uint32 math stays < 2^53
  // (JS-exact) for any real epoch-millis.
  static const int _u32 = 0x100000000;

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
    if (baseline == null || latest == null) {
      // Physically purge (#226): a hidden-but-still-present take would
      // otherwise sit in [_inner] indefinitely — bounding retention must free
      // the bytes, not just stop exposing them through this read.
      await _inner.deleteSkill(skill);
      return null;
    }
    return VoiceTakes(baseline: baseline, latest: latest);
  }

  @override
  Future<void> eraseAll() => _inner.eraseAll();

  @override
  Future<void> deleteSkill(String skill) => _inner.deleteSkill(skill);

  /// Startup sweep (#321): [takesFor]'s purge-on-stale-read only fires for a
  /// skill someone actually re-reads — a skill saved once and never reopened
  /// keeps its stale bytes indefinitely, well past [ttl], until an explicit
  /// [eraseAll]. This purges every EXPIRED skill up front instead of waiting
  /// for a read that may never come, by reusing [takesFor]'s own freshness
  /// check + physical purge for each skill [_inner] reports as having
  /// something stored.
  ///
  /// A no-op if [_inner] doesn't support enumeration (not part of
  /// [VoiceTakeStore] itself — see [SkillEnumerator]); callers should treat
  /// this as best-effort, not a guarantee every expired take is gone by the
  /// time it returns.
  Future<void> sweepExpired() async {
    final inner = _inner;
    if (inner is! SkillEnumerator) return;
    for (final skill in await (inner as SkillEnumerator).knownSkills()) {
      await takesFor(skill);
    }
  }

  Uint8List _stamp(Uint8List bytes, DateTime at) {
    final out = Uint8List(_headerBytes + bytes.length);
    final millis = at.toUtc().millisecondsSinceEpoch;
    final view = ByteData.view(out.buffer);
    view.setUint32(0, millis ~/ _u32, Endian.big); // high 32 bits
    view.setUint32(4, millis % _u32, Endian.big); // low 32 bits
    out.setRange(_headerBytes, out.length, bytes);
    return out;
  }

  Uint8List? _freshBytesOrNull(Uint8List stamped) {
    if (stamped.length < _headerBytes) return null; // too short to carry our header
    final DateTime saved;
    try {
      final view = ByteData.sublistView(stamped, 0, _headerBytes);
      final millis = view.getUint32(0, Endian.big) * _u32 + view.getUint32(4, Endian.big);
      saved = DateTime.fromMillisecondsSinceEpoch(millis, isUtc: true);
    } catch (_) {
      // A malformed header — e.g. a take saved by a PRE-#226 app version, whose
      // raw WAV bytes start with "RIFF"+size that decodes to an out-of-range
      // timestamp — is treated as stale rather than crashing.
      return null;
    }
    if (_now().toUtc().difference(saved) > ttl) return null;
    return stamped.sublist(_headerBytes);
  }
}

import 'dart:io';
import 'dart:typed_data';

import 'voice_take_store.dart';

/// File-backed [VoiceTakeStore] (native): the learner's takes persist on disk so
/// the audible before/after survives app restarts — a genuine "you, 7 days ago vs
/// today". One baseline file + one latest file per skill.
///
/// The directory is injected (a thunk, so opening it can be async and lazy) which
/// keeps the provider synchronous AND makes the store unit-testable against a temp
/// directory. Privacy (#128): these files live on the device only.
class FileVoiceTakeStore implements VoiceTakeStore {
  FileVoiceTakeStore(this._openDir);

  final Future<Directory> Function() _openDir;
  Directory? _dir;

  Future<Directory> _dir_() async {
    final dir = _dir ??= await _openDir();
    if (!await dir.exists()) await dir.create(recursive: true);
    return dir;
  }

  File _baseline(Directory dir, String skill) => File('${dir.path}/${_safe(skill)}.baseline');
  File _latest(Directory dir, String skill) => File('${dir.path}/${_safe(skill)}.latest');

  @override
  Future<void> saveTake(String skill, Uint8List bytes) async {
    final dir = await _dir_();
    final baseline = _baseline(dir, skill);
    // The FIRST take becomes the baseline (written once); every take updates latest.
    if (!await baseline.exists()) {
      await baseline.writeAsBytes(bytes, flush: true);
    }
    await _latest(dir, skill).writeAsBytes(bytes, flush: true);
  }

  @override
  Future<VoiceTakes?> takesFor(String skill) async {
    final dir = await _dir_();
    final baseline = _baseline(dir, skill);
    final latest = _latest(dir, skill);
    if (!await baseline.exists() || !await latest.exists()) return null;
    final b = await baseline.readAsBytes();
    final l = await latest.readAsBytes();
    // Only expose a before/after once there are two DISTINCT takes (the first save
    // leaves baseline == latest).
    if (_equal(b, l)) return null;
    return VoiceTakes(baseline: b, latest: l);
  }

  /// Skill -> a safe filename stem (skills are scenario ids, but be defensive).
  static String _safe(String skill) => skill.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_');

  static bool _equal(Uint8List a, Uint8List b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i] != b[i]) return false;
    }
    return true;
  }
}

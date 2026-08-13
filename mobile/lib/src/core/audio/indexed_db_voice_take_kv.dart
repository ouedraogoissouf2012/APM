import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

import 'kv_voice_take_store.dart';

/// [VoiceTakeKvStore] backed by the browser's IndexedDB, so the learner's spoken
/// takes — and therefore the audible before/after (#199) — survive a page reload
/// on the web / PWA build (#205). The previous web fallback was in-memory and lost
/// the "you, 7 days ago vs today" comparison on every reload.
///
/// Thin on purpose: all the take semantics live in [KvVoiceTakeStore]; this only
/// reads and writes raw bytes by key. IndexedDB can't run on the Dart VM, so this
/// adapter is exercised by a browser test rather than the VM suite.
///
/// Privacy (#128): IndexedDB is on-device; raw learner audio never leaves the
/// browser.
class IndexedDbVoiceTakeKv implements VoiceTakeKvStore {
  static const _dbName = 'apm_voice_takes';
  static const _storeName = 'takes';

  web.IDBDatabase? _db;

  Future<web.IDBDatabase> _open() async {
    final cached = _db;
    if (cached != null) return cached;
    final open = web.window.indexedDB.open(_dbName, 1);
    // Create the object store on first open (or a version bump).
    open.onupgradeneeded = ((web.Event _) {
      final db = open.result! as web.IDBDatabase;
      if (!db.objectStoreNames.contains(_storeName)) {
        db.createObjectStore(_storeName);
      }
    }).toJS;
    await _await(open);
    return _db = open.result! as web.IDBDatabase;
  }

  @override
  Future<Uint8List?> read(String key) async {
    final db = await _open();
    final store =
        db.transaction(_storeName.toJS, 'readonly').objectStore(_storeName);
    final request = store.get(key.toJS);
    await _await(request);
    final result = request.result;
    if (result.isUndefinedOrNull) return null;
    return (result as JSUint8Array).toDart;
  }

  @override
  Future<void> write(String key, Uint8List bytes) async {
    final db = await _open();
    final store =
        db.transaction(_storeName.toJS, 'readwrite').objectStore(_storeName);
    await _await(store.put(bytes.toJS, key.toJS));
  }

  @override
  Future<void> delete(String key) async {
    final db = await _open();
    final store =
        db.transaction(_storeName.toJS, 'readwrite').objectStore(_storeName);
    await _await(store.delete(key.toJS));
  }

  @override
  Future<void> clear() async {
    final db = await _open();
    final store =
        db.transaction(_storeName.toJS, 'readwrite').objectStore(_storeName);
    await _await(store.clear());
  }

  @override
  Future<Set<String>> keys() async {
    final db = await _open();
    final store =
        db.transaction(_storeName.toJS, 'readonly').objectStore(_storeName);
    final request = store.getAllKeys();
    await _await(request);
    final result = request.result;
    if (result.isUndefinedOrNull) return const {};
    final array = result! as JSArray<JSAny?>;
    return {for (final item in array.toDart) (item! as JSString).toDart};
  }

  /// Bridges an [web.IDBRequest]'s success/error events to a Future.
  static Future<void> _await(web.IDBRequest request) {
    final done = Completer<void>();
    request.onsuccess = ((web.Event _) {
      if (!done.isCompleted) done.complete();
    }).toJS;
    request.onerror = ((web.Event _) {
      if (!done.isCompleted) {
        done.completeError(
          StateError('IndexedDB error: ${request.error?.name ?? 'unknown'}'),
        );
      }
    }).toJS;
    return done.future;
  }
}

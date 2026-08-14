import 'package:connectivity_plus/connectivity_plus.dart' as plus;

/// Abstraction over the OS-level connectivity signal (#404), kept separate
/// from [ConnectivityController] so the concrete connectivity_plus plugin —
/// which needs a real platform channel — stays swappable for a fake in unit
/// tests instead of leaking into them.
abstract class ConnectivityMonitor {
  /// Emits whenever the OS-reported connectivity changes: `true` when at
  /// least one transport (WiFi, cellular, ...) is up, `false` when none is.
  /// Does not emit the CURRENT state on subscription — only transitions —
  /// so a fresh app start relies on [ConnectivityController.refresh] (the
  /// persisted queue) rather than this stream for its initial state.
  Stream<bool> get onConnectivityChanged;
}

/// Wraps `package:connectivity_plus`'s [plus.Connectivity].
class PlatformConnectivityMonitor implements ConnectivityMonitor {
  PlatformConnectivityMonitor([plus.Connectivity? connectivity])
    : _connectivity = connectivity ?? plus.Connectivity();

  final plus.Connectivity _connectivity;

  @override
  Stream<bool> get onConnectivityChanged => _connectivity.onConnectivityChanged
      .map((results) => results.any((r) => r != plus.ConnectivityResult.none));
}

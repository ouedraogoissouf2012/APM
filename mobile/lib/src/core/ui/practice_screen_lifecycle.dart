import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Stops a voice-practice screen's hot microphone, recording and loops when the
/// learner leaves the screen OR the app goes to the background (#222).
///
/// Before this, only the explicit "end/stop" button stopped the mic. A system
/// back-press or an app switch mid-recording left the microphone live off-screen
/// — and, for the hands-free conversation, the turn loop kept running and the PCM
/// buffer kept growing while another screen was showing. Both are a privacy and a
/// resource problem.
///
/// A screen mixes this in and supplies [stopPractice]. The mixin calls it:
///  - on background — `AppLifecycleListener.onHide`, so the mic stops the moment
///    the app is no longer visible (the session/round is kept so it can resume);
///  - on dispose — which covers the Android system back button and any
///    `context.go`/pop, since removing the route disposes the screen. dispose is
///    strictly more reliable for teardown than a `PopScope` callback (it fires
///    for every way the screen can leave, not just a user-initiated pop), so we
///    hang the cleanup here rather than on `PopScope`.
///
/// [stopPractice] MUST be idempotent: it is called on background and then again
/// on dispose, and possibly after the view-model has already been reset by an
/// explicit "end".
mixin PracticeScreenLifecycle<T extends ConsumerStatefulWidget>
    on ConsumerState<T> {
  AppLifecycleListener? _lifecycle;

  /// Stop the microphone, any in-progress recording, playback and turn loop.
  ///
  /// MUST NOT use this widget's `ref` — it runs on dispose, where Riverpod throws
  /// "Using ref when a widget is about to or has been unmounted is unsafe". Read
  /// the view-model notifier once in [initState] (while mounted) and cache it;
  /// the notifier outlives the widget, so calling its method here is safe.
  @protected
  Future<void> stopPractice();

  @override
  void initState() {
    super.initState();
    // onHide fires when the app stops being visible (backgrounded, app switcher),
    // which is exactly when an off-screen hot mic must be cut.
    _lifecycle = AppLifecycleListener(onHide: () => stopPractice());
  }

  @override
  void dispose() {
    _lifecycle?.dispose();
    // Fire-and-forget: the view-model outlives the widget (its provider is not
    // autoDispose), so it is safe to drive teardown from here. Runs BEFORE
    // super.dispose() while `ref` is still usable.
    stopPractice();
    super.dispose();
  }
}

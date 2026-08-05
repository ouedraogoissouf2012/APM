import 'package:apm/src/core/offline/connectivity_controller.dart';
import 'package:apm/src/ui/conversation/widgets/network_banner.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// A controller stub exposing a fixed state, so the banner can be tested without
/// the queue/sync plumbing.
class _StubController extends ConnectivityController {
  _StubController(this._initial);
  final ConnectivityState _initial;

  @override
  ConnectivityState build() => _initial;
}

Future<void> _pump(WidgetTester tester, ConnectivityState state) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        connectivityControllerProvider.overrideWith(() => _StubController(state)),
      ],
      child: const MaterialApp(home: Scaffold(body: NetworkBanner())),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('is hidden when online with no pending turns', (tester) async {
    await _pump(tester, const ConnectivityState(online: true, pendingCount: 0));
    expect(find.byKey(const Key('network_banner')), findsNothing);
  });

  testWidgets('shows an offline message with pending turns', (tester) async {
    await _pump(tester, const ConnectivityState(online: false, pendingCount: 2));
    expect(find.byKey(const Key('network_banner')), findsOneWidget);
    expect(find.textContaining('Hors ligne'), findsOneWidget);
    expect(find.byKey(const Key('network_retry')), findsOneWidget);
  });

  testWidgets('shows a pending count when back online but not yet synced',
      (tester) async {
    await _pump(tester, const ConnectivityState(online: true, pendingCount: 1));
    expect(find.byKey(const Key('network_banner')), findsOneWidget);
    expect(find.textContaining('en attente'), findsOneWidget);
  });
}

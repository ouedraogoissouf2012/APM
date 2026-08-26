import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/data/repositories/billing_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements AuthenticatedApiClient {}

void main() {
  test('getSubscription reads GET /me/subscription', () async {
    final api = _MockApiClient();
    when(() => api.getJson('/me/subscription')).thenAnswer(
      (_) async => {
        'tier': 'free',
        'is_premium': false,
        'free_daily_minutes': 10,
        'minutes_used_today': 8,
        'remaining_minutes': 2,
      },
    );

    final sub = await BillingRepository(api).getSubscription();

    expect(sub.remainingMinutes, 2);
    expect(sub.quotaWarning, isTrue);
  });
}

import '../../core/network/authenticated_api_client.dart';
import '../models/subscription.dart';

class BillingRepository {
  BillingRepository(this._api);

  final AuthenticatedApiClient _api;

  Future<Subscription> getSubscription() async {
    final json = await _api.getJson('/me/subscription');
    return Subscription.fromJson(json);
  }
}

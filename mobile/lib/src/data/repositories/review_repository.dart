import '../../core/network/authenticated_api_client.dart';
import '../models/review_item.dart';

/// Reads the learner's spaced-repetition queue (error types due to review).
class ReviewRepository {
  ReviewRepository(this._api);

  final AuthenticatedApiClient _api;

  Future<List<ReviewItem>> dueItems() async {
    final items = await _api.getList('/me/review');
    return items
        .map((e) => ReviewItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }
}

import '../../core/network/authenticated_api_client.dart';
import '../models/vocabulary_entry.dart';

/// Reads and updates the learner's vocabulary notebook.
class VocabularyRepository {
  VocabularyRepository(this._api);

  final AuthenticatedApiClient _api;

  Future<List<VocabularyEntry>> list() async {
    final items = await _api.getList('/vocabulary');
    return items
        .map((e) => VocabularyEntry.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Marks a card 'known' (Je le sais) or 'review' (Encore).
  Future<VocabularyEntry> setStatus(int entryId, String status) async {
    final json = await _api.patchJson(
      '/vocabulary/$entryId',
      body: {'status': status},
    );
    return VocabularyEntry.fromJson(json);
  }
}

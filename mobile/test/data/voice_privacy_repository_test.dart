import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/data/repositories/voice_privacy_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements AuthenticatedApiClient {}

void main() {
  late _MockApiClient api;
  late VoicePrivacyRepository repo;

  setUp(() {
    api = _MockApiClient();
    repo = VoicePrivacyRepository(api);
  });

  test('getConsent parses the consent record', () async {
    when(() => api.getJson('/me/voice-consent')).thenAnswer(
      (_) async => {
        'transcription': true,
        'scoring': false,
        'b2b_share': false,
        'model_training': false,
      },
    );
    final consent = await repo.getConsent();
    expect(consent.transcription, isTrue);
    expect(consent.scoring, isFalse);
  });

  test('setConsent PUTs a partial body', () async {
    Map<String, dynamic>? sentBody;
    when(
      () => api.putJson('/me/voice-consent', body: any(named: 'body')),
    ).thenAnswer((invocation) async {
      sentBody = invocation.namedArguments[#body] as Map<String, dynamic>;
      return {
        'transcription': false,
        'scoring': false,
        'b2b_share': false,
        'model_training': false,
      };
    });

    final consent = await repo.setConsent('transcription', false);
    expect(sentBody, {'transcription': false});
    expect(consent.transcription, isFalse);
  });

  test('exportData returns the export payload', () async {
    when(() => api.postJson('/me/voice-data/export')).thenAnswer(
      (_) async => {
        'raw_audio_retained': false,
        'utterances': [
          {'text': 'I like sports'},
        ],
        'vocabulary': <dynamic>[],
      },
    );
    final data = await repo.exportData();
    expect(data['raw_audio_retained'], isFalse);
    expect((data['utterances'] as List), hasLength(1));
  });

  test('eraseData returns the deleted counts', () async {
    when(() => api.deleteJson('/me/voice-data')).thenAnswer(
      (_) async => {
        'deleted': {'transcripts': 2, 'vocabulary': 5},
      },
    );
    final deleted = await repo.eraseData();
    expect(deleted['transcripts'], 2);
    expect(deleted['vocabulary'], 5);
  });
}

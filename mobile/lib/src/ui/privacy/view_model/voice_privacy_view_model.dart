import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/providers.dart';
import '../../../data/models/voice_consent.dart';
import '../../../data/repositories/voice_privacy_repository.dart';

final voicePrivacyRepositoryProvider = Provider<VoicePrivacyRepository>(
  (ref) => VoicePrivacyRepository(ref.watch(authenticatedApiClientProvider)),
);

/// The learner's current voice consents (for the privacy screen).
final voiceConsentProvider = FutureProvider<VoiceConsent>(
  (ref) => ref.read(voicePrivacyRepositoryProvider).getConsent(),
);

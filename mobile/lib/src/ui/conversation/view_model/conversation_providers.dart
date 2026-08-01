import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/providers.dart';
import '../../../core/speech/speech_service.dart';
import '../../../data/repositories/conversation_repository.dart';

/// Providers shared by the ConversationViewModel and its extracted controllers
/// (#121). Kept here (not inside the view-model file) so a controller can read
/// them without importing the view-model — avoiding a circular dependency.

/// A single long-lived speech service. It must NEVER be rebuilt: the underlying
/// speech_to_text plugin is a process singleton that binds its status callback
/// to the first instance — a second instance would hang forever. Accent changes
/// go through setLanguage() in ConversationViewModel.start.
final speechServiceProvider = Provider<SpeechService>(
  (ref) => DeviceSpeechService(),
);

final conversationRepositoryProvider = Provider<ConversationRepository>(
  (ref) => ConversationRepository(ref.watch(authenticatedApiClientProvider)),
);

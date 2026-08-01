import 'conversation_state.dart';

/// The seam between the ConversationViewModel and its extracted controllers
/// (#121). A controller reads and writes the shared [ConversationState] and asks
/// "am I still live?" through this narrow interface instead of holding the
/// Notifier directly — so each controller depends on an abstraction (DIP), stays
/// unit-testable with a tiny fake, and can never reach into the Notifier's guts.
abstract class ConversationHost {
  /// The current conversation state.
  ConversationState get state;

  /// Replace the conversation state (the Notifier applies it to the UI).
  set state(ConversationState value);

  /// Whether the notifier is still mounted (not disposed). A step resolving
  /// after the screen is gone must not touch state.
  bool get mounted;
}

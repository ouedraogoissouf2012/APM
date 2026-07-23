// Pure greeting helpers for the home screen (DESIGN_SPEC §6.3). No state, no
// I/O — the widget passes in the email and the current hour, so both are
// trivially testable and deterministic.

/// A friendly display name derived from an email's local part, capitalised.
/// Returns '' for empty/malformed input (the caller shows a neutral greeting).
String displayNameFromEmail(String? email) {
  if (email == null) return '';
  final at = email.indexOf('@');
  final local = at <= 0 ? '' : email.substring(0, at);
  if (local.isEmpty) return '';
  return '${local[0].toUpperCase()}${local.substring(1)}';
}

/// Time-appropriate greeting for a 24-hour [hour]. Out-of-range values fall
/// back to evening rather than throwing — a bad clock must never crash home.
String greetingForHour(int hour) {
  if (hour >= 6 && hour < 12) return 'Good morning';
  if (hour >= 12 && hour < 18) return 'Good afternoon';
  return 'Good evening';
}

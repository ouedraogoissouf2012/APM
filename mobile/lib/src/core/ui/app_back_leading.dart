import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../router/routes.dart';

/// Back control that always does something useful: pop if there is a stack,
/// otherwise go home (or [fallback] for public/auth screens).
class AppBackLeading extends StatelessWidget {
  const AppBackLeading({super.key, this.fallback = Routes.home});

  final String fallback;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      key: const Key('app_back'),
      icon: const Icon(Icons.arrow_back),
      tooltip: 'Retour',
      onPressed: () => popOrFallback(context, fallback),
    );
  }

  static void popOrFallback(
    BuildContext context, [
    String fallback = Routes.home,
  ]) {
    if (context.canPop()) {
      context.pop();
      return;
    }
    context.go(fallback);
  }
}

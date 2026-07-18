import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'src/core/router/app_router.dart';
import 'src/core/theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  _registerFontLicenses();
  runApp(const ProviderScope(child: ApmApp()));
}

/// Fraunces et Inter sont bundlées (licence SIL OFL) : leurs licences
/// doivent apparaître dans le LicenseRegistry de l'app.
void _registerFontLicenses() {
  LicenseRegistry.addLicense(() async* {
    yield LicenseEntryWithLineBreaks(
      ['Fraunces'],
      await rootBundle.loadString('assets/fonts/fraunces/OFL.txt'),
    );
    yield LicenseEntryWithLineBreaks(
      ['Inter'],
      await rootBundle.loadString('assets/fonts/inter/OFL.txt'),
    );
  });
}

class ApmApp extends ConsumerWidget {
  const ApmApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(appRouterProvider);
    return MaterialApp.router(
      title: 'APM',
      // Sombre = défaut de toute l'app (DESIGN_SPEC : on parle le soir).
      // Le mode cream s'applique localement (bilan, carnet) via
      // `Theme(data: AppTheme.light(), ...)`.
      theme: AppTheme.dark(),
      routerConfig: router,
    );
  }
}

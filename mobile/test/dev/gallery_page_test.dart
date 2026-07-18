import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/design_system/molecules/correction_chip.dart';
import 'package:apm/src/design_system/molecules/transcript_text.dart';
import 'package:apm/src/design_system/organisms/voice_orb.dart';
import 'package:apm/src/dev/gallery_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('la galerie expose chaque composant du design system',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.dark(),
      home: const GalleryPage(),
    ));
    // Pumps bornés : l'orbe anime en boucle, pumpAndSettle ne converge pas.
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.textContaining('Good evening'), findsOneWidget);
    expect(find.byType(VoiceOrb), findsWidgets);

    // La ListView est paresseuse : on scrolle jusqu'aux composants bas.
    final scrollable = find.byType(Scrollable).first;
    await tester.scrollUntilVisible(
      find.byType(TranscriptText),
      150,
      scrollable: scrollable,
    );
    expect(find.byType(TranscriptText), findsOneWidget);

    await tester.scrollUntilVisible(
      find.byType(CorrectionChip),
      150,
      scrollable: scrollable,
    );
    expect(find.byType(CorrectionChip), findsOneWidget);
  });
}

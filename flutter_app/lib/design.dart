/// Système de design de Jade — source unique des valeurs visuelles.
///
/// Aucun widget ne doit coder en dur une taille, un espacement, un rayon ou une
/// durée : tout vient d'ici (ou de la palette `context.jade` dans theme.dart).
/// Distillé des principes Anthropic (frontend-design), Vercel (Web Interface
/// Guidelines) et Material 3. Voir `.claude/skills/jade-ui-design`.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'theme.dart';

// ─────────────────────────────────────────────────────────────── espacements
/// Grille de 4 px. N'utiliser que ces pas.
abstract final class JadeSpace {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xxl = 24;
  static const double xxxl = 32;
  static const double huge = 40;
}

// ─────────────────────────────────────────────────────────────────── rayons
abstract final class JadeRadius {
  static const double xs = 6;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double pill = 999;

  static BorderRadius all(double r) => BorderRadius.circular(r);
}

// ──────────────────────────────────────────────────────────── échelle de type
/// Une seule échelle typographique. Recolorer avec `.copyWith(color: …)`.
abstract final class JadeType {
  static const _tabular = [FontFeature.tabularFigures()];

  // Geomini pour tout (police variable). Titres : poids marqué, tracking serré.
  static const display = TextStyle(
      fontSize: 32,
      fontWeight: FontWeight.w600,
      letterSpacing: -0.5,
      height: 1.12);
  static const headline = TextStyle(
      fontSize: 22,
      fontWeight: FontWeight.w600,
      letterSpacing: -0.2,
      height: 1.2);
  static const title =
      TextStyle(fontSize: 17, fontWeight: FontWeight.w600, height: 1.3);
  static const subtitle =
      TextStyle(fontSize: 15, fontWeight: FontWeight.w600, height: 1.35);
  static const body = TextStyle(fontSize: 14.5, height: 1.6);
  static const label =
      TextStyle(fontSize: 13, fontWeight: FontWeight.w500, height: 1.4);
  static const caption =
      TextStyle(fontSize: 11.5, fontWeight: FontWeight.w500, height: 1.4);
  static const eyebrow = TextStyle(
      fontSize: 10.5, fontWeight: FontWeight.w700, letterSpacing: 0.7, height: 1.3);

  /// Chiffres alignés (compteurs, versions, colonnes de nombres).
  static const tabular = TextStyle(fontFeatures: _tabular);
}

// ──────────────────────────────────────────────────────────────── élévation
abstract final class JadeElevation {
  /// Ombre douce à deux couches (contact + diffusion) pour un relief crédible.
  static List<BoxShadow> soft(BuildContext context) {
    final d = context.isDark;
    return [
      BoxShadow(
        color: Colors.black.withValues(alpha: d ? 0.30 : 0.04),
        blurRadius: 3,
        offset: const Offset(0, 1),
      ),
      BoxShadow(
        color: Colors.black.withValues(alpha: d ? 0.38 : 0.07),
        blurRadius: 24,
        offset: const Offset(0, 10),
      ),
    ];
  }

  static List<BoxShadow> lift(BuildContext context) {
    final d = context.isDark;
    return [
      BoxShadow(
        color: Colors.black.withValues(alpha: d ? 0.34 : 0.06),
        blurRadius: 4,
        offset: const Offset(0, 2),
      ),
      BoxShadow(
        color: Colors.black.withValues(alpha: d ? 0.46 : 0.12),
        blurRadius: 32,
        offset: const Offset(0, 16),
      ),
    ];
  }
}

// ──────────────────────────────────────────────────────────────────── motion
extension JadeMotion on BuildContext {
  /// Respecte « réduire les animations » du système : renvoie 0 si désactivé.
  Duration motion(Duration d) =>
      MediaQuery.maybeOf(this)?.disableAnimations == true ? Duration.zero : d;

  bool get isDark => Theme.of(this).brightness == Brightness.dark;
}

// ─────────────────────────────────────────────────────────── survol (hover)
/// Reconstruit son enfant selon l'état de survol. Curseur main par défaut.
class Hoverable extends StatefulWidget {
  final Widget Function(BuildContext context, bool hovering) builder;
  final bool clickable;
  const Hoverable({super.key, required this.builder, this.clickable = true});

  @override
  State<Hoverable> createState() => _HoverableState();
}

class _HoverableState extends State<Hoverable> {
  bool _h = false;
  @override
  Widget build(BuildContext context) => MouseRegion(
        cursor: widget.clickable
            ? SystemMouseCursors.click
            : MouseCursor.defer,
        onEnter: (_) => setState(() => _h = true),
        onExit: (_) => setState(() => _h = false),
        child: widget.builder(context, _h),
      );
}

// ─────────────────────────────────────────────────── anneau de focus clavier
/// Entoure un enfant d'un anneau visible quand il reçoit le focus clavier.
class FocusRing extends StatefulWidget {
  final Widget child;
  final double radius;
  const FocusRing({super.key, required this.child, this.radius = JadeRadius.lg});

  @override
  State<FocusRing> createState() => _FocusRingState();
}

class _FocusRingState extends State<FocusRing> {
  bool _focused = false;
  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Focus(
      canRequestFocus: false,
      descendantsAreFocusable: true,
      onFocusChange: (f) => setState(() => _focused = f),
      child: AnimatedContainer(
        duration: context.motion(const Duration(milliseconds: 140)),
        decoration: BoxDecoration(
          borderRadius: JadeRadius.all(widget.radius + 3),
          border: Border.all(
            color: _focused ? jade.ring : Colors.transparent,
            width: 2,
          ),
        ),
        child: widget.child,
      ),
    );
  }
}

// ─────────────────────────────────────────────────────── marque (gemme Jade)
/// Marque du produit : une gemme jade taillée (Jade = pierre verte), posée sur
/// une tuile arrondie sombre pour faire ressortir les facettes. Élément
/// signature unique — le reste de l'UI reste sobre.
class JadeMark extends StatelessWidget {
  final double size;
  const JadeMark({super.key, this.size = 38});

  // Gemme « jade » taillée mais en bleu Jade (marque du produit).
  static const _gemTop = Color(0xFF8FBEFF);
  static const _gemMid = Color(0xFF2E6FD6);
  static const _gemDeep = Color(0xFF002B67);
  static const _tile = Color(0xFF07234A);

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [_tile, Color(0xFF04152E)],
        ),
        borderRadius: JadeRadius.all(size * 0.3),
        boxShadow: [
          BoxShadow(
            color: _gemMid.withValues(alpha: context.isDark ? 0.36 : 0.30),
            blurRadius: size * 0.32,
            offset: Offset(0, size * 0.14),
          ),
        ],
      ),
      child: Center(
        child: CustomPaint(
          size: Size(size * 0.52, size * 0.6),
          painter: _GemPainter(top: _gemTop, mid: _gemMid, deep: _gemDeep),
        ),
      ),
    );
  }
}

/// Gemme taillée « brillant » vue de profil : table plate, couronne facettée,
/// pavillon convergeant en pointe. Dégradé vertical + facettes ombrées + éclat.
class _GemPainter extends CustomPainter {
  final Color top;
  final Color mid;
  final Color deep;
  _GemPainter({required this.top, required this.mid, required this.deep});

  @override
  void paint(Canvas canvas, Size s) {
    final w = s.width, h = s.height;
    final crown = h * 0.34; // ligne du rondiste (bas de la couronne)
    final gx = w * 0.14; // retrait des épaules
    final cx = w * 0.5;

    // silhouette complète, remplie d'un dégradé jade vertical
    final outline = Path()
      ..moveTo(w * 0.28, 0)
      ..lineTo(w * 0.72, 0)
      ..lineTo(w - gx, crown)
      ..lineTo(cx, h)
      ..lineTo(gx, crown)
      ..close();
    canvas.drawPath(
      outline,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [top, mid, deep],
          stops: const [0.0, 0.5, 1.0],
        ).createShader(Rect.fromLTWH(0, 0, w, h)),
    );

    // facettes ombrées (côté droit) — donne du relief à la taille
    final shade = Paint()..color = Colors.black.withValues(alpha: 0.16);
    canvas.drawPath(
      Path()
        ..moveTo(cx, crown)
        ..lineTo(w - gx, crown)
        ..lineTo(cx, h)
        ..close(),
      shade,
    );
    canvas.drawPath(
      Path()
        ..moveTo(w * 0.72, 0)
        ..lineTo(w - gx, crown)
        ..lineTo(cx, crown)
        ..close(),
      shade,
    );

    // arête de table + facettes claires (côté gauche) — lumière
    final light = Paint()..color = Colors.white.withValues(alpha: 0.14);
    canvas.drawPath(
      Path()
        ..moveTo(w * 0.28, 0)
        ..lineTo(cx, crown)
        ..lineTo(gx, crown)
        ..close(),
      light,
    );

    // rondiste (fine ligne claire au niveau de la ceinture)
    canvas.drawLine(
      Offset(gx, crown),
      Offset(w - gx, crown),
      Paint()
        ..color = Colors.white.withValues(alpha: 0.22)
        ..strokeWidth = math.max(0.8, w * 0.012),
    );

    // éclat spéculaire sur la table
    canvas.drawPath(
      Path()
        ..moveTo(w * 0.34, h * 0.06)
        ..lineTo(w * 0.46, h * 0.06)
        ..lineTo(w * 0.40, crown * 0.86)
        ..close(),
      Paint()..color = Colors.white.withValues(alpha: 0.5),
    );
  }

  @override
  bool shouldRepaint(covariant _GemPainter old) =>
      old.top != top || old.mid != mid || old.deep != deep;
}

// ───────────────────────────────────────────────── libellé de section (eyebrow)
class SectionLabel extends StatelessWidget {
  final String text;
  const SectionLabel(this.text, {super.key});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(
            JadeSpace.sm, JadeSpace.lg, JadeSpace.sm, JadeSpace.xs),
        child: Text(text.toUpperCase(),
            style: JadeType.eyebrow.copyWith(color: context.jade.faint)),
      );
}

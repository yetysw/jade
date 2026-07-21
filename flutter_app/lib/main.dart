/// Jade 2.0 — application de bureau native (Flutter Windows).
///
/// L'interface est 100 % native ; toute la logique documentaire (RAG,
/// indexation, sécurité, création de fichiers) reste dans le backend local
/// Python, inchangé (localhost:8765).
library;

import 'package:flutter/material.dart';

import 'backend.dart';
import 'design.dart';
import 'home.dart';
import 'tabler.dart';
import 'theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const JadeApp());
}

class JadeApp extends StatefulWidget {
  const JadeApp({super.key});

  static JadeAppState of(BuildContext context) =>
      context.findAncestorStateOfType<JadeAppState>()!;

  @override
  State<JadeApp> createState() => JadeAppState();
}

class JadeAppState extends State<JadeApp> {
  ThemeMode _mode = ThemeMode.system;

  ThemeMode get themeMode => _mode;

  void cycleTheme() {
    setState(() {
      _mode = switch (_mode) {
        ThemeMode.system => ThemeMode.light,
        ThemeMode.light => ThemeMode.dark,
        ThemeMode.dark => ThemeMode.system,
      };
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Jade',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      themeMode: _mode,
      home: const _Boot(),
    );
  }
}

/// Écran de démarrage : s'assure que le backend local répond avant d'ouvrir
/// l'interface (le lance s'il est installé à côté de l'application).
class _Boot extends StatefulWidget {
  const _Boot();

  @override
  State<_Boot> createState() => _BootState();
}

class _BootState extends State<_Boot> {
  final _backend = BackendManager();
  String? _error;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start() async {
    final err = await _backend.ensureRunning();
    if (!mounted) return;
    if (err == null) {
      final d = context.motion(const Duration(milliseconds: 260));
      Navigator.of(context).pushReplacement(
        PageRouteBuilder(
          transitionDuration: d,
          pageBuilder: (_, __, ___) => const HomeScreen(),
          transitionsBuilder: (_, anim, __, child) => FadeTransition(
            opacity: CurvedAnimation(parent: anim, curve: Curves.easeOut),
            child: child,
          ),
        ),
      );
    } else {
      setState(() => _error = err);
    }
  }

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    final ok = _error == null;
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const JadeMark(size: 72),
              const SizedBox(height: JadeSpace.xxl),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (!ok) ...[
                    Icon(TablerIcons.alertCircle, size: 18, color: jade.danger),
                    const SizedBox(width: JadeSpace.sm),
                  ],
                  Text(
                    ok ? 'Démarrage de Jade…' : 'Backend indisponible',
                    style: JadeType.title.copyWith(color: jade.text),
                  ),
                ],
              ),
              const SizedBox(height: JadeSpace.md),
              if (ok)
                SizedBox(
                  width: 132,
                  child: ClipRRect(
                    borderRadius: JadeRadius.all(JadeRadius.pill),
                    child: LinearProgressIndicator(
                      minHeight: 3,
                      backgroundColor: jade.tile,
                      color: jade.primary,
                    ),
                  ),
                )
              else ...[
                Text(
                  _error!,
                  textAlign: TextAlign.center,
                  style: JadeType.label.copyWith(color: jade.muted, height: 1.55),
                ),
                const SizedBox(height: JadeSpace.xl),
                FilledButton(
                  style: FilledButton.styleFrom(
                    backgroundColor: jade.primary,
                    padding: const EdgeInsets.symmetric(
                        horizontal: JadeSpace.xxl, vertical: JadeSpace.md),
                    shape: RoundedRectangleBorder(
                        borderRadius: JadeRadius.all(JadeRadius.md)),
                  ),
                  onPressed: () {
                    setState(() => _error = null);
                    _start();
                  },
                  child: const Text('Réessayer'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

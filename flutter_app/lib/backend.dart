/// Démarrage / surveillance du backend local (ragagent).
///
/// En production, l'exécutable backend (Jade backend, PyInstaller) est installé
/// à côté de l'app Flutter : `backend\JadeBackend.exe serve`. En développement,
/// on suppose que `jade serve` tourne déjà — on se contente de le détecter.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'api.dart';

class BackendManager {
  Process? _process;

  /// Vrai si le backend répond déjà sur le port local.
  Future<bool> isUp() async {
    try {
      final resp = await http
          .get(Uri.parse('$kBackendBase/api/status'))
          .timeout(const Duration(seconds: 2));
      return resp.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// S'assure que le backend tourne ; le lance s'il est installé à côté.
  /// Retourne un message d'erreur, ou null si tout va bien.
  Future<String?> ensureRunning({
    Duration timeout = const Duration(seconds: 60),
  }) async {
    if (await isUp()) return null;

    final exe = _findBackendExe();
    if (exe == null) {
      return 'Backend Jade introuvable. En développement, lancer « jade serve » '
          'puis rouvrir l’application.';
    }
    try {
      _process = await Process.start(
        exe,
        ['serve'],
        workingDirectory: File(exe).parent.path,
        mode: ProcessStartMode.detachedWithStdio,
      );
      // journal minimal en cas de souci de démarrage
      unawaited(_process!.stdout.transform(utf8.decoder).drain<void>());
      unawaited(_process!.stderr.transform(utf8.decoder).drain<void>());
    } catch (e) {
      return 'Impossible de démarrer le backend : $e';
    }

    final deadline = DateTime.now().add(timeout);
    while (DateTime.now().isBefore(deadline)) {
      if (await isUp()) return null;
      await Future<void>.delayed(const Duration(seconds: 1));
    }
    return 'Le backend ne répond pas après ${timeout.inSeconds} s '
        '(indexation initiale en cours ?).';
  }

  /// Cherche l'exécutable backend installé à côté de l'app Flutter.
  String? _findBackendExe() {
    final appDir = File(Platform.resolvedExecutable).parent.path;
    for (final candidate in [
      '$appDir\\backend\\Jade.exe', // installé (dossier backend/)
      '$appDir\\Jade.exe', // à plat à côté de l'UI
      '${File(appDir).parent.path}\\Jade\\Jade.exe',
    ]) {
      if (File(candidate).existsSync()) return candidate;
    }
    return null;
  }
}

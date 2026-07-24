/// Démarrage / surveillance du backend local (ragagent).
///
/// Le backend choisit un **port libre par session** (isolation RDS : chaque
/// utilisateur du serveur a SON processus, ses conversations et ses droits
/// NTFS) et le publie dans `<données utilisateur>/Jade/backend.json`. Cette
/// classe lit ce fichier, vérifie que le backend répond, le lance sinon, puis
/// fixe `backendBase` pour tout le client HTTP.
///
/// En développement, `jade serve` (port 8765 par défaut) est détecté en repli.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'api.dart';

class BackendManager {
  Process? _process;

  /// Dossier de données par utilisateur — le même que `platformdirs` côté
  /// backend (user_data_dir("Jade", appauthor=False)).
  static String? userDataDir() {
    if (Platform.isWindows) {
      final base = Platform.environment['LOCALAPPDATA'];
      return base == null ? null : '$base\\Jade';
    }
    final home = Platform.environment['HOME'];
    if (home == null) return null;
    if (Platform.isMacOS) return '$home/Library/Application Support/Jade';
    final xdg = Platform.environment['XDG_DATA_HOME'];
    return '${xdg ?? '$home/.local/share'}/Jade';
  }

  /// Port + jeton publiés par le backend de cette session, ou null.
  static (int, String)? _discovered() {
    final dir = userDataDir();
    if (dir == null) return null;
    final f = File('$dir${Platform.pathSeparator}backend.json');
    if (!f.existsSync()) return null;
    try {
      final j = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
      final port = j['port'] as int?;
      final token = j['token'] as String?;
      if (port == null || token == null) return null;
      return (port, token);
    } catch (_) {
      return null;
    }
  }

  /// Vrai si NOTRE backend répond sur ce port (jeton accepté) ; fixe
  /// `backendBase`/`backendToken` si oui. Un backend qui répond 401 (jeton
  /// refusé) appartient à une autre session → considéré indisponible.
  Future<bool> _probe(int port, String token) async {
    try {
      final base = 'http://127.0.0.1:$port';
      final resp = await http.get(
        Uri.parse('$base/api/status'),
        headers: {'X-Jade-Token': token},
      ).timeout(const Duration(seconds: 2));
      if (resp.statusCode == 200) {
        backendBase = base;
        backendToken = token;
        return true;
      }
    } catch (_) {}
    return false;
  }

  /// Cherche NOTRE backend vivant via le fichier de découverte (port + jeton).
  Future<bool> isUp() async {
    final d = _discovered();
    if (d != null && await _probe(d.$1, d.$2)) return true;
    return false;
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
    return 'Le moteur local ne répond pas après ${timeout.inSeconds} s. '
        'Fermer puis rouvrir l’application ; si le problème persiste, '
        'vérifier l’antivirus ou réinstaller.';
  }

  /// Cherche l'exécutable backend installé à côté de l'app Flutter
  /// (multiplateforme : « Jade.exe » sous Windows, « Jade » ailleurs).
  String? _findBackendExe() {
    final appDir = File(Platform.resolvedExecutable).parent.path;
    final exe = Platform.isWindows ? 'Jade.exe' : 'Jade';
    final s = Platform.pathSeparator;
    final parent = File(appDir).parent.path;
    for (final candidate in [
      '$appDir${s}backend$s$exe', // installé (dossier backend/)
      '$appDir$s$exe', // à plat à côté de l'UI
      '$parent${s}Jade$s$exe',
    ]) {
      if (File(candidate).existsSync()) return candidate;
    }
    return null;
  }
}

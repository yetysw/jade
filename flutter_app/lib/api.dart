/// Client HTTP du backend local Jade (FastAPI, 127.0.0.1:8765).
///
/// Toute la logique métier (RAG, routage, fichiers, sécurité) vit côté
/// backend — cette couche ne fait que du transport, y compris le flux SSE
/// des réponses en streaming.
library;

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

/// Base de l'API du backend local. Le port est **dynamique par session**
/// (isolation RDS) : BackendManager le découvre via le fichier
/// `%LOCALAPPDATA%\Jade\backend.json` au démarrage et met cette valeur à jour
/// avant l'ouverture de l'interface. 8765 = repli développement.
String backendBase = 'http://127.0.0.1:8765';

/// Jeton de session partagé UI↔backend (lu depuis backend.json par
/// BackendManager). Envoyé sur chaque requête : le backend rejette (401) tout
/// appel sans ce jeton — c'est ce qui isole les sessions RDS entre elles.
String? backendToken;

/// Client type du backend local (`127.0.0.1`) : requetes HTTP et flux SSE de
/// l'endpoint /ask. Joint le jeton de session ([backendToken]) a chaque appel.
class ApiClient {
  final http.Client _client = http.Client();

  Uri _u(String path) => Uri.parse('$backendBase$path');

  Future<dynamic> _json(String method, String path, [Object? body]) async {
    final req = http.Request(method, _u(path));
    req.headers['Content-Type'] = 'application/json';
    if (backendToken != null) req.headers['X-Jade-Token'] = backendToken!;
    if (body != null) req.body = jsonEncode(body);
    final streamed = await _client.send(req);
    final resp = await http.Response.fromStream(streamed);
    if (resp.statusCode >= 400) {
      String detail;
      try {
        detail = (jsonDecode(utf8.decode(resp.bodyBytes))
                as Map<String, dynamic>)['detail']
            .toString();
      } catch (_) {
        detail = 'Erreur HTTP ${resp.statusCode}';
      }
      throw ApiException(detail, resp.statusCode);
    }
    if (resp.bodyBytes.isEmpty) return null;
    return jsonDecode(utf8.decode(resp.bodyBytes));
  }

  // ------------------------------------------------------------ statut

  Future<AppStatus> status() async =>
      AppStatus.fromJson(await _json('GET', '/api/status'));

  /// Progression du démarrage (téléchargement/chargement des modèles).
  Future<InitStatus> initStatus() async =>
      InitStatus.fromJson(await _json('GET', '/api/init'));

  /// État de santé (LLM, modèles, disque) pour le bandeau et le diagnostic.
  Future<HealthInfo> health() async =>
      HealthInfo.fromJson(await _json('GET', '/api/health'));

  // ---------------------------------------- identifiants de connexion

  /// Identifiants de connexion actuels (le secret n'est jamais renvoyé).
  Future<ConnConfig> getConfig() async =>
      ConnConfig.fromJson(await _json('GET', '/api/config'));

  /// Enregistre et applique à chaud les identifiants de connexion. Un secret
  /// vide conserve celui déjà enregistré. Retourne l'état du LLM après essai.
  Future<Map<String, dynamic>> setConfig({
    required String ollamaUrl,
    required String searxngUrl,
    required String cfClientId,
    String cfSecret = '',
  }) async =>
      (await _json('POST', '/api/config', {
        'ollama_url': ollamaUrl,
        'searxng_url': searxngUrl,
        'cf_client_id': cfClientId,
        'cf_secret': cfSecret,
      })) as Map<String, dynamic>;

  // ---------------------------------------------- premier lancement / légal

  /// État du premier lancement (acceptation légale, onboarding).
  Future<OnboardingState> onboardingState() async =>
      OnboardingState.fromJson(await _json('GET', '/api/onboarding'));

  /// Enregistre l'acceptation des CGU + politique de confidentialité.
  Future<void> acceptLegal() => _json('POST', '/api/onboarding/accept-legal');

  /// Marque le parcours d'accueil comme terminé.
  Future<void> completeOnboarding() =>
      _json('POST', '/api/onboarding/complete');

  /// Texte Markdown d'un document légal (`cgu` | `privacy`).
  Future<String> legalDoc(String name) async {
    final j = await _json('GET', '/api/legal/doc?name=$name');
    return (j?['markdown'] ?? '') as String;
  }

  // ------------------------------------------------ sauvegarde / migration

  /// Exporte l'historique dans un fichier .jadebak. Retourne le chemin produit
  /// et le nombre d'éléments sauvegardés.
  Future<Map<String, dynamic>> backupChats({String dest = ''}) async =>
      (await _json('POST', '/api/backup', {'dest': dest}))
          as Map<String, dynamic>;

  /// Restaure un fichier .jadebak (fusion non destructive). Retourne le nombre
  /// d'éléments réellement importés.
  Future<Map<String, dynamic>> restoreChats(String path) async =>
      (await _json('POST', '/api/restore', {'path': path}))
          as Map<String, dynamic>;

  // ------------------------------------------------------- mises à jour

  /// État de mise à jour (release Gitea la plus récente). Ne lève jamais :
  /// en cas de souci réseau, renvoie « pas de mise à jour ».
  Future<UpdateInfo> checkUpdate({bool force = false}) async {
    try {
      final j = await _json('GET', '/api/update${force ? '?force=true' : ''}');
      return UpdateInfo.fromJson(j);
    } catch (_) {
      return const UpdateInfo(
          current: '', latest: '', available: false, mode: 'off', notes: '',
          assetSize: 0);
    }
  }

  Future<DownloadProgress> startDownload() async =>
      DownloadProgress.fromJson(await _json('POST', '/api/update/download'));

  Future<DownloadProgress> downloadProgress() async =>
      DownloadProgress.fromJson(await _json('GET', '/api/update/progress'));

  /// Lance l'installateur téléchargé. L'app doit se fermer juste après.
  Future<void> applyUpdate() => _json('POST', '/api/update/apply');

  // ----------------------------------------------------- conversations

  Future<List<Conversation>> listConversations() async {
    final list = await _json('GET', '/api/conversations') as List;
    return list
        .map((c) => Conversation.fromJson(c as Map<String, dynamic>))
        .toList();
  }

  Future<Conversation> createConversation() async =>
      Conversation.fromJson(await _json('POST', '/api/conversations'));

  Future<(Conversation, List<Message>)> getConversation(String id) async {
    final j = await _json('GET', '/api/conversations/$id');
    final conv = Conversation.fromJson(j);
    final msgs = (j['messages'] as List? ?? [])
        .map((m) => Message.fromJson(m as Map<String, dynamic>))
        .toList();
    return (conv, msgs);
  }

  Future<void> rename(String id, String title) =>
      _json('PATCH', '/api/conversations/$id', {'title': title});

  Future<void> delete(String id) => _json('DELETE', '/api/conversations/$id');

  Future<void> setFlag(String id, String field, bool value) => _json(
      'PATCH', '/api/conversations/$id/flag', {'field': field, 'value': value});

  Future<List<Conversation>> search(String q) async {
    final list = await _json(
        'GET', '/api/conversations/search?q=${Uri.encodeQueryComponent(q)}') as List;
    return list
        .map((c) => Conversation.fromJson(c as Map<String, dynamic>))
        .toList();
  }

  // --------------------------------------------------- réglages (indexation)

  Future<IndexSettings> getSettings() async =>
      IndexSettings.fromJson(await _json('GET', '/api/settings'));

  Future<IndexSettings> addRoot(String path) async {
    await _json('POST', '/api/settings/roots', {'action': 'add', 'path': path});
    return getSettings();
  }

  Future<IndexSettings> removeRoot(String path) async {
    await _json(
        'POST', '/api/settings/roots', {'action': 'remove', 'path': path});
    return getSettings();
  }

  Future<void> reindex({bool full = false}) =>
      _json('POST', '/api/settings/reindex', {'full': full});

  /// Envoie un retour utilisateur à Jade (e-mail via le backend).
  Future<void> sendFeedback(String content) =>
      _json('POST', '/api/feedback', {'content': content});

  /// Supprime tout l'historique de conversations. Retourne le nombre supprimé.
  Future<int> clearConversations() async {
    final j = await _json('DELETE', '/api/conversations');
    return (j?['deleted'] ?? 0) as int;
  }

  Future<void> clearMemory() => _json('POST', '/api/memory/clear');

  // ---------------------------------------------------------------- profil

  /// Nom actuellement utilisé par Jade pour s'adresser à l'utilisateur (nom
  /// choisi ou, à défaut, nom du compte Windows).
  Future<Profile> getProfile() async =>
      Profile.fromJson(await _json('GET', '/api/profile'));

  /// Définit le nom d'affichage. Une chaîne vide réinitialise sur le nom du
  /// compte Windows.
  Future<Profile> setProfile(String displayName) async => Profile.fromJson(
      await _json('POST', '/api/profile', {'display_name': displayName}));

  // ---------------------------------------------------------- dossiers

  Future<List<Folder>> listFolders() async {
    final list = await _json('GET', '/api/folders') as List;
    return list.map((f) => Folder.fromJson(f as Map<String, dynamic>)).toList();
  }

  Future<Folder> createFolder(String name) async =>
      Folder.fromJson(await _json('POST', '/api/folders', {'title': name}));

  Future<void> renameFolder(String id, String name) =>
      _json('PATCH', '/api/folders/$id', {'title': name});

  Future<void> deleteFolder(String id) => _json('DELETE', '/api/folders/$id');

  Future<void> moveConversation(String cid, String? folderId) => _json(
      'PATCH', '/api/conversations/$cid/folder', {'folder_id': folderId});

  // ------------------------------------------------------------ fichiers

  Future<void> openFile(String path, {bool reveal = false}) =>
      _json('POST', '/api/open', {'path': path, 'reveal': reveal});

  Future<void> openUrl(String url) => _json('POST', '/api/open-url', {'url': url});

  // ------------------------------------------------------------- ask (SSE)

  /// Pose une question ; émet les événements du flux SSE au fur et à mesure.
  ///
  /// [mode] force le canal de réponse : `docs` (documents indexés seulement),
  /// `web` (recherche web) ou `file` (création de fichier). `null` ou `auto`
  /// laisse le backend choisir automatiquement.
  Stream<AskEvent> ask(
    String cid,
    String question, {
    String? reqId,
    String? mode,
    List<Map<String, String>> attachments = const [],
  }) async* {
    final req = http.Request('POST', _u('/api/conversations/$cid/ask'));
    req.headers['Content-Type'] = 'application/json';
    if (backendToken != null) req.headers['X-Jade-Token'] = backendToken!;
    req.body = jsonEncode({
      'question': question,
      'req_id': reqId ?? '',
      'mode': mode ?? 'auto',
      'attachments': attachments,
    });
    final resp = await _client.send(req);
    if (resp.statusCode >= 400) {
      final body = await resp.stream.bytesToString();
      String detail;
      try {
        detail = (jsonDecode(body) as Map<String, dynamic>)['detail'].toString();
      } catch (_) {
        detail = 'Erreur HTTP ${resp.statusCode}';
      }
      yield ErrorEvent(detail);
      return;
    }

    // découpage SSE : événements séparés par une ligne vide, champ "data: "
    var buffer = '';
    await for (final chunk in resp.stream.transform(utf8.decoder)) {
      buffer += chunk;
      while (true) {
        final idx = buffer.indexOf('\n\n');
        if (idx < 0) break;
        final raw = buffer.substring(0, idx).trim();
        buffer = buffer.substring(idx + 2);
        if (!raw.startsWith('data: ')) continue;
        final ev = _parseEvent(raw.substring(6));
        if (ev != null) yield ev;
        if (ev is DoneEvent) return;
      }
    }
  }

  AskEvent? _parseEvent(String data) {
    final Map<String, dynamic> j;
    try {
      j = jsonDecode(data) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
    switch (j['type']) {
      case 'token':
        return TokenEvent(j['delta'] ?? '');
      case 'sources':
        return SourcesEvent(((j['sources'] ?? []) as List)
            .map((s) => Source.fromJson(s as Map<String, dynamic>))
            .toList());
      case 'file':
        return FileEvent(j['path'] ?? '', j['name'] ?? '');
      case 'notice':
        return NoticeEvent(j['message'] ?? '');
      case 'progress':
        return ProgressEvent(j['message'] ?? '');
      case 'followups':
        return FollowupsEvent(((j['questions'] ?? []) as List)
            .map((q) => q.toString())
            .toList());
      case 'replies':
        return RepliesEvent(((j['options'] ?? []) as List)
            .map((o) => o.toString())
            .toList());
      case 'reset':
        return ResetEvent();
      case 'done':
        return DoneEvent(j['interrupted'] == true);
      case 'error':
        return ErrorEvent(j['message'] ?? 'Erreur inconnue');
    }
    return null;
  }

  /// Arrêt réel de la génération côté serveur (Ollama).
  Future<void> stop(String reqId) => _json('POST', '/api/stop', {'req_id': reqId});

  void close() => _client.close();
}

class ApiException implements Exception {
  final String message;
  final int status;
  ApiException(this.message, this.status);

  @override
  String toString() => message;
}

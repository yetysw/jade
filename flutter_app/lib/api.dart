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

const kBackendBase = 'http://127.0.0.1:8765';

class ApiClient {
  final http.Client _client = http.Client();

  Uri _u(String path) => Uri.parse('$kBackendBase$path');

  Future<dynamic> _json(String method, String path, [Object? body]) async {
    final req = http.Request(method, _u(path));
    req.headers['Content-Type'] = 'application/json';
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

  // -------------------------------------------------------- suggestions

  /// Suggestions d'accueil personnalisées (d'après l'historique de l'utilisateur).
  Future<List<Suggestion>> welcomeSuggestions() async {
    final j = await _json('GET', '/api/suggestions/welcome');
    return ((j['suggestions'] ?? []) as List)
        .map((s) => Suggestion.fromJson(s as Map<String, dynamic>))
        .toList();
  }

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
  Stream<AskEvent> ask(
    String cid,
    String question, {
    String? reqId,
    List<Map<String, String>> attachments = const [],
  }) async* {
    final req = http.Request('POST', _u('/api/conversations/$cid/ask'));
    req.headers['Content-Type'] = 'application/json';
    req.body = jsonEncode({
      'question': question,
      'req_id': reqId ?? '',
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

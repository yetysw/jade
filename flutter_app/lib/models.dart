/// Modèles de données — miroir des réponses JSON du backend local (ragagent).
library;

class AppStatus {
  final String username;
  final String appVersion;
  final bool? llmOk;
  final int chunksIndexed;
  final LicenseInfo license;

  AppStatus({
    required this.username,
    required this.appVersion,
    required this.llmOk,
    required this.chunksIndexed,
    required this.license,
  });

  factory AppStatus.fromJson(Map<String, dynamic> j) => AppStatus(
        username: j['username'] ?? 'Utilisateur',
        appVersion: j['app_version'] ?? '',
        llmOk: j['llm_ok'],
        chunksIndexed: j['chunks_indexed'] ?? 0,
        license: LicenseInfo.fromJson(
            (j['license'] as Map<String, dynamic>?) ?? const {}),
      );
}

/// État de licence (miroir du bloc `license` de /api/status).
class LicenseInfo {
  final String status; // off | active | grace | expired | suspended
  final String detail;
  const LicenseInfo({required this.status, required this.detail});

  /// Bandeau à montrer seulement hors « fonctionnement normal ».
  bool get showBanner => status == 'grace' || status == 'expired' ||
      status == 'suspended';

  /// Rouge (bloquant) vs information (grâce).
  bool get isBlocking => status == 'expired' || status == 'suspended';

  factory LicenseInfo.fromJson(Map<String, dynamic> j) => LicenseInfo(
        status: j['status'] ?? 'off',
        detail: j['detail'] ?? '',
      );
}

class Folder {
  final String id;
  final String name;
  Folder({required this.id, required this.name});

  factory Folder.fromJson(Map<String, dynamic> j) =>
      Folder(id: j['id'], name: j['name'] ?? '');
}

class Conversation {
  final String id;
  String title;
  final bool pinned;
  final String? folderId;
  final String updatedAt;

  Conversation({
    required this.id,
    required this.title,
    required this.pinned,
    required this.folderId,
    required this.updatedAt,
  });

  factory Conversation.fromJson(Map<String, dynamic> j) => Conversation(
        id: j['id'],
        title: j['title'] ?? 'Conversation',
        pinned: (j['pinned'] ?? 0) == 1 || j['pinned'] == true,
        folderId: j['folder_id'],
        updatedAt: j['updated_at'] ?? '',
      );
}

class Source {
  final int n;
  final String label;
  final String filename;
  final String path;
  final String url;
  final bool web;
  final String detail;
  final String text;

  Source({
    required this.n,
    required this.label,
    required this.filename,
    required this.path,
    required this.url,
    required this.web,
    required this.detail,
    required this.text,
  });

  factory Source.fromJson(Map<String, dynamic> j) => Source(
        n: j['n'] ?? 0,
        label: j['label'] ?? '',
        filename: j['filename'] ?? '',
        path: j['path'] ?? '',
        url: j['url'] ?? '',
        web: j['web'] == true,
        detail: j['detail'] ?? '',
        text: j['text'] ?? '',
      );
}

class MsgAttachment {
  final String name;
  final String path;
  final String kind; // 'doc' | 'image'
  MsgAttachment({required this.name, required this.path, required this.kind});

  factory MsgAttachment.fromJson(Map<String, dynamic> j) => MsgAttachment(
        name: j['name'] ?? 'fichier',
        path: j['path'] ?? '',
        kind: j['kind'] ?? 'doc',
      );
}

/// Dossier / racine d'indexation (réglages admin).
class IndexRoot {
  final String path;
  final bool online;
  IndexRoot({required this.path, required this.online});

  factory IndexRoot.fromJson(Map<String, dynamic> j) =>
      IndexRoot(path: j['path'] ?? '', online: j['online'] == true);
}

class IndexSettings {
  final List<IndexRoot> roots;
  final int chunksIndexed;
  final bool indexing;
  IndexSettings(
      {required this.roots,
      required this.chunksIndexed,
      required this.indexing});

  factory IndexSettings.fromJson(Map<String, dynamic> j) => IndexSettings(
        roots: ((j['roots'] ?? []) as List)
            .map((r) => IndexRoot.fromJson(r as Map<String, dynamic>))
            .toList(),
        chunksIndexed: j['chunks_indexed'] ?? 0,
        indexing: j['indexing'] == true,
      );
}

/// Suggestion d'accueil personnalisée (générée d'après l'historique).
class Suggestion {
  final String kind; // docs | web | file
  final String prompt;
  const Suggestion({required this.kind, required this.prompt});

  factory Suggestion.fromJson(Map<String, dynamic> j) =>
      Suggestion(kind: j['kind'] ?? 'docs', prompt: j['prompt'] ?? '');
}

class Message {
  final int? id;
  final String role; // 'user' | 'assistant'
  String content;
  List<Source>? sources;
  List<MsgAttachment> attachments;
  List<String> followups; // questions de suivi suggérées (réponse en direct)
  final String? createdAt;
  bool streaming;

  Message({
    this.id,
    required this.role,
    required this.content,
    this.sources,
    this.attachments = const [],
    this.followups = const [],
    this.createdAt,
    this.streaming = false,
  });

  factory Message.fromJson(Map<String, dynamic> j) => Message(
        id: j['id'],
        role: j['role'] ?? 'assistant',
        content: j['content'] ?? '',
        sources: j['sources'] == null
            ? null
            : (j['sources'] as List)
                .map((s) => Source.fromJson(s as Map<String, dynamic>))
                .toList(),
        attachments: j['attachments'] == null
            ? []
            : (j['attachments'] as List)
                .map((a) => MsgAttachment.fromJson(a as Map<String, dynamic>))
                .toList(),
        createdAt: j['created_at'],
      );
}

/// Progression du démarrage (miroir de /api/init) — téléchargement/chargement
/// des modèles de recherche au 1er lancement.
class InitStatus {
  final String phase; // starting|downloading|loading|engine|ready
  final String detail;
  final int downloadedMb;
  final int totalMb;
  final bool ready;

  const InitStatus({
    required this.phase,
    required this.detail,
    required this.downloadedMb,
    required this.totalMb,
    required this.ready,
  });

  /// Fraction connue seulement en téléchargement (sinon barre indéterminée).
  double? get fraction =>
      totalMb > 0 ? (downloadedMb / totalMb).clamp(0.0, 1.0) : null;

  factory InitStatus.fromJson(Map<String, dynamic> j) => InitStatus(
        phase: j['phase'] ?? 'starting',
        detail: j['detail'] ?? '',
        downloadedMb: j['downloaded_mb'] ?? 0,
        totalMb: j['total_mb'] ?? 0,
        ready: j['ready'] == true,
      );
}

/// État de mise à jour (miroir de /api/update).
class UpdateInfo {
  final String current;
  final String latest;
  final bool available;
  final String mode; // manual | scheduled | off
  final String notes;
  final int assetSize;

  const UpdateInfo({
    required this.current,
    required this.latest,
    required this.available,
    required this.mode,
    required this.notes,
    required this.assetSize,
  });

  /// Un bouton n'est proposé qu'en mode « manual » (poste client) ; en
  /// « scheduled » (RDS) la mise à jour est appliquée par une tâche planifiée.
  bool get showButton => available && mode == 'manual';

  factory UpdateInfo.fromJson(Map<String, dynamic> j) => UpdateInfo(
        current: j['current'] ?? '',
        latest: j['latest'] ?? j['current'] ?? '',
        available: j['available'] == true,
        mode: j['mode'] ?? 'manual',
        notes: j['notes'] ?? '',
        assetSize: j['asset_size'] ?? 0,
      );
}

/// Progression du téléchargement d'une mise à jour (miroir de /api/update/progress).
class DownloadProgress {
  final String state; // idle | downloading | ready | error
  final int done;
  final int total;
  final String error;

  const DownloadProgress({
    required this.state,
    required this.done,
    required this.total,
    required this.error,
  });

  double? get fraction => total > 0 ? (done / total).clamp(0.0, 1.0) : null;

  factory DownloadProgress.fromJson(Map<String, dynamic> j) => DownloadProgress(
        state: j['state'] ?? 'idle',
        done: j['done'] ?? 0,
        total: j['total'] ?? 0,
        error: j['error'] ?? '',
      );
}

/// Événements du flux SSE de /ask.
sealed class AskEvent {}

class TokenEvent extends AskEvent {
  final String delta;
  TokenEvent(this.delta);
}

class SourcesEvent extends AskEvent {
  final List<Source> sources;
  SourcesEvent(this.sources);
}

class FileEvent extends AskEvent {
  final String path;
  final String name;
  FileEvent(this.path, this.name);
}

class NoticeEvent extends AskEvent {
  final String message;
  NoticeEvent(this.message);
}

class ProgressEvent extends AskEvent {
  final String message;
  ProgressEvent(this.message);
}

class FollowupsEvent extends AskEvent {
  final List<String> questions;
  FollowupsEvent(this.questions);
}

class ResetEvent extends AskEvent {}

class DoneEvent extends AskEvent {
  final bool interrupted;
  DoneEvent(this.interrupted);
}

class ErrorEvent extends AskEvent {
  final String message;
  ErrorEvent(this.message);
}

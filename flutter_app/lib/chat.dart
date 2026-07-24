/// Zone de conversation : accueil, fil de messages (markdown + citations),
/// cartes des fichiers créés, composer avec envoi/arrêt, streaming SSE.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:markdown/markdown.dart' as md;

import 'api.dart';
import 'design.dart';
import 'home.dart';
import 'models.dart';
import 'tabler.dart';
import 'theme.dart';

/// Largeur de lecture confortable pour le fil et le composer.
const double _kColumn = 768;

class ChatView extends StatefulWidget {
  final ApiClient api;
  final HomeScreenState home;
  const ChatView({super.key, required this.api, required this.home});

  @override
  State<ChatView> createState() => ChatViewState();
}

class ChatViewState extends State<ChatView> {
  final List<Message> _messages = [];
  final _inputCtl = TextEditingController();
  final _scrollCtl = ScrollController();
  final _inputFocus = FocusNode();

  String _title = 'Nouvelle conversation';
  bool _streaming = false;
  String? _reqId;
  String? _progress;

  List<Suggestion>? _welcomeSug;

  bool get _welcome => _messages.isEmpty && !_streaming;

  @override
  void initState() {
    super.initState();
    _loadWelcome();
    // seconde tentative après le préchauffage des modèles (démarrage à froid :
    // la 1re requête peut tomber pendant le warmup et renvoyer les défauts)
    Future.delayed(const Duration(seconds: 9), () {
      if (mounted && _welcome) _loadWelcome();
    });
  }

  Future<void> _loadWelcome() async {
    try {
      final s = await widget.api.welcomeSuggestions();
      if (mounted) setState(() => _welcomeSug = s);
    } catch (_) {
      // suggestions personnalisées indisponibles : l'accueil affiche les défauts
    }
  }

  void reset() {
    setState(() {
      _messages.clear();
      _title = 'Nouvelle conversation';
      _progress = null;
    });
    _loadWelcome(); // rafraîchir d'après l'historique mis à jour
    _inputFocus.requestFocus();
  }

  Future<void> load(String cid) async {
    final (conv, msgs) = await widget.api.getConversation(cid);
    if (!mounted) return;
    setState(() {
      _title = conv.title;
      _messages
        ..clear()
        ..addAll(msgs);
      _progress = null;
    });
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtl.hasClients) {
        _scrollCtl.jumpTo(_scrollCtl.position.maxScrollExtent);
      }
    });
  }

  // ------------------------------------------------------------- envoi

  Future<void> _send() async {
    final q = _inputCtl.text.trim();
    if (q.isEmpty || _streaming) return;
    _inputCtl.clear();

    var cid = widget.home.currentConv;
    if (cid == null) {
      final conv = await widget.api.createConversation();
      cid = conv.id;
      widget.home.onConversationStarted(cid);
      _title = q.length > 60 ? q.substring(0, 60) : q;
    }

    final assistant = Message(role: 'assistant', content: '', streaming: true);
    setState(() {
      _messages.add(Message(role: 'user', content: q));
      _messages.add(assistant);
      _streaming = true;
      _progress = null;
    });
    _scrollToBottom();

    _reqId = _newReqId();
    List<Source>? sources;
    try {
      await for (final ev in widget.api.ask(cid, q, reqId: _reqId)) {
        if (!mounted) return;
        switch (ev) {
          case TokenEvent(:final delta):
            setState(() {
              assistant.content += delta;
              _progress = null;
            });
            _scrollToBottom();
          case SourcesEvent(sources: final s):
            sources = s.isEmpty ? null : s;
            assistant.sources = sources;
          case FileEvent(:final path, :final name):
            setState(() => assistant.attachments = [
                  ...assistant.attachments,
                  MsgAttachment(name: name, path: path, kind: 'doc'),
                ]);
          case FollowupsEvent(:final questions):
            setState(() => assistant.followups = questions);
          case ResetEvent():
            setState(() {
              assistant.content = '';
              assistant.sources = null;
              assistant.followups = const [];
              sources = null;
            });
          case NoticeEvent(:final message):
            setState(() => assistant.content = message);
          case ProgressEvent(:final message):
            setState(() => _progress = message);
          case ErrorEvent(:final message):
            setState(() {
              assistant.content = assistant.content.isEmpty
                  ? '**La réponse n’a pas pu être générée.** $message'
                  : assistant.content;
              _progress = null;
            });
          case DoneEvent():
            break;
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() => assistant.content = assistant.content.isEmpty
            ? '**La réponse n’a pas pu être générée.** $e'
            : assistant.content);
      }
    } finally {
      if (mounted) {
        setState(() {
          assistant.streaming = false;
          _streaming = false;
          _progress = null;
        });
        widget.home.refreshConversations();
        // le titre IA arrive en tâche de fond côté backend
        Future<void>.delayed(const Duration(seconds: 5), () async {
          if (!mounted || widget.home.currentConv == null) return;
          try {
            final (conv, _) =
                await widget.api.getConversation(widget.home.currentConv!);
            if (mounted) setState(() => _title = conv.title);
            widget.home.refreshConversations();
          } catch (_) {}
        });
      }
      _reqId = null;
    }
  }

  void _stop() {
    final id = _reqId;
    if (id != null) widget.api.stop(id);
  }

  static String _newReqId() {
    final r = math.Random();
    return List.generate(16, (_) => r.nextInt(16).toRadixString(16)).join();
  }

  // ------------------------------------------------------------- rendu

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Column(
      children: [
        if (!_welcome) _TitleBar(title: _title),
        Expanded(
          child: _welcome
              ? _WelcomeView(
                  suggestions: _welcomeSug,
                  onSuggestion: (s) {
                    _inputCtl.text = s;
                    _send();
                  },
                )
              : ListView.builder(
                  controller: _scrollCtl,
                  padding: const EdgeInsets.symmetric(vertical: JadeSpace.sm),
                  itemCount: _messages.length,
                  itemBuilder: (ctx, i) => Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: _kColumn),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(
                            horizontal: JadeSpace.xxl),
                        child: _MessageTile(
                          message: _messages[i],
                          home: widget.home,
                          api: widget.api,
                          onFollowup: (q) {
                            _inputCtl.text = q;
                            _send();
                          },
                        ),
                      ),
                    ),
                  ),
                ),
        ),
        if (_progress != null)
          Padding(
            padding: const EdgeInsets.only(bottom: JadeSpace.sm),
            child: _ProgressLine(text: _progress!),
          ),
        if (_streaming)
          Padding(
            padding: const EdgeInsets.only(bottom: JadeSpace.sm),
            child: OutlinedButton.icon(
              onPressed: _stop,
              style: OutlinedButton.styleFrom(
                foregroundColor: jade.body,
                side: BorderSide(color: jade.borderStrong),
                shape: RoundedRectangleBorder(
                    borderRadius: JadeRadius.all(JadeRadius.pill)),
                padding: const EdgeInsets.symmetric(
                    horizontal: JadeSpace.lg, vertical: JadeSpace.sm),
              ),
              icon: const Icon(TablerIcons.playerStop, size: 15),
              label: const Text('Arrêter'),
            ),
          ),
        Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: _kColumn),
            child: _Composer(
              controller: _inputCtl,
              focusNode: _inputFocus,
              enabled: !_streaming,
              onSend: _send,
            ),
          ),
        ),
      ],
    );
  }
}

// ============================================================== barre de titre

class _TitleBar extends StatelessWidget {
  final String title;
  const _TitleBar({required this.title});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Container(
      height: 52,
      alignment: Alignment.centerLeft,
      padding: const EdgeInsets.symmetric(horizontal: JadeSpace.xxl),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: jade.border)),
      ),
      child: Text(title,
          overflow: TextOverflow.ellipsis,
          style: JadeType.subtitle.copyWith(color: jade.body)),
    );
  }
}

// ================================================================ accueil

/// Style d'une suggestion selon son type (icône, couleur, intitulé de carte).
/// Couleurs prises dans le thème (jade) : en dur, le bleu/vert restaient figés
/// et devenaient illisibles en thème sombre.
(IconData, Color, String) _suggestionStyle(BuildContext context, String kind) {
  final jade = context.jade;
  // pas de token « ambre » dans le thème : accent adapté au clair/sombre
  final amber = context.isDark ? const Color(0xFFE0A94A) : const Color(0xFFC07A12);
  return switch (kind) {
    'web' => (TablerIcons.worldSearch, jade.primary, 'Recherche web'),
    'file' => (TablerIcons.filePlus, amber, 'Créer un fichier'),
    _ => (TablerIcons.fileText, jade.secondary, 'Chercher dans les documents'),
  };
}

const _defaultSuggestions = [
  Suggestion(
      kind: 'docs',
      prompt: 'Résume la procédure de sauvegarde décrite dans nos documents.'),
  Suggestion(
      kind: 'web',
      prompt:
          'Quelles sont les dernières recommandations de sécurité Microsoft 365 ?'),
  Suggestion(
      kind: 'file', prompt: 'Crée un tableau Excel de suivi des incidents.'),
];

class _WelcomeView extends StatelessWidget {
  final void Function(String) onSuggestion;
  final List<Suggestion>? suggestions;
  const _WelcomeView({required this.onSuggestion, this.suggestions});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    final items = (suggestions == null || suggestions!.isEmpty)
        ? _defaultSuggestions
        : suggestions!;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(JadeSpace.xxl),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 640),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // gemme sur halo — moment signature
              SizedBox(
                height: 108,
                width: 160,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    Container(
                      decoration: BoxDecoration(
                        gradient: RadialGradient(
                          colors: [
                            const Color(0xFF2E6FD6).withValues(alpha: 0.20),
                            const Color(0xFF2E6FD6).withValues(alpha: 0.0),
                          ],
                        ),
                      ),
                    ),
                    const JadeMark(size: 62),
                  ],
                ),
              ),
              const SizedBox(height: JadeSpace.xl),
              Text('Comment puis-je vous aider ?',
                  textAlign: TextAlign.center,
                  style: JadeType.display.copyWith(color: jade.text)),
              const SizedBox(height: JadeSpace.md),
              Text(
                'Interrogez vos documents internes, lancez une recherche web ou '
                'demandez la création d’un fichier — le tout sans qu’aucun '
                'document ne quitte ce poste.',
                textAlign: TextAlign.center,
                style: JadeType.body.copyWith(color: jade.muted),
              ),
              const SizedBox(height: JadeSpace.xxxl),
              Wrap(
                spacing: JadeSpace.md,
                runSpacing: JadeSpace.md,
                alignment: WrapAlignment.center,
                children: [
                  for (final s in items)
                    Builder(builder: (context) {
                      final (icon, tint, title) = _suggestionStyle(context, s.kind);
                      return _SuggestionCard(
                        icon: icon,
                        title: title,
                        prompt: s.prompt,
                        tint: tint,
                        onTap: () => onSuggestion(s.prompt),
                      );
                    }),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SuggestionCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String prompt;
  final Color tint;
  final VoidCallback onTap;
  const _SuggestionCard({
    required this.icon,
    required this.title,
    required this.prompt,
    required this.tint,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Hoverable(
      builder: (context, hover) => GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: context.motion(const Duration(milliseconds: 150)),
          curve: Curves.easeOutCubic,
          width: 196,
          padding: const EdgeInsets.all(JadeSpace.lg),
          decoration: BoxDecoration(
            color: jade.card,
            borderRadius: JadeRadius.all(JadeRadius.lg),
            border: Border.all(color: hover ? jade.borderStrong : jade.border),
            boxShadow: hover ? JadeElevation.soft(context) : null,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 34,
                height: 34,
                decoration: BoxDecoration(
                  color: tint.withValues(alpha: context.isDark ? 0.18 : 0.12),
                  borderRadius: JadeRadius.all(JadeRadius.sm),
                ),
                child: Icon(icon, size: 18, color: tint),
              ),
              const SizedBox(height: JadeSpace.md),
              Text(title,
                  style: JadeType.subtitle.copyWith(color: jade.text)),
              const SizedBox(height: JadeSpace.xs + 2),
              Text(prompt,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: JadeType.caption
                      .copyWith(color: jade.muted, height: 1.5)),
            ],
          ),
        ),
      ),
    );
  }
}

// ============================================================== ligne de progrès

class _ProgressLine extends StatelessWidget {
  final String text;
  const _ProgressLine({required this.text});
  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: 12,
          height: 12,
          child: CircularProgressIndicator(strokeWidth: 2, color: jade.secondary),
        ),
        const SizedBox(width: JadeSpace.sm),
        Text(text, style: JadeType.caption.copyWith(color: jade.muted)),
      ],
    );
  }
}

// ================================================================ message

class _MessageTile extends StatelessWidget {
  final Message message;
  final HomeScreenState home;
  final ApiClient api;
  final void Function(String) onFollowup;
  const _MessageTile({
    required this.message,
    required this.home,
    required this.api,
    required this.onFollowup,
  });

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    if (message.role == 'user') {
      // suffixe technique « [Pièces jointes : …] » masqué à l'affichage
      final text = message.content
          .replaceAll(RegExp(r'\n\[Pièces jointes :[^\]]*\]'), '');
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: const EdgeInsets.symmetric(vertical: JadeSpace.sm),
          padding: const EdgeInsets.symmetric(
              horizontal: JadeSpace.lg, vertical: JadeSpace.md),
          constraints: const BoxConstraints(maxWidth: 500),
          decoration: BoxDecoration(
            color: jade.tile,
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(JadeRadius.lg),
              topRight: Radius.circular(JadeRadius.lg),
              bottomLeft: Radius.circular(JadeRadius.lg),
              bottomRight: Radius.circular(JadeRadius.xs),
            ),
          ),
          child: SelectableText(text,
              style: JadeType.body.copyWith(color: jade.text)),
        ),
      );
    }

    // message assistant
    return Container(
      margin: const EdgeInsets.symmetric(vertical: JadeSpace.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              // le logo tourne pendant toute la génération (indicateur d'activité)
              JadeMark(size: 22, animate: message.streaming),
              const SizedBox(width: JadeSpace.sm),
              Text(message.streaming ? 'Jade réfléchit…' : 'Jade',
                  style: JadeType.caption.copyWith(
                      color: jade.muted, fontWeight: FontWeight.w700)),
            ],
          ),
          const SizedBox(height: JadeSpace.sm),
          if (message.content.isNotEmpty)
            _AssistantMarkdown(
              text: message.content,
              sources: message.sources,
              onCite: (n) => home.showSources(message.sources ?? const [], n),
              onLink: (url) => api.openUrl(url),
            ),
          // fichiers créés par Jade — cartes cliquables
          ...message.attachments.map((a) => _FileCard(att: a, api: api)),
          if (!message.streaming && (message.sources?.isNotEmpty ?? false))
            Padding(
              padding: const EdgeInsets.only(top: JadeSpace.sm),
              child: _SourcesChip(
                count: message.sources!.length,
                onTap: () => home.showSources(message.sources!, null),
              ),
            ),
          if (!message.streaming && message.followups.isNotEmpty)
            _Followups(questions: message.followups, onTap: onFollowup),
        ],
      ),
    );
  }
}

/// Questions de suivi suggérées, sous une réponse — chaque question relance
/// l'assistant d'un clic.
class _Followups extends StatelessWidget {
  final List<String> questions;
  final void Function(String) onTap;
  const _Followups({required this.questions, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Padding(
      padding: const EdgeInsets.only(top: JadeSpace.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(TablerIcons.messages, size: 13, color: jade.faint),
              const SizedBox(width: JadeSpace.sm),
              Text('SUGGESTIONS DE SUIVI',
                  style: JadeType.eyebrow.copyWith(color: jade.faint)),
            ],
          ),
          const SizedBox(height: JadeSpace.sm),
          ...questions.map((q) => Padding(
                padding: const EdgeInsets.only(bottom: JadeSpace.sm),
                child: Hoverable(
                  builder: (context, hover) => GestureDetector(
                    onTap: () => onTap(q),
                    child: AnimatedContainer(
                      duration:
                          context.motion(const Duration(milliseconds: 130)),
                      padding: const EdgeInsets.symmetric(
                          horizontal: JadeSpace.md, vertical: JadeSpace.sm + 2),
                      constraints: const BoxConstraints(maxWidth: 560),
                      decoration: BoxDecoration(
                        color: hover ? jade.tile : Colors.transparent,
                        borderRadius: JadeRadius.all(JadeRadius.md),
                        border: Border.all(
                            color: hover ? jade.borderStrong : jade.border),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Flexible(
                            child: Text(q,
                                style: JadeType.label.copyWith(
                                    color: hover ? jade.text : jade.body)),
                          ),
                          const SizedBox(width: JadeSpace.sm),
                          Icon(TablerIcons.arrowRight,
                              size: 14, color: jade.secondary),
                        ],
                      ),
                    ),
                  ),
                ),
              )),
        ],
      ),
    );
  }
}

class _SourcesChip extends StatelessWidget {
  final int count;
  final VoidCallback onTap;
  const _SourcesChip({required this.count, required this.onTap});
  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Hoverable(
      builder: (context, hover) => GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(
              horizontal: JadeSpace.md, vertical: JadeSpace.sm),
          decoration: BoxDecoration(
            color: hover ? jade.tile : Colors.transparent,
            borderRadius: JadeRadius.all(JadeRadius.pill),
            border: Border.all(color: jade.border),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(TablerIcons.fileText, size: 14, color: jade.secondary),
              const SizedBox(width: JadeSpace.sm),
              Text('$count source${count > 1 ? 's' : ''}',
                  style: JadeType.caption.copyWith(
                      color: jade.secondary, fontWeight: FontWeight.w600)),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------- markdown + citations

class _AssistantMarkdown extends StatelessWidget {
  final String text;
  final List<Source>? sources;
  final void Function(int) onCite;
  final void Function(String) onLink;
  const _AssistantMarkdown({
    required this.text,
    required this.sources,
    required this.onCite,
    required this.onLink,
  });

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return MarkdownBody(
      data: text,
      selectable: true,
      extensionSet: md.ExtensionSet.gitHubFlavored,
      inlineSyntaxes: [_CiteSyntax()],
      builders: {'cite': _CiteBuilder(jade, onCite)},
      onTapLink: (t, href, title) {
        if (href != null && href.startsWith('http')) onLink(href);
      },
      styleSheet: MarkdownStyleSheet(
        p: JadeType.body.copyWith(color: jade.body, height: 1.65),
        h1: JadeType.headline.copyWith(color: jade.text),
        h2: JadeType.title.copyWith(color: jade.text),
        h3: JadeType.subtitle.copyWith(color: jade.text),
        h1Padding: const EdgeInsets.only(top: JadeSpace.md, bottom: JadeSpace.xs),
        h2Padding: const EdgeInsets.only(top: JadeSpace.md, bottom: JadeSpace.xs),
        h3Padding: const EdgeInsets.only(top: JadeSpace.sm, bottom: JadeSpace.xs),
        listBullet: JadeType.body.copyWith(color: jade.body),
        strong: const TextStyle(fontWeight: FontWeight.w700),
        code: TextStyle(
            fontSize: 12.5,
            fontFamily: 'Consolas',
            backgroundColor: jade.tile,
            color: jade.text),
        codeblockPadding: const EdgeInsets.all(JadeSpace.md),
        codeblockDecoration: BoxDecoration(
          color: jade.tile,
          borderRadius: JadeRadius.all(JadeRadius.md),
          border: Border.all(color: jade.border),
        ),
        blockquotePadding: const EdgeInsets.fromLTRB(
            JadeSpace.md, JadeSpace.sm, JadeSpace.md, JadeSpace.sm),
        blockquoteDecoration: BoxDecoration(
          color: jade.tile,
          borderRadius: JadeRadius.all(JadeRadius.sm),
          border: Border(left: BorderSide(color: jade.secondary, width: 3)),
        ),
        tableBorder: TableBorder.all(color: jade.border, width: 0.8),
        tableHead: JadeType.label.copyWith(
            color: jade.text, fontWeight: FontWeight.w700),
        tableBody: JadeType.label.copyWith(color: jade.body),
        tableCellsPadding: const EdgeInsets.symmetric(
            horizontal: JadeSpace.md, vertical: JadeSpace.sm),
        a: TextStyle(color: jade.primary, fontWeight: FontWeight.w600),
      ),
    );
  }
}

/// [Source N] -> nœud markdown `cite` (rendu en exposant bleu cliquable).
class _CiteSyntax extends md.InlineSyntax {
  _CiteSyntax() : super(r'\s*\[Source (\d+)\]');

  @override
  bool onMatch(md.InlineParser parser, Match match) {
    parser.addNode(md.Element.text('cite', match[1]!));
    return true;
  }
}

class _CiteBuilder extends MarkdownElementBuilder {
  final JadeColors jade;
  final void Function(int) onTap;
  _CiteBuilder(this.jade, this.onTap);

  @override
  Widget? visitElementAfter(md.Element element, TextStyle? preferredStyle) {
    final n = int.tryParse(element.textContent) ?? 0;
    return GestureDetector(
      onTap: () => onTap(n),
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        child: Transform.translate(
          offset: const Offset(2, -5),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
            decoration: BoxDecoration(
              color: jade.primaryContainer,
              borderRadius: BorderRadius.circular(JadeRadius.xs),
            ),
            child: Text('$n',
                style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    color: jade.onPrimaryContainer)),
          ),
        ),
      ),
    );
  }
}

// ------------------------------------------------------- carte de fichier

class _FileCard extends StatelessWidget {
  final MsgAttachment att;
  final ApiClient api;
  const _FileCard({required this.att, required this.api});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    final ext = att.name.contains('.') ? att.name.split('.').last : 'doc';
    return Hoverable(
      builder: (context, hover) => GestureDetector(
        onTap: () => api.openFile(att.path),
        child: AnimatedContainer(
          duration: context.motion(const Duration(milliseconds: 150)),
          margin: const EdgeInsets.only(top: JadeSpace.md),
          padding: const EdgeInsets.all(JadeSpace.md),
          constraints: const BoxConstraints(maxWidth: 400),
          decoration: BoxDecoration(
            color: jade.card,
            borderRadius: JadeRadius.all(JadeRadius.lg),
            border: Border.all(color: hover ? jade.borderStrong : jade.border),
            boxShadow: hover ? JadeElevation.soft(context) : null,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: fileTypeColor(att.name),
                  borderRadius: JadeRadius.all(JadeRadius.md),
                ),
                alignment: Alignment.center,
                child: Text(
                  ext.toUpperCase().substring(0, ext.length.clamp(0, 4)),
                  style: const TextStyle(
                      fontSize: 9,
                      fontWeight: FontWeight.w800,
                      color: Colors.white,
                      letterSpacing: 0.4),
                ),
              ),
              const SizedBox(width: JadeSpace.md),
              Flexible(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(att.name,
                        overflow: TextOverflow.ellipsis,
                        style: JadeType.label.copyWith(
                            color: jade.text, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 1),
                    Text('${fileTypeLabel(att.name)} · créé par Jade',
                        style: JadeType.caption.copyWith(color: jade.muted)),
                  ],
                ),
              ),
              const SizedBox(width: JadeSpace.md),
              AnimatedContainer(
                duration: context.motion(const Duration(milliseconds: 150)),
                width: 34,
                height: 34,
                decoration: BoxDecoration(
                  color: hover ? jade.primary : jade.tile,
                  shape: BoxShape.circle,
                ),
                child: Icon(TablerIcons.externalLink,
                    size: 15, color: hover ? Colors.white : jade.primary),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ------------------------------------------------------------- composer

class _Composer extends StatelessWidget {
  final TextEditingController controller;
  final FocusNode focusNode;
  final bool enabled;
  final VoidCallback onSend;
  const _Composer({
    required this.controller,
    required this.focusNode,
    required this.enabled,
    required this.onSend,
  });

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          JadeSpace.xxl, JadeSpace.xs, JadeSpace.xxl, JadeSpace.md),
      child: Column(
        children: [
          FocusRing(
            radius: JadeRadius.xl,
            child: Container(
              padding: const EdgeInsets.fromLTRB(
                  JadeSpace.xl, JadeSpace.sm, JadeSpace.sm, JadeSpace.sm),
              decoration: BoxDecoration(
                color: jade.card,
                borderRadius: JadeRadius.all(JadeRadius.xl),
                border: Border.all(color: jade.border),
                boxShadow: JadeElevation.soft(context),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: Focus(
                      onKeyEvent: (node, event) {
                        if (event is KeyDownEvent &&
                            event.logicalKey == LogicalKeyboardKey.enter &&
                            !HardwareKeyboard.instance.isShiftPressed) {
                          if (enabled) onSend();
                          return KeyEventResult.handled;
                        }
                        return KeyEventResult.ignored;
                      },
                      child: TextField(
                        controller: controller,
                        focusNode: focusNode,
                        minLines: 1,
                        maxLines: 6,
                        maxLength: 6000,
                        style: JadeType.body.copyWith(color: jade.text),
                        decoration: InputDecoration(
                          hintText: 'Posez votre question…',
                          hintStyle:
                              JadeType.body.copyWith(color: jade.faint),
                          border: InputBorder.none,
                          isCollapsed: true,
                          contentPadding: const EdgeInsets.symmetric(
                              vertical: JadeSpace.sm + 2),
                          counterText: '',
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: JadeSpace.sm),
                  _SendButton(enabled: enabled, onSend: onSend),
                ],
              ),
            ),
          ),
          const SizedBox(height: JadeSpace.sm),
          Text('Entrée pour envoyer · Maj + Entrée pour un saut de ligne',
              style: JadeType.caption.copyWith(color: jade.faint)),
        ],
      ),
    );
  }
}

class _SendButton extends StatelessWidget {
  final bool enabled;
  final VoidCallback onSend;
  const _SendButton({required this.enabled, required this.onSend});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Hoverable(
      clickable: enabled,
      builder: (context, hover) => GestureDetector(
        onTap: enabled ? onSend : null,
        child: AnimatedContainer(
          duration: context.motion(const Duration(milliseconds: 140)),
          width: 38,
          height: 38,
          decoration: BoxDecoration(
            color: enabled
                ? (hover ? jade.primaryHover : jade.primary)
                : jade.tile,
            shape: BoxShape.circle,
          ),
          child: Icon(TablerIcons.arrowUp,
              size: 18, color: enabled ? Colors.white : jade.faint),
        ),
      ),
    );
  }
}

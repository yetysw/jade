/// Retour utilisateur : petit dialogue qui envoie un message à Jade
/// (feedback@example.com) via le backend (API Resend). L'utilisateur écrit, envoie,
/// c'est parti — aucun client mail requis.
library;

import 'package:flutter/material.dart';

import 'api.dart';
import 'design.dart';
import 'tabler.dart';
import 'theme.dart';

Future<void> showFeedbackDialog(BuildContext context, ApiClient api) {
  return showDialog(
    context: context,
    builder: (_) => _FeedbackDialog(api: api),
  );
}

class _FeedbackDialog extends StatefulWidget {
  final ApiClient api;
  const _FeedbackDialog({required this.api});

  @override
  State<_FeedbackDialog> createState() => _FeedbackDialogState();
}

class _FeedbackDialogState extends State<_FeedbackDialog> {
  final _ctl = TextEditingController();
  bool _busy = false;
  bool _sent = false;
  String? _error;

  @override
  void dispose() {
    _ctl.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final content = _ctl.text.trim();
    if (content.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.api.sendFeedback(content);
      if (!mounted) return;
      setState(() => _sent = true);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) {
        setState(() =>
            _error = 'Envoi impossible pour le moment — réessayez plus tard.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return AlertDialog(
      shape:
          RoundedRectangleBorder(borderRadius: JadeRadius.all(JadeRadius.lg)),
      title: Row(
        children: [
          Icon(TablerIcons.send, size: 19, color: jade.primary),
          const SizedBox(width: JadeSpace.md),
          const Text('Votre avis compte'),
        ],
      ),
      content: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420),
        child: _sent ? _thanks(jade) : _form(jade),
      ),
      actions: _sent
          ? [
              FilledButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Fermer'),
              ),
            ]
          : [
              TextButton(
                onPressed: _busy ? null : () => Navigator.pop(context),
                child: const Text('Annuler'),
              ),
              FilledButton.icon(
                onPressed: _busy ? null : _send,
                icon: _busy
                    ? const SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(TablerIcons.send, size: 15),
                label: const Text('Envoyer'),
              ),
            ],
    );
  }

  Widget _form(JadeColors jade) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Un problème, une idée, une remarque ? Votre message part '
          'directement à l’équipe Jade.',
          style: JadeType.label.copyWith(color: jade.muted, height: 1.5),
        ),
        const SizedBox(height: JadeSpace.md),
        TextField(
          controller: _ctl,
          autofocus: true,
          maxLines: 6,
          minLines: 4,
          maxLength: 2000,
          style: JadeType.label.copyWith(color: jade.text, height: 1.5),
          decoration: InputDecoration(
            hintText: 'Décrivez votre remarque…',
            hintStyle: JadeType.label.copyWith(color: jade.faint),
            filled: true,
            fillColor: jade.tile,
            contentPadding: const EdgeInsets.all(JadeSpace.md),
            enabledBorder: OutlineInputBorder(
              borderRadius: JadeRadius.all(JadeRadius.sm),
              borderSide: BorderSide.none,
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: JadeRadius.all(JadeRadius.sm),
              borderSide: BorderSide(color: jade.primary, width: 1.5),
            ),
          ),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: JadeSpace.sm),
            child: Text(_error!,
                style: JadeType.caption.copyWith(color: jade.danger)),
          ),
      ],
    );
  }

  Widget _thanks(JadeColors jade) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(TablerIcons.circleCheck, size: 20, color: jade.secondary),
        const SizedBox(width: JadeSpace.md),
        Expanded(
          child: Text(
            'Merci ! Votre retour a bien été envoyé à l’équipe Jade.',
            style: JadeType.label.copyWith(color: jade.body, height: 1.5),
          ),
        ),
      ],
    );
  }
}

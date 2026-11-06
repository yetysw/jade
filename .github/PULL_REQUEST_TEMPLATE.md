<!-- One topic per PR. Title in Conventional Commits form: feat(scope): ..., fix(scope): ..., docs: ... -->

## What

<!-- One or two sentences: what changes and why. Link the issue if there is one: Closes #123 -->

## How

<!-- Anything a reviewer needs to know: design choices, alternatives rejected, follow-ups left out. -->

## Screenshots

<!-- Required for UI changes: before and after, dark and light. Delete this section otherwise. -->

## Checklist

- [ ] `python -m pytest` passes (backend changes)
- [ ] `flutter analyze` passes in `flutter_app/` (interface changes)
- [ ] New behaviour and bug fixes come with tests (a bug fix with a regression test that fails without the fix)
- [ ] New or changed settings are in `.env.example` and in `docs/configuration.md`
- [ ] Nothing leaves the PC that the Security page does not list
- [ ] No secret, token, real hostname or customer data in the diff or the screenshots

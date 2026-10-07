## Summary

<!-- What does this pull request change, and why? -->

## Checklist

- [ ] Every commit is signed off (`git commit -s`, Developer Certificate of Origin).
- [ ] Commit messages and the title of this pull request follow Conventional Commits.
- [ ] Tests cover the change; `uv run pytest` passes.
- [ ] `uv run pre-commit run --all-files` passes.
- [ ] The change is described in the `[Unreleased]` section of `CHANGELOG.md`.
- [ ] If the generated output changes for identical inputs and data: `ENGINE_REVISION` is
      incremented, the change is noted in `CHANGELOG.md`, and goldens are regenerated
      (`uv run pytest --update-goldens`).

### Universe changes

- [ ] `uv run fakeverse validate --strict universes/` and `uv run fakeverse check-coherence` pass.
- [ ] Only names and short labels; no quotes, descriptions or images; no bulk copy from a wiki.
- [ ] Everything stays within the `universe.sources.scope`; invented elements are marked
      `canon: false`.
- [ ] Translations follow the reference translation of each locale.

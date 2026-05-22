<!--
  Use this template when promoting nightly into main.

  Open with:
    https://github.com/OneCielAI/claude-any/compare/main...nightly?template=release.md

  CI on this PR will run from the nightly head; the release publish
  workflow only fires once this PR is merged to main.
-->

## Release candidate

Target stable version: `vX.Y.Z`

### Pre-merge checklist

- [ ] `package.json` `version` bumped to the new stable `X.Y.Z`.
- [ ] `claude_any.py` `VERSION` bumped to the same `X.Y.Z`.
- [ ] `npm test` passes locally on a clean checkout.
- [ ] `python -m ruff check .` passes locally.
- [ ] No publish-blocking changes (deprecated APIs left in place, breaking
      env/config defaults documented).
- [ ] Manual smoke test on at least one non-Anthropic provider
      (Ollama Cloud, NVIDIA hosted, or local Ollama).

### Highlights since the last stable

<!--
  Summarize what shipped on nightly since the previous stable cut.
  These bullet points become the GitHub Release notes (manual paste
  after merge — there is no auto-generated changelog file).
-->

-

### Risk and rollback

<!--
  Note any user-visible behavior changes and how to revert (npm dist-tag
  `latest` can be moved back: `npm dist-tag add @oneciel-ai/claude-any@PREV latest`).
-->

-

### After merge

- [ ] Verify `Publish to npm` workflow run completed successfully on main.
- [ ] Verify `npm view @oneciel-ai/claude-any version` reports the new `X.Y.Z`.
- [ ] Create the matching `vX.Y.Z` GitHub Release with the highlights above
      as the body.
- [ ] Fast-forward `nightly` to `main` so subsequent nightlies build on
      top of the just-released code:
      `git checkout nightly && git merge --ff-only main && git push origin nightly`.

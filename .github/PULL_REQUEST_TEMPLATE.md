## What

<!-- 1-line description of the change -->

## Why

<!-- What problem does this solve? What use case does it unlock? -->

## How

<!-- Brief technical approach. Link to docs/ or wiki sections if relevant. -->

## Phase

- [ ] Phase 0 (scaffolding)
- [ ] Phase 1 (mice-rca centerpiece)
- [ ] Phase 2 (full set)
- [ ] Cross-phase (tooling, docs, CI)

## Testing

<!-- How did you verify this works? -->

- [ ] `make test` passes
- [ ] `make smoke` passes (or skipped with reason: ___)
- [ ] Manual verification: <describe what you ran>

## Checklist

- [ ] `CHANGELOG.md` updated under `## [Unreleased]` for user-facing changes
- [ ] `docs/*.md` updated if user-facing behavior changed (wiki auto-syncs from there)
- [ ] No new shellcheck/yamllint warnings
- [ ] Snapshot regenerated with `make snapshot` if `templates/` changed
- [ ] No raw secrets committed
- [ ] Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)

## Closes

<!-- Closes #N -->

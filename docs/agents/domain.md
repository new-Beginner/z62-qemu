# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root.
- **`docs/adr/`**: read ADRs that touch the area you're about to work in.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## Layout: single-context

This repo is **single-context**: one `GLOSSARY.md` at the repo root, and one `docs/adr/` directory for decisions that apply to the whole repo. There is no `GLOSSARY-MAP.md` and no per-subproject glossary; this repo's `qemu/`, `tools/`, `tests/`, `analysis/` and `docs/` trees all share the same vocabulary.

```
/
├── GLOSSARY.md
├── docs/adr/
│   ├── 0001-example-decision.md
│   └── 0002-another-decision.md
├── qemu/
├── tools/
└── tests/
```

`GLOSSARY.md` and `docs/adr/` are created lazily, the first time a term or a decision is actually resolved. Neither exists yet; that is expected, not a gap.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `GLOSSARY.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders), but worth reopening because…_

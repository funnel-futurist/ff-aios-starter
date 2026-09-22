# P22 - Starter / client installation and upgrades

Package: `P22-001` (swarm-001). Writer lease: `funnel-futurist/ff-aios-starter`, branch `exec/p22-install-20260922`.

## How to resume (read this first if you are a fresh instance)

1. The repo was not on disk when P22 started. Clone it:
   `cd /Users/phoenixbohannon/Documents/GitHub && gh repo clone funnel-futurist/ff-aios-starter`
2. `git fetch --all && git checkout exec/p22-install-20260922 && git pull --ff-only`
3. Read `STATE.md` in this folder: it lists what is done, what is next, and every open gate.
4. The last receipt is the newest `P22-001-*.md` in this folder.
5. Prompt of record: `CHAT_P22_STARTER.md` plus the model-routing override `ROUTER_ADDENDUM.md`, both in
   the swarm-001 dispatch folder of the private delegation repo (section 3 of the prompt has the URLs).

> **This repository is public and is a GitHub template.** Everything under `evidence/` is world-readable
> and is copied into every repo made with "Use this template". Evidence here names no client, no
> private org member, no secret and no URL into a private repository. Private repos are named, never
> linked.

## Outcome being built

A proven installation path:
**approved pinned package -> role-scoped `/start` -> config and credential references -> verification
-> upgrade and rollback that preserve state.**

Internal validation first. Client portability is claimed only after internal validation passes. No
public skill ports and no external publication in this package.

## Contract consumed, not owned

P01 (AIOS vNext) owns packaging decisions. This package consumes **founder ruling D3**: Starter and
organization deployments consume approved, versioned releases, never mutable `main`. Source of that
ruling: the private ai-os repo, candidate branch `exec/a-foundation-loop-20260921-a001` (not yet on its
`main`), files `00_Foundations/ref_vnext_release_and_upgrade_contract.md` and
`00_Foundations/_manifests/_candidates/RELEASE_CONTRACTS.md`.

## Writable surfaces

- the whole `funnel-futurist/ff-aios-starter` repository, on this branch
- `.github/CODEOWNERS`
- `evidence/dispatch/p22-starter/**`

## Forbidden

Every other repository. Public skill ports. External publication. Production deployment. Client
account provisioning. Secrets anywhere. Merging PR #11 to get around the broken code-owner gate.

## Acceptance criteria (from the prompt, section 12) and negative tests (section 13)

Tracked with status in `STATE.md`.

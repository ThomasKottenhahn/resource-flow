# Issue Tracker

Local Markdown files under `.scratch/`. Full conventions: [agents/issue-tracker.md](agents/issue-tracker.md). Triage labels: [agents/triage-labels.md](agents/triage-labels.md).

## 1. Creating, viewing, listing and closing tickets

- **Spec:** `.scratch/<feature-slug>/spec.md`
- **Create:** add `.scratch/<feature-slug>/issues/<NN>-<ticket-slug>.md`, numbered from `01`, one file per ticket, with a `Status:` line near the top (e.g. `Status: ready-for-agent`).
- **View:** read the file.
- **List:** list `.scratch/<feature-slug>/issues/` (or `.scratch/*/issues/` for all features).
- **Close:** set `Status: resolved`. Comments go at the bottom under `## Comments`.

## 2. Blocking dependencies

Add a `Blocked by: NN, NN` line near the top of the ticket. A ticket is unblocked once every ticket it lists is `resolved`.

## 3. Test plans

Each ticket's test plan sits beside the ticket: `.scratch/<feature-slug>/issues/<NN>-<ticket-slug>-test-plan.md`.

## 4. Branches and pull requests

- Use one branch per feature: `feat/<feature-slug>`, cut from `dev`.
- Commit every ticket of that feature to the same branch.
- Open a single PR into `dev` once all of the feature's tickets are resolved.
- `dev` is merged into `main` only for releases, and only by a human, never an agent.

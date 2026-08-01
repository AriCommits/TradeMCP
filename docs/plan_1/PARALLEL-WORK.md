# Plan 1 Parallel Work Guide

## Coordination Rules

- A wave is a dependency boundary, not a calendar sprint. Do not begin a later wave because its code looks independent; the scientific gate and frozen artifacts are part of the dependency.
- Concurrent agents use separate branches and worktrees. They do not share a mutable checkout, virtual environment state, data partition, MLflow run directory, or output run ID.
- The current repository has unrelated uncommitted options/MCP work. Never stage, rewrite, or clean files outside the assigned list.
- Generated artifacts use run-scoped paths and immutable IDs. Source branches do not commit raw data, caches, bulk predictions, or weights.
- Every merge preserves common UTC cutoffs, the 12-hour minimum purge, fold-local transformations, and completed-candle anchors.
- Model stages advance by recorded out-of-sample gates. Parallel coding never bypasses a baseline, promotion, lockbox, or weekend freeze gate.

## File and Dependency Matrix

Legend: `D` = row task has a direct dependency on column task; `F` = both tasks modify the same versioned file; `.` = same task; `-` = no direct dependency or shared versioned file. Transitive dependencies are enforced by waves even when not repeated as `D`.

```text
+------+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+
| Task | P0 | C0 | D0 | L0 | Q0 | S0 | F0 | E0 | B0 | N0 | H0 | O0 | U0 | X0 | W0 | R0 |
+------+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+
| P0   | .  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | F  |
| C0   | -  | .  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  |
| D0   | D  | D  | .  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  |
| L0   | -  | D  | -  | .  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  |
| Q0   | -  | -  | D  | -  | .  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  |
| S0   | D  | D  | D  | D  | -  | .  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  |
| F0   | -  | -  | -  | -  | D  | D  | .  | -  | -  | -  | -  | -  | -  | -  | -  | -  |
| E0   | -  | -  | -  | D  | -  | D  | -  | .  | -  | -  | -  | -  | -  | -  | -  | -  |
| B0   | -  | -  | -  | -  | -  | -  | D  | D  | .  | -  | -  | -  | -  | -  | -  | -  |
| N0   | -  | -  | -  | -  | -  | -  | D  | D  | D  | .  | -  | -  | -  | -  | -  | -  |
| H0   | -  | -  | -  | -  | -  | -  | -  | D  | -  | D  | .  | -  | -  | -  | -  | -  |
| O0   | -  | -  | -  | -  | -  | -  | -  | -  | D  | D  | -  | .  | -  | -  | -  | -  |
| U0   | -  | -  | D  | -  | D  | -  | -  | -  | -  | -  | D  | D  | .  | -  | -  | -  |
| X0   | D  | -  | -  | -  | -  | -  | -  | -  | -  | -  | D  | D  | -  | .  | -  | -  |
| W0   | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | D  | D  | D  | D  | .  | -  |
| R0   | F  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | -  | D  | .  |
+------+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+
```

## Wave Execution Diagram

```text
Wave 1   +----------------------+     +----------------------+
         | Agent A: P0          |  || | Agent B: C0          |
         | Decisions / skeleton |     | Contracts / time     |
         +----------------------+     +----------------------+
                         |
                         v
Wave 2   +----------------------+     +----------------------+
         | Agent A: D0          |  || | Agent B: L0          |
         | Collection / universe|     | Labels / event rates |
         +----------------------+     +----------------------+
                         |
                         v
Wave 3   +----------------------+     +----------------------+
         | Agent A: Q0          |  || | Agent B: S0          |
         | Quality / 30m bars   |     | Splits / datasets    |
         +----------------------+     +----------------------+
                         |
                         v
Wave 4   +----------------------+     +----------------------+
         | Agent A: F0          |  || | Agent B: E0          |
         | Causal features      |     | Metrics / calibration|
         +----------------------+     +----------------------+
                         |
                         v
Wave 5                 +----------------------+
                       | Agent A: B0          |
                       | Classical baselines  |
                       +----------------------+
                         |
                         v
Wave 6                 +----------------------+
                       | Agent A: N0          |
                       | TCN -> sequence gate |
                       +----------------------+
                         |
                         v
Wave 7   +----------------------+     +----------------------+
         | Agent A: H0          |  || | Agent B: O0          |
         | Multitask / hazard   |     | Walk-forward runner  |
         +----------------------+     +----------------------+
                         |
                         v
Wave 8   +----------------------+     +----------------------+
         | Agent A: U0          |  || | Agent B: X0          |
         | Universe expansion   |     | Costs / prop rules   |
         +----------------------+     +----------------------+
                         |
                         v
Wave 9                 +----------------------+
                       | Agent A: W0          |
                       | Frozen weekend study |
                       +----------------------+
                         |
                         v
Wave 10                +----------------------+
                       | Agent A: R0          |
                       | Reproduce / release  |
                       +----------------------+
```

Parallelizable waves: 1, 2, 3, 4, 7, and 8. Serial/gated waves: 5, 6, 9, and 10.

## Conflict Table

| Tasks | Conflict | Resolution |
|---|---|---|
| P0 / R0 | Both modify `README.md`: P0 adds setup/decision-gate documentation; R0 adds final reproduction/release instructions. | They are separated by nine waves. R0 rebases on the final P0 text and appends/updates only the crypto-movement sections without deleting the full-download gate. |

No same-wave task pair modifies the same versioned file. Directory-level overlap such as `src/crypto_movement/data/` or `evaluation/` is safe because agents own distinct files. Runtime artifacts can still collide if agents reuse an output path, so every concurrent run must use a distinct immutable run ID and must not share an MLflow local-store write target without locking.

Important interface merges that are dependencies rather than file conflicts:

| Producer | Consumer | Contract to freeze before consumer starts |
|---|---|---|
| C0 | D0, L0, S0 | Candle, anchor, horizon, label, artifact, and UTC semantics |
| D0 / L0 | S0 | Storage/index interface and per-anchor label bundle |
| Q0 / S0 | F0 | Quality-approved panel and lazy window/fold identity |
| F0 / E0 | B0 | Training batch plus metric/calibration interfaces |
| B0 | N0, O0 | Model protocol, trial registry, and baseline promotion memo |
| N0 | H0, O0 | Encoder/output shape, saved-package, and Stage B promotion record |
| H0 / O0 | U0, X0 | Frozen model/calibration/threshold package and prediction schema |
| U0 / X0 | W0 | Frozen universe, prediction, and cost-rule artifact IDs |

## Integration Git Workflow

The branch names below are recommendations; keep the repository's `codex/` prefix.

1. Create an integration branch such as `codex/plan1-integration` from the agreed starting commit. Do not include the user's unrelated dirty files.
2. For each parallel task, create a separate worktree and branch: `codex/plan1-w<wave>-<task-id>`.
3. Each agent commits only its owned files, includes focused test results in the commit message/body, and supplies the artifact/schema changes needed by consumers.
4. At wave end, merge in this order, then run the combined gate:

| Wave | Merge order | Combined gate |
|---|---|---|
| 1 | C0, then P0 | Contract/config tests, environment audit, full-download blocker review |
| 2 | D0, then L0 | Stored-fixture to label integration and manual ambiguity sample audit |
| 3 | Q0, then S0 | Quality-approved windows plus fold/batch manifests and leakage assertions |
| 4 | F0, then E0 | Causal-prefix/sentinel tests and dummy prediction report |
| 5 | B0 | Baseline replay, model reload, immutable promotion memo |
| 6 | N0 | Neural causality/batch/reload tests and Stage B promotion memo |
| 7 | O0, then H0 registration | End-to-end nested fixture run; freeze pilot candidate |
| 8 | U0, then X0 | Freeze universe/model/calibration/threshold/cost artifact IDs |
| 9 | W0 | Verify only frozen prediction artifacts were read |
| 10 | R0 | Resolve README conflict, clean replay, release checksum verification |

5. Tag or record the integration commit and artifact IDs after every gate. A downstream wave branches only from that gated integration commit.
6. If a gate fails, fix it on the owning task branch or a narrowly scoped integration-fix branch. Do not let a downstream task redefine the upstream contract silently.
7. Never use destructive cleanup to remove user work. Stage explicit paths and inspect the staged diff before every commit.

## Recommended Assignments: Two-Agent Team

| Wave | Agent A | Agent B |
|---|---|---|
| 1 | P0 decisions/config/environment | C0 contracts/time/provenance |
| 2 | D0 collector/storage/universe | L0 labels/event catalog |
| 3 | Q0 quality/bars/quarantine | S0 splits/windows/batches |
| 4 | F0 features/causality | E0 metrics/calibration/uncertainty |
| 5 | B0 implementation/training | Reproduce fixtures, review leakage and manifests; no downstream code |
| 6 | N0 TCN then sequence ladder | Reproduce baselines, audit batches/GPU determinism; no downstream code |
| 7 | H0 multitask/hazard | O0 orchestration/robustness |
| 8 | U0 universe expansion | X0 economics/prop rules |
| 9 | W0 weekend diagnostic | Audit frozen IDs and multiplicity; no model changes |
| 10 | R0 release/reproduction | Independent clean replay and bundle audit |

## Recommended Assignments: Three-Agent Team

Use Agents A/B exactly as above. Agent C is the integration and scientific-gate owner rather than a third speculative coder:

| Waves | Agent C responsibility |
|---|---|
| 1-2 | Validate decision blockers, contract compatibility, fixture provenance, and manual label audit. |
| 3-4 | Run independent leakage/sentinel tests and review fold-local preprocessing and report math. |
| 5-6 | Reproduce selected baseline/neural folds from manifests and verify promotion evidence before unlocking the next stage. |
| 7-8 | Integrate H0 into O0, verify unchanged folds/search budgets, and freeze the final artifact-ID set. |
| 9-10 | Audit that weekend inputs are frozen, then perform a clean-environment replay and release inventory check. |

If Agent C finds a defect, assign a small explicit fix branch to the owning task. Do not let the gatekeeper edit both parallel branches ad hoc.

## Critical Path and Start Recommendation

```text
C0 -> D0/L0 -> S0 -> F0/E0 -> B0 -> N0 -> H0/O0 -> U0/X0 -> W0 -> R0
```

Start with `sprint_1.md`, Agent A on P0 and Agent B on C0. If only one agent is available, implement C0 first, then P0, because every data/label lane consumes the canonical semantics.


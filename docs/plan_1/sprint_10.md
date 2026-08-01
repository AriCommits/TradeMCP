# Sprint 10: Reproducibility Audit and Release

## Wave Outcome

Demonstrate that a clean process can rebuild a small sample, reproduce selected labels/features/predictions, reload the chosen model package, and verify the final study/release bundle. This is the final serial integration wave.

**Estimated effort:** 16-24 engineering hours for one agent.

## Before This Wave Starts

- All prior sprint gates and reports are complete, including negative or stopped experiments.
- Raw data remains immutable and outside git; a small redistributable fixture or recreation recipe is available.
- Existing unrelated repository changes remain untouched.

## Serial Agent

### Agent A - R0: Reproducibility Audit, Final Study, and Release Bundle

**Files:** `README.md`; `src/crypto_movement/reporting/final_study.py`; `scripts/reproduce_crypto_sample.py`; `scripts/package_crypto_release.py`; `docs/crypto_movement/reproducibility.md`; `docs/crypto_movement/final_study.md`; `tests/crypto_movement/test_model_reload.py`; `tests/crypto_movement/test_reproducibility.py`; `tests/crypto_movement/test_release_bundle.py`

**Instructions:**

1. In a clean environment, rebuild a small sample from immutable inputs or the documented provider request.
2. Reproduce selected quality decisions, labels, causal features, fold/batch membership, calibration, and predictions from recorded hashes/configs/seeds.
3. Reload the saved model plus preprocessing/calibration and compare predictions within declared deterministic/numeric tolerances.
4. Write the final methods, results, robustness, economic, weekend, limitations, and go/no-go study, including all failed model stages.
5. Update README with setup, pilot, reproduction, and artifact-navigation instructions.
6. Package code/config/schema/lightweight manifests/selected outputs/model metadata and recreation instructions. Exclude raw caches, credentials, and unnecessarily large weights.
7. Generate and verify an inventory and checksums for the release archive.

**Definition of done:**

- The clean replay and model-reload tests pass from documented commands.
- Selected prediction identities and report inputs are reproducible.
- The ZIP/release bundle validates against its inventory and can recreate excluded data.
- The final report states proxy/survivorship/ambiguity/compute limitations and gives a direct go/no-go conclusion, including "no robust edge" when warranted.
- Full repository tests/static checks pass, and no Gen-1 or unrelated user files were overwritten.

## Integration Gate

- Resolve the only planned shared-file conflict by rebasing the README update on P0's setup text; retain both the environment decision gate and final reproduction instructions.
- Run clean-install smoke tests, selected full pilot replay, package inventory verification, and model reload.
- Archive the exact artifact IDs, package versions, and release checksum used by the final report.

## This Wave Unblocks

- Final research handoff and an explicit decision about whether further untouched data justifies a new model version.


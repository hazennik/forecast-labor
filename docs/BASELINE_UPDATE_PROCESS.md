# Baseline Update Process

**Purpose:** This document defines the controlled process for updating golden baselines when legitimate code changes occur.

**Critical:** Baselines are **FROZEN in git** to enable the determinism gate to detect regressions. Do NOT update baselines casually.

---

## Overview

### What Are Baselines?

**Golden baselines** are reference files that CI uses to detect unintended changes:

1. **Vintage Determinism Baseline** (`tests/fixtures/golden_baselines/vintage_hashes.json`)
   - SHA256 hashes of test vintage parquet files
   - Detects changes in ETL output structure or data generation logic

2. **Seasonal Diagnostics Baseline** (`tests/fixtures/golden_baselines/golden_seasonal_diagnostics.json`)
   - Placeholder M-statistics and Q-statistics
   - Currently structure-only validation (full X-13 verification in Phase 5+)

### Why Are Baselines Frozen?

**Frozen baselines enable regression detection:**
- CI generates current vintages → compares hashes to frozen baseline
- If hashes differ → CI fails → developer investigates
- If change is intentional → update baseline with documented reason
- If change is unintentional → fix the regression

**Auto-regenerating baselines (Codex 12 approach) creates a tautological gate:**
- CI generates vintages → overwrites baseline → compares to overwritten baseline
- Always passes (compares current to current)
- Cannot detect regressions

---

## When to Update Baselines

### Legitimate Reasons

✅ **Update baselines when:**
1. **Intentional ETL schema changes** - Adding/removing columns, changing data types
2. **Vintage generation logic changes** - Modifying `create_test_vintages.py` intentionally
3. **Data source structure updates** - Upstream APIs change format
4. **Seasonal adjustment improvements** - Updating X-13 specs or diagnostics computation
5. **Test data improvements** - Making synthetic data more realistic

### Invalid Reasons

❌ **DO NOT update baselines for:**
1. **CI failures** - Investigate the root cause first
2. **Convenience** - "CI is failing, let me just regenerate"
3. **Undocumented changes** - Always document why baseline changed
4. **Production bugs** - Fix the bug, don't hide it by updating baseline

---

## Baseline Update Process

### Step 1: Investigate CI Failure

When determinism verification fails:

```bash
# CI output shows:
❌ Vintage determinism check failed
   File: bls_ces_vintage.parquet
   Expected hash: d33ab995751fd2d2656f789df83a3c4cbe1767e6c90a51a39f7704cd7e6be10d
   Actual hash:   a7f29341c8b2e5f9d4a6c7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8
```

**Questions to ask:**
1. Did I intentionally change ETL or vintage generation logic?
2. Did I update dependencies that might affect data generation?
3. Is this hash difference expected?
4. Can I explain what changed and why?

### Step 2: Verify Change Is Intentional

**Local verification:**

```bash
# Generate current vintages
make setup-test-data

# Verify against baseline (should fail)
python scripts/verify_vintage_determinism.py --verify
# Shows hash mismatches

# Inspect the actual changes
python scripts/verify_vintage_determinism.py --verify --verbose
# Shows detailed diff of what changed
```

**Review the changes:**
- Are the new values correct?
- Is the new structure intentional?
- Are there unintended side effects?

### Step 3: Document the Change

**Create a clear commit message explaining:**
1. **What changed** - Specific code/logic that was modified
2. **Why it changed** - Reason for the change
3. **Impact** - What effect it has on baselines/data

**Example commit message:**
```
refactor: Update vintage generation to include new column

- Added 'revision_flag' column to CES vintages
- Required for Phase 5 revision forecasting model
- Updates vintage_hashes.json to reflect new schema

Breaking: Baseline update required
```

### Step 4: Regenerate Baselines Locally

```bash
# Regenerate all baselines with current code
make regenerate-baselines

# This will:
# 1. Generate deterministic vintages (seed=42)
# 2. Compute new hashes
# 3. Update vintage_hashes.json
# 4. Update diagnostics (if needed)
```

### Step 5: Verify Baselines Are Correct

```bash
# Verify the new baselines work
python scripts/verify_vintage_determinism.py --verify
# ✅ Should pass now

# Run full test suite
pytest tests/
# ✅ Should pass (287/287)

# Check git diff
git diff tests/fixtures/golden_baselines/
# Review changes - do they make sense?
```

### Step 6: Commit Baseline Updates

```bash
# Stage baseline files
git add tests/fixtures/golden_baselines/vintage_hashes.json
git add tests/fixtures/golden_baselines/golden_seasonal_diagnostics.json

# Commit with descriptive message
git commit -m "chore: Update baselines for [REASON]

[Detailed explanation of what changed and why]

Breaking: Baseline update required"

# Push to branch
git push origin feature/your-feature-branch
```

### Step 7: PR Review Process

**Baseline updates require extra scrutiny:**

✅ **PR checklist for baseline updates:**
- [ ] Commit message clearly explains what changed and why
- [ ] Code changes justify baseline update
- [ ] No unintended side effects
- [ ] All tests pass with new baselines
- [ ] Baseline diff reviewed and approved
- [ ] Documentation updated if needed

**Reviewers should:**
1. Verify the code change matches the baseline change
2. Check that the baseline update is intentional
3. Ensure documentation is updated
4. Confirm no regressions were hidden

---

## Emergency Baseline Recovery

### If Baselines Are Corrupted

```bash
# Restore from git history
git checkout HEAD -- tests/fixtures/golden_baselines/

# Or restore from specific commit
git checkout <commit-hash> -- tests/fixtures/golden_baselines/
```

### If Baselines Are Lost

```bash
# Regenerate from vetted code version
git checkout <last-known-good-commit>
make regenerate-baselines
git add tests/fixtures/golden_baselines/
git commit -m "restore: Regenerate baselines from vetted commit <hash>"
```

---

## Baseline Audit Trail

### Track Baseline Changes

```bash
# View baseline change history
git log --oneline -- tests/fixtures/golden_baselines/

# View specific baseline changes
git show <commit-hash>:tests/fixtures/golden_baselines/vintage_hashes.json

# Compare baselines between commits
git diff <commit1> <commit2> -- tests/fixtures/golden_baselines/
```

### Maintain Baseline Changelog

For major baseline updates, add entry to `docs/BASELINE_CHANGELOG.md`:

```markdown
## 2025-11-16: CES Vintage Schema Update
- **What:** Added 'revision_flag' column to CES vintages
- **Why:** Required for Phase 5 revision forecasting model
- **Commit:** abc123f
- **Hashes Changed:** bls_ces_vintage.parquet
```

---

## Production Baseline Management

### For Production Deployments

**Production baselines should use REAL ETL outputs:**

```bash
# 1. Run real ETL with production API keys
make seed

# 2. Generate baselines from real data
python scripts/verify_vintage_determinism.py --vintage-date <date> --create-baseline
python scripts/record_golden_diagnostics.py --vintage-date <date> --record

# 3. Store in separate production baseline file
cp tests/fixtures/golden_baselines/vintage_hashes.json \
   tests/fixtures/golden_baselines/vintage_hashes.production.json

# 4. Document production baseline in version control
git add tests/fixtures/golden_baselines/*.production.json
git commit -m "prod: Record production baselines for <date>"
```

**Note:** Test baselines (synthetic) and production baselines (real ETL) should be tracked separately.

---

## Best Practices

### DO:
✅ Document every baseline update with clear reasoning  
✅ Review baseline diffs carefully in PRs  
✅ Regenerate baselines after intentional code changes  
✅ Maintain baseline audit trail  
✅ Test thoroughly before committing baseline updates  

### DON'T:
❌ Update baselines to "fix" CI without investigating  
❌ Commit baseline updates without explanation  
❌ Skip PR review for baseline changes  
❌ Update baselines in CI automatically  
❌ Ignore hash mismatches as "noise"  

---

## Troubleshooting

### CI Fails After Baseline Update

**Problem:** Committed baseline update but CI still fails

**Solution:**
```bash
# Verify you committed the right files
git status
git log -1 --name-only

# Regenerate locally and compare
make regenerate-baselines
git diff tests/fixtures/golden_baselines/

# If differences found, recommit
git add tests/fixtures/golden_baselines/
git commit --amend
```

### Baseline Diverges Across Branches

**Problem:** Different branches have different baselines

**Solution:**
```bash
# Merge main into your branch
git merge main

# If conflicts, choose the appropriate baseline
# Then regenerate to ensure consistency
make regenerate-baselines

# Verify
python scripts/verify_vintage_determinism.py --verify
```

### Hash Changes Without Code Changes

**Problem:** Hashes changed but no code was modified

**Possible causes:**
1. **System/OS differences** - NumPy behavior can vary slightly across platforms
   - Solution: Ensure seed=42 is set consistently
   
2. **Dependency version changes** - Updated packages might affect generation
   - Solution: Pin dependencies in requirements.txt
   
3. **Random state pollution** - Previous code affected random state
   - Solution: Ensure `np.random.seed(42)` is called at start of generation

---

## Related Documentation

- `docs/planning/CODEX_ANALYSIS_13_RESOLUTION.md` - Why baselines must be frozen
- `docs/planning/IMPLEMENTATION_STATUS.md` - Current phase status
- `scripts/regenerate_baselines.py` - Baseline regeneration script
- `scripts/verify_vintage_determinism.py` - Verification script

---

**Last Updated:** 2025-11-16  
**Maintained By:** Forecast-Labor Team  
**Review Frequency:** After each baseline update


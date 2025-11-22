# Testing Mathematical Algorithms - Best Practices

**Purpose:** Prevent TDD blindspots when implementing complex mathematical algorithms  
**Created:** 2025-11-22  
**Motivation:** Codex Analysis 18 Finding 3 (MinT reconciliation algorithm mismatch)

---

## The Problem: TDD Blindspots in Mathematical Algorithms

### What Happened with MinT Reconciliation

**Documented Algorithm:**
```
ỹ = S (S' W^-1 S)^-1 S' W^-1 y  (Variance-minimizing projection)
```

**Actual Implementation:**
```python
# Simple proportional adjustment (enforces coherence only)
incoherence = y_agg - sum(y_bottom)
adjustments = distribute_proportionally(incoherence)
```

**Test Coverage:**
- ✅ Tests validated **coherence** (nation = Σstates)
- ❌ Tests didn't validate **optimality** (variance minimization)
- ❌ Tests didn't validate **method differentiation** (OLS ≠ WLS ≠ MinT)
- ❌ Tests didn't validate **projection matrix properties** (idempotence)

**Result:** 30 tests passed, but algorithm was mathematically incorrect.

### Why This Happens

Developers naturally test **observable behavior** (easy) rather than **mathematical correctness** (hard):

| What's Easy to Test | What's Hard to Test | What Matters Mathematically |
|---------------------|--------------------|-----------------------------|
| Output shape/type | Convergence to optimum | Optimality properties |
| Determinism (same input → same output) | Algorithm correctness | Mathematical invariants |
| Error handling | Method differences | Theoretical guarantees |
| Basic output validation | Reference comparison | Adherence to research literature |

---

## Phase 5 Risk Assessment: Potential TDD Blindspots

### 🚨 **High Risk: Already Fixed**

**1. MinT Reconciliation** ✅ **FIXED (2025-11-22)**
- **Risk:** Projection matrix formula not implemented
- **Tests Missing:** Optimality, method differentiation, projection properties
- **Status:** Fixed with 9 new optimality tests

### ⚠️ **Medium Risk: Review Needed**

**2. DFM (Dynamic Factor Model)**
- **Algorithm:** EM algorithm + Kalman filter
- **Current Tests:** Convergence, reproducibility, output shape
- **Potential Blindspot:**
  - ❓ Does EM converge to correct maximum likelihood estimate?
  - ❓ Does Kalman filter implement correct prediction/update equations?
  - ❓ Are factor loadings orthogonal (if assumed)?
  - ❓ Does likelihood increase monotonically during EM iterations?
- **Recommendation:** Add tests for EM likelihood progression, Kalman filter equations

**3. MIDAS Regression**
- **Algorithm:** NLS estimation with Almon polynomial weights
- **Current Tests:** Reproducibility, output shape, weight constraints
- **Potential Blindspot:**
  - ❓ Do Almon weights sum to 1 (if constrained)?
  - ❓ Does NLS converge to local minimum (not saddle point)?
  - ❓ Are lag weights monotonically decreasing (if assumed)?
  - ❓ Does model match reference MIDAS implementations?
- **Recommendation:** Add tests for weight properties, NLS gradient checks

**4. Isotonic Calibration**
- **Algorithm:** Isotonic regression (PAV algorithm)
- **Current Tests:** ECE reduction, reliability diagrams
- **Potential Blindspot:**
  - ❓ Are predictions monotonically non-decreasing?
  - ❓ Does calibration preserve ranking?
  - ❓ Does ECE actually decrease vs uncalibrated?
- **Recommendation:** Add tests for monotonicity, ranking preservation

### ✅ **Low Risk: Good Coverage**

**5. Conformal Prediction**
- **Algorithm:** Quantile-based prediction intervals
- **Current Tests:** Coverage validation (empirical ≈ nominal), interval width
- **Why Good:** Tests validate **the key property** (coverage guarantee)
- **Test Example:**
  ```python
  def test_coverage_meets_target():
      metrics = predictor.validate_coverage(y_true, y_pred, confidence_level=0.9)
      assert 0.85 <= metrics['empirical_coverage'] <= 0.95  # ✅ Tests mathematical property
  ```

**6. Ridge Regression (Revision Model)**
- **Algorithm:** Standard Ridge regression (sklearn)
- **Risk:** Low (well-tested sklearn implementation)
- **Current Tests:** Reproducibility, feature importance, patterns

**7. XGBoost/LightGBM Quantile Models**
- **Algorithm:** Gradient boosting (sklearn-compatible)
- **Risk:** Low (battle-tested libraries)
- **Current Tests:** Quantile ordering, crossing prevention

---

## Testing Principles for Mathematical Algorithms

### **Principle 1: Test Mathematical Properties, Not Just Outputs**

❌ **Bad Test (Observable Behavior Only):**
```python
def test_reconcile_produces_output():
    """Test that reconciliation returns a DataFrame."""
    reconciled = reconciler.reconcile(forecasts)
    assert isinstance(reconciled, pd.DataFrame)  # ❌ Trivial
    assert len(reconciled) == len(forecasts)      # ❌ Trivial
```

✅ **Good Test (Mathematical Property):**
```python
def test_reconcile_minimizes_variance():
    """Test that MinT reconciliation reduces forecast error variance."""
    base_error_cov = np.cov((base_forecasts - true_values).T)
    reconciled_error_cov = np.cov((reconciled - true_values).T)
    
    # Key MinT property: reconciliation minimizes trace of error covariance
    assert np.trace(reconciled_error_cov) <= np.trace(base_error_cov) * 1.1
```

### **Principle 2: Test Algorithm-Specific Invariants**

Every mathematical algorithm has **invariants** that must hold. Test them.

| Algorithm | Invariant to Test |
|-----------|------------------|
| **MinT Reconciliation** | Projection matrix idempotent: `P @ P = P` |
| **EM Algorithm** | Likelihood increases monotonically: `L[t+1] >= L[t]` |
| **Kalman Filter** | Covariance matrices positive semi-definite |
| **Isotonic Regression** | Predictions monotonically non-decreasing |
| **Conformal Prediction** | Empirical coverage ≈ nominal coverage |
| **Ridge Regression** | Regularization shrinks coefficients toward zero |
| **Gradient Boosting** | Training loss decreases with iterations |

### **Principle 3: Test Method Differentiation**

If you offer multiple algorithm variants (e.g., OLS, WLS, MinT), **test that they differ**:

```python
def test_ols_vs_wls_produce_different_results():
    """Test that OLS and WLS produce different results when variances differ."""
    # Create data with heterogeneous variances
    forecasts = create_forecasts_with_different_variances()
    
    reconciled_ols = MinTReconciler(method='ols').fit(forecasts).reconcile(forecasts)
    reconciled_wls = MinTReconciler(method='wls').fit(forecasts).reconcile(forecasts)
    
    diff = (reconciled_ols - reconciled_wls).abs().values
    assert diff.max() > 0.01, "OLS and WLS should differ when variances differ"
```

### **Principle 4: Test Against Reference Implementations**

Compare your implementation against:
1. **Reference libraries** (e.g., R's `hts` package for MinT)
2. **Known analytical solutions** (e.g., simple 2-series hierarchy)
3. **Published examples** from research papers

```python
def test_against_known_solution():
    """Test against analytically solvable case."""
    # Simple case: 2 series with known optimal weights
    forecasts = create_simple_two_series_case()
    
    reconciled = reconciler.reconcile(forecasts)
    
    # For this case, we know the optimal solution analytically
    expected = compute_analytical_solution(forecasts)
    
    np.testing.assert_allclose(reconciled, expected, rtol=0.01)
```

### **Principle 5: Test Convergence Properties**

For iterative algorithms (EM, NLS, gradient descent):

```python
def test_em_likelihood_increases():
    """Test that EM algorithm increases likelihood monotonically."""
    model = DynamicFactorModel(n_factors=2, max_iter=20)
    
    # Fit with logging
    model.fit(X, y, vintage_date='2024-11-15')
    
    # Check likelihood progression
    likelihoods = model.likelihood_history_
    for t in range(1, len(likelihoods)):
        assert likelihoods[t] >= likelihoods[t-1] - 1e-6, \
            f"Likelihood decreased at iteration {t}: {likelihoods[t-1]} → {likelihoods[t]}"
```

### **Principle 6: Test Edge Cases with Known Behavior**

Create edge cases where behavior is theoretically known:

```python
def test_perfect_data_requires_no_reconciliation():
    """Test that already-coherent forecasts are unchanged."""
    # Create perfectly coherent forecasts
    coherent = pd.DataFrame({
        'national': [100, 110, 120],
        's1': [60, 66, 72],
        's2': [40, 44, 48]  # Sums exactly to national
    })
    
    reconciled = reconciler.reconcile(coherent)
    
    # Should be unchanged (or nearly so)
    np.testing.assert_allclose(reconciled, coherent, atol=1e-6)
```

---

## Testing Checklist for Mathematical Algorithms

When implementing a mathematical algorithm, ensure tests cover:

### ✅ **Basic Functionality (Necessary but Not Sufficient)**
- [ ] Correct output shape/type
- [ ] Deterministic (same seed → same output)
- [ ] Handles missing data gracefully
- [ ] Error handling for invalid inputs
- [ ] Save/load persistence

### ✅ **Mathematical Correctness (Critical)**
- [ ] **Key algorithmic property verified**
  - MinT: Variance minimization
  - EM: Likelihood increases
  - Conformal: Coverage guarantee
  - Isotonic: Monotonicity
- [ ] **Invariants hold**
  - Projection matrices idempotent
  - Covariances positive semi-definite
  - Weights sum to constraints
- [ ] **Convergence properties**
  - Iterative methods converge
  - Convergence criterion meaningful
  - Stopping conditions appropriate

### ✅ **Method Differentiation (If Multiple Variants)**
- [ ] Different methods produce different results
- [ ] Differences align with theory
  - E.g., WLS vs OLS differ when variances differ
  - E.g., MinT vs WLS differ when correlations exist
- [ ] Each method has distinct use case

### ✅ **Reference Validation**
- [ ] Matches known analytical solutions
- [ ] Matches reference implementations (R, Python libraries)
- [ ] Matches published examples from papers
- [ ] Edge cases behave as theoretically expected

### ✅ **Performance Properties**
- [ ] Computational complexity as expected
- [ ] Scales appropriately with data size
- [ ] Numerical stability with ill-conditioned data

---

## Red Flags: When to Be Extra Vigilant

### 🚩 **Red Flag 1: "Tests Pass But I Don't Understand Why"**

If you can't explain mathematically **why** a test passes, the test may not be validating correctness.

**Action:** Add tests for theoretical properties you **do** understand.

### 🚩 **Red Flag 2: "All Methods Produce Similar Results"**

If OLS/WLS/MinT produce nearly identical results, your implementation may not be using the weights correctly.

**Action:** Create test cases where methods **should** differ significantly.

### 🚩 **Red Flag 3: "Tests Only Check Coherence/Format"**

If all tests validate output format or simple constraints, you're likely missing algorithmic correctness.

**Action:** Add tests for the algorithm's **defining property** (what makes it special).

### 🚩 **Red Flag 4: "Docstring Says X, Code Does Y"**

If documentation references a formula/paper, verify the code implements that exact formula.

**Action:** Add reference validation test or simplify documentation to match implementation.

### 🚩 **Red Flag 5: "No Comparison to Baseline/Alternative"**

If you don't test that your method improves over a baseline, you can't verify it works.

**Action:** Add tests comparing to simpler alternatives or baselines.

---

## Implementation Workflow

### **Before Writing Code**

1. **Read the research paper** - Understand the algorithm deeply
2. **Identify key properties** - What makes this algorithm work?
3. **Write property tests first** - TDD for mathematical properties
4. **Create reference cases** - Find known solutions to test against

### **While Writing Code**

1. **Implement incrementally** - One mathematical component at a time
2. **Validate each component** - Test invariants at each step
3. **Log intermediate values** - For debugging and convergence monitoring
4. **Compare to reference** - Frequently check against known implementations

### **After Code Works**

1. **Review test coverage** - Do tests validate correctness, not just behavior?
2. **Add edge case tests** - Degenerate cases, perfect data, extreme values
3. **Document assumptions** - What conditions must hold for correctness?
4. **Peer review math** - Have someone verify algorithm matches documentation

---

## Lessons from Codex Analysis 18

### **What Went Wrong**
- ✅ TDD was followed (tests written alongside code)
- ✅ Tests passed (30/30)
- ❌ Tests validated **coherence** (easy) not **optimality** (hard)
- ❌ Algorithm didn't match documented formula
- ❌ Methods (OLS/WLS/MinT) not differentiated

### **What Went Right**
- ✅ Codex Analysis caught the issue
- ✅ Fix was straightforward (proper formula implementation)
- ✅ New tests prevent regression (9 optimality tests)

### **Key Takeaway**

> **"Passing tests ≠ Correct algorithm"**
>
> Tests must validate **mathematical correctness**, not just **observable behavior**.

---

## Examples: Good vs Bad Tests

### **Example 1: Reconciliation**

❌ **Bad:**
```python
def test_reconciliation_works():
    reconciled = reconciler.reconcile(forecasts)
    assert reconciled is not None  # Trivial
    assert len(reconciled) == len(forecasts)  # Trivial
```

✅ **Good:**
```python
def test_reconciliation_minimizes_variance():
    """MinT reconciliation should minimize forecast error variance."""
    true_values = generate_true_values()
    base_error = (forecasts - true_values).values
    reconciled_error = (reconciled - true_values).values
    
    base_variance = np.trace(np.cov(base_error.T))
    reconciled_variance = np.trace(np.cov(reconciled_error.T))
    
    assert reconciled_variance <= base_variance * 1.1
```

### **Example 2: Convergence**

❌ **Bad:**
```python
def test_em_converges():
    model.fit(X, y)
    assert model.n_iter_ < model.max_iter  # May converge by chance
```

✅ **Good:**
```python
def test_em_likelihood_increases_monotonically():
    """EM algorithm must increase likelihood at each iteration."""
    model.fit(X, y)
    
    likelihoods = model.likelihood_history_
    for t in range(1, len(likelihoods)):
        assert likelihoods[t] >= likelihoods[t-1] - 1e-8, \
            f"Likelihood decreased: {likelihoods[t-1]} → {likelihoods[t]}"
```

### **Example 3: Method Differentiation**

❌ **Bad:**
```python
def test_all_methods_work():
    for method in ['ols', 'wls', 'mint']:
        result = reconciler(method=method).reconcile(forecasts)
        assert result is not None  # All methods work, but are they different?
```

✅ **Good:**
```python
def test_methods_produce_different_results():
    """OLS, WLS, and MinT should produce different results."""
    results = {
        method: reconciler(method=method).reconcile(forecasts)
        for method in ['ols', 'wls', 'mint']
    }
    
    # Verify all pairs differ significantly
    for m1, m2 in [('ols', 'wls'), ('wls', 'mint'), ('ols', 'mint')]:
        diff = (results[m1] - results[m2]).abs().values
        assert diff.max() > 0.01, f"{m1} and {m2} produce nearly identical results"
```

---

## When to Update This Document

Add new sections when:
1. New mathematical algorithms are implemented
2. New TDD blindspots are discovered
3. Better testing strategies are identified
4. Reference validation approaches improve

---

## References

- Codex Analysis 18 (2025-11-22): MinT reconciliation algorithm mismatch
- CODEX_ANALYSIS_18_FINDING_3_RESOLUTION.md: Detailed fix documentation
- Wickramasuriya et al. (2019): "Optimal forecast reconciliation..."
- Test-Driven Development: By Example (Kent Beck)

---

**Document Version:** 1.0  
**Last Updated:** 2025-11-22  
**Status:** Active guideline for all mathematical algorithm development


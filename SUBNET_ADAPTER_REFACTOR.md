# Subnet Adapter Pattern - Architectural Refactor

**Date:** November 11, 2025  
**Status:** ✅ Scaffolding Updated, Ready for Phase 7 Implementation  
**Impact:** Future-proof, no rework needed

---

## Executive Summary

Refactored the project architecture from **SN41-specific** to **subnet-agnostic** using the **Adapter Pattern**. This change prepares the system to integrate with any Bittensor subnet without requiring core system modifications.

### Key Decision
- **Before:** Hardcoded SN41 integration (`sn41/` directory, SN41-specific logic)
- **After:** Generic subnet framework with SN41 as first implementation

---

## What Changed

### 1. Directory Structure
```diff
- sn41/                          # SN41-specific hardcoded
-   ├─ event_catalog/
-   ├─ payloads/
-   ├─ submitter/
-   ├─ health/
-   └─ keys/

+ subnets/                       # Subnet-agnostic framework
+   ├─ base_adapter.py           # Abstract base class (interface)
+   ├─ registry.py               # Dynamic adapter discovery
+   ├─ scheduler.py              # Multi-subnet scheduling
+   ├─ scoring_shim.py           # Scoring abstraction layer
+   ├─ sn41/                     # SN41 implementation (first adapter)
+   │   ├─ adapter.py            # Implements base_adapter
+   │   ├─ event_catalog.py      # SN41-specific events
+   │   ├─ payload_builder.py    # SN41 probability vectors
+   │   ├─ config.yaml           # SN41 config (bins, targets, cadence)
+   │   └─ tests/                # SN41-specific tests
+   └─ keys/                     # Hotkey/coldkey storage
```

### 2. Configuration System
```diff
+ configs/
+   ├─ subnets/
+   │   ├─ sn41.yaml             # SN41-specific configuration
+   │   └─ template.yaml         # Template for new subnet adapters
+   └─ zones/
+       ├─ zone1.yaml            # Training zone settings
+       └─ zone2.yaml            # Inference zone settings
```

### 3. Scripts Updated
```diff
- scripts/make_sn41_payload.py   # SN41-only
- scripts/submit_sn41.py          # SN41-only

+ scripts/make_subnet_payload.py  # Works with any subnet
+ scripts/submit_to_subnet.py     # Reads ACTIVE_SUBNET env var
```

### 4. Database Schema (Generalized)
```diff
- sn41.submission_log            # SN41-specific
- sn41.event_catalog             # SN41-specific

+ subnets.submission_log         # Any subnet
+ subnets.event_catalog          # Any subnet
  + subnet_id column             # Differentiates between subnets
```

---

## Adapter Pattern Architecture

### Base Adapter Interface
```python
# subnets/base_adapter.py
class BaseSubnetAdapter(ABC):
    @abstractmethod
    def get_event_catalog(self) -> Dict:
        """Return subnet-specific event definitions"""
        
    @abstractmethod
    def build_payload(self, predictions: Dict) -> bytes:
        """Convert predictions to subnet-specific payload format"""
        
    @abstractmethod
    def validate_payload(self, payload: bytes) -> bool:
        """Validate payload before submission"""
        
    @abstractmethod
    def submit(self, payload: bytes, keys: Keys) -> SubmissionResult:
        """Submit to subnet (signing, retries, etc.)"""
        
    @abstractmethod
    def get_config(self) -> SubnetConfig:
        """Return subnet-specific configuration"""
```

### SN41 Adapter Implementation
```python
# subnets/sn41/adapter.py
class SN41Adapter(BaseSubnetAdapter):
    def __init__(self):
        self.config = load_yaml("configs/subnets/sn41.yaml")
        
    def get_event_catalog(self) -> Dict:
        return load_sn41_events()
        
    def build_payload(self, predictions: Dict) -> bytes:
        return build_sn41_probability_vector(predictions, self.config)
        
    # ... other methods
```

### Registry System
```python
# subnets/registry.py
class SubnetRegistry:
    def __init__(self):
        self.adapters = {
            "sn41": SN41Adapter,
            # Future: "sn18": SN18Adapter,
            # Future: "sn25": SN25Adapter,
        }
    
    def get_adapter(self, subnet_id: str) -> BaseSubnetAdapter:
        """Load adapter dynamically based on ACTIVE_SUBNET"""
        adapter_class = self.adapters.get(subnet_id)
        if not adapter_class:
            raise ValueError(f"Unknown subnet: {subnet_id}")
        return adapter_class()
```

### Scheduler (Multi-Subnet Support)
```python
# subnets/scheduler.py
class SubnetScheduler:
    def __init__(self, active_subnets: List[str]):
        self.adapters = [registry.get_adapter(s) for s in active_subnets]
        
    def get_next_submission_window(self) -> Dict:
        """Coordinate submission windows across multiple subnets"""
        
    def should_submit(self, subnet_id: str) -> bool:
        """Check if submission window is open for subnet"""
```

---

## Configuration Example

### SN41 Configuration (configs/subnets/sn41.yaml)
```yaml
subnet_id: sn41
name: "Labor Market Forecasting"
netuid: 41

# Event catalog
events:
  - event_id: "NFP_2025_12"
    target: "Non-Farm Payrolls"
    release_date: "2025-12-05"
    bins:
      - [-inf, -200]
      - [-200, -100]
      - [-100, 0]
      - [0, 100]
      - [100, 200]
      - [200, 300]
      - [300, inf]

# Submission windows
cadence:
  type: "monthly"
  window_open: "T-5d"
  window_close: "T-1d"

# Scoring assumptions
scoring:
  metric: "log_score"
  calibration_weight: 0.3
  variance_penalty: 0.2
  
# Network settings
network:
  endpoint: "wss://entrypoint-finney.opentensor.ai"
  timeout: 30
  retries: 3
  backoff: "exponential"
```

---

## Environment Variables

### Active Subnet Selection
```bash
# .env or .env.production
ACTIVE_SUBNET=sn41              # Primary subnet
BACKUP_SUBNETS=sn18,sn25        # Optional: fallback subnets
```

### Zone 2 Configuration
```bash
# zone2/active_subnet.env (production)
ACTIVE_SUBNET=sn41
HOTKEY_PATH=/subnets/keys/hotkey
COLDKEY_PATH=/subnets/keys/coldkey
```

---

## Benefits of This Architecture

### 1. Future-Proof
- Add new subnets without touching core forecasting logic
- No refactoring needed when integrating with SN18, SN25, etc.
- Clean separation of concerns

### 2. Testable
- Mock adapters for testing without network calls
- Test each subnet in isolation
- Validate payloads before submission

### 3. Flexible
- Switch subnets via environment variable
- Run multiple subnets in parallel (multi-miner)
- A/B test different subnets

### 4. Maintainable
- Each subnet is self-contained module
- Clear interface contracts
- Easy to debug and extend

### 5. Industry Best Practice
- Adapter Pattern is well-established design pattern
- Used by: AWS SDK, payment processors, multi-chain crypto wallets
- Scales to dozens of integrations

---

## Development Impact

### No Rework Required
- ✅ **Zero SN41 code written yet** (Phase 7 not started)
- ✅ Only planning/scaffolding documents updated
- ✅ No refactoring of existing code

### Timeline Impact
- **Original Phase 7:** 2 weeks (SN41-specific)
- **Updated Phase 7:** 2.5 weeks (adapter pattern + SN41)
- **Added time:** ~2-3 days for base adapter framework
- **Future subnet adds:** ~3-5 days each (vs. weeks with refactor)

### Phase 7 Updated Tasks
1. **Week 1:**
   - Build base adapter interface (`base_adapter.py`)
   - Implement registry (`registry.py`)
   - Implement scheduler (`scheduler.py`)
   - Create scoring shim (`scoring_shim.py`)
   - Set up configuration system

2. **Week 2:**
   - Implement SN41 adapter
   - Build SN41 event catalog
   - Build SN41 payload builders
   - Signing & submission logic
   - Health checks & monitoring

3. **Week 2.5:**
   - Comprehensive testing (unit, integration, e2e)
   - Multi-subnet switching tests
   - Documentation (`docs/SUBNET_INTEGRATION.md`)

---

## Testing Strategy

### Base Adapter Tests
```python
# tests/subnets/test_base_adapter.py
def test_adapter_interface():
    """Ensure all adapters implement required methods"""
    
def test_registry_discovery():
    """Verify registry can load adapters dynamically"""
    
def test_scheduler_coordination():
    """Test multi-subnet window management"""
```

### SN41 Adapter Tests
```python
# tests/subnets/test_sn41_adapter.py
def test_sn41_event_catalog():
    """Validate SN41 event definitions"""
    
def test_sn41_payload_building():
    """Test probability vector generation"""
    
def test_sn41_payload_validation():
    """Ensure payloads sum to 1, valid bins"""
```

### Mock Adapter (Testing)
```python
# tests/subnets/mock_adapter.py
class MockSubnetAdapter(BaseSubnetAdapter):
    """Mock adapter for testing without network calls"""
    
    def submit(self, payload: bytes, keys: Keys):
        return SubmissionResult(success=True, txn_hash="0xMOCK")
```

---

## Documentation

### New Documentation Required
1. **`docs/SUBNET_INTEGRATION.md`** - Guide for adding new subnet adapters
   - Step-by-step tutorial
   - Configuration examples
   - Testing requirements
   - Deployment checklist

2. **`configs/subnets/template.yaml`** - Template for new subnet configs
   - Commented examples
   - Required vs. optional fields
   - Best practices

3. **Update existing docs:**
   - `docs/PROJECT_INSTRUCTIONS.md` - Reflect adapter pattern
   - `docs/AGENTS_AND_OPS_RUNBOOK.md` - Multi-subnet ops
   - `README.md` - Highlight subnet flexibility

---

## Migration Path (Future Subnets)

### Adding a New Subnet (Example: SN18)

**Step 1:** Create adapter
```bash
mkdir -p subnets/sn18
touch subnets/sn18/adapter.py
touch subnets/sn18/event_catalog.py
touch subnets/sn18/payload_builder.py
touch subnets/sn18/config.yaml
```

**Step 2:** Implement interface
```python
# subnets/sn18/adapter.py
class SN18Adapter(BaseSubnetAdapter):
    # Implement required methods
```

**Step 3:** Configure
```yaml
# configs/subnets/sn18.yaml
subnet_id: sn18
name: "Example Subnet"
# ... SN18-specific config
```

**Step 4:** Register
```python
# subnets/registry.py
self.adapters = {
    "sn41": SN41Adapter,
    "sn18": SN18Adapter,  # Add new adapter
}
```

**Step 5:** Test
```bash
ACTIVE_SUBNET=sn18 python scripts/submit_to_subnet.py --dry-run
```

**Estimated time:** 3-5 days per new subnet

---

## Comparison: Before vs. After

### Before (SN41-Specific)
```
❌ Hardcoded SN41 logic throughout codebase
❌ Adding new subnet = major refactor
❌ Can't test multiple subnets easily
❌ Tight coupling between forecasting & submission
❌ 2-3 weeks to add new subnet
```

### After (Adapter Pattern)
```
✅ Generic subnet interface
✅ Adding new subnet = implement adapter (~3-5 days)
✅ Easy to mock and test
✅ Clean separation of concerns
✅ Multi-subnet support out of the box
```

---

## Files Updated

### Planning Documents
- ✅ `docs/planning/REPO_SCAFFOLDING.md` - Directory structure updated
- ✅ `docs/planning/IMPLEMENTATION_STATUS.md` - Phase 7 tasks updated

### Infrastructure (No Code Yet)
- ✅ Directory structure: `subnets/` (replaces `sn41/`)
- ✅ Directory structure: `configs/subnets/`
- ✅ Database schema references updated

### Future Implementation (Phase 7)
- 📋 `subnets/base_adapter.py`
- 📋 `subnets/registry.py`
- 📋 `subnets/scheduler.py`
- 📋 `subnets/scoring_shim.py`
- 📋 `subnets/sn41/adapter.py`
- 📋 `subnets/sn41/event_catalog.py`
- 📋 `subnets/sn41/payload_builder.py`
- 📋 `subnets/sn41/config.yaml`
- 📋 `configs/subnets/template.yaml`
- 📋 `scripts/make_subnet_payload.py`
- 📋 `scripts/submit_to_subnet.py`
- 📋 `docs/SUBNET_INTEGRATION.md`

---

## Decision Rationale

### Why Now?
- ✅ **Perfect timing:** Phase 7 hasn't started yet (no rework)
- ✅ **Feedback validated:** GPT-5 recommendations align with best practices
- ✅ **Low cost:** Only planning docs updated, +2-3 days to Phase 7
- ✅ **High value:** Future-proof for multiple subnets

### Why Adapter Pattern?
- ✅ **Industry standard:** Used by AWS, Stripe, multi-chain wallets
- ✅ **Testable:** Clean mocking without network calls
- ✅ **Maintainable:** Each subnet is isolated module
- ✅ **Scalable:** Adding subnet #10 is same effort as subnet #2

### Alternatives Considered
1. **Keep SN41 hardcoded** ❌
   - Pro: Slightly faster Phase 7
   - Con: Major refactor needed for subnet #2
   
2. **Plugin system** ❌
   - Pro: Ultra-flexible
   - Con: Over-engineered for our use case
   
3. **Adapter pattern** ✅ **CHOSEN**
   - Pro: Right balance of flexibility and simplicity
   - Pro: Well-understood pattern
   - Pro: Easy to test and maintain

---

## Success Criteria

### Phase 7 Completion
- [ ] All base adapter tests pass
- [ ] SN41 adapter fully implemented
- [ ] SN41 payloads validated (sum to 1, valid bins)
- [ ] Mock adapter tests demonstrate pattern works
- [ ] Documentation guide for adding new subnets
- [ ] Dry-run submission successful

### Future Validation
- [ ] Second subnet (SN18 or SN25) added in <5 days
- [ ] No refactoring of core forecasting logic required
- [ ] Multi-subnet parallel operation works

---

## Conclusion

✅ **Scaffolding successfully refactored** to subnet-agnostic adapter pattern  
✅ **No code rework required** (perfect timing before Phase 7)  
✅ **Future-proof architecture** ready for multiple Bittensor subnets  
✅ **Industry best practices** aligned with GPT-5 feedback  

**Next Steps:**
1. Complete Phase 3.5 (Testing Foundation) - CURRENT
2. Implement Phase 4-6.5 (Features, Models, API, Backtests)
3. Implement Phase 7 with adapter pattern (Week 11.5-13.5)

**Estimated Impact:**
- Development time: +2-3 days (Phase 7 only)
- Future subnet adds: 3-5 days each (vs. weeks)
- Technical debt: Eliminated
- Code quality: Significantly improved

---

**Document Author:** AI Assistant  
**Review Status:** Ready for User Approval  
**Implementation Phase:** Phase 7 (Not Started)


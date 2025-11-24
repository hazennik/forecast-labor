# Security: Key Management for Model Artifact Signing

**Version:** 1.0  
**Last Updated:** 2025-11-24  
**Applies To:** Phase 5.10 Model Registry & Signing  
**Status:** Production Operational Procedures

---

## Overview

Model artifacts are signed using SHA256 signatures to ensure integrity and authenticity during Zone 1 → Zone 2 transfers. This document describes operational procedures for key generation, storage, rotation, and revocation.

**Security Model:**
- **Zone 1 (Training):** Private environment with signing keys
- **Zone 2 (Inference):** Public environment with verification keys only
- **Artifact Transfer:** Signed bundles prevent tampering

---

## Table of Contents

1. [Key Lifecycle](#key-lifecycle)
2. [Key Generation](#key-generation)
3. [Key Storage](#key-storage)
4. [Key Rotation](#key-rotation)
5. [Key Revocation](#key-revocation)
6. [Audit Logging](#audit-logging)
7. [Security Checklist](#security-checklist)
8. [Troubleshooting](#troubleshooting)

---

## Key Lifecycle

### Lifecycle Stages

```
Generation → Active Use → Rotation → Deprecation → Archival
     ↓           ↓            ↓            ↓           ↓
  Create     Sign         Gradual      Grace      Audit
  Keys      Artifacts    Rollover     Period      Only
```

### Recommended Schedule

| Event | Frequency | Action |
|-------|-----------|--------|
| **Regular Rotation** | Every 90 days (quarterly) | Rotate to new key version |
| **Emergency Rotation** | Immediately | Upon suspected compromise |
| **Audit Review** | Monthly | Review signing logs |
| **Archive Cleanup** | Annually | Remove keys >2 years old |

---

## Key Generation

### When to Generate Keys

- **Initial Setup:** First-time system deployment
- **Scheduled Rotation:** Every 90 days
- **Emergency Rotation:** After suspected compromise
- **Environment Setup:** Separate keys for dev/staging/prod

### Generation Procedure

**Manual Generation (Development):**

```bash
# Generate SHA256-based signing key (placeholder for actual key generation)
# In practice, use proper key generation tools (GPG, OpenSSL, etc.)

python -c "
import secrets
import hashlib
from pathlib import Path

# Generate random key material
key_bytes = secrets.token_bytes(64)  # 512 bits
key_hex = key_bytes.hex()

# Create key file
key_dir = Path('data/secrets/signing_keys')
key_dir.mkdir(parents=True, exist_ok=True)

key_file = key_dir / 'signing_key_v1.key'
key_file.write_text(key_hex)
key_file.chmod(0o600)  # Owner read/write only

print(f'✅ Key generated: {key_file}')
print(f'   Key ID: {hashlib.sha256(key_bytes).hexdigest()[:16]}')
"
```

**Production Generation (Recommended):**

```bash
# Use secrets manager CLI (AWS, Azure, GCP)
# Example with AWS Secrets Manager:
aws secretsmanager create-secret \
    --name forecast-labor/signing-key-v2 \
    --description "Model artifact signing key v2" \
    --secret-string "$(python -c 'import secrets; print(secrets.token_hex(64))')"
```

### Key Properties

- **Algorithm:** SHA256 (currently)
- **Size:** 512 bits minimum
- **Format:** Hex-encoded string
- **Versioning:** v1, v2, v3, etc.
- **Environment:** Separate keys per environment

---

## Key Storage

### Development Environment

```bash
# Directory structure
data/secrets/signing_keys/
├── signing_key_v1.key   # Current key
├── signing_key_v2.key   # Next key (during rotation)
└── .gitignore           # MUST be gitignored

# Environment variables
export SIGNING_KEY_PATH=data/secrets/signing_keys/signing_key_v1.key
export SIGNING_KEY_VERSION=v1
```

**Security Requirements:**
- ✅ Keys in `data/secrets/` (gitignored)
- ✅ File permissions: 0600 (owner read/write only)
- ✅ Never committed to git
- ✅ `.env` file gitignored

### Production Environment

```bash
# Use secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.)

# AWS Secrets Manager
export SIGNING_KEY_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123456789012:secret:signing-key-v2

# HashiCorp Vault
export VAULT_ADDR=https://vault.example.com
export VAULT_TOKEN=<token>
export SIGNING_KEY_PATH=secret/data/forecast-labor/signing-key-v2
```

**Security Requirements:**
- ✅ Keys in secrets manager (AWS, Vault, Azure Key Vault)
- ✅ Access controlled via IAM/RBAC
- ✅ Audit logging enabled
- ✅ Encryption at rest
- ✅ Automatic rotation supported

### Key Access Control

**Who Can Access Signing Keys:**
- Training pipeline service account
- Model deployment service account
- Senior ML engineers (emergency only)

**Who Can Access Verification Keys:**
- Zone 2 inference service (public key)
- All engineers (verification is not sensitive)

---

## Key Rotation

### Regular Rotation (Every 90 Days)

**Week 1: Generate New Key**

```bash
# Generate v3 (assuming v2 is current)
python scripts/generate_signing_key.py --version v3

# Verify generation
ls -la data/secrets/signing_keys/
# Should show: signing_key_v2.key, signing_key_v3.key
```

**Week 2: Configure Dual-Key Verification**

```python
# Update ArtifactSigner configuration
from models_src.utils.signing import ArtifactSigner

signer = ArtifactSigner(
    signing_key=load_key('v3'),           # Sign with new key
    verification_keys={
        'v2': load_key('v2'),             # Still verify old signatures
        'v3': load_key('v3')              # And verify new signatures
    }
)
```

**Week 3: Sign New Artifacts with New Key**

```bash
# All new model training uses v3
export SIGNING_KEY_VERSION=v3

# Old models still verified with v2
# New models signed and verified with v3
```

**Week 4: Deprecate Old Key**

```bash
# After all production models re-signed with v3
# Remove v2 from verification (keep for audit)

# Move to archive
mv data/secrets/signing_keys/signing_key_v2.key \
   data/secrets/signing_keys/archived/signing_key_v2.key.$(date +%Y%m%d)
```

### Emergency Rotation (Immediate)

**If key compromise suspected:**

1. **Immediate Actions (< 1 hour):**
   ```bash
   # Revoke compromised key immediately
   echo "REVOKED: $(date)" >> data/secrets/signing_keys/REVOKED_KEYS.txt
   echo "v2" >> data/secrets/signing_keys/REVOKED_KEYS.txt
   
   # Generate replacement
   python scripts/generate_signing_key.py --version v3 --emergency
   
   # Update environment
   export SIGNING_KEY_VERSION=v3
   ```

2. **Short-term Actions (< 24 hours):**
   ```bash
   # Re-sign all production models
   python scripts/resign_all_models.py --new-key-version v3
   
   # Audit all signatures made with compromised key
   python scripts/audit_signatures.py --key-version v2 --since 2025-01-01
   ```

3. **Follow-up Actions (< 1 week):**
   - Review audit logs for suspicious activity
   - Update all environments (dev, staging, prod)
   - Document incident in security log
   - Notify stakeholders

---

## Key Revocation

### When to Revoke

- ✅ Key compromise confirmed
- ✅ Key lost or stolen
- ✅ Personnel change (if key was personal)
- ✅ Security policy violation detected

### Revocation Procedure

```bash
# 1. Add to revocation list
echo "v2,$(date),compromised,incident-2025-11-24" >> REVOKED_KEYS.csv

# 2. Remove from verification keys immediately
# Update ArtifactSigner config to exclude revoked key

# 3. Re-sign all production artifacts
python scripts/resign_all_models.py --exclude-key v2

# 4. Audit all signatures made with revoked key
python scripts/audit_signatures.py --key v2 --output revoked_key_audit.json

# 5. Archive (do not delete - needed for audit)
mv signing_key_v2.key archived/REVOKED_signing_key_v2.key
```

---

## Audit Logging

### What to Log

All signing operations must be logged:

```json
{
  "timestamp": "2025-11-24T10:30:00Z",
  "operation": "sign_artifact",
  "artifact_id": "dfm_model_v1.2.3",
  "key_version": "v3",
  "key_id": "abc123def456",
  "user": "training_pipeline_sa",
  "environment": "production",
  "signature": "sha256:1234567890abcdef..."
}
```

### Log Retention

- **Active keys:** Retain logs indefinitely
- **Rotated keys:** Retain logs 2 years minimum
- **Revoked keys:** Retain logs 5 years minimum (compliance)

### Log Review

**Monthly Review Checklist:**
- [ ] Verify all signatures use current key version
- [ ] Check for unauthorized signing attempts
- [ ] Review failed verification attempts
- [ ] Confirm rotation schedule on track
- [ ] Audit key access patterns

---

## Security Checklist

### Development

- [ ] Keys gitignored (in `.gitignore`)
- [ ] Keys not committed to repo (verify with `git log --all -- '*.key'`)
- [ ] `.env` file gitignored
- [ ] File permissions set to 0600
- [ ] Test keys separate from production keys
- [ ] Key version tracked in environment variable

### Production

- [ ] Keys in secrets manager (not filesystem)
- [ ] Access controlled (IAM/RBAC)
- [ ] Audit logging enabled
- [ ] Rotation schedule documented and automated
- [ ] Emergency procedures documented and tested
- [ ] Key backup and recovery tested
- [ ] Separate keys per environment (dev/staging/prod)
- [ ] Incident response plan documented

### Before Model Deployment

- [ ] Model signed with current key version
- [ ] Signature verification tested
- [ ] Key version documented in model metadata
- [ ] Verification keys deployed to Zone 2
- [ ] Rollback plan tested

---

## Troubleshooting

### Q: Signature verification failing

**A:** Check key version mismatch

```bash
# Check what key was used to sign
python scripts/inspect_signature.py --artifact model.bundle

# Compare to verification keys
echo $SIGNING_KEY_VERSION

# If mismatch, either:
# 1. Add old key to verification keys (during rotation)
# 2. Re-sign artifact with current key
```

### Q: How to handle key compromise?

**A:** Follow Emergency Rotation procedure immediately

1. Revoke compromised key (remove from verification)
2. Generate replacement key
3. Re-sign all production artifacts
4. Audit all signatures made with compromised key
5. Document incident

### Q: Can I use the same key for dev and prod?

**A:** **NO.** Always use separate keys for different environments.

- `signing_key_dev_v1.key` for development
- `signing_key_staging_v1.key` for staging
- `signing_key_prod_v1.key` for production

### Q: How do I recover if I lose the signing key?

**A:** Cannot recover lost signing keys

1. Generate new key immediately
2. Re-sign all production artifacts
3. Update all environments
4. Review backup procedures to prevent future loss

### Q: What if I committed a key to git by mistake?

**A:** **Critical Security Incident**

1. Revoke key immediately (assume compromised)
2. Remove from all branches (`git filter-branch` or `BFG Repo-Cleaner`)
3. Force push (after team coordination)
4. Generate replacement key
5. Re-sign all production artifacts
6. Audit git history for other secrets

---

## References

### Related Documentation

- **Model Signing Implementation:** `models_src/utils/signing.py`
- **Artifact Bundle Format:** `models_src/utils/signing.py:SignedArtifact`
- **Zone Transfer Workflow:** `docs/5_PILLARS.md` (Multi-Zone Architecture)
- **Phase 5.10 Plan:** `docs/planning/PHASE_5_IMPLEMENTATION_PLAN.md` (Lines 701-783)

### Security Best Practices

- [NIST Digital Signature Standards](https://csrc.nist.gov/publications/detail/fips/186/5/final)
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html)
- [AWS Secrets Manager Best Practices](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html)

### Internal Contacts

- **Security Lead:** [Contact Info]
- **MLOps Team:** [Contact Info]
- **Incident Response:** [On-call Rotation]

---

**Document Revision History:**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-24 | System | Initial documentation (Phase 5.9.2 Quality Gap Resolution) |

---

**Review Schedule:** This document should be reviewed quarterly or after any security incident.


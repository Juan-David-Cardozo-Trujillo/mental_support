---
name: PIA Review
about: Privacy Impact Assessment checklist for new releases
title: 'PIA Review - v[VERSION]'
labels: ['pia-required']
assignees: ''
---

# Privacy Impact Assessment Checklist

Before every production deployment, this PIA must be completed and this issue closed.

## 1. Data Minimization & Exposure
- [ ] Data minimization verified (no unnecessary data collected)
- [ ] No PII in any API response except `/auth/me` (which only returns `role` and `profile_id`)
- [ ] IP addresses hashed before storage (no raw IPs in any table)

## 2. Zero-Knowledge Architecture
- [ ] `auth_service` and `platform_db` cross-database query audit passed (zero cross-DB joins found in code)
- [ ] Public share tokens verified: no user context, no session context embedded

## 3. Communication Privacy
- [ ] No plaintext message content in `chat_messages` table (verified by DB inspection)
- [ ] Message retention policy verified: non-flagged messages purged 24h after session close
- [ ] Flagged messages require dual-admin authorization to decrypt

## 4. Security Controls
- [ ] AES-256 encryption keys verified as stored in Secrets Manager (NOT in code or config files)
- [ ] OWASP ZAP scan completed: zero CVSS ≥ 7.0 vulnerabilities
- [ ] Anomalous login detection active and tested
- [ ] Rate limiting verified on all endpoint categories
- [ ] Backup encryption verified (RDS encryption at rest enabled)
- [ ] TLS 1.3 verified on all external connections
- [ ] Dependabot alerts reviewed and resolved

## 5. Session & Consent Management
- [ ] Consent gate verified: all endpoints blocked without consent record
- [ ] Session inactivity timeout (30 min) verified
- [ ] JWT stored in HttpOnly cookie only (not localStorage/sessionStorage)

## 6. Safety & Reporting
- [ ] Privacy & Safety Hub accessible from all authenticated screens
- [ ] Peer suspension auto-trigger at 3 reports verified

## Approval Sign-off
- Approved by: [ ] Privacy Officer
- Approved by: [ ] University DPO
- Approved by: [ ] Platform Admin Lead

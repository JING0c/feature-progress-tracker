"""Bindings for legacy/nonconvertible fixture plans without reference repositories.

Convertible workflow tests should use source_revision returned by /api/ledger/generate.
Tests opt in at each payload; request helpers must not silently add bindings,
because missing/stale binding attacks need to reach the server unchanged.
"""
import hashlib
import json


def legacy_no_reference_context(plan_revision):
    context = {'plan_revision': plan_revision, 'research_revision': None, 'source': {}}
    source_revision = hashlib.sha256(json.dumps(context, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {'plan_revision': plan_revision, 'source_revision': source_revision}

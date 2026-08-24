"""Execution interface: venue-agnostic order routing abstractions.

Live trading is Phase 15 and is NOT implemented. Every executor here is
hard-gated: constructing one in LIVE mode raises unless the config carries
explicit enablement plus the confirmation phrase — and even then, actual live
routing does not exist yet.
"""

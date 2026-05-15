"""Alerts package — pluggable rule evaluators + notification channels.

Layout:
    rules.py     — rule_type registry; one class per type
    channels.py  — channel_type registry; one class per type
    engine.py    — orchestration: pull enabled rules, eval, dedup, dispatch
"""

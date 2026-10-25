import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from routers.analytics import calculate_success_rate


def test_calculate_success_rate_returns_none_without_decided_applications():
    assert calculate_success_rate(approved_count=0, rejected_count=0) is None


def test_calculate_success_rate_uses_decided_applications_only():
    assert calculate_success_rate(approved_count=3, rejected_count=1) == 75.0
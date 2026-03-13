#!/usr/bin/env python3
"""
Test script to verify date parsing fix
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from core.utils import parse_graph_datetime

# Test cases with Microsoft Graph date formats
test_dates = [
    "2026-02-16T05:21:08.9749073+00:00",  # 7-digit microseconds
    "2026-02-16T05:21:08.974907+00:00",   # 6-digit microseconds
    "2026-02-16T05:21:08Z",               # No microseconds with Z
    "2026-02-16T05:21:08+00:00",          # No microseconds
    "2026-02-16T05:21:08.97+00:00",       # 2-digit microseconds
]

print("Testing date parsing fixes...")
print("=" * 50)

all_passed = True
for date_str in test_dates:
    try:
        result = parse_graph_datetime(date_str)
        print(f"✅ PASS: {date_str}")
        print(f"   Parsed to: {result}")
    except Exception as e:
        print(f"❌ FAIL: {date_str}")
        print(f"   Error: {e}")
        all_passed = False

print("=" * 50)
if all_passed:
    print("✅ All tests passed!")
    sys.exit(0)
else:
    print("❌ Some tests failed!")
    sys.exit(1)

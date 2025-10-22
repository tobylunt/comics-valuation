#!/usr/bin/env python3
"""
Test runner for the Comic Book Valuation System.
Runs all unit tests and displays results.
"""

import sys
import unittest
from pathlib import Path

def run_tests():
    """Run all tests and display results."""

    print("=" * 60)
    print("Comic Book Valuation System - Test Suite")
    print("=" * 60)
    print()

    # Discover and load all tests
    loader = unittest.TestLoader()
    suite = loader.discover(
        start_dir='.',
        pattern='tests.py',
        top_level_dir='.'
    )

    # Run tests with verbosity
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print()
    print("=" * 60)
    if result.wasSuccessful():
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed.")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
    print("=" * 60)

    # Return appropriate exit code
    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    sys.exit(run_tests())

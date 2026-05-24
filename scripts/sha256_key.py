#!/usr/bin/env python3
"""Print SHA-256 (hex) of a string for matching API_KEY_HASH / ADMIN_API_KEY_HASH.

Usage (plain key not stored in shell history):

  printf '%s' 'your-plain-admin-key' | python3 scripts/sha256_key.py

Or (history risk):

  python3 scripts/sha256_key.py 'your-plain-admin-key'

Compare output to ADMIN_API_KEY_HASH in .env; they must match.
"""
from __future__ import annotations

import hashlib
import sys


def main() -> None:
    if sys.stdin.isatty() and len(sys.argv) >= 2:
        raw = sys.argv[1]
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    elif len(sys.argv) >= 2:
        raw = sys.argv[1]
    else:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(2)
    hexout = hashlib.sha256(raw.encode()).hexdigest()
    print(hexout)


if __name__ == "__main__":
    main()

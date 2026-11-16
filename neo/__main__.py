"""
neo/__main__.py — Package entry point for `python -m neo`.
"""
import sys
from neo.cli import main

if __name__ == "__main__":
    sys.exit(main())

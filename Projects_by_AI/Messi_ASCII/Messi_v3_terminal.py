"""Messi in ASCII - version 3: right in the terminal, filling it; particles fall from above and build
him from his head down, then the stadium lights up around him. It fits itself to the terminal whenever
the terminal changes size; a bigger terminal or a smaller font gives more detail.

Run:  python Messi_v3_terminal.py                    (add --mp4 for a video, --png for a picture)
Needs messi_ascii.py and messi_art.npz in the same folder.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from messi_ascii import main  # noqa: E402

if __name__ == "__main__":
    try:
        main(version=3)
    except KeyboardInterrupt:
        pass

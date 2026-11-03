"""Messi in ASCII - version 1: in a window, small letters; particles fall from above and build him
from his head down, then the stadium lights up around him.

Run:  python Messi_v1_window_head_first.py          (add --mp4 for a video, --png for a picture)
Needs messi_ascii.py and messi_art.npz in the same folder.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from messi_ascii import main  # noqa: E402

if __name__ == "__main__":
    try:
        main(version=1)
    except KeyboardInterrupt:
        pass

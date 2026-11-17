"""Dira sovereign broadcast intelligence."""

import os
import sys

# Set before importing FAISS/Torch: their bundled arm64 OpenMP runtimes conflict.
if sys.platform == "darwin":
    for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ.setdefault(_name, "1")

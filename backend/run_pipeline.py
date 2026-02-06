#!/usr/bin/env python
"""
Single entrypoint for the whole pipeline:

- Run the training Jupyter notebook
- Build the inference bundle
- Optionally upload the bundle to S3

Usage examples:

  python run_pipeline.py
  python run_pipeline.py --no-training
  python run_pipeline.py --upload --s3-bucket your-s3-bucket-name
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from deadlock_backend.manage_pipeline import main

if __name__ == "__main__":
    main()


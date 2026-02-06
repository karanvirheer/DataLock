"""
Deadlock backend package.

Contains:
- config: shared paths and constants
- exports: logic to build a compact inference bundle
- deploy: logic to upload bundles to S3
- inference: runtime recommendation engine (for Lambda / local inference)
- manage_pipeline: orchestration CLI for training + export + upload
"""

from . import config

__all__ = ["config"]


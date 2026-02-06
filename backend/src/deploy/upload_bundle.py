"""
Upload a built inference bundle and static assets to S3.

S3 layout (single "current" bundle + assets):

    s3://<bucket>/<DEFAULT_BUNDLE_PREFIX>/bundle.zip
    s3://<bucket>/<DEFAULT_ASSET_PREFIX>/hero_assets.json
    s3://<bucket>/<DEFAULT_ASSET_PREFIX>/model_metadata.json
"""

from __future__ import annotations

from pathlib import Path

import boto3

from ..config import (
    EXPORTS_ROOT,
    DEFAULT_BUNDLE_PREFIX,
    DEFAULT_S3_BUCKET,
    DEFAULT_ASSET_PREFIX,
)


def upload_bundle_to_s3(
    bucket: str | None,
    model_version: str,
    prefix: str = DEFAULT_BUNDLE_PREFIX,
) -> tuple[str, str]:
    """
    Upload the bundle zip for the given model_version to S3.

    S3 layout (single latest bundle only):

        s3://<bucket>/<prefix>/bundle.zip
    """
    if bucket is None:
        bucket = DEFAULT_S3_BUCKET

    bundle_dir = EXPORTS_ROOT / model_version
    zip_path = bundle_dir / f"{model_version}.zip"

    if not zip_path.exists():
        raise FileNotFoundError(f"Bundle zip not found at {zip_path}")

    s3_client = boto3.client("s3")

    key = f"{prefix}/bundle.zip"

    print(f"Uploading {zip_path} -> s3://{bucket}/{key}")
    s3_client.upload_file(str(zip_path), bucket, key)

    print("Bundle upload complete.")
    return bucket, key


def upload_hero_assets(
    bucket: str | None,
    asset_path: Path,
    prefix: str = DEFAULT_ASSET_PREFIX,
) -> tuple[str, str]:
    """
    Upload hero_assets.json to:

        s3://<bucket>/<prefix>/hero_assets.json
    """
    if bucket is None:
        bucket = DEFAULT_S3_BUCKET

    asset_path = Path(asset_path)

    if not asset_path.exists():
        raise FileNotFoundError(f"hero_assets.json not found at {asset_path}")

    s3 = boto3.client("s3")
    key = f"{prefix}/hero_assets.json"

    print(f"Uploading {asset_path} -> s3://{bucket}/{key}")
    s3.upload_file(str(asset_path), bucket, key)

    print("Hero assets upload complete.")
    return bucket, key


def upload_model_metadata(
    bucket: str | None,
    asset_path: Path,
    prefix: str = DEFAULT_ASSET_PREFIX,
) -> tuple[str, str]:
    """
    Upload model_metadata.json to:

        s3://<bucket>/<prefix>/model_metadata.json
    """
    if bucket is None:
        bucket = DEFAULT_S3_BUCKET

    asset_path = Path(asset_path)

    if not asset_path.exists():
        raise FileNotFoundError(f"model_metadata.json not found at {asset_path}")

    s3 = boto3.client("s3")
    key = f"{prefix}/model_metadata.json"

    print(f"Uploading {asset_path} -> s3://{bucket}/{key}")
    s3.upload_file(str(asset_path), bucket, key)

    print("Model metadata upload complete.")
    return bucket, key


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Upload inference bundle to S3")
    parser.add_argument("model_version", help="e.g. minor_20251024")
    parser.add_argument(
        "--bucket",
        help="S3 bucket name (defaults to DEFAULT_S3_BUCKET)",
        default=None,
    )
    args = parser.parse_args()

    upload_bundle_to_s3(model_version=args.model_version, bucket=args.bucket)

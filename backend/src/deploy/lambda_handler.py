from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict

import boto3

from ..inference.inference_core import (
    load_bundle_from_dir,
    load_bundle_from_zip,
    InferenceBundle,
    recommend_build_from_bundle,
)

# Environment variables
BUNDLE_BUCKET = os.environ.get("BUNDLE_BUCKET", "")
BUNDLE_KEY = os.environ.get("BUNDLE_KEY", "bundles/bundle.zip")
API_KEY = os.environ.get("API_KEY")
MODEL_VERSION_ENV = os.environ.get("MODEL_VERSION")
HERO_ASSETS_KEY = os.environ.get("HERO_ASSETS_KEY", "assets/hero_assets.json")
MODEL_METADATA_KEY = os.environ.get("MODEL_METADATA_KEY", "assets/model_metadata.json")
ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "https://datalock.dev"
)

s3_client = boto3.client("s3")

_BUNDLE: InferenceBundle | None = None
_HERO_ASSETS: list[Dict[str, Any]] | None = None
_MODEL_METADATA: Dict[str, Any] | None = None


def _load_bundle() -> InferenceBundle:
    """
    Lazy-load the inference bundle from S3 into /tmp and cache it.

    Called on first invocation or after a container recycle.
    """
    global _BUNDLE

    if _BUNDLE is not None:
        return _BUNDLE

    if not BUNDLE_BUCKET:
        raise RuntimeError("BUNDLE_BUCKET env var is not set")

    tmp_zip = Path("/tmp/bundle.zip")
    extract_dir = Path("/tmp/bundle")

    # Clean previous extract
    if extract_dir.exists():
        shutil.rmtree(extract_dir)

    extract_dir.mkdir(parents=True, exist_ok=True)

    # Download bundle.zip from S3
    print(f"Downloading bundle from s3://{BUNDLE_BUCKET}/{BUNDLE_KEY} -> {tmp_zip}")
    s3_client.download_file(BUNDLE_BUCKET, BUNDLE_KEY, tmp_zip.as_posix())

    # Use helper from inference_core
    _BUNDLE = load_bundle_from_zip(tmp_zip, extract_dir)
    print(
        f"Loaded InferenceBundle. "
        f"Model version in bundle: {_BUNDLE.bundle_meta.get('model_version')}"
    )
    return _BUNDLE

def _load_hero_assets() -> list[Dict[str, Any]]:
    """
    Lazy-load hero_assets.json from S3 and cache it for warm invocations.

    Structure in S3:
      s3://<BUNDLE_BUCKET>/<HERO_ASSETS_KEY>
    """
    global _HERO_ASSETS

    if _HERO_ASSETS is not None:
        return _HERO_ASSETS

    if not BUNDLE_BUCKET:
        raise RuntimeError("BUNDLE_BUCKET env var is not set")

    print(f"Downloading hero assets from s3://{BUNDLE_BUCKET}/{HERO_ASSETS_KEY}")
    obj = s3_client.get_object(Bucket=BUNDLE_BUCKET, Key=HERO_ASSETS_KEY)
    data = obj["Body"].read()
    _HERO_ASSETS = json.loads(data)

    print(f"Loaded {len(_HERO_ASSETS)} hero assets.")
    return _HERO_ASSETS

def _load_model_metadata() -> Dict[str, Any]:
    """
    Lazy-load model_metadata.json from S3 and cache it for warm invocations.

    Structure in S3:
      s3://<BUNDLE_BUCKET>/<MODEL_METADATA_KEY>
    """
    global _MODEL_METADATA

    if _MODEL_METADATA is not None:
        return _MODEL_METADATA

    if not BUNDLE_BUCKET:
        raise RuntimeError("BUNDLE_BUCKET env var is not set")

    print(f"Downloading model metadata from s3://{BUNDLE_BUCKET}/{MODEL_METADATA_KEY}")
    obj = s3_client.get_object(Bucket=BUNDLE_BUCKET, Key=MODEL_METADATA_KEY)
    data = obj["Body"].read()
    _MODEL_METADATA = json.loads(data)

    print(f"Loaded {len(_MODEL_METADATA)} model metadata.")
    return _MODEL_METADATA


def _check_api_key(event: Dict[str, Any]) -> tuple[bool, str | None]:
    """
    If API_KEY env is set, enforce x-api-key header.
    """
    if not API_KEY:
        return True, None

    headers = event.get("headers") or {}
    provided = (
        headers.get("x-api-key")
        or headers.get("X-Api-Key")
        or headers.get("x-api_key")
    )

    if provided != API_KEY:
        return False, "Invalid or missing x-api-key"
    return True, None


def _parse_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Accepts either:
      - API Gateway HTTP API proxy event: { "body": "{...json...}" }
      - Direct test event: { hero_id: ..., lane_ally_id: ..., ... }
    """
    if "body" in event:
        body = event["body"]
        if isinstance(body, str):
            payload = json.loads(body)
        else:
            payload = body
    else:
        payload = event

    # Basic validation
    required = [
        "hero_id",
        "lane_ally_id",
        "team_other_ids",
        "lane_enemy_ids",
        "enemy_other_ids",
    ]
    missing = [k for k in required if k not in payload]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    return payload

def _get_cors_origin(event: Dict[str, Any] | None) -> str:
    default_origin = "https://datalock.dev"

    if not event:
        return default_origin

    headers = event.get("headers") or {}
    request_origin = headers.get("origin") or headers.get("Origin")

    if not request_origin:
        return default_origin

    allowed = {o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()}
    if request_origin in allowed:
        return request_origin

    return default_origin

def _response(
    status: int,
    body: Dict[str, Any],
    event: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    origin = _get_cors_origin(event)

    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Headers": "Content-Type,x-api-key",
            "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
        },
        "body": json.dumps(body),
    }

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda entrypoint.

    Expects draft payload either in event["body"] (HTTP API)
    or directly in event (for console testing).
    """
    try:
        ok, err = _check_api_key(event)
        if not ok:
            return _response(401, {"error": err or "Unauthorized"}, event)
        
        # HTTP API 
        http = (event.get("requestContext") or {}).get("http") or {}
        method = (http.get("method") or "").upper()
        path = http.get("path") or ""

        # Fallbacks for local / console testing without full HTTP API context
        if not method:
            method = (event.get("method") or "POST").upper()
        if not path:
            path = event.get("path") or "/recommend"

        if method == "OPTIONS":
            return _response(204, {}, event)

        if method == "GET" and path.endswith("/heroes"):
            heroes = _load_hero_assets()
            return _response(200, {"heroes": heroes}, event)

        if method == "GET" and path.endswith("/metadata"):
            model_metadata = _load_model_metadata()
            return _response(200, {"model_metadata": model_metadata}, event)

        payload = _parse_payload(event)

        bundle = _load_bundle()
        recs = recommend_build_from_bundle(bundle, payload)

        model_version = (
            MODEL_VERSION_ENV
            or bundle.bundle_meta.get("model_version")
            or bundle.training_meta.get("model_version")
        )

        return _response(
            200,
            {
                "model_version": model_version,
                "recommendations": recs,
            },
            event
        )

    except ValueError as ve:
        # User input error
        return _response(400, {"error": str(ve)}, event)

    except Exception as e:
        # Log full exception to CloudWatch for debugging
        print("ERROR during handler execution:", repr(e))
        return _response(500, {"error": "Internal server error"}, event)

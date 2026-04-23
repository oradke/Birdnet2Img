#!/usr/bin/env python3
import hashlib
import sseclient
import json
import requests
import socket
import time
from PIL import Image, ImageOps, ImageDraw, ImageFont
from pixoo1664 import Pixoo
import urllib.request
import urllib.parse
from urllib.error import HTTPError
import os
from typing import Any
from io import BytesIO

PIXOO_IP = os.getenv("PIXOO_IP", "192.168.2.230")
BIRDNET_GO_BASE_URL = os.getenv("BIRDNET_GO_BASE_URL", "http://192.168.2.135:8127")
SSE_CONNECT_TIMEOUT_SECONDS = float(os.getenv("SSE_CONNECT_TIMEOUT_SECONDS", "10"))
SSE_READ_TIMEOUT_SECONDS = float(os.getenv("SSE_READ_TIMEOUT_SECONDS", "65"))
SSE_RECONNECT_BASE_SECONDS = float(os.getenv("SSE_RECONNECT_BASE_SECONDS", "5"))
SSE_RECONNECT_MAX_SECONDS = float(os.getenv("SSE_RECONNECT_MAX_SECONDS", "60"))
SHOW_BIRD_NAME = os.getenv("SHOW_BIRD_NAME", "1").lower() in ("1", "true", "yes")
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_CACHE_DIR = os.getenv("IMAGE_CACHE_DIR", os.path.join(PROJECT_DIR, "cache", "images"))
IMAGE_CACHE_ENABLED = os.getenv("IMAGE_CACHE_ENABLED", "1").lower() not in ("0", "false", "no")
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".avif"}


def first_present(d: dict, keys, default=None):
    for key in keys:
        value = d.get(key)
        if value is not None and value != "":
            return value
    return default


def extract_detection_fields(detection: dict):
    common_name = first_present(detection, ["CommonName", "commonName", "common_name", "label"], "Unknown")
    scientific_name = first_present(detection, ["ScientificName", "scientificName", "scientific_name"], "Unknown")
    confidence = float(first_present(detection, ["Confidence", "confidence"], 0.0))
    detected_time = str(first_present(detection, ["Time", "time", "timestamp"], "Unknown"))

    source = first_present(detection, ["Source", "source"], "Unknown")
    if isinstance(source, dict):
        source = first_present(source, ["displayName", "safeString", "id"], "Unknown")
    source = str(source)

    image_url = None
    bird_image = detection.get("birdImage") or detection.get("BirdImage")
    if isinstance(bird_image, dict):
        image_url = first_present(bird_image, ["URL", "url", "thumbnailURL", "thumbnailUrl"])

    if not image_url:
        image_url = first_present(detection, ["imageUrl", "image_url", "thumbnailUrl", "thumbnail_url"])

    return {
        "common_name": common_name,
        "scientific_name": scientific_name,
        "confidence": confidence,
        "time": detected_time,
        "source": source,
        "image_url": image_url,
    }


def cache_path_for_url(url: str):
    parsed = urllib.parse.urlparse(url)
    extension = os.path.splitext(parsed.path)[1].lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        extension = ".img"

    file_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return os.path.join(IMAGE_CACHE_DIR, f"{file_hash}{extension}")


def cache_meta_path(cache_path: str):
    return f"{cache_path}.meta.json"


def load_image_from_bytes(raw: bytes):
    return Image.open(BytesIO(raw)).convert("RGB")


def load_cached_image(cache_path: str):
    with open(cache_path, "rb") as handle:
        raw = handle.read()
    return load_image_from_bytes(raw)


def save_cached_image(cache_path: str, raw: bytes):
    os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
    temp_path = f"{cache_path}.tmp"
    with open(temp_path, "wb") as handle:
        handle.write(raw)
    os.replace(temp_path, cache_path)


def load_cache_metadata(meta_path: str):
    if not os.path.exists(meta_path):
        return {}

    try:
        with open(meta_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass

    return {}


def save_cache_metadata(meta_path: str, source_url: str, etag: str = "", last_modified: str = ""):
    payload = {
        "url": source_url,
        "etag": etag,
        "last_modified": last_modified,
        "updated_at": int(time.time()),
    }

    temp_path = f"{meta_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    os.replace(temp_path, meta_path)


def fit_text_to_width(text: str, draw: ImageDraw.ImageDraw, font: Any, max_width: int):
    if not text:
        return ""

    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text

    suffix = "..."
    for end in range(len(text), 0, -1):
        candidate = text[:end].rstrip() + suffix
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            return candidate

    return suffix


def draw_name_overlay(img: Image.Image, bird_name: str):
    if not bird_name:
        return ImageOps.fit(img, (64, 64), method=Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (64, 64), (0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    max_text_width = canvas.width - 2
    text = fit_text_to_width(bird_name, draw, font, max_text_width)
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]

    # Reserve bottom rows for the label and fit/crop the bird image into the remaining area.
    strip_height = int(max(text_height + 2, 9))
    strip_height = int(min(strip_height, canvas.height - 1))
    image_height = int(canvas.height - strip_height)

    bird_area = ImageOps.fit(img, (canvas.width, image_height), method=Image.Resampling.LANCZOS)
    canvas.paste(bird_area, (0, 0))

    strip_top = image_height
    draw.rectangle([(0, strip_top), (canvas.width - 1, canvas.height - 1)], fill=(0, 0, 0))

    x = max(0, (canvas.width - text_width) // 2)
    y = strip_top + max(0, (strip_height - text_height) // 2)
    draw.text((x, y), text, fill=(255, 255, 255), font=font)
    return canvas

def image_from_url(url: str):
    cache_path = cache_path_for_url(url)
    meta_path = cache_meta_path(cache_path)
    metadata = load_cache_metadata(meta_path) if IMAGE_CACHE_ENABLED else {}

    if IMAGE_CACHE_ENABLED and os.path.exists(cache_path):
        try:
            load_cached_image(cache_path)
        except Exception as exc:
            print(f"⚠️ Cached image invalid, re-fetching: {exc}")
            try:
                os.remove(cache_path)
            except OSError:
                pass
            try:
                os.remove(meta_path)
            except OSError:
                pass

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://app.birdweather.com/",
        "Connection": "keep-alive",
    }

    if IMAGE_CACHE_ENABLED and os.path.exists(cache_path):
        etag = metadata.get("etag", "")
        last_modified = metadata.get("last_modified", "")
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

    last_error = None
    for attempt in range(3):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                raw = response.read()

            etag = response.headers.get("ETag", "")
            last_modified = response.headers.get("Last-Modified", "")

            if IMAGE_CACHE_ENABLED:
                try:
                    save_cached_image(cache_path, raw)
                    save_cache_metadata(meta_path, url, etag=etag, last_modified=last_modified)
                except OSError as exc:
                    print(f"⚠️ Could not save image cache: {exc}")

            return load_image_from_bytes(raw)
        except HTTPError as exc:
            if exc.code == 304 and IMAGE_CACHE_ENABLED and os.path.exists(cache_path):
                return load_cached_image(cache_path)

            last_error = exc
            if exc.code not in (403, 429):
                raise
            time.sleep(1.5 * (attempt + 1))

    if IMAGE_CACHE_ENABLED and os.path.exists(cache_path):
        try:
            print("⚠️ Falling back to cached image due to fetch errors")
            return load_cached_image(cache_path)
        except Exception:
            pass

    if last_error:
        raise last_error

    raise RuntimeError(f"Failed to fetch image URL: {url}")


def process_stream_event(event):
    if event.event == 'connected':
        data = json.loads(event.data)
        print(f"✅ Connected: {data['message']}")
        return

    if event.event == 'heartbeat':
        data = json.loads(event.data)
        print(f"💓 Heartbeat - {data['clients']} clients connected")
        return

    if event.event != 'detection':
        return

    detection = json.loads(event.data)
    parsed = extract_detection_fields(detection)

    print(f"🐦 {parsed['common_name']} detected!")
    print(f"   Scientific: {parsed['scientific_name']}")
    print(f"   Confidence: {parsed['confidence']:.2f}")
    print(f"   Time: {parsed['time']}")
    print(f"   Source: {parsed['source']}")
    print(f"   Image URL: {parsed['image_url']}")

    try:
        process_detection(parsed)
    except Exception as e:
        print(f"⚠️ Detection processing failed, continuing stream: {e}")


def stream_detections_once(url: str):
    with requests.get(
        url,
        stream=True,
        headers={'Accept': 'text/event-stream'},
        timeout=(SSE_CONNECT_TIMEOUT_SECONDS, SSE_READ_TIMEOUT_SECONDS),
    ) as response:
        response.raise_for_status()
        client = sseclient.SSEClient(response)  # type: ignore[arg-type]

        print(f"Connected to BirdNET-Go detection stream at {url}...")

        for event in client.events():
            process_stream_event(event)

    raise RuntimeError("BirdNET-Go SSE stream ended unexpectedly")


def listen_to_detections(base_url=BIRDNET_GO_BASE_URL):
    """
    Listen to BirdNET-Go detection stream and process detections.

    Requires: pip install sseclient-py requests
    """
    url = f"{base_url}/api/v2/detections/stream"
    reconnect_delay = SSE_RECONNECT_BASE_SECONDS

    while True:
        try:
            stream_detections_once(url)
            reconnect_delay = SSE_RECONNECT_BASE_SECONDS
        except KeyboardInterrupt:
            print("\n👋 Disconnecting from stream...")
            return
        except Exception as e:
            print(f"❌ BirdNET-Go stream error: {e}")
            print(f"↻ Reconnecting in {reconnect_delay:.1f}s...")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, SSE_RECONNECT_MAX_SECONDS)

def process_detection(detection):
    """
    Custom processing function for detections.
    Add your own logic here.
    """
    pixoo = Pixoo(PIXOO_IP)
    if not detection.get("image_url"):
        raise RuntimeError(f"No image URL in detection payload: {detection}")

    img = image_from_url(detection["image_url"])
    if SHOW_BIRD_NAME:
        img = draw_name_overlay(img, detection.get("common_name", ""))
    else:
        img = ImageOps.fit(img, (64, 64), method=Image.Resampling.LANCZOS)
    try:
        pixoo.send_image(img)  # type: ignore[arg-type]
    except (TimeoutError, socket.timeout) as exc:
        print(f"⚠️ Pixoo timeout while sending image: {exc}")
        return
    except OSError as exc:
        if "timed out" in str(exc).lower() or "timeout" in str(exc).lower():
            print(f"⚠️ Pixoo timeout while sending image: {exc}")
            return
        raise

    # Example: Save to file
    with open('detections.log', 'a') as f:
        f.write(f"{detection['time']},{detection['common_name']},{detection['confidence']}\n")

    # Example: Send notification for high confidence detections
    if detection['confidence'] > 0.9:
        send_notification(f"High confidence detection: {detection['common_name']}")

    # Example: Store in database
    # store_in_database(detection)

def send_notification(message):
    """Example notification function"""
    print(f"🔔 Notification: {message}")

if __name__ == "__main__":
    listen_to_detections()
#!/usr/bin/env python3
import sseclient
import json
import requests
import socket
import time
from PIL import Image, ImageOps
from pixoo1664 import Pixoo
import urllib.request
from urllib.error import HTTPError
import os
from io import BytesIO

PIXOO_IP = os.getenv("PIXOO_IP", "192.168.2.230")
BIRDNET_GO_BASE_URL = os.getenv("BIRDNET_GO_BASE_URL", "http://192.168.2.135:8127")
SSE_CONNECT_TIMEOUT_SECONDS = float(os.getenv("SSE_CONNECT_TIMEOUT_SECONDS", "10"))
SSE_READ_TIMEOUT_SECONDS = float(os.getenv("SSE_READ_TIMEOUT_SECONDS", "65"))
SSE_RECONNECT_BASE_SECONDS = float(os.getenv("SSE_RECONNECT_BASE_SECONDS", "5"))
SSE_RECONNECT_MAX_SECONDS = float(os.getenv("SSE_RECONNECT_MAX_SECONDS", "60"))


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

def image_from_url(url: str):
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

    last_error = None
    for attempt in range(3):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                raw = response.read()
            return Image.open(BytesIO(raw)).convert("RGB")
        except HTTPError as exc:
            last_error = exc
            if exc.code not in (403, 429):
                raise
            time.sleep(1.5 * (attempt + 1))

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
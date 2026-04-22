# BirdNET-Go to Pixoo Bridge

This project listens to the BirdNET-Go v2 Server-Sent Events detection stream, extracts the detected bird image from each event, resizes it for a Divoom Pixoo display, and sends the image to the Pixoo in near real time.

It is designed for simple home-lab and wildlife-monitoring setups where BirdNET-Go performs the bird recognition and a Pixoo acts as a small live display for the latest bird detection.

## What It Does

- Connects to the BirdNET-Go SSE endpoint at `/api/v2/detections/stream`
- Parses BirdNET-Go detection payloads, including the `birdImage.URL` field
- Downloads the bird image with browser-like headers to avoid common CDN `403` issues
- Crops and resizes the image to `64x64` for Pixoo
- Sends the image to a Pixoo device on the local network
- Logs detections to `detections.log`
- Continues running when individual detections fail
- Handles Pixoo send timeouts without crashing the stream listener

## Project Files

- `birdnet_sse.py`  
  Main bridge script that listens to BirdNET-Go SSE and updates Pixoo.

- `requirements.txt`  
  Python dependencies for the project.

- `run_birdnet_sse.sh`  
  Small launcher script for Linux and Raspberry Pi deployments.

- `birdnet-sse.service`  
  `systemd` service unit template for running the bridge as a background daemon.

- `birdnet-sse.env.example`  
  Example environment configuration for the daemon.

- `install_systemd_service.sh`  
  Raspberry Pi installer that copies the app to `/opt/pixoo`, creates or updates the virtual environment, installs dependencies, and enables the `systemd` service.

## Requirements

- Python 3.10+ recommended
- A reachable BirdNET-Go v2 instance
- A reachable Divoom Pixoo device
- Network access from the machine running the script to both BirdNET-Go and the Pixoo

## Python Dependencies

Dependencies are listed in `requirements.txt`:

- `Pillow`
- `requests`
- `sseclient-py`
- `pixoo1664`

For a local setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Configuration

The script uses environment variables:

- `PIXOO_IP`  
  IP address of the Pixoo device.  
  Default: `192.168.2.230`

- `BIRDNET_GO_BASE_URL`  
  Base URL of the BirdNET-Go instance.  
  Default: `http://192.168.2.135:8127`

Example:

```bash
export PIXOO_IP=192.168.1.50
export BIRDNET_GO_BASE_URL=http://192.168.1.20:8080
```

## Running Locally

Run the bridge directly:

```bash
python birdnet_sse.py
```

Or with the launcher script on Linux:

```bash
./run_birdnet_sse.sh
```

When running, the script will:

- connect to BirdNET-Go SSE
- wait for `detection` events
- extract bird metadata and image URL
- fetch the image
- resize it to `64x64`
- send it to Pixoo

## BirdNET-Go Event Format

This project is built around the BirdNET-Go v2 SSE detection stream. It supports payloads where fields use BirdNET-Go's capitalized keys, for example:

- `CommonName`
- `ScientificName`
- `Confidence`
- `Time`
- `Source.displayName`
- `birdImage.URL`

The image URL is primarily taken from:

- `birdImage.URL`

with a small set of fallback keys for compatibility.

## Error Handling

The script is intentionally defensive:

- image download retries on `403` and `429`
- Pixoo timeouts are logged and ignored
- per-detection failures do not stop the SSE listener
- malformed or incomplete detections are skipped through exception handling in the stream loop

## Raspberry Pi Daemon Setup

This repository includes a `systemd` deployment path for Raspberry Pi.

### Install prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-venv
```

### Install the service

From the project directory:

```bash
chmod +x install_systemd_service.sh run_birdnet_sse.sh
sudo ./install_systemd_service.sh
```

The installer will:

- copy project files to `/opt/pixoo`
- create `/opt/pixoo/.venv` if needed
- upgrade `pip`
- install or update dependencies from `requirements.txt`
- install `/etc/systemd/system/birdnet-sse.service`
- enable the service at boot
- restart the service immediately

### Configure runtime values

Edit:

```bash
sudo nano /etc/default/birdnet-sse
```

Example content:

```bash
PIXOO_IP=192.168.2.230
BIRDNET_GO_BASE_URL=http://192.168.2.135:8127
```

### Service management

Restart:

```bash
sudo systemctl restart birdnet-sse.service
```

Status:

```bash
sudo systemctl status birdnet-sse.service
```

Logs:

```bash
journalctl -u birdnet-sse.service -f
```

## Notes

- The current image pipeline uses crop-to-fill via `ImageOps.fit` so the Pixoo screen is fully covered.
- `detections.log` is local runtime output and is ignored by Git.
- `.venv/` is also ignored by Git.

## Future Improvements

Possible next steps:

- automatic SSE reconnect with backoff after BirdNET-Go restarts
- duplicate detection suppression based on event ID or timestamp
- overlaying species name or confidence on the Pixoo image
- caching remote bird images locally to reduce repeated downloads

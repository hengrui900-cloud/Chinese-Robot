# Raspberry Pi Network Camera Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the CH-RO web simulation connect to a Raspberry Pi Zero 2 W camera URL on the same LAN and use that stream for preview, capture, and dynamic recognition.

**Architecture:** Extend `vision.CameraManager` from local-only indexes to a unified camera source that can be either an integer index or a URL. Add Flask endpoints to register/test a network URL, then keep all preview and recognition requests on the backend so the browser and AI pipeline use the same frames.

**Tech Stack:** Python standard library, OpenCV `VideoCapture`, Flask backend, vanilla JavaScript frontend, Raspberry Pi OS camera stack notes.

---

### Task 1: Camera Source Tests

**Files:**
- Modify: `tests/test_camera_source.py`

- [ ] Add tests for URL source detection, local index preservation, and URL sanitization.
- [ ] Run `python -m unittest discover -s tests -p "test_camera_source.py" -v`; expected failure before implementation.

### Task 2: CameraManager URL Support

**Files:**
- Modify: `vision/camera.py`
- Modify: `vision/recognizer.py`

- [ ] Add `camera_source`, `source_label`, and URL detection helpers.
- [ ] Use `cv2.VideoCapture(url, CAP_FFMPEG/CAP_ANY)` for URL sources and retain local backend probing for integer sources.
- [ ] Make `BoardRecognizer` accept `camera_source` while retaining `camera_index` compatibility.

### Task 3: Flask Network Camera Flow

**Files:**
- Modify: `web_simulation/app.py`

- [ ] Add global `current_camera_source` and `current_network_camera_url`.
- [ ] Add `/api/network_camera/connect`, `/api/network_camera/status`, and `/api/network_camera/disconnect`.
- [ ] Update frame, capture, dynamic recognition, and camera status/start endpoints to accept `camera_source='network'` or current source.

### Task 4: Frontend Network Camera Flow

**Files:**
- Modify: `web_simulation/static/js/app.js`

- [ ] Change `connectNetworkCamera()` to call the backend endpoint.
- [ ] Make network preview use `/api/camera/frame?camera_source=network`.
- [ ] Make capture and dynamic recognition include network source when selected.
- [ ] Log backend status/error messages in the existing system log.

### Task 5: Raspberry Pi Zero 2 W Instructions

**Files:**
- Create: `docs/raspberry_pi_zero2w_camera.md`

- [ ] Document expected performance.
- [ ] Provide recommended RTSP MediaMTX setup and a simple MJPEG fallback.
- [ ] Provide the exact URL format to enter in the web UI.

### Task 6: Verification

**Files:**
- Read-only verification across changed files.

- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Run `python -m compileall vision web_simulation tests`.
- [ ] Run bundled Node `--check` on `web_simulation/static/js/app.js`.
- [ ] Smoke-test Flask endpoints with an invalid network URL and confirm graceful JSON failure.
- [ ] Restart Flask on port 5000.

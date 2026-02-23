import base64
import math
import os
import tempfile

import cv2


def _compute_frame_count(duration: float, max_frames: int = 20) -> int:
    """Decide how many frames to extract based on video duration.

    Uses a logarithmic curve so that:
      - A 1-second video  -> 6 frames
      - A 5-second video  -> 10 frames
      - A 30-second video -> 15 frames
      - A 5-minute video  -> 20 frames (capped)
      - A 60-minute video -> 20 frames (capped)

    This keeps Claude API cost roughly constant regardless of video length.
    """
    if duration <= 0:
        return 1
    # log2 curve: grows fast at first, then flattens
    count = int(4 + math.log2(1 + duration) * 2.4)
    return max(4, min(count, max_frames))


def _pick_timestamps(duration: float, n: int) -> list[float]:
    """Pick n evenly-spaced timestamps, always including start and end.

    For n=1, returns [0.0].
    For n=2, returns [0.0, duration - small_offset].
    For n>=3, returns first frame, evenly-spaced interior frames, last frame.
    """
    if n <= 1:
        return [0.0]

    # Slight offset from the very end to avoid a blank trailing frame
    end = max(0.0, duration - 0.1)

    if n == 2:
        return [0.0, end]

    # Interior frames evenly distributed between start and end
    step = end / (n - 1)
    return [round(i * step, 3) for i in range(n)]


async def extract_frames(
    video_bytes: bytes,
    max_frames: int = 10,
    target_max_dimension: int = 1024,
) -> list[dict]:
    """Extract key frames from video bytes for Claude vision analysis.

    Frame count adapts to video duration via a logarithmic curve so that
    short clips (2 s) and long videos (60 min) produce a similar number
    of frames (and therefore similar API cost).

    Returns a list of dicts, each containing:
        - "data": base64-encoded JPEG string
        - "media_type": "image/jpeg"
        - "timestamp": float (seconds into the video)
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".mp4", delete=False
        ) as tmp:
            tmp.write(video_bytes)
            tmp_path = tmp.name

        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            raise ValueError(
                "Could not open video file. "
                "Ensure the format is supported (mp4, avi, mov, mkv)."
            )

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0

        if duration <= 0:
            cap.release()
            raise ValueError("Could not determine video duration.")

        n_frames = _compute_frame_count(duration, max_frames)
        timestamps = _pick_timestamps(duration, n_frames)

        frames = []
        for ts in timestamps:
            cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
            ret, frame = cap.read()
            if not ret:
                continue

            # Resize so the longest edge fits within target_max_dimension
            h, w = frame.shape[:2]
            if max(h, w) > target_max_dimension:
                scale = target_max_dimension / max(h, w)
                new_w = int(w * scale)
                new_h = int(h * scale)
                frame = cv2.resize(
                    frame, (new_w, new_h), interpolation=cv2.INTER_AREA
                )

            # Encode as JPEG
            ok, buf = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85]
            )
            if not ok:
                continue

            frames.append(
                {
                    "data": base64.standard_b64encode(buf.tobytes()).decode(
                        "utf-8"
                    ),
                    "media_type": "image/jpeg",
                    "timestamp": ts,
                }
            )

        cap.release()

        if not frames:
            raise ValueError("Could not extract any frames from video.")

        return frames

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

import base64
import os
import tempfile

import cv2


async def extract_frames(
    video_bytes: bytes,
    max_frames: int = 10,
    interval_seconds: float = 2.0,
    target_max_dimension: int = 1024,
) -> list[dict]:
    """Extract key frames from video bytes for Claude vision analysis.

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

        # Distribute frames evenly across the video
        actual_interval = max(interval_seconds, duration / max_frames)
        timestamps = [
            i * actual_interval
            for i in range(max_frames)
            if i * actual_interval < duration
        ]

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

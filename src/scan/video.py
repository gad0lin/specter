"""
scan/video.py — Video-based space discovery.

Upload a video of a space → extract frames → NIM scans each →
builds a rich, multi-angle understanding of the environment.

Much better than a single photo:
- Discovers objects from multiple angles
- Builds spatial relationships across frames
- Identifies movement patterns (where people walk, gathering spots)
- Cross-references findings across frames for confidence

Usage:
    from src.scan.video import scan_video
    results = scan_video("shack15_walk.mp4", sample_fps=0.5)
"""
import os
import subprocess
import tempfile
from pathlib import Path


def extract_frames(video_path: str, fps: float = 0.5) -> list[bytes]:
    """
    Extract frames from video at given fps using ffmpeg.
    Returns list of JPEG bytes.
    fps=0.5 = one frame every 2 seconds (good for a slow walkthrough)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        out_pattern = os.path.join(tmpdir, "frame_%04d.jpg")
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vf", f"fps={fps},scale=1280:-1",
            "-q:v", "3",
            out_pattern,
            "-loglevel", "error",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr}")

        frames = []
        for img_path in sorted(Path(tmpdir).glob("frame_*.jpg")):
            frames.append(img_path.read_bytes())

        print(f"📽️  Extracted {len(frames)} frames from video")
        return frames


def scan_video(video_path: str, sample_fps: float = 0.5, max_frames: int = 8) -> list[dict]:
    """
    Scan a video of a space — extract frames, run NIM vision on each.

    Args:
        video_path:  Path to video file (.mp4, .mov, etc.)
        sample_fps:  Frames per second to sample (0.5 = 1 frame/2s)
        max_frames:  Max frames to analyze (controls cost + time)

    Returns:
        List of scan result dicts (same format as scan/vision.py)
    """
    from src.scan.vision import scan_frame

    frames = extract_frames(video_path, fps=sample_fps)

    # Limit frames
    if len(frames) > max_frames:
        # Sample evenly across the video
        step = len(frames) // max_frames
        frames = frames[::step][:max_frames]
        print(f"📽️  Sampling {len(frames)} frames evenly")

    results = []
    for i, frame_bytes in enumerate(frames):
        location = f"frame {i+1}/{len(frames)} — {_timestamp(i, sample_fps)}s into video"
        print(f"👁 Scanning {location}...")
        try:
            result = scan_frame(frame_bytes, location_hint=location)
            result["frame_index"] = i
            result["timestamp_approx"] = round(i / sample_fps)
            results.append(result)
        except Exception as e:
            print(f"⚠️  Frame {i} scan failed: {e}")

    print(f"✅ Scanned {len(results)} frames")
    return results


def _timestamp(frame_idx: int, fps: float) -> int:
    return round(frame_idx / fps)


def merge_scan_results(results: list[dict]) -> dict:
    """
    Merge multiple frame scans into one rich scene description.
    Deduplicates objects, combines interesting findings.
    """
    all_objects = []
    all_interesting = []
    all_text = []
    all_people = 0
    atmospheres = []
    room_types = []

    for r in results:
        all_objects.extend(r.get("objects", []))
        all_interesting.extend(r.get("interesting", []))
        all_text.extend(r.get("text_visible", []))
        all_people = max(all_people, r.get("people_count", 0))
        if r.get("atmosphere"):
            atmospheres.append(r["atmosphere"])
        if r.get("room_type"):
            room_types.append(r["room_type"])

    # Deduplicate
    def dedup(lst):
        seen = set()
        return [x for x in lst if x.lower() not in seen and not seen.add(x.lower())]

    return {
        "room_type": room_types[0] if room_types else "unknown",
        "atmosphere": ", ".join(set(atmospheres[:3])),
        "objects": dedup(all_objects)[:20],
        "text_visible": dedup(all_text)[:10],
        "interesting": dedup(all_interesting)[:8],
        "people_count": all_people,
        "frame_count": len(results),
        "source": "video",
    }

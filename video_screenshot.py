#!/usr/bin/env python
"""
Video Screenshot Extraction Module
Extracts screenshots from video files at specific timestamps
"""

import os
import cv2
from typing import List, Optional, Dict
import numpy as np


class VideoScreenshotExtractor:
    """Extract screenshots from video files"""

    def __init__(self, video_path: str):
        """Initialize with video file path

        Args:
            video_path: Path to the video file
        """
        self.video_path = video_path

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        self.video_capture = cv2.VideoCapture(video_path)

        if not self.video_capture.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        # Get video properties
        self.fps = self.video_capture.get(cv2.CAP_PROP_FPS)
        self.total_frames = int(self.video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration = self.total_frames / self.fps if self.fps > 0 else 0

        print(f"Video loaded: {video_path}")
        print(f"  FPS: {self.fps}")
        print(f"  Total frames: {self.total_frames}")
        print(f"  Duration: {self.duration:.2f} seconds")

    def extract_frame_at_time(self, time_seconds: float) -> Optional[np.ndarray]:
        """Extract a single frame at specific time

        Args:
            time_seconds: Time in seconds

        Returns:
            Frame as numpy array (BGR format) or None if failed
        """
        # Calculate frame number
        frame_number = int(time_seconds * self.fps)

        # Set video position to the frame
        self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

        # Read the frame
        success, frame = self.video_capture.read()

        if success:
            return frame
        else:
            print(f"Warning: Could not extract frame at {time_seconds}s")
            return None

    def extract_screenshots(
        self,
        timestamps: List[float],
        output_dir: str,
        filename_prefix: str = "screenshot",
        segment_indices: Optional[List[int]] = None
    ) -> List[str]:
        """Extract screenshots at multiple timestamps

        Args:
            timestamps: List of timestamps in seconds
            output_dir: Directory to save screenshots
            filename_prefix: Prefix for screenshot filenames
            segment_indices: Optional list of segment indices for naming

        Returns:
            List of saved file paths
        """
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        saved_files = []

        for i, timestamp in enumerate(timestamps):
            # Get frame
            frame = self.extract_frame_at_time(timestamp)

            if frame is None:
                continue

            # Generate filename
            if segment_indices and i < len(segment_indices):
                segment_idx = segment_indices[i]
                filename = f"{filename_prefix}_segment_{segment_idx:04d}.jpg"
            else:
                filename = f"{filename_prefix}_{i:04d}.jpg"

            output_path = os.path.join(output_dir, filename)

            # Save frame
            cv2.imwrite(output_path, frame)
            saved_files.append(output_path)

            print(f"  Saved: {filename} (at {timestamp:.2f}s)")

        return saved_files

    def extract_screenshots_from_srt_info(
        self,
        srt_timestamps: List[Dict],
        output_dir: str,
        filename_prefix: str = "screenshot"
    ) -> List[Dict]:
        """Extract screenshots based on SRT timestamp information

        Args:
            srt_timestamps: List of dicts with 'index', 'start_seconds', 'text'
            output_dir: Directory to save screenshots
            filename_prefix: Prefix for screenshot filenames

        Returns:
            List of dicts with screenshot info
        """
        results = []

        for timestamp_info in srt_timestamps:
            segment_index = timestamp_info['index']
            start_seconds = timestamp_info['start_seconds']
            text = timestamp_info.get('text', '')

            # Extract frame
            frame = self.extract_frame_at_time(start_seconds)

            if frame is None:
                continue

            # Generate filename
            filename = f"{filename_prefix}_segment_{segment_index:04d}.jpg"
            output_path = os.path.join(output_dir, filename)

            # Create output directory if needed
            os.makedirs(output_dir, exist_ok=True)

            # Save frame
            cv2.imwrite(output_path, frame)

            result = {
                'segment_index': segment_index,
                'timestamp': start_seconds,
                'file_path': output_path,
                'subtitle_text': text
            }
            results.append(result)

            print(f"  Saved: {filename} (segment {segment_index} at {start_seconds:.2f}s)")

        return results

    def close(self):
        """Release video capture resources"""
        if self.video_capture:
            self.video_capture.release()

    def __enter__(self):
        """Context manager support"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support"""
        self.close()


if __name__ == "__main__":
    # Test the extractor
    import sys

    if len(sys.argv) < 3:
        print("Usage: python video_screenshot.py <video_file> <output_dir> [timestamps...]")
        print("Example: python video_screenshot.py video.mp4 output/ 1.5 5.0 10.2")
        sys.exit(1)

    video_file = sys.argv[1]
    output_dir = sys.argv[2]
    timestamps = [float(t) for t in sys.argv[3:]] if len(sys.argv) > 3 else [1.0, 5.0, 10.0]

    with VideoScreenshotExtractor(video_file) as extractor:
        saved_files = extractor.extract_screenshots(timestamps, output_dir)
        print(f"\nExtracted {len(saved_files)} screenshots")

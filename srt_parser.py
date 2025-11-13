#!/usr/bin/env python
"""
SRT Parser Module
Parses SRT (SubRip) subtitle files and extracts timestamps
"""

import re
from typing import List, Dict


class SRTSegment:
    """Represents a single subtitle segment"""
    def __init__(self, index: int, start_time: str, end_time: str, text: str):
        self.index = index
        self.start_time = start_time
        self.end_time = end_time
        self.text = text
        self.start_seconds = self._time_to_seconds(start_time)
        self.end_seconds = self._time_to_seconds(end_time)

    @staticmethod
    def _time_to_seconds(time_str: str) -> float:
        """Convert SRT timestamp to seconds

        Args:
            time_str: Time string in format HH:MM:SS,mmm

        Returns:
            Time in seconds as float
        """
        # SRT format: HH:MM:SS,mmm
        time_str = time_str.replace(',', '.')
        parts = time_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])

        total_seconds = hours * 3600 + minutes * 60 + seconds
        return total_seconds

    def __repr__(self):
        return f"SRTSegment({self.index}, {self.start_time} --> {self.end_time}, '{self.text[:30]}...')"


class SRTParser:
    """Parser for SRT subtitle files"""

    @staticmethod
    def parse(srt_file_path: str) -> List[SRTSegment]:
        """Parse an SRT file and return list of segments

        Args:
            srt_file_path: Path to the SRT file

        Returns:
            List of SRTSegment objects
        """
        segments = []

        with open(srt_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Split by double newlines to separate segments
        raw_segments = re.split(r'\n\s*\n', content.strip())

        for raw_segment in raw_segments:
            lines = raw_segment.strip().split('\n')

            if len(lines) < 3:
                continue

            try:
                # First line: index
                index = int(lines[0].strip())

                # Second line: timestamps
                timestamp_line = lines[1].strip()
                timestamp_match = re.match(
                    r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})',
                    timestamp_line
                )

                if not timestamp_match:
                    continue

                start_time = timestamp_match.group(1)
                end_time = timestamp_match.group(2)

                # Remaining lines: text
                text = '\n'.join(lines[2:])

                segment = SRTSegment(index, start_time, end_time, text)
                segments.append(segment)

            except (ValueError, IndexError) as e:
                print(f"Warning: Could not parse segment: {e}")
                continue

        return segments

    @staticmethod
    def get_timestamps(srt_file_path: str) -> List[Dict]:
        """Get list of start timestamps from SRT file

        Args:
            srt_file_path: Path to the SRT file

        Returns:
            List of dictionaries with segment info
        """
        segments = SRTParser.parse(srt_file_path)

        timestamps = []
        for segment in segments:
            timestamps.append({
                'index': segment.index,
                'start_time': segment.start_time,
                'start_seconds': segment.start_seconds,
                'text': segment.text
            })

        return timestamps


if __name__ == "__main__":
    # Test the parser
    import sys

    if len(sys.argv) < 2:
        print("Usage: python srt_parser.py <srt_file>")
        sys.exit(1)

    srt_file = sys.argv[1]

    parser = SRTParser()
    segments = parser.parse(srt_file)

    print(f"Found {len(segments)} segments")
    for segment in segments[:5]:  # Show first 5
        print(segment)

#!/usr/bin/env python
"""
Video SRT Screenshot Generator

비디오 파일과 SRT 자막 파일을 업로드하면 각 타임스탬프의 시작 시간을 기준으로
비디오를 스크린샷 찍어서 구간 번호로 저장합니다.
나중에 그 사진을 보고 얼굴을 인식해서 화자 태깅을 할 수 있습니다.

Usage:
    python video_srt_screenshot.py <video_file> <srt_file> [output_dir]

Example:
    python video_srt_screenshot.py video.mp4 subtitles.srt screenshots/
"""

import os
import sys
import argparse
import json
from typing import List, Dict
from datetime import datetime

from srt_parser import SRTParser
from video_screenshot import VideoScreenshotExtractor


def generate_screenshots_from_video_and_srt(
    video_path: str,
    srt_path: str,
    output_dir: str = "screenshots",
    save_metadata: bool = True
) -> List[Dict]:
    """Generate screenshots from video at SRT subtitle timestamps

    Args:
        video_path: Path to video file
        srt_path: Path to SRT subtitle file
        output_dir: Output directory for screenshots
        save_metadata: Whether to save metadata JSON file

    Returns:
        List of dictionaries with screenshot information
    """
    print("=" * 80)
    print("Video SRT Screenshot Generator")
    print("=" * 80)
    print(f"Video file: {video_path}")
    print(f"SRT file: {srt_path}")
    print(f"Output directory: {output_dir}")
    print()

    # Validate input files
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"SRT file not found: {srt_path}")

    # Parse SRT file
    print("Parsing SRT file...")
    srt_timestamps = SRTParser.get_timestamps(srt_path)
    print(f"Found {len(srt_timestamps)} subtitle segments")
    print()

    # Extract screenshots
    print("Extracting screenshots from video...")
    with VideoScreenshotExtractor(video_path) as extractor:
        # Get base filename from video
        video_basename = os.path.splitext(os.path.basename(video_path))[0]

        results = extractor.extract_screenshots_from_srt_info(
            srt_timestamps,
            output_dir,
            filename_prefix=video_basename
        )

    print()
    print(f"Successfully extracted {len(results)} screenshots")

    # Save metadata
    if save_metadata:
        metadata_path = os.path.join(output_dir, f"{video_basename}_metadata.json")

        metadata = {
            'video_file': video_path,
            'srt_file': srt_path,
            'generated_at': datetime.now().isoformat(),
            'total_screenshots': len(results),
            'screenshots': results
        }

        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        print(f"Metadata saved to: {metadata_path}")

    print()
    print("=" * 80)
    print("Screenshot extraction completed!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("  1. Review the screenshots in the output directory")
    print("  2. Use face recognition on the screenshots for speaker tagging")
    print("  3. Associate detected faces with subtitle segments")
    print()

    return results


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='비디오와 SRT 자막 파일에서 각 구간의 스크린샷을 추출합니다.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # 기본 사용법
    python video_srt_screenshot.py video.mp4 subtitles.srt

    # 출력 디렉토리 지정
    python video_srt_screenshot.py video.mp4 subtitles.srt --output screenshots/

    # 메타데이터 저장 안함
    python video_srt_screenshot.py video.mp4 subtitles.srt --no-metadata

Output:
    - 각 자막 구간의 시작 시간에 스크린샷 생성
    - 파일명 형식: <video_name>_segment_<번호>.jpg
    - 메타데이터 JSON 파일 (선택사항)
        """
    )

    parser.add_argument(
        'video_file',
        help='비디오 파일 경로 (mp4, avi, mov 등)'
    )

    parser.add_argument(
        'srt_file',
        help='SRT 자막 파일 경로'
    )

    parser.add_argument(
        '-o', '--output',
        default='screenshots',
        help='스크린샷 출력 디렉토리 (기본값: screenshots)'
    )

    parser.add_argument(
        '--no-metadata',
        action='store_true',
        help='메타데이터 JSON 파일을 생성하지 않음'
    )

    args = parser.parse_args()

    try:
        results = generate_screenshots_from_video_and_srt(
            video_path=args.video_file,
            srt_path=args.srt_file,
            output_dir=args.output,
            save_metadata=not args.no_metadata
        )

        # Print summary
        print(f"Summary:")
        print(f"  Total segments processed: {len(results)}")
        print(f"  Output directory: {args.output}")

        if results:
            print(f"  First screenshot: {results[0]['file_path']}")
            print(f"  Last screenshot: {results[-1]['file_path']}")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

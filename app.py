#!/usr/bin/env python
"""
Video SRT Screenshot Generator - Web Interface
웹 인터페이스를 통해 비디오와 SRT 파일을 업로드하고 스크린샷을 ZIP으로 다운로드
"""

import streamlit as st
import os
import tempfile
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

from srt_parser import SRTParser
from video_screenshot import VideoScreenshotExtractor


def create_zip_file(screenshots_dir, output_zip_path):
    """Create ZIP file from screenshots directory

    Args:
        screenshots_dir: Directory containing screenshots
        output_zip_path: Path for output ZIP file

    Returns:
        Path to created ZIP file
    """
    with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(screenshots_dir):
            for file in sorted(files):
                if file.endswith('.jpg'):
                    file_path = os.path.join(root, file)
                    arcname = file  # Just use filename in ZIP
                    zipf.write(file_path, arcname)

    return output_zip_path


def process_video_and_srt(video_file, srt_file, progress_callback=None):
    """Process video and SRT files to extract screenshots

    Args:
        video_file: Uploaded video file object
        srt_file: Uploaded SRT file object
        progress_callback: Optional callback function for progress updates

    Returns:
        Tuple of (zip_file_path, num_screenshots, temp_dir)
    """
    # Create temporary directory for processing
    temp_dir = tempfile.mkdtemp()

    try:
        # Save uploaded files to temp directory
        video_path = os.path.join(temp_dir, "video" + Path(video_file.name).suffix)
        srt_path = os.path.join(temp_dir, "subtitles.srt")

        if progress_callback:
            progress_callback("비디오 파일 저장 중...", 0.1)

        with open(video_path, 'wb') as f:
            f.write(video_file.getbuffer())

        if progress_callback:
            progress_callback("SRT 파일 저장 중...", 0.2)

        with open(srt_path, 'wb') as f:
            f.write(srt_file.getbuffer())

        # Parse SRT file
        if progress_callback:
            progress_callback("SRT 파일 파싱 중...", 0.3)

        srt_timestamps = SRTParser.get_timestamps(srt_path)
        total_segments = len(srt_timestamps)

        # Create output directory for screenshots
        screenshots_dir = os.path.join(temp_dir, "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)

        # Extract screenshots
        if progress_callback:
            progress_callback(f"{total_segments}개 구간 스크린샷 추출 중...", 0.4)

        with VideoScreenshotExtractor(video_path) as extractor:
            for idx, timestamp_info in enumerate(srt_timestamps):
                segment_index = timestamp_info['index']
                start_seconds = timestamp_info['start_seconds']

                # Extract frame
                frame = extractor.extract_frame_at_time(start_seconds)

                if frame is not None:
                    # Save with simple numbering: 1.jpg, 2.jpg, etc.
                    filename = f"{segment_index}.jpg"
                    output_path = os.path.join(screenshots_dir, filename)

                    import cv2
                    cv2.imwrite(output_path, frame)

                # Update progress
                if progress_callback and idx % 5 == 0:
                    progress = 0.4 + (0.4 * (idx + 1) / total_segments)
                    progress_callback(f"스크린샷 추출 중... ({idx + 1}/{total_segments})", progress)

        # Create ZIP file
        if progress_callback:
            progress_callback("ZIP 파일 생성 중...", 0.9)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"screenshots_{timestamp}.zip"
        zip_path = os.path.join(temp_dir, zip_filename)

        create_zip_file(screenshots_dir, zip_path)

        if progress_callback:
            progress_callback("완료!", 1.0)

        # Count actual screenshots
        num_screenshots = len([f for f in os.listdir(screenshots_dir) if f.endswith('.jpg')])

        return zip_path, num_screenshots, temp_dir

    except Exception as e:
        # Clean up on error
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise e


def main():
    """Main Streamlit application"""

    # Page configuration
    st.set_page_config(
        page_title="비디오 스크린샷 추출기",
        page_icon="🎬",
        layout="wide"
    )

    # Title and description
    st.title("🎬 비디오 SRT 스크린샷 추출기")
    st.markdown("""
    비디오 파일과 SRT 자막 파일을 업로드하면 각 자막 구간의 시작 시간에 스크린샷을 자동으로 추출합니다.
    추출된 스크린샷은 ZIP 파일로 다운로드할 수 있습니다.
    """)

    st.divider()

    # Create two columns for file uploads
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📹 비디오 파일")
        video_file = st.file_uploader(
            "비디오 파일을 선택하세요",
            type=['mp4', 'avi', 'mov', 'mkv', 'flv', 'wmv'],
            help="지원 형식: MP4, AVI, MOV, MKV, FLV, WMV"
        )

        if video_file:
            st.success(f"✅ 업로드됨: {video_file.name}")
            st.info(f"파일 크기: {video_file.size / (1024*1024):.2f} MB")

    with col2:
        st.subheader("📝 SRT 자막 파일")
        srt_file = st.file_uploader(
            "SRT 파일을 선택하세요",
            type=['srt'],
            help="SubRip 형식의 자막 파일"
        )

        if srt_file:
            st.success(f"✅ 업로드됨: {srt_file.name}")
            # Preview SRT content
            srt_content = srt_file.getvalue().decode('utf-8')
            with st.expander("SRT 파일 미리보기"):
                st.text(srt_content[:500] + ("..." if len(srt_content) > 500 else ""))

    st.divider()

    # Process button
    if video_file and srt_file:
        col_center = st.columns([1, 2, 1])[1]

        with col_center:
            process_button = st.button(
                "🚀 스크린샷 추출 시작",
                type="primary",
                use_container_width=True
            )

        if process_button:
            # Progress tracking
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_progress(message, progress):
                status_text.text(message)
                progress_bar.progress(progress)

            try:
                # Process files
                with st.spinner("처리 중..."):
                    zip_path, num_screenshots, temp_dir = process_video_and_srt(
                        video_file,
                        srt_file,
                        progress_callback=update_progress
                    )

                # Success message
                st.success(f"✅ 성공적으로 {num_screenshots}개의 스크린샷을 추출했습니다!")

                # Download button
                with open(zip_path, 'rb') as f:
                    zip_data = f.read()

                col_download = st.columns([1, 2, 1])[1]
                with col_download:
                    st.download_button(
                        label="📦 ZIP 파일 다운로드",
                        data=zip_data,
                        file_name=os.path.basename(zip_path),
                        mime="application/zip",
                        type="primary",
                        use_container_width=True
                    )

                # Display info
                st.info(f"""
                **추출 정보:**
                - 총 스크린샷 개수: {num_screenshots}개
                - 파일명 형식: 1.jpg, 2.jpg, 3.jpg, ...
                - ZIP 파일 크기: {len(zip_data) / (1024*1024):.2f} MB
                """)

                # Clean up temp directory
                shutil.rmtree(temp_dir, ignore_errors=True)

            except Exception as e:
                st.error(f"❌ 오류 발생: {str(e)}")
                st.exception(e)

    else:
        st.info("👆 비디오 파일과 SRT 파일을 모두 업로드하세요.")

    # Footer
    st.divider()
    with st.expander("ℹ️ 사용 방법 및 정보"):
        st.markdown("""
        ### 사용 방법
        1. **비디오 파일** 업로드 (MP4, AVI, MOV 등)
        2. **SRT 자막 파일** 업로드
        3. **스크린샷 추출 시작** 버튼 클릭
        4. 처리 완료 후 **ZIP 파일 다운로드**

        ### 출력 형식
        - 스크린샷 파일명: `1.jpg`, `2.jpg`, `3.jpg`, ...
        - 각 숫자는 자막 구간 번호에 해당합니다
        - 모든 이미지는 ZIP 파일로 압축되어 제공됩니다

        ### 다음 단계
        - 추출된 스크린샷으로 얼굴 인식 수행
        - 화자 태깅 및 자막 매핑
        - 화자별 대화 분석

        ### 기술 정보
        - OpenCV를 사용한 비디오 프레임 추출
        - SRT 파일 파싱 및 타임스탬프 변환
        - 자동 ZIP 압축 및 다운로드
        """)


if __name__ == "__main__":
    main()

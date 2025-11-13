#!/bin/bash

# Video Screenshot Generator Web App Launcher
# 비디오 스크린샷 추출기 웹 앱 실행 스크립트

echo "=================================="
echo "비디오 스크린샷 추출기 웹 앱"
echo "=================================="
echo ""

# Check if streamlit is installed
if ! command -v streamlit &> /dev/null
then
    echo "⚠️  Streamlit이 설치되어 있지 않습니다."
    echo "다음 명령어로 설치하세요:"
    echo "  pip install streamlit>=1.28.0"
    echo ""
    exit 1
fi

# Check if required files exist
if [ ! -f "app.py" ]; then
    echo "❌ app.py 파일을 찾을 수 없습니다."
    exit 1
fi

if [ ! -f "srt_parser.py" ]; then
    echo "❌ srt_parser.py 파일을 찾을 수 없습니다."
    exit 1
fi

if [ ! -f "video_screenshot.py" ]; then
    echo "❌ video_screenshot.py 파일을 찾을 수 없습니다."
    exit 1
fi

echo "✅ 모든 필수 파일이 확인되었습니다."
echo ""
echo "🚀 웹 앱을 시작합니다..."
echo "브라우저가 자동으로 열립니다."
echo ""
echo "종료하려면 Ctrl+C를 누르세요."
echo ""

# Run streamlit app
streamlit run app.py

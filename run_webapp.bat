@echo off
REM Video Screenshot Generator Web App Launcher for Windows
REM 비디오 스크린샷 추출기 웹 앱 실행 스크립트 (Windows)

echo ==================================
echo 비디오 스크린샷 추출기 웹 앱
echo ==================================
echo.

REM Check if streamlit is installed
where streamlit >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ⚠️  Streamlit이 설치되어 있지 않습니다.
    echo 다음 명령어로 설치하세요:
    echo   pip install streamlit^>=1.28.0
    echo.
    exit /b 1
)

REM Check if required files exist
if not exist "app.py" (
    echo ❌ app.py 파일을 찾을 수 없습니다.
    exit /b 1
)

if not exist "srt_parser.py" (
    echo ❌ srt_parser.py 파일을 찾을 수 없습니다.
    exit /b 1
)

if not exist "video_screenshot.py" (
    echo ❌ video_screenshot.py 파일을 찾을 수 없습니다.
    exit /b 1
)

echo ✅ 모든 필수 파일이 확인되었습니다.
echo.
echo 🚀 웹 앱을 시작합니다...
echo 브라우저가 자동으로 열립니다.
echo.
echo 종료하려면 Ctrl+C를 누르세요.
echo.

REM Run streamlit app
streamlit run app.py

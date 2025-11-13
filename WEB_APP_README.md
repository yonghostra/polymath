# 비디오 스크린샷 추출 웹 앱

비디오와 SRT 자막 파일을 업로드하여 각 자막 구간의 스크린샷을 자동으로 추출하는 웹 인터페이스입니다.

![Web Interface](https://img.shields.io/badge/Framework-Streamlit-FF4B4B?style=for-the-badge&logo=streamlit)
![Python](https://img.shields.io/badge/Python-3.7+-3776AB?style=for-the-badge&logo=python)

## 🌟 주요 기능

- ✅ **간편한 파일 업로드**: 드래그 앤 드롭으로 비디오와 SRT 파일 업로드
- ✅ **실시간 진행률**: 처리 상태를 실시간으로 확인
- ✅ **자동 파일명 지정**: 1.jpg, 2.jpg, 3.jpg... 순서대로 자동 저장
- ✅ **ZIP 다운로드**: 모든 스크린샷을 ZIP 파일로 압축하여 다운로드
- ✅ **SRT 미리보기**: 업로드한 자막 파일 내용 확인
- ✅ **반응형 디자인**: 모든 화면 크기에 최적화

## 📦 설치

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

또는 개별 설치:

```bash
pip install streamlit>=1.28.0 opencv-python>=4.5.0
```

### 2. FFmpeg 설치 (필요시)

비디오 처리를 위해 FFmpeg가 필요할 수 있습니다:

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
[FFmpeg 공식 사이트](https://ffmpeg.org/download.html)에서 다운로드

## 🚀 실행 방법

### 로컬에서 실행

```bash
streamlit run app.py
```

실행 후 브라우저가 자동으로 열립니다. (기본 주소: `http://localhost:8501`)

### 포트 변경

```bash
streamlit run app.py --server.port 8080
```

### 원격 접속 허용

```bash
streamlit run app.py --server.address 0.0.0.0
```

## 💡 사용 방법

### 1단계: 파일 업로드

![Upload Step](https://via.placeholder.com/800x400?text=File+Upload+Step)

1. **비디오 파일 업로드**
   - 좌측 "비디오 파일" 영역에 비디오 파일을 드래그 앤 드롭
   - 또는 "Browse files" 버튼을 클릭하여 파일 선택
   - 지원 형식: MP4, AVI, MOV, MKV, FLV, WMV

2. **SRT 파일 업로드**
   - 우측 "SRT 자막 파일" 영역에 SRT 파일을 업로드
   - "SRT 파일 미리보기"를 클릭하여 내용 확인 가능

### 2단계: 처리 시작

![Process Step](https://via.placeholder.com/800x400?text=Processing+Step)

1. 두 파일이 모두 업로드되면 중앙에 "🚀 스크린샷 추출 시작" 버튼이 활성화됩니다
2. 버튼을 클릭하여 처리를 시작합니다
3. 진행률 바와 상태 메시지로 진행 상황을 확인할 수 있습니다

### 3단계: 다운로드

![Download Step](https://via.placeholder.com/800x400?text=Download+Step)

1. 처리가 완료되면 "📦 ZIP 파일 다운로드" 버튼이 나타납니다
2. 버튼을 클릭하여 스크린샷이 포함된 ZIP 파일을 다운로드합니다
3. ZIP 파일 내부에는 `1.jpg`, `2.jpg`, `3.jpg` 등의 파일이 포함되어 있습니다

## 📁 출력 파일 구조

다운로드한 ZIP 파일의 구조:

```
screenshots_20231113_120000.zip
├── 1.jpg    (첫 번째 자막 구간 스크린샷)
├── 2.jpg    (두 번째 자막 구간 스크린샷)
├── 3.jpg    (세 번째 자막 구간 스크린샷)
├── ...
└── N.jpg    (N번째 자막 구간 스크린샷)
```

- 각 파일명의 숫자는 SRT 파일의 자막 구간 번호와 일치합니다
- 모든 이미지는 JPEG 형식입니다
- 이미지는 자막 구간의 **시작 시간**에 캡처됩니다

## 🎯 사용 예시

### 예시 1: 인터뷰 영상 처리

```
입력:
- interview.mp4 (30분 분량 인터뷰 영상)
- interview.srt (150개 자막 구간)

출력:
- screenshots_20231113_143022.zip
  ├── 1.jpg ~ 150.jpg (150개 스크린샷)
```

### 예시 2: 강의 영상 처리

```
입력:
- lecture.mp4 (1시간 강의 영상)
- lecture.srt (300개 자막 구간)

출력:
- screenshots_20231113_150030.zip
  ├── 1.jpg ~ 300.jpg (300개 스크린샷)
```

## ⚙️ 설정 옵션

### Streamlit 설정 파일 생성

`.streamlit/config.toml` 파일을 생성하여 앱을 커스터마이징할 수 있습니다:

```toml
[theme]
primaryColor = "#FF4B4B"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
font = "sans serif"

[server]
maxUploadSize = 2000
maxMessageSize = 2000

[browser]
gatherUsageStats = false
```

### 업로드 파일 크기 제한 변경

기본값은 200MB입니다. 더 큰 파일을 처리하려면:

```bash
streamlit run app.py --server.maxUploadSize 2000
```

(2000MB = 2GB)

## 🔧 문제 해결

### 비디오 파일을 열 수 없음

**문제**: "Could not open video file" 오류

**해결책**:
1. FFmpeg가 설치되어 있는지 확인
2. 비디오 파일이 손상되지 않았는지 확인
3. 지원되는 비디오 형식인지 확인

### 메모리 부족 오류

**문제**: 큰 비디오 파일 처리 시 메모리 부족

**해결책**:
- 더 작은 비디오 파일로 테스트
- 서버 메모리 증가
- 비디오 해상도를 낮춤

### 업로드 실패

**문제**: 파일 업로드가 실패함

**해결책**:
```bash
# 업로드 크기 제한 증가
streamlit run app.py --server.maxUploadSize 2000
```

### 포트 사용 중 오류

**문제**: "Address already in use"

**해결책**:
```bash
# 다른 포트 사용
streamlit run app.py --server.port 8502
```

## 📊 성능

| 비디오 길이 | 자막 구간 수 | 처리 시간 (예상) |
|-------------|--------------|------------------|
| 5분         | 50개         | ~10초            |
| 30분        | 150개        | ~30초            |
| 1시간       | 300개        | ~1분             |
| 2시간       | 600개        | ~2분             |

*처리 시간은 하드웨어 성능에 따라 달라질 수 있습니다.*

## 🌐 배포

### Streamlit Cloud에 배포

1. GitHub 저장소에 코드 푸시
2. [Streamlit Cloud](https://streamlit.io/cloud)에 접속
3. "New app" 클릭
4. 저장소 및 파일 선택 (`app.py`)
5. 배포 완료!

### Docker로 배포

`Dockerfile`:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0"]
```

빌드 및 실행:

```bash
docker build -t video-screenshot-app .
docker run -p 8501:8501 video-screenshot-app
```

## 🔐 보안 고려사항

- 업로드된 파일은 임시 디렉토리에 저장되며 처리 후 자동 삭제됩니다
- 민감한 콘텐츠가 포함된 비디오는 로컬에서만 처리하는 것을 권장합니다
- 프로덕션 환경에서는 파일 크기 제한과 사용자 인증을 고려하세요

## 📝 라이센스

이 프로젝트는 Polymath 프로젝트의 일부이며 MIT 라이센스를 따릅니다.

## 🤝 기여

버그 리포트나 기능 제안은 GitHub Issues를 통해 제출해주세요.

## 📞 지원

문제가 발생하면 다음을 확인하세요:
1. [VIDEO_SCREENSHOT_README.md](VIDEO_SCREENSHOT_README.md) - 커맨드라인 도구 문서
2. GitHub Issues
3. Streamlit 공식 문서

---

**즐거운 스크린샷 추출 되세요! 🎬✨**

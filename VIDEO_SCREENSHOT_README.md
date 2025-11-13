# 비디오 SRT 스크린샷 생성기

비디오 파일과 SRT 자막 파일에서 각 자막 구간의 시작 시간에 스크린샷을 자동으로 추출하는 도구입니다.

## 기능

- **SRT 파일 파싱**: SRT (SubRip) 자막 파일을 파싱하여 타임스탬프 정보 추출
- **자동 스크린샷 추출**: 각 자막 구간의 시작 시간에 비디오에서 프레임 캡처
- **구조화된 파일명**: `<비디오명>_segment_<번호>.jpg` 형식으로 저장
- **메타데이터 생성**: 추출된 스크린샷 정보를 JSON 파일로 저장
- **화자 태깅 준비**: 추출된 스크린샷으로 얼굴 인식 및 화자 태깅 가능

## 설치

필요한 패키지를 설치합니다:

```bash
pip install opencv-python>=4.5.0
```

또는 전체 의존성 설치:

```bash
pip install -r requirements.txt
```

## 사용법

### 기본 사용법

```bash
python video_srt_screenshot.py <비디오_파일> <SRT_파일>
```

**예시:**
```bash
python video_srt_screenshot.py interview.mp4 interview.srt
```

### 출력 디렉토리 지정

```bash
python video_srt_screenshot.py interview.mp4 interview.srt --output my_screenshots/
```

### 메타데이터 저장 비활성화

```bash
python video_srt_screenshot.py interview.mp4 interview.srt --no-metadata
```

### 도움말

```bash
python video_srt_screenshot.py --help
```

## 출력 파일

### 스크린샷 파일
- **형식**: JPEG 이미지
- **파일명**: `<비디오명>_segment_<구간번호>.jpg`
- **예시**:
  - `interview_segment_0001.jpg`
  - `interview_segment_0002.jpg`
  - `interview_segment_0003.jpg`

### 메타데이터 파일
- **형식**: JSON
- **파일명**: `<비디오명>_metadata.json`
- **내용**:
  ```json
  {
    "video_file": "interview.mp4",
    "srt_file": "interview.srt",
    "generated_at": "2025-11-13T12:00:00",
    "total_screenshots": 100,
    "screenshots": [
      {
        "segment_index": 1,
        "timestamp": 0.5,
        "file_path": "screenshots/interview_segment_0001.jpg",
        "subtitle_text": "안녕하세요"
      },
      ...
    ]
  }
  ```

## 모듈 설명

### 1. `srt_parser.py`
SRT 자막 파일 파싱 모듈

**주요 클래스:**
- `SRTSegment`: 개별 자막 구간 표현
- `SRTParser`: SRT 파일 파싱 및 타임스탬프 추출

**사용 예시:**
```python
from srt_parser import SRTParser

# SRT 파일 파싱
segments = SRTParser.parse('subtitles.srt')

# 타임스탬프 정보 추출
timestamps = SRTParser.get_timestamps('subtitles.srt')
for ts in timestamps:
    print(f"Segment {ts['index']}: {ts['start_seconds']}s - {ts['text']}")
```

### 2. `video_screenshot.py`
비디오 스크린샷 추출 모듈

**주요 클래스:**
- `VideoScreenshotExtractor`: 비디오에서 특정 시간의 프레임 추출

**사용 예시:**
```python
from video_screenshot import VideoScreenshotExtractor

# 비디오 열기
with VideoScreenshotExtractor('video.mp4') as extractor:
    # 특정 시간에 스크린샷 추출
    timestamps = [1.5, 5.0, 10.2]
    extractor.extract_screenshots(timestamps, 'output/')
```

### 3. `video_srt_screenshot.py`
메인 스크립트 - 비디오와 SRT 파일을 통합 처리

**사용 예시:**
```python
from video_srt_screenshot import generate_screenshots_from_video_and_srt

results = generate_screenshots_from_video_and_srt(
    video_path='interview.mp4',
    srt_path='interview.srt',
    output_dir='screenshots/',
    save_metadata=True
)

print(f"추출된 스크린샷: {len(results)}개")
```

## 화자 태깅 워크플로우

이 도구로 추출한 스크린샷을 사용하여 화자를 태깅하는 워크플로우:

### 1단계: 스크린샷 추출
```bash
python video_srt_screenshot.py interview.mp4 interview.srt
```

### 2단계: 얼굴 인식 (별도 도구 필요)
추출된 스크린샷에서 얼굴을 인식합니다. 예시 코드:

```python
import cv2
import json

# 얼굴 검출기 초기화
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
)

# 메타데이터 로드
with open('screenshots/interview_metadata.json', 'r') as f:
    metadata = json.load(f)

# 각 스크린샷에서 얼굴 검출
for screenshot in metadata['screenshots']:
    image_path = screenshot['file_path']
    image = cv2.imread(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 얼굴 검출
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)

    print(f"Segment {screenshot['segment_index']}: {len(faces)} 얼굴 검출")
```

### 3단계: 화자 식별 및 태깅
- 검출된 얼굴을 얼굴 인식 모델로 식별
- 자막 구간과 화자를 매핑
- 자막 파일에 화자 정보 추가

### 추천 도구
- **얼굴 검출**: OpenCV, dlib, MTCNN
- **얼굴 인식**: face_recognition, DeepFace, InsightFace
- **화자 분리 (음성)**: pyannote.audio

## SRT 파일 형식

SRT (SubRip) 파일 형식 예시:

```
1
00:00:00,500 --> 00:00:02,000
안녕하세요

2
00:00:02,500 --> 00:00:05,000
반갑습니다

3
00:00:05,500 --> 00:00:08,000
오늘은 날씨가 좋네요
```

각 구간은 다음으로 구성됩니다:
1. 구간 번호
2. 타임스탬프 (시작 --> 종료)
3. 자막 텍스트
4. 빈 줄

## 지원 비디오 형식

OpenCV가 지원하는 모든 비디오 형식:
- MP4
- AVI
- MOV
- MKV
- FLV
- WMV
- 기타 (FFmpeg 지원 형식)

## 문제 해결

### OpenCV 설치 오류
```bash
pip uninstall opencv-python
pip install opencv-python-headless
```

### 비디오 파일을 열 수 없음
- FFmpeg가 설치되어 있는지 확인
- 비디오 파일 경로와 형식이 올바른지 확인

### 메모리 부족
큰 비디오 파일의 경우 프레임을 하나씩 처리하므로 메모리 효율적입니다.

## 라이센스

이 프로젝트는 Polymath 프로젝트의 일부입니다. MIT 라이센스를 따릅니다.

## 기여

버그 리포트나 기능 제안은 GitHub Issues를 통해 제출해주세요.

## 다음 단계

1. ✅ 비디오와 SRT 파일에서 스크린샷 추출
2. 🔜 얼굴 인식 통합
3. 🔜 자동 화자 태깅
4. 🔜 화자별 자막 분리
5. 🔜 대화 분석 및 시각화

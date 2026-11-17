# 숏폼 조립: `tools/shortform.py` (ffmpeg 대체 경로)

HyperFrames(`guides/make/shortform-hyperframes.md`)를 쓸 수 없을 때(Node 22+·크롬이 안 될 때)만 연다. 파이썬과 ffmpeg만 있으면 된다. 움직임은 단순하다(확대·전환·자막 상자).

1. `BASE + tools/shortform.py`(0.2.0)를 받는다. 예시 장면표: `BASE + examples/shortform-scenes-sample.json`.
2. 장면표를 JSON으로 쓴다. 템플릿 JSON과 키 설명은 `guides/make/shortform-scenes.md`. 핵심만:
   - 맨 위: `layout`(`info` 정보형 = 위아래 검은 띠 + 가운데 사진 / `full` = 사진이 화면 전체), `theme`(`info` 검정+노랑 / `warm` 크림·갈색), `fixed_title`(위 띠 고정 제목), `caption_size` 66(64 아래로 내리지 않는다), `title_size` 76, `caption_style`(`box`/`outline`, 기본은 info=box·full=outline), `brand`(훅 카드 위 작은 꼬리표). 색은 아래 '같은 브랜드 팔레트'대로 프로필 '우리 가게 색'을 `colors`로 넘긴다. 테마 기본값(info 검정+노랑, warm 크림·갈색)은 프로필 색이 없을 때만 쓴다.
   - **같은 브랜드 팔레트**(카드뉴스와 맞추기): 카드뉴스 `brand.colors`가 `{main, accent, bg, text, deep}`이면 숏폼은 `"colors": {"bg": deep, "fg": "#FFFFFF", "accent": accent, "cards": [[bg, text, accent], [main, "#FFFFFF", accent], [deep, "#FFFFFF", accent]], "box": "deep값@0.8"}`. 카드 표지 제목이 명조(고운바탕 등)면 그 글꼴 파일을 `"font"`로 넘긴다(`cardnews.py fonts`로 받은 파일 경로). 만든 뒤 `frames --at 1`로 뽑은 첫 장면을 카드 표지 그림과 나란히 놓고 색·글씨·훅 문구가 같은지 본다.
   - 장면: `photo` 또는 `clip`, `duration`, `caption`(아래 자막), `title`, `hook`, `fit`, `zoom`, `transition`. 사진이 없는 장면은 **글자 카드**(색 면 + 큰 글자)가 된다. 생성 그림은 `photo`에 경로를 넣는다(사진 장면으로 셈).
   - `title`은 장면 종류에 따라 다르다: 사진·영상 장면에선 강조색 상자 **꼬리표**(시각·항목 이름, 짧게), 글자 카드에선 **큰 글자 본문**.
   - `*이렇게*` 별표로 감싼 말은 강조색. 한 화면에 한 곳만.
   - 목소리(사장님 또는 AI) 하나를 깔려면 `"music": {"path": "voice.m4a", "volume": 1.0}`. 녹음 길이를 영상 길이에 맞춘다(짧으면 반복된다).
3. 점검: `python3 shortform.py check scenes.json` → 길이·자막 글자 수·파일·훅을 본다. 자막·제목에 `[직접 입력: …]` 빈칸이 남아 있으면 '고칠 것'으로 막는다(채우거나 지운다).
4. 조립: `python3 shortform.py build scenes.json -o out.mp4`. 사진·클립 장면이 하나도 없으면 '사진 없는 시험본' 경고가 나오고 파일명 뒤에 `_draft`가 붙는다(`--no-draft-suffix`로 끔). 시험본은 올리지 않고, 사장님 사진·영상을 받아 다시 만든다.
5. 눈으로 확인: `python3 shortform.py frames out.mp4 --scenes scenes.json --sheet sheet.png` → 장면마다 1장씩 이어 붙인 `sheet.png`를 직접 열어 글자 크기·위치·가독성을 본다. 안전 영역이 걱정되면 `--guide`를 붙여 한 번 더 조립해 빨간 선을 본다(이 파일은 올리지 않는다).
6. ffmpeg가 없으면 스크립트가 설치 방법을 알려 주고 멈춘다. 설치가 어려우면 아래 대체 경로로 간다.


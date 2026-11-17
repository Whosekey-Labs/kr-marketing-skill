# 숏폼 조립: HyperFrames (Node·크롬이 있을 때)

`guides/make/shortform.md` 6절에서 연다. HyperFrames는 HTML 화면을 한 프레임씩 찍어 mp4로 만드는 도구다(무료, 내 컴퓨터에서 렌더). 키네틱 글자·자막 강조·밀어 넘기기 같은 움직임을 템플릿으로 바로 쓴다. 이 맥에서 22초 숏폼 한 편이 **12~18초**에 렌더됐다(`tests/runs/r16-hyperframes/notes.md`).

**어느 길로 갈지(처음 한 번 확인하고 기억한다. 두 렌더러는 같은 장면표를 읽으니 길이 바뀌어도 장면표는 그대로다)**
1. 아래 0)의 확인이 모두 되면 → **HyperFrames**(이 파일).
2. Node 22+나 크롬이 안 되지만 파이썬·ffmpeg는 되면 → `tools/shortform.py`(`guides/make/shortform-ffmpeg.md`).
3. 둘 다 안 되면 → 장면표 + 캡컷 안내(`guides/make/shortform.md` 6절 '대체 경로').
4. 피클 같은 사장님용 환경에 Node·크롬이 있는지는 짐작하지 않는다. 아래 0)을 그 자리에서 돌려 본다(실기 시험에서 확인 예정).

## 0) 처음 쓸 때: 설치·확인 (명령 4줄)

```sh
node -v                                   # v22 이상이어야 함. 아니면 https://nodejs.org LTS 설치
ffmpeg -version | head -1                 # 없으면 맥: brew install ffmpeg / 윈도우: winget install Gyan.FFmpeg
npx --yes hyperframes --version           # 처음엔 내려받느라 몇 초 걸림
npx --yes hyperframes browser ensure      # 렌더용 크롬(헤드리스)을 찾거나 받음. "Ready to render"가 나오면 끝
```

- 하나라도 실패하면 고치려고 오래 붙잡지 않는다. 사장님 컴퓨터에 설치를 부탁해야 하면 대체 경로(2·3번)로 먼저 결과를 드리고 설치는 다음에 제안한다.
- 에이전트 셸이 `npx … --옵션`을 다른 명령으로 바꿔 버리면(예: "Missing script: hyperframes") `node ~/.npm/_npx/*/node_modules/hyperframes/bin/hyperframes.mjs <명령>`으로 직접 부른다.
- 렌더할 때 인터넷이 필요하다(GSAP 스크립트를 CDN에서 읽음).

## 1) 프로젝트 만들기

```sh
sh templates/shortform-hyperframes/new.sh <폴더> <템플릿>   # 원격이면 BASE + templates/shortform-hyperframes/ 의 파일을 받아서
```

`new.sh`가 하는 일: 세로 1080×1920 빈 프로젝트(`hyperframes init --resolution portrait`) → 템플릿을 `index.html`로 복사 → Pretendard 글꼴 4개를 `assets/fonts/`에 넣기 → 크롬 확인. `init`이 만드는 `CLAUDE.md`는 지운다(지침 파일은 `AGENTS.md` 하나).

## 2) 템플릿 4개 (가게용)

| 템플릿 | 맞는 카드(`guides/styles/shortform.md`) | 구성 | 재료 |
|---|---|---|---|
| `time-routine.html` 시간 자막 루틴 | G7 오늘 하루, G1 만드는 과정 | 훅(0프레임부터 큰 글자) → 시각 꼬리표 장면 4개(`11:00 첫 판`) + 진행 막대 → 가격 카운트업·행동 | 사진·그림 5장 |
| `info-card.html` 정보 카드 | G5 정보, F06 N가지 | 훅 → 번호 카드 4장(그림 또는 큰 숫자) + 위 고정 제목 → 저장용 요약 체크·행동 | 그림 3~4장(없으면 숫자 카드) |
| `showcase.html` 쇼케이스 | G3 상품 한 컷, G4 가게 구경 | 사진 화면 전체 + 위 고정 제목 + 외곽선 큰 자막 4장면 → 가게 이름·행동 | 세로 사진 4장 |
| `before-after.html` 전후 | G2 전후 | 전 사진 + 훅 → 닦아 내듯 후 사진 → 기간·금액·상담 | 같은 각도 전·후 2장 |

- 그림·사진은 `assets/art/`·`assets/photo/`에 넣고 경로만 바꾼다. 생성 그림은 바탕을 뺀 투명 PNG가 카드 위에서 깔끔하다.
- `[대괄호]`는 사장님 자료로만 채운다. 없는 장면은 지우고 뒤 장면의 `data-start`와 맨 위 `data-duration`을 당긴다(지어내지 않는다).
- 색은 맨 위 `:root`의 `--bg`·`--main`·`--accent`(카드뉴스 `brand.colors`와 같은 값). 2안(기존 색 살린 안)은 `--accent`만 바꾼다.

## 3) 장면표 → HyperFrames 매핑

장면표(`guides/make/shortform-scenes.md`의 JSON)를 그대로 옮긴다. 한 장면 = `class="clip"` 상자 하나.

| 장면표 키 | HyperFrames에서 |
|---|---|
| `duration`, 순서 | 장면 상자의 `data-start`(앞 장면 끝 − 0.2초, 겹쳐서 밀어 넘김), `data-duration`. 맨 위 `#root`의 `data-duration` = 전체 길이 |
| `hook` | 첫 장면 큰 글자. **0프레임(썸네일)에 다 보이게** 두고 단어마다 튕김 + 강조 밑줄(`.hl`, `--hl` 0→1) |
| `fixed_title` | `#fixed` 상자 **1줄**이 기본(정보형만 흰 상자 + 강조색 상자 2줄), 훅 다음부터 끝까지 |
| `caption` | `.cap` 큰 자막(70~76px, 두 줄까지). `*강조*` → `<span class="hl">` 또는 `<span class="y">` |
| `title`(꼬리표) | `.chip`(짧은 이름표) 또는 `.time`(시각 `11:00` + 할 일) |
| `photo` / `clip` | `<img>` 또는 `<video muted>`(원본 소리 끔이 기본. `keep_audio`일 때만 `data-has-audio="true"`). `zoom` → 이미지 `scale` 1.0↔1.14 천천히 |
| `transition` | 들어올 때 오른쪽에서 밀려 옴, 나갈 때 왼쪽으로(registry `page-slide` 방식). 컷은 겹침 0초 |
| 숫자(가격·횟수) | 카운트업(registry `count-up` 방식): 값은 타임라인 시간으로 계산(`onUpdate`), 착지 때 한 번 맥박 |
| 글자 카드(`bg`/`fg`) | 색 면 장면(`#s5` 같은 상자)에 큰 글자 |
| `music` | `<audio id="voice" src="assets/voice.m4a" data-volume="1">`. 원본엔 음악 넣지 않음(`shortform.md` 2절) |

움직임을 새로 짜기 전에 registry에서 찾는다: `npx hyperframes catalog --query "<영어로 원하는 움직임>" --json` → `npx hyperframes add <이름>`. 이번에 쓴 것: `kinetic-center-build`(단어 밀려 들어옴), `inline-highlight`(강조 밑줄), `spring-pop`(카드·1+1 튕김), `page-slide`(밀어 넘기기), `count-up`(가격 숫자), `before-after-wipe`(전후). 가로 1920 기준 블록(`mk-specs-list` 등)은 세로에 맞지 않으니 방식만 빌린다.

## 4) 지킬 규칙 (HyperFrames 계약 중 자주 걸리는 것)

- 글자는 **안전 영역 x 120~890, y 288~1248** 안. `check`가 틱톡·릴스·쇼츠 안전 영역을 따로 재 준다. 틱톡은 아래쪽(y 840~1260)에서 오른쪽 780까지라 긴 자막이 '경고'로 뜰 수 있다 → 두 줄로 나누거나 넘어간다(릴스·쇼츠 기준은 통과).
- 0프레임에 훅 글자가 보여야 한다(검은 화면·로고로 시작 금지).
- `Date.now()`, 무작위, 타이머 금지. 움직임은 모두 `tl`(멈춘 GSAP 타임라인)에 넣고 맨 끝에 `window.__timelines["main"] = tl`.
- GSAP로 움직이는 요소에 CSS `transform`을 따로 주지 않는다(가운데 맞춤도 `xPercent: -50`으로).
- `.clip` 상자 자체에는 `opacity`만, 위치·크기 움직임은 그 안쪽 요소에.
- 한글 글꼴은 `@font-face`로 `assets/fonts/Pretendard-*.otf`를 꼭 연결한다(이름만 쓰면 다른 글꼴로 바뀜).
- 마지막 문장은 2초 넘게 화면에 둔다(`check`의 `line_unread`).

## 5) 점검 → 렌더 → 눈으로 보기

```sh
npx hyperframes lint                                   # 오류 0
npx hyperframes check --json                           # ok:true. 안전 영역·대비·마지막 문장 경고는 읽고 고침
npx hyperframes snapshot --at 0,1.5,5,9,13,17,21 -o snap   # snap/contact-sheet.jpg 를 직접 열어 본다
npx hyperframes render --quality delivery -o out.mp4
ffprobe -v error -show_entries format=duration -of csv=p=0 out.mp4   # 길이 = data-duration
```

시트를 보고 최소 2번 고친다: ① 첫 프레임 훅이 다 보이나 ② 글자가 그림과 겹쳐 안 읽히는 곳(→ 흰 테두리 `paint-order: stroke`·상자) ③ 위 고정 제목과 카드가 붙거나 겹치나 ④ 자막이 두 줄을 넘나 ⑤ 가격·기간·수량이 사장님 자료와 같나. 고친 뒤 다시 `snapshot`.

사장님이 직접 고치고 싶어 하면 "HyperFrames 데스크톱 앱에서 열면 글자를 눌러 바로 고칠 수 있어요"라고 한 번만 알린다(`npx hyperframes preview`).

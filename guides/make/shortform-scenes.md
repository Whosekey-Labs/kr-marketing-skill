# 숏폼 장면표 템플릿 (1/2): 공통 규칙 · 키 설명 · T1~T3

`guides/make/shortform.md` 5절에서 연다. 고른 카드(G1~G9)에 맞는 템플릿 JSON 하나를 복사해 사장님 재료로 채운다. T4~T7은 `guides/make/shortform-scenes-2.md`. `[ ]`은 사장님 자료로만 채우고, 없으면 `[직접 입력: …]`으로 둔다.

## 공통 규칙

1. 세로 1080×1920. **첫 1초 안에 화면 글자.** 훅은 두 줄, 줄마다 8~12자.
2. 글자는 안전 영역(x 65~890, y 270~1250) 안. 도구가 알아서 맞춘다. 아래쪽 버튼·설명 자리는 비운다.
3. 사진 한 장 = 2.5~4초, 약하게 확대(`zoom`). 클립은 2~6초, 말이 있으면 문장 단위로 자른다.
4. 마지막 장면은 가게 이름 + 위치 또는 다음 행동 하나. **로고 그림은 넣지 않고 가게 이름을 글자로** 쓴다.
5. 길이·장면 수는 **권장**이다. 재료가 모자라면 장면을 지어내지 말고 빼서 짧게 만든 뒤 필요한 재료를 구체적으로 요청한다.
6. 업종 규칙을 먼저 건다: 의료는 전후사진 권하지 않음(5조건 점검표 통과 때만)·효과 단정 금지, 피부는 전후·효과 단정 금지, 부동산은 표시 항목, 가격엔 기준가·기간, AI 인물엔 "가상인물".
7. '알릴 소식 붙이기'를 켜면 마지막 장면을 글자 카드 `[혜택] [기간] [기준가]`로 바꾼다.
8. 색은 잘하는 숏폼의 문법에서 온다(`theme`). 시안은 늘 2안: 1안(레퍼런스안, 고르기 전 기본)은 `theme`만, 2안(기존 색 살린 안)은 사장님 간판·로고 색을 `highlight_color`로 얹는다(`guides/07-design-kit.md` 1)). 밝은 색이면 강조 글자는 같은 계열 진한 색으로.

## 화면 녹화 받는 법 (앱·홈페이지·서비스를 보여 줄 때)

사진 대신 화면이 소재인 업종(소프트웨어·B2B·온라인 판매 등)은 10~20초 화면 녹화를 부탁한다. 사장님께 이렇게 보낸다.
> "보여 주고 싶은 화면을 10초만 녹화해 주세요. 아이폰: 제어센터 → 화면 기록(●). 갤럭시: 화면 위에서 두 번 내리기 → 화면 녹화. PC: 윈도우 Win+Alt+R, 맥 Shift+Command+5. 손님 이름·전화번호가 보이면 가리거나 가짜 자료로 다시 찍어 주세요."
- 받은 녹화는 장면표의 `clip`으로 쓴다(가로 녹화면 `fit: contain`).

## 키 설명 (`tools/shortform.py` 0.2.0)

**맨 위**

| 키 | 값 | 뜻 |
|---|---|---|
| `layout` | `info` / `full` | info = 위아래 검은 띠 + 가운데 사진 띠(y 520~1500). full = 사진이 화면 전체 |
| `theme` | `info` / `warm` | info = 검정 + 노랑 강조(정보 숏폼). warm = 크림·갈색(가게 브이로그). 안 쓰면 layout info → info, full → warm |
| `colors` | `{bg, fg, accent, cards, box}` | theme 색을 덮어쓴다. `cards` = 글자 카드 색 `[[바탕, 글자, 강조], …]` 순서대로 돌아감, `box` = 자막 상자 색 |
| `highlight_color` | `"#FF5A1F"` | 강조색만 바꾼다(2안 기존 색 살린 안) |
| `fixed_title` | 글 | 계속 떠 있는 위 제목. info: 위 띠 2줄(윗줄 흰색, 아랫줄 강조색). full: 줄마다 진한 상자. 1번 장면이 훅이면 그 뒤부터 보인다 |
| `caption_size` | 66 | 아래 자막 크기. 64보다 작게 적어도 64로 그린다 |
| `title_size` | 76 | `fixed_title` 크기 |
| `caption_style` | `box` / `outline` | 자막 상자 또는 흰 글자 + 굵은 외곽선. 기본 info = box, full = outline |
| `brand` | 가게 이름 | 훅 카드 위 작은 꼬리표 |
| `font`, `music` | 경로 | 글꼴(기본 Pretendard), 목소리·현장음 파일 `{"path": …, "volume": 1.0}` |

**장면마다**

| 키 | 뜻 |
|---|---|
| `photo` / `clip` | 사진 또는 영상(장면표 파일 기준 경로). 둘 다 없으면 **글자 카드**(색 면 + 큰 글자, 한 글자씩 등장) |
| `duration` | 초(필수) |
| `caption` | 아래 자막. 1초에 7자 이하, 두 줄까지 |
| `title` | 사진·영상 장면: 강조색 상자 **꼬리표**(시각·항목 이름, 짧게). 글자 카드: **큰 글자 본문**(info 띠 안 카드에서 `caption`도 있으면 title은 작은 이름표, caption이 큰 글자) |
| `hook` | 화면 전체 큰 글자 카드. 문자열이면 그 글을 크게, `caption`은 그 아래 작게. 1번 장면에 사진이 없으면 자동으로 훅. 사진 장면에 붙이면 글은 그려지지 않고 고정 제목만 그 장면 뒤로 미뤄진다 |
| `fit` | `cover`(꽉 채움, 사진 기본) / `contain`(통째로 + 흐린 배경, 가로 캡처 영상 기본) |
| `zoom` | `in` / `out` / `none` (기본은 장면마다 번갈아) |
| `transition` | 이 장면으로 넘어갈 때: `slideleft`, `slideup`, `zoomin`, `smoothleft`, `fadeblack`, `slideright` 등(ffmpeg xfade 이름) 또는 `cut` |
| `bg` / `fg` / `accent` | 글자 카드 하나의 바탕·글자·강조색 |
| `tag` | 글자 카드 위 작은 꼬리표 |
| `size` | 글자 카드 큰 글자 크기(기본: 훅 132, 짧은 글 190, 긴 글 120) |
| `keep_audio`, `clip_start` | 클립 소리 살리기, 클립 시작 초 |

**강조**: `*이렇게*` 별표로 감싼 말은 강조색. 한 화면에 한 곳만.

## T1 전후 (G2) — 15~25초, 잔잔하게

피부관리·필라테스는 쓰지 않는다. 의료는 기본값 '권하지 않음'(복지부 가이드라인 Q3 5조건+사전심의, `guides/compliance/medical.md`). AI 생성·보정 금지. 전·후는 같은 각도.

```json
{"layout": "full", "theme": "warm", "brand": "[가게 이름]",
 "scenes": [
  {"duration": 2.5, "hook": "[대상]\n*[문제 한 줄]*"},
  {"photo": "before.jpg", "duration": 3, "title": "전", "caption": "이런 상태였어요", "zoom": "in"},
  {"photo": "process.jpg", "duration": 2.5, "title": "[작업 이름]", "transition": "smoothleft"},
  {"photo": "after.jpg", "duration": 4, "title": "*후*", "caption": "[결과 한 줄]", "transition": "fadeblack"},
  {"duration": 3, "title": "[기간·범위]", "caption": "[금액(포함 범위)]"},
  {"duration": 2.5, "title": "[가게 이름]", "caption": "[상담 방법]"}
 ]}
```

## T2 쇼케이스 (G3) — 8~20초, 잔잔하게

```json
{"layout": "full", "theme": "warm", "brand": "[가게 이름]",
 "scenes": [
  {"photo": "front.jpg", "duration": 3, "caption": "[상품 이름]", "zoom": "in"},
  {"photo": "hand.jpg", "duration": 3, "transition": "smoothleft"},
  {"photo": "detail.jpg", "duration": 3, "title": "[특징 한 단어]", "transition": "fadeblack"},
  {"photo": "display.jpg", "duration": 3},
  {"duration": 2.5, "title": "[가게 이름]", "caption": "[동네]"}
 ]}
```

1번 장면은 가장 예쁜 정면 컷이 먼저다(결과 먼저). 자막을 빼고 싶으면 `caption` 대신 사진 없는 `hook` 장면을 1.5초 앞에 둔다.

## T3 가게 구경 (G4) — 20~45초, 잔잔하게

```json
{"layout": "full", "theme": "warm", "brand": "[가게 이름]",
 "fixed_title": "[놀람 질문 1줄]\n[가게 이름]",
 "scenes": [
  {"duration": 2.5, "hook": "[동네]에 *[놀람 질문]*"},
  {"photo": "outside.jpg", "duration": 3.5, "title": "입구"},
  {"photo": "room1.jpg", "duration": 4, "title": "[공간 이름]", "transition": "smoothleft"},
  {"photo": "room2.jpg", "duration": 4, "title": "[공간 이름]", "transition": "smoothleft"},
  {"photo": "room3.jpg", "duration": 4, "title": "[공간 이름]", "transition": "smoothleft"},
  {"photo": "detail.jpg", "duration": 3, "caption": "[디테일 한 줄]"},
  {"duration": 3, "title": "[위치]", "caption": "[예약 방법]"}
 ]}
```

손님이 나오는 컷은 동의받은 것만. 부동산이면 장면마다 `caption`에 `중개사무소 이름·등록번호·면적·가격`을 넣는다.

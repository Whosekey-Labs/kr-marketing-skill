# 카드뉴스 원고 JSON 칸 (HTML 템플릿, `tools/cardnews_html.py` 1.0)

`guides/make/cardnews.md` 4) 단계에서 원고 JSON을 쓸 때만 연다. 견본을 먼저 본다:
- `tests/runs/r17-cardnews-html/work/bakery.json` — 동네 빵집 신메뉴(C01), 갈래 B. 표지는 이미지 생성(글자 포함), 본문은 캐릭터 + 레이아웃 7종.
- `tests/runs/r17-cardnews-html/work/wkl.json` — B2B 정보형(C06), 갈래 B.
- `gallery/cardnews/src/*.json` — 갈래 A(사진)·C(매거진)와 메뉴·이벤트·공지·예약·FAQ.
- 크롬이 없어서 Pillow로 그릴 때는 `guides/make/cardnews-spec-pillow.md`.

## 전체 칸

| 칸 | 뜻 |
|---|---|
| `theme` | 갈래 `A`(실사진 + 하단 큰 흰 글씨) / `B`(캐릭터 일러스트 + 큰 제목, 크림 바탕) / `C`(미니멀 매거진, 검정 바탕 + 형광 1색). 장마다 `theme`로 바꿀 수 있다 |
| `brand.colors` | `bg`(바탕) `text`(글자) `main`(라벨·띠·번호·버튼) `accent`(강조 1색: 핵심어·숫자) `marker`(형광펜) `sub`(보조 글자). 프로필 '우리 가게 색' 헥스 |
| `series`, `ep` | **시리즈 틀**: 왼쪽 위 라벨(예: "밀과결 겨울 메뉴" + "EP.1"). 매주 같은 이름, 회차만 바꾼다 |
| `account` | 아래 띠의 계정 이름 글자(로고 그림이 아니다). C는 `account_vertical: ["치과","한장"]`처럼 세로 두 줄 |
| `page_numbers` | 오른쪽 위 `2/8` 쪽번호. 기본 켬 |
| `chrome` | 머리말·꼬리말 전체. 기본 켬(레퍼런스 25곳 중 21곳이 시리즈 틀을 고정). 장마다 `false` 가능 |
| `css` | 이 원고에만 더할 CSS 한 줄(예외 때만) |

## 장 칸 (`slides[]`) — `layout`이 핵심

| `layout` | 쓰는 때 | 칸 |
|---|---|---|
| `image` | 이미지 생성 표지·단독 포스터를 꽉 채울 때 | `image`(경로). 위에 라벨·쪽번호·아래 띠가 얹힌다 → 그림은 위 13%·아래 7%를 비워 만든다 |
| `cover` | HTML 표지 | `kicker`, `title`(2~4줄), `subtitle`, `photo`(있으면 꽉 채우고 아래 어둡게 = 갈래 A), `focus`("50% 40%"), `t_size` |
| `list` | "○가지", 가격·조건 3개 | `items:[{title,text}]` (2~4개) |
| `vs` | A vs B, 해도 되는 것·안 되는 것 | `left`/`right: {label, items}`, `good: "right"`, `vs_mark` |
| `qa` | 자주 묻는 질문 | `q`(크게, 앞에 Q.), `lead`, `a`(아래 결론 상자) |
| `number` | 숫자 하나(가격·기간·횟수) | `value`, `unit`, `label`, `chips`, `value_size`, `chips_w` |
| `checklist` | 저장용 요약(마지막 장 바로 앞) | `items`, `tape: true`(마스킹 테이프) |
| `steps` | 1→2→3 순서 | `items:[{title,text,img}]` — `img`는 그 단계 소품 그림(투명 PNG) |
| `text` | 설명·공감 한 장 | `heading`, `lead` + 그림 |
| `photo` | 사진 칸 + 짧은 글(갈래 A 본문) | `photo`, `heading`, `text` |
| `cta` | 마지막 장, 행동 1개 | `title`, `text`, `info:[[이름,값]]`, `button`, `button_color`, `save`(작은 안내) |

모든 장에 쓸 수 있는 칸:

| 칸 | 뜻 |
|---|---|
| `kicker`, `heading`, `lead`(또는 `text`), `note` | 작은 머리말(강조색) / 큰 제목 / 보조 글 / 맨 아래 작은 주의 |
| `conclude`, `conclude_icon` | 아래 **결론 상자**(한 줄 요약, 왼쪽 위 동그란 아이콘). 정보형 장의 기본 마무리 |
| `art` | 그림 목록 `[{src, left/right/top/bottom, w, h, blend, round}]` — px 절대 위치. 투명 PNG 권장 |
| `bubbles` | 말풍선 `[{text, left, top, w, size, tail: "right"/"side"}]` — 캐릭터 입 쪽으로 꼬리를 둔다 |
| `stickers` | 자유 글자 `[{text, left, top, size, font: "hand"/"title", rotate, color, bg}]` — 손글씨 메모, 그림 속 시계판 숫자 등 |
| `gap` | 본문과 결론 상자 사이 간격 px(없으면 남는 높이를 채움) |
| `h_size`, `body_top`, `body_bottom`, `body_right`, `align: "center"` | 미세 조정(예외 때만) |

## 글 표기

- `*핵심어*` → 강조색 글자. `==핵심어==` → 붓으로 그은 형광펜. `\n` → 줄바꿈. **한 장에 강조 2곳까지, 빨강(강조색)은 한 번.**
- 한글은 어절 단위로 줄이 바뀐다(`word-break: keep-all`). 제목은 원고에서 `\n`으로 직접 끊는다(레퍼런스처럼 의미 단위로).
- 제목이 칸을 넘으면 렌더러가 글자를 줄이고(최대 38%) `[주의] 제목을 줄여 맞춤`을 띄운다. 글이 칸을 넘치면 `[고칠 것]`.

## 크기 위계 (1080 폭, `templates/cardnews-html/base.css` 토큰)

| 자리 | 크기 |
|---|---|
| 표지 제목 | 112~132px(B는 132), 2~4줄 |
| 본문 장 제목 | 갈래 A 80 · B 102 · C 76px |
| 항목 제목 / 본문 | 50px / 36~38px (최소 34px) |
| 큰 숫자 | 300px(조정 `value_size`) |
| 라벨·쪽번호 | 26px |

## 그림 준비 (`art`)

- 이미지 생성으로 **캐릭터 시트(2×2 포즈 4개)** 를 먼저 만들고, 칸별로 잘라 쓴다(같은 캐릭터가 장마다 다른 포즈). 나머지 장면·소품은 시트를 참조 이미지로 넣어 만든다.
- 생성 그림의 단색 바탕은 `python3 cardnews_html.py cutout art/*.png -o art/cut --drop-edge`로 투명하게 뺀다(가장자리에 걸친 옆 칸 조각도 지움). 바탕을 안 빼면 네모 테두리가 보인다.
- 사장님 실제 사진은 `photo`(cover·photo 레이아웃)로. 그림으로 바꾸지 않는다.

## 명령

```bash
python3 cardnews_html.py render spec.json -o out/      # 01.png… + 01.jpg… + check.json + cardnews.html
python3 cardnews_html.py sheet out/ -o sheet.png --ref r1.jpg r2.jpg r3.jpg r4.jpg   # 레퍼런스와 나란히 보는 시트
python3 cardnews_html.py layouts                        # 갈래·레이아웃 목록
```
템플릿 파일(`templates/cardnews-html/`)이 스크립트 옆에 없으면 저장소에서 받아 `~/.cache/kr-cardnews/`에 둔다.

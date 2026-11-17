# 카드뉴스 원고 JSON 칸 — Pillow 대체 경로 (tools/cardnews.py 0.5.0)

> 기본 경로는 HTML 템플릿이다(`guides/make/cardnews-spec.md`). 이 파일은 크롬(헤드리스 브라우저)이 없어 `tools/cardnews.py`(Pillow)로 그릴 때만 연다.

`guides/make/cardnews.md` 4) 단계에서 원고 JSON을 쓸 때만 연다. 견본 두 개를 먼저 본다:
- `examples/cardnews-spec-sample.json` — 동네 빵집 신메뉴(C01). 사진 장·`photo_match`·`사진 필요` 처리 예시. 결과 `examples/cardnews-sample/`.
- `examples/cardnews-spec-faq-sample.json` — 가상 B2B 회사의 자주 묻는 질문(C07). 앵커 종류를 장마다 바꾼 예시(chips·number·flow·table·vs·button), `tone` brand/deep, `account`.

## 전체 칸

| 칸 | 뜻 |
|---|---|
| `brand.colors` | `main`(주색), `accent`(강조), `bg`(밝은 바탕), `text`(글자, 먹색), `deep`(짙은 바탕, 없으면 짙은 남색) — 헥스 값 |
| `cover_style`, `body_style` | 표지·본문 스타일 코드(S01~S11). 장마다 `style`로 바꿀 수 있다 |
| `body_tone` | 본문 장 기본 바탕: `light`(기본)/`dark`/`alternate`(밝은 장·어두운 장 번갈아) |
| `account` | 계정 이름 **글자**(예: `"후스키랩스"`). 본문은 왼쪽 아래 작게, 표지·마지막 장은 조금 크게. 로고 그림이 아니다 |
| `em_style` | `*강조*`를 그리는 법: `marker`(형광펜), `box`(상자), `color`(글자색). 안 쓰면 자동, 강조색 대비가 3:1 미만이면 `box`로 바꾼다. 장마다 덮어쓸 수 있다 |
| `chrome` | `true`면 머리말(`series`)·쪽번호·진행 막대를 그린다. **기본 끔** |
| `swipe_arrow` | 표지 오른쪽 아래 '넘겨서 보기 →'. 기본 켬, **표지에만** 그린다 |
| `series` | `chrome` 켰을 때 왼쪽 위 이름(없으면 표지 `kicker`) |

## 장 칸 (`slides[]`)

| 칸 | 뜻 |
|---|---|
| `role` | `cover`(1장), `body`, `cta`(마지막 장) |
| 글 | `title`(표지·CTA), `subtitle`, `kicker`(작은 꼬리표), `heading`, `text`, `note`(작은 주의 문구) |
| `tone` | 장 바탕: `light`, `dark`, `brand`(주색 바탕), `deep`(`brand.colors.deep` 바탕) |
| `items` | 번호 리스트. `checklist: true`면 체크, `steps: true`면 단계로 이음. `items[].icon`이면 번호 대신 아이콘 |
| `cards` | `true`면 항목을 흰 카드로(체크리스트는 기본 켬, `false`로 끔) |
| `bar` | 장 아래 **요약 막대**(결론 한 줄, 진한 띠). `*강조*` 가능 |
| `compare`, `menu`, `info` | 두 칸 비교 `[{label, items}, …]` / 메뉴·가격표 `[[이름, 가격, 한 줄], …]` / `[["위치","…"], …]` |
| `q`·`a` | 질문(제목처럼 크게, 질문이 2개 이상이면 Q1·Q2 자동)·답 |
| `big`, `kicker_en` | S08 큰 숫자, S03 영문 소제목 |
| `photo` | 원고 파일 기준 사진 경로. `photo_hint`(사진 없을 때 칸에 적을 말), `photo_focus`([0.5,0.3] 살릴 위치) |
| `photo_match` | 사진이 문구와 **다를 때 그 이유**를 적는다(예: `"밤 크루아상이 아닌 일반 크루아상 사진"`). 적으면 점검에 '확인 필요'가 뜬다. 맞으면 안 쓴다 |
| `anchor` | 장의 시각 앵커(아래 표). `pos`: `top`/`mid`/`bottom` |
| `art` | 이미지 생성으로 만든 그림(아래 '그림 칸'). 문자열이면 경로만 |

## 시각 앵커 (`anchor`) — 장마다 하나

| `type` | 쓰는 법 | 쓸 때 |
|---|---|---|
| `number` | `{"value":"4,800원","label":"밤 크루아상 1개"}` + `chips:[…]`(숫자 옆 칩) 또는 `band:[…]`(숫자 아래 칸) | 가격·기간·개수 한 개를 크게 |
| `icon` | `{"name":"clock"}` | 숫자가 없는 설명 장 |
| `flow` | `{"steps":[{"label":"카톡으로\n일 알려 주기","icon":"chat"}, …]}` | 순서(예약 방법, 진행 단계) |
| `vs` | `{"left":{"label","items"},"right":{…}}` | A와 B 비교, 해도 되는 것·안 되는 것 |
| `button` | `{"text":"카카오톡 채널 열기","color":"#FEE500"}` | 마지막 장 행동 |
| `chips` | `{"items":["Q1 …","Q2 …"]}` | 표지 목차, 키워드 묶음 |
| `table` | `{"head":["바뀐 것","한 일"],"rows":[[…],[…]]}` | 짝으로 된 정보 3~4줄 |
| `timeline` | `{"start":10,"end":20,"marks":[[11,"11시 20개"],[15,"15시 20개"]]}` | 시간대(굽는 시간, 영업시간) |

아이콘 이름: check arrow clock chat bulb calendar won wrench user cup star phone.
`pos` 기본: `number`·`icon`은 `top`(제목 위), 나머지는 글 아래. `mid`는 본문 글과 항목 사이.

긴 숫자는 숫자와 단위 사이에 띄어쓰기를 넣는다(예: `"3,100만 원"`). 렌더러가 넘칠 때 단위를 아랫줄로 내리고, 그래도 넘치면 칩을 숫자 아래로 옮긴다. 잘리면 check가 '잘림'을 고칠 것으로 낸다.
앵커·사진·리스트가 하나도 없는 본문 장은 렌더러가 아이콘을 자동으로 넣고 '시각 앵커' 주의를 띄운다.

## 그림 칸 (`art`) — 생성 그림 넣기

만드는 법·상한·금지는 `guides/make/image-gen.md`. 그림 안에 글자를 넣지 않는다(글자는 렌더러가).

| 칸 | 뜻 | 기본 |
|---|---|---|
| `path` | 원고 파일 기준 그림 경로(PNG 투명 배경 가능, JPEG) | — |
| `pos` | `top`(제목 위) / `mid`(본문 글 아래, 항목 위) / `bottom`(항목·앵커 아래, 요약 막대 위) / `full`(장 바탕 전체) | `top` |
| `h`, `w` | 높이 px(1 이하면 세로 비율, 0.3 = 405px, 최대 60%) / 칸 폭 비율(0.5 = 절반, 가운데 정렬) | 420, 1.0 |
| `fit` | `contain`(그림 전체가 보이게, 투명 PNG에 알맞음) / `cover`(칸을 꽉 채우고 잘라냄) | `contain` |
| `radius`, `focus` | 둥근 모서리 px / `cover`일 때 살릴 위치 [x, y] | cover 28·contain 0 / [0.5, 0.5] |
| `wash` | `full`일 때 그림 위에 장 바탕색을 얹는 정도(0~0.9). 글자 대비가 모자라면 0.3~0.6 | 0 |
| `hint` | 그림이 아직 없을 때 '그림 자리'에 적을 말 | — |

- `full`은 어느 스타일이든 단색 바탕 대신 그림을 깐다. 글자 대비 점검은 그림 위에서 잰다. 그림 밝기를 장 `tone`에 맞춘다(밝은 그림은 light 장, 어두운 그림은 brand·deep 장).
- 글이 넘치면 그림도 함께 줄인다(원래 높이의 60%까지). 그림 파일이 없으면 '그림 자리'를 그리고 '그림 없음'(고칠 것).
- S06(그림·캐릭터)은 `art`가 있는 S05로 그린다. 예: 표지 `{"style":"S06", "art":{"path":"art/mascot.png","pos":"top","h":520}}`.

## 렌더러가 알아서 하는 것

- 본문 장은 **위(y 150)부터 아래(y 1190)까지** 채운다. 남는 높이는 항목 사이에 나눈다(위 정렬, 가운데 몰림 없음).
- 크기: 본문 40px 이상, 장 제목 96~112px, 표지 제목은 가장 긴 줄이 폭 90%가 되게 자동.
- 실제 사진이 없는 사진 스타일(S01·S02·S03·S09) 장은 글자 카드(S05)로 대신 그리고 '사진 필요'를 띄운다.

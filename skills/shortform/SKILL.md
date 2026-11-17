---
name: kr-shortform
description: 한국 소상공인 가게의 세로 숏폼(릴스·쇼츠·네이버 클립·틱톡) 원본을 기획하고 만든다. 목적·가진 재료로 갤러리 카드 9장(G1~G9)과 편집 느낌 3개 중에서 고르고, 같은 업종 레퍼런스의 디자인 문법 → 시안 2안 → 훅 3초 대본 → 장면표 템플릿 → 1080×1920 조립(파이썬·ffmpeg) → 점검 → 플랫폼별 제목·해시태그까지 한다. 영상을 못 만드는 에이전트는 장면표를 주고 캡컷 조립을 안내한다. "릴스 만들어줘", "쇼츠 만들어줘", "이 사진으로 숏폼", "클립 올릴 영상" 등.
---

# 숏폼 (단독 사용)

전체 마케터 스킬의 숏폼 부분만 쓴다. 원문 주소 앞부분(BASE): `https://raw.githubusercontent.com/Whosekey-Labs/kr-marketing-skill/main/`

## 순서

1. 업종을 확인하고 `guides/compliance/index.md`에서 규제 플래그를 고른다. `guides/compliance/common.md`는 모든 업종에 열고, 법규에 걸리는 업종이면 해당 플래그 파일도 연다.
2. 카드와 편집 느낌을 고른다: `guides/styles/shortform.md` (목적 → 가진 재료 → 카드 G1~G9, '알릴 소식 붙이기'는 옵션. 편집 느낌은 잔잔하게/정보 또박또박/빠르고 신나게. 재료 분류 P1~P7은 에이전트가 정한다)
3. 만든다: `guides/make/shortform.md` (같은 업종 레퍼런스 3~5개 → 디자인 문법 → 시안 2안 → 대본 → 장면표(`guides/make/shortform-scenes.md`·`shortform-scenes-2.md` 템플릿 JSON 7개) → 조립 → 점검 → 플랫폼별 문구)
4. 파이썬을 쓸 수 있으면 `BASE + tools/shortform.py`(0.2.0)로 조립한다. 예시 장면표: `BASE + examples/shortform-scenes-sample.json`
   - 맨 위 `layout`(`info` 정보형 검은 띠 / `full` 사진 전체), `theme`(`info` 검정+노랑 / `warm` 크림·갈색), `fixed_title`, `brand`, `caption_size` 66(최소 64), `title_size` 76, `caption_style`(info=`box`, full=`outline`), 바꿀 때만 `highlight_color`·`colors`.
   - 장면마다 `photo`/`clip`, `duration`, `caption`, `title`(사진 장면 = 꼬리표, 사진 없는 글자 카드 = 큰 글자), `hook`, `fit`(cover/contain), `zoom`, `transition`(xfade 이름 또는 `cut`), 글자 카드 색 `bg`/`fg`/`accent`, `tag`, `size`. `*별표*`로 감싼 말은 강조색(한 화면 한 곳).
   - `check` → `build` → `frames out.mp4 --scenes scenes.json --sheet sheet.png`로 장면 시트를 직접 보고 고친다.
5. 사장님께 카드를 보여 줄 때는 견본 `gallery/shortform/G1.png`~`G9.png`(영상 `.mp4`), 편집 느낌은 `feel-calm.png`·`feel-info.png`·`feel-fast.png`.

## 꼭 지킬 것

- 내보내기 전에 항상 `guides/compliance/common.md`(모든 업종) + 이 업종 플래그 파일을 열어 검수한다(전체 스킬 `SKILL.md` 규칙 4). 스크립트 모드면 `python3 mk.py lint`도. 결과 끝에 `검수: 연 파일 이름` 한 줄, 못 열었으면 '검수 안 됨'으로 표시하고 올리지 않는다.
- 1080×1920, 15~60초 권장·90초 이하, 자막은 안전 영역(x 65~890, y 270~1250) 안. 재료가 모자라면 지어내지 말고 짧게 만들고 필요한 재료를 요청한다.
- 색은 사장님 홈페이지 색이 아니라 잘하는 숏폼 레퍼런스 문법(`theme`)에서. 시안은 늘 2안: 1안 레퍼런스안(기본), 2안 기존 가게 색을 `highlight_color`로 살린 안. 사장님께는 번호로 고르게 한다. 로고·워터마크는 영상 안에 넣지 않고 가게 이름은 글자로.
- 워터마크·다른 앱 로고 없는 원본 하나를 플랫폼마다 따로 올린다.
- 원본에 대중가요를 넣지 않는다. 음악은 각 앱의 상업용 라이브러리에서.
- 가격·경험담·수치는 지어내지 않는다. 실제 매장·상품·사람처럼 보이는 AI 이미지·영상은 만들지 않고(누가 봐도 그림인 장식만 허용), AI 인물은 "가상인물"로 표시하며 경험담을 말하게 하지 않는다.
- 의료 전후사진은 기본으로 권하지 않는다(원장님이 원하면 guides/compliance/medical.md 전후사진 점검표를 모두 채우고 사전심의를 거친 경우만). 리뷰 혜택 소식은 기본으로 제안하지 않는다.
- 해시태그 5개 이하. 네이버 클립은 플레이스 스티커를 붙이고, AI 목소리·그림을 썼으면 'AI 활용' 표시를 켠다.
- 가게 조사·4주 계획까지 하려면 전체 스킬 `SKILL.md`를 연다.

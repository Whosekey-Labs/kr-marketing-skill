# 카드뉴스 갤러리 견본 출처

이 폴더의 견본은 **HTML 템플릿(`templates/cardnews-html`) + 헤드리스 크롬 캡처(`tools/cardnews_html.py`)**로 만든 새 방식 견본이에요(2026-11-17). 예전 Pillow 렌더러 견본(S01~S11, C01~C12)은 `pillow/`에 그대로 두었어요(대체 경로 `tools/cardnews.py`용).

- 브랜드는 모두 **가상**이에요: 밀과결(빵집), 오후네시반(카페), 코어숨(필라테스), 그리고 후스키랩스(우리 회사, 사실은 스킬 소개 원고 그대로). 가상 이름 셋은 2026-11-17 웹 검색에서 같은 이름의 가게를 찾지 못했어요. 가격·날짜·주소도 견본용 가상 값이에요.
- 원고: `src/*.json`(C02·C03·C04·C05·C07), C01·C06은 `tests/runs/r17-cardnews-html/work/bakery.json`·`wkl.json`.
- 다시 만들기: `python3 tools/cardnews_html.py render gallery/cardnews/src/c02-menu.json -o out/c02`

| 파일 | 유형 | 갈래 | 내용 |
|---|---|---|---|
| `A.png` | 갈래 A 표지 | 실사진 + 하단 큰 흰 글씨 | 코어숨 첫 방문 안내, 오후네시반 메뉴 |
| `B.png` | 갈래 B 표지 | 캐릭터 일러스트 + 큰 제목 | 밀과결·후스키랩스 표지(이미지 생성, 글자까지), 오후네시반 이벤트(HTML 표지) |
| `C.png` | 갈래 C 표지 | 미니멀 매거진 | 코어숨 FAQ(사진), 밀과결 휴무 공지 |
| `C01.png` | 신메뉴 출시 | B | 밀과결 밤 크루아상(표지·Q&A·단계) |
| `C02.png` | 메뉴·가격표 | A | 오후네시반 겨울 메뉴(표지·리스트·사진) |
| `C03.png` | 이벤트 | B(그림 없이) | 오후네시반 리뷰 이벤트(표지·단계·숫자) |
| `C04.png` | 공지 | C | 밀과결 임시 휴무(표지·숫자·마지막 장) |
| `C05.png` | 예약·찾아오는 길 | A | 코어숨 첫 수업 예약(표지·단계·마지막 장) |
| `C06.png` | 정보·꿀팁 | B | 후스키랩스 'AI 마케터 쓰기 전 꼭 확인할 5가지'(표지·숫자·VS) |
| `C07.png` | 자주 묻는 질문 | C | 코어숨 FAQ(표지·Q&A 2장) |

## 사진 (위키미디어 공용 CC0 1.0)

상업 이용·수정이 가능하고 출처 표시 의무는 없지만 적어 둬요. 가상 가게의 실제 매장·상품 사진이 아니에요. 원본은 폭 760px 이하로 줄인 사본이라 1080 카드에서는 조금 흐려요(실제 가게는 사장님 원본 사진을 써요).

| 파일 | 원본 | 올린 사람 | 쓴 곳 |
|---|---|---|---|
| `src/photos/sf_f00.jpg` | [Cafe Interior with Coffee.jpg](https://commons.wikimedia.org/wiki/File:Cafe_Interior_with_Coffee.jpg) | Kavig624 | C02 표지, A |
| `src/photos/latte_1.jpg` | [Latte art 3.jpg](https://commons.wikimedia.org/wiki/File:Latte_art_3.jpg) | Kim Sanso | C02 3장 |
| `src/photos/cookiebox_1.jpg` | [Assorted cookies in a box at a party.jpg](https://commons.wikimedia.org/wiki/File:Assorted_cookies_in_a_box_at_a_party.jpg) | Tomwsulcer | C03 표지, B |
| `src/photos/reformer_3.jpg` | [Aula Pilates Turma 07 Ed Física Unifesp.jpg](https://commons.wikimedia.org/wiki/File:Aula_Pilates_Turma_07_Ed_F%C3%ADsica_Unifesp.jpg) | Autor e Colaboradores da Aula 7 | C05 표지, A |
| `src/photos/reformer_0.jpg` | [Pilates reformer.jpg](https://commons.wikimedia.org/wiki/File:Pilates_reformer.jpg) | Maddi Bazzocco | C07 표지, C |

## 그림 (이미지 생성)

C01·C06·B의 캐릭터·소품 그림과 두 표지(글자 포함)는 designer-cli(gpt-image-2)로 만들었어요. 프롬프트 원문은 `tests/runs/r17-cardnews-html/prompts/`. 누가 봐도 그림(색연필 일러스트)이고 실사 상품·인물은 없어요. 표지 한글은 원고와 한 글자씩 대조해 틀린 글자 0개였어요.

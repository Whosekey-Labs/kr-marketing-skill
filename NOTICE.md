# 참고한 공개 자료 (NOTICE)

이 스킬의 지침은 아래 공개 자료의 **아이디어와 구조**를 참고해 한국 소상공인 상황에 맞게 우리 말로 새로 썼어요. 문장·코드를 그대로 옮기지 않았어요.

| 자료 | 라이선스 | 참고한 아이디어 |
|---|---|---|
| [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) | MIT | 모든 하위 스킬이 먼저 읽는 공통 사업 정보 파일, 실제 문장으로 정의하는 브랜드 말투 |
| [anthropics/knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins) (small-business) | Apache-2.0 | 공유 말투 프로필, 생성량 사전 승인, 자동 게시 대신 승인 후 게시, 연결된 자료에 없는 가격 쓰지 않기 |
| [aaron-he-zhu/aaron-marketing-skills](https://github.com/aaron-he-zhu/aaron-marketing-skills) | Apache-2.0 | 광고 문구-근거 장부 방식의 검수 |
| [modu-ai/moai-cowork](https://github.com/modu-ai/moai-cowork) | Apache-2.0 | 업종 선택에 따라 켜지는 광고 법규 검사, 증빙 없으면 통과하지 않는 구조 |
| [gugdongbag-eng/korean-marketing-skills](https://github.com/gugdongbag-eng/korean-marketing-skills) | MIT | 한국 소상공인용 공통 정보 파일, 한 번에 1~2개만 묻기 |
| [chegom/ig-cardnews](https://github.com/chegom/ig-cardnews) | MIT | 한글은 생성 모델이 아니라 렌더러로, 대비·안전 영역 자동 검사 |
| [bam-bam-2/solo-skills](https://github.com/bam-bam-2/solo-skills) | MIT | 네이버 블로그 발행 후 노출 확인 |

공식 근거(법령·플랫폼 정책·네이버 공식 블로그)는 각 지침 파일에 출처를 적었어요.

## 폰트
카드뉴스·숏폼 렌더러는 아래 폰트를 실행할 때 내려받아 써요.

| 폰트 | 출처 | 라이선스 |
|---|---|---|
| Pretendard | https://github.com/orioncactus/pretendard | SIL Open Font License 1.1 |
| Nanum Pen Script | https://fonts.google.com/specimen/Nanum+Pen+Script | SIL Open Font License 1.1 |
| Gowun Batang | https://fonts.google.com/specimen/Gowun+Batang | SIL Open Font License 1.1 |
이 저장소에는 폰트 파일을 넣지 않았어요.

## 예시 사진 (카드뉴스 견본)
`examples/cardnews-sample/photos/croissant.jpg`는 **예시 사진**이에요. 가상 빵집 '밀과결'의 실제 매장·제품 사진이 아니고, 원고 속 '밤 크루아상'도 아니에요(일반 크루아상). 실제 가게는 사장님 사진으로 바꿔요. 위키미디어 공용(Wikimedia Commons)의 CC0(퍼블릭 도메인 기증) 사진이라 상업 이용과 수정이 가능해요(밝기를 조금 낮춤). 카드 이미지 안에는 '예시 사진' 글자를 넣지 않고, 원고(spec)의 `photo_match` 표시로 렌더 점검에 경고를 남겨요.

| 파일 | 원본 | 라이선스 |
|---|---|---|
| `croissant.jpg` | [File:Un croissant sur le comptoir du Café du Palais (Belley).jpg](https://commons.wikimedia.org/wiki/File:Un_croissant_sur_le_comptoir_du_Caf%C3%A9_du_Palais_(Belley).jpg) | CC0 1.0 |

## 예시 사진 (숏폼 갤러리 견본)
`gallery/shortform/`의 견본 영상·장면 시트는 가상 브랜드('밀과결', '오후세시반', '코어담필라테스', '틈새집 인테리어')로 만든 예시예요. 사진은 모두 위키미디어 공용의 CC0 1.0 사진이라 상업 이용과 수정이 가능해요. 실제 매장·제품 사진이 아니에요. 사진마다 원본 주소와 쓴 곳은 `gallery/shortform/CREDITS.md`에 적었어요.

## 예시 사진 (블로그 갤러리 견본)
`gallery/blog/`의 견본 화면(B01~B13, V1~V5)에 넣은 사진은 모두 위키미디어 공용의 CC0 1.0 사진이라 상업 이용과 수정이 가능해요. 가상 가게의 실제 매장·제품 사진이 아니에요. 사진마다 원본 주소·올린 사람·쓴 곳은 `gallery/blog/CREDITS.md`에 적었어요.

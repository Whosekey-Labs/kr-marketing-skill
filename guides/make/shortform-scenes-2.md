# 숏폼 장면표 템플릿 (2/2): T4~T7

공통 규칙과 키 설명은 `guides/make/shortform-scenes.md`. 같은 방식으로 JSON 하나를 복사해 사장님 재료로 채운다.

## T4 정보 카드 (G5) — 20~40초, 정보 또박또박

```json
{"layout": "info", "theme": "info", "brand": "[가게 이름]",
 "fixed_title": "[대상]이 꼭 알아야 할\n[N]가지",
 "scenes": [
  {"duration": 3, "hook": "[대상]이 꼭 알아야 할\n*[N]가지*"},
  {"photo": "item1.jpg", "duration": 6, "title": "① [항목 이름]", "caption": "[설명 한 줄, *핵심어*]"},
  {"photo": "item2.jpg", "duration": 6, "title": "② [항목 이름]", "caption": "[설명 한 줄]"},
  {"photo": "item3.jpg", "duration": 6, "title": "③ [항목 이름]", "caption": "[설명 한 줄]"},
  {"duration": 3, "title": "정리", "caption": "[한 줄 정리]"},
  {"duration": 2.5, "title": "[가게 이름]", "caption": "궁금한 건 *댓글*로"}
 ],
 "music": {"path": "voice.m4a", "volume": 1.0}}
```

N은 3이 기본. 가격이면 숫자를 `*강조*`하고 기준일을 자막 끝에 쓴다. 목소리는 사장님 녹음이 먼저, 없으면 AI 목소리(재료 분류 P7). 목소리가 없으면 `music` 줄을 지운다. 가로 화면 캡처는 `"fit": "contain"`.

## T5 만드는 과정 (G1) — 15~40초, 잔잔하게

**과정 클립이 없으면 쓰지 않는다**(사진만으로는 과정이 안 보인다).

```json
{"layout": "full", "theme": "warm", "brand": "[가게 이름]",
 "scenes": [
  {"photo": "done.jpg", "duration": 2.5, "caption": "*[완성품 이름]* 만들기", "zoom": "in"},
  {"photo": "ingredients.jpg", "duration": 3, "title": "재료"},
  {"clip": "step1.mp4", "duration": 4, "title": "1", "caption": "[동작]", "keep_audio": true},
  {"clip": "step2.mp4", "duration": 4, "title": "2", "caption": "[동작]", "keep_audio": true},
  {"clip": "step3.mp4", "duration": 4, "title": "3", "caption": "[동작]", "keep_audio": true},
  {"photo": "done2.jpg", "duration": 3, "title": "완성", "transition": "fadeblack"},
  {"duration": 2.5, "title": "[가게 이름]", "caption": "[동네]"}
 ]}
```

'방법 설명 넣기'를 켜면 `caption`을 짧은 팁 문장으로 바꾸고 `"layout": "info"` + `fixed_title: "[완성품] 만드는 법"`, 목소리를 넣는다.

## T6 오늘 하루 (G7) — 40~90초(10~15장면), 빠르고 신나게

```json
{"layout": "full", "theme": "warm", "brand": "[가게 이름]",
 "fixed_title": "[업종] 사장의\n오픈 전 [N]시간",
 "scenes": [
  {"duration": 2.5, "hook": "오픈 전 *[N]시간*\n무슨 일이?"},
  {"clip": "c01.mp4", "duration": 3, "title": "[07:00]", "caption": "[작업]", "transition": "cut"},
  {"clip": "c02.mp4", "duration": 3, "title": "[07:20]", "caption": "[작업]", "transition": "slideleft"},
  {"photo": "p03.jpg", "duration": 2.5, "title": "[07:45]", "caption": "[작업]", "transition": "cut"},
  {"clip": "c04.mp4", "duration": 3, "title": "[08:10]", "caption": "*[작업]*", "transition": "slideleft"},
  {"photo": "open.jpg", "duration": 3.5, "title": "[09:00] *오픈*", "caption": "오늘도 오픈!"}
 ]}
```

아래는 줄인 예다. 10~15장면까지 같은 줄을 늘린다. 시각(`title`)은 **사진·영상 파일에 저장된 촬영 시각**으로 넣는다. 없으면 사장님께 순서만 받고 시각을 빼거나 `[직접 입력: 시각]`. 사장님께 하는 말: "내일 하루 동안 일하시면서 10번만, 세로로 5초씩 찍어 주세요. 시간은 제가 자막으로 넣을게요."

## T7 가게 이야기 (G8, 사진형) — 25~45초, 잔잔하게 + 목소리

```json
{"layout": "full", "theme": "warm", "brand": "[가게 이름]",
 "fixed_title": "[반전 이력 한 줄]",
 "scenes": [
  {"duration": 3, "hook": "[반전 이력]\n*[지금 하는 일]*"},
  {"photo": "old1.jpg", "duration": 5, "title": "[연도]", "caption": "[사장님이 한 말 1]"},
  {"photo": "old2.jpg", "duration": 5, "caption": "[사장님이 한 말 2]"},
  {"photo": "now1.jpg", "duration": 5, "title": "지금", "caption": "[사장님이 한 말 3]", "transition": "fadeblack"},
  {"photo": "now2.jpg", "duration": 5, "caption": "[사장님이 한 말 4]"},
  {"photo": "product.jpg", "duration": 3, "caption": "*[지금 하고 싶은 말]*"},
  {"duration": 2.5, "title": "[가게 이름]", "caption": "[위치]"}
 ],
 "music": {"path": "voice.m4a", "volume": 1.0}}
```

이야기는 사장님이 말한 것만 쓴다. 손님 이야기면 손님 얼굴·이름은 가리고 손님 말투를 지어내지 않는다. 지금 가게 모습 비중을 높인다(창업 고생담만으로는 반응이 약하다).

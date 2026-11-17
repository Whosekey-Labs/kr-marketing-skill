#!/bin/sh
# 숏폼 HyperFrames 프로젝트 하나 만들기.
# 사용: sh new.sh <만들 폴더> <템플릿: time-routine | info-card | showcase | before-after>
# 하는 일: 세로(1080x1920) 빈 프로젝트 → 템플릿을 index.html로 복사 → Pretendard 글꼴 받기 → 점검.
set -e
DIR="$1"; TPL="${2:-info-card}"
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -n "$DIR" ] || { echo "사용: sh new.sh <폴더> <템플릿>"; exit 1; }
[ -f "$HERE/$TPL.html" ] || { echo "템플릿 없음: $TPL (time-routine, info-card, showcase, before-after)"; exit 1; }

node -e 'process.exit(+process.versions.node.split(".")[0] >= 22 ? 0 : 1)' \
  || { echo "Node.js 22 이상이 필요해요. https://nodejs.org 에서 LTS 설치"; exit 2; }
command -v ffmpeg >/dev/null || { echo "ffmpeg가 필요해요 (맥: brew install ffmpeg)"; exit 2; }

npx --yes hyperframes init "$DIR" --resolution portrait --non-interactive --skip-skills >/dev/null
rm -f "$DIR/CLAUDE.md"   # 지침 파일은 AGENTS.md 하나만 둔다
cp "$HERE/$TPL.html" "$DIR/index.html"
mkdir -p "$DIR/assets/fonts" "$DIR/assets/photo" "$DIR/assets/art"

PRET="https://raw.githubusercontent.com/orioncactus/pretendard/v1.3.9/packages/pretendard/dist/public/static"
for w in SemiBold Bold ExtraBold Black; do
  f="$DIR/assets/fonts/Pretendard-$w.otf"
  if [ -f "$HOME/Library/Fonts/Pretendard-$w.otf" ]; then cp "$HOME/Library/Fonts/Pretendard-$w.otf" "$f"
  else curl -fsSL "$PRET/Pretendard-$w.otf" -o "$f"; fi
done

npx --yes hyperframes browser ensure >/dev/null   # 렌더용 크롬(헤드리스) 확인·설치
echo "준비 끝: $DIR (사진은 $DIR/assets/photo, 그림은 $DIR/assets/art)"
echo "다음: [대괄호] 채우기 → npx hyperframes check --json → snapshot → render --quality delivery -o out.mp4"

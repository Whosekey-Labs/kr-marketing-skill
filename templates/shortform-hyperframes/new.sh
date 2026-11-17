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

# hyperframes CLI 찾기: npx가 셸 별칭·훅 때문에 실패하면 node로 CLI 파일을 직접 부른다.
# 우선순위: 환경변수 HF_CLI(.mjs 경로) → npx → ~/.npm/_npx 안의 가장 높은 버전 → ~/.cache 에 설치
find_cli() {
  node -e '
    const fs=require("fs"),path=require("path"),os=require("os");
    const roots=[path.join(os.homedir(),".npm","_npx"),path.join(os.homedir(),".cache","hyperframes-cli")];
    let best=null;
    const cmp=(a,b)=>{a=a.split(/[.-]/).map(Number);b=b.split(/[.-]/).map(Number);
      for(let i=0;i<3;i++){if((a[i]||0)!==(b[i]||0))return (a[i]||0)-(b[i]||0);}return 0;};
    for(const r of roots){
      let dirs=[];try{dirs=r.endsWith("_npx")?fs.readdirSync(r).map(d=>path.join(r,d)):[r];}catch(e){}
      for(const d of dirs){const pk=path.join(d,"node_modules","hyperframes");
        try{const v=JSON.parse(fs.readFileSync(path.join(pk,"package.json"))).version;
          const bin=path.join(pk,"bin","hyperframes.mjs");
          if(fs.existsSync(bin)&&(!best||cmp(v,best.v)>0))best={v,bin};}catch(e){}}
    }
    if(best)console.log(best.bin);'
}
HF_MODE=""
if [ -n "$HF_CLI" ] && [ -f "$HF_CLI" ]; then HF_MODE=node
elif npx --yes hyperframes --version 2>/dev/null | grep -q '[0-9]'; then HF_MODE=npx
else
  HF_CLI="$(find_cli)"
  if [ -z "$HF_CLI" ]; then
    npm install --silent --prefix "$HOME/.cache/hyperframes-cli" hyperframes >/dev/null 2>&1 || true
    HF_CLI="$(find_cli)"
  fi
  [ -n "$HF_CLI" ] || { echo "hyperframes를 실행하지 못했어요. npx와 직접 호출 모두 실패 → 다른 렌더 경로(shortform.py)로 가세요."; exit 3; }
  HF_MODE=node
fi
hf() { if [ "$HF_MODE" = npx ]; then npx --yes hyperframes "$@"; else node "$HF_CLI" "$@"; fi; }
[ "$HF_MODE" = node ] && echo "npx 대신 직접 호출: node $HF_CLI"

hf init "$DIR" --resolution portrait --non-interactive --skip-skills >/dev/null
rm -f "$DIR/CLAUDE.md"   # 지침 파일은 AGENTS.md 하나만 둔다
cp "$HERE/$TPL.html" "$DIR/index.html"
mkdir -p "$DIR/assets/fonts" "$DIR/assets/photo" "$DIR/assets/art"

PRET="https://raw.githubusercontent.com/orioncactus/pretendard/v1.3.9/packages/pretendard/dist/public/static"
for w in SemiBold Bold ExtraBold Black; do
  f="$DIR/assets/fonts/Pretendard-$w.otf"
  if [ -f "$HOME/Library/Fonts/Pretendard-$w.otf" ]; then cp "$HOME/Library/Fonts/Pretendard-$w.otf" "$f"
  else curl -fsSL "$PRET/Pretendard-$w.otf" -o "$f"; fi
done

hf browser ensure >/dev/null   # 렌더용 크롬(헤드리스) 확인·설치
echo "준비 끝: $DIR (사진은 $DIR/assets/photo, 그림은 $DIR/assets/art)"
if [ "$HF_MODE" = node ]; then HFCMD="node $HF_CLI"; else HFCMD="npx hyperframes"; fi
echo "다음: [대괄호] 채우기 → $HFCMD check --json → snapshot → render --quality delivery -o out.mp4"

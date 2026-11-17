#!/usr/bin/env python3
"""gallery/blog/src/*.md -> 네이버 블로그 모바일 모양 HTML (390px). 사용: render.py src.md out.html"""
import html, json, os, re, sys

# 견본 사진(CC0): src/photos.json 에 {"B01": {"3": "folder_0"}} 처럼 적은 자리만 사진으로 채운다. 나머지는 회색 상자.
SRC = os.path.dirname(os.path.abspath(sys.argv[1])) if len(sys.argv) > 1 else "."
CODE = os.path.splitext(os.path.basename(sys.argv[1]))[0] if len(sys.argv) > 1 else ""
try:
    PHOTOS = json.load(open(os.path.join(SRC, "photos.json"), encoding="utf-8")).get(CODE, {})
except OSError:
    PHOTOS = {}

HEADER_WORDS = {"항목", "구분", "메뉴", "구성", "세트", "상자", "기준", "결제 방식", "내용", "요일", "시간"}

def esc(s):
    s = html.escape(s)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)

CAM = ('<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#9aa0a6" stroke-width="1.6">'
       '<path d="M4 8h3l2-2.5h6L17 8h3v11H4z"/><circle cx="12" cy="13" r="3.6"/></svg>')

def photo_block(items):
    n = len(items)
    cls = "ph1" if n == 1 else "phn"
    cells = []
    for num, desc in items:
        if num in PHOTOS:
            src = "file://" + os.path.join(SRC, "photos", PHOTOS[num] + ".jpg")
            cells.append(f'<div class="ph {cls} phimg"><img src="{src}" alt="{html.escape(desc)}"></div>')
            continue
        cells.append(f'<div class="ph {cls}"><div class="phin">{CAM}<div class="phl">사진 자리 {num}</div>'
                     f'<div class="phd">{esc(desc)}</div></div></div>')
    return f'<div class="phrow n{n}">' + "".join(cells) + "</div>"

def table_block(rows):
    cells = [[c.strip() for c in r.split("|")] for r in rows if r.strip()]
    head = cells and (len(cells[0]) > 2 or cells[0][0] in HEADER_WORDS)
    out = ['<table class="tb">']
    for i, r in enumerate(cells):
        tag = "th" if head and i == 0 else "td"
        out.append("<tr>" + "".join(
            f'<{tag} class="{"c0" if j == 0 else ""}">{esc(c)}</{tag}>' for j, c in enumerate(r)) + "</tr>")
    out.append("</table>")
    return "".join(out)

def map_block(arg):
    name, _, addr = arg.partition("|")
    return (f'<div class="map"><div class="mapimg"><div class="road r1"></div><div class="road r2"></div>'
            f'<div class="road r3"></div><div class="pin"><svg width="28" height="36" viewBox="0 0 24 32">'
            f'<path d="M12 0C5.4 0 0 5.2 0 11.7 0 20.5 12 32 12 32s12-11.5 12-20.3C24 5.2 18.6 0 12 0z" fill="#03c75a"/>'
            f'<circle cx="12" cy="11.5" r="4.5" fill="#fff"/></svg></div></div>'
            f'<div class="mapcard"><div class="mapn">{esc(name.strip())}</div><div class="mapa">{esc(addr.strip())}</div>'
            f'<div class="mapb">지도 블록 (네이버 플레이스 연결 자리)</div></div></div>')

def parse(path):
    raw = open(path, encoding="utf-8").read()
    m = re.search(r"<!--\s*견본:(.*?)-->", raw, re.S)
    label = m.group(1).strip() if m else ""
    parts = re.split(r"^---\s*$", raw, flags=re.M)
    head, body = parts[0], parts[1]
    meta = {}
    for line in head.splitlines():
        if ":" in line and not line.startswith("<!--"):
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return label, meta, body

def body_html(body):
    blocks, para, mid_done = [], [], 0
    lines = body.strip("\n").splitlines()
    i = 0
    qcount = 0
    def flush():
        if para:
            blocks.append("<p>" + "<br>".join(esc(x) for x in para) + "</p>")
            para.clear()
    while i < len(lines):
        ln = lines[i].strip()
        if not ln:
            flush(); i += 1; continue
        if ln == "[표]":
            flush(); rows = []
            i += 1
            while i < len(lines) and lines[i].strip() != "[/표]":
                rows.append(lines[i]); i += 1
            blocks.append(table_block(rows)); i += 1; continue
        q = re.fullmatch(r"\[인용구\]\s*(.+?)\s*\[/인용구\]", ln)
        if q:
            flush(); qcount += 1
            mid = ' id="mid"' if qcount == 2 else ""
            blocks.append(f'<div class="qt"{mid}><span class="qm">“</span><div class="qtx">{esc(q.group(1))}</div><span class="qm">”</span></div>')
            i += 1; continue
        ph = re.findall(r"\[사진(\d+):\s*([^\]]+)\]", ln)
        if ph and re.fullmatch(r"(\s*\[사진\d+:[^\]]+\]\s*)+", ln):
            flush(); blocks.append(photo_block(ph)); i += 1; continue
        if ln == "[구분선]":
            flush(); blocks.append('<div class="hr"><span></span><span></span><span></span></div>'); i += 1; continue
        mp = re.fullmatch(r"\[지도:\s*(.+)\]", ln)
        if mp:
            flush(); blocks.append(map_block(mp.group(1))); i += 1; continue
        para.append(ln); i += 1
    flush()
    return "\n".join(blocks), qcount

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:#fff;width:390px;overflow:hidden}
body{font-family:"Apple SD Gothic Neo","Noto Sans KR",sans-serif;color:#222;-webkit-font-smoothing:antialiased}
.frame{position:relative;overflow:hidden;width:390px}
.bar{height:48px;display:flex;align-items:center;justify-content:space-between;padding:0 14px;border-bottom:1px solid #eee;font-size:15px;color:#111}
.bar .bn{font-weight:700;font-size:15px;max-width:250px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar .ic{color:#555;font-size:18px;letter-spacing:6px}
.badge{background:#fff7d6;color:#7a5a00;font-size:12px;padding:7px 16px;border-bottom:1px solid #f0e2a8;line-height:1.45}
.badge b{color:#5a4200}
.hd{padding:22px 20px 16px;border-bottom:1px solid #eee}
.cat{color:#03a94f;font-size:13px;margin-bottom:9px}
.ttl{font-size:22px;line-height:1.42;font-weight:700;letter-spacing:-0.4px;color:#111;word-break:keep-all}
.au{display:flex;align-items:center;margin-top:16px}
.av{width:34px;height:34px;border-radius:50%;background:#d8ead9;color:#2f6b3a;font-size:14px;font-weight:700;display:flex;align-items:center;justify-content:center;margin-right:10px}
.aun{font-size:13.5px;font-weight:600;color:#333}.aud{font-size:12px;color:#999;margin-top:2px}
.flag{font-size:11.5px;color:#888;margin-top:12px}
.bd{padding:6px 0 24px}
.bd p{font-size:16px;line-height:1.85;color:#333;padding:0 20px;margin:14px 0;word-break:keep-all;letter-spacing:-0.2px}
.bd p b{color:#111}
.phrow{display:flex;gap:3px;margin:16px 0}
.ph{background:#e8eaed;display:flex;align-items:center;justify-content:center;text-align:center}
.ph1{width:390px;height:220px}
.phn{flex:1;height:150px}
.phrow.n3 .phn{height:130px}
.phin{padding:0 14px}
.phimg{background:#ddd;overflow:hidden}.phimg img{width:100%;height:100%;object-fit:cover;display:block}
.phl{font-size:12.5px;font-weight:700;color:#80868b;margin-top:4px}
.phd{font-size:12.5px;color:#5f6368;margin-top:4px;line-height:1.45;word-break:keep-all}
.phrow.n3 .phd{font-size:11px}
.qt{margin:34px 24px 18px;text-align:center}
.qm{display:block;font-family:Georgia,serif;font-size:40px;line-height:26px;color:#c4c4c4;height:26px}
.qtx{font-size:18.5px;font-weight:700;color:#111;line-height:1.5;padding:8px 0;word-break:keep-all}
.tb{width:350px;margin:16px 20px;border-collapse:collapse;font-size:13.5px;line-height:1.5;color:#333}
.tb td,.tb th{border:1px solid #dcdcdc;padding:8px 9px;vertical-align:top;word-break:keep-all;text-align:left}
.tb th{background:#f4f6f5;font-weight:700}
.tb td.c0{background:#fafafa;font-weight:600;white-space:nowrap}
.hr{display:flex;justify-content:center;gap:9px;margin:30px 0}
.hr span{width:5px;height:5px;border-radius:50%;background:#bbb}
.map{margin:22px 20px;border:1px solid #e2e2e2;border-radius:6px;overflow:hidden}
.mapimg{position:relative;height:150px;background:#eef1ea;
 background-image:linear-gradient(#e3e7df 1px,transparent 1px),linear-gradient(90deg,#e3e7df 1px,transparent 1px);background-size:26px 26px}
.road{position:absolute;background:#fff;border:1px solid #dde2d8}
.r1{left:0;right:0;top:62px;height:14px}.r2{top:0;bottom:0;left:150px;width:12px}.r3{left:0;right:0;top:118px;height:8px;transform:rotate(-8deg)}
.pin{position:absolute;left:170px;top:40px}
.mapcard{padding:11px 14px;background:#fff}
.mapn{font-size:15px;font-weight:700;color:#111}.mapa{font-size:13px;color:#666;margin-top:3px}.mapb{font-size:11.5px;color:#03a94f;margin-top:5px}
.tags{padding:6px 20px 18px;display:flex;flex-wrap:wrap;gap:6px}
.tags span{font-size:13px;color:#4a6ea8;background:#f1f4f9;border-radius:14px;padding:4px 10px}
.foot{word-break:keep-all;font-size:12px;color:#777;background:#f6f6f6;padding:12px 20px;line-height:1.55;border-top:1px solid #eee}
.cut{height:44px;display:flex;align-items:center;justify-content:center;background:
 repeating-linear-gradient(135deg,#f3f3f3 0 8px,#fafafa 8px 16px);color:#888;font-size:12.5px;border-top:1px dashed #ccc;border-bottom:1px dashed #ccc}
.bot{height:40px;background:#333;color:#fff;font-size:12px;display:flex;align-items:center;justify-content:center;letter-spacing:-0.2px}
"""

def page(src, mode):
    label, meta, body = parse(src)
    bh, qcount = body_html(body)
    name = meta.get("작성자", "")
    av = html.escape(name[:1] or "블")
    tags = "".join(f"<span>{html.escape(t)}</span>" for t in meta.get("태그", "").split())
    lab = [x.strip() for x in label.split(" · ")]
    badge = f'<div class="badge"><b>견본</b> · {html.escape(" · ".join(lab[:2]))}<br>스킬이 만든 예시 글 · 상호·인물·숫자는 가상</div>'
    post = f"""
<div class="bar"><span class="ic">←</span><span class="bn">{html.escape(meta.get('블로그',''))}</span><span class="ic">⋯</span></div>
{badge}
<div class="hd"><div class="cat">{html.escape(meta.get('카테고리',''))}</div>
<div class="ttl">{esc(meta.get('제목',''))}</div>
<div class="au"><div class="av">{av}</div><div><div class="aun">{html.escape(name)}</div><div class="aud">{html.escape(meta.get('날짜',''))}</div></div></div>
</div>
<div class="bd">{bh}</div>
<div class="tags">{tags}</div>
<div class="foot">※ 견본 안내: 스킬이 만든 예시입니다. 상호·인물·가격·숫자·주소는 모두 가상이며 실제 업체와 관계없습니다.</div>
"""
    if mode == "full":
        content = f'<style>.ph1{{height:150px}}</style><div class="frame" id="all">{post}</div>'
        script = "document.title=String(document.getElementById('all').offsetHeight)"
    else:
        H1, H2 = 1010, 520
        content = (f'<div class="frame" id="f1" style="height:{H1}px">{post}</div>'
                   f'<div class="cut">··· 중간 생략 · 아래는 글 중간 부분 ···</div>'
                   f'<div class="frame" id="f2" style="height:{H2}px"><div id="m2" style="position:relative">{post}</div></div>'
                   f'<div class="bot">스킬이 만든 견본 · 상호·인물·숫자는 가상</div>')
        script = ("function blocks(r){return Array.prototype.slice.call(r.querySelectorAll('.bar,.badge,.hd,.bd > *'));}"
                  "function bottom(e){return e.offsetTop+e.offsetHeight;}"
                  "function fit(r,top,lim){var best=0;blocks(r).forEach(function(e){var b=bottom(e)-top;if(e.offsetTop>=top-1&&b<=lim&&b>best&&!e.classList.contains('qt'))best=b;});return best>lim*0.6?best+10:lim;}"
                  "var f1=document.getElementById('f1');f1.style.height=fit(f1,0,"+str(H1)+")+'px';"
                  "var m=document.getElementById('m2');var t=m.querySelector('#mid');"
                  "var ps=m.querySelectorAll('.bd > p');"
                  "var y=t?t.offsetTop-14:ps[Math.floor(ps.length*0.5)].offsetTop-10;"
                  "var h1=f1.offsetHeight;if(y<h1)y=h1;m.style.top=(-y)+'px';"
                  "var f2=document.getElementById('f2');f2.style.height=fit(m,y,"+str(H2)+")+'px';"
                  "document.title=String(document.body.scrollHeight);")
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=390">
<title>견본</title><style>{CSS}</style></head><body style="position:relative">{content}<script>{script}</script></body></html>"""

if __name__ == "__main__":
    src, out, mode = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "split")
    open(out, "w", encoding="utf-8").write(page(src, mode))

#!/usr/bin/env python3
"""카드뉴스 HTML 렌더러 (기본 경로).

원고 JSON → 장마다 HTML(templates/cardnews-html 의 base.css + 테마) → 헤드리스 크롬으로 1080×1350 PNG.
글자·숫자·레이아웃은 HTML이 그린다(웹폰트, 자간·행간, 한글 어절 줄바꿈). 표지·단독 포스터는
이미지 생성 그림을 `layout: image`로 그대로 깔고 머리말·쪽번호만 얹을 수 있다.
Pillow 렌더러(tools/cardnews.py)는 크롬이 없을 때 쓰는 대체 경로다.

사용법:
  python3 cardnews_html.py render spec.json -o out/          # out/01.png… + 01.jpg…(Pillow 있으면) + check.json + cardnews.html
  python3 cardnews_html.py render spec.json -o out/ --html-only   # HTML만 (네 브라우저로 #card01… 캡처)
  python3 cardnews_html.py sheet out/ -o sheet.png [--ref a.jpg b.jpg …]   # 한 장 시트(레퍼런스와 나란히), Pillow 필요
  python3 cardnews_html.py cutout art/*.png -o art/cut --drop-edge   # 생성 그림 바탕을 투명하게(Pillow)
  python3 cardnews_html.py layouts                            # 레이아웃·테마 목록

크롬 찾는 순서: 환경변수 CHROME → 파이썬 playwright → playwright 번들 크롬(~/Library/Caches/ms-playwright,
~/.cache/ms-playwright) → 설치된 Google Chrome/Chromium. 없으면 HTML을 남기고 안내한다.
표준 라이브러리만으로 돈다(Pillow·playwright는 있으면 씀).
"""
import argparse
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

VERSION = "1.0.0"
BASE_URL = "https://raw.githubusercontent.com/Whosekey-Labs/kr-marketing-skill/main/"
HERE = Path(__file__).resolve().parent
TPL_CANDIDATES = [HERE.parent / "templates" / "cardnews-html", HERE / "cardnews-html"]
THEMES = {"A": "a-photo.css", "B": "b-illust.css", "C": "c-magazine.css"}
THEME_NOTE = {
    "A": "실사진 + 하단 큰 흰 글씨. 사장님 실제 사진이 있을 때(표지 사진, 본문 흰 모눈)",
    "B": "캐릭터 일러스트 + 큰 제목. 크림 바탕, 말풍선, 결론 상자(그림은 이미지 생성)",
    "C": "미니멀 매거진. 검정 바탕, 흰 제목, 형광 강조 1색, 긴 글·전문 정보",
}
LAYOUTS = {
    "image": "이미지 생성 표지·포스터 한 장을 꽉 채움(+ 머리말·쪽번호 얹기 선택)",
    "cover": "HTML 표지: 큰 제목 2~4줄 + 부제 (+ photo 꽉 채움 또는 art 그림)",
    "list": "번호 리스트 2~4개 (items: [{title, text}])",
    "vs": "두 칸 비교 (left/right: {label, items}, good: 'left'|'right')",
    "qa": "질문 크게 + 그림·말풍선 + 결론 상자 (q, a)",
    "number": "숫자 하나 크게 (value, unit, label, chips)",
    "checklist": "저장용 체크리스트 메모지 (items: [{title, text}])",
    "steps": "단계 1→2→3 (items: [{title, text}])",
    "text": "제목 + 짧은 글 + 그림/말풍선 (설명형·공감 장)",
    "photo": "사진 칸 + 제목·짧은 글 (갈래 A 본문)",
    "cta": "마지막 장: 행동 1개 + 정보 + 버튼",
}
FONT_LINKS = [
    "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css",
    "https://fonts.googleapis.com/css2?family=Gaegu:wght@400;700&family=Gowun+Batang:wght@400;700&display=block",
]


# ───────────────────────── 글 표기 ─────────────────────────
def md(s):
    """*강조* → em(강조색), ==형광펜== → mark, __밑줄__ → u, 줄바꿈 → <br>."""
    if s is None:
        return ""
    t = html.escape(str(s))
    t = re.sub(r"==(.+?)==", r"<mark>\1</mark>", t)
    t = re.sub(r"__(.+?)__", r"<u>\1</u>", t)
    t = re.sub(r"\*(.+?)\*", r"<em>\1</em>", t)
    return t.replace("\n", "<br>")


def plain(s):
    return re.sub(r"[*=_]", "", str(s or ""))


def esc(s):
    return html.escape(str(s or ""), quote=True)


# ───────────────────────── 템플릿 파일 ─────────────────────────
def tpl_dir():
    for d in TPL_CANDIDATES:
        if (d / "base.css").exists():
            return d
    cache = Path.home() / ".cache" / "kr-cardnews" / "cardnews-html"
    if not (cache / "base.css").exists():
        (cache / "themes").mkdir(parents=True, exist_ok=True)
        for rel in ["base.css"] + ["themes/" + f for f in THEMES.values()]:
            url = BASE_URL + "templates/cardnews-html/" + rel
            try:
                urllib.request.urlretrieve(url, cache / rel)
            except Exception as e:  # noqa: BLE001
                sys.exit(f"템플릿을 못 받았어요({url}): {e}\n저장소의 templates/cardnews-html 폴더를 이 스크립트 옆(../templates)에 두세요.")
    return cache


def uri(path, base):
    if not path:
        return ""
    if re.match(r"^(https?|data|file):", path):
        return path
    p = (base / path).resolve()
    return p.as_uri()


# ───────────────────────── 부품 ─────────────────────────
POS_KEYS = ("left", "right", "top", "bottom")


def pos_style(d):
    st = []
    for k in POS_KEYS:
        if k in d:
            st.append(f"{k}:{d[k]}px")
    if "w" in d:
        st.append(f"width:{d['w']}px")
    if "h" in d:
        st.append(f"height:{d['h']}px")
    if "rotate" in d:
        st.append(f"transform:rotate({d['rotate']}deg)")
    if "z" in d:
        st.append(f"z-index:{d['z']}")
    return ";".join(st)


def arts(slide, base, missing):
    out = []
    items = slide.get("art") or []
    if isinstance(items, (dict, str)):
        items = [items]
    for a in items:
        if isinstance(a, str):
            a = {"src": a, "right": 40, "bottom": 110, "w": 460}
        src = a.get("src", "")
        if src and not re.match(r"^(https?|data):", src) and not (base / src).exists():
            missing.append(src)
        cls = "art" + (" blend" if a.get("blend", True) else "") + (" round" if a.get("round") else "")
        crop = ""
        if a.get("crop"):  # [x, y, w, h] 비율(0~1) — 캐릭터 시트에서 한 칸만
            x, y, w, h = a["crop"]
            crop = (f' style="width:{100 / w:.4f}%;height:{100 / h:.4f}%;max-width:none;object-fit:fill;'
                    f'transform:translate({-x * 100:.4f}%,{-y * 100:.4f}%)"')
            cls += " cropbox"
        style = pos_style(a) + (";overflow:hidden" if crop else "")
        out.append(f'<div class="{cls}" style="{style}"><img src="{esc(uri(src, base))}"{crop}></div>')
    return "".join(out)


def bubbles(slide):
    out = []
    for b in slide.get("bubbles") or []:
        tail = {"right": " tail-right", "side": " tail-left-side"}.get(b.get("tail", ""), "")
        size = f";font-size:{b['size']}px" if "size" in b else ""
        out.append(f'<div class="bubble{tail}" style="position:absolute;{pos_style(b)}{size};z-index:3">{md(b["text"])}</div>')
    return "".join(out)


def stickers(slide):
    """자유 글자(손글씨 메모·숫자 얹기). {text, left, top, size, color, font: hand|title, rotate, bg}"""
    out = []
    for s in slide.get("stickers") or []:
        fam = {"hand": "var(--f-hand)", "title": "var(--f-title)", "serif": "var(--f-serif)"}.get(s.get("font", "title"))
        bg = f";background:{s['bg']};padding:8px 20px;border-radius:12px" if s.get("bg") else ""
        st = (f"position:absolute;{pos_style(s)};font-family:{fam};font-size:{s.get('size', 40)}px;"
              f"font-weight:{s.get('weight', 800)};color:{s.get('color', 'var(--ink)')};line-height:1.15;z-index:4;"
              f"text-align:{s.get('align', 'left')};white-space:nowrap{bg}")
        out.append(f'<div class="sticker" style="{st}">{md(s["text"])}</div>')
    return "".join(out)


def head_block(slide, cls="h"):
    out = ""
    if slide.get("kicker"):
        out += f'<div class="kicker">{md(slide["kicker"])}</div>'
    h = slide.get("heading") or slide.get("title")
    if h:
        size = f' style="font-size:{slide["h_size"]}px"' if slide.get("h_size") else ""
        out += f'<h2 class="{cls}" data-fit="1"{size}>{md(h)}</h2>'
    if slide.get("lead") or slide.get("text"):
        out += f'<p class="lead">{md(slide.get("lead") or slide.get("text"))}</p>'
    return out


def tail_block(slide):
    out = ""
    if slide.get("gap") is not None:
        out += f'<div style="height:{slide["gap"]}px;flex:none"></div>'
    else:
        out += '<div class="spacer"></div>'
    if slide.get("conclude"):
        ic = slide.get("conclude_icon", "💡")
        ic_html = f'<span class="ic">{esc(ic)}</span>' if ic else ""
        out += f'<div class="conclude">{ic_html}{md(slide["conclude"])}</div>'
    if slide.get("note"):
        out += f'<p class="note">{md(slide["note"])}</p>'
    return out


def items_of(slide):
    res = []
    for it in slide.get("items") or []:
        if isinstance(it, str):
            it = {"title": it}
        res.append(it)
    return res


# ───────────────────────── 레이아웃 ─────────────────────────
def L_list(s, ctx):
    rows = []
    for i, it in enumerate(items_of(s), 1):
        n = esc(it.get("num", i))
        tx = f'<div class="ix">{md(it["text"])}</div>' if it.get("text") else ""
        rows.append(f'<div class="item"><div class="num">{n}</div><div><div class="it">{md(it["title"])}</div>{tx}</div></div>')
    w = f' style="max-width:{s["items_w"]}px"' if s.get("items_w") else ""
    return head_block(s) + f'<div class="items"{w}>{"".join(rows)}</div>' + tail_block(s)


def L_vs(s, ctx):
    def col(c, good):
        lis = "".join(f"<li>{md(x)}</li>" for x in c.get("items", []))
        return f'<div class="col{" good" if good else ""}"><span class="ch">{md(c.get("label", ""))}</span><ul>{lis}</ul></div>'
    good = s.get("good", "right")
    mark = f'<div class="vsmark">{esc(s.get("vs_mark", "VS"))}</div>' if s.get("vs_mark", "VS") else ""
    return head_block(s) + (f'<div class="cols">{col(s.get("left", {}), good == "left")}'
                            f'{col(s.get("right", {}), good == "right")}{mark}</div>') + tail_block(s)


def L_qa(s, ctx):
    q = f'<div class="qline"><span class="qmark">Q.</span><h2 class="h" data-fit="1">{md(s.get("q", ""))}</h2></div>'
    k = f'<div class="kicker">{md(s["kicker"])}</div>' if s.get("kicker") else ""
    lead = f'<p class="lead" style="margin-top:26px">{md(s["lead"])}</p>' if s.get("lead") else ""
    s2 = dict(s)
    if s.get("a") and not s.get("conclude"):
        s2["conclude"] = s["a"]
        s2["conclude_icon"] = s.get("conclude_icon", "A")
    return k + q + lead + tail_block(s2)


def L_number(s, ctx):
    unit = f"<small>{md(s['unit'])}</small>" if s.get("unit") else ""
    size = f' style="font-size:{s["value_size"]}px"' if s.get("value_size") else ""
    big = f'<div class="big"{size}>{md(s.get("value", ""))}{unit}</div>'
    lab = f'<div class="blabel">{md(s["label"])}</div>' if s.get("label") else ""
    chips = ""
    if s.get("chips"):
        cw = f";max-width:{s['chips_w']}px" if s.get("chips_w") else ""
        chips = f'<div class="chips" style="margin-top:30px{cw}">' + "".join(f'<span class="chip">{md(c)}</span>' for c in s["chips"]) + "</div>"
    return head_block(s) + big + lab + chips + tail_block(s)


def L_checklist(s, ctx):
    rows = []
    for it in items_of(s):
        tx = f'<div class="cx">{md(it["text"])}</div>' if it.get("text") else ""
        rows.append(f'<div class="ck"><div class="box">✓</div><div><div class="ct">{md(it["title"])}</div>{tx}</div></div>')
    tape = '<span class="tape"></span>' if s.get("tape") else ""
    return head_block(s) + f'<div class="memo">{tape}{"".join(rows)}</div>' + tail_block(s)


def L_steps(s, ctx):
    rows = []
    for i, it in enumerate(items_of(s), 1):
        tx = f'<div class="stx">{md(it["text"])}</div>' if it.get("text") else ""
        im = f'<img class="sti" src="{esc(uri(it["img"], ctx["base"]))}">' if it.get("img") else ""
        rows.append(f'<div class="st"><div class="sn"><div><small>STEP</small><b>{i}</b></div></div>'
                    f'<div class="stbody"><div class="stt">{md(it["title"])}</div>{tx}</div>{im}</div>')
    w = f' style="max-width:{s["items_w"]}px"' if s.get("items_w") else ""
    return head_block(s) + f'<div class="track"{w}>{"".join(rows)}</div>' + tail_block(s)


def L_text(s, ctx):
    return head_block(s) + tail_block(s)


def L_photo(s, ctx):
    img = f'<div class="photo-box"><img src="{esc(uri(s.get("photo"), ctx["base"]))}"></div>' if s.get("photo") else ""
    s2 = dict(s, gap=s.get("gap", 0))
    return head_block(s) + img + tail_block(s2)


def L_cover(s, ctx):
    k = f'<div class="kicker">{md(s["kicker"])}</div>' if s.get("kicker") else ""
    size = f' style="font-size:{s["t_size"]}px"' if s.get("t_size") else ""
    t = f'<h1 class="ctitle" data-fit="1"{size}>{md(s.get("title", ""))}</h1>'
    sub = f'<p class="csub">{md(s["subtitle"])}</p>' if s.get("subtitle") else ""
    return k + t + sub + ('<div class="spacer"></div>' if not s.get("photo") else "")


def L_cta(s, ctx):
    k = f'<div class="kicker">{md(s["kicker"])}</div>' if s.get("kicker") else ""
    t = f'<h1 class="ctitle title" data-fit="1">{md(s.get("title", ""))}</h1>'
    tx = f'<p class="lead" style="margin-top:28px">{md(s["text"])}</p>' if s.get("text") else ""
    info = ""
    if s.get("info"):
        info = '<dl class="info">' + "".join(f"<dt>{md(a)}</dt><dd>{md(b)}</dd>" for a, b in s["info"]) + "</dl>"
    bst = ""
    if s.get("button_color"):
        bst = f' style="background:{esc(s["button_color"])};color:{esc(s.get("button_text_color", "#191919"))}"'
    btn = f'<div class="spacer"></div><div class="btn"{bst}>{md(s["button"])}</div>' if s.get("button") else ""
    save = f'<p class="save">{md(s["save"])}</p>' if s.get("save") else ""
    return k + t + tx + info + btn + save


RENDER = {"list": L_list, "vs": L_vs, "qa": L_qa, "number": L_number, "checklist": L_checklist,
          "steps": L_steps, "text": L_text, "photo": L_photo, "cover": L_cover, "cta": L_cta}


def build_card(s, i, n, spec, ctx):
    theme = (s.get("theme") or spec.get("theme") or "B").upper()
    layout = s.get("layout", "text")
    cls = ["card", f"theme-{theme.lower()}", layout]
    dark = theme == "C" or s.get("dark")
    if s.get("photo") and layout == "cover":
        cls.append("photo")
        dark = True
    if dark:
        cls.append("on-dark")
    style = ""
    if s.get("bg"):
        style = f' style="background:{esc(s["bg"])}"'
    inner = ""
    if layout == "image":
        src = s.get("image", "")
        if src and not (ctx["base"] / src).exists():
            ctx["missing"].append(src)
        inner += f'<img class="full" src="{esc(uri(src, ctx["base"]))}">'
        cls[2] = "image-only"
    elif layout == "cover" and s.get("photo"):
        inner += f'<img class="bgimg" src="{esc(uri(s["photo"], ctx["base"]))}" style="object-position:{esc(s.get("focus", "50% 50%"))}"><div class="shade"></div>'
    # 시리즈 틀
    chrome = s.get("chrome", spec.get("chrome", True))
    if chrome:
        lab = ""
        if spec.get("series"):
            ep = f'<span class="ep">{esc(spec["ep"])}</span>' if spec.get("ep") else ""
            lab = f'<span class="label">{esc(spec["series"])}{ep}</span>'
        page = f'<span class="page">{i}/{n}</span>' if spec.get("page_numbers", True) else ""
        inner += f'<div class="chrome-top">{lab}<span></span>{page}</div>'
        acct = esc(spec.get("account", ""))
        if theme == "C" and spec.get("account_vertical"):
            acct = "<br>".join(esc(x) for x in spec["account_vertical"])
        swipe = '<span class="swipe">&gt;&gt;</span>' if i < n and s.get("swipe", True) else "<span></span>"
        inner += f'<div class="chrome-foot"><span class="acct">{acct}</span>{swipe}</div>'
    if layout != "image":
        body_style = ""
        if s.get("body_top") is not None:
            body_style += f"top:{s['body_top']}px;"
        if s.get("body_bottom") is not None:
            body_style += f"bottom:{s['body_bottom']}px;"
        if s.get("body_right") is not None:
            body_style += f"right:{s['body_right']}px;"
        if s.get("align") == "center":
            body_style += "text-align:center;align-items:center;"
        inner += f'<div class="body" style="{body_style}">{RENDER[layout](s, ctx)}</div>'
    inner += arts(s, ctx["base"], ctx["missing"]) + bubbles(s) + stickers(s)
    return f'<section class="{" ".join(cls)}" id="card{i:02d}"{style}>{inner}</section>'


FIT_JS = r"""
<script>
(function(){
  function fit(){
    var report=[];
    document.querySelectorAll('.card').forEach(function(card){
      var body=card.querySelector('.body');
      card.querySelectorAll('[data-fit]').forEach(function(el){
        var fs=parseFloat(getComputedStyle(el).fontSize), min=fs*0.62, guard=0;
        // 제목 한 줄이 칸 폭을 넘거나 본문 칸이 넘치면 줄인다(최대 38%)
        while(guard++<60 && fs>min && (el.scrollWidth>el.clientWidth+1 || (body && body.scrollHeight>body.clientHeight+1))){
          fs-=2; el.style.fontSize=fs+'px';
        }
      });
      var r={id:card.id, overflow:false, shrunk:[]};
      if(body && body.scrollHeight>body.clientHeight+1){ r.overflow=true; card.setAttribute('data-overflow','1'); }
      card.querySelectorAll('[data-fit]').forEach(function(el){
        if(el.style.fontSize){ r.shrunk.push(el.style.fontSize); }
        // 한 글자만 남은 줄 찾기
      });
      var imgs=[].slice.call(card.querySelectorAll('img')).filter(function(im){return !im.complete||im.naturalWidth===0;});
      r.broken_images=imgs.map(function(im){return im.getAttribute('src');});
      report.push(r);
    });
    window.__report=report; document.body.setAttribute('data-ready','1');
  }
  var go=function(){ (document.fonts&&document.fonts.ready?document.fonts.ready:Promise.resolve()).then(function(){ setTimeout(fit,60); }); };
  if(document.readyState==='complete') go(); else window.addEventListener('load', go);
})();
</script>"""


def page_html(cards_html, spec, tdir, only_one=False):
    theme = (spec.get("theme") or "B").upper()
    css = [tdir / "base.css"] + [tdir / "themes" / f for f in THEMES.values()]
    links = "".join(f'<link rel="stylesheet" href="{u}">' for u in FONT_LINKS)
    links += "".join(f'<link rel="stylesheet" href="{p.resolve().as_uri()}">' for p in css)
    c = spec.get("brand", {}).get("colors", {})
    var_map = {"bg": "--bg", "bg2": "--bg2", "text": "--ink", "ink": "--ink", "sub": "--sub", "main": "--main",
               "accent": "--accent", "marker": "--marker", "on_main": "--on-main"}
    vars_ = ";".join(f"{var_map[k]}:{v}" for k, v in c.items() if k in var_map)
    over = f"<style>.card.theme-{theme.lower()}{{{vars_}}}</style>" if vars_ else ""
    extra = f"<style>{spec['css']}</style>" if spec.get("css") else ""
    bodycss = "<style>html,body{background:transparent}.card+.card{margin-top:0}</style>" if only_one else ""
    mk = c.get("marker") or {"A": "#CFE0FF", "B": "#FFD86B", "C": "#C6F35E"}.get(theme, "#FFD86B")
    brush = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 40' preserveAspectRatio='none'>"
             f"<path fill='{mk}' d='M3 14 C20 8 40 11 62 9 S120 7 150 9 S190 6 197 11 L195 19 C197 25 193 31 196 35 "
             "C170 38 140 34 110 37 S50 36 20 38 S4 34 6 28 C2 22 5 18 3 14Z'/></svg>")
    import urllib.parse as _u
    brush_css = ("<style>mark{background:url(\"data:image/svg+xml," + _u.quote(brush) + "\") 0 62%/100% 58% no-repeat;"
                 "padding:0 .12em;margin:0 -.04em}</style>")
    rough = ('<svg width="0" height="0" style="position:absolute"><filter id="rough" x="-5%" y="-5%" width="110%" height="110%">'
             '<feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="2" seed="7"/>'
             '<feDisplacementMap in="SourceGraphic" scale="5"/></filter></svg>')
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=1080">{links}{over}{extra}{bodycss}</head>'
            f"{brush_css}<body>{rough}{cards_html}{FIT_JS}</body></html>")


# ───────────────────────── 점검 ─────────────────────────
def lint(spec):
    warn, fix = [], []
    slides = spec.get("slides", [])
    if len(slides) > 10:
        fix.append(f"장수 {len(slides)}장: 10장 이하로")
    for i, s in enumerate(slides, 1):
        lay = s.get("layout", "text")
        if lay not in RENDER and lay != "image":
            fix.append(f"{i}장: 모르는 레이아웃 '{lay}'")
        if i == 1 and lay == "cover":
            n = len(re.sub(r"\s", "", plain(s.get("title"))))
            if not 8 <= n <= 22:
                warn.append(f"1장 표지 제목 {n}자(공백 빼고): 12~19자 권장")
        allt = " ".join(plain(s.get(k)) for k in ("heading", "title", "text", "lead", "q", "a", "conclude"))
        allt += " ".join(plain(it.get("title", "")) + plain(it.get("text", "")) for it in items_of(s))
        if "[직접 입력" in allt:
            fix.append(f"{i}장: [직접 입력] 빈칸이 남음")
        body_len = len(re.sub(r"\s", "", allt))
        if lay not in ("image", "cover") and body_len > 170:
            warn.append(f"{i}장: 글자 {body_len}자 — 한 장 한 가지(120자 안팎)로 줄이거나 나누기")
        em = len(re.findall(r"\*[^*]+\*|==[^=]+==", json.dumps(s, ensure_ascii=False)))
        if em > 3:
            warn.append(f"{i}장: 강조 {em}곳 — 2곳 이하 권장")
    lays = [s.get("layout", "text") for s in slides]
    for a in range(len(lays) - 2):
        if lays[a] == lays[a + 1] == lays[a + 2] and lays[a] not in ("image",):
            fix.append(f"{a + 1}~{a + 3}장: 같은 레이아웃 3장 연속")
    if slides and slides[-1].get("layout") != "cta":
        warn.append("마지막 장이 cta가 아님: 행동 1개로 끝내기")
    return warn, fix


# ───────────────────────── 캡처 ─────────────────────────
def find_chrome():
    if os.environ.get("CHROME") and Path(os.environ["CHROME"]).exists():
        return os.environ["CHROME"]
    pats = [
        "~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        "~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
        "~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome",
        "~/AppData/Local/ms-playwright/chromium-*/chrome-win*/chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for p in pats:
        hits = sorted(glob.glob(os.path.expanduser(p)))
        if hits:
            return hits[-1]
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        w = shutil.which(name)
        if w:
            return w
    return None


def capture_playwright(files, out, scale):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    reports = []
    exe = find_chrome()
    with sync_playwright() as p:
        kw = {}
        if exe and "ms-playwright" not in exe:
            kw["executable_path"] = exe
        try:
            br = p.chromium.launch(**kw)
        except Exception:  # noqa: BLE001
            if not exe:
                return None
            br = p.chromium.launch(executable_path=exe)
        pg = br.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=scale)
        for i, f in enumerate(files, 1):
            pg.goto(f.resolve().as_uri(), wait_until="networkidle")
            pg.wait_for_selector("body[data-ready='1']", timeout=20000)
            reports += pg.evaluate("window.__report") or []
            pg.locator(f"#card{i:02d}").screenshot(path=str(out / f"{i:02d}.png"))
        br.close()
    return reports


def capture_cli(files, out, exe):
    for i, f in enumerate(files, 1):
        cmd = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
               "--window-size=1080,1350", "--virtual-time-budget=8000", f"--screenshot={out / f'{i:02d}.png'}",
               f.resolve().as_uri()]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    return []


def to_jpeg(out, n):
    try:
        from PIL import Image
    except ImportError:
        return False
    for i in range(1, n + 1):
        p = out / f"{i:02d}.png"
        if p.exists():
            Image.open(p).convert("RGB").save(out / f"{i:02d}.jpg", quality=92, optimize=True)
    return True


def cmd_render(a):
    spec_path = Path(a.spec).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tdir = tpl_dir()
    ctx = {"base": spec_path.parent, "missing": []}
    slides = spec.get("slides", [])
    n = len(slides)
    cards = [build_card(s, i, n, spec, ctx) for i, s in enumerate(slides, 1)]
    (out / "cardnews.html").write_text(page_html("".join(cards), spec, tdir), encoding="utf-8")
    files = []
    for i, c in enumerate(cards, 1):
        f = out / f"card{i:02d}.html"
        f.write_text(page_html(c, spec, tdir, only_one=True), encoding="utf-8")
        files.append(f)
    warn, fix = lint(spec)
    for m in sorted(set(ctx["missing"])):
        fix.append(f"그림 없음: {m}")
    engine = "html-only"
    reports = []
    if not a.html_only:
        reports = capture_playwright(files, out, a.scale)
        if reports is not None:
            engine = "playwright"
        else:
            reports = []
            exe = find_chrome()
            if exe:
                capture_cli(files, out, exe)
                engine = "chrome-cli"
            else:
                print("크롬(헤드리스 브라우저)을 못 찾았어요. 아래 중 하나로 하세요:\n"
                      "  1) `pip install playwright && python3 -m playwright install chromium` 후 다시 실행\n"
                      f"  2) 네 브라우저로 {out / 'cardnews.html'} 을 열고 #card01, #card02 … 요소를 1080×1350으로 캡처\n"
                      "  3) Pillow 대체 경로: python3 cardnews.py render (tools/cardnews.py)")
    for r in reports:
        if r.get("overflow"):
            fix.append(f"{r['id'][4:]}장: 글이 칸을 넘침 — 글을 줄이거나 장을 나누기")
        if r.get("shrunk"):
            warn.append(f"{r['id'][4:]}장: 제목을 줄여 맞춤({', '.join(r['shrunk'])})")
        for b in r.get("broken_images") or []:
            fix.append(f"{r['id'][4:]}장: 그림을 못 읽음 {b}")
    jpg = to_jpeg(out, n) if engine != "html-only" else False
    check = {"version": VERSION, "engine": engine, "slides": n, "fix": fix, "warn": warn, "jpeg": jpg}
    (out / "check.json").write_text(json.dumps(check, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{engine}] {n}장 → {out}")
    for m in fix:
        print("  [고칠 것]", m)
    for m in warn:
        print("  [주의]", m)
    return 1 if fix else 0


def cmd_sheet(a):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        sys.exit("시트는 Pillow가 필요해요(pip install pillow).")
    src = Path(a.dir)
    cards = sorted(src.glob("[0-9][0-9].png"))
    th_w = a.width
    def load(p):
        im = Image.open(p).convert("RGB")
        return im.resize((th_w, int(im.height * th_w / im.width)))
    rows = []
    if a.ref:
        rows.append(("레퍼런스", [load(p) for p in a.ref]))
    rows.append(("결과", [load(p) for p in cards]))
    per = a.cols
    lines = []
    for label, ims in rows:
        for k in range(0, len(ims), per):
            lines.append(ims[k:k + per])
    gap = 14
    H = sum(max(i.height for i in ln) + gap for ln in lines) + gap
    W = per * (th_w + gap) + gap
    sheet = Image.new("RGB", (W, H), (235, 235, 235))
    y = gap
    for ln in lines:
        x = gap
        for im in ln:
            sheet.paste(im, (x, y))
            x += th_w + gap
        y += max(i.height for i in ln) + gap
    sheet.save(a.output)
    print("시트:", a.output, sheet.size)


def cmd_cutout(a):
    """생성 그림의 단색 바탕을 투명하게 뺀다(가장자리에서 이어진 바탕만). 캐릭터 시트 한 칸을 자른 그림이면
    가장자리에 걸친 옆 칸 조각도 지운다. Pillow 필요."""
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        sys.exit("cutout은 Pillow가 필요해요(pip install pillow).")
    from collections import deque
    for src in a.images:
        im = Image.open(src).convert("RGBA")
        W, H = im.size
        px = im.load()
        cs = [px[0, 0], px[W - 1, 0], px[0, H - 1], px[W - 1, H - 1]]
        bg = tuple(sorted(c[k] for c in cs)[1] for k in range(3))
        tol = a.tol
        def is_bg(c):
            return abs(c[0] - bg[0]) + abs(c[1] - bg[1]) + abs(c[2] - bg[2]) <= tol * 3
        seen = bytearray(W * H)
        q = deque()
        for x in range(W):
            q.append((x, 0)); q.append((x, H - 1))
        for y in range(H):
            q.append((0, y)); q.append((W - 1, y))
        while q:
            x, y = q.popleft()
            i = y * W + x
            if seen[i] or not is_bg(px[x, y]):
                continue
            seen[i] = 1
            if x > 0: q.append((x - 1, y))
            if x < W - 1: q.append((x + 1, y))
            if y > 0: q.append((x, y - 1))
            if y < H - 1: q.append((x, y + 1))
        if a.drop_edge:  # 가장자리에 닿은 그림 조각(옆 칸) 지우기
            q = deque((x, y) for x in range(W) for y in (0, H - 1))
            q.extend((x, y) for y in range(H) for x in (0, W - 1))
            while q:
                x, y = q.popleft()
                i = y * W + x
                if seen[i]:
                    continue
                seen[i] = 2
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < W and 0 <= ny < H and not seen[ny * W + nx]:
                        q.append((nx, ny))
        alpha = Image.frombytes("L", (W, H), bytes(0 if v else 255 for v in seen))
        alpha = alpha.filter(ImageFilter.GaussianBlur(1.2))
        im.putalpha(alpha)
        box = alpha.point(lambda v: 255 if v > 40 else 0).getbbox()
        if box and a.trim:
            m = 12
            box = (max(0, box[0] - m), max(0, box[1] - m), min(W, box[2] + m), min(H, box[3] + m))
            im = im.crop(box)
        out = Path(a.outdir) / (Path(src).stem + ".png") if a.outdir else Path(src).with_name(Path(src).stem + "-cut.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(out)
        print("투명 바탕:", out, im.size)


def main():
    ap = argparse.ArgumentParser(description="카드뉴스 HTML 렌더러 " + VERSION)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("spec")
    r.add_argument("-o", "--out", default="out")
    r.add_argument("--html-only", action="store_true")
    r.add_argument("--scale", type=float, default=1)
    s = sub.add_parser("sheet")
    s.add_argument("dir")
    s.add_argument("-o", "--output", default="sheet.png")
    s.add_argument("--ref", nargs="*")
    s.add_argument("--cols", type=int, default=4)
    s.add_argument("--width", type=int, default=360)
    c = sub.add_parser("cutout")
    c.add_argument("images", nargs="+")
    c.add_argument("-o", "--outdir")
    c.add_argument("--tol", type=int, default=14)
    c.add_argument("--drop-edge", action="store_true")
    c.add_argument("--no-trim", dest="trim", action="store_false")
    sub.add_parser("layouts")
    a = ap.parse_args()
    if a.cmd == "render":
        sys.exit(cmd_render(a))
    if a.cmd == "sheet":
        cmd_sheet(a)
    if a.cmd == "cutout":
        cmd_cutout(a)
    if a.cmd == "layouts":
        print("테마(갈래):")
        for k, v in THEME_NOTE.items():
            print(f"  {k}  {v}")
        print("레이아웃:")
        for k, v in LAYOUTS.items():
            print(f"  {k:10s} {v}")


if __name__ == "__main__":
    main()

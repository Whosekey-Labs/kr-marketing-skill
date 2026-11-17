#!/usr/bin/env python3
"""카드뉴스 렌더러.

장별 원고 JSON(제목·본문·사진·스타일 코드·브랜드 색·폰트)을 받아 1080x1350 카드 여러 장을 만든다.
한글 글자는 이 렌더러가 그린다(이미지 생성 AI에 한글을 맡기지 않는다).

사용법:
  python3 cardnews.py render spec.json -o out/             # PNG + JPEG(업로드용) + check.json
  python3 cardnews.py render spec.json -o out/ --format png
  python3 cardnews.py render spec.json -o out/ --html      # Pillow 없을 때: HTML을 만들어 브라우저로 캡처
  python3 cardnews.py check spec.json                      # 원고만 점검(글자 수·장수·대비)
  python3 cardnews.py styles                               # 스타일·유형 코드 목록
  python3 cardnews.py fonts                                # 폰트 받기(처음 한 번)

원고 칸(0.2.0에서 추가): steps(items를 단계로 이음), compare([{label, items}, {label, items}] 두 칸 비교),
menu([[이름, 가격, 한 줄 설명], …] 메뉴·가격표), tone(장별 "light"/"dark"), 전체 body_tone("light"/"dark"/"alternate"),
series(본문 장 위 왼쪽 시리즈 이름, 기본은 표지 kicker). S11 레트로 지원.
0.3.0: anchor(장마다 시각 앵커: {"type":"number","value","label"} · {"type":"icon","name"} ·
{"type":"flow","steps":[{"label","icon"}]} · {"type":"vs","left":{label,items},"right":{…}} · {"type":"button","text"}),
items[].icon(번호 대신 아이콘), em_style("marker"/"box"/"color", 대비 3:1 미만이면 box로 자동), chrome(true면 머리말·쪽번호·
진행 막대, 기본 끔), swipe_arrow(기본 켬), 표지 제목은 가장 긴 줄이 폭 90%가 되게 자동 크기.
아이콘: check arrow clock chat bulb calendar won wrench user cup star phone. 실제 사진이 없으면 사진 스타일 대신 S05.
0.4.0: 본문 장은 위(y 150)부터 아래(y 1190)까지 채움(남는 높이를 항목 사이에 나눔). anchor 추가: number에 chips(오른쪽 칩)·band(아래 칸),
{"type":"chips","items"}, {"type":"table","head":[a,b],"rows":[[…]]}, {"type":"timeline","start","end","marks":[[시,라벨]]},
bar(결론 띠 글자), cards(true면 흰 카드 목록, 체크리스트는 기본), tone "brand"/"deep"(brand.colors.deep), account(계정 이름 글자),
photo_match(사진이 문구와 다르면 이유를 적음 → 경고). anchor.pos: top/mid/bottom. 점검: 콘텐츠 높이 60% 미만, 같은 바탕 3장 연속.

Pillow가 있으면 PNG/JPEG를 바로 만든다. 없으면 --html 경로를 쓴다.
폰트는 Pretendard(SIL OFL)를 공식 저장소에서 받아 캐시에 둔다. 실패하면 시스템 한글 폰트를 쓴다.
"""
import argparse
import html
import json
import os
import re
import sys
import urllib.request

VERSION = "0.4.0"

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
    HAS_PIL = True
except ImportError:  # Pillow 없음 → --html 경로
    HAS_PIL = False

# ---------------------------------------------------------------- 코드 목록
TYPES = {
    "C01": "신메뉴·신상품 출시", "C02": "메뉴·가격표", "C03": "이벤트·할인", "C04": "공지",
    "C05": "예약·찾아오는 길", "C06": "정보·꿀팁", "C07": "자주 묻는 질문", "C08": "전후·사례",
    "C09": "손님 후기", "C10": "우리 가게·사람", "C11": "공간 투어", "C12": "일상·시즌 인사",
}
STYLES = {
    "S01": ("사진 그대로", True), "S02": ("사진 + 큰 제목", True), "S03": ("매거진", True),
    "S04": ("브랜드 색", True), "S05": ("깔끔한 글자 카드", True), "S06": ("그림·캐릭터", False),
    "S07": ("손글씨 메모", True), "S08": ("전단·특가", True), "S09": ("고급스러운", True),
    "S10": ("화면·메신저 모양", True), "S11": ("레트로(선택)", True),
}
SIZES = {"4:5": (1080, 1350), "3:4": (1080, 1440), "1:1": (1080, 1080)}

# ---------------------------------------------------------------- 폰트
FONT_DIR = os.path.join(os.path.expanduser("~"), ".cache", "kr-marketing", "fonts")
PRET = "https://raw.githubusercontent.com/orioncactus/pretendard/v1.3.9/packages/pretendard/dist/public/static/Pretendard-{w}.otf"
GF = "https://raw.githubusercontent.com/google/fonts/main/ofl/{d}/{f}"
FONT_FILES = {
    # 역할: (파일 이름, 받을 주소)
    "regular": ("Pretendard-Regular.otf", PRET.format(w="Regular")),
    "semibold": ("Pretendard-SemiBold.otf", PRET.format(w="SemiBold")),
    "bold": ("Pretendard-Bold.otf", PRET.format(w="Bold")),
    "black": ("Pretendard-ExtraBold.otf", PRET.format(w="ExtraBold")),
    "hand": ("NanumPenScript-Regular.ttf", GF.format(d="nanumpenscript", f="NanumPenScript-Regular.ttf")),
    "serif": ("GowunBatang-Regular.ttf", GF.format(d="gowunbatang", f="GowunBatang-Regular.ttf")),
    "serif_bold": ("GowunBatang-Bold.ttf", GF.format(d="gowunbatang", f="GowunBatang-Bold.ttf")),
}
SYSTEM_FONTS = [  # 받기 실패 시 (경로, ttc 인덱스: regular, bold)
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 0, 6),
    ("C:/Windows/Fonts/malgun.ttf", None, None), ("C:/Windows/Fonts/malgunbd.ttf", None, None),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 1, 1),
    ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", None, None),
    ("/System/Library/Fonts/Supplemental/AppleGothic.ttf", None, None),
]
_font_cache = {}
_font_notes = set()


def fetch_font(role):
    name, url = FONT_FILES[role]
    path = os.path.join(FONT_DIR, name)
    if os.path.exists(path) and os.path.getsize(path) > 100000:
        return path
    try:
        os.makedirs(FONT_DIR, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "kr-marketing-skill"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        if len(data) < 100000:
            raise ValueError("파일이 너무 작음")
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
        return path
    except Exception as e:  # 네트워크 없음 등
        _font_notes.add(f"폰트 {name} 받기 실패({e.__class__.__name__}) → 시스템 한글 폰트 사용")
        return None


def system_font(bold):
    win_bold = "C:/Windows/Fonts/malgunbd.ttf"
    if bold and os.path.exists(win_bold):
        return win_bold, 0
    for path, ri, bi in SYSTEM_FONTS:
        if os.path.exists(path) and path != win_bold:
            idx = (bi if bold else ri) or 0
            return path, idx
    return None, 0


def font(role, size):
    size = max(8, int(round(size)))
    key = (role, size)
    if key in _font_cache:
        return _font_cache[key]
    path = fetch_font(role)
    f = None
    if path:
        f = ImageFont.truetype(path, size)
    else:
        sp, idx = system_font(role in ("bold", "black", "semibold", "serif_bold"))
        if sp:
            try:
                f = ImageFont.truetype(sp, size, index=idx)
            except OSError:
                f = ImageFont.truetype(sp, size)
        else:
            sys.exit("한글 폰트를 찾지 못했어요. 인터넷 연결을 확인하거나 나눔고딕·맑은 고딕을 설치해 주세요.")
    _font_cache[key] = f
    return f


# ---------------------------------------------------------------- 색
def hex2rgb(h):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lum(rgb):
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def readable_on(bg, dark=(26, 26, 26), light=(255, 255, 255)):
    return dark if contrast(dark, bg) >= contrast(light, bg) else light


def palette(brand):
    c = brand.get("colors", {})
    main = hex2rgb(c.get("main", "#2F4B7C"))
    accent = hex2rgb(c.get("accent", "#F2B544"))
    bg = hex2rgb(c.get("bg", "#FFFFFF"))
    text = hex2rgb(c.get("text", "#1A1A1A"))
    return {"main": main, "accent": accent, "bg": bg, "text": text, "white": (255, 255, 255),
            "on_main": readable_on(main, text), "on_accent": readable_on(accent, text),
            "muted": mix(text, bg, 0.3), "deep_hex": c.get("deep")}


# ---------------------------------------------------------------- 글자 배치
EM = re.compile(r"\*([^*]+)\*")


def tokens(text):
    """'*강조*' 표시를 (조각, 강조여부) 목록으로. 줄바꿈은 그대로 둔다."""
    out, pos = [], 0
    for m in EM.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], False))
        out.append((m.group(1), True))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False))
    return out


def plain(text):
    return EM.sub(r"\1", text or "")


def _vis(line):
    return plain("".join(t for t, _ in line)).replace(" ", "")


def _orphan(line):
    """마지막 줄이 고아인가: 한 어절짜리 두 글자 이하, 또는 한 글자뿐."""
    v = _vis(line)
    words = [t for t in "".join(t for t, _ in line).split(" ") if t]
    return len(v) <= 1 or (len(words) <= 1 and len(v) <= 2)


def _split_last_word(line):
    """줄에서 마지막 어절을 떼어 (앞부분, 마지막 어절)로."""
    for i in range(len(line) - 1, -1, -1):
        if line[i][0] == " ":
            return line[:i], line[i + 1:]
    return line, []


def _rebalance(lines, f, max_w):
    """마지막 줄이 고아면 앞 줄 끝 어절을 내려 균형을 맞춘다(폭 안에서만)."""
    lines = [list(l) for l in lines]
    for _ in range(4):
        if len(lines) < 2 or not _orphan(lines[-1]):
            break
        prev, last = lines[-2], lines[-1]
        if not any(t == " " for t, _ in prev):  # 글자 단위로 끊긴 줄은 어절 경계를 알 수 없어 건드리지 않는다
            break
        head, moved = _split_last_word(prev)
        if not head or not _vis(head) or not moved:
            break
        cand = moved + [(" ", False)] + last
        if line_width(cand, f) > max_w:
            break
        lines[-2], lines[-1] = head, cand
    return lines


def wrap(text, f, max_w):
    """어절 단위 줄바꿈 + 마지막 줄에 한두 글자만 남지 않게(고아 줄) 앞 줄 어절을 내리거나 폭을 줄여 다시 나눈다."""
    out = []
    for para in (text or "").split("\n"):
        best = _rebalance(_wrap(para, f, max_w), f, max_w)
        if len(best) >= 2 and _orphan(best[-1]):
            for k in (0.94, 0.88, 0.82, 0.76):
                alt = _rebalance(_wrap(para, f, max_w * k), f, max_w)
                if len(alt) == len(best) and not _orphan(alt[-1]):
                    best = alt
                    break
        out += best
    return out


def _wrap(text, f, max_w):
    """어절 단위로 줄바꿈. 한 어절이 너무 길면 글자 단위로 끊는다. 결과: 줄 목록(각 줄 = [(조각, 강조)])."""
    lines = []
    for para in (text or "").split("\n"):
        words, gap = [], False  # 어절 = [(조각, 강조), ...], 강조 경계에서도 붙어 있으면 한 어절
        for seg, em in tokens(para):
            for p in re.split(r"( +)", seg):
                if not p:
                    continue
                if p.isspace():
                    gap = True
                    continue
                if words and not gap:
                    words[-1].append((p, em))
                else:
                    words.append([(p, em)])
                gap = False
        line, w = [], 0.0
        for word in words:
            ww = sum(f.getlength(t) for t, _ in word)
            sp = f.getlength(" ") if line else 0
            if line and w + sp + ww > max_w:
                lines.append(line)
                line, w, sp = [], 0.0, 0
            if not line and ww > max_w:  # 긴 어절은 글자 단위
                for t, em in word:
                    for ch in t:
                        cw = f.getlength(ch)
                        if line and w + cw > max_w:
                            lines.append(line)
                            line, w = [], 0.0
                        line.append((ch, em))
                        w += cw
                continue
            if sp:
                line.append((" ", False))
            line.extend(word)
            w += sp + ww
        lines.append(line)
    return lines


def em_runs(line, f):
    """강조 조각이 이어진 구간(사이 공백 포함)의 (시작 x, 끝 x) 목록. 줄마다 따로 계산한다."""
    runs, x, start, end, pend = [], 0.0, None, None, 0.0
    for seg, e in line:
        sw = f.getlength(seg)
        if e:
            if start is None:
                start = x
            end = x + sw
        elif not seg.isspace() and start is not None:
            runs.append((start, end))
            start = None
        x += sw
    if start is not None:
        runs.append((start, end))
    return runs


def line_width(line, f):
    return sum(f.getlength(s) for s, _ in line)


class Canvas:
    """배경을 먼저 그리고, 글자는 모아 두었다가 마지막에 그린다(배경 대비 점검용)."""

    def __init__(self, w, h, bg):
        self.w, self.h = w, h
        self.img = Image.new("RGBA", (w, h), bg + (255,))
        self.draw = ImageDraw.Draw(self.img)
        self.texts = []  # dict(x,y,line,font,color,em_color,role,size,stroke)

    def paste_photo(self, path, box, radius=0, focus=(0.5, 0.5), hint=""):
        x0, y0, x1, y1 = [int(v) for v in box]
        bw, bh = x1 - x0, y1 - y0
        if path and os.path.exists(path):
            ph = Image.open(path)
            ph = ImageOps.exif_transpose(ph).convert("RGB")
            ph = ImageOps.fit(ph, (bw, bh), Image.LANCZOS, centering=tuple(focus))
        else:
            ph = Image.new("RGB", (bw, bh), (214, 208, 198))
            d = ImageDraw.Draw(ph)
            for i in range(-bh, bw, 40):
                d.line([(i, 0), (i + bh, bh)], fill=(204, 197, 186), width=2)
            h = (hint or "사장님 사진").strip().strip("[]").replace("사진 자리:", "").strip()
            fl = font("semibold", 34)
            lines = [plain("".join(t for t, _ in ln)) for ln in wrap(f"사진 자리: {h}", fl, bw - 80)][:3]
            yy = bh / 2 - len(lines) * 24
            for ln in lines:
                d.text(((bw - fl.getlength(ln)) / 2, yy), ln, font=fl, fill=(90, 84, 76))
                yy += 48
            self.notes = getattr(self, "notes", []) + [f"사진 없음: {path or hint}"]
        mask = None
        if radius:
            mask = Image.new("L", (bw, bh), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, bw - 1, bh - 1], radius=radius, fill=255)
        self.img.paste(ph, (x0, y0), mask)

    def gradient(self, y_from, y_to, color=(0, 0, 0), a_from=0, a_to=170):
        h = int(y_to - y_from)
        if h <= 0:
            return
        g = Image.linear_gradient("L").resize((self.w, h))
        g = g.point(lambda v: int(a_from + (a_to - a_from) * v / 255))
        layer = Image.new("RGBA", (self.w, h), color + (0,))
        layer.putalpha(g)
        self.img.alpha_composite(layer, (0, int(y_from)))

    def rect(self, box, fill, radius=0, outline=None, width=1, alpha=255):
        if alpha < 255:
            layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
            ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, fill=fill + (alpha,))
            self.img.alpha_composite(layer)
        else:
            self.draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

    def text(self, x, y, line, f, color, em_color=None, role="body", stroke=0, stroke_color=None):
        self.texts.append(dict(x=x, y=y, line=line, font=f, color=color, em=em_color or color,
                               role=role, size=f.size, stroke=stroke, stroke_color=stroke_color))

    def finish(self):
        bg = self.img.convert("RGB")
        for t in self.texts:
            x = t["x"]
            for seg, em in t["line"]:
                col = t["em"] if em else t["color"]
                kw = {}
                if t["stroke"]:
                    kw = dict(stroke_width=t["stroke"], stroke_fill=t["stroke_color"])
                self.draw.text((x, t["y"]), seg, font=t["font"], fill=col, **kw)
                bb = self.draw.textbbox((x, t["y"]), seg, font=t["font"], stroke_width=t["stroke"])
                t.setdefault("boxes", []).append((bb, col))
                x += t["font"].getlength(seg)
        return bg


# ---------------------------------------------------------------- 내용 블록
BASE = {"kicker": 32, "title": 92, "heading": 96, "text": 40, "item_title": 52, "item_text": 38,
        "info": 44, "qa": 42, "big": 260}
# 넘칠 때 줄일 수 있는 하한(본문 40px 미만이면 점검에서 주의)
MIN = {"title": 64, "heading": 64, "text": 38, "item_title": 40, "item_text": 36, "info": 38, "qa": 38}
# 글이 적은 장은 키워서 채우되 이 크기를 넘지 않는다. 제목:본문 = 약 2.4:1 을 유지한다.
MAX = {"kicker": 40, "heading": 112, "title": 124, "text": 46, "item_title": 60, "item_text": 44, "info": 52, "qa": 48,
       "big": 340}
FILL_MIN, FILL_MAX = 0.72, 0.84  # 칸 높이 대비 내용 높이: 이보다 적으면 키우고, 이 이상은 키우지 않음


# ---------------------------------------------------------------- 아이콘(코드로 그리는 단순 도형)
ICONS = ("check", "arrow", "clock", "chat", "bulb", "calendar", "won", "wrench", "user", "cup", "star", "phone")
ICON_WORDS = [("won", "비용 가격 원 견적 얼마 할인"), ("clock", "시간 언제 몇 시 빨리 분"), ("wrench", "고장 수리 고쳐 손봐 관리"),
              ("chat", "카톡 상담 문의 말씀 질문 묻"), ("calendar", "예약 기간 날짜 일정 휴무 월 일"),
              ("bulb", "팁 방법 비결 아이디어 알아"), ("cup", "우유 커피 음료 마시"), ("user", "사장님 손님 직원 사람")]


def pick_icon(text):
    t = plain(text or "")
    for name, words in ICON_WORDS:
        if any(w in t for w in words.split()):
            return name
    return "check"


def draw_icon(d, name, cx, cy, r, color, fill=None):
    """원 안에 선 아이콘. d = ImageDraw."""
    if fill:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
    w = max(5, int(r * 0.1))
    k = r * 0.5
    if name == "check":
        d.line([(cx - k * 0.95, cy + k * 0.05), (cx - k * 0.25, cy + k * 0.75), (cx + k * 1.0, cy - k * 0.7)], fill=color,
               width=w + 2, joint="curve")
    elif name == "arrow":
        d.line([(cx - k, cy), (cx + k, cy)], fill=color, width=w)
        d.line([(cx + k * 0.35, cy - k * 0.6), (cx + k, cy), (cx + k * 0.35, cy + k * 0.6)], fill=color, width=w, joint="curve")
    elif name == "clock":
        d.ellipse([cx - k * 1.1, cy - k * 1.1, cx + k * 1.1, cy + k * 1.1], outline=color, width=w)
        d.line([(cx, cy - k * 0.7), (cx, cy), (cx + k * 0.55, cy + k * 0.35)], fill=color, width=w, joint="curve")
    elif name == "chat":
        d.rounded_rectangle([cx - k * 1.15, cy - k * 0.9, cx + k * 1.15, cy + k * 0.6], radius=k * 0.45, outline=color, width=w)
        d.line([(cx - k * 0.5, cy + k * 0.6), (cx - k * 0.75, cy + k * 1.1), (cx - k * 0.05, cy + k * 0.6)], fill=color, width=w)
        for dx in (-0.5, 0, 0.5):
            d.ellipse([cx + k * dx - w * 0.8, cy - k * 0.15 - w * 0.8, cx + k * dx + w * 0.8, cy - k * 0.15 + w * 0.8], fill=color)
    elif name == "bulb":
        d.ellipse([cx - k * 0.8, cy - k * 1.15, cx + k * 0.8, cy + k * 0.45], outline=color, width=w)
        d.line([(cx - k * 0.4, cy + k * 0.75), (cx + k * 0.4, cy + k * 0.75)], fill=color, width=w)
        d.line([(cx - k * 0.28, cy + k * 1.05), (cx + k * 0.28, cy + k * 1.05)], fill=color, width=w)
    elif name == "calendar":
        d.rounded_rectangle([cx - k, cy - k * 0.8, cx + k, cy + k], radius=k * 0.2, outline=color, width=w)
        d.line([(cx - k, cy - k * 0.25), (cx + k, cy - k * 0.25)], fill=color, width=w)
        for dx in (-0.5, 0.5):
            d.line([(cx + k * dx, cy - k * 1.15), (cx + k * dx, cy - k * 0.55)], fill=color, width=w)
        d.rectangle([cx + k * 0.15, cy + k * 0.2, cx + k * 0.6, cy + k * 0.6], fill=color)
    elif name == "won":
        f = font("black", k * 2.0)
        tw = f.getlength("₩")
        d.text((cx - tw / 2, cy - k * 1.3), "₩", font=f, fill=color)
    elif name == "wrench":
        d.line([(cx - k * 0.8, cy + k * 0.8), (cx + k * 0.25, cy - k * 0.25)], fill=color, width=int(w * 1.8))
        d.arc([cx - k * 0.1, cy - k * 1.1, cx + k * 1.1, cy + k * 0.1], 100, 350, fill=color, width=w)
    elif name == "user":
        d.ellipse([cx - k * 0.45, cy - k * 1.0, cx + k * 0.45, cy - k * 0.1], outline=color, width=w)
        d.arc([cx - k * 0.95, cy + k * 0.1, cx + k * 0.95, cy + k * 1.9], 180, 360, fill=color, width=w)
    elif name == "cup":
        d.rounded_rectangle([cx - k * 0.8, cy - k * 0.6, cx + k * 0.5, cy + k * 0.9], radius=k * 0.15, outline=color, width=w)
        d.arc([cx + k * 0.2, cy - k * 0.3, cx + k * 1.05, cy + k * 0.5], 270, 90, fill=color, width=w)
    elif name == "star":
        import math
        pts = []
        for i in range(10):
            rr = k * (1.1 if i % 2 == 0 else 0.45)
            a = -math.pi / 2 + i * math.pi / 5
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        d.polygon(pts, outline=color, width=w)
    elif name == "phone":
        d.rounded_rectangle([cx - k * 0.6, cy - k * 1.05, cx + k * 0.6, cy + k * 1.05], radius=k * 0.2, outline=color, width=w)
        d.line([(cx - k * 0.2, cy + k * 0.7), (cx + k * 0.2, cy + k * 0.7)], fill=color, width=w)


def fit_size(text, role, target_w, lo, hi):
    """줄바꿈(\n)은 그대로 두고, 가장 긴 줄이 target_w가 되는 글자 크기(lo~hi)."""
    f = font(role, 100)
    widest = max(sum(f.getlength(t) for t, _ in tokens(line)) for line in (text or " ").split("\n"))
    return max(lo, min(hi, 100 * target_w / max(1, widest)))


class Block:
    """요소를 위에서 아래로 쌓는다. 넘치면 글자를 줄이고, 최소 크기에서도 넘치면 overflow."""

    def __init__(self, cv, area, pal, fonts, align="top", center_x=False, sizes=None, grow=True):
        self.cv, self.area, self.pal = cv, area, pal
        self.fonts = dict({"title": "black", "heading": "black", "text": "regular"}, **fonts)
        self.grow = grow
        self.align, self.center_x = align, center_x
        self.sizes = dict(BASE, **(sizes or {}))
        self.items = []
        self.overflow = False
        self.scale = 1.0

    def add(self, kind, value, **opt):
        if value:
            self.items.append((kind, value, opt))

    def _sz(self, k):
        base = self.sizes[k]
        v = base * self.scale
        if self.scale < 1:
            return max(v, min(MIN.get(k, 0), base))
        cap = MAX.get(k, base)
        if not any(it[0] in ("items", "info", "compare", "menu", "bubble") for it in self.items):
            cap *= 1.2  # 제목·짧은 글만 있는 장은 한 덩어리로 더 크게
        return min(v, max(cap, base))

    def _layout(self, dry=True):
        x0, y0, x1, y1 = self.area
        w = x1 - x0
        y = 0
        ops = []  # (y, callable)
        self._marks = []  # (이 항목의 첫 op 번호, 항목 번호)
        for ii, (kind, val, opt) in enumerate(self.items):
            self._marks.append(len(ops))
            gap = opt.get("gap", 28) * max(1.0, 0.6 + 0.4 * self.scale)
            if kind in ("title", "heading", "text", "kicker_text"):
                k = "text" if kind == "kicker_text" else kind
                size = opt.get("size") or self._sz(k)
                if opt.get("fit"):  # 표지 헤드라인: 가장 긴 줄이 폭의 90%
                    lo, hi = opt["fit"]
                    size = fit_size(val, opt.get("font", self.fonts.get(k, "regular")), w * 0.9, lo, hi) * min(1.0, self.scale)
                elif opt.get("size"):
                    size = max(size * self.scale, MIN.get(k, 30)) if self.scale < 1 else min(size * self.scale, size * 1.15)
                f = font(opt.get("font", self.fonts.get(k, "regular")), size)
                lh = size * opt.get("lh", (1.14 if opt.get("fit") else 1.22) if k in ("title", "heading") else 1.5)
                lines = wrap(val, f, w)
                for ln in lines:
                    lw = line_width(ln, f)
                    lx = x0 + (w - lw) / 2 if (self.center_x or opt.get("center")) else x0
                    ops.append((y, ("text", lx, ln, f, opt.get("color"), opt.get("em"), opt.get("role", "body"),
                                     opt.get("stroke", 0), opt.get("stroke_color"),
                                     ("box", opt["box"]) if opt.get("box") else opt.get("hl"), size)))
                    y += lh
                y += gap
            elif kind == "kicker":
                size = self._sz("kicker")
                f = font("bold", size)
                tw = f.getlength(val)
                pad = 18
                bx = x0 + (w - tw - 2 * pad) / 2 if self.center_x else x0
                ops.append((y, ("pill", bx, val, f, pad, opt)))
                y += size + 2 * 12 + gap
            elif kind == "rule":
                ops.append((y, ("rule", opt)))
                y += 2 + gap
            elif kind == "items" and opt.get("cards"):  # 흰 카드 목록: 표시 + 굵은 제목 + 회색 설명
                numbered = opt.get("mode", "number")
                ft = font("bold", min(self._sz("item_title"), 48))
                fd = font("regular", 32)
                n = len(val)
                for i, it in enumerate(val, 1):
                    if isinstance(it, str):
                        it = {"title": it}
                    mk = 96 if it.get("icon") else 64
                    tx = x0 + 40 + mk + 32
                    tl = wrap(it.get("title", ""), ft, x1 - tx - 30)
                    dl = wrap(it["text"], fd, x1 - tx - 30) if it.get("text") else []
                    inner = len(tl) * ft.size * 1.25 + (8 + len(dl) * fd.size * 1.4 if dl else 0)
                    chh = max(160 if n <= 4 else 130, inner + 56, mk + 48)
                    ops.append((y, ("card", x0, w, chh, opt)))
                    ops.append((y + (chh - mk) / 2, ("badge", x0 + 40, mk, i,
                                                     numbered if not it.get("icon") else "icon:" + it["icon"], opt)))
                    yy = y + (chh - inner) / 2
                    for ln in tl:
                        ops.append((yy, ("text", tx, ln, ft, opt.get("color"), opt.get("em"), "body", 0, None, None, ft.size)))
                        yy += ft.size * 1.25
                    yy += 8
                    for ln in dl:
                        ops.append((yy, ("text", tx, ln, fd, opt.get("sub"), opt.get("em"), "note", 0, None, None, fd.size)))
                        yy += fd.size * 1.4
                    y += chh + 20
                y += gap - 20
            elif kind == "items":
                numbered = opt.get("mode", "number")
                ft = font("bold", self._sz("item_title"))
                fd = font("regular", self._sz("item_text"))
                badge = self._sz("item_title") * 1.45
                tx = x0 + badge + 26
                for i, it in enumerate(val, 1):
                    if isinstance(it, str):
                        it = {"title": it}
                    ops.append((y, ("badge", x0, badge, i, numbered if not it.get("icon") else "icon:" + it["icon"], opt)))
                    tl = wrap(it.get("title", ""), ft, x1 - tx)
                    yy = y + (badge - ft.size * 1.3) / 2 if len(tl) == 1 and not it.get("text") else y
                    for ln in tl:
                        ops.append((yy, ("text", tx, ln, ft, opt.get("color"), opt.get("em"), "body", 0, None, None, ft.size)))
                        yy += ft.size * 1.3
                    if it.get("text"):
                        yy += 6
                        for ln in wrap(it["text"], fd, x1 - tx):
                            ops.append((yy, ("text", tx, ln, fd, opt.get("sub"), opt.get("em"), "body", 0, None, None, fd.size)))
                            yy += fd.size * 1.45
                    ny = max(yy, y + badge) + opt.get("gap", 30)
                    if numbered == "step" and i < len(val):  # 단계: 번호 사이를 선으로 잇는다
                        ops.append((y + badge + 8, ("vline", x0 + badge / 2, ny - y - badge - 16, opt)))
                    y = ny
                y += 4
            elif kind == "compare":  # 비교: 두 칸 나란히
                cg = 80 if opt.get("vs") else 24
                cw = (w - cg) / 2
                ft = font("black", 52 if opt.get("vs") else min(self._sz("item_title"), 46))
                fd = font("semibold", 44 if opt.get("vs") else min(self._sz("item_text"), 40))
                pad = 32
                cols = []
                for ci, col in enumerate(val[:2]):
                    cops, yy = [], pad
                    for ln in wrap(col.get("label", ""), ft, cw - 2 * pad):
                        cops.append((yy, ln, ft, "head"))
                        yy += ft.size * 1.25
                    yy += 22
                    for it in col.get("items", []):
                        for k, ln in enumerate(wrap(it, fd, cw - 2 * pad - fd.size * 0.9)):
                            cops.append((yy, ln, fd, "dot" if k == 0 else "cont"))
                            yy += fd.size * 1.4
                        yy += 14
                    cols.append((cops, yy + pad - 14))
                ch = max(max(c[1] for c in cols), 400 if opt.get("vs") else 0)
                if opt.get("vs"):
                    ops.append((y + ch / 2, ("vsbadge", x0 + w / 2, opt)))
                for ci, (cops, _) in enumerate(cols):
                    cx = x0 + ci * (cw + cg)
                    ops.append((y, ("panel", cx, cw, ch, ci, opt)))
                    for yy, ln, f, kind2 in cops:
                        ops.append((y + yy, ("ctext", cx + pad, ln, f, kind2, ci, opt)))
                if opt.get("vs"):  # 배지를 칸 위에 그리도록 맨 뒤로
                    k_ = next(i for i in range(len(ops) - 1, -1, -1) if ops[i][1][0] == "vsbadge")
                    ops.append(ops.pop(k_))
                y += ch + gap
            elif kind == "menu":  # 메뉴·가격표: 이름 ……… 가격
                fn = font("bold", self._sz("item_title"))
                fp = font("black", self._sz("item_title"))
                fd = font("regular", self._sz("item_text") * 0.9)
                for k, row in enumerate(val):
                    name, price = row[0], row[1]
                    desc = row[2] if len(row) > 2 else ""
                    pw = fp.getlength(price)
                    nl = wrap(name, fn, w - pw - 60)
                    yy = y
                    for j, ln in enumerate(nl):
                        ops.append((yy, ("text", x0, ln, fn, opt.get("color"), opt.get("em"), "body", 0, None, None, fn.size)))
                        if j == len(nl) - 1:
                            nw = line_width(ln, fn)
                            ops.append((yy, ("dots", x0 + nw + 18, x1 - pw - 18, fn.size, opt)))
                            ops.append((yy, ("text", x1 - pw, [(price, False)], fp, opt.get("price"), None, "key", 0, None, None, fp.size)))
                        yy += fn.size * 1.3
                    if desc:
                        yy += 4
                        for ln in wrap(desc, fd, w - pw - 60):
                            ops.append((yy, ("text", x0, ln, fd, opt.get("sub"), opt.get("em"), "body", 0, None, None, fd.size)))
                            yy += fd.size * 1.45
                    y = yy + 22
                    if k < len(val) - 1:
                        ops.append((y, ("rule", dict(len=w, h=2, color=opt.get("line")))))
                        y += 26
                y += gap
            elif kind == "info":
                fl = font("bold", self._sz("info"))
                fv = font("regular", self._sz("info"))
                lw = max(fl.getlength(r[0]) for r in val) + 28
                for label, value in val:
                    ops.append((y, ("text", x0, [(label, False)], fl, opt.get("label_color"), None, "key", 0, None, None, fl.size)))
                    yy = y
                    for ln in wrap(value, fv, w - lw):
                        ops.append((yy, ("text", x0 + lw, ln, fv, opt.get("color"), opt.get("em"), "body", 0, None, None, fv.size)))
                        yy += fv.size * 1.45
                    y = yy + 14
                y += gap
            elif kind == "bubble":
                size = self._sz("qa") * (1.12 if opt.get("big") else 1)
                f = font(opt.get("font", "regular"), size)
                bw = w * 0.92
                pad = int(size * 0.85)
                av = int(size * 1.6)
                lines = wrap(val, f, bw - 2 * pad - (av + 20 if opt.get("side") == "left" else 0))
                bh = len(lines) * size * 1.45 + 2 * pad - size * 0.45
                if opt.get("side") == "left":
                    bh = max(bh, av + 2 * pad - 24)
                ops.append((y, ("bubble", lines, f, size, bw, bh, pad, av, opt)))
                y += bh + 30 + gap  # 꼬리 자리
            elif kind == "big":
                size = self._sz("big")
                f = font("black", size)
                ops.append((y, ("big", val, f, size, opt)))
                y += size * 1.05 + gap
            elif kind == "anumber":  # 시각 앵커: 큰 숫자 (+ 오른쪽 칩, 아래 띠)
                f = font("black", 100)
                chips = list(opt.get("chips") or [])
                top_cap = opt.get("max", 380)
                nw = w * (0.56 if chips else 0.98)
                size = min(top_cap, 100 * nw / max(1, f.getlength(val)))
                lines = [val]
                parts = val.strip().rsplit(" ", 1)
                if (size < top_cap * 0.5 and len(parts) == 2 and re.search(r"\d", parts[0])
                        and not re.search(r"\d", parts[1])):  # 긴 숫자: 단위(원·명 등)를 아랫줄로
                    lines = parts
                    size = min(top_cap, 100 * nw / max(1, max(f.getlength(t) for t in lines)))
                if chips and size < top_cap * 0.5:  # 그래도 작으면 칩을 숫자 아래 띠로 옮긴다
                    nw = w * 0.98
                    one = min(top_cap, 100 * nw / max(1, f.getlength(val)))
                    if one >= top_cap * 0.5:  # 넓어진 폭에 한 줄로 들어가면 한 줄로
                        lines = [val]
                    size = min(top_cap, 100 * nw / max(1, max(f.getlength(t) for t in lines)))
                    opt = dict(opt, band=(opt.get("band") or []) + chips)
                    chips = []
                f = font("black", size)
                nh = 0
                for t in lines:
                    ops.append((y + nh, ("big", t, f, size, opt)))
                    nh += size * 1.16
                if chips:
                    ch, cg = 96, 20
                    th = len(chips) * ch + (len(chips) - 1) * cg
                    cy = y + max(0, (nh - th) / 2)
                    for t in chips:
                        ops.append((cy, ("chip", x0 + w * 0.6, w * 0.4, ch, t, 40, opt)))
                        cy += ch + cg
                    nh = max(nh, th)
                y += nh
                if opt.get("label"):
                    fl = font("bold", self._sz("item_title"))
                    ops.append((y, ("text", x0 + (w - fl.getlength(opt["label"])) / 2 if opt.get("center") else x0,
                                    [(opt["label"], False)], fl, opt.get("label_color"), None, "body", 0, None, None, fl.size)))
                    y += fl.size * 1.3
                if opt.get("band"):
                    y += 30
                    n = len(opt["band"])
                    cw = (w - 16 * (n - 1)) / n
                    for i, t in enumerate(opt["band"]):
                        ops.append((y, ("chip", x0 + i * (cw + 16), cw, 100, t, 36, opt)))
                    y += 100
                y += gap
            elif kind == "chips":  # 칩 줄(표지 미리보기 등)
                fc = font("bold", 30)
                xx, rowy = 0, 0
                for t in val:
                    cw = fc.getlength(t) + 48
                    if xx and xx + cw > w:
                        xx, rowy = 0, rowy + 72 + 14
                    ops.append((y + rowy, ("chip", x0 + xx, cw, 72, t, 30, opt)))
                    xx += cw + 14
                y += rowy + 72 + gap
            elif kind == "table":  # 전/후 미니 표
                head, rows = val
                fh, fr = font("bold", 34), font("semibold", 36)
                hh, rh = 72, 76
                cw = (w - 12) / 2
                for ci in range(2):
                    ops.append((y, ("cell", x0 + ci * (cw + 12), cw, hh, head[ci], fh, "head", ci, opt)))
                yy = y + hh + 10
                for r in rows:
                    for ci in range(2):
                        ops.append((yy, ("cell", x0 + ci * (cw + 12), cw, rh, r[ci], fr, "row", ci, opt)))
                    yy += rh + 10
                y = yy - 10 + gap
            elif kind == "bar":  # 결론 띠
                fb = font("black", 40)
                lines = wrap(val, fb, w - 80)
                bh = max(110, len(lines) * 52 + 50)
                ops.append((y, ("bar", lines, fb, bh, opt)))
                y += bh + gap
            elif kind == "timeline":  # 가로 시간 막대
                st, en, marks = val
                ops.append((y, ("timeline", st, en, marks, opt)))
                y += 230 + gap
            elif kind == "icon":
                r = min(110, 96 * max(1, self.scale * 0.85))
                cx = x0 + (w / 2 if opt.get("center") else r)
                ops.append((y, ("icon", val, cx, r, opt)))
                y += 2 * r + gap
            elif kind == "flow":  # 과정 도식: 원 아이콘 → 원 아이콘 → …
                n = len(val)
                r = min(92, w / (n * 2.9))
                fl = font("bold", min(self._sz("item_title"), 46))
                slot = w / n
                ops.append((y, ("flow", val, slot, r, fl, opt)))
                maxl = max(len(wrap(st.get("label", ""), fl, slot - 16)) for st in val)
                y += 2 * r + 24 + maxl * fl.size * 1.3 + gap
            elif kind == "button":  # 행동 버튼(카카오 채널 모양 등)
                fb = font("black", 48)
                bh = 128
                ops.append((y, ("button", val, fb, bh, opt)))
                y += bh + gap
            elif kind == "space":
                y += val * self.scale
        if self.items:
            y -= self.items[-1][2].get("gap", 28)
        return y, ops

    def render(self):
        x0, y0, x1, y1 = self.area
        avail = y1 - y0
        h, ops = self._layout()
        while h > avail and self.scale > 0.55:
            self.scale -= 0.05
            h, ops = self._layout()
        if h > avail:
            self.overflow = True
        elif self.grow and h < avail * FILL_MIN:  # 글이 적으면 키운다(최대 MAX 크기)
            while self.scale < 2.0:
                self.scale += 0.05
                h2, ops2 = self._layout()
                if h2 > avail * FILL_MAX:
                    self.scale -= 0.05
                    break
                h, ops = h2, ops2
            h, ops = self._layout()  # 표시(_marks)를 최종 크기에 맞춘다
        if self.align == "spread" and len(self.items) > 1 and h < avail:  # 위 정렬 + 남는 높이를 항목 사이에 나눔
            wts = []
            for i in range(1, len(self.items)):
                pk, pv, po = self.items[i - 1]
                tight = pk == "kicker" or (pk == "text" and po.get("role") == "key" and po.get("tight"))
                wts.append(0 if tight else (1.6 if self.items[i][0] in ("anumber", "flow", "compare", "table", "bar", "items",
                                                                              "timeline", "button", "chips", "icon") else 1))
            tw = sum(wts) or 1
            per = min((avail - h) / tw, getattr(self, "spread_cap", 150))
            shift, acc = [0.0], 0.0
            for wv in wts:
                acc += wv * per
                shift.append(acc)
            marks = self._marks + [len(ops)]
            new = []
            for ii in range(len(self.items)):
                for j in range(marks[ii], marks[ii + 1]):
                    new.append((ops[j][0] + shift[ii], ops[j][1]))
            ops = new
            h += acc
            top = y0
        elif self.align == "center":
            top = y0 + max(0, (avail - h) / 2)
        elif self.align == "bottom":
            top = y1 - h
        else:
            top = y0
        self.top, self.height = top, h
        cv, pal = self.cv, self.pal
        n_before = len(cv.texts)
        self._n_before = n_before
        for oy, op in ops:
            y = top + oy
            kind = op[0]
            if kind == "text":
                _, lx, ln, f, color, em, role, stroke, scol, hl, size = op
                if hl and isinstance(hl[0], str):  # 반전 박스: 강조어에만 바탕색
                    fill = hl[1]
                    for a0, a1 in em_runs(ln, f):
                        cv.rect([lx + a0 - size * 0.1, y + size * 0.08, lx + a1 + size * 0.1, y + size * 1.22], fill,
                                radius=max(4, int(size * 0.06)))
                    em = readable_on(fill, pal["text"])
                elif hl:  # 형광펜: 글자 아래쪽 40%만
                    for a0, a1 in em_runs(ln, f):
                        cv.rect([lx + a0 - 4, y + size * 0.66, lx + a1 + 4, y + size * 1.14], hl)
                cv.text(lx, y, ln, f, color or pal["text"], em or pal["accent"], role, stroke, scol)
            elif kind == "pill":
                _, bx, val, f, pad, opt = op
                tw = f.getlength(val)
                fill = opt.get("fill", pal["accent"])
                cv.rect([bx, y, bx + tw + 2 * pad, y + f.size + 24], fill, radius=(f.size + 24) // 2)
                cv.text(bx + pad, y + 12 - f.size * 0.08, [(val, False)], f, opt.get("color", readable_on(fill)), role="minor")
            elif kind == "rule":
                cv.rect([x0, y, x0 + op[1].get("len", 80), y + op[1].get("h", 6)], op[1].get("color", pal["accent"]))
            elif kind == "badge":
                _, bx, s, i, mode, opt = op
                fill = opt.get("badge", pal["main"])
                if mode.startswith("icon:"):
                    draw_icon(cv.draw, mode[5:], bx + s / 2, y + s / 2, s / 2, readable_on(fill), fill)
                elif mode == "check":
                    cv.rect([bx + 6, y + 6, bx + s - 6, y + s - 6], fill=opt.get("badge_bg", pal["white"]),
                            radius=10, outline=fill, width=5)
                    f = font("black", s * 0.62)
                    cv.text(bx + s * 0.2, y + s * 0.12, [("✓", False)], f, fill, role="minor")
                else:
                    cv.rect([bx, y, bx + s, y + s], fill, radius=int(s * (0.5 if mode == "step" else 0.28)))
                    f = font("black", s * 0.55)
                    lbl = str(i)
                    cv.text(bx + (s - f.getlength(lbl)) / 2, y + s * 0.16, [(lbl, False)], f, readable_on(fill), role="minor")
            elif kind == "chip":
                _, cx, cw, ch, t, fs, opt = op
                fill = opt.get("chip_fill", pal["white"])
                cv.rect([cx, y, cx + cw, y + ch], fill, radius=24 if ch > 80 else ch // 2)
                fc = font("bold", fs)
                tc = opt.get("chip_color") or readable_on(fill, pal["text"])
                cv.text(cx + (cw - fc.getlength(t)) / 2, y + (ch - fs * 1.2) / 2, [(t, False)], fc, tc, role="label")
            elif kind == "card":
                _, cx, cw, ch, opt = op
                fill = opt.get("card_fill", pal["white"])
                sh = Image.new("RGBA", (int(cw) + 40, int(ch) + 40), (0, 0, 0, 0))
                ImageDraw.Draw(sh).rounded_rectangle([20, 20, cw + 20, ch + 20], radius=24, fill=(0, 0, 0, 22))
                sh = sh.filter(ImageFilter.GaussianBlur(9))
                cv.img.alpha_composite(sh, (int(cx - 20), int(y - 14)))
                cv.rect([cx, y, cx + cw, y + ch], fill, radius=24)
            elif kind == "cell":
                _, cx, cw, ch, t, f, part, ci, opt = op
                fills = opt.get("cell_fills") or {"head": [mix(pal["text"], pal["bg"], 0.86), pal["main"]],
                                                  "row": [pal["white"], pal["white"]]}
                fill = fills[part][ci]
                cv.rect([cx, y, cx + cw, y + ch], fill, radius=16)
                tc = readable_on(fill, pal["text"])
                if part == "row" and ci == 1:
                    tc = pal["main"] if contrast(pal["main"], fill) >= 4.5 else tc
                lns = wrap(t, f, cw - 40)[:2]
                yy = y + (ch - len(lns) * f.size * 1.25) / 2
                for ln in lns:
                    cv.text(cx + 28, yy, ln, f, tc, role="label")
                    yy += f.size * 1.25
            elif kind == "bar":
                _, lines, fb, bh, opt = op
                fill = opt.get("fill", pal["text"])
                cv.rect([x0, y, x1, y + bh], fill, radius=24)
                tc = readable_on(fill)
                yy = y + (bh - len(lines) * 52) / 2 + 2
                for ln in lines:
                    emc = opt.get("em", tc)
                    cv.text(x0 + (x1 - x0 - line_width(ln, fb)) / 2, yy, ln, fb, tc,
                            emc if contrast(emc, fill) >= 4.5 else tc, role="key")
                    yy += 52
            elif kind == "timeline":
                _, st, en, marks, opt = op
                tc, acc = opt.get("color", pal["text"]), opt.get("accent", pal["main"])
                by = y + 120
                cv.rect([x0, by, x1, by + 24], mix(tc, pal["bg"], 0.85), radius=12)
                fl = font("semibold", 30)
                for hh in range(st, en + 1):
                    xx = x0 + (x1 - x0) * (hh - st) / (en - st)
                    cv.rect([xx - 2, by + 30, xx + 2, by + 46], mix(tc, pal["bg"], 0.5))
                    if (hh - st) % 2 == 0 or hh == en:
                        lb = f"{hh}시"
                        cv.text(xx - fl.getlength(lb) / 2, by + 58, [(lb, False)], fl, mix(tc, pal["bg"], 0.2), role="label")
                fb = font("black", 34)
                for hh, lab in marks:
                    xx = x0 + (x1 - x0) * (hh - st) / (en - st)
                    cv.draw.ellipse([xx - 34, by - 22, xx + 34, by + 46], fill=acc)
                    lw = fb.getlength(lab) + 40
                    px = min(max(xx, x0 + lw / 2), x1 - lw / 2)  # 배지가 칸 밖으로 나가지 않게
                    cv.rect([px - lw / 2, y, px + lw / 2, y + 70], acc, radius=35)
                    cv.text(px - fb.getlength(lab) / 2, y + 14, [(lab, False)], fb, readable_on(acc), role="key")
            elif kind == "icon":
                _, name, cx, r, opt = op
                draw_icon(cv.draw, name, cx, y + r, r, opt.get("color", pal["white"]), opt.get("fill", pal["main"]))
            elif kind == "flow":
                _, steps, slot, r, fl, opt = op
                col, fill = opt.get("color", pal["white"]), opt.get("fill", pal["main"])
                for i, st in enumerate(steps):
                    cx = x0 + slot * (i + 0.5)
                    fi = opt.get("last_fill", fill) if i == len(steps) - 1 else fill
                    draw_icon(cv.draw, st.get("icon") or pick_icon(st.get("label")), cx, y + r, r,
                              readable_on(fi) if fi != fill else col, fi)
                    yy = y + 2 * r + 24
                    for ln in wrap(st.get("label", ""), fl, slot - 16):
                        cv.text(cx - line_width(ln, fl) / 2, yy, ln, fl, opt.get("label_color", pal["text"]), role="body")
                        yy += fl.size * 1.3
                    if i < len(steps) - 1:
                        ax = x0 + slot * (i + 1)
                        ac = opt.get("arrow", mix(pal["text"], pal["bg"], 0.5))
                        cv.draw.line([(ax - 14, y + r), (ax + 10, y + r)], fill=ac, width=6)
                        cv.draw.polygon([(ax + 22, y + r), (ax + 6, y + r - 12), (ax + 6, y + r + 12)], fill=ac)
            elif kind == "button":
                _, val, fb, bh, opt = op
                fill = opt.get("fill", (254, 229, 0))
                tc = readable_on(fill)
                tw = fb.getlength(val) + 110
                bx = x0 + ((x1 - x0) - tw) / 2 if opt.get("center") else x0
                cv.rect([bx, y, bx + tw + 60, y + bh], fill, radius=bh // 2)
                draw_icon(cv.draw, opt.get("icon", "chat"), bx + 30 + 46, y + bh / 2, 46, tc)
                cv.text(bx + 30 + 110, y + (bh - fb.size * 1.2) / 2, [(val, False)], fb, tc, role="key")
            elif kind == "vsbadge":
                _, cx, opt = op
                r = 65
                fill = opt.get("vs_fill", pal["accent"])
                cv.draw.ellipse([cx - r, y - r, cx + r, y + r], fill=fill, outline=pal["white"], width=8)
                fv = font("black", 50)
                cv.text(cx - fv.getlength("VS") / 2, y - 34, [("VS", False)], fv, readable_on(fill), role="minor")
            elif kind == "vline":
                _, vx, ln, opt = op
                if ln > 4:
                    cv.rect([vx - 2, y, vx + 2, y + ln], opt.get("line") or mix(opt.get("badge", pal["main"]), pal["bg"], 0.6))
            elif kind == "panel":
                _, cx, cw, ch, ci, opt = op
                fills = opt.get("fills") or [mix(pal["text"], pal["bg"], 0.92), pal["main"]]
                cv.rect([cx, y, cx + cw, y + ch], fills[ci], radius=28)
            elif kind == "ctext":
                _, cx, ln, f, kind2, ci, opt = op
                fills = opt.get("fills") or [mix(pal["text"], pal["bg"], 0.92), pal["main"]]
                col = readable_on(fills[ci], pal["text"])
                if kind2 == "head":
                    hc = opt.get("heads", [None, None])[ci] or col
                    cv.text(cx, y, ln, f, hc if contrast(hc, fills[ci]) >= 3 else col, role="key")
                else:
                    ind = f.size * 0.9
                    if kind2 == "dot":
                        r = f.size * 0.13
                        cy = y + f.size * 0.62
                        cv.draw.ellipse([cx + r, cy - r, cx + 3 * r, cy + r], fill=col)
                    cv.text(cx + ind, y, ln, f, col)
            elif kind == "dots":
                _, dx0, dx1, size, opt = op
                c = opt.get("line") or mix(pal["text"], pal["bg"], 0.7)
                xx = dx0
                while xx < dx1:
                    cv.draw.ellipse([xx, y + size * 0.72, xx + 5, y + size * 0.72 + 5], fill=c)
                    xx += 14
            elif kind == "bubble":
                _, lines, f, size, bw, bh, pad, av, opt = op
                left = opt.get("side") == "left"
                fill = opt.get("fill", pal["white"])
                bx = x0 if left else x1 - bw
                cv.rect([bx, y, bx + bw, y + bh], fill, radius=40)
                tail = [(bx + 46, y + bh - 2), (bx + 96, y + bh - 2), (bx + 40, y + bh + 30)] if left else \
                    [(bx + bw - 96, y + bh - 2), (bx + bw - 46, y + bh - 2), (bx + bw - 40, y + bh + 30)]
                cv.draw.polygon(tail, fill=fill)
                tx = bx + pad
                if left:
                    ac = opt.get("avatar", pal["main"])
                    cv.rect([bx + pad - 8, y + pad - 12, bx + pad - 8 + av, y + pad - 12 + av], ac, radius=av // 2)
                    fa = font("black", av * 0.5)
                    cv.text(bx + pad - 8 + (av - fa.getlength(opt.get("mark", "Q"))) / 2, y + pad - 12 + av * 0.2,
                            [(opt.get("mark", "Q"), False)], fa, readable_on(ac), role="minor")
                    tx += av + 20
                yy = y + pad
                for ln in lines:
                    cv.text(tx, yy, ln, f, opt.get("color", pal["text"]), opt.get("em"), opt.get("role", "body"))
                    yy += size * 1.45
            elif kind == "big":
                _, val, f, size, opt = op
                tw = f.getlength(val)
                if tw > (x1 - x0) * 1.001:  # 폭을 넘으면 줄여서 그린다(잘림 방지)
                    f = font("black", size * (x1 - x0) / tw)
                    tw = f.getlength(val)
                bx = x0 + (x1 - x0 - tw) / 2 if (self.center_x or opt.get("center")) else x0
                cv.text(bx, y, [(val, False)], f, opt.get("color", pal["text"]), role="key",
                        stroke=opt.get("stroke", 0), stroke_color=opt.get("stroke_color"))
        for t in cv.texts[self._n_before:]:
            t["area"] = self.area
        return self


# ---------------------------------------------------------------- 스타일
def safe_box(W, H):
    """핵심 글자 영역: 가운데 1080x1080(4:5에서 위아래 135px 비움)."""
    top = (H - min(W, H)) // 2
    return 72, max(top, 80), W - 72, min(H - top, H - 96)


VISUAL_KEYS = ("items", "menu", "compare", "big", "anchor", "photo", "info")


def em_style(c, pal, style):
    """강조 방식 3가지: marker(형광펜 띠) · box(반전 박스) · color(글자색). 색이 바탕과 3:1이 안 되면 box로 바꾼다."""
    bg = c.get("bg")
    if style == "marker" and c.get("hl"):
        return {"hl": c["hl"]}
    if style == "box" or (bg and contrast(c["em"], bg) < 3):
        fill = c.get("box") or max((pal["accent"], pal["main"]), key=lambda x: contrast(x, bg or pal["bg"]))
        return {"box": fill}
    return {"hl": c.get("hl")} if c.get("hl") and style != "color" else {}


def add_anchor(b, a, c, pal, center=False):
    t = a.get("type")
    if t == "number":
        b.add("anumber", a["value"], color=c.get("anchor", c["em_safe"]), label=a.get("label"),
              label_color=c["title"], center=center, gap=34, chips=a.get("chips"), band=a.get("band"),
              chip_fill=c.get("chip_fill", pal["white"]), chip_color=c.get("chip_color"))
    elif t == "chips":
        b.add("chips", a["items"], chip_fill=c.get("chip_fill", pal["white"]), chip_color=c.get("chip_color"), gap=30)
    elif t == "table":
        b.add("table", (a["head"], a["rows"]), cell_fills=c.get("cell_fills"), gap=34)
    elif t == "timeline":
        b.add("timeline", (a.get("start", 9), a.get("end", 21), a["marks"]), color=c["title"],
              accent=c.get("icon_fill", pal["main"]), gap=34)
    elif t == "icon":
        b.add("icon", a.get("name", "check"), fill=c.get("icon_fill", pal["main"]),
              color=readable_on(c.get("icon_fill", pal["main"])), center=center, gap=40)
    elif t == "flow":
        b.add("flow", a["steps"], fill=c.get("icon_fill", pal["main"]), color=readable_on(c.get("icon_fill", pal["main"])),
              last_fill=pal["accent"], label_color=c["title"], arrow=c["sub"], gap=34)
    elif t == "vs":
        b.add("compare", [a["left"], a["right"]], vs=True, fills=c.get("fills"), heads=c.get("heads", [None, None]),
              vs_fill=pal["accent"], gap=34)
    elif t == "button":
        b.add("button", a.get("text", "카카오톡 채널 열기"), fill=tuple(hex2rgb(a["color"])) if a.get("color") else (254, 229, 0),
              icon=a.get("icon", "chat"), center=center, gap=34)


def add_content(b, s, pal, cover, colors=None):
    """원고 한 장의 칸을 블록에 넣는다. 장마다 시각 앵커(숫자·아이콘·도식·사진·리스트) 1개를 둔다."""
    c = dict(title=pal["text"], text=pal["text"], em=pal["accent"], sub=pal["muted"], hl=None)
    c.update(colors or {})
    c.setdefault("em_safe", c["em"] if not c.get("bg") or contrast(c["em"], c["bg"]) >= 3 else c["title"])
    style = s.get("em_style") or c.get("em_style") or "auto"
    emk = em_style(c, pal, style)
    anchor = s.get("anchor")
    a_top = anchor and anchor.get("type") in ("number", "icon") and anchor.get("pos", "top") == "top"
    a_mid = anchor and not a_top and anchor.get("pos") == "mid"
    if not cover and not anchor and not any(s.get(k) for k in VISUAL_KEYS) and not c.get("no_auto_icon"):
        anchor = {"type": "icon", "name": pick_icon((s.get("heading") or "") + (s.get("q") or "") + (s.get("text") or ""))}
        a_top = True
        b.auto_icon = True
    if s.get("kicker"):
        b.add("kicker", s["kicker"], fill=c.get("kicker_fill", pal["accent"]), gap=26)
    if a_top:
        add_anchor(b, anchor, c, pal, center=b.center_x)
    if s.get("big"):
        b.add("big", s["big"], color=c.get("big", c["title"]), stroke=c.get("big_stroke", 0),
              stroke_color=c.get("big_stroke_color"), gap=10)
    key = "title" if cover or s.get("role") == "cta" else "heading"
    head = s.get("title") or s.get("heading")
    if s.get("q"):  # 질문은 제목처럼 크게, 번호(Q1)는 그 위에
        if s.get("_qn"):
            b.add("text", f"Q{s['_qn']}.", size=56, font="black", color=c["em_safe"], role="key", gap=14, tight=True)
        head = s["q"]
    fit = c.get("fit") if key == "title" else None
    b.add(key, head, color=c["title"], em=c["em"], role="key", fit=fit,
          stroke=c.get("title_stroke", 0), stroke_color=c.get("title_stroke_color"),
          size=c.get("title_size") if key == "title" else None, gap=c.get("title_gap", 34), **emk)
    if c.get("rule"):
        b.add("rule", True, color=c["rule"], gap=30)
    sub = s.get("subtitle") if cover else (s.get("a") or s.get("text"))
    if sub:
        b.add("text", sub, color=c["text"] if not cover else c.get("subtitle", c["text"]),
              em=c["em_safe"] if contrast(c["em_safe"], c.get("bg") or pal["bg"]) >= 4.5 else c["title"],
              font="semibold" if s.get("a") else "regular", size=c.get("sub_size", 40) if cover else None, gap=34)
    if a_mid:
        add_anchor(b, anchor, c, pal, center=b.center_x)
    if s.get("items"):
        mode = "check" if s.get("checklist") else ("step" if s.get("steps") else "number")
        b.add("items", s["items"], mode=mode, color=c["title"], sub=c["sub"], em=c["em_safe"],
              badge=c.get("badge", pal["main"]), badge_bg=c.get("badge_bg", pal["white"]),
              cards=s.get("cards", bool(s.get("checklist"))) and not c.get("no_cards"), card_fill=c.get("card_fill", pal["white"]))
    if s.get("compare"):
        b.add("compare", s["compare"], fills=c.get("fills"), heads=c.get("heads", [None, None]))
    if s.get("menu"):
        b.add("menu", s["menu"], color=c["title"], sub=c["sub"], em=c["em_safe"], price=c.get("price", c["title"]),
              line=c.get("line"))
    if s.get("info"):
        b.add("info", s["info"], color=c["text"], label_color=c.get("label", pal["main"]), em=c["em_safe"])
    if anchor and not a_top and not a_mid:
        add_anchor(b, anchor, c, pal, center=b.center_x)
    if s.get("bar"):
        b.add("bar", s["bar"], fill=c.get("bar_fill", pal["text"]), em=pal["accent"], gap=30)
    if s.get("note"):
        b.add("text", s["note"], color=c["sub"], size=32, role="note", gap=0)


def tones(pal):
    """(밝은 바탕, 어두운 바탕). 어두운 바탕은 브랜드 주색이 흰 글자와 4.5:1 이상이면 주색, 아니면 글자색."""
    dark = pal["main"] if contrast(pal["main"], pal["white"]) >= 4.5 else pal["text"]
    if contrast(dark, pal["white"]) < 4.5:
        dark = (26, 26, 26)
    light = pal["bg"] if contrast(pal["bg"], pal["text"]) >= 4.5 else (247, 246, 242)
    return light, dark


def em_on(pal, bg, fallback):
    """강조색을 이 바탕에 써도 되는지(4.5:1). 안 되면 대신 쓸 색."""
    for c in (pal["accent"], pal["main"]):
        if contrast(c, bg) >= 4.5:
            return c
    return fallback


def style_paint(code, cv, s, pal, cover, W, H):
    """배경을 칠하고 내용 블록을 돌려준다."""
    sx0, sy0, sx1, sy1 = safe_box(W, H)
    photo, focus, hint = s.get("photo"), s.get("photo_focus", [0.5, 0.5]), s.get("photo_hint", "")
    if cover:  # 표지 핵심 글자는 가운데 1012px 안(프로필 격자 3:4 잘림 대비)
        sx0, sx1 = max(sx0, 34 + 40), min(sx1, W - 34 - 40)
    white, dark = pal["white"], pal["text"]

    if code in ("S01", "S02"):
        cv.paste_photo(photo, (0, 0, W, H), focus=focus, hint=hint)
        if code == "S01":
            cv.gradient(H * 0.5, H * 0.7, a_to=200)
            cv.rect([0, int(H * 0.7), W, H], (0, 0, 0), alpha=200)
            b = Block(cv, (sx0, sy0, sx1, sy1), pal, {"title": "bold", "heading": "bold"}, align="bottom",
                      sizes={"title": 64, "heading": 52, "text": 34})
            add_content(b, s, pal, cover, dict(title=white, text=white, subtitle=white, em=pal["accent"], sub=white,
                                               no_auto_icon=True))
        else:  # 피사체는 위 55~60%, 아래 40%에 어두운 그라데이션 + 큰 흰 제목
            shade = mix(pal["main"], (0, 0, 0), 0.6)
            al = 185 if cover else 205  # 본문 장은 사진이 바빠도 읽히게 더 어둡게
            cv.gradient(H * 0.38, H * 0.62, color=shade, a_from=0, a_to=al)
            cv.rect([0, int(H * 0.62), W, H], shade, alpha=al)
            cv.gradient(H * 0.62, H, color=shade, a_from=0, a_to=70)
            b = Block(cv, (sx0, int(H * 0.46), sx1, H - 110), pal, {"title": "black", "heading": "black"},
                      align="bottom", sizes={"heading": 80})
            add_content(b, s, pal, cover, dict(title=white, text=white, subtitle=(240, 236, 230), em=pal["accent"],
                                               sub=(230, 225, 220), bg=shade, fit=(104, 150), sub_size=36,
                                               no_auto_icon=True))
        return b

    if code == "S03":  # 매거진
        cv.img.paste(Image.new("RGB", (W, H), pal["bg"]), (0, 0))
        ph_bottom = int(H * (0.6 if cover else 0.667))  # 위 60~67% 풀폭 사진
        cv.paste_photo(photo, (0, 0, W, ph_bottom), focus=focus, hint=hint)
        y = ph_bottom + 48
        if s.get("kicker_en"):
            f = font("semibold", 24)
            cv.text(72, y, [("  ".join(s["kicker_en"].upper()), False)], f, pal["main"], role="minor")
            y += 44
        b = Block(cv, (84, y, W - 84, H - 90), pal, {"title": "black", "heading": "black"},
                  sizes={"title": 84, "heading": 88, "text": 40})
        add_content(b, s, pal, cover, dict(title=pal["text"], em=pal["main"], bg=pal["bg"], no_auto_icon=True))
        return b

    if code == "S04":  # 브랜드 색: 표지·마지막 장에 주색을 통째로
        cv.img.paste(Image.new("RGB", (W, H), pal["main"]), (0, 0))
        on = pal["on_main"]
        if cover or s.get("role") == "cta":
            area_top = sy0
            if cover and photo and os.path.exists(photo):
                cv.paste_photo(photo, (sx0, sy0, sx1, sy0 + 520), radius=24, focus=focus, hint=hint)
                area_top = sy0 + 560
            if cover:
                b = Block(cv, (sx0, area_top, sx1, sy1), pal, {"title": "black"}, align="center" if area_top == sy0 else "top",
                          sizes={"title": 112, "text": 42})
            else:  # 마지막 장: 위에 큰 제목, 아래에 행동 버튼까지 채운다
                b = Block(cv, (84, 170, W - 84, 1150), pal, {"title": "black"}, align="spread", sizes={"title": 112, "text": 44})
                b.spread_cap = 420  # 버튼을 아래쪽으로 내려 화면을 위아래로 쓴다
            add_content(b, s, pal, cover, dict(title=on, text=mix(on, pal["main"], 0.08), subtitle=mix(on, pal["main"], 0.12),
                                               em=pal["accent"], bg=pal["main"], kicker_fill=pal["accent"],
                                               sub=mix(on, pal["main"], 0.18), icon_fill=pal["accent"], label=pal["accent"],
                                               fit=(124, 168) if cover else (112, 150), no_auto_icon=True,
                                               box=pal["accent"]))
            return b
        card = pal["bg"] if contrast(pal["bg"], pal["text"]) >= 7 else white
        cv.rect([72, sy0, W - 72, sy1], card, radius=24)
        b = Block(cv, (72 + 64, sy0 + 72, W - 72 - 64, sy1 - 72), pal, {"heading": "black", "title": "black"}, align="center")
        add_content(b, s, pal, False, dict(title=pal["main"] if contrast(pal["main"], card) >= 4.5 else pal["text"],
                                           em=pal["text"], hl=mix(pal["accent"], card, 0.35), label=pal["main"],
                                           sub=mix(pal["text"], card, 0.35), bg=card))
        return b

    if code == "S05":  # 깔끔한 글자 카드 (번호·체크 리스트)
        light, deep = tones(pal)
        cv.img.paste(Image.new("RGB", (W, H), light), (0, 0))
        hl = mix(pal["accent"], light, 0.25)
        base = dict(title=dark, em=dark, hl=hl, bg=light, title_gap=30, price=dark, line=mix(dark, light, 0.75),
                    fills=[mix(dark, light, 0.92), deep], heads=[pal["main"], pal["accent"]],
                    em_safe=em_on(pal, light, dark), anchor=em_on(pal, light, dark), icon_fill=deep,
                    box=deep if contrast(deep, light) > contrast(pal["accent"], light) else pal["accent"])
        if cover:
            b = Block(cv, (sx0, sy0, sx1, sy1), pal, {"title": "black"}, align="center")
            add_content(b, s, pal, True, dict(base, subtitle=pal["muted"], fit=(124, 168), sub_size=36))
            return b
        tone = s.get("tone")
        if tone in ("dark", "brand", "deep") or s.get("role") == "cta":  # 어두운 장: 주색·짙은 색 바탕
            if tone == "deep":
                deep = hex2rgb(s.get("deep") or pal.get("deep_hex") or "#111A3A")
            cv.img.paste(Image.new("RGB", (W, H), deep), (0, 0))
            on = readable_on(deep)
            em = em_on(pal, deep, on)
            panel = mix(on, deep, 0.84)
            b = Block(cv, (84, 150, W - 84, 1190), pal, {"heading": "black", "title": "black"},
                      align="center" if s.get("role") == "cta" else "spread")
            add_content(b, s, pal, False, dict(title=on, text=mix(on, deep, 0.1), em=em, sub=mix(on, deep, 0.3),
                                               title_gap=30, badge=pal["accent"], bg=deep, em_safe=em, anchor=em,
                                               label=em, kicker_fill=pal["accent"], line=mix(on, deep, 0.75),
                                               price=em, fills=[mix(on, deep, 0.12 if tone != "deep" else 0.16) if False else
                                                                mix(deep, (255, 255, 255), 0.12), pal["accent"]],
                                               heads=[on, None], icon_fill=pal["accent"], box=pal["accent"],
                                               chip_fill=mix(deep, (255, 255, 255), 0.14), chip_color=on,
                                               card_fill=mix(deep, (255, 255, 255), 0.1), bar_fill=pal["accent"]))
            return b
        b = Block(cv, (84, 150, W - 84, 1190), pal, {"heading": "black"}, align="spread")
        add_content(b, s, pal, False, base)
        return b

    if code == "S07":  # 손글씨 메모
        paper = (246, 238, 220)
        cv.img.paste(Image.new("RGB", (W, H), paper), (0, 0))
        for yy in range(sy0 + 40, H - 60, 64):
            cv.rect([60, yy, W - 60, yy + 2], (226, 214, 190))
        cv.tape = pal["accent"]  # 내용 위치가 정해진 뒤 render_slide에서 붙인다
        brown = (74, 52, 34)
        b = Block(cv, (sx0, sy0 + 40, sx1, sy1), pal, {"title": "hand", "heading": "hand"},
                  align="center", sizes={"title": 190, "heading": 160, "text": 44})
        add_content(b, s, pal, cover, dict(title=brown, text=(60, 48, 38), subtitle=(60, 48, 38), em=(176, 72, 40),
                                           sub=(110, 92, 72), label=(150, 70, 40), badge=(150, 90, 50)))
        b.center_x = cover
        return b

    if code == "S08":  # 전단·특가 (이벤트)
        bgc = pal["accent"]
        cv.img.paste(Image.new("RGB", (W, H), bgc), (0, 0))
        for i in range(-H, W, 90):  # 사선 줄무늬
            cv.draw.line([(i, 0), (i + H, H)], fill=mix(bgc, white, 0.12), width=24)
        on = readable_on(bgc)
        if cover:
            b = Block(cv, (sx0, sy0, sx1, sy1), pal, {"title": "black"}, align="center", center_x=True,
                      sizes={"title": 104, "big": 230})
            add_content(b, s, pal, True, dict(title=pal["main"] if contrast(pal["main"], bgc) >= 3 else on,
                                              text=on, subtitle=on, em=pal["main"],
                                              big=white, big_stroke=10, big_stroke_color=pal["main"],
                                              kicker_fill=pal["main"]))
            return b
        cv.rect([72, sy0, W - 72, sy1], white, radius=24)
        b = Block(cv, (72 + 56, sy0 + 60, W - 72 - 56, sy1 - 56), pal, {"heading": "black"}, align="spread",
                  center_x=True, sizes={"big": 330, "heading": 84})
        add_content(b, s, pal, False, dict(title=pal["main"], em=pal["main"], kicker_fill=pal["accent"],
                                           big=pal["main"], bg=white, no_auto_icon=bool(s.get("big"))))
        return b

    if code == "S09":  # 고급스러운
        cream = (247, 243, 236)
        cv.img.paste(Image.new("RGB", (W, H), cream), (0, 0))
        ink = (43, 43, 43)
        y = sy0
        if photo or hint:
            cv.paste_photo(photo, (84, sy0, W - 84, sy0 + (560 if cover else 470)), focus=focus, hint=hint)
            y = sy0 + (560 if cover else 470) + 50
        b = Block(cv, (150, y, W - 150, sy1), pal, {"title": "serif_bold", "heading": "serif_bold", "text": "serif"},
                  align="center" if y == sy0 else "top", center_x=True,
                  sizes={"title": 66, "heading": 52, "text": 34, "kicker": 24})
        gold = mix(pal["main"], cream, 0.0)
        add_content(b, s, pal, cover, dict(title=ink, text=(70, 70, 70), subtitle=(90, 90, 90), em=gold,
                                           kicker_fill=gold))
        for it in b.items:  # 가운데 정렬
            it[2]["center"] = True
        return b

    if code == "S10":  # 화면·메신저 모양 (Q&A)
        chat_bg = mix(pal["main"], white, 0.82)
        cv.img.paste(Image.new("RGB", (W, H), chat_bg), (0, 0))
        if cover:
            cv.rect([72, sy0 + 120, W - 72, sy0 + 250], white, radius=65)
            cv.draw.ellipse([W - 72 - 108, sy0 + 152, W - 72 - 52, sy0 + 208], outline=pal["main"], width=8)
            cv.draw.line([(W - 72 - 60, sy0 + 200), (W - 72 - 36, sy0 + 226)], fill=pal["main"], width=9)
            q = s.get("search") or plain(s.get("title", "")).replace("\n", " ")[:14]
            f = font("semibold", 44)
            cv.text(72 + 50, sy0 + 160, [(q, False)], f, pal["text"], role="minor")
            b = Block(cv, (sx0, sy0 + 320, sx1, sy1), pal, {"title": "black"}, align="center", sizes={"title": 88})
            add_content(b, s, pal, True, dict(title=pal["text"], em=pal["main"], subtitle=pal["muted"]))
            return b
        light, deep = tones(pal)
        dk = s.get("tone") == "dark"
        bgc = deep if dk else light
        cv.img.paste(Image.new("RGB", (W, H), bgc), (0, 0))
        on = readable_on(bgc)
        ems = em_on(pal, bgc, on)
        b = Block(cv, (84, sy0, W - 84, sy1), pal, {"heading": "black"}, align="center", sizes={"heading": 88, "qa": 42})
        if s.get("_qn"):
            b.add("text", f"Q{s['_qn']}.", size=60, font="black", color=ems, role="key", gap=14)
        head = s.get("q") or s.get("heading")
        if head:
            b.add("heading", head, color=on, em=ems, role="key", gap=40)
        if s.get("a"):
            af = pal["accent"] if dk else deep
            ac = readable_on(af)
            b.add("bubble", s["a"], side="right", fill=af, color=ac, em=em_on(pal, af, ac), gap=40)
        if s.get("anchor"):
            add_anchor(b, s["anchor"], dict(title=on, em_safe=ems, sub=mix(on, bgc, 0.4), icon_fill=deep if not dk else pal["accent"],
                                            fills=[mix(on, bgc, 0.9), deep if not dk else pal["accent"]]), pal)
        if s.get("note"):
            b.add("text", s["note"], color=mix(on, bgc, 0.3), size=32, role="note", gap=0)
        if s.get("info"):
            b.add("info", s["info"], color=on, label_color=ems)
        return b

    if code == "S11":  # 레트로: 누런 종이 + 두 줄 테두리 + 그림자 글자
        paper = (241, 228, 200)
        red, green, ink = (196, 52, 38), (34, 96, 70), (40, 30, 24)
        cv.img.paste(Image.new("RGB", (W, H), paper), (0, 0))
        for k in range(0, H, 6):  # 종이 결
            cv.rect([0, k, W, k + 1], mix(paper, (200, 180, 140), 0.12))
        cv.rect([20, 20, W - 20, H - 20], paper, outline=ink, width=6)
        cv.rect([34, 34, W - 34, H - 34], paper, outline=red, width=3)
        b = Block(cv, (sx0 + 20, sy0, sx1 - 20, sy1), pal, {"title": "black", "heading": "black"}, align="center",
                  center_x=cover, sizes={"title": 112, "heading": 76})
        add_content(b, s, pal, cover, dict(title=red, text=ink, subtitle=ink, em=green, sub=mix(ink, paper, 0.25),
                                           title_stroke=0, kicker_fill=green, badge=red, label=red, price=red,
                                           line=mix(ink, paper, 0.6), big=red,
                                           fills=[mix(ink, paper, 0.85), green]))
        cv.retro_shadow = ink
        return b

    raise KeyError(code)


# ---------------------------------------------------------------- 렌더·점검
def render_slide(spec, s, idx, total, pal, W, H, base_dir):
    role = s.get("role", "cover" if idx == 0 else "body")
    s = dict(s, role=role)
    if s.get("photo") and not os.path.isabs(s["photo"]):
        s["photo"] = os.path.join(base_dir, s["photo"])
    code = s.get("style") or (spec.get("cover_style") if role == "cover" else spec.get("body_style")) or "S05"
    notes = []
    if code not in STYLES or not STYLES[code][1]:
        notes.append(f"{code}는 렌더러에 아직 없어 S05로 대신 그림")
        code = "S05"
    if s.get("photo") and s.get("photo_match") not in (None, True, "ok"):
        notes.append(f"photo_match: 확인 필요 — 사진이 문구와 맞는지 확인하세요 ({s.get('photo_match')})")
    if code in ("S01", "S02", "S03", "S09") and not (s.get("photo") and os.path.exists(s["photo"])):
        notes.append(f"사진 필요: {code}는 실제 사진이 있어야 해요 → 글자 카드(S05)로 대신 그림 ({s.get('photo_hint') or '사진 없음'})")
        code = "S05"
        s.pop("photo", None)
        s.pop("photo_hint", None)
    slides = spec["slides"]
    if s.get("q") and sum(1 for x in slides if x.get("q")) > 1:  # 질문 번호(Q1, Q2 …), 질문이 2개 이상일 때만
        s["_qn"] = sum(1 for x in slides[:idx + 1] if x.get("q"))
    if "tone" not in s and role == "body":  # 장마다 리듬: 밝은 장·어두운 장 번갈아(body_tone: alternate)
        mode = spec.get("body_tone", "light")
        if mode == "alternate":
            k = sum(1 for x in slides[1:idx + 1] if x.get("role", "body") == "body")
            s["tone"] = "dark" if k % 2 == 0 else "light"
        else:
            s["tone"] = mode
    cv = Canvas(W, H, pal["bg"])
    cv.pal_accent = pal["accent"]
    b = style_paint(code, cv, s, pal, role == "cover", W, H).render()
    if getattr(cv, "tape", None):  # 손글씨 메모: 내용 바로 위에 마스킹테이프
        tape = Image.new("RGBA", (300, 70), cv.tape + (170,))
        tape = tape.rotate(-4, expand=True, resample=Image.BICUBIC)
        cv.img.alpha_composite(tape, (W // 2 - 155, int(max(20, b.top - 130))))
    if getattr(cv, "retro_shadow", None):  # 레트로: 제목에 어긋난 그림자
        for t in list(cv.texts):
            if t["role"] == "key" and t["size"] >= 60:
                cv.texts.insert(cv.texts.index(t), dict(t, x=t["x"] + 6, y=t["y"] + 6, color=cv.retro_shadow,
                                                        em=cv.retro_shadow, role="minor"))
    if spec.get("chrome") and role != "cover":  # 머리말·쪽번호·진행 막대(기본 끔)
        chrome(cv, spec, idx, total, W, H)
    acct = spec.get("account")
    if acct:  # 계정 이름(글자, 로고 아님): 본문은 왼쪽 아래 작게, 표지·마지막 장은 조금 크게
        px = cv.img.getpixel((90, H - 60))[:3]
        big = role in ("cover", "cta")
        fa = font("bold" if big else "semibold", 32 if big else 24)
        cv.text(84, H - (92 if big else 80), [(acct, False)], fa, mix(readable_on(px), px, 0.15 if big else 0.4), role="minor")
    if role == "cover" and spec.get("swipe_arrow", True):  # 표지에만 '넘겨서 보기 →'
        px = cv.img.getpixel((W - 120, H - 70))[:3]
        col = mix(readable_on(px), px, 0.2)
        fs = font("semibold", 26)
        t = "넘겨서 보기"
        cv.text(W - 84 - 50 - fs.getlength(t), H - 92, [(t, False)], fs, col, role="minor")
        draw_icon(cv.draw, "arrow", W - 84 - 22, H - 76, 24, col)
    bg = cv.finish()
    notes += getattr(cv, "notes", [])
    return cv.img.convert("RGB"), bg, cv.texts, b, code, notes, s


def chrome(cv, spec, idx, total, W, H):
    """본문 장 공통 틀: 위 왼쪽 시리즈 이름, 위 오른쪽 쪽번호, 아래 진행 막대. 표지와 같은 강조색으로 이어 준다."""
    corner = cv.img.getpixel((W // 2, 40))[:3]
    fg = readable_on(corner, (40, 40, 40), (235, 235, 235))
    soft = mix(fg, corner, 0.45)
    f = font("semibold", 30)
    series = spec.get("series")
    if series is None:
        first = spec["slides"][0]
        series = first.get("kicker") or spec.get("brand", {}).get("name", "")
    if series:
        cv.text(84, 58, [(plain(series), False)], f, soft, role="minor")
    fb = font("bold", 30)
    cur, tot = f"{idx + 1:02d}", f" / {total:02d}"
    tw = fb.getlength(cur) + f.getlength(tot)
    cv.text(W - 84 - tw, 58, [(cur, False)], fb, fg, role="minor")
    cv.text(W - 84 - f.getlength(tot), 58, [(tot, False)], f, soft, role="minor")
    # 진행 막대
    x0, x1, y = 84, W - 84, H - 64
    seg_gap = 8
    sw = (x1 - x0 - seg_gap * (total - 2)) / max(1, total - 1)
    acc = cv.pal_accent if contrast(cv.pal_accent, corner) >= 1.8 else fg
    for k in range(1, total):
        sx = x0 + (k - 1) * (sw + seg_gap)
        cv.rect([sx, y, sx + sw, y + 6], acc if k <= idx else mix(fg, corner, 0.82), radius=3)


def check_slide(n, s, texts, bg, block, W, H):
    res = []
    sx0, sy0, sx1, sy1 = 0, (H - min(W, H)) // 2, W, H - (H - min(W, H)) // 2
    cover = s["role"] == "cover"
    if cover:
        sx0, sx1 = 34, W - 34
    worst = None
    for t in texts:
        if t["role"] == "minor":
            continue
        large = t["size"] >= 60 or (t["size"] >= 46 and t["role"] == "key")
        need = 3.0 if large else 4.5
        for (bb, col) in t.get("boxes", []):
            x0, y0, x1, y1 = [int(v) for v in bb]
            x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
            if x1 <= x0 or y1 <= y0:
                continue
            reg = bg.crop((x0, y0, x1, y1)).resize((max(1, (x1 - x0) // 6), max(1, (y1 - y0) // 6)))
            ratios = sorted(contrast(col, p) for p in (reg.get_flattened_data() if hasattr(reg, 'get_flattened_data') else reg.getdata()))
            r = ratios[len(ratios) // 10]  # 하위 10% 값(사진 배경의 밝은 점 대비)
            if t["stroke"]:
                r = max(r, contrast(col, t["stroke_color"]))
            if worst is None or r / need < worst[0] / worst[1]:
                worst = (r, need, plain("".join(x for x, _ in t["line"]))[:12])
            if t["role"] == "key" and (y0 < sy0 or y1 > sy1 or x0 < sx0 or x1 > sx1):
                res.append(("FAIL", "안전 영역", f"핵심 글자 '{plain(t['line'][0][0])[:10]}…'가 가운데 "
                            f"{'1012px 폭·' if cover else ''}1080×1080 밖(y {y0}~{y1})"))
            if x0 < 30 or x1 > W - 30 or bb[2] > W or bb[0] < 0:
                res.append(("FAIL", "잘림", f"'{plain(t['line'][0][0])[:10]}' 글자가 가장자리 30px 안까지 나감(잘림)"))
            elif t.get("area") and t["role"] == "key" and bb[2] > t["area"][2] + 6:
                res.append(("FAIL", "잘림", f"'{plain(t['line'][0][0])[:10]}' 글자가 칸 오른쪽을 넘음 → 짧게 쓰거나 단위를 띄어 쓰세요"))
    if worst:
        r, need, txt = worst
        lvl = "OK" if r >= need else ("WARN" if r >= need * 0.8 else "FAIL")
        res.append((lvl, "대비", f"가장 낮은 곳 {r:.1f}:1 (기준 {need}:1, '{txt}')"))
    if block.overflow:
        res.append(("FAIL", "넘침", "최소 글자 크기로 줄여도 칸을 넘음 → 글을 줄이거나 장을 나누세요"))
    elif block.scale < 1:
        res.append(("WARN", "과밀", f"글자를 {int(block.scale * 100)}%로 줄여서 맞춤 → 글을 줄이면 더 잘 읽혀요"))
    if not (s.get("photo") or s.get("photo_hint")):  # 사진 장은 사진이 공간을 채운다
        ys = [bb[1] for t in texts if t["role"] != "minor" for bb, _ in t.get("boxes", [])]
        ye = [bb[3] for t in texts if t["role"] != "minor" for bb, _ in t.get("boxes", [])]
        if ys:
            top, bot = min(min(ys), block.top), max(max(ye), block.top + block.height)
            share = (bot - top) / H
            if share < 0.40:
                res.append(("WARN", "빈 공간 과다", f"내용이 캔버스 세로의 {share * 100:.0f}%만 차지(40% 이상 권장) "
                                                  "→ 글을 한 덩어리로 키우거나 항목을 더하세요"))
            elif share < 0.60:
                res.append(("WARN", "콘텐츠 높이", f"내용 높이 {share * 100:.0f}% (60% 이상 권장, 목표 70~80%) "
                                                "→ 앵커(숫자·표·카드)를 키우거나 항목을 더하세요"))
    res += text_checks(s)
    sizes = [t["size"] for t in texts if t["role"] != "minor"]
    if sizes and min(sizes) < 30:
        res.append(("WARN", "글자 크기", f"가장 작은 글자 {min(sizes)}px (최소 30px)"))
    body_sizes = [t["size"] for t in texts if t["role"] not in ("minor", "note", "label")]
    if sizes and min(sizes) < 30:
        pass
    elif body_sizes and not cover and min(body_sizes) < 40 and not (s.get("photo") or s.get("photo_hint")):
        res.append(("WARN", "글자 크기", f"본문 장 가장 작은 글자 {min(body_sizes)}px (폰에서 읽히려면 40px 이상 권장)"))
    return res


def text_checks(s):
    res = []
    blob = json.dumps({k: v for k, v in s.items() if not k.startswith("_")}, ensure_ascii=False)
    holes = re.findall(r"\[직접 입력[^\]]*\]", blob)
    if holes:
        res.append(("FAIL", "빈칸", f"원고에 채우지 않은 칸 {len(holes)}개: {holes[0][:30]} → 사장님 자료로 채우세요"))
    if s["role"] == "cover":
        n = len(re.sub(r"\s", "", plain(s.get("title", ""))))
        if not 12 <= n <= 19:
            res.append(("WARN", "표지 제목", f"{n}자 (권장 12~19자, 공백 빼고)"))
    else:
        body = plain(s.get("text", "")) + plain(s.get("q", "")) + plain(s.get("a", ""))
        for it in s.get("items", []):
            body += plain(it if isinstance(it, str) else it.get("title", "") + it.get("text", ""))
        for row in s.get("info", []):
            body += plain(row[1])
        n = len(re.sub(r"\s", "", body))
        if n > 160:
            res.append(("FAIL", "글자 과밀", f"본문 {n}자 (권장 80자 안팎, 최대 120자)"))
        elif n > 120:
            res.append(("WARN", "글자 과밀", f"본문 {n}자 (권장 80자 안팎, 최대 120자)"))
    return res


def deck_checks(spec):
    res = []
    slides = spec.get("slides", [])
    if len(slides) > 10:
        res.append(("FAIL", "장수", f"{len(slides)}장 (10장 이하)"))
    if slides and slides[-1].get("role") != "cta":
        res.append(("WARN", "마지막 장", "마지막 장이 CTA(role: cta)가 아님 → 예약·방문·저장 중 행동 1개로 끝내세요"))
    if spec.get("logo") or any(s.get("logo") for s in slides):
        res.append(("FAIL", "로고", "이미지 안에 로고·워터마크를 넣지 않습니다(인스타 추천 조건)"))
    return res


def print_report(rows):
    mark = {"OK": "통과", "WARN": "주의", "FAIL": "고칠 것"}
    for where, lvl, item, msg in rows:
        print(f"  [{mark[lvl]}] {where} {item}: {msg}")
    nf = sum(1 for r in rows if r[1] == "FAIL")
    nw = sum(1 for r in rows if r[1] == "WARN")
    print(f"점검 결과: 고칠 것 {nf}, 주의 {nw}")
    return nf


def load_spec(path):
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    if not spec.get("slides"):
        sys.exit("slides가 비어 있어요.")
    return spec


def cmd_render(a):
    spec = load_spec(a.spec)
    base_dir = os.path.dirname(os.path.abspath(a.spec))
    os.makedirs(a.out, exist_ok=True)
    if a.html or not HAS_PIL:
        if not a.html:
            print("Pillow가 없어 HTML로 만듭니다(설치: pip install pillow).")
        return cmd_html(spec, a.out, base_dir)
    W, H = SIZES.get(spec.get("ratio", "4:5"), SIZES["4:5"])
    pal = palette(spec.get("brand", {}))
    rows = [("전체", *r) for r in deck_checks(spec)]
    slides = spec["slides"]
    report = []
    sigs = []
    bgs = []
    for i, s in enumerate(slides):
        img, bg, texts, block, code, notes, s2 = render_slide(spec, s, i, len(slides), pal, W, H, base_dir)
        stem = os.path.join(a.out, f"{i + 1:02d}")
        files = []
        if a.format in ("png", "both"):
            img.save(stem + ".png", optimize=True)
            files.append(stem + ".png")
        if a.format in ("jpg", "both"):
            img.save(stem + ".jpg", quality=92, subsampling=0, optimize=True)
            mb = os.path.getsize(stem + ".jpg") / 1048576
            if mb > 8:
                rows.append((f"{i + 1}장", "FAIL", "용량", f"JPEG {mb:.1f}MB (8MB 이하)"))
            files.append(stem + ".jpg")
        res = check_slide(i + 1, s2, texts, bg, block, W, H)
        res += [("WARN", "참고", n) for n in notes]
        if getattr(block, "auto_icon", False):
            res.append(("WARN", "시각 앵커", "숫자·사진·도식이 없어 아이콘을 자동으로 넣음 → anchor로 숫자·도식을 지정하면 더 좋아요"))
        rows += [(f"{i + 1}장({code})", *r) for r in res]
        bgs.append(bg.getpixel((W - 6, 6)) if not s2.get("photo") else ("photo", i))
        sigs.append((code, s2.get("tone"), tuple(sorted({k for k, _, _ in block.items if k not in ("space", "rule")}))))
        report.append({"slide": i + 1, "style": code, "files": files,
                       "checks": [dict(level=r[0], item=r[1], message=r[2]) for r in res]})
    brun = 1
    for i in range(1, len(bgs)):
        brun = brun + 1 if bgs[i] == bgs[i - 1] else 1
        if brun == 3:
            rows.append((f"{i + 1}장", "WARN", "같은 바탕", f"{i - 1}~{i + 1}장 3장 연속 같은 바탕색 → 주색·짙은 색 장을 섞으세요"))
    run = 1
    for i in range(1, len(sigs)):  # 같은 레이아웃이 이어지면 템플릿처럼 보인다
        run = run + 1 if sigs[i] == sigs[i - 1] else 1
        if run == 2:
            rows.append((f"{i + 1}장", "WARN", "같은 레이아웃", f"{i}~{i + 1}장이 같은 틀 → 앵커(숫자·도식·체크)나 바탕을 바꾸세요"))
        elif run >= 3:
            rows.append((f"{i + 1}장", "FAIL", "같은 레이아웃", f"{i - run + 2}~{i + 1}장 {run}장 연속 같은 틀"))
    for n in sorted(_font_notes):
        rows.append(("전체", "WARN", "폰트", n))
    with open(os.path.join(a.out, "check.json"), "w", encoding="utf-8") as f:
        json.dump({"version": VERSION, "size": [W, H], "slides": report,
                   "deck": [dict(level=r[1], item=r[2], message=r[3]) for r in rows if r[0] == "전체"]},
                  f, ensure_ascii=False, indent=1)
    print(f"{len(slides)}장 만들었어요 → {a.out}")
    nf = print_report([r for r in rows if r[1] != "OK" or a.verbose])
    return 1 if (nf and a.strict) else 0


def cmd_check(a):
    spec = load_spec(a.spec)
    pal = palette(spec.get("brand", {}))
    rows = [("전체", *r) for r in deck_checks(spec)]
    for i, s in enumerate(spec["slides"]):
        s = dict(s, role=s.get("role", "cover" if i == 0 else "body"))
        rows += [(f"{i + 1}장", *r) for r in text_checks(s)]
    for k in ("main", "accent"):
        r = contrast(pal[k], readable_on(pal[k]))
        if r < 4.5:
            rows.append(("색", "WARN", "대비", f"{k} 색 위 글자 대비 {r:.1f}:1 → 큰 제목에만 쓰세요"))
    r = contrast(pal["text"], pal["bg"])
    rows.append(("색", "OK" if r >= 4.5 else "FAIL", "대비", f"본문 글자색/바탕색 {r:.1f}:1"))
    print_report(rows)


# ---------------------------------------------------------------- HTML 대체 경로
CSS = """
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
body{margin:0;background:#777;font-family:Pretendard,'Apple SD Gothic Neo','Malgun Gothic',sans-serif}
.card{width:1080px;height:1350px;position:relative;overflow:hidden;margin:0 auto 40px;box-sizing:border-box;
 word-break:keep-all;background:var(--bg);color:var(--text)}
.ph{position:absolute;inset:0;background-size:cover;background-position:center}
.grad{position:absolute;inset:0;background:linear-gradient(to bottom,rgba(0,0,0,0) 30%,rgba(0,0,0,.84) 100%)}
.box{position:absolute;left:84px;right:84px;top:135px;bottom:135px;display:flex;flex-direction:column;justify-content:center}
.cover .box{left:74px;right:74px}
.bottom .box{justify-content:flex-end}
.kicker{display:inline-block;align-self:flex-start;background:var(--accent);padding:12px 18px;border-radius:40px;font:700 30px Pretendard;margin-bottom:26px}
h1{font-size:92px;font-weight:800;line-height:1.2;margin:0 0 30px}
h2{font-size:68px;font-weight:800;line-height:1.25;margin:0 0 30px}
p{font-size:44px;line-height:1.5;margin:0 0 30px}
em{font-style:normal;color:var(--em)}
ol,ul{list-style:none;padding:0;margin:0}
li{display:flex;gap:26px;margin-bottom:30px;font-size:50px;font-weight:700}
li span.n{flex:0 0 61px;height:61px;border-radius:17px;background:var(--main);color:#fff;text-align:center;line-height:61px}
li small{display:block;font-size:40px;font-weight:400;color:var(--muted)}
.panel{background:#fff;border-radius:40px;padding:64px 56px}
.info div{font-size:44px;margin-bottom:14px}.info b{color:var(--main);margin-right:28px}
.bubble{background:#fff;border-radius:36px;padding:40px;font-size:46px;line-height:1.45;max-width:92%;margin-bottom:30px}
.bubble.a{align-self:flex-end;background:var(--accentl)}
.pn{position:absolute;right:84px;top:58px;font:600 30px Pretendard;opacity:.7}
"""


def cmd_html(spec, out, base_dir):
    pal = palette(spec.get("brand", {}))
    hexc = lambda c: "#%02x%02x%02x" % c
    em = lambda t: EM.sub(r"<em>\1</em>", html.escape(t or "")).replace("\n", "<br>")
    cards = []
    n = len(spec["slides"])
    for i, s in enumerate(spec["slides"]):
        role = s.get("role", "cover" if i == 0 else "body")
        code = s.get("style") or (spec.get("cover_style") if role == "cover" else spec.get("body_style")) or "S05"
        bgc, txt = pal["bg"], pal["text"]
        cls = ["card", role]
        inner = ""
        if code in ("S01", "S02", "S03", "S09") and s.get("photo"):
            src = os.path.relpath(os.path.join(base_dir, s["photo"]), out)
            inner += f'<div class="ph" style="background-image:url(\'{html.escape(src)}\')"></div>'
            if code in ("S01", "S02"):
                inner += '<div class="grad"></div>'
                cls.append("bottom")
                txt = pal["white"]
        if code in ("S04",):
            bgc, txt = pal["main"], pal["on_main"]
        if code == "S08":
            bgc, txt = pal["accent"], pal["on_accent"]
        if code == "S10":
            bgc = mix(pal["main"], pal["white"], 0.82)
        body = ""
        if s.get("kicker"):
            body += f'<span class="kicker">{html.escape(s["kicker"])}</span>'
        if s.get("big"):
            body += f'<h1 style="font-size:200px">{html.escape(s["big"])}</h1>'
        head = s.get("title") or s.get("heading")
        if head:
            body += f'<h1>{em(head)}</h1>' if role in ("cover", "cta") else f'<h2>{em(head)}</h2>'
        t = s.get("subtitle") if role == "cover" else s.get("text")
        if t:
            body += f"<p>{em(t)}</p>"
        if s.get("items"):
            lis = ""
            for k, it in enumerate(s["items"], 1):
                it = {"title": it} if isinstance(it, str) else it
                mark = "✓" if s.get("checklist") else str(k)
                lis += f'<li><span class="n">{mark}</span><div>{em(it.get("title"))}<small>{em(it.get("text", ""))}</small></div></li>'
            body += f"<ol>{lis}</ol>"
        if s.get("q"):
            body += f'<div class="bubble q"><b>Q.</b> {em(s["q"])}</div>'
        if s.get("a"):
            body += f'<div class="bubble a">{em(s["a"])}</div>'
        if s.get("info"):
            body += '<div class="info">' + "".join(f"<div><b>{html.escape(a)}</b>{em(b)}</div>" for a, b in s["info"]) + "</div>"
        if code in ("S04", "S08") and role != "cover":
            body = f'<div class="panel" style="color:{hexc(pal["text"])}">{body}</div>'
        inner += f'<div class="box">{body}</div>'
        if role != "cover":
            inner += f'<div class="pn">{i + 1}/{n}</div>'
        cards.append(f'<div class="{" ".join(cls)}" id="card{i + 1:02d}" style="--bg:{hexc(bgc)};--text:{hexc(txt)}">{inner}</div>')
    root = (f":root{{--main:{hexc(pal['main'])};--accent:{hexc(pal['accent'])};--em:{hexc(pal['accent'])};"
            f"--muted:{hexc(pal['muted'])};--accentl:{hexc(mix(pal['accent'], pal['white'], .55))}}}")
    doc = (f"<!doctype html><html lang=ko><meta charset=utf-8><title>카드뉴스</title><style>{root}{CSS}</style>"
           f"<body>{''.join(cards)}</body></html>")
    path = os.path.join(out, "cardnews.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"HTML을 만들었어요 → {path}")
    print("브라우저로 열고 창 너비를 1080px 이상으로 둔 뒤, #card01 ~ #card%02d 요소를 하나씩 캡처해 01.jpg… 로 저장하세요." % n)
    print("(요소 캡처가 안 되면 화면 캡처 후 1080×1350으로 자르기. 이 경로는 사진 대비 자동 점검을 못 하니 눈으로 확인하세요.)")
    rows = [("전체", *r) for r in deck_checks(spec)]
    for i, s in enumerate(spec["slides"]):
        s = dict(s, role=s.get("role", "cover" if i == 0 else "body"))
        rows += [(f"{i + 1}장", *r) for r in text_checks(s)]
    print_report(rows)
    return 0


def cmd_styles(_):
    print("구성 유형 (자세한 장 구성: guides/styles/cardnews.md)")
    for k, v in TYPES.items():
        print(f"  {k} {v}")
    print("디자인 스타일 (* = 렌더러 지원)")
    for k, (v, ok) in STYLES.items():
        print(f"  {k} {v}{'  *' if ok else ''}")


def cmd_fonts(_):
    if not HAS_PIL:
        print("Pillow가 없어도 폰트는 받아 둡니다.")
    for role in FONT_FILES:
        p = fetch_font(role)
        print(f"  {role}: {p or '실패'}")
    for n in sorted(_font_notes):
        print("  " + n)


def main():
    ap = argparse.ArgumentParser(description="카드뉴스 렌더러")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="원고 JSON → 카드 이미지")
    r.add_argument("spec")
    r.add_argument("-o", "--out", default="out")
    r.add_argument("--format", choices=["png", "jpg", "both"], default="both")
    r.add_argument("--html", action="store_true", help="Pillow 없이 HTML로 만들기")
    r.add_argument("--strict", action="store_true", help="고칠 것이 있으면 종료 코드 1")
    r.add_argument("--verbose", action="store_true", help="통과 항목도 출력")
    c = sub.add_parser("check", help="원고만 점검")
    c.add_argument("spec")
    sub.add_parser("styles", help="코드 목록")
    sub.add_parser("fonts", help="폰트 받기")
    sub.add_parser("version")
    a = ap.parse_args()
    if a.cmd == "render":
        sys.exit(cmd_render(a))
    if a.cmd == "check":
        cmd_check(a)
    elif a.cmd == "styles":
        cmd_styles(a)
    elif a.cmd == "fonts":
        cmd_fonts(a)
    else:
        print(VERSION)


if __name__ == "__main__":
    main()

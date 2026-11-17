#!/usr/bin/env python3
"""숏폼 조립 도구: 장면표(JSON) → 1080x1920 mp4.

표준 라이브러리 + ffmpeg만으로 동작한다. Pillow가 있으면 글자 폭을 정확히 재서
강조 단어 색·글자 단위 등장 위치가 더 정확해진다(없어도 근사값으로 그린다).

사용법
  python3 shortform.py check scenes.json            # 장면표 점검(길이·자막 글자 수·파일 존재)
  python3 shortform.py build scenes.json -o out.mp4 # 조립
  python3 shortform.py build scenes.json -o out.mp4 --guide   # 안전 영역 선을 그려서 점검용으로 조립
  python3 shortform.py frames out.mp4 --at 1,5,9    # 지정한 초의 프레임을 png로 뽑기(점검용)
  python3 shortform.py frames out.mp4 --scenes scenes.json --sheet sheet.png  # 장면마다 1장씩 이어 붙인 한 장

장면표 형식은 guides/make/shortform.md 의 "장면표" 절과 examples/shortform-scenes-sample.json 을 본다.

화면 짜임(layout)
  "info" : 정보형(IT·세무·병원 등 조회수 높은 정보 숏폼 문법). 위아래 검은 띠, 위 띠에 고정 제목 2줄
           (윗줄 흰색 + 아랫줄 강조색), 가운데 띠에 사진·캡처, 자막은 검은 상자 위 흰 글씨.
  "full" : 브이로그형(가게 하루·시간 자막). 사진·영상이 화면 전체, 글자는 흰색 + 굵은 외곽선.
장면 종류
  photo/clip 이 있으면 사진·영상 장면, 없으면 "글자 카드"(브랜드 색 면 + 큰 글자, 글자 단위로 등장).
  1번 장면은 0~3초 훅: 사진이 없으면 화면 전체 글자 카드로 크게 보여 준다.
강조: 자막·카드 글에서 *이렇게* 감싼 부분은 강조색으로 그린다.
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile

VERSION = "0.2.0"
W, H, FPS = 1080, 1920, 30

# 자막 안전 영역(1080x1920). Meta 릴스 광고 가이드 위 14%·아래 35%·좌우 6% [공식]
# + 쇼츠·틱톡 오른쪽 버튼 열 190px [실무 → 추정]. 근거: 06-크로스포스팅-규격 3-2.
SAFE_L, SAFE_R, SAFE_T, SAFE_B = 65, 890, 270, 1250
SAFE_W = SAFE_R - SAFE_L
SAFE_CX = (SAFE_L + SAFE_R) // 2

# 정보형 짜임: 위 띠(고정 제목) / 가운데 띠(사진·캡처) / 아래 띠(앱 버튼·설명 자리)
INFO_MEDIA_Y, INFO_MEDIA_H = 520, 980

XFADE = 0.3  # 장면 전환 길이(초)
TRANSITIONS = ["slideleft", "slideup", "zoomin", "smoothleft", "fadeblack", "slideright"]

# 미리 정한 색 조합. 장면표의 "theme" 로 고르거나 "colors" 로 덮어쓴다.
THEMES = {
    # IT·정보형: 검정 바탕, 노랑 강조(정보 숏폼에서 가장 흔하고 잘 읽히는 조합)
    "info": {"bg": "#000000", "fg": "#FFFFFF", "accent": "#FFD400",
             "cards": [["#FFD400", "#111111", "#E8340C"], ["#111111", "#FFFFFF", "#FFD400"],
                       ["#FFFFFF", "#111111", "#2F6BFF"]],
             "box": "black@0.78"},
    # 따뜻한 가게: 크림·갈색·버터 노랑
    "warm": {"bg": "#2A1C14", "fg": "#FFFFFF", "accent": "#FFC94A",
             "cards": [["#F6E7D2", "#3A2416", "#D9682B"], ["#C8662F", "#FFF6E8", "#FFE08A"],
                       ["#3A2416", "#FFF6E8", "#FFC94A"]],
             "box": "#2A1C14@0.82"},
}

FONT_CANDIDATES = [
    # Pretendard 우선
    "~/Library/Fonts/Pretendard-Bold.otf",
    "/Library/Fonts/Pretendard-Bold.otf",
    "/usr/share/fonts/opentype/pretendard/Pretendard-Bold.otf",
    "/usr/share/fonts/truetype/pretendard/Pretendard-Bold.ttf",
    "~/.local/share/fonts/Pretendard-Bold.otf",
    "C:/Windows/Fonts/Pretendard-Bold.otf",
    "~/AppData/Local/Microsoft/Windows/Fonts/Pretendard-Bold.otf",
    "~/Library/Fonts/PretendardVariable.ttf",
    # 대체 한글 글꼴
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "C:/Windows/Fonts/malgunbd.ttf",
]

PRETENDARD_HELP = (
    "Pretendard 글꼴을 찾지 못했어요. https://github.com/orioncactus/pretendard/releases 에서 받아\n"
    "Pretendard-Bold.otf 를 설치하거나, 장면표에 \"font\": \"글꼴 파일 경로\" 를 적어 주세요."
)

try:  # 있으면 글자 폭을 정확히 잰다
    from PIL import ImageFont  # type: ignore
except Exception:  # noqa: BLE001
    ImageFont = None
_FONT_CACHE = {}


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def need_ffmpeg():
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return
    sysname = platform.system()
    how = {
        "Darwin": "맥: 터미널에서 brew install ffmpeg",
        "Windows": "윈도우: winget install Gyan.FFmpeg (설치 후 새 터미널)",
    }.get(sysname, "리눅스: sudo apt install ffmpeg")
    die(
        "ffmpeg가 없어서 영상을 조립할 수 없어요.\n"
        f"- 설치: {how}\n"
        "- 설치가 어려우면: 장면표·자막·대본을 사장님께 드리고 캡컷 등 무료 앱으로 조립하는 방법\n"
        "  (guides/make/shortform.md 의 '대체 경로')으로 진행하세요.",
        2,
    )


def find_font(user_font=None):
    if user_font:
        p = os.path.expanduser(user_font)
        if os.path.exists(p):
            return p
        print(f"[주의] 지정한 글꼴이 없어요: {user_font}", file=sys.stderr)
    for c in FONT_CANDIDATES:
        p = os.path.expanduser(c)
        if os.path.exists(p):
            if "Pretendard" not in p:
                print("[주의] " + PRETENDARD_HELP + f"\n지금은 {p} 로 대신 그려요.", file=sys.stderr)
            return p
    die(PRETENDARD_HELP)


def heavy_font(font):
    """제목·카드용 더 두꺼운 글꼴(같은 폴더에 있으면)."""
    for w in ("ExtraBold", "Black"):
        p = font.replace("-Bold.", f"-{w}.")
        if p != font and os.path.exists(p):
            return p
    return font


def esc(s):
    """ffmpeg 필터 인자 값 이스케이프(경로·색 등)."""
    s = s.replace("\\", "/")
    return s.replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")


def text_units(s):
    """화면 폭 계산용 글자 너비(글자 크기 대비). Pretendard Bold 실측: 한글 0.86, 숫자 0.62, 영문 0.5, 공백 0.23."""
    return sum(0.23 if ch == " " else 0.86 if ord(ch) > 0x2E80 else 0.62 if ch.isdigit() or ch.isupper()
               else 0.29 if ch in ":.,'!·" else 0.5 for ch in s)


def measure(s, size, font):
    """글자 폭(px). Pillow가 있으면 실제 글꼴로 재고, 없으면 근사."""
    if ImageFont is not None and font:
        key = (font, size)
        try:
            f = _FONT_CACHE.get(key) or ImageFont.truetype(font, size)
            _FONT_CACHE[key] = f
            return f.getlength(s)
        except Exception:  # noqa: BLE001
            pass
    return text_units(s) * size


def strip_marks(s):
    return str(s).replace("*", "")


def segments(line, base, accent):
    """'*강조*' 표시를 (글, 색) 조각으로."""
    out, on = [], False
    for i, part in enumerate(line.split("*")):
        if part:
            out.append((part, accent if on else base))
        if i < len(line.split("*")) - 1:
            on = not on
    return out


def wrap(text, size, width=SAFE_W - 40, font=None):
    """줄 수는 그대로 두고 줄 길이를 고르게(마지막 줄에 한두 글자만 남지 않게) 줄바꿈."""
    best = _wrap(text, size, width, font)
    w = width
    while w > size * 3:
        w -= size // 2
        cand = _wrap(text, size, w, font)
        if len(cand) != len(best) or not _whole_words(text, cand):
            break
        best = cand
    return best


def _whole_words(text, lines):
    """낱말 중간에서 끊지 않았는지."""
    words = strip_marks(text).split()
    return sorted(strip_marks(" ".join(lines)).split()) == sorted(words)


def _wrap(text, size, width, font=None):
    """폭에 맞춰 줄바꿈. 사용자가 넣은 \\n 은 그대로 둔다. 강조 표시(*)는 줄마다 짝을 맞춘다."""
    lines = []
    for para in str(text).split("\n"):
        words, cur = [], ""
        for tok in para.split(" "):
            # '·', '/', '-' 같은 구분 기호만 있는 낱말은 앞 낱말에 붙여 줄 머리에 오지 않게 한다
            if words and tok and all(c in "·•/-–—|:" for c in tok):
                words[-1] = words[-1] + " " + tok
            else:
                words.append(tok)
        for w in words:
            cand = (cur + " " + w).strip()
            if measure(strip_marks(cand), size, font) <= width or not cur:
                cur = cand
            else:
                lines.append(cur)
                cur = w
            while measure(strip_marks(cur), size, font) > width:  # 띄어쓰기 없는 긴 낱말은 강제로 자른다
                cut = 1
                while measure(strip_marks(cur[: cut + 1]), size, font) <= width:
                    cut += 1
                lines.append(cur[:cut])
                cur = cur[cut:]
        lines.append(cur)
    lines = [ln for ln in lines if strip_marks(ln).strip()]
    # 강조가 줄을 넘어가면 줄마다 닫고 다시 연다
    fixed, open_ = [], False
    for ln in lines:
        if open_:
            ln = "*" + ln
        if ln.count("*") % 2:
            ln += "*"
            open_ = True
        else:
            open_ = False
        fixed.append(ln)
    return fixed


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        die(f"장면표를 읽지 못했어요: {e}")
    base = os.path.dirname(os.path.abspath(path))
    scenes = data.get("scenes") or die("장면표에 scenes 가 비어 있어요.")
    for i, s in enumerate(scenes, 1):
        for k in ("photo", "clip"):
            if s.get(k) and not os.path.isabs(s[k]):
                s[k] = os.path.join(base, s[k])
        if "duration" not in s:
            die(f"{i}번 장면에 duration(초)이 없어요.")
    m = data.get("music")
    if isinstance(m, str):
        data["music"] = m = {"path": m}
    if m and not os.path.isabs(m["path"]):
        m["path"] = os.path.join(base, m["path"])
    return data


def theme_of(data):
    t = dict(THEMES.get(data.get("theme", "info" if data.get("layout", "info") == "info" else "warm"),
                        THEMES["info"]))
    t.update(data.get("colors") or {})
    if data.get("highlight_color"):
        t["accent"] = data["highlight_color"]
    return t


DRAFT_MSG = "사진 없는 시험본 — 사장님 사진·영상을 넣어 다시 만들 것"


def has_media(data):
    """실제 사진·클립 장면이 하나라도 있는지."""
    return any(s.get("photo") or s.get("clip") for s in data["scenes"])


def draft_name(out):
    """사진 없는 시험본 파일명: 확장자 앞에 _draft."""
    base, ext = os.path.splitext(out)
    return out if base.endswith("_draft") else f"{base}_draft{ext or '.mp4'}"


def check(data, quiet=False):
    """문제 목록(심각, 내용)을 돌려준다."""
    probs = []
    total = sum(float(s["duration"]) for s in data["scenes"])
    if total > 180:
        probs.append(("오류", f"총 {total:.1f}초: 3분을 넘어 쇼츠·릴스·틱톡 기본 한도를 넘어요."))
    elif total > 90:
        probs.append(("주의", f"총 {total:.1f}초: 기본 상한 90초를 넘어요(페이스북 릴스 API 90초, 쇼츠 1분 초과 시 Content ID 차단 위험)."))
    for i, s in enumerate(data["scenes"], 1):
        for k in ("photo", "clip"):
            if s.get(k) and not os.path.exists(s[k]):
                probs.append(("오류", f"{i}번 장면 파일이 없어요: {s[k]}"))
        d = float(s["duration"])
        cap = strip_marks(s.get("caption", ""))
        if cap and len(cap.replace("\n", "").replace(" ", "")) / max(d, 0.1) > 7:
            probs.append(("주의", f"{i}번 장면 자막이 길어요({len(cap)}자/{d}초). 1초에 7자 이하로 줄이거나 장면을 늘리세요."))
        if cap and cap.count("\n") >= 2:
            probs.append(("주의", f"{i}번 장면 자막이 3줄이에요. 한 화면에 한 메시지, 2줄까지만."))
        if s.get("title") and text_units(strip_marks(s["title"])) > 24:
            probs.append(("주의", f"{i}번 장면 큰 제목이 길어요. 두 줄·줄마다 8~12자를 권해요."))
        if d < 1.0:
            probs.append(("주의", f"{i}번 장면이 1초보다 짧아요. 자막을 읽을 시간이 없어요."))
    # 사장님 자료로 채워야 할 빈칸([직접 입력: …])이 화면 글자에 남아 있으면 그대로 나가면 안 된다
    texts = [("고정 제목", data.get("fixed_title")), ("브랜드", data.get("brand"))]
    for i, s in enumerate(data["scenes"], 1):
        for k in ("hook", "title", "caption", "tag"):
            texts.append((f"{i}번 장면 {k}", s.get(k)))
    for where, v in texts:
        if isinstance(v, str) and "[직접 입력" in v:
            probs.append(("고칠 것", f"{where}에 빈칸이 남아 있어요: {v.strip()[:40]} → 사장님 자료로 채우거나 지우세요."))
    if not has_media(data):
        probs.append(("주의", DRAFT_MSG))
    hook = data["scenes"][0]
    if not (hook.get("title") or hook.get("caption") or hook.get("hook") or data.get("fixed_title")):
        probs.append(("주의", "1번 장면(0~3초)에 훅 문구가 없어요."))
    if int(data.get("caption_size", 66)) < 64:
        probs.append(("주의", "자막 크기가 64px보다 작아요. 폰에서 약해요."))
    m = data.get("music")
    if m and not os.path.exists(m["path"]):
        probs.append(("오류", f"배경음 파일이 없어요: {m['path']}"))
    if not quiet:
        print(f"장면 {len(data['scenes'])}개, 총 {total:.1f}초")
        for lvl, msg in probs:
            print(f"[{lvl}] {msg}")
        if not probs:
            print("문제 없음")
    return probs


_YALIGN = None


def ffmpeg_has_yalign():
    """ffmpeg drawtext 가 y_align(6.1+)을 지원하는지 한 번만 확인한다."""
    global _YALIGN
    if _YALIGN is None:
        try:
            r = subprocess.run(["ffmpeg", "-hide_banner", "-h", "filter=drawtext"],
                               capture_output=True, text=True)
            _YALIGN = "y_align" in (r.stdout + r.stderr)
        except Exception:  # noqa: BLE001
            _YALIGN = False
    return _YALIGN


class Draw:
    """drawtext 필터를 모으는 도우미. 글은 임시 파일로 넘겨 이스케이프 문제를 피한다."""

    def __init__(self, tmp):
        self.tmp, self.f = tmp, []

    def text(self, s, font, size, x, y, color, border=0, bcolor="black", shadow=False,
             alpha=None, box=None, enable=None, font_align=False):
        fd, tpath = tempfile.mkstemp(suffix=".txt", dir=self.tmp)
        with os.fdopen(fd, "w", encoding="utf-8") as tf:
            tf.write(s)
        p = [f"fontfile='{esc(font)}'", f"textfile='{esc(tpath)}'", f"fontsize={size}",
             f"fontcolor={color}", f"x='{x}'", f"y='{y}'"]
        if border:
            p += [f"borderw={border}", f"bordercolor={bcolor}"]
        if shadow:
            p += ["shadowx=0", "shadowy=6", "shadowcolor=black@0.45"]
        if box:
            p += ["box=1", f"boxcolor={box[0]}", f"boxborderw={box[1]}"]
        if font_align and ffmpeg_has_yalign():
            # 글자 하나씩 그릴 때 '·' 같은 작은 글자가 위로 뜨지 않게 폰트 기준선으로 맞춘다
            p.append("y_align=font")
        if alpha:
            p.append(f"alpha='{alpha}'")
        if enable:
            p.append(f"enable='{enable}'")
        self.f.append("drawtext=" + ":".join(p))

    def rect(self, x, y, w, h, color, enable=None):
        e = f":enable='{enable}'" if enable else ""
        self.f.append(f"drawbox=x={int(x)}:y={int(y)}:w={int(w)}:h={int(h)}:color={color}:t=fill{e}")


def rich_line(dr, line, font, size, cx, y, base, accent, border=0, shadow=False, enable=None):
    """한 줄을 가운데 정렬로, 강조 조각은 강조색으로 그린다. 그린 폭을 돌려준다."""
    segs = segments(line, base, accent)
    plain = "".join(t for t, _ in segs)
    total = measure(plain, size, font)
    x = cx - total / 2
    for t, col in segs:
        dr.text(t, font, size, int(round(x)), int(y), col, border=border, shadow=shadow, enable=enable)
        x += measure(t, size, font)
    return total


def caption_block(dr, text, font, size, bottom, th, style, cx=SAFE_CX, width=SAFE_W - 20):
    """아래 자막: 줄마다 상자(또는 외곽선). bottom = 마지막 줄 상자 아래 끝."""
    lines = wrap(text, size, width, font)
    pad_x, pad_y = int(size * 0.36), int(size * 0.2)
    lh = int(size * 1.18) + 2 * pad_y + 8
    y = bottom - lh * len(lines)
    for ln in lines:
        wpx = measure(strip_marks(ln), size, font)
        if style == "box":
            dr.rect(cx - wpx / 2 - pad_x, y, wpx + 2 * pad_x, size * 1.18 + 2 * pad_y, th["box"])
            rich_line(dr, ln, font, size, cx, y + pad_y + size * 0.06, th["fg"], th["accent"])
        else:
            rich_line(dr, ln, font, size, cx, y + pad_y, th["fg"], th["accent"],
                      border=max(6, size // 9), shadow=True)
        y += lh
    return bottom - lh * len(lines)


def kinetic_text(dr, text, font, size, cx, cy, fg, accent, start=0.15, per_char=0.045,
                 rise=36, line_gap=1.22):
    """글자 단위로 아래에서 올라오며 나타나는 큰 글자(카드용). cy = 글 묶음의 세로 가운데."""
    lines = wrap(text, size, W - 150, font)
    lh = int(size * line_gap)
    y0 = cy - lh * len(lines) / 2
    k = 0
    for li, ln in enumerate(lines):
        segs = segments(ln, fg, accent)
        plain = "".join(t for t, _ in segs)
        x = cx - measure(plain, size, font) / 2
        done = ""
        for t, col in segs:
            for ch in t:
                if ch != " ":
                    t0 = start + k * per_char + li * 0.12
                    a = f"if(lt(t,{t0:.3f}),0,min(1,(t-{t0:.3f})/0.12))"
                    yy = (f"{int(y0 + li * lh)}+{rise}*(1-min(1,max(0,(t-{t0:.3f})/0.18)))"
                          f"*(1-min(1,max(0,(t-{t0:.3f})/0.18)))")
                    xx = int(round(x + measure(done, size, font)))
                    dr.text(ch, font, size, xx, yy, col, alpha=a, font_align=True)
                    k += 1
                done += ch
            x += 0  # done 이 줄 처음부터 쌓이므로 x 는 그대로
    return y0, y0 + lh * len(lines)


def probe_size(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", path],
                           capture_output=True, text=True)
        w, h = r.stdout.strip().split(",")[:2]
        return int(w), int(h)
    except Exception:  # noqa: BLE001
        return None


def media_filter(s, d, box_w, box_h, idx):
    """사진·영상을 box_w x box_h 칸에 채운다. 비율이 많이 다르면(가로 캡처 등) 흐린 배경 + 통째로 보이기.
    입력 [0:v] → 출력 [m]."""
    frames = int(round(d * FPS))
    size = probe_size(s.get("clip") or s.get("photo")) or (box_w, box_h)
    ratio, box_ratio = size[0] / size[1], box_w / box_h
    # 사진은 칸을 꽉 채우고(가운데 기준 잘라냄), 화면 캡처 영상처럼 비율이 많이 다른 영상은 통째로 보이게
    fit = s.get("fit") or ("cover" if s.get("photo") or not (ratio > box_ratio * 1.25 or ratio < box_ratio / 1.6)
                           else "contain")
    zoom = s.get("zoom", ["in", "out"][idx % 2])
    zmax = 0.10 if s.get("photo") else 0.05
    if zoom == "none":
        z = "1"
    elif zoom == "out":
        z = f"{1 + zmax}-{zmax}*on/{frames}"
    else:
        z = f"1+{zmax}*on/{frames}"
    pre = f"fps={FPS},setsar=1," if s.get("clip") else ""
    zp = (f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={box_w}x{box_h}:fps={FPS}")
    if fit == "cover":
        return (f"[0:v]{pre}scale={box_w * 2}:{box_h * 2}:force_original_aspect_ratio=increase,"
                f"crop={box_w * 2}:{box_h * 2},{zp},setsar=1[m]")
    # contain: 흐린 배경 위에 통째로
    return (f"[0:v]{pre}split[a][b];"
            f"[a]scale={box_w // 4}:{box_h // 4}:force_original_aspect_ratio=increase,"
            f"crop={box_w // 4}:{box_h // 4},gblur=sigma=6,eq=brightness=-0.08:saturation=1.1,"
            f"scale={box_w}:{box_h},setsar=1[bg];"
            f"[b]scale={box_w * 2 - 40}:{box_h * 2 - 40}:force_original_aspect_ratio=decrease,"
            f"format=rgba,pad={box_w * 2}:{box_h * 2}:(ow-iw)/2:(oh-ih)/2:color=black@0,"
            f"{zp},format=rgba[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[m]")


def card_colors(data, th, s, idx):
    if s.get("bg"):
        return s["bg"], s.get("fg", th["fg"]), s.get("accent", th["accent"])
    if s.get("color") or s.get("gradient"):  # 예전 장면표 호환: 지정 색을 카드 바탕으로
        c = s.get("color") or s["gradient"][-1]
        return c, th["fg"], th["accent"]
    cards = th["cards"]
    return tuple(cards[idx % len(cards)])


def render_scene(i, s, data, fonts, tmp, guide, dur):
    """장면 하나 → mp4. 고정 제목은 여기서 그리지 않고 전체 합친 뒤에 얹는다(전환 때 흔들리지 않게)."""
    font, hfont = fonts
    th = theme_of(data)
    layout = data.get("layout", "info")
    cap_size = max(64, int(data.get("caption_size", 66)))
    style = data.get("caption_style", "box" if layout == "info" else "outline")
    has_media = bool(s.get("photo") or s.get("clip"))
    hook = (i == 1 and not has_media) or s.get("hook")
    dr = Draw(tmp)
    inputs, keep_audio = [], False
    if s.get("clip"):
        inputs = ["-ss", str(s.get("clip_start", 0)), "-t", f"{dur}", "-i", s["clip"]]
        keep_audio = bool(s.get("keep_audio"))
    elif s.get("photo"):
        inputs = ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur}", "-i", s["photo"]]

    full_card = hook or (layout == "full" and not has_media)
    if has_media:
        if layout == "info":
            mf = media_filter(s, dur, W, INFO_MEDIA_H, i)
            graph = (f"color=c={th['bg']}:s={W}x{H}:r={FPS}:d={dur}[base];{mf};"
                     f"[base][m]overlay=0:{INFO_MEDIA_Y}:shortest=1")
        else:
            mf = media_filter(s, dur, W, H, i)
            graph = mf.replace("[m]", "[mm]") + ";[mm]null"
    else:
        bg, fg, ac = card_colors(data, th, s, i - 1)
        if full_card:
            graph = f"color=c={bg}:s={W}x{H}:r={FPS}:d={dur}"
        else:
            graph = (f"color=c={th['bg']}:s={W}x{H}:r={FPS}:d={dur}[base];"
                     f"color=c={bg}:s={W}x{INFO_MEDIA_H}:r={FPS}:d={dur}[m];"
                     f"[base][m]overlay=0:{INFO_MEDIA_Y}")

    # 글자
    title = s.get("title")
    if not has_media:
        bg, fg, ac = card_colors(data, th, s, i - 1)
        main = s.get("hook") if isinstance(s.get("hook"), str) else (title or s.get("caption", ""))
        sub = s.get("caption") if (title or isinstance(s.get("hook"), str)) else None
        if full_card:
            size = int(s.get("size", 132 if hook else (190 if len(strip_marks(main)) <= 8 else 120)))
            cy = 840 if sub else 920
            # 위쪽 작은 꼬리표(브랜드·분류)
            if s.get("tag") or (hook and data.get("brand")):
                tag = s.get("tag") or data.get("brand")
                tw = measure(tag, 44, font)
                dr.rect(W / 2 - tw / 2 - 26, 330, tw + 52, 80, ac)
                dr.text(tag, font, 44, int(W / 2 - tw / 2), 344, bg)
            top, bot = kinetic_text(dr, main, hfont, size, W // 2, cy, fg, ac)
            if sub:
                dr.rect(W / 2 - 60, bot + 36, 120, 10, ac, enable="gte(t,0.5)")
                sl = wrap(sub, 80, W - 200, font)
                for n, ln in enumerate(sl):
                    rich_line(dr, ln, font, 80, W // 2, bot + 100 + n * 108, fg, ac,
                              enable="gte(t,0.6)")
        else:  # 정보형 가운데 띠 안의 카드
            size = int(s.get("size", 116))
            cy = INFO_MEDIA_Y + INFO_MEDIA_H * 0.42
            if title and s.get("caption"):
                tw = measure(strip_marks(title), 54, font)
                dr.rect(W / 2 - tw / 2 - 28, INFO_MEDIA_Y + 70, tw + 56, 88, fg)
                dr.text(strip_marks(title), font, 54, int(W / 2 - tw / 2), INFO_MEDIA_Y + 84, bg)
                main = s["caption"]
                sub = None
            kinetic_text(dr, main, hfont, size, W // 2, int(cy) + 40, fg, ac)
    else:
        if title:  # 장면 꼬리표(시간·항목 이름): 강조색 상자
            ts = 58
            tw = measure(strip_marks(title), ts, font)
            ty = INFO_MEDIA_Y + 40 if layout == "info" else SAFE_T + 230
            dr.rect(SAFE_CX - tw / 2 - 26, ty, tw + 52, ts * 1.5, th["accent"])
            dr.text(strip_marks(title), font, ts, int(SAFE_CX - tw / 2), int(ty + ts * 0.2), th.get("on_accent", "#111111"))
        if s.get("caption"):
            caption_block(dr, s["caption"], font, cap_size, SAFE_B - 10, th, style)
    if guide:
        dr.rect(SAFE_L, SAFE_T, SAFE_W, 4, "red@0.8")
        dr.rect(SAFE_L, SAFE_B, SAFE_W, 4, "red@0.8")
        dr.rect(SAFE_L, SAFE_T, 4, SAFE_B - SAFE_T, "red@0.8")
        dr.rect(SAFE_R, SAFE_T, 4, SAFE_B - SAFE_T, "red@0.8")
    chain = ",".join(dr.f + ["format=yuv420p"])
    graph = f"{graph},{chain}[v]" if chain else f"{graph}[v]"
    out = os.path.join(tmp, f"s{i:03d}.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if inputs:
        cmd += inputs
    else:
        cmd += ["-f", "lavfi", "-t", f"{dur}", "-i", f"color=c=black:s=16x16:r={FPS}"]
    if keep_audio:
        amap = ["-map", "0:a?"]
        cmd += ["-filter_complex", graph, "-map", "[v]"] + amap + ["-af", f"aresample=44100,apad,atrim=0:{dur}"]
    else:
        cmd += ["-f", "lavfi", "-t", f"{dur}", "-i", "anullsrc=r=44100:cl=stereo",
                "-filter_complex", graph, "-map", "[v]", "-map", "1:a"]
    cmd += ["-t", f"{dur}", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        die(f"{i}번 장면 조립 실패:\n{r.stderr[-2000:]}")
    return out


def title_hidden_spans(data):
    """고정 제목을 숨길 구간(초). 훅 장면과 위쪽 꼬리표(브랜드·분류)를 그리는 전체 카드에서는
    고정 제목 상자가 꼬리표를 가리므로 그 장면 동안 숨긴다. render_scene 과 같은 기준."""
    sc = data["scenes"]
    if len(sc) < 2:
        return []
    layout = data.get("layout", "info")
    spans, acc = [], 0.0
    for i, s in enumerate(sc, 1):
        d = float(s["duration"])
        has_media = bool(s.get("photo") or s.get("clip"))
        hook = (i == 1 and not has_media) or s.get("hook")
        full_card = hook or (layout == "full" and not has_media)
        tagged = full_card and not has_media and (s.get("tag") or (hook and data.get("brand")))
        if hook or tagged:
            if spans and abs(spans[-1][1] - acc) < 1e-6:
                spans[-1] = (spans[-1][0], acc + d)
            else:
                spans.append((acc, acc + d))
        acc += d
    return spans


def fixed_title_filters(data, fonts, tmp, hidden=()):
    """정보형: 위 띠 고정 제목 2줄(윗줄 흰색, 아랫줄 강조색). 훅·꼬리표 카드 동안은 숨긴다."""
    t = data.get("fixed_title")
    if not t:
        return []
    font, hfont = fonts
    th = theme_of(data)
    layout = data.get("layout", "info")
    size = int(data.get("title_size", 76))
    lines = wrap(t, size, SAFE_W - 20, hfont)  # 오른쪽 버튼 열을 피해 안전 영역 가운데에 맞춘다
    dr = Draw(tmp)
    en = None
    if hidden:
        en = "not(" + "+".join(f"between(t,{a:.2f},{b:.2f})" if a > 0 else f"lt(t,{b:.2f})"
                               for a, b in hidden) + ")"
    lh = int(size * 1.25) if layout == "info" else int(size * 1.2) + 6
    y = SAFE_T + 10
    if layout == "info":
        y = INFO_MEDIA_Y - 40 - lh * len(lines)
    for n, ln in enumerate(lines):
        base = th["accent"] if (n == len(lines) - 1 and len(lines) > 1 and "*" not in t) else th["fg"]
        if layout == "info":
            rich_line(dr, ln, hfont, size, SAFE_CX, y + n * lh, base, th["accent"], enable=en)
        else:  # 브이로그형: 줄마다 진한 상자(사진·카드 어디서나 읽힘)
            wpx = measure(strip_marks(ln), size, hfont)
            dr.rect(SAFE_CX - wpx / 2 - 24, y + n * lh - 10, wpx + 48, size * 1.2 + 6, th["box"], enable=en)
            rich_line(dr, ln, hfont, size, SAFE_CX, y + n * lh, base, th["accent"], enable=en)
    return dr.f


def build(path, out, guide=False, crf=26, draft_suffix=True):
    need_ffmpeg()
    data = load(path)
    probs = check(data)
    if any(lvl in ("오류", "고칠 것") for lvl, _ in probs):
        die("오류·고칠 것을 고친 뒤 다시 실행하세요.")
    draft = not has_media(data)
    if draft and draft_suffix:
        out = draft_name(out)
    font = find_font(data.get("font"))
    fonts = (font, heavy_font(font))
    tmp = tempfile.mkdtemp(prefix="shortform_")
    sc = data["scenes"]
    n = len(sc)
    T = XFADE if n > 1 else 0
    # 전환으로 겹치는 만큼 장면을 늘려서 총 길이는 장면표 합계와 같게
    parts = [render_scene(i, s, data, fonts, tmp, guide, float(s["duration"]) + (T if i < n else 0))
             for i, s in enumerate(sc, 1)]
    total = sum(float(s["duration"]) for s in sc)
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for p in parts:
        cmd += ["-i", p]
    fc, v, a, off = [], "[0:v]", "[0:a]", 0.0
    for k in range(1, n):
        off += float(sc[k - 1]["duration"])
        tr = sc[k].get("transition") or TRANSITIONS[(k - 1) % len(TRANSITIONS)]
        if tr == "cut":  # 바로 넘김(아주 짧은 디졸브)
            tr = "fade"
        fc.append(f"{v}[{k}:v]xfade=transition={tr}:duration={T}:offset={off:.3f}[v{k}]")
        fc.append(f"{a}[{k}:a]acrossfade=d={T}[a{k}]")
        v, a = f"[v{k}]", f"[a{k}]"
    tf = fixed_title_filters(data, fonts, tmp, title_hidden_spans(data))
    fc.append(f"{v}{','.join(tf + ['format=yuv420p'])}[vo]")
    m = data.get("music")
    if m:
        cmd += ["-stream_loop", "-1", "-i", m["path"]]
        vol = float(m.get("volume", 0.25))
        fade = max(0.0, total - 1.5)
        fc.append(f"[{n}:a]volume={vol},atrim=0:{total},afade=t=out:st={fade}:d=1.5[mu];"
                  f"{a}[mu]amix=inputs=2:duration=first:normalize=0[ao]")
    else:
        fc.append(f"{a}anull[ao]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[vo]", "-map", "[ao]", "-t", f"{total}",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    shutil.rmtree(tmp, ignore_errors=True)
    if r.returncode != 0:
        die(f"합치기 실패:\n{r.stderr[-2000:]}")
    size = os.path.getsize(out) / 1e6
    print(f"완성: {out} ({W}x{H}, {total:.1f}초, {size:.1f}MB)")
    if draft:
        print(f"[주의] {DRAFT_MSG}. 이 파일은 올리지 마세요.")
    print("다음: frames --scenes 로 장면마다 1장씩 뽑아 자막 위치·가독성을 눈으로 확인하세요.")


def scene_times(scenes_path):
    data = load(scenes_path)
    ts, acc = [], 0.0
    for s in data["scenes"]:
        d = float(s["duration"])
        ts.append(round(acc + min(d * 0.6, d - 0.3), 2))  # 글자가 다 나온 뒤, 전환 전
        acc += d
    return ts


def frames(video, at, outdir, sheet=None):
    need_ffmpeg()
    outdir = outdir or os.path.splitext(video)[0] + "_frames"
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for t in at:
        p = os.path.join(outdir, f"t{t:05.1f}.png".replace(" ", "0"))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", video,
                        "-frames:v", "1", "-vf", "scale=540:-1", p], check=False)
        paths.append(p)
        print(p)
    if sheet and paths:
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        for p in paths:
            cmd += ["-i", p]
        lbl = "".join(f"[{k}:v]" for k in range(len(paths)))
        cmd += ["-filter_complex", f"{lbl}hstack=inputs={len(paths)}" if len(paths) > 1 else "null", sheet]
        subprocess.run(cmd, check=False)
        print(sheet)


def main():
    ap = argparse.ArgumentParser(description="숏폼 장면표 → 1080x1920 mp4")
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="장면표 점검")
    c.add_argument("scenes")
    b = sub.add_parser("build", help="조립")
    b.add_argument("scenes")
    b.add_argument("-o", "--out", default="shortform.mp4")
    b.add_argument("--guide", action="store_true", help="안전 영역 선을 그린다(점검용, 올리지 말 것)")
    b.add_argument("--crf", type=int, default=26, help="화질(낮을수록 고화질·큰 파일, 기본 26)")
    b.add_argument("--no-draft-suffix", dest="draft_suffix", action="store_false",
                   help="사진·클립 없는 시험본에도 파일명 뒤 _draft 를 붙이지 않는다(기본: 붙임)")
    f = sub.add_parser("frames", help="점검용 프레임 뽑기")
    f.add_argument("video")
    f.add_argument("--at", default="1,4,8", help="초, 쉼표로 구분")
    f.add_argument("--scenes", default=None, help="장면표를 주면 장면마다 1장씩 뽑는다")
    f.add_argument("--sheet", default=None, help="뽑은 프레임을 가로로 이어 붙인 한 장 png")
    f.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.cmd == "check":
        probs = check(load(a.scenes))
        sys.exit(1 if any(lvl in ("오류", "고칠 것") for lvl, _ in probs) else 0)
    if a.cmd == "build":
        build(a.scenes, a.out, a.guide, a.crf, a.draft_suffix)
    if a.cmd == "frames":
        at = scene_times(a.scenes) if a.scenes else [float(x) for x in a.at.split(",")]
        frames(a.video, at, a.out, a.sheet)


if __name__ == "__main__":
    main()

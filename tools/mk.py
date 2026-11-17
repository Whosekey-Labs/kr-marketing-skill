#!/usr/bin/env python3
"""mk.py — AI 마케터가 '묻기 전에 스스로 조사'할 때 쓰는 도우미 (파이썬 기본 기능만 사용).

명령:
  check        동작 확인 (네이버 검색 1회)
  search-blog  네이버 블로그 검색 상위 글 (제목·블로그·날짜·주소, 사장님 글/손님 후기/체험단 추정)
  read-blog    블로그 글 하나 읽기 (본문·사진 수·소제목·지도 유무·글자 수·협찬 표기)
  blog-list    블로그 최근 글 목록 (RSS) — 게시 빈도
  place        네이버 플레이스 정보 (업종·주소·리뷰 수·별점·예약·빠진 정보·리뷰 키워드·최근 리뷰)
  rank         검색어별로 우리 가게가 블로그·플레이스 검색에서 몇 위인지 (주 1회 측정용)
  colors       이미지 대표 색 (Pillow 있으면 사용, 없으면 PNG 직접 처리 / 맥은 sips로 변환)
  contrast     두 색의 글자 대비 (WCAG 기준)
  count        글자 수 (공백 포함·제외), 문단 수, 사진 표시 수
  lint         금지·주의 표현 검사 (tools/rules.json 기준)

동작 원칙:
  - 사장님 가게 조사용 도구. 일반 브라우저 User-Agent 하나를 고정해서 쓴다 (바꿔 가며 속이지 않는다).
  - 같은 사이트는 1초 + 0~0.8초 랜덤 간격, 한 번 실행에 요청 20번까지 (접속 차단 방지).
  - 허용 목록(ALLOWED_HOSTS)에 있는 네이버 주소만 연다. 다른 주소는 에이전트 브라우저로 연다.
  - 하나가 실패해도 나머지는 계속한다. 출력은 짧은 텍스트, --json이면 JSON.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import html
import http.client
import json
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from email.utils import parsedate_to_datetime

VERSION = "0.1.0"
REPO = "https://github.com/Whosekey-Labs/kr-marketing-skill"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MAX_REQUESTS = 20         # 한 번 실행에서 보낼 수 있는 최대 요청 수 (재시도 포함)
MAX_BODY = 6_000_000      # 응답 크기 상한 (네이버 모바일 검색이 2MB 안팎)
SAME_HOST_GAP = 1.0       # 같은 사이트 요청 사이 기본 간격(초)
GAP_JITTER = 0.8          # 여기에 0~0.8초 랜덤을 더한다
HERE = os.path.dirname(os.path.abspath(__file__))

# 스크립트가 직접 여는 주소 (정확히 이 호스트만). 임의 주소를 열지 않으므로 내부망 접근이 불가능하다.
ALLOWED_HOSTS = ("search.naver.com", "m.search.naver.com", "blog.naver.com", "m.blog.naver.com",
                 "rss.blog.naver.com")

_last_hit: dict[str, float] = {}
_request_count = 0
_cache: dict[str, str] = {}


# ---------------------------------------------------------------- 공통 HTTP

def check_url(url: str) -> None:
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or (u.hostname or "").lower() not in ALLOWED_HOSTS or u.port not in (None, 443) \
            or u.username or u.password:
        raise RuntimeError("스크립트가 여는 주소가 아니에요 (네이버 검색·블로그만). 브라우저로 열어 주세요.")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(urllib.parse.urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirect)


def fetch(url: str) -> str:
    """같은 사이트는 간격을 두고, 실행당 요청 수를 제한해서 가져온다. 끊김·5xx는 한 번 더."""
    global _request_count
    if url in _cache:
        return _cache[url]
    check_url(url)
    host = urllib.parse.urlparse(url).hostname
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml",
                                               "Accept-Language": "ko-KR,ko;q=0.9"})
    for attempt in range(2):
        if _request_count >= MAX_REQUESTS:
            raise RuntimeError(f"한 번 실행에 요청은 {MAX_REQUESTS}번까지예요. 검색어를 줄여 나눠 실행해 주세요.")
        wait = SAME_HOST_GAP + random.uniform(0, GAP_JITTER) - (time.time() - _last_hit.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        _request_count += 1
        try:
            with _opener.open(req, timeout=20) as res:
                body = res.read(MAX_BODY).decode(res.headers.get_content_charset() or "utf-8", "replace")
            _cache[url] = body
            return body
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RuntimeError(f"{host}가 요청이 많다고 거절했어요(429). 10분쯤 뒤 다시 하거나 브라우저로 확인하세요.") from e
            if e.code < 500 or attempt:
                raise RuntimeError(f"{host} 응답 오류 {e.code}") from e
        except (http.client.IncompleteRead, TimeoutError, urllib.error.URLError, ConnectionError) as e:
            if attempt:
                raise RuntimeError(f"{host} 연결이 불안정해요: {e}") from e
        finally:
            _last_hit[host] = time.time()
        time.sleep(2 + random.uniform(0, 1))
    raise RuntimeError(f"{host} 연결 실패")


def strip_tags(s: str) -> str:
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h\d)>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    s = s.replace("​", "").replace("\xa0", " ")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def norm(s: str) -> str:
    """비교용: 공백·기호 없애고 소문자."""
    return re.sub(r"[\s\W_]+", "", (s or "").lower())


def out(data, as_json: bool, text: str) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=1) if as_json else text)


# ---------------------------------------------------------------- 네이버 블로그 검색

AD_RE = re.compile(r"체험단|협찬|제공\s*받|원고료|업체로부터|소정의|광고\s*포함|무상\s*제공|지원\s*받아")
# 손님도 '저희가 갔을 때'라고 쓰므로 '저희' 단독은 신호로 보지 않는다
OWNER_RE = re.compile(r"(?:저희|우리)\s*(?:가게|매장|카페|식당|빵집|공방|샵|숍|병원|의원|학원|업체)|"
                      r"(?:사장|대표|원장|실장)(?:입니다|이에요|예요)")      # 강한 신호
OWNER_WEAK_RE = re.compile(r"오픈\s*안내|영업\s*시간\s*안내|휴무\s*안내|예약\s*안내|공지|신메뉴\s*출시|이벤트\s*안내|정기\s*휴무")
GUEST_RE = re.compile(r"방문|다녀|후기|내돈내산|먹고\s*왔|재방문|웨이팅|맛집|추천|솔직|리뷰")


def guess_kind(title: str, snippet: str, blog_name: str = "", store: str = "") -> str:
    """제목·요약으로 글 성격 추정: 체험단 / 사장님 / 손님 후기 / 기타."""
    t = f"{title} {snippet}"
    if store and norm(store) and norm(store) in norm(blog_name):
        return "사장님 추정"
    if AD_RE.search(t):
        return "체험단·협찬 추정"
    if OWNER_RE.search(t):
        return "사장님 추정"
    if GUEST_RE.search(t):
        return "손님 후기 추정"
    if OWNER_WEAK_RE.search(t):
        return "사장님 추정"
    return "기타"


def parse_blog_search(page: str, store: str = "") -> list[dict]:
    """네이버 블로그 탭 검색 결과에서 글 목록 (2026-11 화면 구조 기준)."""
    items, seen = [], set()
    for seg in page.split('data-heatmap-target="articleSourceJSX_title"')[1:]:
        m = re.search(r'href="(https://(?:m\.)?blog\.naver\.com/([A-Za-z0-9_\-]+)/(\d{9,}))"[^>]*'
                      r'data-heatmap-target="\.nblg"><span[^>]*headline1[^>]*>(.*?)</span>', seg, re.S)
        if not m:
            continue
        url, blog_id, log_no, title = m.group(1), m.group(2), m.group(3), strip_tags(m.group(4))
        if (blog_id, log_no) in seen:
            continue
        seen.add((blog_id, log_no))
        name = re.search(r'<span class="sds-comps-text sds-comps-text-ellipsis sds-comps-text-ellipsis-1">(.*?)</span>', seg)
        date = re.search(r'profile-info-subtext">([^<]*)<', seg)
        snip = re.search(r'data-heatmap-target="\.nblg"><span class="sds-comps-text sds-comps-text-type-body1[^>]*>(.*?)</span>',
                         seg, re.S)
        bname = strip_tags(name.group(1)) if name else ""
        snippet = strip_tags(snip.group(1)) if snip else ""
        items.append(dict(rank=len(items) + 1, title=title, blog=bname, blog_id=blog_id, date=date.group(1).strip() if date else "",
                          url=f"https://blog.naver.com/{blog_id}/{log_no}", snippet=snippet[:160],
                          kind=guess_kind(title, snippet, bname, store)))
    if not items:     # 화면 구조가 바뀌었을 때: 주소만이라도
        for blog_id, log_no in dict.fromkeys(re.findall(r'blog\.naver\.com/([A-Za-z0-9_\-]+)/(\d{9,})', page)):
            items.append(dict(rank=len(items) + 1, title="", blog="", blog_id=blog_id, date="",
                              url=f"https://blog.naver.com/{blog_id}/{log_no}", snippet="", kind="확인 필요"))
    return items


def blog_search(keyword: str, store: str = "") -> list[dict]:
    page = fetch("https://search.naver.com/search.naver?ssc=tab.blog.all&sm=tab_jum&query=" + urllib.parse.quote(keyword))
    return parse_blog_search(page, store)


def cmd_search_blog(a):
    kw = a.keyword or a.kw
    if not kw:
        raise RuntimeError('검색어를 넣어 주세요. 예: search-blog -k "망원동 카페"')
    items = blog_search(kw, a.name or "")[: a.max]
    lines = [f"## 블로그 검색: {kw} (상위 {len(items)}개)"]
    for x in items:
        lines.append(f"{x['rank']}. [{x['kind']}] {x['title']} — {x['blog']} ({x['blog_id']}) · {x['date']}\n   {x['url']}")
    if items:
        c = collections.Counter(x["kind"] for x in items)
        lines.append("요약: " + ", ".join(f"{k} {v}" for k, v in c.most_common()) + " (제목·요약 기준 추정, 본문은 read-blog로 확인)")
    else:
        lines.append("결과를 못 읽었어요. 브라우저로 네이버 블로그 탭을 확인하세요.")
    out(dict(keyword=kw, items=items), a.json, "\n".join(lines))


# ---------------------------------------------------------------- 블로그 글 읽기

def blog_ids(url: str) -> tuple[str, str]:
    u = urllib.parse.urlparse(url.strip())
    q = urllib.parse.parse_qs(u.query)
    if q.get("blogId") and q.get("logNo"):
        return q["blogId"][0], q["logNo"][0]
    m = re.match(r"/([A-Za-z0-9_\-]+)/(\d{6,})", u.path)
    if m and (u.hostname or "") in ("blog.naver.com", "m.blog.naver.com"):
        return m.group(1), m.group(2)
    raise RuntimeError("네이버 블로그 글 주소가 아니에요 (예: https://blog.naver.com/아이디/글번호).")


def parse_post(page: str) -> dict:
    """스마트에디터(se-) 글 구조에서 본문·사진·소제목·지도 등을 뽑는다."""
    t = re.search(r'<meta property="og:title" content="([^"]*)"', page)
    title = html.unescape(t.group(1)) if t else ""
    d = re.search(r'class="(?:blog_date|se_publishDate[^"]*)"[^>]*>\s*(?:<span[^>]*>)?\s*([^<]+)<', page)
    i = page.find("se-main-container")
    main = page[i:] if i >= 0 else page
    end = re.search(r'class="(?:comment_area|post_footer|wrap_postdata|post-btn|blog_btnArea|area_sympathy)', main)
    main = main[: end.start()] if end else main
    kinds = collections.Counter(re.findall(r'class="se-component se-(\w+)', main))
    heads = []
    for blk in re.split(r'class="se-component ', main)[1:]:
        if blk.startswith(("se-quotation", "se-sectionTitle")):
            h = strip_tags(re.sub(r"<[^>]*$", "", blk[blk.find(">") + 1:])).replace("\n", " ").strip()
            if h:
                heads.append(h[:60])
    paras = [strip_tags(p) for p in re.findall(r'<p class="se-text-paragraph[^"]*"[^>]*>(.*?)</p>', main, re.S)]
    body = "\n".join(p for p in paras if p)
    photos = len(re.findall(r'class="se-image-resource', main)) or (kinds["image"] + kinds["imageStrip"])
    tags = sorted(set(re.findall(r"#([0-9A-Za-z가-힣_]{2,20})", body)))
    return dict(title=title, date=d.group(1).strip() if d else "", chars=len(body),
                chars_no_space=len(re.sub(r"\s", "", body)), paragraphs=len([p for p in paras if p]),
                photos=photos, videos=kinds["video"] + kinds["oembed"], stickers=kinds["sticker"],
                headings=heads, map=bool(kinds["placesMap"] or kinds["map"]), links=kinds["oglink"],
                sponsored=bool(AD_RE.search(body)), hashtags=tags[:20], body=body)


def cmd_read_blog(a):
    blog_id, log_no = blog_ids(a.url)
    try:
        page = fetch(f"https://m.blog.naver.com/{blog_id}/{log_no}")
    except RuntimeError as e:     # 모바일이 거절하면 PC 본문 주소로 한 번
        print(f"(모바일 주소 실패: {e} → PC 주소로 다시)", file=sys.stderr)
        page = fetch(f"https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}")
    p = parse_post(page)
    p["url"] = f"https://blog.naver.com/{blog_id}/{log_no}"
    if not p["body"]:
        raise RuntimeError("본문을 못 읽었어요 (비공개·삭제·옛 에디터 글일 수 있어요). 브라우저로 열어 주세요.")
    body = p["body"] if a.max_chars <= 0 else p["body"][: a.max_chars]
    text = (f"## {p['title']}\n{p['url']} · {p['date']}\n"
            f"글자 {p['chars']}자(공백 제외 {p['chars_no_space']}) · 문단 {p['paragraphs']} · 사진 {p['photos']} · "
            f"영상 {p['videos']} · 지도 {'있음' if p['map'] else '없음'} · 링크 {p['links']} · "
            f"협찬 표기 {'있음' if p['sponsored'] else '없음'}\n"
            f"소제목(인용구) {len(p['headings'])}개: " + " / ".join(p["headings"][:12]) + "\n"
            + (f"해시태그: {' '.join('#' + x for x in p['hashtags'])}\n" if p["hashtags"] else "")
            + f"--- 본문{' (앞부분)' if len(body) < len(p['body']) else ''}\n{body}")
    if a.json:
        p["body"] = body
    out(p, a.json, text)


# ---------------------------------------------------------------- 블로그 RSS

def parse_rss(xml: str, now: dt.datetime) -> dict:
    tt = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", xml, re.S)
    posts = []
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        ti = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        pd = re.search(r"<pubDate>(.*?)</pubDate>", it)
        lk = re.search(r"<guid>(.*?)</guid>", it) or re.search(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", it)
        cat = re.search(r"<category>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</category>", it)
        try:
            when = parsedate_to_datetime(pd.group(1).strip()) if pd else None
        except (TypeError, ValueError):
            when = None
        posts.append(dict(title=html.unescape(ti.group(1)).strip() if ti else "",
                          date=when.strftime("%Y-%m-%d") if when else "", _dt=when,
                          url=(lk.group(1).split("?")[0] if lk else ""),
                          category=html.unescape(cat.group(1)) if cat else ""))
    ds = sorted((p["_dt"] for p in posts if p["_dt"]), reverse=True)
    n30 = sum(1 for d in ds if now - d <= dt.timedelta(days=30))
    n90 = sum(1 for d in ds if now - d <= dt.timedelta(days=90))
    recent = [d for d in ds if now - d <= dt.timedelta(days=180)] or ds[:10]     # 오래된 고정 글이 간격을 흐리지 않게
    gaps = sorted((recent[i] - recent[i + 1]).total_seconds() / 86400 for i in range(len(recent) - 1))
    for p in posts:
        p.pop("_dt")
    return dict(blog=html.unescape(tt.group(1)).strip() if tt else "", total_in_rss=len(posts), last_30d=n30,
                last_90d=n90, median_gap_days=round(gaps[len(gaps) // 2], 1) if gaps else None,
                days_since_last=(now - ds[0]).days if ds else None, posts=posts)


def cmd_blog_list(a):
    bid = a.blog_id.strip()
    m = re.search(r"blog\.naver\.com/([A-Za-z0-9_\-]+)", bid)
    bid = m.group(1) if m else bid
    if not re.fullmatch(r"[A-Za-z0-9_\-]{2,40}", bid):
        raise RuntimeError("블로그 아이디 형식이 아니에요 (blog.naver.com/아이디 의 '아이디').")
    r = parse_rss(fetch(f"https://rss.blog.naver.com/{bid}.xml"), dt.datetime.now(dt.timezone.utc))
    r["blog_id"] = bid
    r["posts"] = r["posts"][: a.max]
    lines = [f"## {r['blog']} ({bid})",
             f"RSS 글 {r['total_in_rss']}개 · 최근 30일 {r['last_30d']}개 · 90일 {r['last_90d']}개 · "
             f"보통 간격 {r['median_gap_days']}일(최근 6개월 중앙값) · 마지막 글 {r['days_since_last']}일 전"]
    lines += [f"- {p['date']} [{p['category']}] {p['title']}" for p in r["posts"]]
    out(r, a.json, "\n".join(lines))


# ---------------------------------------------------------------- 네이버 플레이스 (모바일 통합검색)

def apollo_states(page: str) -> list[dict]:
    dec, res = json.JSONDecoder(), []
    for m in re.finditer(r"__APOLLO_STATE__\s*=\s*", page):
        try:
            res.append(dec.raw_decode(page, m.end())[0])
        except ValueError:
            continue
    return res


def _deref(o: dict, v):
    return o.get(v["__ref"], {}) if isinstance(v, dict) and "__ref" in v else v


def _num(v):
    if v in (None, ""):
        return None
    try:
        return int(str(v).replace(",", ""))
    except ValueError:
        return str(v)


def parse_place_detail(states: list[dict]) -> dict | None:
    """가게 이름으로 검색했을 때 나오는 단일 플레이스 정보."""
    for o in states:
        base = next((v for k, v in o.items() if k.startswith("PlaceDetailBase:") and v.get("name")), None)
        if not base:
            continue
        pd = next((v for k, v in o.get("ROOT_QUERY", {}).items() if k.startswith("placeDetail")), {})
        stats = next((v for k, v in o.items() if k.startswith("VisitorReviewStatsResult")), {})
        reviews = sorted((v for k, v in o.items() if k.startswith("VisitorReview:")),
                         key=lambda r: r.get("visitedDate") or "", reverse=True)
        missing = base.get("missingInfo") or {}
        booking = pd.get("naverBooking") or {}
        hp = pd.get("homepages") or {}
        links = [x for x in [hp.get("repr")] + list(hp.get("etc") or []) if x]
        an = (stats.get("analysis") or {})
        vk = (an.get("votedKeyword") or {}).get("details") or []
        hours = []
        for nb in pd.get("newBusinessHours") or []:
            for h in nb.get("businessHours") or []:
                bh = h.get("businessHours") or {}
                hours.append(f"{h.get('day')} {bh.get('start')}~{bh.get('end')}" if bh.get("start") else f"{h.get('day')} 휴무·미등록")
        score = base.get("visitorReviewsScore") if (base.get("reviewSettings") or {}).get("showVisitorReviewScore") else None
        replied = sum(1 for r in reviews if (r.get("reply") or {}).get("body"))
        return dict(
            id=base.get("id"), name=base.get("name"), category=base.get("category"),
            road_address=base.get("roadAddress"), address=base.get("address"),
            phone=base.get("phone") or base.get("virtualPhone"),
            visitor_reviews=base.get("visitorReviewsTotal"), blog_cafe_reviews=base.get("cafeBlogReviewsTotal"),
            text_reviews=base.get("visitorReviewsTextReviewTotal"), rating=score,
            booking=bool(booking.get("naverBookingUrl") or booking.get("bookingBusinessId")),
            talktalk=bool(base.get("talktalkUrl")), conveniences=base.get("conveniences") or [],
            payment=base.get("paymentInfo") or [], micro_review=(base.get("microReviews") or [None])[0],
            description=bool(pd.get("description")), hours=hours,
            missing=[lab for key, lab in (("isBizHourMissing", "영업시간"), ("isDescriptionMissing", "소개글"),
                                         ("isMenuImageMissing", "메뉴 사진"), ("isConveniencesMissing", "편의시설"))
                     if missing.get(key) and not (key == "isBizHourMissing" and hours)       # 시간이 보이면 빠진 게 아님
                     and not (key == "isDescriptionMissing" and pd.get("description"))],
            links=[f"{x.get('type') or '링크'}:{x.get('url')}" for x in links],
            photos=(pd.get("topPhotos") or {}).get("total"),
            broadcasts=[f"{b.get('channel')} {b.get('program')}" for b in pd.get("broadcastInfos") or []],
            keywords=[f"{x.get('displayName')} {x.get('count')}" for x in vk[:8]],
            menus_in_reviews=[f"{x.get('label')} {x.get('count')}" for x in (an.get("menus") or [])[:8]],
            recent_reviews=[dict(date=r.get("visitedDate") or r.get("created"), rating=r.get("rating"),
                                 type=r.get("originType"), body=" ".join((r.get("body") or "").split())[:200]) for r in reviews[:10]],
            owner_reply=f"{replied}/{len(reviews)}" if reviews else None,
            url=f"https://m.place.naver.com/place/{base.get('id')}/home")
    return None


def parse_place_list(states: list[dict]) -> list[dict]:
    """지역·업종으로 검색했을 때의 플레이스 목록 (광고 제외, 화면 순서)."""
    for o in states:
        for k, v in o.get("ROOT_QUERY", {}).items():
            if not k.startswith("placeList"):
                continue
            biz = (v or {}).get("businesses") or {}
            items = []
            for ref in biz.get("items") or []:
                x = _deref(o, ref)
                if not x.get("name"):
                    continue
                items.append(dict(rank=len(items) + 1, id=x.get("id"), name=x.get("name"), category=x.get("category"),
                                  address=x.get("commonAddress") or x.get("address"),
                                  visitor_reviews=_num(x.get("visitorReviewCount")),
                                  blog_cafe_reviews=_num(x.get("blogCafeReviewCount")),
                                  rating=x.get("visitorReviewScore"), booking=bool(x.get("hasBooking")),
                                  talktalk=bool(x.get("talktalkUrl")), saves=x.get("saveCount")))
            if items:
                return items
    return []


def place_ads(states: list[dict]) -> list[str]:
    return [v.get("name") for o in states for k, v in o.items() if "AdSummary" in k and v.get("name")]


def place_search(query: str) -> tuple[dict | None, list[dict], list[str]]:
    page = fetch("https://m.search.naver.com/search.naver?query=" + urllib.parse.quote(query))
    st = apollo_states(page)
    return parse_place_detail(st), parse_place_list(st), place_ads(st)


def fmt_detail(d: dict) -> str:
    yn = lambda b: "있음" if b else "없음"
    s = [f"## {d['name']} ({d['category']}) — 플레이스 ID {d['id']}",
         f"주소: {d['road_address'] or d['address']} · 전화: {d['phone'] or '-'}",
         f"방문자 리뷰 {d['visitor_reviews']} (글 리뷰 {d['text_reviews']}) · 블로그·카페 리뷰 {d['blog_cafe_reviews']} · "
         f"별점 {d['rating'] if d['rating'] is not None else '비공개'} · 사진 {d['photos']}",
         f"네이버 예약 {yn(d['booking'])} · 톡톡 {yn(d['talktalk'])} · 소개글 {yn(d['description'])} · "
         f"최근 리뷰 사장님 답글 {d['owner_reply'] or '-'}"]
    if d["missing"]:
        s.append("네이버가 '비어 있음'으로 표시한 정보: " + ", ".join(d["missing"]) + " (사장님이 스마트플레이스에서 채울 것)")
    if d["hours"]:
        s.append("영업시간: " + ", ".join(d["hours"][:7]))
    if d["conveniences"]:
        s.append("편의: " + ", ".join(d["conveniences"]))
    if d["links"]:
        s.append("등록 링크: " + " ; ".join(d["links"]))
    if d["broadcasts"]:
        s.append("방송: " + ", ".join(d["broadcasts"]))
    if d["keywords"]:
        s.append("리뷰 키워드: " + ", ".join(d["keywords"]))
    if d["menus_in_reviews"]:
        s.append("리뷰에 많이 나온 메뉴: " + ", ".join(d["menus_in_reviews"]))
    if d["micro_review"]:
        s.append(f"한 줄 요약(네이버): {d['micro_review']}")
    for r in d["recent_reviews"][:5]:
        s.append(f"- 리뷰 {r['date']} ({r['type']}): {r['body'][:120]}")
    s.append(d["url"])
    return "\n".join(s)


def fmt_list(items: list[dict]) -> str:
    return "\n".join(f"{x['rank']}. {x['name']}{' (' + x['category'] + ')' if x['category'] else ''} {x['address']} · 방문자 {x['visitor_reviews']} · "
                     f"블로그 {x['blog_cafe_reviews']} · 예약 {'Y' if x['booking'] else 'N'} · ID {x['id']}" for x in items)


def cmd_place(a):
    q = a.name or a.q
    if not q:
        raise RuntimeError('상호와 지역을 넣어 주세요. 예: place -n "후후베이크 성수"')
    detail, items, ads = place_search(q)
    if detail:
        out(dict(query=q, place=detail), a.json, fmt_detail(detail))
    elif items:
        out(dict(query=q, place=None, list=items, ads=ads), a.json,
            f"## '{q}' — 가게 하나로 특정되지 않아 목록을 보여 드려요 (상호+동네로 다시 검색하면 자세히 나와요)\n" + fmt_list(items))
    else:
        raise RuntimeError("플레이스 정보를 못 찾았어요. 상호·지역을 바꿔 보거나 네이버 지도에서 직접 확인하세요."
                           + similar_places(q))


def _region(addr: str | None) -> str:
    """주소에서 시·구·동 앞부분만 (예: '서울 성동구 성수동2가')."""
    return " ".join((addr or "").split()[:3]) or "지역 모름"


def similar_places(q: str) -> str:
    """못 찾았을 때 지역을 빼고 상호만으로 다시 찾아 비슷한 이름 결과를 한 줄로 (다른 지역 포함)."""
    words = q.split()
    if len(words) < 2:
        return ""
    try:
        detail, items, _ = place_search(" ".join(words[:-1]))
    except RuntimeError:
        return ""
    found = items or ([dict(name=detail["name"], address=detail.get("road_address") or detail.get("address"))] if detail else [])
    if not found:
        return ""
    top = ", ".join(f"{x['name']}({_region(x.get('address'))})" for x in found[:3])
    return f"\n비슷한 이름 결과 {len(found)}건(다른 지역 포함): {top} — 이 중에 사장님 가게가 있으면 그 이름·동네로 다시 찾으세요."


# ---------------------------------------------------------------- 순위

def find_rank(names: list[str], store: str) -> list[int]:
    s = norm(store)
    return [i + 1 for i, n in enumerate(names) if s and (s in norm(n) or (norm(n) and norm(n) in s and len(norm(n)) >= 2))]


def cmd_rank(a):
    kws = [k.strip() for k in (a.keyword or a.kw or "").split(",") if k.strip()]
    store = a.name
    if not kws or not store:
        raise RuntimeError('예: rank -k "망원동 카페,망원 디저트" -n "가게이름"')
    rows, lines = [], [f"## 순위 측정: {store} ({dt.date.today()})"]
    for kw in kws:
        row = dict(date=str(dt.date.today()), keyword=kw, store=store)
        try:
            items = blog_search(kw, store)
            hits = [x["rank"] for x in items if norm(store) in norm(x["title"] + x["blog"])]
            own = [x["rank"] for x in items if a.blog_id and x["blog_id"] == a.blog_id]
            row.update(blog_rank=hits[0] if hits else None, blog_mentions=len(hits), blog_total=len(items),
                       own_blog_rank=own[0] if own else None)
        except RuntimeError as e:
            row["blog_error"] = str(e)
        try:
            detail, items, ads = place_search(kw)
            names = [x["name"] for x in items]
            r = find_rank(names, store)
            row.update(place_rank=r[0] if r else None, place_shown=len(items),
                       place_ad=bool(find_rank(ads, store)), place_top=names[:5])
        except RuntimeError as e:
            row["place_error"] = str(e)
        rows.append(row)
        b = (row.get("blog_error") or (f"상호가 들어간 글 최고 {row['blog_rank']}위 (상위 {row['blog_total']}개 중 {row['blog_mentions']}건)"
                                       if row.get("blog_rank") else f"상위 {row.get('blog_total')}개 안에 없음"))
        if a.blog_id and "blog_error" not in row:
            b += f" · 우리 블로그 {row['own_blog_rank'] or '없음'}"
        p = (row.get("place_error") or (f"{row['place_rank']}위" if row.get("place_rank")
                                        else f"검색 화면 상위 {row.get('place_shown')}곳 안에 없음")
             + (" (광고 노출 있음)" if row.get("place_ad") else ""))
        lines.append(f"- {kw}\n  블로그: {b}\n  플레이스: {p}" + (f"\n  플레이스 상위: {', '.join(row['place_top'])}"
                                                            if row.get("place_top") else ""))
    lines.append("참고: 플레이스 순위는 모바일 통합검색에 처음 보이는 목록 기준이에요(보통 5곳). 위치·시간에 따라 달라져요.")
    if a.log:
        new = not os.path.exists(a.log)
        with open(a.log, "a", encoding="utf-8") as f:
            if new:
                f.write("date,keyword,store,blog_rank,place_rank,place_ad\n")
            for r in rows:
                f.write(",".join(str(r.get(k) if r.get(k) is not None else "") .replace(",", " ")
                                 for k in ("date", "keyword", "store", "blog_rank", "place_rank", "place_ad")) + "\n")
        lines.append(f"기록 추가: {a.log}")
    out(rows, a.json, "\n".join(lines))


# ---------------------------------------------------------------- 색

def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise RuntimeError(f"색 코드 형식이 아니에요: {h} (예: #1A2B3C)")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(c) -> str:
    return "#%02X%02X%02X" % tuple(int(x) for x in c[:3])


def luminance(c) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


def contrast_verdict(r: float) -> str:
    if r >= 7:
        return "아주 좋음 (작은 글씨도 OK)"
    if r >= 4.5:
        return "좋음 (본문 글씨 OK)"
    if r >= 3:
        return "큰 글씨·제목만 OK (본문엔 부족)"
    return "부족 (글씨가 잘 안 읽혀요)"


def cmd_contrast(a):
    c1, c2 = hex_to_rgb(a.color1), hex_to_rgb(a.color2)
    r = contrast_ratio(c1, c2)
    out(dict(color1=rgb_to_hex(c1), color2=rgb_to_hex(c2), ratio=r, verdict=contrast_verdict(r)), a.json,
        f"{rgb_to_hex(c1)} vs {rgb_to_hex(c2)} → 대비 {r}:1 — {contrast_verdict(r)}")


def read_png(path: str) -> tuple[int, int, list]:
    """8비트·비인터레이스 PNG를 표준 라이브러리로 읽어 (너비, 높이, RGB 픽셀 목록)을 돌려준다."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("PNG가 아니에요")
    pos, idat, pal = 8, b"", None
    w = h = depth = ctype = inter = 0
    while pos < len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", chunk)
        elif typ == b"PLTE":
            pal = [tuple(chunk[i:i + 3]) for i in range(0, len(chunk), 3)]
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
        pos += 12 + ln
    if depth != 8 or inter:
        raise ValueError("8비트·일반 PNG만 직접 읽을 수 있어요")
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw, stride, prev, px = zlib.decompress(idat), w * bpp, bytearray(w * bpp), []
    step = max(1, max(w, h) // 200)       # 큰 그림은 200칸 정도로 건너뛰며 본다
    i = 0
    for y in range(h):
        ft, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a_ = line[x - bpp] if x >= bpp else 0
            b_, c_ = prev[x], (prev[x - bpp] if x >= bpp else 0)
            if ft == 1:
                line[x] = (line[x] + a_) & 255
            elif ft == 2:
                line[x] = (line[x] + b_) & 255
            elif ft == 3:
                line[x] = (line[x] + (a_ + b_) // 2) & 255
            elif ft == 4:
                p = a_ + b_ - c_
                pa, pb, pc = abs(p - a_), abs(p - b_), abs(p - c_)
                line[x] = (line[x] + (a_ if pa <= pb and pa <= pc else b_ if pb <= pc else c_)) & 255
        prev = line
        if y % step:
            continue
        for x in range(0, w, step):
            o = x * bpp
            if ctype == 2 or ctype == 6:
                if ctype == 6 and line[o + 3] < 128:
                    continue
                px.append(tuple(line[o:o + 3]))
            elif ctype == 3 and pal:
                px.append(pal[line[o]])
            else:
                if ctype == 4 and line[o + 1] < 128:
                    continue
                px.append((line[o],) * 3)
    return w, h, px


def dominant_colors(px: list, k: int) -> list[tuple]:
    """비슷한 색을 묶어 많이 쓰인 순으로 (색, 비율)."""
    if not px:
        return []
    buckets = collections.Counter((r >> 4, g >> 4, b >> 4) for r, g, b in px)
    sums: dict = collections.defaultdict(lambda: [0, 0, 0, 0])
    for r, g, b in px:
        s = sums[(r >> 4, g >> 4, b >> 4)]
        s[0] += r; s[1] += g; s[2] += b; s[3] += 1
    picked = []
    for key, n in buckets.most_common():
        s = sums[key]
        c = (s[0] / s[3], s[1] / s[3], s[2] / s[3])
        near = next((p for p in picked if sum((c[i] - p[0][i]) ** 2 for i in range(3)) < 40 ** 2), None)
        if near:
            near[1] += n
        else:
            picked.append([c, n])
    picked.sort(key=lambda p: -p[1])
    total = len(px)
    return [(tuple(round(v) for v in c), round(n / total * 100, 1)) for c, n in picked
            if n / total >= 0.01][:k]                     # 1% 미만 (테두리·잡티)은 뺀다


def load_pixels(path: str) -> tuple[list, str]:
    try:
        from PIL import Image  # type: ignore
        im = Image.open(path).convert("RGB")
        im.thumbnail((200, 200))
        return list(im.getdata()), "Pillow"
    except ImportError:
        pass
    try:
        return read_png(path)[2], "PNG 직접"
    except (ValueError, KeyError, OSError, zlib.error):
        pass
    if shutil.which("sips"):          # 맥: 기본 도구로 PNG 변환 후 읽기
        with tempfile.TemporaryDirectory() as d:
            tmp = os.path.join(d, "x.png")
            subprocess.run(["sips", "-s", "format", "png", "-Z", "200", path, "--out", tmp],
                           capture_output=True, timeout=60, check=False)
            if os.path.exists(tmp):
                return read_png(tmp)[2], "sips 변환"
    raise RuntimeError("이 그림은 읽을 수 없어요. `pip install Pillow` 후 다시 하거나, PNG로 저장해서 주시거나, "
                       "브라우저·눈으로 대표 색을 골라 #코드를 적어 주세요.")


def cmd_colors(a):
    if not os.path.isfile(a.image):
        raise RuntimeError(f"파일이 없어요: {a.image}")
    px, how = load_pixels(a.image)
    cols = dominant_colors(px, a.k)
    res = []
    for c, pct in cols:
        cw, cb = contrast_ratio(c, (255, 255, 255)), contrast_ratio(c, (0, 0, 0))
        res.append(dict(hex=rgb_to_hex(c), percent=pct, vs_white=cw, vs_black=cb,
                        text_on_it="흰 글씨" if cw >= cb else "검은 글씨"))
    lines = [f"## 대표 색 {len(res)}개 ({how}, 많이 쓰인 순)"]
    lines += [f"- {r['hex']} {r['percent']}% · 위에 쓸 글씨: {r['text_on_it']} (흰 {r['vs_white']}:1 / 검정 {r['vs_black']}:1)"
              for r in res]
    lines.append("배경·흰색 비중이 큰 색은 브랜드 색이 아닐 수 있어요. 로고·간판에서 눈에 띄는 색을 고르세요.")
    out(dict(image=a.image, method=how, colors=res), a.json, "\n".join(lines))


# ---------------------------------------------------------------- 글자 수

PHOTO_MARK = re.compile(r"\[\s*(?:사진|이미지|그림|photo|image|img)[^\]]*\]|!\[[^\]]*\]\([^)]*\)|<img\b|\(\s*사진[^)]*\)|📷",
                        re.I)


def count_text(t: str) -> dict:
    photos = len(PHOTO_MARK.findall(t))
    body = PHOTO_MARK.sub("", t)
    paras = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    lines_ = [l for l in body.splitlines() if l.strip()]
    return dict(chars=len(body.strip()), chars_no_space=len(re.sub(r"\s", "", body)), paragraphs=len(paras),
                lines=len(lines_), photo_marks=photos,
                headings=len([l for l in lines_ if re.match(r"\s*(#{1,6}\s|>\s|【|■|▶|\d+\.\s)", l)]))


def read_input(path: str | None) -> str:
    if not path or path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def cmd_count(a):
    c = count_text(read_input(a.input))
    out(c, a.json, f"글자 {c['chars']}자 (공백 제외 {c['chars_no_space']}자) · 문단 {c['paragraphs']} · 줄 {c['lines']} · "
                   f"사진 표시 {c['photo_marks']} · 소제목 줄 {c['headings']}")


# ---------------------------------------------------------------- 표현 검사

def load_rules(path: str) -> dict[str, list[dict]]:
    """rules.json을 {플래그: [규칙]}로 정리. 여러 모양을 받는다:
    {"flags": {"common": [...]}} / {"common": [...]} / {"rules": [{"flag": "common", ...}]} / [{"flag": ...}]
    규칙 하나: pattern|patterns|words|regex (글자 또는 목록), reason|why|message, fix|suggest|alternative, law|source|basis, level|severity"""
    with open(path, encoding="utf-8") as f:
        return load_rules_obj(json.load(f))


def load_rules_obj(data) -> dict[str, list[dict]]:
    groups: dict[str, list] = collections.defaultdict(list)
    if isinstance(data, dict) and isinstance(data.get("flags"), dict):
        data = data["flags"]
    if isinstance(data, dict) and isinstance(data.get("rules"), list):
        data = data["rules"]
    if isinstance(data, list):
        for r in data:
            if isinstance(r, dict):
                fls = r["flags"] if isinstance(r.get("flags"), list) else [r.get("flag", "common")]
                for fl in fls:
                    groups[fl].append(r)
    elif isinstance(data, dict):
        for fl, v in data.items():
            if fl.startswith(("_", "$")) or fl in ("version", "updated", "note", "notes"):
                continue
            rules = v.get("rules") if isinstance(v, dict) else v
            for r in rules or []:
                groups[fl].append(r if isinstance(r, dict) else {"pattern": r})
    return dict(groups)


def _rule_patterns(r: dict) -> list[tuple[str, bool]]:
    pats = []
    for key, is_re in (("regex", True), ("re", True), ("pattern", r.get("type") == "regex" or r.get("is_regex") is True),
                       ("patterns", r.get("type") == "regex" or r.get("is_regex") is True), ("words", False),
                       ("word", False), ("keywords", False)):
        v = r.get(key)
        if isinstance(v, str):
            pats.append((v, is_re))
        elif isinstance(v, list):
            pats += [(x, is_re) for x in v if isinstance(x, str)]
    return pats


def _ascii_alnum(c: str) -> bool:
    return c.isascii() and c.isalnum()


def _ascii_word_ok(line: str, start: int, end: int) -> bool:
    """영문으로 시작·끝나는 찾은 말은 영문 단어 경계에서만 인정한다.
    "ad-messaging"·"loaded" 안의 "ad"처럼 영문 단어(하이픈·밑줄로 이어진 것 포함)의 일부면 버린다. 한글은 그대로."""
    joined = lambda i, step: (0 <= i < len(line) and (_ascii_alnum(line[i]) or
                              (line[i] in "-_" and 0 <= i + step < len(line) and _ascii_alnum(line[i + step]))))
    if start < end and line[start].isascii() and line[start].isalpha() and joined(start - 1, -1):
        return False
    if start < end and line[end - 1].isascii() and line[end - 1].isalpha() and joined(end, 1):
        return False
    return True


def lint_text(text: str, rules: dict[str, list[dict]], flags: list[str]) -> list[dict]:
    hits = []
    lines = text.splitlines()
    for fl in flags:
        for r in rules.get(fl, []):
            for pat, is_re in _rule_patterns(r):
                try:
                    rx = re.compile(pat if is_re else re.escape(pat), re.I)
                except re.error:
                    continue
                for ln, line in enumerate(lines, 1):
                    for m in rx.finditer(line):
                        if not _ascii_word_ok(line, m.start(), m.end()):
                            continue
                        hits.append(dict(flag=fl, line=ln, found=m.group(0),
                                         context=line.strip()[max(0, m.start() - 20): m.end() + 20],
                                         level=r.get("level") or r.get("severity") or "",
                                         reason=r.get("reason") or r.get("why") or r.get("message") or "",
                                         fix=r.get("fix") or r.get("suggest") or r.get("alternative") or "",
                                         law=r.get("law") or r.get("source") or r.get("basis") or ""))
    uniq = {(h["flag"], h["line"], h["found"]): h for h in hits}
    return sorted(uniq.values(), key=lambda h: (h["line"], h["flag"]))


def cmd_lint(a):
    path = a.rules or os.path.join(HERE, "rules.json")
    if not os.path.exists(path):
        msg = (f"규칙 파일이 아직 없어요({path}) — 검사를 건너뜁니다. "
               "guides/compliance/ 의 검수표를 직접 읽고 눈으로 확인하세요.")
        out(dict(skipped=True, reason=msg), a.json, msg)
        return
    rules = load_rules(path)
    flags = [f.strip() for f in (a.flags or "common").split(",") if f.strip()]
    unknown = [f for f in flags if f not in rules]
    hits = lint_text(read_input(a.input), rules, flags)
    lines = []
    if unknown:
        lines.append(f"규칙에 없는 플래그(건너뜀): {', '.join(unknown)} · 있는 플래그: {', '.join(sorted(rules))}")
    if not hits:
        lines.append(f"걸린 표현 없음 (검사한 플래그: {', '.join(f for f in flags if f in rules)}). "
                     "규칙에 없는 과장·사실 확인은 따로 봐야 해요.")
    else:
        lines.append(f"걸린 표현 {len(hits)}개")
        lines.append("| 줄 | 플래그 | 표현 | 이유 | 고친 안 | 근거 |")
        lines.append("|---|---|---|---|---|---|")
        for h in hits:
            cell = lambda s: str(s).replace("|", "/").replace("\n", " ")
            lines.append(f"| {h['line']} | {h['flag']} | {cell(h['found'])} | {cell(h['reason'])} | {cell(h['fix'])} | {cell(h['law'])} |")
    out(dict(flags=flags, unknown_flags=unknown, hits=hits), a.json, "\n".join(lines))


# ---------------------------------------------------------------- 동작 확인

def cmd_check(a):
    t0 = time.time()
    items = blog_search("네이버 블로그")
    ok = len(items) > 0 and bool(items[0]["title"])
    pil = True
    try:
        import PIL  # type: ignore  # noqa: F401
    except ImportError:
        pil = False
    res = dict(ok=ok, version=VERSION, blog_results=len(items), seconds=round(time.time() - t0, 1),
               pillow=pil, sips=bool(shutil.which("sips")), rules=os.path.exists(os.path.join(HERE, "rules.json")))
    out(res, a.json,
        (f"OK — 스크립트 모드 사용 가능 (mk.py {VERSION}, 네이버 검색 {len(items)}건, {res['seconds']}초)" if ok else
         "네이버 검색 결과를 못 읽었어요 — 화면 구조가 바뀌었을 수 있어요. 브라우저 모드로 진행하고 제보해 주세요.")
        + f"\n이미지 색: {'Pillow' if pil else ('PNG 직접 + 맥 sips' if res['sips'] else 'PNG만')} · "
          f"표현 검사 규칙: {'있음' if res['rules'] else '없음(lint 건너뜀)'}")
    if not ok:
        sys.exit(1)


# ---------------------------------------------------------------- main

def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="AI 마케터 조사 도우미 (네이버 블로그·플레이스·순위·색·글자 수·표현 검사)")
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def p(name, fn, help_):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--json", action="store_true", help="JSON으로 출력")
        s.set_defaults(fn=fn)
        return s

    p("check", cmd_check, "동작 확인 (네이버 검색 1회)")

    s = p("search-blog", cmd_search_blog, "네이버 블로그 검색 상위 글")
    s.add_argument("kw", nargs="?", help="검색어")
    s.add_argument("--keyword", "-k", help="검색어")
    s.add_argument("--name", "-n", help="우리 상호 (블로그 이름에 있으면 사장님 블로그로 표시)")
    s.add_argument("--max", type=int, default=10)

    s = p("read-blog", cmd_read_blog, "블로그 글 하나 읽기")
    s.add_argument("url")
    s.add_argument("--max-chars", type=int, default=3000, help="본문 출력 길이 (0이면 전부)")

    s = p("blog-list", cmd_blog_list, "블로그 최근 글 목록·게시 빈도 (RSS)")
    s.add_argument("blog_id", help="블로그 아이디 또는 주소")
    s.add_argument("--max", type=int, default=20)

    s = p("place", cmd_place, "네이버 플레이스 정보")
    s.add_argument("q", nargs="?", help="상호 지역 (예: 후후베이크 성수)")
    s.add_argument("--name", "-n", help="상호 지역")

    s = p("rank", cmd_rank, "검색어별 블로그·플레이스 순위")
    s.add_argument("kw", nargs="?", help="검색어 (쉼표로 여러 개)")
    s.add_argument("--keyword", "-k", help="검색어 (쉼표로 여러 개)")
    s.add_argument("--name", "-n", required=True, help="우리 상호")
    s.add_argument("--blog-id", help="우리 블로그 아이디 (있으면 우리 블로그 순위도)")
    s.add_argument("--log", help="결과를 이 CSV에 한 줄씩 더하기 (주간 비교용)")

    s = p("colors", cmd_colors, "이미지 대표 색")
    s.add_argument("image")
    s.add_argument("-k", type=int, default=5, help="색 개수")

    s = p("contrast", cmd_contrast, "두 색의 글자 대비")
    s.add_argument("color1")
    s.add_argument("color2")

    s = p("count", cmd_count, "글자 수·문단·사진 표시 수")
    s.add_argument("--input", "-i", help="텍스트·마크다운 파일 (없으면 표준 입력)")

    s = p("lint", cmd_lint, "금지·주의 표현 검사 (tools/rules.json)")
    s.add_argument("--input", "-i", help="검사할 파일 (없으면 표준 입력)")
    s.add_argument("--flags", default="common", help="규제 플래그 쉼표로 (예: common,food-origin)")
    s.add_argument("--rules", help="규칙 파일 경로 (기본: mk.py 옆 rules.json)")

    a = ap.parse_args()
    try:
        a.fn(a)
    except Exception as e:
        print(f"오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

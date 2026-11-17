#!/usr/bin/env python3
"""mk.py — AI 마케터가 '묻기 전에 스스로 조사'할 때 쓰는 도우미 (파이썬 기본 기능만 사용).

명령:
  check        동작 확인 (키가 있으면 공식 검색 API 1회, 조사 경로 안내)
  search-blog  네이버 블로그 검색 상위 글 — 키 있으면 공식 검색 API(정확도순), 없으면 --unofficial일 때만 화면
  read-blog    블로그 글 하나 읽기 (본문·사진 수·소제목 …) — 공식 API가 없어 --unofficial일 때만
  blog-list    블로그 최근 글 목록 (RSS) — 게시 빈도
  place        네이버 플레이스 — 키 있으면 공식 지역 API(이름·업종·주소), --unofficial이면 리뷰 수·빠진 정보 등도
  rank         검색어별 우리 가게 블로그·플레이스 순위 — 키 있으면 공식 API 기준, 없으면 --unofficial일 때만
  colors       이미지 대표 색 (Pillow 있으면 사용, 없으면 PNG 직접 처리 / 맥은 sips로 변환)
  contrast     두 색의 글자 대비 (WCAG 기준)
  count        글자 수 (공백 포함·제외), 문단 수, 사진 표시 수
  lint         금지·주의 표현 검사 (tools/rules.json 기준)
  ideas        콘텐츠 발굴: 구글·유튜브 자동완성(동→시·구→업종 넓히기) + 키 있으면 지식iN·월간 검색수
               (--unofficial이면 네이버 자동완성·관련 검색어도)
  trend        검색어 추이 비교 (네이버 데이터랩 키가 있으면 데이터랩, 없으면 구글 트렌드)
  season       앞으로 N주 기념일·절기·시즌 (+--unofficial: 쇼핑인사이트 작년 같은 시기 2~6주 뒤 인기 검색어)
  festival     지역 축제 목록 (대한민국 구석구석)

네이버 약관 (근거: 내부 조사 10b 4장):
  - 네이버 이용약관은 양과 상관없이 '사전 허락 없는 자동화된 수단으로 특정 질의어 검색'을 금지하고,
    검색·자동완성·관련 검색어 주소의 robots.txt는 Disallow: / 이다.
  - 그래서 기본 경로는 공식 API다: 환경변수 NAVER_CLIENT_ID·NAVER_CLIENT_SECRET(네이버 개발자 — 검색 API
    블로그·지식iN·지역, 데이터랩 검색어트렌드), NAVER_AD_*(검색광고 키워드도구).
  - 네이버 검색 화면·블로그 본문을 직접 읽는 길은 --unofficial을 붙였을 때만 연다(위험을 안 사장님 가게 1곳 몫,
    사장님 PC에서, 주 1회). 여러 가게 몫을 서버에서 모아 부르는 데 쓰지 않는다.
  - 키도 --unofficial도 없으면: 사장님이 보낸 링크·화면 캡처로 본다. 에이전트 브라우저로 사장님이 준 특정 주소
    (플레이스·블로그 글)를 여는 것은 괜찮지만, 네이버에 검색어를 넣어 검색하는 것은 --unofficial과 같은 동의 단계를 거친다.

동작 원칙:
  - 사장님 가게 조사용 도구. 일반 브라우저 User-Agent 하나를 고정해서 쓴다 (바꿔 가며 속이지 않는다).
  - 같은 사이트는 1초 + 0~0.8초 랜덤 간격, 한 번 실행에 요청 20번까지 (접속 차단을 줄이는 기준이지 약관상 허용 기준이 아님).
  - 허용 목록(ALLOWED_HOSTS)에 있는 주소만 연다. 다른 주소는 에이전트 브라우저로 연다.
  - 발굴 명령(ideas·trend·season·festival)은 소스 하나가 실패하면 그 소스만 건너뛴다.
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

VERSION = "0.2.0"
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
                 "rss.blog.naver.com",
                 # 콘텐츠 발굴(ideas·trend·season·festival) — 근거: 내부 조사 10 2장, 10b
                 "ac.search.naver.com", "s.search.naver.com", "kin.naver.com", "datalab.naver.com",
                 "trends.google.com", "suggestqueries.google.com", "korean.visitkorea.or.kr",
                 # 키가 있을 때만 (환경변수)
                 "openapi.naver.com", "api.searchad.naver.com")

# 네이버 검색 화면·블로그 본문·비공식 내부 주소 — --unofficial일 때만 연다 (10b 4-1·4-3)
NAVER_UNOFFICIAL_HOSTS = ("search.naver.com", "m.search.naver.com", "s.search.naver.com", "ac.search.naver.com",
                          "blog.naver.com", "m.blog.naver.com", "kin.naver.com", "datalab.naver.com")
UNOFFICIAL = {"on": False, "warned": False}
UNOFFICIAL_MSG = ("네이버 검색 화면을 자동으로 읽는 길이라 기본으로 꺼 두었어요(네이버 약관은 허락 없는 자동 검색을 금지). "
                  "① 네이버 개발자 키(NAVER_CLIENT_ID·NAVER_CLIENT_SECRET)를 넣으면 공식 API로 하고, "
                  "② 키가 없으면 사장님께 링크·화면 캡처를 받으세요(사장님이 준 특정 주소는 네 브라우저로 열어도 돼요. "
                  "네이버에 검색어를 넣어 검색하는 건 ③과 같은 동의가 필요해요). "
                  "③ 사장님께 위험을 알리고 동의받은 뒤 이 가게 1곳 몫만 할 때만 --unofficial을 붙이세요.")

UNOFFICIAL_RISK = ("네이버 검색 화면을 프로그램이나 에이전트가 대신 검색해 읽는 건 네이버 약관상 문제가 될 수 있어요. "
                   "열쇠(공식 키)를 받아 두면 이 걱정 없이 할 수 있어요.")


def naver_gate(host: str) -> None:
    """네이버 검색 화면·비공식 주소는 --unofficial일 때만 (리다이렉트로 넘어가는 경우도 포함)."""
    if (host or "").lower() not in NAVER_UNOFFICIAL_HOSTS:
        return
    if not UNOFFICIAL["on"]:
        raise RuntimeError(UNOFFICIAL_MSG)
    if not UNOFFICIAL["warned"]:
        UNOFFICIAL["warned"] = True
        print("주의(--unofficial): 네이버 약관상 허락 없는 자동 검색에 해당할 수 있어요. 이 가게 1곳 몫만, 주 1회만 쓰세요.",
              file=sys.stderr)

_last_hit: dict[str, float] = {}
_request_count = 0
_cache: dict[str, str] = {}


# ---------------------------------------------------------------- 공통 HTTP

def check_url(url: str) -> None:
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or (u.hostname or "").lower() not in ALLOWED_HOSTS or u.port not in (None, 443) \
            or u.username or u.password:
        raise RuntimeError("스크립트가 여는 주소가 아니에요 (허용 목록 밖). 브라우저로 열어 주세요.")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newurl = urllib.parse.urljoin(req.full_url, newurl)
        # 네이버 RSS는 별칭 아이디를 http 주소로 넘긴다 → 같은 허용 호스트면 https로 올려서 따라간다
        if newurl.startswith("http://") and (urllib.parse.urlparse(newurl).hostname or "").lower() in ALLOWED_HOSTS:
            newurl = "https://" + newurl[len("http://"):]
        try:
            check_url(newurl)
        except RuntimeError:
            raise RuntimeError(f"{urllib.parse.urlparse(req.full_url).hostname}가 다른 주소"
                               f"({urllib.parse.urlparse(newurl).hostname})로 넘겼어요 — 요청이 많아 막혔거나 확인 화면일 수 있어요. "
                               "나중에 다시 하거나 화면으로 확인하세요.") from None
        naver_gate(urllib.parse.urlparse(newurl).hostname)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# 쿠키는 이번 실행 동안만 메모리에 둔다 (구글 트렌드가 첫 방문 쿠키를 요구함). 파일로 남기지 않는다.
_opener = urllib.request.build_opener(_SafeRedirect, urllib.request.HTTPCookieProcessor())


def fetch(url: str, data: bytes | None = None, headers: dict | None = None) -> str:
    """같은 사이트는 간격을 두고, 실행당 요청 수를 제한해서 가져온다. 끊김·5xx는 한 번 더.
    data가 있으면 POST. headers는 기본 머리말에 덧붙인다(Referer·Content-Type 등)."""
    global _request_count
    key = url + ("\x00" + data.decode("utf-8", "replace") if data else "")
    if key in _cache:
        return _cache[key]
    check_url(url)
    host = urllib.parse.urlparse(url).hostname
    naver_gate(host)
    hd = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xml,application/json,*/*",
          "Accept-Language": "ko-KR,ko;q=0.9"}
    hd.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hd)
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
            _cache[key] = body
            return body
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RuntimeError(f"{host}가 요청이 많다고 거절했어요(429). 이번엔 건너뛰세요(다시 몰아 부르지 않기).") from e
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


# ---------------------------------------------------------------- 네이버 공식 검색 API (키 있을 때 기본)

def naver_keys() -> tuple[str, str] | None:
    cid, sec = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    return (cid, sec) if cid and sec else None


def naver_api(kind: str, query: str, display: int = 10, sort: str = "sim") -> list[dict]:
    """검색 API (blog·kin·local …). 하루 25,000회 (developers.naver.com 문서). 키 없으면 RuntimeError."""
    keys = naver_keys()
    if not keys:
        raise RuntimeError("네이버 개발자 키가 없어요 (NAVER_CLIENT_ID·NAVER_CLIENT_SECRET).")
    url = (f"https://openapi.naver.com/v1/search/{kind}.json?display={display}&sort={sort}&query="
           + urllib.parse.quote(query))
    body = fetch(url, headers={"X-Naver-Client-Id": keys[0], "X-Naver-Client-Secret": keys[1]})
    return json.loads(body).get("items", [])


def parse_api_blog(items: list[dict], store: str = "") -> list[dict]:
    """검색 API 블로그 결과 → search-blog와 같은 모양. 순서는 API 정확도순(화면 순위와 다를 수 있음)."""
    res = []
    for x in items:
        link = x.get("link") or ""
        m = re.search(r"blog\.naver\.com/([A-Za-z0-9_\-]+)/?(\d{6,})?", link)
        bid = m.group(1) if m else ""
        bname, title, snip = strip_tags(x.get("bloggername") or ""), strip_tags(x.get("title") or ""), \
            strip_tags(x.get("description") or "")
        pd = x.get("postdate") or ""
        res.append(dict(rank=len(res) + 1, title=title, blog=bname, blog_id=bid,
                        date=f"{pd[:4]}-{pd[4:6]}-{pd[6:]}" if len(pd) == 8 else pd, url=link, snippet=snip[:160],
                        kind=guess_kind(title, snip, bname, store)))
    return res


def parse_api_local(items: list[dict]) -> list[dict]:
    """검색 API 지역 결과 (최대 5곳) → 플레이스 목록 모양. 리뷰 수·별점은 API에 없다."""
    return [dict(rank=i + 1, id=None, name=strip_tags(x.get("title") or ""), category=x.get("category") or "",
                 address=x.get("roadAddress") or x.get("address") or "", visitor_reviews=None, blog_cafe_reviews=None,
                 rating=None, booking=None, talktalk=None, saves=None, link=x.get("link") or "",
                 phone=x.get("telephone") or "") for i, x in enumerate(items)]


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
    if naver_keys():          # 키가 있으면 --unofficial이어도 공식 API
        return parse_api_blog(naver_api("blog", keyword, display=30), store)
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
        if naver_keys():
            lines.append("출처: 네이버 검색 API (정확도순 — 블로그 탭 화면 순위와 다를 수 있어요)")
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
    if not UNOFFICIAL["on"]:      # 블로그 본문은 공식 API가 없다 (검색 API는 요약만)
        raise RuntimeError("블로그 본문 읽기는 공식 API가 없어요. 네 브라우저로 이 글을 한 번 열어 읽거나, "
                           "사장님 글이면 사장님께 본문을 받아 주세요. (위험을 알고 이 가게 몫만: --unofficial)")
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
    if naver_keys():
        api = parse_api_local(naver_api("local", query, display=5, sort="random"))
        if not UNOFFICIAL["on"]:
            return None, api, []
        # 키 + --unofficial: 기본 칸은 API, API에 없는 칸(리뷰 수·리뷰·빠진 정보·영업시간)만 화면에서
        st = apollo_states(fetch("https://m.search.naver.com/search.naver?query=" + urllib.parse.quote(query)))
        detail = parse_place_detail(st)
        if detail and api and norm(api[0]["name"]) == norm(detail["name"]):
            detail.update(name=api[0]["name"], category=api[0]["category"] or detail["category"],
                          road_address=api[0]["address"] or detail["road_address"])
        return detail, api, place_ads(st)
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
    if items and items[0].get("id") is None:          # 공식 API 결과 (리뷰 수 없음)
        return "\n".join(f"{x['rank']}. {x['name']}{' (' + x['category'] + ')' if x['category'] else ''} {x['address']}"
                         + (f" · {x['link']}" if x.get("link") else "") for x in items) + \
            ("\n(공식 검색 API: 이름·업종·주소만. 리뷰 수·리뷰 문장·빠진 정보·영업시간은 API에 없어요 → "
             "사장님께 스마트플레이스 화면 캡처나 플레이스 링크를 받거나, 네 브라우저로 플레이스를 열어 보세요.)")
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
            (f"## '{q}' — 공식 검색 API 지역 결과\n" if items[0].get("id") is None else
             f"## '{q}' — 가게 하나로 특정되지 않아 목록을 보여 드려요 (상호+동네로 다시 검색하면 자세히 나와요)\n")
            + fmt_list(items))
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
    if not naver_keys() and not UNOFFICIAL["on"]:
        raise RuntimeError(UNOFFICIAL_MSG + " 순위는 사장님 폰 검색 화면 캡처로도 볼 수 있어요.")
    source = "api" if naver_keys() else "screen"
    rows, lines = [], [f"## 순위 측정: {store} ({dt.date.today()}, 출처 {source})"]
    for kw in kws:
        row = dict(date=str(dt.date.today()), keyword=kw, store=store, source=source)
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
    if naver_keys():
        lines.append("참고: 공식 검색 API 기준이에요(블로그 정확도순 30개, 지역 5곳). 실제 화면 순위와 다를 수 있어 "
                     "정확한 화면 순위는 사장님 폰 캡처로 확인하세요.")
    else:
        lines.append("참고: 플레이스 순위는 모바일 통합검색에 처음 보이는 목록 기준이에요(보통 5곳). 위치·시간에 따라 달라져요.")
    if a.log:
        new = not os.path.exists(a.log)
        with open(a.log, "a", encoding="utf-8") as f:
            if new:
                f.write("date,keyword,store,blog_rank,place_rank,place_ad,source\n")
            for r in rows:
                f.write(",".join(str(r.get(k) if r.get(k) is not None else "") .replace(",", " ")
                                 for k in ("date", "keyword", "store", "blog_rank", "place_rank", "place_ad", "source")) + "\n")
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


# ---------------------------------------------------------------- 콘텐츠 발굴 (ideas·trend·season·festival)
# 근거: 내부 조사 10 2장(소스 시험), 10b(독립 검증·약관).
# 기본: 내장 달력·구글/유튜브 자동완성·구글 트렌드(비공식, 자주 막힘)·축제 + 키 있으면 네이버 공식 API.
# 네이버 자동완성·관련 검색어·지식iN 화면·쇼핑인사이트 순위는 --unofficial(동의 뒤 이 가게 1곳 몫)일 때만.
# 실패하면 그 소스만 건너뛰고 한 줄로 알린다.

MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


def _try(fails: list, label: str, fn, *args, **kw):
    """소스 하나를 시도하고, 실패하면 이유를 fails에 적고 None."""
    try:
        return fn(*args, **kw)
    except Exception as e:  # noqa: BLE001 — 한 소스 실패로 전체를 멈추지 않는다
        fails.append(f"{label}: {e}")
        return None


def parse_naver_ac(body: str) -> list[str]:
    """네이버 자동완성(PC) JSON → 검색어 목록."""
    d = json.loads(body)
    return [x[0] for x in (d.get("items") or [[]])[0] if x]


def naver_ac(q: str) -> list[str]:
    url = ("https://ac.search.naver.com/nx/ac?con=1&frm=nv&ans=2&r_format=json&r_enc=UTF-8&r_unicode=0"
           "&t_koreng=1&run=2&rev=4&q_enc=UTF-8&st=100&q=" + urllib.parse.quote(q))
    return parse_naver_ac(fetch(url))


def find_qra_url(page: str) -> str | None:
    """모바일 검색결과 HTML 안의 '관련 검색어' 호출 주소."""
    m = re.search(r'"apiURL":"(https://s\.search\.naver\.com/p/qra/[^"]+)"', page)
    return json.loads('"' + m.group(1) + '"') if m else None


def parse_qra(body: str) -> list[dict]:
    """관련 검색어 JSON → [{query, badge}]. badge 예: '많이 찾는'."""
    d = json.loads(body)
    res = []
    for c in (d.get("result") or {}).get("contents") or []:
        if c.get("query"):
            res.append(dict(query=c["query"], badge=(c.get("badge") or {}).get("text", "")))
    return res


def naver_related(q: str) -> list[dict]:
    page = fetch("https://m.search.naver.com/search.naver?query=" + urllib.parse.quote(q),
                 headers={"User-Agent": MOBILE_UA})
    api = find_qra_url(page)
    if not api:
        return []
    return parse_qra(fetch(api, headers={"User-Agent": MOBILE_UA, "Referer": "https://m.search.naver.com/"}))


def parse_kin(page: str, today: dt.date, months: int = 12) -> tuple[list[dict], int]:
    """지식iN 검색 결과 → (최근 months개월 질문 [{title, date, url}], 오래돼서 뺀 수)."""
    items, old = [], 0
    cutoff = today - dt.timedelta(days=months * 30)
    for li in re.findall(r"<dl>(.*?)</dl>", page, re.S):
        a = re.search(r'<dt>\s*<a href="([^"]+)"[^>]*>(.*?)</a>', li, re.S)
        d = re.search(r'<dd class="txt_inline">\s*(\d{4})\.(\d{1,2})\.(\d{1,2})', li)
        if not a:
            continue
        date = dt.date(int(d.group(1)), int(d.group(2)), int(d.group(3))) if d else None
        if date and date < cutoff:
            old += 1
            continue
        url = re.sub(r"&qb=[^&]*", "", html.unescape(a.group(1)))
        items.append(dict(title=strip_tags(a.group(2)), date=date.isoformat() if date else "", url=url))
    return items, old


def kin_questions(q: str, today: dt.date) -> tuple[list[dict], int]:
    return parse_kin(fetch("https://kin.naver.com/search/list.naver?query=" + urllib.parse.quote(q)), today)


def parse_google_suggest(body: str) -> list[str]:
    d = json.loads(body)
    return [x for x in d[1] if isinstance(x, str)] if isinstance(d, list) and len(d) > 1 else []


def youtube_ac(q: str) -> list[str]:
    return parse_google_suggest(fetch("https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&hl=ko&q="
                                      + urllib.parse.quote(q)))


def searchad_volume(keywords: list[str]) -> list[dict]:
    """네이버 검색광고 키워드도구 (환경변수 NAVER_AD_API_KEY·NAVER_AD_SECRET·NAVER_AD_CUSTOMER_ID 있을 때만).
    월간 검색수(PC·모바일)·경쟁정도. 서명: HMAC-SHA256("{ms}.GET./keywordstool") base64."""
    import base64
    import hashlib
    import hmac
    key, sec, cid = (os.environ.get(k) for k in ("NAVER_AD_API_KEY", "NAVER_AD_SECRET", "NAVER_AD_CUSTOMER_ID"))
    if not (key and sec and cid):
        return []
    ts = str(int(time.time() * 1000))
    sig = base64.b64encode(hmac.new(sec.encode(), f"{ts}.GET./keywordstool".encode(), hashlib.sha256).digest()).decode()
    hint = ",".join(k.replace(" ", "") for k in keywords[:5])      # 키워드도구는 공백 없는 말만 받는다
    body = fetch("https://api.searchad.naver.com/keywordstool?showDetail=1&hintKeywords=" + urllib.parse.quote(hint),
                 headers={"X-Timestamp": ts, "X-API-KEY": key, "X-Customer": cid, "X-Signature": sig})
    res = []
    for x in json.loads(body).get("keywordList", [])[:30]:
        res.append(dict(keyword=x.get("relKeyword"), pc=x.get("monthlyPcQcCnt"), mobile=x.get("monthlyMobileQcCnt"),
                        comp=x.get("compIdx")))
    return res


def google_ac(q: str) -> list[str]:
    """구글 웹 검색 자동완성 (키 없음). 네이버 자동완성 대신 기본으로 쓴다."""
    return parse_google_suggest(fetch("https://suggestqueries.google.com/complete/search?client=firefox&hl=ko&q="
                                      + urllib.parse.quote(q)))


def parse_api_kin(items: list[dict]) -> list[dict]:
    """검색 API 지식iN 결과 → [{title, date, url}]. API에는 날짜가 없다."""
    return [dict(title=strip_tags(x.get("title") or ""), date="", url=x.get("link") or "") for x in items]


def ideas_seeds(kw: str, menus: list[str], area: str | None) -> list[str]:
    """'동네 업종' + '동네 메뉴' 씨앗. 동네는 --area, 없으면 -k의 마지막 단어 앞부분."""
    seeds = [k.strip() for k in kw.split(",") if k.strip()]
    if menus:
        a = area if area is not None else split_seed(seeds[0])[0]
        seeds += [f"{a} {m}".strip() for m in menus]
    return list(dict.fromkeys(seeds))


def split_seed(seed: str) -> tuple[str, str]:
    """'서울 마포 빵집' → ('서울 마포', '빵집'). 마지막 단어가 업종·메뉴 (ideas_seeds와 같은 기준)."""
    return tuple(seed.rsplit(" ", 1)) if " " in seed else ("", seed)  # type: ignore[return-value]


def widen_levels(seed: str, wide: list[str]) -> list[tuple[str, str]]:
    """동 → 시·구 → 업종만 순서로 넓힌 검색어 (10b 2-2). [(단계, 검색어)]."""
    area, rest = split_seed(seed)
    if not area:
        return [("그대로", seed)]
    levels = [("동네", seed)] + [("시·구", f"{w} {rest}") for w in wide if w and w != area] + [("업종만", rest)]
    return list(dict.fromkeys(levels))


def cmd_ideas(a):
    kw = a.keyword or a.kw
    if not kw:
        raise RuntimeError('씨앗 검색어를 넣어 주세요. 예: ideas -k "정발산동 빵집" --wide 일산 --menu 소금빵,크루아상')
    menus = [m.strip() for m in (a.menu or "").split(",") if m.strip()][:3]
    all_seeds = ideas_seeds(kw, menus, a.area)
    if not all_seeds:
        raise RuntimeError('씨앗 검색어가 비었어요. 예: ideas -k "정발산동 빵집" --wide 일산 --menu 소금빵')
    keys, unoff = bool(naver_keys()), UNOFFICIAL["on"]
    # 요청 20번 상한에 조용히 잘리지 않게: --unofficial은 씨앗당 요청이 많아 2개, 키(지식iN)가 있으면 3개
    cap = 2 if unoff else 3 if keys else 4
    seeds = all_seeds[:cap]
    local = a.area != ""           # --area "" (매장 없는 사업)이면 넓히지 않는다
    wide = [w.strip() for w in (a.wide or "").split(",") if w.strip()][:2]
    today = dt.date.today()
    fails: list[str] = []
    res = dict(date=today.isoformat(), route=dict(naver_api=keys, unofficial=unoff), seeds=[], youtube=[], volume=[],
               fails=fails)
    lines = [f"## 콘텐츠 발굴 재료 ({today}) — 씨앗 {len(seeds)}개"
             + (f" (넣은 {len(all_seeds)}개 중 앞 {len(seeds)}개만 — 나머지({', '.join(all_seeds[cap:])})는 "
                + ("다음 주에, 또는 --unofficial 없이)" if unoff else "따로 한 번 더 실행)")
                if len(all_seeds) > cap else ""),
             "경로: 구글 자동완성(키 없음)" + (" + 네이버 검색 API(지식iN)" if keys else "")
             + (" + 네이버 자동완성·관련 검색어(--unofficial)" if unoff else "")]
    vol = _try(fails, "검색광고 키워드도구", searchad_volume, seeds)      # 요청 예산을 먼저 확보
    for sd in seeds:
        row = dict(seed=sd, level="", query=sd, google=None, naver_ac=None, related=None, kin=[], kin_old=0)
        for level, q in (widen_levels(sd, wide) if local else [("그대로", sd)]):   # 값이 나올 때까지 넓힌다
            g = _try(fails, f"구글 자동완성 '{q}'", google_ac, q)
            row.update(level=level, query=q, google=g)
            if g:
                break
        if unoff:
            row["naver_ac"] = _try(fails, f"네이버 자동완성 '{row['query']}'", naver_ac, row["query"])
            row["related"] = _try(fails, f"관련 검색어 '{row['query']}'", naver_related, row["query"])
        if keys:
            k = _try(fails, f"지식iN API '{sd}'", lambda q: parse_api_kin(naver_api("kin", q, display=10)), sd)
            row["kin"] = (k or [])[: a.max]
        elif unoff:
            k = _try(fails, f"지식iN '{sd}'", kin_questions, sd, today)
            row["kin"], row["kin_old"] = ((k[0][: a.max], k[1]) if k else ([], 0))
        res["seeds"].append(row)
        lab = "" if row["level"] in ("동네", "그대로") else f" → 넓힘: {row['level']} '{row['query']}' (전국·넓은 지역 사람 말일 수 있음)"
        lines.append(f"\n### {sd}{lab}")
        lines.append("- 구글 자동완성: " + (", ".join(row["google"]) if row["google"] else "(없음)"))
        if unoff:
            lines.append("- 네이버 자동완성: " + (", ".join(row["naver_ac"] or []) or "(없음/못 가져옴)"))
            lines.append("- 관련 검색어: " + (", ".join(r["query"] + (f"[{r['badge']}]" if r["badge"] else "")
                                                   for r in (row["related"] or [])) or "(없음/못 가져옴)"))
        if keys or unoff:
            lines.append(f"- 지식iN 질문 {len(row['kin'])}개" + (f" (최근 12개월만, 오래된 것 {row['kin_old']}개 뺌)" if not keys
                                                            else " (API는 날짜가 없어요 — 열어서 최근 것만 쓰기)") + ":")
            lines += [f"  · {k['title']}" + (f" ({k['date']})" if k["date"] else "") + f" {k['url']}" for k in row["kin"]]
    if not a.no_youtube:
        yt = _try(fails, "유튜브 자동완성", youtube_ac, res["seeds"][0]["query"])
        res["youtube"] = yt or []
        lines.append(f"\n- 유튜브 자동완성({res['seeds'][0]['query']}): " + (", ".join(yt) if yt else "(없음/못 가져옴)"))
    if vol:
        res["volume"] = vol
        lines.append("\n- 월간 검색수(키워드도구, PC/모바일/광고 경쟁): "
                     + "; ".join(f"{v['keyword']} {v['pc']}/{v['mobile']}/{v['comp']}" for v in vol[:15])
                     + "\n  (경쟁 = 광고주 수. 블로그 경쟁이 아니에요)")
    elif vol == []:
        lines.append("\n- 월간 검색수: 검색광고 키 없음(선택). guides/00-start.md 5-1)")
    if not keys and not unoff:
        lines.append("- 지식iN·네이버 자동완성: 네이버 개발자 키가 없어 건너뜀. 손님 질문은 사장님 3문항·리뷰에서 받아요.")
    if fails:
        lines.append("\n이번에 못 가져온 것 (건너뛰고 계속함): " + " / ".join(fails))
        if any("요청은" in f for f in fails):
            lines.append("※ 한 번 실행 요청 상한(20번)에 걸려 일부가 잘렸어요. 씨앗을 줄여 나눠 실행하세요.")
    out(res, a.json, "\n".join(lines))


# --- trend

def parse_gt_json(body: str):
    """구글 트렌드 응답 앞의 )]}' 같은 방어 글자를 떼고 JSON."""
    return json.loads(body[body.find("{"):])


def trend_direction(values: list[float]) -> str:
    """최근 4주 평균 vs 그 전 4주 평균 (일 단위면 28일씩)."""
    n = 28 if len(values) > 40 else 4
    if len(values) < n * 2:
        return "판단 불가(자료 부족)"
    recent, before = sum(values[-n:]) / n, sum(values[-2 * n:-n]) / n
    if recent < 3 and before < 3:
        return "검색 적음(판단 보류)"
    if sum(1 for v in values[-n:] if v == 0) * 2 >= n:      # 최근 구간 절반 넘게 0 = 띄엄띄엄 튀는 값
        return "검색 드묾(판단 보류)"
    if before == 0:
        return "새로 생김" if recent > 0 else "검색 거의 없음"
    r = (recent - before) / before
    return f"오름 (+{r:.0%})" if r >= 0.2 else f"내림 ({r:.0%})" if r <= -0.2 else f"보합 ({r:+.0%})"


def related_index(widget_id: str) -> int:
    """'RELATED_QUERIES_1' → 1. 키워드가 1개면 id가 'RELATED_QUERIES'(번호 없음) → 0."""
    return int(widget_id.rsplit("_", 1)[1]) if widget_id[-1].isdigit() else 0


def _gt_explore(kws: list[str]) -> list[dict]:
    req = {"comparisonItem": [{"keyword": k, "geo": "KR", "time": "today 3-m"} for k in kws], "category": 0, "property": ""}
    ex = parse_gt_json(fetch("https://trends.google.com/trends/api/explore?hl=ko&tz=-540&req="
                             + urllib.parse.quote(json.dumps(req, ensure_ascii=False))))
    return [w for w in ex.get("widgets", []) if "token" in w
            and (w["id"] == "TIMESERIES" or w["id"].startswith("RELATED_QUERIES"))]


def _gt_widget(kind: str, w: dict):
    q = "?hl=ko&tz=-540&req=" + urllib.parse.quote(json.dumps(w["request"], ensure_ascii=False)) + "&token=" + w["token"]
    return parse_gt_json(fetch(f"https://trends.google.com/trends/api/widgetdata/{kind}" + q))["default"]


def google_trend(kws: list[str], joint: bool = True) -> dict:
    """키워드마다 따로 조회해 방향을 본다(같은 차트에 넣으면 작은 말이 0 근처로 눌림).
    joint=True면 크기 비교용 공동 차트를 한 번 더. 비공식 내부 주소라 자주 막힌다(429)."""
    fetch("https://trends.google.com/trends/?geo=KR")       # 첫 방문 쿠키
    res = dict(source="구글 트렌드 (비공식 내부 주소·자주 막힘(429), 최근 3개월, 한국, 키워드마다 최고점=100)",
               series={}, related={}, joint={})
    for k in kws:
        try:
            for w in _gt_explore([k]):
                if w["id"] == "TIMESERIES":
                    tl = _gt_widget("multiline", w)["timelineData"]
                    res["series"][k] = [(t["formattedTime"], t["value"][0]) for t in tl]
                elif related_index(w["id"]) == 0:
                    rl = _gt_widget("relatedsearches", w)["rankedList"]
                    res["related"][k] = dict(top=[(x["query"], x.get("formattedValue")) for x in rl[0]["rankedKeyword"][:8]],
                                             rising=[(x["query"], x.get("formattedValue")) for x in rl[1]["rankedKeyword"][:8]])
        except Exception as e:  # noqa: BLE001 — 한 키워드 실패로 나머지를 멈추지 않는다
            res["related"].setdefault(k, dict(error=str(e)))
    if not res["series"]:
        raise RuntimeError("구글 트렌드에서 추이를 하나도 못 받았어요: "
                           + "; ".join(dict.fromkeys(v.get("error", "") for v in res["related"].values() if "error" in v)))
    if joint and len(kws) > 1:
        try:
            tw = next(w for w in _gt_explore(kws) if w["id"] == "TIMESERIES")
            tl = _gt_widget("multiline", tw)["timelineData"][-28:]
            res["joint"] = {k: round(sum(t["value"][i] for t in tl) / max(len(tl), 1), 1) for i, k in enumerate(kws)}
        except Exception as e:  # noqa: BLE001
            res["joint"] = dict(error=str(e))
    return res


def datalab_trend(kws: list[str]) -> dict:
    """네이버 데이터랩 검색어트렌드 공식 API (NAVER_CLIENT_ID·NAVER_CLIENT_SECRET 있을 때). 하루 1,000회(공식 문서).
    키워드마다 따로 한 번씩(방향용) + 공동 한 번(크기 비교용)."""
    keys = naver_keys()
    if not keys:
        return {}
    end = dt.date.today() - dt.timedelta(days=1)

    def call(groups: list[str]) -> list[dict]:
        body = dict(startDate=(end - dt.timedelta(weeks=26)).isoformat(), endDate=end.isoformat(), timeUnit="week",
                    keywordGroups=[dict(groupName=k, keywords=[k]) for k in groups])
        return json.loads(fetch("https://openapi.naver.com/v1/datalab/search", data=json.dumps(body).encode(),
                                headers={"X-Naver-Client-Id": keys[0], "X-Naver-Client-Secret": keys[1],
                                         "Content-Type": "application/json"})).get("results", [])
    res = dict(source="네이버 데이터랩 검색어트렌드 (공식 API, 최근 26주, 주 단위, 키워드마다 최고점=100)",
               series={}, related={}, joint={})
    for k in kws[:5]:
        for r in call([k]):
            res["series"][r["title"]] = [(p["period"], p["ratio"]) for p in r["data"]]
    if len(kws) > 1:
        res["joint"] = {r["title"]: round(sum(p["ratio"] for p in r["data"][-4:]) / 4, 1) for r in call(kws[:5])}
    return res


def cmd_trend(a):
    kw = a.keyword or a.kw
    kws = [k.strip() for k in (kw or "").split(",") if k.strip()][:5]
    if not kws:
        raise RuntimeError('검색어를 쉼표로 넣어 주세요 (5개까지). 예: trend -k 소금빵,크루아상')
    fails: list[str] = []
    res = None
    if not a.google:
        res = _try(fails, "데이터랩 API", datalab_trend, kws) or None
    if not res:
        res = _try(fails, "구글 트렌드", google_trend, kws)
    if not res:
        out(dict(fails=fails), a.json, "추이를 못 가져왔어요: " + " / ".join(fails)
            + "\n사장님께 trends.google.com(또는 데이터랩) 화면 캡처를 받아 보세요.")
        return
    lines = [f"## 검색어 추이 — {res['source']}"]
    res["direction"] = {}
    for k, ser in res["series"].items():
        vals = [float(v) for _, v in ser]
        res["direction"][k] = trend_direction(vals)
        last = ", ".join(f"{t} {v}" for t, v in ser[-3:])
        lines.append(f"- {k}: {res['direction'][k]} · 최근 {last}")
    for k, r in res["related"].items():
        if "error" in r:
            lines.append(f"- {k}: 못 가져옴 ({r['error'][:80]})")
            continue
        lines.append(f"- {k} 관련 상위: " + (", ".join(f"{q}({v})" for q, v in r["top"]) or "(없음)"))
        lines.append("  급등: " + (", ".join(f"{q}({v})" for q, v in r["rising"]) or "(없음)"))
    if res.get("joint") and "error" not in res["joint"]:
        lines.append("- 크기 비교(같은 차트, 최근 4주 평균, 가장 큰 말 기준 상대값): "
                     + ", ".join(f"{k} {v}" for k, v in res["joint"].items()))
    elif res.get("joint"):
        lines.append("- 크기 비교: 못 가져옴")
    lines.append("※ 방향은 키워드마다 따로 본 것, 크기 비교만 같은 차트예요. 숫자는 검색 '양'이 아니라 상대값이에요. "
                 "한국 동네 가게 검색은 네이버 비중이 커서 구글 값은 참고만.")
    if fails:
        lines.append("못 가져온 것: " + " / ".join(fails))
    res["fails"] = fails
    out(res, a.json, "\n".join(lines))


# --- season

# 날짜가 해마다 같은 기념일·행사 (월, 일, 이름, 메모)
FIXED_DAYS = [
    (1, 1, "새해 첫날", "새해 인사·첫 방문"), (2, 14, "밸런타인데이", "선물·디저트"), (3, 1, "삼일절", "공휴일"),
    (3, 3, "삼겹살데이", "고깃집"), (3, 14, "화이트데이", "선물·디저트"), (4, 14, "블랙데이", "짜장면"),
    (5, 1, "노동절", "쉬는 곳 많음"), (5, 5, "어린이날", "공휴일·가족"), (5, 8, "어버이날", "선물·가족 외식"),
    (5, 15, "스승의 날", "선물"), (6, 6, "현충일", "공휴일"), (7, 17, "제헌절", ""),
    (8, 15, "광복절", "공휴일"), (10, 3, "개천절", "공휴일"), (10, 9, "한글날", "공휴일"),
    (10, 31, "핼러윈", "포토존·한정 메뉴"), (11, 11, "빼빼로데이·가래떡데이", "선물"),
    (12, 24, "크리스마스이브", "케이크·모임"), (12, 25, "크리스마스", "공휴일·케이크·모임"), (12, 31, "한 해 마지막 날", "연말"),
]
# 음력·해마다 바뀌는 날 (확인된 해만). 다음 해는 발표·달력 확인 후 추가한다.
YEAR_DAYS = {
    2026: [("2026-02-16", "2026-02-18", "설 연휴", "귀성·선물·휴무 안내"), ("2026-03-03", None, "정월대보름", "부럼·오곡밥"),
           ("2026-05-24", None, "부처님오신날", "공휴일"), ("2026-09-24", "2026-09-26", "추석 연휴", "선물·휴무 안내"),
           ("2026-11-19", None, "수능", "수험생 응원·수능 끝난 뒤")],
    2027: [("2027-02-06", "2027-02-08", "설 연휴", "귀성·선물·휴무 안내 (대체휴일은 달력 확인)"),
           ("2027-02-21", None, "정월대보름", "부럼·오곡밥"), ("2027-05-13", None, "부처님오신날", "공휴일"),
           ("2027-09-14", "2027-09-16", "추석 연휴", "선물·휴무 안내")],
}
# 절기 (대략 날짜, 해마다 하루 정도 다름)
SOLAR_TERMS = [(1, 5, "소한"), (1, 20, "대한"), (2, 4, "입춘"), (2, 19, "우수"), (3, 5, "경칩"), (3, 20, "춘분"),
               (4, 5, "청명·식목일"), (4, 20, "곡우"), (5, 5, "입하"), (5, 21, "소만"), (6, 6, "망종"), (6, 21, "하지"),
               (7, 7, "소서"), (7, 23, "대서"), (8, 7, "입추"), (8, 23, "처서"), (9, 7, "백로"), (9, 23, "추분"),
               (10, 8, "한로"), (10, 23, "상강"), (11, 7, "입동"), (11, 22, "소설"), (12, 7, "대설"), (12, 22, "동지(팥죽)")]
# 기간 시즌 (시작 월/일, 끝 월/일, 이름) — 보통 그렇다는 범위. 지역·해마다 다르다.
SEASONS = [((1, 1), (1, 31), "새해 다짐·다이어트"), ((2, 1), (2, 28), "졸업 시즌"), ((3, 1), (3, 15), "입학·개학"),
           ((3, 25), (4, 15), "벚꽃·봄나들이"), ((5, 1), (5, 31), "가정의 달"), ((6, 20), (7, 25), "장마"),
           ((7, 20), (8, 15), "여름휴가·방학"), ((10, 10), (11, 10), "단풍·가을나들이"), ((11, 10), (12, 10), "김장철"),
           ((12, 1), (12, 31), "연말 모임·송년회"), ((12, 20), (12, 31), "겨울방학 시작")]


def _nth_weekday(y: int, m: int, weekday: int, n: int) -> dt.date:
    d = dt.date(y, m, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def day_stem(d: dt.date) -> int:
    """일진 천간 번호 (0=갑 … 6=경 … 9=계). 기준: 2024-07-15 초복(경일)."""
    return (6 + (d - dt.date(2024, 7, 15)).days) % 10


def boknal(y: int) -> list[tuple[dt.date, str]]:
    """초복 = 하지 뒤 셋째 경일, 중복 = 넷째 경일, 말복 = 입추 뒤 첫 경일 (하지 6/21, 입추 8/7 기준 근사)."""
    def gyeong_after(start: dt.date, n: int) -> dt.date:
        d, c = start, 0
        while True:
            if day_stem(d) == 6:
                c += 1
                if c == n:
                    return d
            d += dt.timedelta(days=1)
    return [(gyeong_after(dt.date(y, 6, 21), 3), "초복"), (gyeong_after(dt.date(y, 6, 21), 4), "중복"),
            (gyeong_after(dt.date(y, 8, 7), 1), "말복")]


def season_events(today: dt.date, weeks: int) -> list[dict]:
    """오늘부터 weeks주 안의 기념일·절기·시즌 (D-day 순)."""
    end = today + dt.timedelta(weeks=weeks)
    ev = []

    def add(start: dt.date, name: str, memo: str = "", kind: str = "기념일", until: dt.date | None = None):
        last = until or start
        if last >= today and start <= end:
            ev.append(dict(date=start.isoformat(), until=until.isoformat() if until else "", name=name, memo=memo,
                           kind=kind, d=(start - today).days))
    for y in (today.year, today.year + 1):
        for m, d, name, memo in FIXED_DAYS:
            add(dt.date(y, m, d), name, memo)
        for s, u, name, memo in YEAR_DAYS.get(y, []):
            add(dt.date.fromisoformat(s), name, memo, until=dt.date.fromisoformat(u) if u else None)
        for m, d, name in SOLAR_TERMS:
            add(dt.date(y, m, d), name, "절기(하루 정도 차이)", "절기")
        for (m1, d1), (m2, d2), name in SEASONS:
            add(dt.date(y, m1, d1), name, "보통 이 무렵", "시즌", until=dt.date(y, m2, d2))
        for d, name in boknal(y):
            add(d, name, "삼계탕·보양", "절기")
        bf = _nth_weekday(y, 11, 3, 4) + dt.timedelta(days=1)     # 미국 추수감사절(넷째 목) 다음 날
        add(bf, "블랙프라이데이", "할인 행사")
        add(_nth_weekday(y, 5, 0, 3), "성년의 날", "")
    if today.year not in YEAR_DAYS or (end.year != today.year and end.year not in YEAR_DAYS):
        ev.append(dict(date="", until="", name="(설·추석 등 음력 날짜 표가 없는 해가 섞였어요 — 달력 확인)", memo="",
                       kind="안내", d=999))
    for y in sorted({today.year, end.year}):       # 수능은 해마다 교육부가 정한다 — 모르는 해는 넣지 않고 안내만
        nov = (dt.date(y, 11, 1), dt.date(y, 11, 30))
        if nov[0] <= end and nov[1] >= today and not any(n == "수능" for _, _, n, _ in YEAR_DAYS.get(y, [])):
            ev.append(dict(date="", until="", name=f"({y}년 수능 날짜가 표에 없어요 — 교육부 발표 확인)", memo="",
                           kind="안내", d=999))
    ev.sort(key=lambda x: (x["d"], x["name"]))
    return ev


SHOP_CATS = {"패션의류": "50000000", "패션잡화": "50000001", "화장품/미용": "50000002", "디지털/가전": "50000003",
             "가구/인테리어": "50000004", "출산/육아": "50000005", "식품": "50000006", "스포츠/레저": "50000007",
             "생활/건강": "50000008", "여가/생활편의": "50000009"}


def parse_shop_rank(body: str) -> list[str]:
    return [r["keyword"] for r in json.loads(body).get("ranks", [])]


def shop_rank(cid: str, start: dt.date, end: dt.date) -> list[str]:
    data = urllib.parse.urlencode(dict(cid=cid, timeUnit="date", startDate=start.isoformat(), endDate=end.isoformat(),
                                       age="", gender="", device="", page=1, count=20)).encode()
    return parse_shop_rank(fetch("https://datalab.naver.com/shoppingInsight/getCategoryKeywordRank.naver", data=data,
                                 headers={"Referer": "https://datalab.naver.com/shoppingInsight/sCategory.naver",
                                          "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}))


def cmd_season(a):
    today = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    ev = season_events(today, a.weeks)
    lines = [f"## 앞으로 {a.weeks}주 시즌 달력 ({today} 기준)"]
    for e in ev:
        if e["kind"] == "안내":
            lines.append(f"- {e['name']}")
            continue
        when = f"D-{e['d']}" if e["d"] > 0 else ("오늘" if e["d"] == 0 else "진행 중")
        rng = f"~{e['until'][5:]}" if e["until"] else ""
        lines.append(f"- {when:>5} {e['date'][5:]}{rng} {e['name']} [{e['kind']}]" + (f" — {e['memo']}" if e["memo"] else ""))
    res = dict(date=today.isoformat(), weeks=a.weeks, events=ev, shopping={}, fails=[])
    cats = [c.strip() for c in (a.cat or "식품").split(",") if c.strip()][:3]
    if a.no_shop:
        pass
    elif not UNOFFICIAL["on"]:
        lines.append("\n- 쇼핑 인기 검색어: 공식 API에 '분야별 순위'가 없어 기본으로 건너뜀. 사장님께 datalab.naver.com 쇼핑인사이트 "
                     "분야별 인기검색어를 기간 '작년 같은 시기 2~6주 뒤'로 맞춘 화면 캡처를 부탁하면 다가올 시즌 상품이 나와요. "
                     "자동으로 보려면 사장님 동의 뒤 이 가게 몫만 --unofficial.")
    else:
        fs, fe = shop_window(today)
        end = today - dt.timedelta(days=1)
        for c in cats:
            cid = SHOP_CATS.get(c, c)
            fut = _try(res["fails"], f"쇼핑인사이트 {c}(작년 같은 시기)", shop_rank, cid, fs, fe)
            now = _try(res["fails"], f"쇼핑인사이트 {c}(지난 7일)", shop_rank, cid, end - dt.timedelta(days=6), end)
            res["shopping"][c] = dict(cid=cid, future_period=f"{fs}~{fe}", future=fut or [],
                                      recent_period=f"{end - dt.timedelta(days=6)}~{end}", recent=now or [])
            lines.append(f"\n- 다가올 시즌 신호({c}) = 작년 {fs}~{fe} 인기 검색어: "
                         + (", ".join(f"{i + 1} {k}" for i, k in enumerate(fut)) if fut else "못 가져옴"))
            lines.append(f"- 지난 7일 순위({c}, 이미 지난 결과 — '지금 반응' 확인용): "
                         + (", ".join(f"{i + 1} {k}" for i, k in enumerate(now)) if now else "못 가져옴"))
        lines.append("  ※ 작년 유행이 올해도 통할지는 따로 판단(예: 반짝 유행 상품). 근거: 10b 2-3")
    if res["fails"]:
        lines.append("못 가져온 것 (건너뜀): " + " / ".join(res["fails"]))
    out(res, a.json, "\n".join(lines))


def shop_window(today: dt.date) -> tuple[dt.date, dt.date]:
    """'퓨처 키워드' 창: 작년 같은 날 + 2주 ~ + 6주 (10b 2-3)."""
    try:
        ly = today.replace(year=today.year - 1)
    except ValueError:          # 2월 29일
        ly = today.replace(year=today.year - 1, day=28)
    return ly + dt.timedelta(weeks=2), ly + dt.timedelta(weeks=6)


# --- festival

FEST_AREAS = {"서울": "1", "인천": "2", "대전": "3", "대구": "4", "광주": "5", "전남": "5", "부산": "6", "울산": "7",
              "세종": "8", "경기": "31", "강원": "32", "충북": "33", "충남": "34", "경북": "35", "경남": "36",
              "전북": "37", "제주": "39"}
# 시·군 이름만 넣었을 때 시·도를 찾는 짧은 표 (자주 쓰는 곳만, 없으면 시·도부터 넣어 달라고 안내)
CITY_TO_AREA = {"고양": "경기", "일산": "경기", "파주": "경기", "김포": "경기", "수원": "경기", "성남": "경기", "분당": "경기",
                "용인": "경기", "부천": "경기", "안양": "경기", "화성": "경기", "평택": "경기", "의정부": "경기",
                "남양주": "경기", "안산": "경기", "춘천": "강원", "강릉": "강원", "속초": "강원", "원주": "강원",
                "청주": "충북", "천안": "충남", "아산": "충남", "포항": "경북", "경주": "경북", "안동": "경북",
                "창원": "경남", "김해": "경남", "통영": "경남", "전주": "전북", "군산": "전북", "여수": "전남",
                "순천": "전남", "목포": "전남", "해운대": "부산", "서귀포": "제주"}


def festival_area(area: str) -> tuple[str, list[str]]:
    """'경기 고양' → ('31', ['고양']). 첫 단어가 시·군이면 표에서 시·도를 찾는다."""
    words = area.replace(",", " ").split()
    if not words:
        raise RuntimeError('지역을 넣어 주세요. 예: festival --area "경기 고양"')
    first = words[0]
    for full, short in (("충청북", "충북"), ("충청남", "충남"), ("경상북", "경북"), ("경상남", "경남"),
                        ("전라북", "전북"), ("전라남", "전남")):
        first = first.replace(full, short)
    alias = {"일산": "고양", "분당": "성남"}           # 시·군이 아닌 생활권 이름 → 축제 목록의 시·군
    for k, code in FEST_AREAS.items():
        if first.startswith(k):
            return code, [alias.get(w, w) for w in words[1:]]
    for city, prov in CITY_TO_AREA.items():
        if first.startswith(city):
            return FEST_AREAS[prov], [alias.get(w, w) for w in words]
    raise RuntimeError(f"'{first}'의 시·도를 모르겠어요. 시·도부터 넣어 주세요. 예: --area \"경기 {first}\"")


def parse_festivals(body: str) -> tuple[list[dict], int]:
    d = json.loads(body)
    items = []
    for x in d.get("resultList") or []:
        items.append(dict(name=x.get("cntntsNm") or "", start=(x.get("fstvlBgngDe") or "").replace(".", "-"),
                          end=(x.get("fstvlEndDe") or "").replace(".", "-"), area=x.get("areaNm") or "",
                          place=x.get("dtadr") or "", fee=(x.get("fstvlUtztFareInfo") or "").strip()))
    return items, int(d.get("totalCnt") or 0)


def filter_festivals(items: list[dict], cities: list[str], today: dt.date, weeks: int) -> list[dict]:
    end = (today + dt.timedelta(weeks=weeks)).isoformat()
    t = today.isoformat()
    keep = [x for x in items if x["end"] >= t and x["start"] <= end
            and (not cities or any(c in x["area"] or c in x["place"] for c in cities))]
    return sorted(keep, key=lambda x: x["start"])


def cmd_festival(a):
    code, cities = festival_area(a.area)
    today = dt.date.today()
    items, fails, total, page = [], [], None, 0
    while page < 8:                                 # 한 번에 최대 8쪽(96개)
        body = _try(fails, f"축제 목록 {page + 1}쪽", fetch,
                    "https://korean.visitkorea.or.kr/kfes/list/selectWntyFstvlList.do",
                    data=urllib.parse.urlencode(dict(startIdx=page * 12, searchType="A", searchDate="", searchArea=code,
                                                     searchCate="")).encode(),
                    headers={"Referer": "https://korean.visitkorea.or.kr/kfes/list/wntyFstvlList.do",
                             "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        if body is None:
            break
        got, total = parse_festivals(body)
        items += got
        page += 1
        if not got or len(items) >= total:
            break
    keep = filter_festivals(items, cities, today, a.weeks)
    wide = filter_festivals(items, [], today, a.weeks) if cities and not keep else []
    lines = [f"## 축제 ({a.area}, 오늘~{a.weeks}주, 대한민국 구석구석 {len(items)}/{total or '?'}개 중)"]
    for x in keep:
        lines.append(f"- {x['start'][5:]}~{x['end'][5:]} {x['name']} — {x['area']} {x['place']}" + (f" · {x['fee']}" if x["fee"] else ""))
    if not keep:
        lines.append("- 이 지역에는 이 기간 축제가 없어요." + (" 같은 시·도 전체:" if wide else ""))
        lines += [f"  · {x['start'][5:]}~{x['end'][5:]} {x['name']} — {x['area']}" for x in wide[:10]]
    if fails:
        lines.append("못 가져온 것 (건너뜀): " + " / ".join(fails) + " → 브라우저로 korean.visitkorea.or.kr 축제 달력 확인")
    out(dict(area=a.area, code=code, festivals=keep, same_province=wide[:10], fetched=len(items), total=total,
             fails=fails), a.json, "\n".join(lines))


# ---------------------------------------------------------------- 동작 확인

def cmd_check(a):
    """파이썬이 돌면 스크립트 모드. 조사 경로(공식 API / --unofficial / 없음)를 함께 알려 준다."""
    t0 = time.time()
    pil = True
    try:
        import PIL  # type: ignore  # noqa: F401
    except ImportError:
        pil = False
    route, n, err = "없음", 0, ""
    try:
        if naver_keys():
            n, route = len(naver_api("blog", "네이버 블로그", display=5)), "공식 검색 API"
        elif UNOFFICIAL["on"]:
            n, route = len(blog_search("네이버 블로그")), "비공식(--unofficial)"
    except RuntimeError as e:
        err = str(e)
    res = dict(ok=True, version=VERSION, search_route=route, search_results=n, search_error=err,
               seconds=round(time.time() - t0, 1), pillow=pil, sips=bool(shutil.which("sips")),
               rules=os.path.exists(os.path.join(HERE, "rules.json")))
    if route == "없음":
        srch = ("검색 조사: 키 없음 → 네이버 개발자 키를 넣으면 공식 API로 조사해요(guides/00-start.md 5-1)). "
                "그전에는 사장님 링크·캡처 + 네 브라우저로 사람이 보듯 확인하세요. 발굴은 season·trend·festival·ideas(구글·유튜브)로 돼요.")
    elif err or not n:
        srch = f"검색 조사({route}): 결과를 못 읽었어요 {err} — 브라우저로 진행하고 제보해 주세요."
    else:
        srch = f"검색 조사: {route} 사용 가능 ({n}건)"
    out(res, a.json,
        f"OK — 스크립트 모드 사용 가능 (mk.py {VERSION}, {res['seconds']}초)\n{srch}"
        + f"\n이미지 색: {'Pillow' if pil else ('PNG 직접 + 맥 sips' if res['sips'] else 'PNG만')} · "
          f"표현 검사 규칙: {'있음' if res['rules'] else '없음(lint 건너뜀)'}")


# ---------------------------------------------------------------- main

def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="AI 마케터 조사 도우미 (네이버 블로그·플레이스·순위·색·글자 수·표현 검사·콘텐츠 발굴)")
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def p(name, fn, help_):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--json", action="store_true", help="JSON으로 출력")
        s.add_argument("--unofficial", action="store_true",
                       help="네이버 검색 화면·비공식 주소도 읽기 (약관 위험. 이 가게 1곳 몫·주 1회만)")
        s.set_defaults(fn=fn)
        return s

    p("check", cmd_check, "동작 확인 (키가 있으면 공식 검색 API 1회)")

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

    s = p("ideas", cmd_ideas, "콘텐츠 발굴: 구글·유튜브 자동완성 (+키: 지식iN·검색수, +--unofficial: 네이버 자동완성·관련 검색어)")
    s.add_argument("kw", nargs="?", help="'동네 업종' (쉼표로 여러 개)")
    s.add_argument("--keyword", "-k", help="'동네 업종' 예: \"정발산동 빵집\" (쉼표로 여러 개)")
    s.add_argument("--menu", "-m", help="대표 메뉴·서비스 쉼표로 (3개까지, '동네 메뉴'로 검색)")
    s.add_argument("--area", help="동네 (없으면 -k 첫 검색어의 앞 단어, 매장 없는 사업은 --area \"\")")
    s.add_argument("--wide", help="값이 없을 때 넓힐 시·구 이름 쉼표로 (예: 일산,고양). 그다음은 업종만")
    s.add_argument("--max", type=int, default=6, help="씨앗별 지식iN 질문 수")
    s.add_argument("--no-youtube", action="store_true", help="유튜브 자동완성 건너뛰기")

    s = p("trend", cmd_trend, "검색어 추이 비교 (데이터랩 키 있으면 데이터랩, 없으면 구글 트렌드)")
    s.add_argument("kw", nargs="?", help="검색어 쉼표로 (5개까지)")
    s.add_argument("--keyword", "-k", help="검색어 쉼표로 (5개까지)")
    s.add_argument("--google", action="store_true", help="키가 있어도 구글 트렌드로")

    s = p("season", cmd_season, "앞으로 N주 기념일·절기·시즌 (+--unofficial: 쇼핑인사이트 작년 같은 시기)")
    s.add_argument("--weeks", type=int, default=8)
    s.add_argument("--cat", default="식품", help="쇼핑인사이트 분야 쉼표로 (3개까지): " + ", ".join(SHOP_CATS))
    s.add_argument("--no-shop", action="store_true", help="쇼핑 인기 검색어 건너뛰기 (달력만)")
    s.add_argument("--date", help="기준 날짜 YYYY-MM-DD (기본 오늘)")

    s = p("festival", cmd_festival, "지역 축제 목록 (대한민국 구석구석)")
    s.add_argument("--area", required=True, help="시·도 시·군 예: \"경기 고양\" (시·군만 넣어도 자주 쓰는 곳은 찾음)")
    s.add_argument("--weeks", type=int, default=6)

    a = ap.parse_args()
    UNOFFICIAL["on"] = bool(getattr(a, "unofficial", False))
    try:
        a.fn(a)
    except Exception as e:
        print(f"오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

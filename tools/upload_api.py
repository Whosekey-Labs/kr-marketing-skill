#!/usr/bin/env python3
"""공식 API 게시 도우미 (표준 라이브러리만 사용).

대상: 유튜브(쇼츠 포함) 업로드, 인스타그램 이미지·캐러셀·릴스, 스레드, 페이스북 페이지.
안내 문서: guides/upload/index.md, guides/upload/youtube.md, guides/upload/instagram.md

기본은 시험 실행(--dry-run)이다. 보낼 요청만 출력하고 아무것도 올리지 않는다.
출력에 "DRY-RUN(실제로 안 보냄)"이 보이면 성공이 아니다. ig-refresh 같은 새로 고침도 --live 가 있어야 실제로 된다.
사장님이 최종 내용을 승인한 뒤에만 --live 를 붙여 실제로 게시한다.
유튜브 refresh token은 youtube-auth 로 받는다(인증 주소 출력 → 허용 → 코드 붙여넣기).

토큰은 인자나 환경 변수로 받는다. 출력에는 토큰을 가린다.
  YT_ACCESS_TOKEN 또는 (YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN)
  IG_ACCESS_TOKEN, IG_USER_ID, IG_HOST(기본 graph.instagram.com)
  THREADS_ACCESS_TOKEN, THREADS_USER_ID
  FB_PAGE_TOKEN, FB_PAGE_ID
  META_GRAPH_VERSION (기본 v27.0 — 2026-11 공식 문서 예시 버전. 바뀌면 현재 버전으로 바꿔 써라)

예:
  python3 upload_api.py youtube --file short.mp4 --title "단호박 크림빵 굽는 아침"      # 기본 비공개(private)
  python3 upload_api.py youtube --file short.mp4 --title "…" --privacy private --publish-at 2026-11-20T01:00:00Z
  python3 upload_api.py instagram-reel --file reel.mp4 --caption "..."   # 공개 주소 없이(이어 올리기)
  python3 upload_api.py instagram-carousel --image-url https://.../1.jpg --image-url https://.../2.jpg --caption "..."
  python3 upload_api.py threads --text "오늘 첫 판 나왔어요" --live
  python3 upload_api.py ig-refresh --live
  python3 upload_api.py youtube-auth            # 인증 주소 출력
  python3 upload_api.py youtube-auth --code 'http://localhost/?code=...'
"""

import argparse
import json
import os
import sys
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

VERSION = "0.1.0"
GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v27.0")
DRY_RUN = True  # main()에서 --live 일 때만 False


# ---------------------------------------------------------------- 공통

def _mask(value):
    if not value:
        return value
    s = str(value)
    return s[:4] + "…(가림)" if len(s) > 8 else "…(가림)"


def _masked_params(params):
    return {k: (_mask(v) if "token" in k or "secret" in k else v) for k, v in (params or {}).items()}


def _need(value, name):
    if not value:
        sys.exit(f"[오류] {name} 값이 없습니다. 인자나 환경 변수로 주세요.")
    return value


def _warn(msg):
    print(f"[주의] {msg}", file=sys.stderr)


def _request(method, url, params=None, data=None, headers=None, expect_json=True):
    """시험 실행이면 요청 내용만 출력하고 가짜 응답을 돌려준다."""
    headers = dict(headers or {})
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    if DRY_RUN:
        shown = url
        if params:
            shown = url.split("?")[0] + "?" + urllib.parse.urlencode(_masked_params(params))
        h = {k: (_mask(v) if k.lower() == "authorization" else v) for k, v in headers.items()}
        size = len(data) if isinstance(data, (bytes, bytearray)) else (len(data.encode()) if data else 0)
        print(f"[DRY-RUN(실제로 안 보냄)] {method} {shown}")
        if h:
            print(f"        헤더: {h}")
        if size:
            print(f"        본문: {size} 바이트")
        return {"id": "DRY-RUN(실제로 안 보냄)", "status_code": "DRY-RUN(실제로 안 보냄) — 아무것도 바뀌지 않음"}, {}
    if isinstance(data, str):
        data = data.encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read()
            resp_headers = dict(resp.headers)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        sys.exit(f"[실패] {method} {url.split('?')[0]} → HTTP {e.code}\n{detail}")
    if expect_json and body:
        return json.loads(body.decode("utf-8")), resp_headers
    return body, resp_headers


def _form(params):
    return urllib.parse.urlencode(params)


def _count_hashtags(text):
    return sum(1 for w in (text or "").split() if w.startswith("#"))


# ---------------------------------------------------------------- 유튜브
# 업로드: https://developers.google.com/youtube/v3/docs/videos/insert
# 재개 가능 업로드: https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol
# 쿼터(videos.insert 하루 100회): https://developers.google.com/youtube/v3/determine_quota_cost
# publishAt: https://developers.google.com/youtube/v3/docs/videos#status.publishAt
# OAuth 토큰 새로 받기: https://developers.google.com/identity/protocols/oauth2

YT_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YT_REDIRECT = "http://localhost"  # 'OAuth 클라이언트 ID' 유형: 데스크톱 앱


def youtube_auth_url(client_id):
    """사장님이 열 인증 주소. 허용 뒤 주소창이 http://localhost/?code=... 로 바뀐다(페이지는 안 열려도 정상)."""
    q = {"client_id": client_id, "redirect_uri": YT_REDIRECT, "response_type": "code",
         "scope": YT_SCOPE, "access_type": "offline", "prompt": "consent"}
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(q)


def youtube_exchange_code(client_id, client_secret, code):
    """인증 코드 → refresh token. 코드는 몇 분 안에 한 번만 쓸 수 있다."""
    if "code=" in code:  # 주소 전체를 붙여 넣은 경우
        code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query).get("code", [""])[0]
    code = urllib.parse.unquote(code.strip())
    data = _form({"client_id": client_id, "client_secret": client_secret, "code": code,
                  "grant_type": "authorization_code", "redirect_uri": YT_REDIRECT})
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data.encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            res = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"[실패] 토큰 교환 HTTP {e.code}\n{e.read().decode('utf-8', 'replace')}\n"
                 "코드는 한 번만, 몇 분 안에만 쓸 수 있다. 인증 주소를 다시 열어 새 코드를 받아라.")
    rt = res.get("refresh_token")
    if not rt:
        sys.exit("[실패] refresh_token이 오지 않았다. 인증 주소(prompt=consent 포함)를 다시 열어 허용받아라.")
    return rt


def youtube_access_token(access_token=None, client_id=None, client_secret=None, refresh_token=None):
    """access token이 있으면 그대로, 없으면 refresh token으로 새로 받는다."""
    if access_token:
        return access_token
    data = _form({
        "client_id": _need(client_id, "YT_CLIENT_ID"),
        "client_secret": _need(client_secret, "YT_CLIENT_SECRET"),
        "refresh_token": _need(refresh_token, "YT_REFRESH_TOKEN"),
        "grant_type": "refresh_token",
    })
    if DRY_RUN:
        print("[DRY-RUN(실제로 안 보냄)] POST https://oauth2.googleapis.com/token (refresh_token으로 access token 받기)")
        return "DRY-RUN-TOKEN"
    res, _ = _request("POST", "https://oauth2.googleapis.com/token", data=data,
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    return res["access_token"]


def youtube_upload(file_path, title, description="", tags=None, privacy="private",
                   publish_at=None, category_id="22", made_for_kids=False,
                   token=None, chunk_mb=8):
    """재개 가능 업로드로 영상을 올린다. 쇼츠는 3분 이하·세로/정사각 영상이면 된다."""
    if len(title) > 100:
        sys.exit("[오류] 유튜브 제목은 100자 이하여야 합니다.")
    if publish_at and privacy != "private":
        sys.exit("[오류] publishAt 예약은 privacy=private 일 때만 됩니다.")
    if not os.path.isfile(file_path):
        sys.exit(f"[오류] 파일이 없습니다: {file_path}")
    total = os.path.getsize(file_path)
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": made_for_kids}
    if publish_at:
        status["publishAt"] = publish_at
    meta = {
        "snippet": {"title": title, "description": description, "tags": tags or [], "categoryId": category_id},
        "status": status,
    }
    init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
    _, headers = _request("POST", init_url, data=json.dumps(meta, ensure_ascii=False), headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Length": str(total),
        "X-Upload-Content-Type": "video/*",
    })
    if DRY_RUN:
        print(f"        메타데이터: {json.dumps(meta, ensure_ascii=False)}")
        print(f"[DRY-RUN(실제로 안 보냄)] PUT (업로드 주소) 파일 {total} 바이트를 {chunk_mb}MB씩 나눠 보냄")
        return {"id": "DRY-RUN(실제로 안 보냄)"}
    upload_url = headers.get("Location") or headers.get("location")
    if not upload_url:
        sys.exit("[실패] 업로드 주소(Location)를 받지 못했습니다.")
    chunk = chunk_mb * 1024 * 1024
    start = 0
    with open(file_path, "rb") as f:
        while start < total:
            f.seek(start)
            piece = f.read(chunk)
            end = start + len(piece) - 1
            req = urllib.request.Request(upload_url, data=piece, method="PUT", headers={
                "Authorization": f"Bearer {token}",
                "Content-Length": str(len(piece)),
                "Content-Range": f"bytes {start}-{end}/{total}",
            })
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    return json.loads(resp.read().decode("utf-8"))  # 200/201: 끝
            except urllib.error.HTTPError as e:
                if e.code == 308:  # 아직 남음. Range 헤더로 받은 만큼 확인
                    rng = e.headers.get("Range")
                    start = int(rng.split("-")[1]) + 1 if rng else 0
                    print(f"  … {start}/{total} 바이트 올림")
                    continue
                sys.exit(f"[실패] 업로드 HTTP {e.code}\n{e.read().decode('utf-8', 'replace')}")
    sys.exit("[실패] 업로드가 끝나지 않았습니다. 다시 시도하세요.")


# ---------------------------------------------------------------- 인스타그램
# 콘텐츠 게시: https://developers.facebook.com/docs/instagram-platform/content-publishing/
#   - 미디어는 게시 시점에 공개 서버에 있어야 함, 이미지는 JPEG만, 캐러셀 최대 20개
# 게시 한도: https://developers.facebook.com/docs/instagram-platform/reference/ig-user/media_publish
# 토큰 새로 고침: https://developers.facebook.com/docs/instagram-platform/reference/refresh_access_token
#
# 공개 이미지 주소가 없을 때: 인스타 API로는 사진을 올릴 수 없다.
#   1) 에이전트가 쓸 수 있는 공개 파일 주소(로그아웃 브라우저에서 바로 열리는 https)에 JPEG를 올리거나
#   2) Meta 비즈니스 스위트(브라우저)로 간다. guides/upload/instagram.md 참고.
#
# 릴스 로컬 파일(공개 주소 없이): 이어 올리기(resumable) — 같은 콘텐츠 게시 문서의 "Resumable Upload Session",
#   IG User Media 참조 https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media
#   1) POST graph.facebook.com/<ver>/<IG_ID>/media  media_type=REELS, upload_type=resumable → {id, uri}
#   2) POST https://rupload.facebook.com/ig-api-upload/<ver>/<IG_CONTAINER_ID>
#      헤더 Authorization: OAuth <토큰>, offset: 0, file_size: <바이트>, 본문 = 파일 그대로
#   3) status_code FINISHED 확인 → media_publish
#   조건(원문): "Only for apps that have implemented Facebook Login for Business."
#   → 호스트 graph.facebook.com, 인스타가 페이스북 페이지에 연결돼 있어야 하고, 토큰도 페이스북 로그인 토큰이어야 한다.
#     graph.instagram.com(인스타그램 로그인) 토큰으로는 이 방법을 쓸 수 없다.
#   사진은 이 방법이 없다(동영상만). 사진·캐러셀 사진은 여전히 공개 주소가 필요하다.

def _ig_base(host=None):
    host = host or os.environ.get("IG_HOST", "graph.instagram.com")
    return f"https://{host}/{GRAPH_VERSION}"


def _check_image_url(url):
    if not url.lower().startswith("https://"):
        sys.exit(f"[오류] 공개 https 주소가 필요합니다: {url}")
    path = urllib.parse.urlparse(url).path.lower()
    if not path.endswith((".jpg", ".jpeg")):
        _warn(f"인스타 API는 JPEG만 받습니다. 주소가 .jpg/.jpeg로 끝나지 않아요: {url}")


def _caption_check(caption):
    if _count_hashtags(caption) > 5:
        _warn("해시태그가 5개를 넘습니다. 이 스킬은 5개 이하로 씁니다.")


def _ig_wait_finished(container_id, token, host=None, tries=20, wait=6):
    """컨테이너 상태가 FINISHED가 될 때까지 기다린다(영상은 처리 시간이 걸림)."""
    for _ in range(tries):
        res, _ = _request("GET", f"{_ig_base(host)}/{container_id}",
                          params={"fields": "status_code", "access_token": token})
        if DRY_RUN:
            return
        code = res.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            sys.exit(f"[실패] 컨테이너 상태: {code}")
        time.sleep(wait)
    sys.exit("[실패] 처리 시간이 너무 깁니다. 나중에 다시 확인하세요.")


def _ig_publish(ig_id, container_id, token, host=None):
    res, _ = _request("POST", f"{_ig_base(host)}/{ig_id}/media_publish",
                      data=_form({"creation_id": container_id, "access_token": token}),
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    return res


def instagram_image(ig_id, image_url, caption, token, host=None):
    """사진 1장 게시: 컨테이너 만들기 → 게시."""
    _check_image_url(image_url)
    _caption_check(caption)
    res, _ = _request("POST", f"{_ig_base(host)}/{ig_id}/media",
                      data=_form({"image_url": image_url, "caption": caption, "access_token": token}),
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    _ig_wait_finished(res["id"], token, host)
    return _ig_publish(ig_id, res["id"], token, host)


def instagram_carousel(ig_id, image_urls, caption, token, host=None):
    """캐러셀(카드뉴스): 장마다 자식 컨테이너 → CAROUSEL 컨테이너 → 게시."""
    if not 2 <= len(image_urls) <= 20:
        sys.exit("[오류] 캐러셀은 2~20장입니다.")
    if len(image_urls) > 10:
        _warn("10장을 넘으면 비즈니스 스위트로는 못 올립니다. 이 스킬은 10장 이하를 권합니다.")
    _caption_check(caption)
    children = []
    for url in image_urls:
        _check_image_url(url)
        res, _ = _request("POST", f"{_ig_base(host)}/{ig_id}/media",
                          data=_form({"image_url": url, "is_carousel_item": "true", "access_token": token}),
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
        children.append(res["id"])
    res, _ = _request("POST", f"{_ig_base(host)}/{ig_id}/media",
                      data=_form({"media_type": "CAROUSEL", "children": ",".join(children),
                                  "caption": caption, "access_token": token}),
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    _ig_wait_finished(res["id"], token, host)
    return _ig_publish(ig_id, res["id"], token, host)


def _ig_reel_resumable(ig_id, file_path, caption, token, host):
    """릴스 이어 올리기: 컨테이너(upload_type=resumable) → rupload로 파일 전송. 컨테이너 ID를 돌려준다."""
    if not os.path.isfile(file_path):
        sys.exit(f"[오류] 파일이 없습니다: {file_path}")
    total = os.path.getsize(file_path)
    res, _ = _request("POST", f"{_ig_base(host)}/{ig_id}/media",
                      data=_form({"media_type": "REELS", "upload_type": "resumable",
                                  "caption": caption, "access_token": token}),
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    cid = res["id"]
    uri = res.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{GRAPH_VERSION}/{cid}"
    if DRY_RUN:
        _request("POST", uri, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(total)})
        print(f"        본문: 파일 {os.path.basename(file_path)} {total} 바이트 그대로")
        return cid
    with open(file_path, "rb") as f:
        body = f.read()
    up, _ = _request("POST", uri, data=body, headers={
        "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(total)})
    if isinstance(up, dict) and up.get("success") is False:
        sys.exit(f"[실패] 영상 전송: {json.dumps(up, ensure_ascii=False)}")
    return cid


def instagram_reel(ig_id, video_url, caption, token, host=None, share_to_feed=True, file_path=None):
    """릴스: video_url(공개 주소) 또는 file_path(이어 올리기) → 처리 대기 → 게시."""
    _caption_check(caption)
    if file_path:
        host = host or "graph.facebook.com"
        if host != "graph.facebook.com":
            sys.exit("[오류] 파일로 올리기(이어 올리기)는 graph.facebook.com + 페이스북 로그인 토큰에서만 됩니다(Meta 원문: "
                     "Only for apps that have implemented Facebook Login for Business). "
                     "인스타그램 로그인 토큰이면 --video-url(공개 주소)이나 비즈니스 스위트(guides/upload/instagram.md B)로 가세요.")
        cid = _ig_reel_resumable(ig_id, file_path, caption, token, host)
        _ig_wait_finished(cid, token, host, tries=40, wait=10)
        return _ig_publish(ig_id, cid, token, host)
    if not video_url or not video_url.lower().startswith("https://"):
        sys.exit("[오류] --video-url 에는 공개 https 주소가 필요합니다. 주소가 없으면 --file 로 파일을 주세요.")
    res, _ = _request("POST", f"{_ig_base(host)}/{ig_id}/media",
                      data=_form({"media_type": "REELS", "video_url": video_url, "caption": caption,
                                  "share_to_feed": "true" if share_to_feed else "false",
                                  "access_token": token}),
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    _ig_wait_finished(res["id"], token, host, tries=40, wait=10)
    return _ig_publish(ig_id, res["id"], token, host)


def instagram_limit(ig_id, token, host=None):
    """최근 24시간 게시 수 확인(content_publishing_limit)."""
    res, _ = _request("GET", f"{_ig_base(host)}/{ig_id}/content_publishing_limit",
                      params={"fields": "quota_usage,config", "access_token": token})
    return res


def instagram_refresh(token):
    """장기 토큰(60일) 새로 고침. 발급 24시간 뒤부터, 만료 전에만 된다."""
    res, _ = _request("GET", "https://graph.instagram.com/refresh_access_token",
                      params={"grant_type": "ig_refresh_token", "access_token": token})
    return res


# ---------------------------------------------------------------- 스레드
# 게시: https://developers.facebook.com/docs/threads/posts
# 개요(테스터만 게시 가능 조건): https://developers.facebook.com/docs/threads/overview
#   - 글 500자, 캐러셀 2~20개, 이미지는 공개 주소, 24시간 250건, 예약 기능 없음

THREADS_BASE = "https://graph.threads.net/v1.0"


def threads_post(user_id, text, token, image_urls=None, made_with_ai=False):
    """글만 / 사진 1장 / 캐러셀(2~20장) 게시. 컨테이너 만들기 → threads_publish."""
    image_urls = image_urls or []
    if len(text) > 500:
        sys.exit("[오류] 스레드 글은 500자 이하입니다.")
    for url in image_urls:
        if not url.lower().startswith("https://"):
            sys.exit(f"[오류] 공개 https 주소가 필요합니다: {url}")
    form = {"Content-Type": "application/x-www-form-urlencoded"}
    extra = {"is_made_with_ai": "true"} if made_with_ai else {}
    if not image_urls:
        params = {"media_type": "TEXT", "text": text, "access_token": token, **extra}
    elif len(image_urls) == 1:
        params = {"media_type": "IMAGE", "image_url": image_urls[0], "text": text, "access_token": token, **extra}
    else:
        if len(image_urls) > 20:
            sys.exit("[오류] 스레드 캐러셀은 20장 이하입니다.")
        children = []
        for url in image_urls:
            res, _ = _request("POST", f"{THREADS_BASE}/{user_id}/threads",
                              data=_form({"media_type": "IMAGE", "image_url": url,
                                          "is_carousel_item": "true", "access_token": token}), headers=form)
            children.append(res["id"])
        params = {"media_type": "CAROUSEL", "children": ",".join(children), "text": text,
                  "access_token": token, **extra}
    res, _ = _request("POST", f"{THREADS_BASE}/{user_id}/threads", data=_form(params), headers=form)
    if not DRY_RUN:
        time.sleep(30)  # 공식 문서: 게시 전 서버 처리 시간을 두라고 권한다
    res, _ = _request("POST", f"{THREADS_BASE}/{user_id}/threads_publish",
                      data=_form({"creation_id": res["id"], "access_token": token}), headers=form)
    return res


# ---------------------------------------------------------------- 페이스북 페이지
# 페이지 게시물·예약: https://developers.facebook.com/docs/pages-api/posts
#   - published=false + scheduled_publish_time, 10분~30일
# 페이지 사진(파일 직접 첨부): https://developers.facebook.com/docs/graph-api/reference/page/photos/
# 장기 페이지 토큰: https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived

def _fb_base():
    return f"https://graph.facebook.com/{GRAPH_VERSION}"


def _schedule_ts(when):
    """ISO 시각(예: 2026-11-20T10:00:00+09:00) → 유닉스 초. 10분~30일 범위 확인."""
    dt = datetime.fromisoformat(when)
    if dt.tzinfo is None:
        sys.exit("[오류] 예약 시각에 시간대를 붙여 주세요. 예: 2026-11-20T10:00:00+09:00")
    now = datetime.now(timezone.utc)
    if not (now + timedelta(minutes=10) <= dt <= now + timedelta(days=30)):
        sys.exit("[오류] 페이지 예약은 지금부터 10분~30일 사이만 됩니다.")
    return int(dt.timestamp())


def facebook_page_post(page_id, message, token, link=None, schedule=None):
    """페이지 글(링크 선택). schedule을 주면 예약 게시."""
    _caption_check(message)
    if link:
        _warn("페이스북은 링크 없는 캡션이 성과가 좋다고 안내합니다. 링크는 댓글·프로필도 고려하세요.")
    params = {"message": message, "access_token": token}
    if link:
        params["link"] = link
    if schedule:
        params["published"] = "false"
        params["scheduled_publish_time"] = str(_schedule_ts(schedule))
    res, _ = _request("POST", f"{_fb_base()}/{page_id}/feed", data=_form(params),
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    return res


def facebook_page_photo(page_id, photo_path, caption, token):
    """페이지 사진 1장. 파일을 multipart/form-data로 직접 올린다(공개 주소 불필요)."""
    if not os.path.isfile(photo_path):
        sys.exit(f"[오류] 파일이 없습니다: {photo_path}")
    _caption_check(caption)
    boundary = uuid.uuid4().hex
    with open(photo_path, "rb") as f:
        content = f.read()
    ctype = "image/png" if photo_path.lower().endswith(".png") else "image/jpeg"
    parts = []
    for name, value in (("caption", caption), ("access_token", token)):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="source"; filename="{os.path.basename(photo_path)}"\r\n'
        f"Content-Type: {ctype}\r\n\r\n".encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    res, _ = _request("POST", f"{_fb_base()}/{page_id}/photos", data=body,
                      headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return res


# ---------------------------------------------------------------- 명령줄

def main():
    global DRY_RUN
    p = argparse.ArgumentParser(description="공식 API 게시 도우미 (기본: 시험 실행)")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        g = sp.add_mutually_exclusive_group()
        g.add_argument("--dry-run", action="store_true", default=True, help="요청만 출력(기본값)")
        g.add_argument("--live", action="store_true", help="실제로 보낸다(게시·새로 고침 모두). 없으면 아무것도 안 바뀜")
        return sp

    ya = sub.add_parser("youtube-auth", help="유튜브 refresh token 받기(처음 한 번). 실제 요청이므로 --live 없음")
    ya.add_argument("--client-id", default=os.environ.get("YT_CLIENT_ID"))
    ya.add_argument("--client-secret", default=os.environ.get("YT_CLIENT_SECRET"))
    ya.add_argument("--code", help="허용 뒤 주소창의 code= 값(또는 주소 전체). 없으면 인증 주소만 출력")

    y = common(sub.add_parser("youtube", help="유튜브 업로드(쇼츠 포함)"))
    y.add_argument("--file", required=True)
    y.add_argument("--title", required=True)
    y.add_argument("--description", default="")
    y.add_argument("--tag", action="append", default=[])
    y.add_argument("--privacy", choices=["public", "unlisted", "private"], default="private",
                   help="기본 private(비공개). 첫 업로드는 비공개로 올리고 사장님이 확인한 뒤 공개한다")
    y.add_argument("--publish-at", help="예약 시각(ISO 8601, 예: 2026-11-20T01:00:00Z). privacy=private 필요")
    y.add_argument("--token", default=os.environ.get("YT_ACCESS_TOKEN"))

    for name in ("instagram-image", "instagram-carousel", "instagram-reel", "instagram-limit", "ig-refresh"):
        sp = common(sub.add_parser(name))
        sp.add_argument("--ig-id", default=os.environ.get("IG_USER_ID"))
        sp.add_argument("--token", default=os.environ.get("IG_ACCESS_TOKEN"))
        sp.add_argument("--host", default=None, help="graph.instagram.com(기본) 또는 graph.facebook.com")
        if name in ("instagram-image", "instagram-carousel"):
            sp.add_argument("--image-url", action="append", required=True, help="공개 https JPEG 주소")
        if name == "instagram-reel":
            src = sp.add_mutually_exclusive_group(required=True)
            src.add_argument("--video-url", help="공개 https mp4 주소")
            src.add_argument("--file", help="내 컴퓨터의 mp4. 공개 주소 없이 이어 올리기(graph.facebook.com + 페이스북 로그인 토큰 필요)")
        if name not in ("instagram-limit", "ig-refresh"):
            sp.add_argument("--caption", default="")

    t = common(sub.add_parser("threads", help="스레드 게시(예약 없음)"))
    t.add_argument("--text", required=True)
    t.add_argument("--image-url", action="append", default=[])
    t.add_argument("--made-with-ai", action="store_true", help="AI 정보 레이블 붙이기")
    t.add_argument("--user-id", default=os.environ.get("THREADS_USER_ID"))
    t.add_argument("--token", default=os.environ.get("THREADS_ACCESS_TOKEN"))

    f = common(sub.add_parser("fb-post", help="페이스북 페이지 글(예약 가능)"))
    f.add_argument("--message", required=True)
    f.add_argument("--link")
    f.add_argument("--schedule", help="예약 시각(ISO, 시간대 포함). 10분~30일")
    f.add_argument("--page-id", default=os.environ.get("FB_PAGE_ID"))
    f.add_argument("--token", default=os.environ.get("FB_PAGE_TOKEN"))

    fp = common(sub.add_parser("fb-photo", help="페이스북 페이지 사진(파일 직접)"))
    fp.add_argument("--file", required=True)
    fp.add_argument("--caption", default="")
    fp.add_argument("--page-id", default=os.environ.get("FB_PAGE_ID"))
    fp.add_argument("--token", default=os.environ.get("FB_PAGE_TOKEN"))

    a = p.parse_args()
    if a.cmd == "youtube-auth":
        cid = _need(a.client_id, "YT_CLIENT_ID")
        if not a.code:
            print("1) 아래 주소를 사장님 구글 계정 브라우저에서 연다 → 허용")
            print("2) 주소창이 http://localhost/?code=... 로 바뀌면(페이지 오류는 정상) 그 주소 전체를 복사")
            print("3) python3 upload_api.py youtube-auth --code '<복사한 주소>'  (YT_CLIENT_ID·YT_CLIENT_SECRET 환경 변수 필요)\n")
            print(youtube_auth_url(cid))
            return
        rt = youtube_exchange_code(cid, _need(a.client_secret, "YT_CLIENT_SECRET"), a.code)
        print("refresh token을 받았다. 채팅·문서에 쓰지 말고 금고에 YT_REFRESH_TOKEN 이름으로 저장하라:")
        print(rt)
        return
    DRY_RUN = not a.live
    print("== DRY-RUN(실제로 안 보냄): 아무것도 올리거나 바꾸지 않습니다. 실제로 하려면 --live ==" if DRY_RUN else "== 실제 실행(--live) ==")
    tok = lambda v, n: (v or f"<{n}>") if DRY_RUN else _need(v, n)  # 시험 실행은 토큰 없이도 흐름을 보여 줌

    if a.cmd == "youtube":
        token = a.token or youtube_access_token(
            None, os.environ.get("YT_CLIENT_ID") or ("x" if DRY_RUN else None),
            os.environ.get("YT_CLIENT_SECRET") or ("x" if DRY_RUN else None),
            os.environ.get("YT_REFRESH_TOKEN") or ("x" if DRY_RUN else None))
        res = youtube_upload(a.file, a.title, a.description, a.tag, a.privacy, a.publish_at, token=token)
        if a.privacy == "private" and not a.publish_at:
            print("[안내] 비공개로 올림. 사장님이 영상을 확인한 뒤 공개로 바꾼다(guides/upload/youtube.md '첫 업로드').")
    elif a.cmd == "instagram-image":
        res = instagram_image(tok(a.ig_id, "IG_USER_ID"), a.image_url[0], a.caption, tok(a.token, "IG_ACCESS_TOKEN"), a.host)
    elif a.cmd == "instagram-carousel":
        res = instagram_carousel(tok(a.ig_id, "IG_USER_ID"), a.image_url, a.caption, tok(a.token, "IG_ACCESS_TOKEN"), a.host)
    elif a.cmd == "instagram-reel":
        res = instagram_reel(tok(a.ig_id, "IG_USER_ID"), a.video_url, a.caption, tok(a.token, "IG_ACCESS_TOKEN"), a.host,
                             file_path=a.file)
    elif a.cmd == "instagram-limit":
        res = instagram_limit(tok(a.ig_id, "IG_USER_ID"), tok(a.token, "IG_ACCESS_TOKEN"), a.host)
    elif a.cmd == "ig-refresh":
        res = instagram_refresh(tok(a.token, "IG_ACCESS_TOKEN"))
    elif a.cmd == "threads":
        res = threads_post(tok(a.user_id, "THREADS_USER_ID"), a.text, tok(a.token, "THREADS_ACCESS_TOKEN"),
                           a.image_url, a.made_with_ai)
    elif a.cmd == "fb-post":
        res = facebook_page_post(tok(a.page_id, "FB_PAGE_ID"), a.message, tok(a.token, "FB_PAGE_TOKEN"), a.link, a.schedule)
    elif a.cmd == "fb-photo":
        res = facebook_page_photo(tok(a.page_id, "FB_PAGE_ID"), a.file, a.caption, tok(a.token, "FB_PAGE_TOKEN"))
    else:
        p.error("알 수 없는 명령")
        return
    if isinstance(res, dict) and "access_token" in res:
        res = dict(res, access_token=_mask(res["access_token"]))
    print(json.dumps(res, ensure_ascii=False))
    if DRY_RUN:
        print("== DRY-RUN 끝: 실제로는 아무것도 보내지 않았습니다(성공 아님). ==")


if __name__ == "__main__":
    main()

"""mk.py 단위 테스트 — 네트워크 없이 돈다. 실행: python3 -m unittest tests/test_mk.py"""
import datetime as dt
import importlib.util
import json
import os
import pathlib
import struct
import tempfile
import unittest
import zlib

spec = importlib.util.spec_from_file_location("mk", pathlib.Path(__file__).parent.parent / "tools" / "mk.py")
mk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mk)


# 2026-11 네이버 블로그 탭 검색 결과 구조를 줄인 것
BLOG_ITEM = ('<a nocr="1" class="x" href="https://blog.naver.com/{bid}" target="_blank" '
             'data-heatmap-target="articleSourceJSX_title"><span class="sds-comps-text sds-comps-text-ellipsis '
             'sds-comps-text-ellipsis-1">{bname}</span></a></span></div><div><span class="sds-comps-text '
             'sds-comps-profile-info-subtext">{date}</span></div>'
             '<a nocr="1" class="y" href="https://blog.naver.com/{bid}/{no}" target="_blank" '
             'data-heatmap-target=".nblg"><span class="sds-comps-text sds-comps-text-ellipsis '
             'sds-comps-text-type-headline1 sds-comps-text-weight-sm">{title}</span></a>'
             '<a nocr="1" class="z" href="https://blog.naver.com/{bid}/{no}" data-heatmap-target=".nblg">'
             '<span class="sds-comps-text sds-comps-text-type-body1 sds-comps-text-weight-sm">{snip}</span></a>')


def blog_page(*items):
    return "<html>" + "".join(BLOG_ITEM.format(**i) for i in items) + "</html>"


class BlogSearchTest(unittest.TestCase):
    def test_parse(self):
        page = blog_page(
            dict(bid="guest1", no="224000000001", bname="먹방일기", date="1주 전",
                 title="<mark>망원동</mark> 카페 내돈내산 후기", snip="친구랑 다녀왔어요"),
            dict(bid="shop_official", no="224000000002", bname="달빛카페 공식 블로그", date="2026.10.05.",
                 title="11월 휴무 안내", snip="정기 휴무 안내드립니다"),
            dict(bid="ad1", no="224000000003", bname="리뷰왕", date="3일 전",
                 title="망원 디저트 맛집", snip="업체로부터 제품을 제공받아 작성했습니다"))
        items = mk.parse_blog_search(page, store="달빛카페")
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["title"], "망원동 카페 내돈내산 후기")
        self.assertEqual(items[0]["blog"], "먹방일기")
        self.assertEqual(items[0]["date"], "1주 전")
        self.assertEqual(items[0]["url"], "https://blog.naver.com/guest1/224000000001")
        self.assertEqual(items[0]["kind"], "손님 후기 추정")
        self.assertEqual(items[1]["kind"], "사장님 추정")
        self.assertEqual(items[2]["kind"], "체험단·협찬 추정")

    def test_guess_kind(self):
        self.assertEqual(mk.guess_kind("성수 빵집 방문 후기", "저희가 갔을 때 웨이팅"), "손님 후기 추정")
        self.assertEqual(mk.guess_kind("오늘의 빵", "안녕하세요 저희 가게는 매일 아침 굽습니다"), "사장님 추정")
        self.assertEqual(mk.guess_kind("아무 제목", ""), "기타")

    def test_fallback_when_layout_changes(self):
        items = mk.parse_blog_search('<a href="https://blog.naver.com/abc/223456789012">x</a>')
        self.assertEqual(items[0]["kind"], "확인 필요")
        self.assertEqual(items[0]["blog_id"], "abc")


POST = """<meta property="og:title" content="후후 빵집 후기"/>
<p class="blog_date"><span class="txt">2026. 11. 10. 16:01</span></p>
<div class="se-main-container">
<div class="se-component se-documentTitle se-l-default" id="a"><p class="se-text-paragraph">제목</p></div>
<div class="se-component se-quotation se-l-default" id="b"><blockquote><p class="se-text-paragraph"><b>메뉴 추천</b></p></blockquote></div>
<div class="se-component se-text se-l-default" id="c"><p class="se-text-paragraph"><span>크로와상이 맛있어요&nbsp;정말</span></p>
<p class="se-text-paragraph"><span>&#8203;</span></p><p class="se-text-paragraph">#성수빵집 #크로와상</p></div>
<div class="se-component se-image se-l-default"><img class="se-image-resource" src="a.jpg"></div>
<div class="se-component se-imageStrip se-l-default"><img class="se-image-resource" src="b.jpg"><img class="se-image-resource" src="c.jpg"></div>
<div class="se-component se-placesMap se-l-default"><img src="map.png"></div>
</div>
<div class="comment_area"><p class="se-text-paragraph">댓글은 세지 않음</p></div>"""


class ReadBlogTest(unittest.TestCase):
    def test_parse_post(self):
        p = mk.parse_post(POST)
        self.assertEqual(p["title"], "후후 빵집 후기")
        self.assertEqual(p["date"], "2026. 11. 10. 16:01")
        self.assertEqual(p["photos"], 3)
        self.assertTrue(p["map"])
        self.assertEqual(p["headings"], ["메뉴 추천"])
        self.assertIn("크로와상이 맛있어요 정말", p["body"])
        self.assertNotIn("댓글", p["body"])
        self.assertEqual(p["hashtags"], ["성수빵집", "크로와상"])
        self.assertFalse(p["sponsored"])

    def test_blog_ids(self):
        self.assertEqual(mk.blog_ids("https://blog.naver.com/abc_1/224471773435"), ("abc_1", "224471773435"))
        self.assertEqual(mk.blog_ids("https://m.blog.naver.com/PostView.naver?blogId=abc&logNo=123456789"),
                         ("abc", "123456789"))
        with self.assertRaises(RuntimeError):
            mk.blog_ids("https://example.com/abc/224471773435")


RSS = """<rss><channel><title><![CDATA[달빛카페]]></title>
<item><title><![CDATA[새 메뉴]]></title><link><![CDATA[https://blog.naver.com/x/3?fromRss=true]]></link>
<guid>https://blog.naver.com/x/3</guid><pubDate>Mon, 16 Nov 2026 10:00:00 +0900</pubDate></item>
<item><title><![CDATA[휴무 안내]]></title><guid>https://blog.naver.com/x/2</guid><pubDate>Thu, 12 Nov 2026 10:00:00 +0900</pubDate></item>
<item><title><![CDATA[오픈]]></title><guid>https://blog.naver.com/x/1</guid><pubDate>Fri, 01 Aug 2025 10:00:00 +0900</pubDate></item>
</channel></rss>"""


class RssTest(unittest.TestCase):
    def test_freq(self):
        now = dt.datetime(2026, 11, 17, tzinfo=dt.timezone.utc)
        r = mk.parse_rss(RSS, now)
        self.assertEqual(r["blog"], "달빛카페")
        self.assertEqual(r["total_in_rss"], 3)
        self.assertEqual(r["last_30d"], 2)
        self.assertEqual(r["posts"][0]["url"], "https://blog.naver.com/x/3")
        self.assertEqual(r["median_gap_days"], 4.0)       # 오래된 글(2025-08)은 간격 계산에서 빠진다
        self.assertEqual(r["days_since_last"], 0)


def apollo(o):
    return "<script>window.__APOLLO_STATE__ = " + json.dumps(o, ensure_ascii=False) + ";</script>"


class PlaceTest(unittest.TestCase):
    def test_detail(self):
        o = {"PlaceDetailBase:1": {"id": "1", "name": "달빛카페", "category": "카페", "roadAddress": "서울 마포구 1",
                                   "visitorReviewsTotal": 120, "cafeBlogReviewsTotal": 30, "visitorReviewsScore": 4.5,
                                   "reviewSettings": {"showVisitorReviewScore": True}, "talktalkUrl": None,
                                   "missingInfo": {"isBizHourMissing": True, "isDescriptionMissing": False}},
             "VisitorReview:a": {"body": "커피가\n맛있어요", "visitedDate": "2026.11.01.", "reply": {"body": "감사합니다"}},
             "VisitorReview:b": {"body": "좋아요", "visitedDate": "2026.11.05.", "reply": {"body": None}},
             "ROOT_QUERY": {"placeDetail({})": {"naverBooking": {"naverBookingUrl": "https://booking"},
                                                "description": "소개", "homepages": {"repr": {"type": "인스타그램",
                                                                                           "url": "https://instagram.com/x"}}}}}
        d = mk.parse_place_detail(mk.apollo_states(apollo(o)))
        self.assertEqual(d["name"], "달빛카페")
        self.assertEqual(d["rating"], 4.5)
        self.assertTrue(d["booking"])
        self.assertEqual(d["missing"], ["영업시간"])
        self.assertEqual(d["owner_reply"], "1/2")
        self.assertEqual(d["recent_reviews"][0]["date"], "2026.11.05.")      # 최근 순
        self.assertEqual(d["recent_reviews"][1]["body"], "커피가 맛있어요")
        self.assertIn("인스타그램:https://instagram.com/x", d["links"])

    def test_hidden_rating(self):
        o = {"PlaceDetailBase:1": {"id": "1", "name": "A", "visitorReviewsScore": 4.9,
                                   "reviewSettings": {"showVisitorReviewScore": False}}}
        self.assertIsNone(mk.parse_place_detail([o])["rating"])

    def test_list_and_rank(self):
        o = {"PlaceListBusinessesItem:1:1": {"id": "1", "name": "하츠베이커리 성수점", "category": "베이커리",
                                             "visitorReviewCount": "1,440", "hasBooking": True},
             "PlaceListBusinessesItem:2:2": {"id": "2", "name": "달빛 카페", "visitorReviewCount": "12"},
             "RestaurantAdSummary:9:9": {"name": "광고집"},
             "ROOT_QUERY": {"placeList({})": {"businesses": {"items": [{"__ref": "PlaceListBusinessesItem:1:1"},
                                                                        {"__ref": "PlaceListBusinessesItem:2:2"}]}}}}
        st = mk.apollo_states(apollo(o))
        items = mk.parse_place_list(st)
        self.assertEqual([x["rank"] for x in items], [1, 2])
        self.assertEqual(items[0]["visitor_reviews"], 1440)
        self.assertEqual(mk.place_ads(st), ["광고집"])
        self.assertEqual(mk.find_rank([x["name"] for x in items], "달빛카페"), [2])
        self.assertEqual(mk.find_rank([x["name"] for x in items], "없는가게"), [])


class ContrastTest(unittest.TestCase):
    def test_ratio(self):
        self.assertEqual(mk.contrast_ratio((0, 0, 0), (255, 255, 255)), 21.0)
        self.assertEqual(mk.contrast_ratio(mk.hex_to_rgb("#777"), mk.hex_to_rgb("#FFFFFF")), 4.48)
        self.assertEqual(mk.contrast_ratio((10, 20, 30), (10, 20, 30)), 1.0)

    def test_verdict(self):
        self.assertIn("본문 글씨 OK", mk.contrast_verdict(4.6))
        self.assertIn("큰 글씨", mk.contrast_verdict(3.2))
        self.assertIn("부족", mk.contrast_verdict(2))

    def test_hex(self):
        self.assertEqual(mk.hex_to_rgb("fa0"), (255, 170, 0))
        self.assertEqual(mk.rgb_to_hex((255, 170, 0)), "#FFAA00")
        with self.assertRaises(RuntimeError):
            mk.hex_to_rgb("#12345G")


def write_png(path, w, h, fn, ctype=6):
    bpp = 4 if ctype == 6 else 3
    rows = []
    for y in range(h):
        rows.append(b"\x00" + bytes(v for x in range(w) for v in fn(x, y)[:bpp]))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0))
                + ch(b"IDAT", zlib.compress(b"".join(rows))) + ch(b"IEND", b""))


class ColorsTest(unittest.TestCase):
    def test_png_dominant(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "logo.png")
            # 왼쪽 3/4 주황, 오른쪽 1/4 흰색, 맨 위 줄은 투명 (빼고 센다)
            write_png(p, 40, 20, lambda x, y: (0, 0, 0, 0) if y == 0 else
                      ((230, 90, 30, 255) if x < 30 else (255, 255, 255, 255)))
            w, h, px = mk.read_png(p)
            self.assertEqual((w, h), (40, 20))
            self.assertEqual(len(px), 40 * 19)
            cols = mk.dominant_colors(px, 3)
            self.assertEqual(mk.rgb_to_hex(cols[0][0]), "#E65A1E")
            self.assertEqual(cols[0][1], 75.0)
            self.assertEqual(mk.rgb_to_hex(cols[1][0]), "#FFFFFF")

    def test_rgb_png_with_filters(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "g.png")
            write_png(p, 8, 8, lambda x, y: (x * 30, y * 30, 100), ctype=2)
            _, _, px = mk.read_png(p)
            self.assertEqual(px[9], (30, 30, 100))


class CountTest(unittest.TestCase):
    def test_count(self):
        t = "# 제목\n\n오늘 [사진1] 빵 굽는 날\n\n![a](b.jpg)\n둘째 문단\n"
        c = mk.count_text(t)
        self.assertEqual(c["photo_marks"], 2)
        self.assertEqual(c["paragraphs"], 3)
        self.assertEqual(c["headings"], 1)
        self.assertEqual(c["chars_no_space"], len("#제목오늘빵굽는날둘째문단"))

    def test_korean_spaces(self):
        c = mk.count_text("가 나\n다")
        self.assertEqual((c["chars"], c["chars_no_space"]), (5, 3))


class SimilarPlaceTest(unittest.TestCase):
    def test_not_found_shows_similar_names(self):
        calls = []
        def fake(q):
            calls.append(q)
            if q == "후후베이크 성수":
                return None, [], []
            return None, [dict(name=f"후후베이크 {i}호점", address=f"서울 {g}구 {g}동 1-{i}") for i, g in
                          enumerate(["마포", "강남", "중", "종로"], 1)], []
        orig = mk.place_search
        mk.place_search = fake
        try:
            with self.assertRaises(RuntimeError) as cm:
                mk.cmd_place(type("A", (), dict(name="후후베이크 성수", q=None, json=False))())
        finally:
            mk.place_search = orig
        msg = str(cm.exception)
        self.assertEqual(calls, ["후후베이크 성수", "후후베이크"])
        self.assertIn("비슷한 이름 결과 4건(다른 지역 포함)", msg)
        self.assertIn("후후베이크 1호점(서울 마포구 마포동)", msg)
        self.assertNotIn("4호점", msg)

    def test_single_word_no_retry(self):
        self.assertEqual(mk.similar_places("후후베이크"), "")


class LintTest(unittest.TestCase):
    TEXT = "국내산 한우로 만든 최고의 맛!\n100% 효과 보장\n"

    def test_flags_dict(self):
        rules = mk.load_rules_obj({"flags": {
            "common": [{"words": ["최고의", "100% 효과"], "reason": "최상급", "fix": "사실로", "law": "표시광고법"}],
            "food-origin": [{"regex": r"국내산\s*\S+", "reason": "원산지 근거"}]}})
        hits = mk.lint_text(self.TEXT, rules, ["common", "food-origin"])
        self.assertEqual([(h["line"], h["found"]) for h in hits],
                         [(1, "최고의"), (1, "국내산 한우로"), (2, "100% 효과")])
        self.assertEqual(hits[0]["law"], "표시광고법")
        self.assertEqual(mk.lint_text(self.TEXT, rules, ["common"])[0]["flag"], "common")

    def test_list_shape_and_bad_regex(self):
        rules = mk.load_rules_obj([{"flag": "common", "pattern": "최고"},
                                   {"flags": ["common", "cosmetics"], "regex": "(", "reason": "깨진 정규식은 건너뜀"}])
        self.assertEqual(sorted(rules), ["common", "cosmetics"])
        self.assertEqual(len(mk.lint_text(self.TEXT, rules, ["common"])), 1)

    def test_plain_word_is_literal(self):
        rules = mk.load_rules_obj({"common": ["100%"]})
        self.assertEqual(len(mk.lint_text("100% 만족", rules, ["common"])), 1)
        self.assertEqual(len(mk.lint_text("1000 만족", rules, ["common"])), 0)

    def test_short_english_needs_word_boundary(self):
        rules = mk.load_rules_obj({"common": [{"regex": r"(#|\b)(AD|PR)\b"}, {"words": ["ad", "DM"]}]})
        found = lambda t: [h["found"] for h in mk.lint_text(t, rules, ["common"])]
        self.assertEqual(found("compliance/ad-messaging.md 참고"), [])
        self.assertEqual(found("loaded, DMZ, pr_team"), [])
        self.assertIn("#AD", found("#AD 협찬"))
        self.assertIn("ad", [f.lower() for f in found("이건 ad 표시")])
        self.assertEqual(found("가격은 DM으로"), ["DM"])

    def test_real_rules_file_if_present(self):
        p = pathlib.Path(__file__).parent.parent / "tools" / "rules.json"
        if not p.exists():
            self.skipTest("tools/rules.json 아직 없음")
        rules = mk.load_rules(str(p))
        self.assertTrue(rules)
        for fl, rs in rules.items():
            for r in rs:
                self.assertTrue(mk._rule_patterns(r), f"{fl}: 패턴 없는 규칙 {r}")


class UrlCheckTest(unittest.TestCase):
    def test_allows_naver(self):
        mk.check_url("https://search.naver.com/search.naver?query=x")
        mk.check_url("https://rss.blog.naver.com/abc.xml")

    def test_rejects(self):
        for u in ("http://search.naver.com/", "https://evil.com/", "https://search.naver.com.evil.com/",
                  "https://naver.com/", "file:///etc/passwd", "https://user@blog.naver.com/x",
                  "https://blog.naver.com:8080/x", "https://127.0.0.1/"):
            with self.assertRaises(RuntimeError, msg=u):
                mk.check_url(u)


# ---------------------------------------------------------------- 콘텐츠 발굴 (응답 모양은 2026-11-17 실제 응답을 줄인 것)

class DiscoveryParseTest(unittest.TestCase):
    def test_naver_ac(self):
        body = '{"query":["일산 소금빵"],"items":[[["일산 소금빵"],["일산 소금빵 맛집"],["일산 소금빵 성지"]]]}'
        self.assertEqual(mk.parse_naver_ac(body), ["일산 소금빵", "일산 소금빵 맛집", "일산 소금빵 성지"])
        self.assertEqual(mk.parse_naver_ac('{"items":[[]]}'), [])

    def test_qra(self):
        page = 'x,"apiURL":"https://s.search.naver.com/p/qra/1/search.naver?a=1\\u0026q=%EC%9D%BC",y'
        self.assertEqual(mk.find_qra_url(page), "https://s.search.naver.com/p/qra/1/search.naver?a=1&q=%EC%9D%BC")
        self.assertIsNone(mk.find_qra_url("<html></html>"))
        body = json.dumps({"result": {"contents": [
            {"query": "일산 빵집 맛집", "badge": {"type": "global", "text": "많이 찾는"}},
            {"query": "일산 레이크빵집"}, {"title": "query 없음"}]}}, ensure_ascii=False)
        self.assertEqual(mk.parse_qra(body), [dict(query="일산 빵집 맛집", badge="많이 찾는"),
                                              dict(query="일산 레이크빵집", badge="")])

    def test_kin_recent_only(self):
        li = ('<dl><dt><a href="https://kin.naver.com/qna/detail.naver?dirId=1&amp;docId={d}&amp;qb=7KCV" class="_x">'
              '<b>정발산</b> {t}</a></dt><dd class="txt_inline">{date}</dd><dd>요약</dd></dl>')
        page = "<ul>" + li.format(d=1, t="글루텐프리 카페 추천", date="2026.01.15.") \
            + li.format(d=2, t="옛날 질문", date="2008.10.16.") + "</ul>"
        items, old = mk.parse_kin(page, dt.date(2026, 11, 17))
        self.assertEqual(old, 1)
        self.assertEqual(items, [dict(title="정발산 글루텐프리 카페 추천", date="2026-01-15",
                                      url="https://kin.naver.com/qna/detail.naver?dirId=1&docId=1")])

    def test_google_suggest_and_gt(self):
        self.assertEqual(mk.parse_google_suggest('["일산 빵집",["일산 빵집 추천","일산 빵집 브이로그"]]'),
                         ["일산 빵집 추천", "일산 빵집 브이로그"])
        self.assertEqual(mk.parse_gt_json(')]}\',\n{"default":{"x":1}}'), {"default": {"x": 1}})

    def test_trend_direction(self):
        self.assertTrue(mk.trend_direction([10] * 28 + [20] * 28).startswith("오름"))
        self.assertTrue(mk.trend_direction([20] * 28 + [10] * 28).startswith("내림"))
        self.assertTrue(mk.trend_direction([10] * 8).startswith("보합"))
        self.assertEqual(mk.trend_direction([0] * 50 + [2] * 6), "검색 적음(판단 보류)")
        self.assertEqual(mk.trend_direction([1, 2]), "판단 불가(자료 부족)")
        self.assertEqual(mk.trend_direction([0] * 40 + [0, 100] * 8), "검색 드묾(판단 보류)")

    def test_shop_rank(self):
        body = '{"range":"2026.11.10. ~ 2026.11.16.","ranks":[{"rank":1,"keyword":"수능선물"},{"rank":2,"keyword":"빼빼로"}]}'
        self.assertEqual(mk.parse_shop_rank(body), ["수능선물", "빼빼로"])

    def test_festivals(self):
        body = json.dumps({"totalCnt": 3, "resultList": [
            dict(cntntsNm="운정호수공원 불꽃축제", fstvlBgngDe="2026.10.31", fstvlEndDe="2026.12.31", areaNm="경기도 파주시",
                 dtadr="운정호수공원 일대", fstvlUtztFareInfo="무료\t"),
            dict(cntntsNm="고양도시농업축제", fstvlBgngDe="2026.10.31", fstvlEndDe="2026.11.01", areaNm="경기도 고양시"),
            dict(cntntsNm="고양 겨울축제", fstvlBgngDe="2026.12.05", fstvlEndDe="2026.12.06", areaNm="경기도 고양시")]},
            ensure_ascii=False)
        items, total = mk.parse_festivals(body)
        self.assertEqual(total, 3)
        self.assertEqual(items[0]["fee"], "무료")
        today = dt.date(2026, 11, 17)
        self.assertEqual([x["name"] for x in mk.filter_festivals(items, ["고양"], today, 6)], ["고양 겨울축제"])
        self.assertEqual([x["name"] for x in mk.filter_festivals(items, [], today, 6)],
                         ["운정호수공원 불꽃축제", "고양 겨울축제"])
        self.assertEqual(mk.filter_festivals(items, ["고양"], today, 2), [])

    def test_festival_area(self):
        self.assertEqual(mk.festival_area("경기 고양"), ("31", ["고양"]))
        self.assertEqual(mk.festival_area("경기도 고양시"), ("31", ["고양시"]))
        self.assertEqual(mk.festival_area("충청남도 천안"), ("34", ["천안"]))
        self.assertEqual(mk.festival_area("일산")[0], "31")
        self.assertEqual(mk.festival_area("서울 성수")[0], "1")
        with self.assertRaises(RuntimeError):
            mk.festival_area("어딘가")

    def test_seeds(self):
        self.assertEqual(mk.ideas_seeds("정발산동 빵집", ["소금빵"], None), ["정발산동 빵집", "정발산동 소금빵"])
        self.assertEqual(mk.ideas_seeds("정발산동 빵집,일산 빵집", ["소금빵"], "일산"),
                         ["정발산동 빵집", "일산 빵집", "일산 소금빵"])
        self.assertEqual(mk.ideas_seeds("소상공인 AI", ["카톡 자동응답"], ""), ["소상공인 AI", "카톡 자동응답"])


class SeasonTest(unittest.TestCase):
    def test_boknal_known_years(self):
        # 실제 발표값: 2024 초복 7/15·중복 7/25·말복 8/14, 2025 7/20·7/30·8/9
        self.assertEqual([d.isoformat() for d, _ in mk.boknal(2024)], ["2024-07-15", "2024-07-25", "2024-08-14"])
        self.assertEqual([d.isoformat() for d, _ in mk.boknal(2025)], ["2025-07-20", "2025-07-30", "2025-08-09"])

    def test_window(self):
        ev = mk.season_events(dt.date(2026, 11, 17), 6)
        names = [e["name"] for e in ev]
        self.assertIn("수능", names)
        self.assertIn("크리스마스", names)
        self.assertIn("김장철", names)                 # 진행 중인 시즌도 나온다
        self.assertNotIn("빼빼로데이·가래떡데이", names)  # 지난 날은 빠진다
        self.assertEqual(ev[0]["d"] <= ev[-1]["d"], True)
        bf = [e for e in ev if e["name"] == "블랙프라이데이"][0]
        self.assertEqual(bf["date"], "2026-11-27")

    def test_unknown_year_warns(self):
        ev = mk.season_events(dt.date(2028, 1, 10), 6)
        self.assertTrue(any(e["kind"] == "안내" for e in ev))


class DiscoveryUrlTest(unittest.TestCase):
    def test_new_hosts(self):
        for u in ("https://ac.search.naver.com/nx/ac?q=x", "https://s.search.naver.com/p/qra/1/search.naver",
                  "https://kin.naver.com/search/list.naver?query=x",
                  "https://datalab.naver.com/shoppingInsight/getCategoryKeywordRank.naver",
                  "https://trends.google.com/trends/api/explore", "https://suggestqueries.google.com/complete/search",
                  "https://korean.visitkorea.or.kr/kfes/list/selectWntyFstvlList.do"):
            mk.check_url(u)
        for u in ("https://google.com/", "https://visitkorea.or.kr.evil.com/", "http://kin.naver.com/"):
            with self.assertRaises(RuntimeError, msg=u):
                mk.check_url(u)


class OfficialFirstTest(unittest.TestCase):
    """10b 4장: 네이버 검색 화면은 --unofficial 없이는 열지 않는다."""
    def test_gate(self):
        mk.UNOFFICIAL["on"] = False
        for u in ("https://search.naver.com/search.naver?query=x", "https://ac.search.naver.com/nx/ac?q=x",
                  "https://kin.naver.com/search/list.naver?query=x", "https://m.blog.naver.com/a/123456789",
                  "https://datalab.naver.com/shoppingInsight/getCategoryKeywordRank.naver"):
            with self.assertRaisesRegex(RuntimeError, "기본으로 꺼", msg=u):
                mk.fetch(u)

    def test_api_blog(self):
        items = [dict(title="<b>일산</b> 소금빵 후기", link="https://blog.naver.com/abc_1/224471871253",
                      description="주말 방문 솔직 후기", bloggername="류구리", bloggerlink="blog.naver.com/abc_1",
                      postdate="20261110")]
        r = mk.parse_api_blog(items)
        self.assertEqual(r[0]["title"], "일산 소금빵 후기")
        self.assertEqual(r[0]["blog_id"], "abc_1")
        self.assertEqual(r[0]["date"], "2026-11-10")
        self.assertEqual(r[0]["kind"], "손님 후기 추정")

    def test_api_local_and_kin(self):
        loc = mk.parse_api_local([dict(title="<b>밀</b>과결", category="음식점>제과,베이커리", roadAddress="경기 고양시 …",
                                       link="", telephone="")])
        self.assertEqual((loc[0]["name"], loc[0]["id"]), ("밀과결", None))
        self.assertIn("API에 없어요", mk.fmt_list(loc))
        kin = mk.parse_api_kin([dict(title="<b>소금빵</b> 보관", link="https://kin.naver.com/qna/detail.naver?d=1")])
        self.assertEqual(kin, [dict(title="소금빵 보관", date="", url="https://kin.naver.com/qna/detail.naver?d=1")])

    def test_widen(self):
        self.assertEqual(mk.widen_levels("정발산동 빵집", ["일산"]),
                         [("동네", "정발산동 빵집"), ("시·구", "일산 빵집"), ("업종만", "빵집")])
        self.assertEqual(mk.widen_levels("빵집", ["일산"]), [("그대로", "빵집")])

    def test_shop_window(self):
        fs, fe = mk.shop_window(dt.date(2026, 11, 17))
        self.assertEqual((fs.isoformat(), fe.isoformat()), ("2025-12-01", "2025-12-29"))


class ReviewFixTest(unittest.TestCase):
    """독립 검수 P1·P2 반영 확인."""
    def test_related_index_single(self):
        self.assertEqual(mk.related_index("RELATED_QUERIES"), 0)      # 키워드 1개일 때
        self.assertEqual(mk.related_index("RELATED_QUERIES_3"), 3)

    def test_redirect_gate(self):
        import urllib.request
        mk.UNOFFICIAL["on"] = False
        req = urllib.request.Request("https://rss.blog.naver.com/x.xml")
        with self.assertRaisesRegex(RuntimeError, "기본으로 꺼"):
            mk._SafeRedirect().redirect_request(req, None, 302, "", {}, "https://m.blog.naver.com/x")

    def test_festival_alias(self):
        self.assertEqual(mk.festival_area("경기 일산"), ("31", ["고양"]))
        self.assertEqual(mk.festival_area("경기도 분당"), ("31", ["성남"]))

    def test_daeboreum_2027(self):
        ev = mk.season_events(dt.date(2027, 2, 1), 4)
        self.assertIn(("2027-02-21", "정월대보름"), [(e["date"], e["name"]) for e in ev])

    def test_ideas_no_widen_and_cap(self):
        calls = []
        orig = (mk.google_ac, mk.youtube_ac, mk.searchad_volume, mk.naver_ac, mk.naver_related, mk.kin_questions)
        mk.google_ac = lambda q: calls.append(q) or []
        mk.youtube_ac = lambda q: []
        mk.searchad_volume = lambda k: []
        mk.naver_ac = lambda q: []
        mk.naver_related = lambda q: []
        mk.kin_questions = lambda q, t: ([], 0)
        try:
            import argparse, contextlib, io
            a = argparse.Namespace(keyword="소상공인 AI", kw=None, menu="카톡 자동응답", area="", wide="일산",
                                   max=3, no_youtube=True, json=True)
            mk.UNOFFICIAL["on"] = False
            with contextlib.redirect_stdout(io.StringIO()):
                mk.cmd_ideas(a)
            self.assertEqual(calls, ["소상공인 AI", "카톡 자동응답"])     # 넓히지 않음
            calls.clear()
            a = argparse.Namespace(keyword="정발산동 빵집", kw=None, menu="소금빵,크루아상,깜파뉴", area=None, wide="",
                                   max=3, no_youtube=True, json=False)
            mk.UNOFFICIAL["on"] = True
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                mk.cmd_ideas(a)
            self.assertIn("앞 2개만", buf.getvalue())
        finally:
            mk.UNOFFICIAL["on"] = False
            (mk.google_ac, mk.youtube_ac, mk.searchad_volume, mk.naver_ac, mk.naver_related, mk.kin_questions) = orig


class Review2Test(unittest.TestCase):
    """2차 검수 반영 확인."""
    def test_split_same_basis(self):
        self.assertEqual(mk.widen_levels("서울 마포 빵집", ["마포"]),
                         [("동네", "서울 마포 빵집"), ("시·구", "마포 빵집"), ("업종만", "빵집")])
        self.assertEqual(mk.ideas_seeds("서울 마포 빵집", ["소금빵"], None), ["서울 마포 빵집", "서울 마포 소금빵"])

    def test_ideas_empty(self):
        import argparse
        a = argparse.Namespace(keyword=" , ", kw=None, menu=None, area=None, wide="", max=3, no_youtube=True, json=True)
        with self.assertRaisesRegex(RuntimeError, "비었어요"):
            mk.cmd_ideas(a)

    def test_rank_refuses_once_without_key(self):
        import argparse
        mk.UNOFFICIAL["on"] = False
        old = os.environ.pop("NAVER_CLIENT_ID", None)
        try:
            a = argparse.Namespace(keyword="일산 빵집,일산 소금빵", kw=None, name="밀과결", blog_id=None, log=None, json=False)
            with self.assertRaisesRegex(RuntimeError, "기본으로 꺼"):
                mk.cmd_rank(a)
        finally:
            if old is not None:
                os.environ["NAVER_CLIENT_ID"] = old

    def test_suneung_unknown_year_warns(self):
        ev = mk.season_events(dt.date(2027, 10, 20), 8)
        self.assertTrue(any("2027년 수능" in e["name"] for e in ev))
        ev = mk.season_events(dt.date(2026, 11, 1), 4)
        self.assertFalse(any("수능 날짜가 표에 없어요" in e["name"] for e in ev))


if __name__ == "__main__":
    unittest.main()

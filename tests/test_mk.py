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


if __name__ == "__main__":
    unittest.main()

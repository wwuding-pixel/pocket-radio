"""口袋电台 电台列表构建脚本
来源：Radio Browser（中港澳台 + 全球华语）、蜻蜓FM公开频道接口（各省地方台、网络台、主播台）
步骤：抓取 -> 归类 -> 逐个测速（开播时间 + 下载速度） -> 去重（同一路流 / 同名台只留最快的） -> 写 stations.json
用法：python -I build_stations.py stations.json
"""
import json, re, sys, ssl, time, urllib.request, urllib.parse, concurrent.futures as cf
from collections import Counter

OUT = sys.argv[1]
UA = {"User-Agent": "PocketRadio/1.1"}
RB = "https://de1.api.radio-browser.info/json/"
CTX = ssl.create_default_context()
MAX_START = 3.0      # 开播超过 3 秒算慢
MIN_RATIO = 1.0      # 下载速度至少等于码率（实时）
TEST_SECS = 3.0

def get(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.load(r)

PROV = {
 "北京":["beijing","peking","北京"],"天津":["tianjin","tientsin","天津"],"上海":["shanghai","上海"],"重庆":["chongqing","chungking","重庆"],
 "河北":["hebei","hopei","河北","石家庄","唐山","保定","邯郸"],"山西":["shanxi","shansi","山西","太原"],"内蒙古":["inner mongolia","nei mongol","内蒙古","呼和浩特","包头"],
 "辽宁":["liaoning","辽宁","沈阳","大连","dalian"],"吉林":["jilin","吉林","长春","延边"],"黑龙江":["heilongjiang","amur river","黑龙江","哈尔滨"],
 "江苏":["jiangsu","kiangsu","江苏","南京","苏州","无锡","常州","徐州"],"浙江":["zhejiang","chekiang","浙江","杭州","宁波","温州"],
 "安徽":["anhui","anhwei","安徽","合肥"],"福建":["fujian","fukien","福建","福州","厦门","泉州"],"江西":["jiangxi","kiangsi","江西","南昌"],
 "山东":["shandong","shantung","山东","济南","青岛"],"河南":["henan","honan","河南","郑州"],"湖北":["hubei","hupei","湖北","武汉"],
 "湖南":["hunan","湖南","长沙"],"广东":["guangdong","kwangtung","广东","广州","深圳","珠江","佛山","东莞","珠海","中山","江门"],"广西":["guangxi","kwangsi","广西","南宁"],
 "海南":["hainan","海南","海口","三亚"],"四川":["sichuan","szechuan","四川","成都"],"贵州":["guizhou","kweichow","贵州","贵阳"],
 "云南":["yunnan","云南","昆明"],"西藏":["xizang","tibet","西藏","拉萨"],"陕西":["shaanxi","shensi","陕西","西安"],
 "甘肃":["gansu","kansu","甘肃","兰州"],"青海":["qinghai","tsinghai","青海","西宁"],"宁夏":["ningxia","ningsia","宁夏","银川"],
 "新疆":["xinjiang","sinkiang","新疆","乌鲁木齐"],
}
NAT_PREFIX = ("cnr", "cri", "cmg", "cctv", "cgtn", "cetv", "china plus")
NAT_WORDS = ["中国之声","经济之声","中华之声","神州之声","华夏之声","中国交通","环球资讯","南海之声","乡村之声","大湾区之声","世界华声","民族之声","中央人民","国际台"]

CAT_RULES = [
 ("音乐", ["音乐","music","歌","流行","摇滚","古典","爵士","jazz","rock","pop","hits","hit fm","怀旧","金曲","lofi","dj","电音","民谣","easy fm","轻松","mix","melody","love radio","asiafm","星空","动听","好声音","经典fm","飞扬","倾城","情迷经典","旋律","钢琴","轻音乐"]),
 ("文艺", ["文艺","故事","文化","culture","评书","相声","小品","曲艺","戏曲","戏","京剧","越剧","黄梅","豫剧","昆曲","粤剧","粤曲","秦腔","小说","阅读","读书","诗","散文","文学","朗读","有声","广播剧","话剧","夜话","情感","倾听","讲古","书场","电影","影视","艺术","脱口秀"]),
 ("粤语", ["粤语","广东话","cantonese","cantopop","讲古","粤剧","粤曲","香港","rthk","商业电台","雷霆","叱咤","澳门","两广之声","珠江经济","广州","佛山","江门","肇庆","中山","东莞","清远","阳江","茂名","湛江","云浮","鹤山","台山","怀集","顺德","南海","番禺","开平","恩平","新会"]),
 ("新闻", ["新闻","资讯","news","经济","财经","股市","中国之声","综合广播"]),
 ("交通", ["交通","traffic","汽车","私家车","路况","车"]),
 ("方言/民族", ["方言","闽南","客家","客都","潮州","潮汕","藏语","维吾尔","维语","哈萨克","蒙古","蒙语","朝鲜","民语","民族语","hokkien","hakka","teochew"]),
]
NOT_CANTO = ["深圳","潮州","汕头","梅州","客","揭阳","普宁","澄海","汕尾"]
QT_CAT = {"音乐台":"音乐","文艺台":"文艺","曲艺台":"文艺","资讯台":"新闻","经济台":"新闻","交通台":"交通","方言台":"方言/民族","旅游台":"综合","生活台":"综合","都市台":"综合","综合台":"综合","体育台":"综合"}
PERSONAL_HOSTS = ["zeno.fm","radio.co","radioking","caster.fm","listen2myradio","mixlr","airtime.pro","streamguys","surfernetwork","live365","radiojar","myradio24","laut.fm","stream.radiojar","icecast.audio","fastcast4u","hearthis","shoutcast.com","citrus3","radiohost","bitbucket"]
INSTITUTION = ["广播","电台","fm","am","之声","人民","台","rthk","cnr","cri","cctv"]

def region_of(cc, state, name, country=""):
    if cc == "HK": return "香港"
    if cc == "MO": return "澳门"
    if cc == "TW": return "台湾"
    if cc and cc != "CN": return "海外华语"
    low = name.lower()
    if low.startswith(NAT_PREFIX): return "中央/全国"
    s = (state or "").lower()
    for p, keys in PROV.items():
        if any(k.lower() in s for k in keys): return p
    for p, keys in PROV.items():
        if any(k.lower() in low for k in keys): return p
    if any(k in low for k in NAT_WORDS): return "中央/全国"
    if "rthk" in low or "香港" in low or "hong kong" in s or "商业电台" in low: return "香港"
    if "澳门" in low or "macau" in low: return "澳门"
    if "台湾" in low or "臺灣" in low or "taiwan" in s: return "台湾"
    return "网络/其他"

def cats_of(name, extra, region, url, base=()):
    t = (name + " " + extra).lower()
    out = list(base)
    for c, keys in CAT_RULES:
        if c not in out and any(k in t for k in keys): out.append(c)
    if region in ("香港", "澳门") and "粤语" not in out and "putonghua" not in t and "普通话" not in t and "english" not in t: out.append("粤语")
    if "粤语" in out and any(k in name for k in NOT_CANTO) and not any(k in t for k in ["粤语","广东话","cantonese"]): out.remove("粤语")
    return out or ["综合"]

def fav(u):
    u = u or ""
    if u.startswith("http://pic.qtfm.cn"): u = "https" + u[4:]
    return u if u.startswith("https") else ""

# ---------- 1. 抓取 ----------
cands = []
def add(name, url, region, cats, votes, logo, src, personal=False, br=0):
    name = re.sub(r"\s+", " ", name or "").strip()
    if not name or not url or name.lower().startswith("http"): return
    if personal and "个人电台" not in cats: cats = cats + ["个人电台"]
    cands.append(dict(n=name, u=url, r=region, c=cats, v=votes, f=logo, src=src, br=br))

# Radio Browser：中港澳台全部（含被它标为失效的，因为它从欧洲测，国内台常被误判）
rb = {}
for cc in ["CN", "HK", "MO", "TW"]:
    for x in get(RB + f"stations/bycountrycodeexact/{cc}?limit=10000"): rb[x["stationuuid"]] = x
for lang in ["chinese", "mandarin", "cantonese", "hokkien", "hakka", "teochew", "粤语"]:
    for x in get(RB + "stations/bylanguageexact/" + urllib.parse.quote(lang) + "?hidebroken=true&limit=5000"): rb[x["stationuuid"]] = x
for tag in ["chinese", "cpop", "c-pop", "mandopop", "cantopop", "cantonese", "chinese music"]:
    for x in get(RB + "stations/bytagexact/" + urllib.parse.quote(tag) + "?hidebroken=true&limit=5000"): rb[x["stationuuid"]] = x
for kw in ["粤语", "香港", "文艺", "故事", "相声", "评书", "戏曲", "越剧", "京剧", "黄梅", "小说", "华语", "中文", "电台", "音乐", "广播", "之声"]:
    for x in get(RB + "stations/byname/" + urllib.parse.quote(kw) + "?hidebroken=true&limit=5000"): rb[x["stationuuid"]] = x
for x in rb.values():
    cc = x["countrycode"]; name = x["name"]; url = x["url_resolved"] or x["url"]
    if cc not in ("CN", "HK", "MO", "TW") and not re.search(r"[一-鿿]", name) and not set((x["language"] or "").lower().split(",")) & {"chinese","mandarin","cantonese","hokkien","hakka","teochew"} \
       and not set((x["tags"] or "").lower().split(",")) & {"chinese","cpop","c-pop","mandopop","cantopop","cantonese","chinese music"}:
        continue
    reg = region_of(cc, x["state"], name)
    extra = (x["tags"] or "") + " " + (x["language"] or "")
    host = url.split("/")[2] if "//" in url else ""
    personal = any(h in host for h in PERSONAL_HOSTS) or (reg in ("网络/其他", "海外华语") and not any(k in name.lower() for k in INSTITUTION))
    add(name, url, reg, cats_of(name, extra, reg, url), x["votes"], fav(x["favicon"]), "rb", personal, x["bitrate"] or 0)
print("radio-browser", len(cands), flush=True)

# 蜻蜓FM：各省地方台 + 网络台 + 主播节目台
def qt_list(cid):
    items, page = [], 1
    while True:
        try: d = get(f"https://rapi.qingting.fm/categories/{cid}/channels?with_total=true&page={page}&pagesize=100", 30)["Data"]
        except Exception: break
        items += d["items"]
        if len(items) >= d["total"] or not d["items"]: break
        page += 1
    return items
regions = get("https://webapi.qingting.fm/api/mobile/radio/regions")["regions"]
n0 = len(cands)
for rg in regions:
    for it in qt_list(rg["id"]):
        name = it["title"]; base = [QT_CAT[c["title"]] for c in it.get("categories", []) if c["title"] in QT_CAT]
        reg = rg["name"]
        if name.lower().startswith(NAT_PREFIX) or any(k in name for k in NAT_WORDS): reg = "中央/全国"
        add(name, f"https://lhttp.qingting.fm/live/{it['content_id']}/64k.mp3", reg,
            cats_of(name, it.get("description", "")[:60], reg, "", [b for b in base if b != "综合"]),
            it.get("audience_count", 0) // 100, fav(it.get("cover")), "qt", br=64)
for cid in list(range(396, 409)) + [427, 470]:
    for it in qt_list(cid):
        name = it["title"]
        reg = "网络/其他"
        rgn = (it.get("region") or {}).get("title") or ""
        for p in PROV:
            if p in rgn: reg = p
        is_net = cid in (407, 408)
        add(name, f"https://lhttp.qingting.fm/live/{it['content_id']}/64k.mp3", reg,
            cats_of(name, it.get("description", "")[:60], reg, ""), it.get("audience_count", 0) // 100, fav(it.get("cover")), "qt",
            personal=True, br=64)
print("qingting", len(cands) - n0, "total candidates", len(cands))

# ---------- 2. 测速 ----------
def read_for(r, secs):
    t0 = time.time(); n = 0; body = b""
    while time.time() - t0 < secs:
        b = r.read(8192)
        if not b: break
        if len(body) < 4096: body += b
        n += len(b)
    return n, time.time() - t0, body

def open_url(u, timeout=MAX_START + 1):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=timeout, context=CTX)

def test_hls(u, t0):
    with open_url(u) as r: final = r.geturl(); text = r.read(200000).decode("utf-8", "ignore")
    if "#EXTM3U" not in text: return None
    if "#EXT-X-STREAM-INF" in text:
        lines = [l for l in text.splitlines() if l and not l.startswith("#")]
        final = urllib.parse.urljoin(final, lines[0])
        with open_url(final) as r: final = r.geturl(); text = r.read(200000).decode("utf-8", "ignore")
    segs = [l for l in text.splitlines() if l and not l.startswith("#")]
    durs = [float(x) for x in re.findall(r"#EXTINF:([\d.]+)", text)]
    if not segs: return None
    seg = urllib.parse.urljoin(final, segs[-1]); dur = durs[-1] if durs else 6
    ts = time.time()
    with open_url(seg, 6) as r:
        data = b""
        while len(data) < 4_000_000 and time.time() - ts < 8:
            b = r.read(65536)
            if not b: break
            data += b
        if time.time() - ts >= 8: return None
    dl = time.time() - ts
    start = time.time() - t0
    if len(data) < 1000: return None
    return start, dur / max(dl, 0.01)

def test(c):
    u = c["u"]
    if u.startswith("http:"): u = "https:" + u[5:]
    t0 = time.time()
    try:
        if re.search(r"\.m3u8(\?|$)", u, re.I):
            res = test_hls(u, t0)
            if not res: return None
            start, ratio = res
        else:
            with open_url(u) as r:
                final = r.geturl()
                if not final.startswith("https"): return None
                ct = (r.headers.get("Content-Type") or "").lower()
                first = r.read(2048)
                ttfb = time.time() - t0
                if b"#EXTM3U" in first:   # 没有 .m3u8 后缀的 HLS
                    res = test_hls(final, t0)
                    if not res: return None
                    start, ratio = res
                else:
                    if "html" in ct or "json" in ct or "text" in ct: return None
                    n, secs, _ = read_for(r, TEST_SECS)
                    n += len(first)
                    kbps = n * 8 / 1000 / max(secs + (ttfb if secs < 0.5 else 0), 0.5)
                    need = max(c["br"] or 64, 32)
                    start, ratio = ttfb, kbps / need
                u = final if final.startswith("https") else u
        if start > MAX_START or ratio < MIN_RATIO: return None
        return u, round(start, 2)
    except Exception:
        return None

import os
CACHE = OUT + ".tested.json"
if os.path.exists(CACHE) and "--cached" in sys.argv:
    ok = json.load(open(CACHE, encoding="utf-8")); cands = []
t = time.time()
res = [None] * len(cands)
with cf.ThreadPoolExecutor(32) as ex:
    futs = {ex.submit(test, c): i for i, c in enumerate(cands)}
    for k, f in enumerate(cf.as_completed(futs)):
        res[futs[f]] = f.result()
        if k % 200 == 0: print("tested", k, "of", len(cands), flush=True)
# 开播时间波动大：没通过的台用低并发再测一次，避免误删
retry = [i for i, r in enumerate(res) if r is None]
print("retesting", len(retry), flush=True)
with cf.ThreadPoolExecutor(24) as ex:
    for i, r in zip(retry, ex.map(lambda i: test(cands[i]), retry)): res[i] = r
ok = ok if not cands else []
for c, r in zip(cands, res):
    if r:
        c["u"], c["s"] = r
        ok.append(c)
print(f"tested {len(cands)} in {time.time()-t:.0f}s, fast enough: {len(ok)}")
if cands: json.dump(ok, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

# ---------- 3. 去重 ----------
def url_key(u):
    m = re.search(r"qingting\.fm/live/(\d+)|qtfm\.cn/live/(\d+)", u)
    if m: return "qt:" + (m.group(1) or m.group(2))
    return re.sub(r"^https?://|[?#].*$", "", u).rstrip("/").lower()
def name_key(n):
    k = n.lower()
    k = re.sub(r"[\s·•\-_|()（）【】\[\]「」《》:：,，.。!！'\"/]+", "", k)
    k2 = re.sub(r"(fm|am|调频)?\d{2,4}(\.\d+)?(mhz|khz)?", "", k)
    return k2 if len(k2) >= 4 else k

parent = list(range(len(ok)))
def find(i):
    while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
    return i
seen = {}
for i, c in enumerate(ok):
    for k in (("u", url_key(c["u"])), ("n", c["r"], name_key(c["n"]))):
        if k in seen: parent[find(i)] = find(seen[k])
        else: seen[k] = i
groups = {}
for i in range(len(ok)): groups.setdefault(find(i), []).append(ok[i])
final = []
for g in groups.values():
    best = min(g, key=lambda c: (bool(re.search(r"m3u8", c["u"], re.I)), c["s"], -c["v"]))   # 同一个台优先 MP3，兼容性更好
    names = sorted(g, key=lambda c: (c["src"] != "qt", -c["v"]))   # 名称和图标优先用蜻蜓的
    cats = []
    for c in g:
        for x in c["c"]:
            if x not in cats: cats.append(x)
    if len(cats) > 1 and "综合" in cats: cats.remove("综合")
    reg = next((c["r"] for c in names if c["r"] not in ("网络/其他",)), best["r"])
    final.append(dict(id=re.sub(r"[^a-z0-9]", "", url_key(best["u"]))[-24:] or str(len(final)),
                      n=names[0]["n"], u=best["u"], r=reg, c=cats, v=max(c["v"] for c in g),
                      f=next((c["f"] for c in names if c["f"]), ""), s=best["s"]))
# 粤语只留：两广/港澳/海外华语，或台名明确写了粤语的
CANTO_OK = ("广东", "广西", "香港", "澳门", "海外华语", "网络/其他")
for x in final:
    if "粤语" in x["c"] and x["r"] not in CANTO_OK and not re.search(r"粤|广东话|cantonese|香港|港澳", x["n"], re.I):
        x["c"].remove("粤语")
        if not x["c"]: x["c"] = ["综合"]
# id 去冲突
ids = Counter(x["id"] for x in final)
for i, x in enumerate(final):
    if ids[x["id"]] > 1: x["id"] += str(i)
final.sort(key=lambda x: -x["v"])
print("after dedup", len(final))
json.dump(final, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
with open(OUT + ".report.txt", "w", encoding="utf-8") as o:
    print("candidates", len(cands), "fast", len(ok), "final", len(final), file=o)
    print(Counter(x["r"] for x in final).most_common(), file=o)
    print(Counter(c for x in final for c in x["c"]).most_common(), file=o)
    print("start-time median", sorted(x["s"] for x in final)[len(final)//2], file=o)
    for cat in ["粤语", "文艺", "个人电台"]:
        print(cat, [x["n"] for x in final if cat in x["c"]][:80], file=o)

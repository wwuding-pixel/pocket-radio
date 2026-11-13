"""Fetch CN/HK/MO/TW stations from Radio Browser, normalize, test streams over HTTPS, write stations.json."""
import json, re, sys, ssl, urllib.request, concurrent.futures as cf

OUT = sys.argv[1]
UA = {"User-Agent": "PocketRadio/1.0"}
API = "https://de1.api.radio-browser.info/json/stations/bycountrycodeexact/{}?hidebroken=true&limit=5000"

PROV = {  # canonical Chinese name -> keyword list (english variants + chinese)
 "北京":["beijing","peking","北京"],"天津":["tianjin","tientsin","天津"],"上海":["shanghai","上海"],"重庆":["chongqing","chungking","重庆"],
 "河北":["hebei","hopei","河北","石家庄"],"山西":["shanxi","shansi","山西","太原"],"内蒙古":["inner mongolia","nei mongol","内蒙古","呼和浩特","包头"],
 "辽宁":["liaoning","辽宁","沈阳","大连","dalian"],"吉林":["jilin","吉林","长春"],"黑龙江":["heilongjiang","amur river","黑龙江","哈尔滨"],
 "江苏":["jiangsu","kiangsu","江苏","南京","苏州","无锡","常州","徐州"],"浙江":["zhejiang","chekiang","浙江","杭州","宁波","温州"],
 "安徽":["anhui","anhwei","安徽","合肥"],"福建":["fujian","fukien","福建","福州","厦门"],"江西":["jiangxi","kiangsi","江西","南昌"],
 "山东":["shandong","shantung","山东","济南","青岛"],"河南":["henan","honan","河南","郑州"],"湖北":["hubei","hupei","湖北","武汉"],
 "湖南":["hunan","湖南","长沙"],"广东":["guangdong","kwangtung","广东","广州","深圳","珠江","佛山","东莞"],"广西":["guangxi","kwangsi","广西","南宁"],
 "海南":["hainan","海南","海口","三亚"],"四川":["sichuan","szechuan","四川","成都"],"贵州":["guizhou","kweichow","贵州","贵阳"],
 "云南":["yunnan","云南","昆明"],"西藏":["xizang","tibet","西藏","拉萨"],"陕西":["shaanxi","shensi","陕西","西安"],
 "甘肃":["gansu","kansu","甘肃","兰州"],"青海":["qinghai","tsinghai","青海","西宁"],"宁夏":["ningxia","ningsia","宁夏","银川"],
 "新疆":["xinjiang","sinkiang","新疆","乌鲁木齐"],
}
NATIONAL = ["中国之声","经济之声","音乐之声","经典音乐","中华之声","神州之声","华夏之声","香港之声","文艺之声","老年之声","藏语","维吾尔","哈萨克","中国交通","环球资讯","南海之声","轻松调频","劲曲调频","hit fm","easy fm","cnr","cri","中央","国际台","国家应急","中国乡村之声","大湾区之声","阅读之声","经典音乐广播"]
CAT_RULES = [
 ("音乐", ["音乐","music","歌","流行","摇滚","古典","爵士","jazz","rock","pop","hits","hit","怀旧","金曲","lofi","dj","电音","民谣","音乐台","easy fm","轻松","mix","melody","love radio","asiafm","星空","动听","伴音乐"]),
 ("新闻", ["新闻","资讯","news","之声","综合","经济","财经","中国之声"]),
 ("交通", ["交通","traffic","汽车","私家车","路况"]),
 ("文艺", ["文艺","故事","文化","culture","评书","相声","曲艺","戏曲","戏","小说","阅读","都市"]),
 ("方言/民族", ["粤语","闽南","客家","藏语","维吾尔","哈萨克","蒙古","朝鲜","方言","cantonese"]),
]

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)

NAT_PREFIX = ("cnr", "cri", "cmg", "cctv", "cgtn", "cetv", "china plus")
NAT_WORDS = ["中国之声","经济之声","中华之声","神州之声","华夏之声","中国交通","环球资讯","南海之声","乡村之声","大湾区之声","世界华声","民族之声","中央人民","国际台"]
def norm_region(cc, state, name):
    if cc == "HK": return "香港"
    if cc == "MO": return "澳门"
    if cc == "TW": return "台湾"
    low = name.lower()
    if low.startswith(NAT_PREFIX): return "中央/全国"
    s = (state or "").lower()
    for p, keys in PROV.items():
        if any(k.lower() in s for k in keys): return p
    for p, keys in PROV.items():
        if any(k.lower() in low for k in keys): return p
    if any(k in low for k in NAT_WORDS): return "中央/全国"
    if "rthk" in low or "香港" in low or "hong kong" in s or "hong kong" in low or "商业电台" in low: return "香港"
    if "澳门" in low or "macau" in low: return "澳门"
    if "台湾" in low or "臺灣" in low or "taiwan" in s: return "台湾"
    return "网络/其他"

def cats(name, tags):
    t = (name + " " + tags).lower()
    return [c for c, keys in CAT_RULES if any(k in t for k in keys)] or ["综合"]

CTX = ssl.create_default_context()
def probe(url):
    """Return working https url or None."""
    cands = [url] if url.startswith("https:") else ["https:" + url[5:]]
    for u in cands:
        try:
            req = urllib.request.Request(u, headers={**UA, "Range": "bytes=0-4095"})
            with urllib.request.urlopen(req, timeout=10, context=CTX) as r:
                ct = (r.headers.get("Content-Type") or "").lower()
                body = r.read(4096)
                if "html" in ct and b"#EXTM3U" not in body: continue
                if len(body) < 200 and b"#EXTM3U" not in body: continue
                return r.geturl() if r.geturl().startswith("https") else None
        except Exception:
            continue
    return None

raw = []
for cc in ["CN", "HK", "MO", "TW"]:
    for x in get(API.format(cc)):
        x["_cc"] = cc
        raw.append(x)
print("raw", len(raw))

seen, items = set(), []
for x in raw:
    name = re.sub(r"\s+", " ", x["name"]).strip()
    url = x["url_resolved"] or x["url"]
    if not name or not url.startswith("http") or name.lower().startswith("http"): continue
    key = (name.lower(), url)
    if key in seen: continue
    seen.add(key)
    items.append(dict(n=name, u=url, r=norm_region(x["_cc"], x["state"], name), c=cats(name, x["tags"] or ""),
                      v=x["votes"], f=x["favicon"] if (x["favicon"] or "").startswith("https") else "", id=x["stationuuid"]))
print("dedup", len(items))

with cf.ThreadPoolExecutor(64) as ex:
    res = list(ex.map(lambda it: probe(it["u"]), items))
ok = []
for it, good in zip(items, res):
    if good:
        it["u"] = good
        ok.append(it)
# same name repeated: keep the most-voted working one
best = {}
for it in ok:
    k = it["n"].lower()
    if k not in best or it["v"] > best[k]["v"]: best[k] = it
final = sorted(best.values(), key=lambda i: -i["v"])
print("working", len(ok), "unique", len(final))
json.dump(final, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
from collections import Counter
print(Counter(i["r"] for i in final).most_common())
print(Counter(c for i in final for c in i["c"]).most_common())

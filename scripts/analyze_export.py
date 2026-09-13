#!/usr/bin/env python3
"""分析授权 JSONL 导出；不执行网页采集。"""
from __future__ import annotations
import argparse, collections, csv, hashlib, html, json, pathlib, re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

POS=("满意","方便","快速","推荐","划算","及时","靠谱","喜欢","不错","贴心","惊喜","值得")
NEG=("难吃","失望","慢","贵","投诉","退款","破损","迟到","糟糕","不满","缺货","没货","漏","洒","凉")
STOP=set("的 了 和 是 就 都 而 及 与 一个 没有 我们 你们 他们 这个 那个 什么 怎么 为什么 在 有 不 也 还 很 太 真 视频 抖音 点赞 评论 收藏 分享 喜欢 推荐 支持 希望 期待".split())
CLUSTERS=[
 ("外卖履约时效",("配送","超时","迟到","洒","漏","凉了","没送到","送错","骑手","等太久","还没到"),"配送或出餐链路延迟","核查超时节点，设置异常单主动通知与补偿","履约 / 运营","配送时长、超时率"),
 ("餐品与质量",("难吃","分量","太咸","太甜","变质","食材","卫生","异物","不新鲜","凉"),"出品或包装标准不稳定","抽检出品与保温包装，回访质量客诉","餐饮 / 供应链","质量客诉率、退单率"),
 ("价格与优惠",("贵","涨价","优惠","券","满减","价格","不值","割韭菜"),"价格感知或促销规则不清","核对价差并简化优惠规则说明","产品 / 商务","优惠核销率、转化率"),
 ("客服与售后",("投诉","退款","客服","不理","赔偿","没人管","不处理","踢皮球"),"响应链路或责任边界不清","明确首响和解决时限，展示退款进度","客服 / 售后","解决率、响应时长"),
 ("即时零售缺货与库存",("缺货","没货","无货","取消","库存","断货","买不到","售罄"),"库存同步或补货不足","校验库存准确率并提供替换建议","供应链 / 门店","缺货率、取消率"),
]
MEME_RULES=[
 ("XX来，妈妈XX",r"(?:妈妈.{0,12}[\u4e00-\u9fffA-Za-z0-9]{1,5}来|[\u4e00-\u9fffA-Za-z0-9]{1,5}来.{0,12}妈妈)","「主体」来，妈妈「回应/动作」","把主体替换成品牌、产品、人物或动物，再保留‘来/妈妈’的召唤关系"),
 ("不是哥们，XX",r"不是[，, ]*哥们","不是哥们，「反常事件或吐槽点」","把意外情节或槽点放进后半句"),
 ("小丑竟是我自己",r"小丑(竟是|原来是)?我自己","铺垫判断，最后接“小丑竟是我自己”","用于自嘲式反转"),
 ("这谁顶得住",r"这谁顶得住","这种「强烈体验」，谁顶得住","替换前面的体验对象"),
 ("退退退",r"退[！! ]*退[！! ]*退","「不想要的事物」退退退","把拒绝对象放在前面"),
 ("已老实，求放过",r"已老实|求放过","已老实，求「对象」放过","替换让人受挫的对象或情境"),
 ("主打一个XX",r"主打一个","主打一个「状态/态度」","替换最后的状态词"),
 ("听君一席话",r"听君一席话","听君一席话，如听一席话","保留前半句，用无信息量后半句制造反差"),
 ("我嘞个XX",r"我嘞个","我嘞个「名词/形容词」","替换最后的惊叹对象"),
 ("我貌似提前XX了呢",r"我貌似提前.{1,10}了呢","我貌似提前「得到/遭遇某事」了呢＋反应表情","替换提前发生的事件，用反应表情强化反差"),
 ("尊嘟假嘟",r"尊嘟假嘟","尊嘟假嘟＋事件","用于谐音式惊讶或反问"),
 ("City不City",r"city不city|city or not city","「地点/体验」City不City","替换被评价的地点或体验"),
 ("泼天的富贵",r"泼天的富贵","这泼天的「好运/流量」终于轮到XX","替换受益对象和收益"),
]

def val(row,keys,default=""):
 for k in keys:
  if row.get(k) not in (None,""): return row[k]
 return default
def nint(v):
 try:return max(0,int(float(str(v).replace(",",""))))
 except:return 0
def dt(v):
 if v in (None,""):raise ValueError("缺少时间")
 s=str(v).strip()
 if re.fullmatch(r"\d+(\.\d+)?",s):
  x=float(s);x=x/1000 if x>1e10 else x
  return datetime.fromtimestamp(x,timezone.utc)
 s=s.replace("Z","+00:00")
 for f in (lambda:datetime.fromisoformat(s),lambda:datetime.strptime(s,"%Y-%m-%d %H:%M:%S"),lambda:datetime.strptime(s,"%Y-%m-%d")):
  try:
   x=f();return x.replace(tzinfo=timezone.utc) if x.tzinfo is None else x.astimezone(timezone.utc)
  except ValueError:pass
 raise ValueError("时间格式不支持")
def redact(s):
 old=s
 for p,r in [(r"(?<!\d)1[3-9]\d{9}(?!\d)","[手机号已脱敏]"),(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}","[邮箱已脱敏]"),(r"(?i)(微信|vx|wechat)\s*[:：号]?\s*[A-Za-z][\w-]{5,19}","[账号已脱敏]"),(r"(?<!\w)@[\w\-\u4e00-\u9fff]{2,30}","@[账号已脱敏]"),(r"https?://\S+","[链接已脱敏]"),(r"(地址|住址|收货地址)\s*[:：]?\s*[^，。；;\n]{4,60}","地址：[地址已脱敏]")]:s=re.sub(p,r,s)
 return s,s!=old
def cell(s):return str(s or "").replace("\n"," ").replace("\r"," ").replace("|","\\|").replace("[","\\[").replace("]","\\]").strip()
def kws(row):
 out=[]
 for k in ("source_keyword","search_keyword","keyword","keywords","matched_keywords"):
  v=row.get(k)
  out.extend(v if isinstance(v,list) else re.split(r"[,，;；]",str(v))) if v not in (None,"") else None
 return {str(x).strip() for x in out if str(x).strip()}
def post(platform,row):
 pid=str(val(row,("note_id","aweme_id","post_id","id"))).strip();title=str(val(row,("title","desc","content","text")));desc=str(row.get("desc") or "")
 text,red=redact("\n".join(dict.fromkeys(x for x in (title,desc) if x)));url=str(val(row,("source_url","aweme_url","url"),f"https://www.douyin.com/video/{pid}"))
 if not re.match(r"^https?://",url,re.I):url=f"https://www.douyin.com/video/{pid}"
 return dict(platform=platform,post_id=pid,creator_id=str(val(row,("creator_id","user_id","sec_uid","author_id"))).strip(),url=url,text=text,published_at=dt(val(row,("published_at","create_time","time","publish_time","timestamp"))),like_count=nint(val(row,("like_count","liked_count","digg_count"))),comment_count=nint(val(row,("comment_count","comments_count"))),matched_keywords=kws(row),privacy_redacted=red)
def comment(platform,row):
 text,red=redact(str(val(row,("content","text","comment_text"))))
 return dict(platform=platform,comment_id=str(val(row,("comment_id","cid","id"))).strip(),post_id=str(val(row,("note_id","aweme_id","post_id"))).strip(),creator_id=str(val(row,("creator_hash","creator_id","user_id","sec_uid"))).strip(),text=text,published_at=dt(val(row,("published_at","create_time","time","timestamp"))),like_count=nint(val(row,("like_count","liked_count","digg_count"))),parent=str(val(row,("parent_comment_id","parent_id"))).strip(),privacy_redacted=red)

def load(root,platforms,wanted,args):
 stats=collections.Counter();warnings=[];posts={};comments={}
 for platform in platforms:
  dirs=[root/"dy/jsonl",root/"douyin/jsonl"]
  for d in dirs:
   if not d.exists():continue
   for kind,pattern,mapper in (("posts","*contents_*.jsonl",post),("comments","*comments_*.jsonl",comment)):
    for path in sorted(d.glob(pattern)):
     stats["files"]+=1
     for no,line in enumerate(path.open(encoding="utf-8-sig",errors="replace"),1):
      if not line.strip():continue
      stats["raw_"+kind]+=1
      try:row=json.loads(line);x=mapper(platform,row)
      except (json.JSONDecodeError,ValueError,TypeError):
       stats["invalid"]+=1
       if len(warnings)<20:warnings.append(f"{path.name}:{no} 无法解析或字段无效")
       continue
      if kind=="posts":
       if not x["post_id"]:stats["missing_id"]+=1;continue
       matched=x["matched_keywords"]&wanted if x["matched_keywords"] else {k for k in wanted if k in x["text"]}
       if not matched or any(k in x["text"] for k in args.exclude):stats["target_filtered"]+=1;continue
       if args.creator_id and args.creator_scope=="owned_posts" and x["creator_id"]!=args.creator_id:stats["target_filtered"]+=1;continue
       if args.post_url and x["url"] not in args.post_url:stats["target_filtered"]+=1;continue
       x["matched_keywords"]=matched;key=(platform,x["post_id"])
       if key in posts:stats["duplicates"]+=1;posts[key]["matched_keywords"]|=matched
       else:posts[key]=x
      else:
       if not x["comment_id"] or not x["post_id"]:stats["missing_id"]+=1;continue
       if x["parent"] not in ("","0","None"):stats["replies"]+=1;continue
       if len(re.sub(r"\s+","",x["text"]))<2 or re.search(r"(加我|进群|扫码).{0,10}(微信|vx|二维码)",x["text"],re.I):stats["spam"]+=1;continue
       key=(platform,x["comment_id"])
       if key in comments:stats["duplicates"]+=1
       else:comments[key]=x
 return list(posts.values()),list(comments.values()),stats,warnings

def snownlp():
 try:
  from snownlp import SnowNLP;return SnowNLP
 except ImportError:return None
def sent(text,S):
 p=any(w in text for w in POS);n=any(w in text for w in NEG)
 if (p and n) or re.search(r"[？?].*(呵呵|真棒|真行)|就这|笑死",text):return "mixed",None
 score=None
 if S:
  try:score=float(S(text).sentiments)
  except:pass
 if p:return "positive",score
 if n:return "negative",score
 if score is None:return "neutral",None
 return ("positive" if score>=.7 else "negative" if score<=.3 else "neutral"),score
def words(text,S):
 ws=S(text).words if S else re.findall(r"[\u4e00-\u9fff]{2,6}",text)
 return {w.strip() for w in ws if len(w.strip())>1 and w.strip() not in STOP and re.search(r"[\u4e00-\u9fff]",w)}
def sample(cs,candidate,limit):
 cand=sorted(cs,key=lambda x:(x["like_count"],x["published_at"]),reverse=True)[:candidate];target=min(limit,len(cand));out={}
 groups=[cand[:max(1,target*4//10)],sorted(cand,key=lambda x:x["published_at"],reverse=True)[:max(1,target*3//10)]]
 chrono=sorted(cand,key=lambda x:x["published_at"]);groups.append(chrono[::max(1,len(chrono)//max(1,target-sum(map(len,groups))))])
 for group in groups+[cand]:
  for c in group:
   out[(c["platform"],c["comment_id"])]=c
   if len(out)>=target:return list(out.values())
 return list(out.values())
def meme_key(text):
 """返回可复刻的表达模板。"""
 low=text.lower()
 for rule in MEME_RULES:
  if re.search(rule[1],low,re.I):return rule
 return None
def memes(items):
 groups={}
 for item in items:
  rule=meme_key(item["text"])
  if rule:
   name,_,formula,guide=rule;groups.setdefault(name,{"formula":formula,"guide":guide,"items":[]})["items"].append(item)
 out=[]
 for name,group in groups.items():
  unique={}
  for x in group["items"]:
   key=("评论用户",x["creator_id"]) if x["source_type"]=="评论" and x.get("creator_id") else x["item_key"]
   if key not in unique or x["engagement"]>unique[key]["engagement"]:unique[key]=x
  items=sorted(unique.values(),key=lambda x:x["engagement"],reverse=True)
  mentions=len(items);likes=sum(x["like_count"] for x in items);engagement=sum(x["engagement"] for x in items);peak=max((x["engagement"] for x in items),default=0)
  if mentions<2 and engagement<10:continue
  posts=sum(x["source_type"]=="帖子" for x in items);comments=mentions-posts;heat=engagement+mentions*5
  out.append(dict(name=name,formula=group["formula"],guide=group["guide"],mentions=mentions,posts=posts,comments=comments,likes=likes,engagement=engagement,peak=peak,heat=heat,evidence=items[:4],strength="热门模板" if mentions>=3 or engagement>=50 else "可复刻候选"))
 return sorted(out,key=lambda x:(x["heat"],x["mentions"],x["peak"]),reverse=True)[:10]
def analyze(platform,label,days,posts,comments,args,now,S):
 start=now.astimezone(timezone.utc)-timedelta(days=days);pool=[p for p in posts if p["platform"]==platform and p["published_at"]>=start]
 ranked=sorted(pool,key=lambda p:(p["like_count"]*args.like_weight+p["comment_count"]*args.comment_weight,p["published_at"]),reverse=True)[:args.post_limit]
 meme_posts=sorted(pool,key=lambda p:(p["like_count"],p["published_at"]),reverse=True)[:args.post_limit]
 keys={(p["platform"],p["post_id"]) for p in ranked};by=collections.defaultdict(list)
 for c in comments:
  if (c["platform"],c["post_id"]) in keys:by[(c["platform"],c["post_id"])].append(c)
 chosen=[]
 for key in keys:chosen+=sample(by[key],args.comment_candidate_limit,args.comment_limit)
 chosen=list({(c["platform"],c["comment_id"]):c for c in chosen}.values());labeled=[(c,*sent(c["text"],S)) for c in chosen];counts=collections.Counter(x[1] for x in labeled);terms={"positive":collections.Counter(),"negative":collections.Counter()}
 for c,l,_ in labeled:
  if l in terms:terms[l].update(words(c["text"],S))
 meme_keys={(p["platform"],p["post_id"]) for p in meme_posts};meme_by=collections.defaultdict(list)
 for c in comments:
  key=(c["platform"],c["post_id"])
  if key in meme_keys:meme_by[key].append(c)
 meme_comments=[]
 for key in meme_keys:meme_comments+=sorted(meme_by[key],key=lambda c:(c["like_count"],c["published_at"]),reverse=True)[:args.comment_limit]
 urls={(p["platform"],p["post_id"]):p["url"] for p in meme_posts}
 meme_items=[dict(c,item_key=("评论",c["platform"],c["comment_id"]),source_type="评论",source_url=urls.get((c["platform"],c["post_id"]),""),engagement=c["like_count"]) for c in meme_comments]
 meme_items += [dict(p,item_key=("帖子",p["platform"],p["post_id"]),source_type="帖子",source_url=p["url"],engagement=p["like_count"]+p["comment_count"]*2) for p in meme_posts]
 neg=[c for c,l,_ in labeled if l in ("negative","mixed")];ins=[]
 for name,keys2,cause,action,team,metric in CLUSTERS:
  ev=sorted([c for c in neg if any(k in c["text"] for k in keys2)],key=lambda c:c["like_count"],reverse=True)
  if ev:ins.append(dict(name=name,count=len(ev),ratio=len(ev)/len(neg),cause=cause,action=action,team=team,metric=metric,evidence=ev[:5],strength="数据支持" if len(ev)>=3 else "弱信号"))
 ins.sort(key=lambda x:x["count"],reverse=True);total=len(labeled);shares={k:counts[k]/total if total else 0 for k in ("positive","neutral","negative","mixed")}
 return dict(platform=platform,label=label,posts=pool,ranked=ranked,labeled=labeled,counts=counts,shares=shares,terms=terms,insights=ins,memes=memes(meme_items),small=total<30)

def render(s,num,tz,args):
 L=[f"## {num}、{s['label']}",""]
 if not s["posts"]:return L+["> 无可用数据：该平台和时间窗没有匹配帖子。","","### 本板块限制","","- 无数据，不生成分析结论。",""]
 total=len(s["labeled"])
 if s["small"]:L += [f"> ⚠️ 小样本：仅 {total} 条有效评论，仅供定性参考。",""]
 L += ["### 1. 数据概览","","| 指标 | 结果 |","|---|---:|",f"| 匹配帖子 | {len(s['posts'])} |",f"| 入榜帖子 | {len(s['ranked'])} |",f"| 有效评论样本 | {total} |"]+[f"| {zh} | {s['shares'][en]:.1%} |" for en,zh in (("positive","正面"),("neutral","中性"),("negative","负面"),("mixed","混合/不确定"))]+["","> 情绪为自动初筛；风险和业务判断须结合原文与人工复核。","","### 2. 高频主题",""]
 for pol,title in (("positive","正面"),("negative","负面")):
  L += [f"#### {title}","","| 排名 | 主题 | 覆盖评论数 |","|---:|---|---:|"]
  rows=s["terms"][pol].most_common(10);L += [f"| {i} | {cell(w)} | {n} |" for i,(w,n) in enumerate(rows,1)] or ["| — | 无可靠主题 | 0 |"] ;L.append("")
 L += ["### 3. 可复刻玩梗（高赞帖子＋高赞评论）","","> 只在按点赞排序的帖子池及每帖按点赞排序的评论池中识别，并展示能抽象为复刻公式的表达模板。帖子互动基数 = 点赞 + 评论 × 2；评论互动基数 = 点赞；热度分 = 互动基数 + 内容提及数 × 5。","","| 排名 | 玩梗模板 | 帖子 / 评论 | 互动基数 | 热度分 |","|---:|---|---:|---:|---:|"]
 L += [f"| {i} | {cell(x['name'])} | {x['posts']} / {x['comments']} | {x['engagement']} | {x['heat']} |" for i,x in enumerate(s["memes"],1)] or ["| — | 未识别到达到热度门槛的可复刻玩梗 | 0 / 0 | 0 | 0 |"]
 for x in s["memes"]:
  L += ["",f"**{cell(x['name'])} · {x['strength']}**",f"- 复刻公式：{cell(x['formula'])}",f"- 怎么玩：{cell(x['guide'])}","- 样本证据："]+[f"  - {e['source_type']}：“{cell(e['text'])}”（赞 {e['like_count']}）" for e in x["evidence"]]
 L += ["","### 4. 用户关心点与问题链路",""]
 if not s["insights"]:L += ["- 当前样本未形成可归类的负面关心点。",""]
 for i,x in enumerate(s["insights"],1):
  L += [f"#### {i}. {x['name']}（{x['strength']}）","",f"- 用户不满意：{x['name']}相关体验",f"- 可能原因：{x['cause']}（需业务数据验证）",f"- 用户希望怎么改：{x['action']}",f"- 证据：{x['count']} 条，占负面及混合评论 {x['ratio']:.1%}","- 原生评论（已自动脱敏）："]+[f"  - “{cell(e['text'])}”（赞 {e['like_count']}）" for e in x["evidence"]]+[""]
 L += ["### 5. 高互动帖子","","| 帖子 | 发布时间 | 赞 / 评 | 结论强度 |","|---|---|---:|---|"]
 for p in s["ranked"][:10]:L.append(f"| [{cell(p['text'][:50]) or '无标题'}]({p['url'].replace(')','%29')}) | {p['published_at'].astimezone(tz):%Y-%m-%d %H:%M} | {p['like_count']} / {p['comment_count']} | 推测 |")
 L += ["","### 6. 业务建议","","| 关心点 | 证据 | 建议动作 | 团队 | 强度 | 验证指标 |","|---|---:|---|---|---|---|"]+[f"| {x['name']} | {x['count']} | {cell(x['action'])} | {x['team']} | {x['strength']} | {cell(x['metric'])} |" for x in s["insights"]]+["","### 7. 本板块限制","","- 本报告反映已采集样本，不代表全平台总体。",f"- 每帖最多 {args.comment_candidate_limit} 条候选，再从高赞、最新和不同时段分层选取最多 {args.comment_limit} 条。","- 可复刻玩梗从高赞帖子及其已采集评论中的高赞候选识别；同一账号重复使用同一模板只计一次。低频新模板可能漏检，语境可能误判。","- 正式发布前应完成复核 CSV 的人工抽检。",""]
 return L

def review(path,sections):
 rows={}
 for s in sections:
  xs=sorted(s["labeled"],key=lambda x:hashlib.sha256(f"{x[0]['platform']}:{x[0]['comment_id']}".encode()).hexdigest())[:30]
  for c,l,score in xs:rows[(s["label"],c["platform"],c["comment_id"])]=(s["label"],c,l,score)
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("w",encoding="utf-8-sig",newline="") as f:
  w=csv.writer(f);w.writerow(["section","platform","post_id","comment_id","text_redacted","auto_sentiment","auto_score","manual_sentiment","manual_topic","review_note"])
  for sec,c,l,score in rows.values():w.writerow([sec,c["platform"],c["post_id"],c["comment_id"],c["text"],l,"" if score is None else f"{score:.4f}","","",""])
 return len(rows)

def page(sections,title,subtitle,current_keyword):
 data=[]
 for s in sections:
  data.append({"label":s["label"],"posts":len(s["posts"]),"comments":len(s["labeled"]),"shares":s["shares"],"small":s["small"],
   "pos":s["terms"]["positive"].most_common(10),"neg":s["terms"]["negative"].most_common(10),
   "memes":[{"name":x["name"],"formula":x["formula"],"guide":x["guide"],"mentions":x["mentions"],"posts":x["posts"],"comments":x["comments"],"engagement":x["engagement"],"peak":x["peak"],"heat":x["heat"],"strength":x["strength"],"evidence":[{"text":e["text"],"likes":e["like_count"],"source":e["source_type"],"url":e["source_url"]} for e in x["evidence"]]} for x in s["memes"]],
   "insights":[{"name":x["name"],"count":x["count"],"cause":x["cause"],"action":x["action"],"team":x["team"],"metric":x["metric"],"strength":x["strength"],"evidence":[{"text":e["text"],"likes":e["like_count"]} for e in x["evidence"]]} for x in s["insights"]],
   "top":[{"text":p["text"][:100],"url":p["url"],"likes":p["like_count"],"comments":p["comment_count"]} for p in s["ranked"][:10]]})
 payload=json.dumps(data,ensure_ascii=False).replace("</","<\\/")
 template='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title><style>
:root{--bg:#f7f4ef;--card:#fff;--ink:#263432;--muted:#8e9794;--line:#eae5dd;--teal:#4a9d9a;--teal2:#e8f4f2;--red:#bd6a5d;--red2:#faece9;--shadow:0 15px 42px rgba(43,51,49,.07)}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif}.shell{min-height:100vh;display:grid;grid-template-columns:220px 1fr}aside{position:sticky;top:0;height:100vh;background:#fff;border-right:1px solid var(--line);padding:28px 18px;display:flex;flex-direction:column}.brand{display:flex;align-items:center;gap:11px;font-weight:800}.mark{width:38px;height:38px;display:grid;place-items:center;border-radius:12px;background:var(--teal);color:#fff}.nav{margin-top:35px;padding:12px 14px;border-radius:12px;background:var(--teal2);color:#357b78;font-size:13px;font-weight:700}.note{margin-top:auto;padding:14px;background:#f7f3ed;border-radius:14px;color:#8d857a;font-size:11px;line-height:1.7}main{padding:34px clamp(20px,4vw,58px) 60px;min-width:0}header{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}.eyebrow{margin:0 0 7px;color:var(--teal);font-size:10px;font-weight:800;letter-spacing:.17em}h1{margin:0;font-size:28px}.sub{color:var(--muted);font-size:12px}.tabs{display:flex;gap:4px;padding:4px;background:#e9e4dc;border-radius:12px}.tabs button{border:0;background:transparent;padding:9px 13px;border-radius:9px;color:#737b78;cursor:pointer}.tabs button.active{background:var(--teal);color:white}.warning{margin-top:22px;padding:12px 15px;background:#fff7e8;border:1px solid #f1ddb8;border-radius:12px;color:#8a6c38;font-size:12px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin-top:22px}.card,.panel{background:var(--card);border:1px solid rgba(229,225,218,.85);border-radius:18px;box-shadow:var(--shadow)}.card{padding:19px}.card span{color:var(--muted);font-size:11px}.card strong{display:block;margin-top:9px;font-size:25px}.pos strong{color:#3d9189}.neg strong{color:var(--red)}section{margin-top:28px}.kicker{margin:0 0 5px;color:var(--teal);font-size:9px;font-weight:800;letter-spacing:.15em}h2{margin:0 0 13px;font-size:19px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.panel{overflow:hidden}.panel h3{margin:0;padding:18px 20px;border-bottom:1px solid #eee9e2;font-size:14px}.cloud{display:flex;gap:8px;flex-wrap:wrap;padding:18px}.pill{padding:7px 9px;border-radius:9px;background:var(--teal2);color:#427d79;font-size:11px}.pill.red{background:var(--red2);color:#a05a52}.pill b{margin-left:5px;font-size:9px;opacity:.7}.insight{padding:17px 20px;border-bottom:1px solid #f0ece6}.insight:last-child{border:0}.head{display:flex;justify-content:space-between;gap:12px;font-weight:700;font-size:13px}.badge{padding:4px 7px;border-radius:7px;background:var(--red2);color:#a45c53;font-size:9px}.chain{margin:9px 0;color:#6f7976;font-size:11px;line-height:1.7}blockquote{margin:8px 0 0;padding:9px 11px;border-left:3px solid #d6e8e5;background:#faf9f7;color:#59635f;font-size:10px}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;min-width:700px}th,td{padding:12px 14px;text-align:left;border-top:1px solid #eeeae4;font-size:10px}th{background:#faf8f5;color:#8f9592}a{color:#378a86}footer{margin-top:30px;color:#999;font-size:10px}@media(max-width:820px){.shell{grid-template-columns:1fr}aside{position:static;height:auto}.note{display:none}.metrics{grid-template-columns:repeat(2,1fr)}}@media(max-width:620px){main{padding:22px 14px}header{flex-direction:column}.grid{grid-template-columns:1fr}}
</style></head><body><div class="shell"><aside><div class="brand"><span class="mark">评</span><span>用户评论监测</span></div><div class="nav">抖音数据总览</div><div class="note">只显示抖音。观点均来自本次样本，可回链到原始帖子与脱敏评论。</div></aside><main><header><div><p class="eyebrow">DOUYIN COMMENT MONITOR</p><h1>__TITLE__</h1><p class="sub">__SUBTITLE__</p></div><div class="tabs" id="tabs"></div></header><div id="app"></div><footer>单文件离线报告 · 结论只代表已采集样本，不代表抖音平台总体。</footer></main></div><script>const DATA=__DATA__,E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),F=n=>new Intl.NumberFormat('zh-CN').format(n),tabs=document.querySelector('#tabs'),app=document.querySelector('#app');DATA.forEach((s,i)=>{let b=document.createElement('button');b.textContent=s.label.split('｜')[1];b.onclick=()=>render(i);tabs.appendChild(b)});function render(i){[...tabs.children].forEach((b,j)=>b.classList.toggle('active',i===j));let s=DATA[i],cloud=(a,r)=>a.map(x=>`<span class="pill ${r?'red':''}">${E(x[0])}<b>${F(x[1])}</b></span>`).join('')||'<span class="sub">无可靠主题</span>',ins=s.insights.map(x=>`<div class="insight"><div class="head"><span>${E(x.name)}</span><span class="badge">${E(x.strength)} · ${x.count} 条</span></div><div class="chain">可能原因：${E(x.cause)}<br>建议动作：${E(x.action)}<br>负责团队：${E(x.team)} · 验证指标：${E(x.metric)}</div>${x.evidence.map(e=>`<blockquote>“${E(e.text)}” · 赞 ${F(e.likes)}</blockquote>`).join('')}</div>`).join('')||'<div class="insight">当前样本未形成可归类的负面关心点。</div>',rows=s.top.map(p=>`<tr><td><a href="${E(p.url)}" target="_blank" rel="noopener">${E(p.text||'无标题')}</a></td><td>${F(p.likes)}</td><td>${F(p.comments)}</td><td>推测</td></tr>`).join('');app.innerHTML=`${s.small?'<div class="warning">小样本，仅供定性参考；正式发布前请完成人工复核。</div>':''}<div class="metrics"><article class="card"><span>匹配帖子</span><strong>${F(s.posts)}</strong></article><article class="card"><span>有效评论</span><strong>${F(s.comments)}</strong></article><article class="card pos"><span>正面占比</span><strong>${(s.shares.positive*100).toFixed(1)}%</strong></article><article class="card neg"><span>负面占比</span><strong>${(s.shares.negative*100).toFixed(1)}%</strong></article></div><section><p class="kicker">WHAT PEOPLE SAY</p><h2>高频主题</h2><div class="grid"><article class="panel"><h3>正面高频词 Top 10</h3><div class="cloud">${cloud(s.pos,false)}</div></article><article class="panel"><h3>负面高频词 Top 10</h3><div class="cloud">${cloud(s.neg,true)}</div></article></div></section><section><p class="kicker">USER NEEDS</p><h2>用户关心点与问题链路</h2><article class="panel">${ins}</article></section><section><p class="kicker">CONTENT LEADS</p><h2>高互动帖子</h2><article class="panel scroll"><table><thead><tr><th>帖子</th><th>点赞</th><th>评论</th><th>结论强度</th></tr></thead><tbody>${rows}</tbody></table></article></section>`}render(0);</script></body></html>'''
 template=template.replace(",rows=s.top.map",",memeCards=s.memes.map(x=>`<div class=\"insight\"><div class=\"head\"><span>${E(x.name)}</span><span class=\"badge\">${E(x.strength)} · 热度 ${F(x.heat)}</span></div><div class=\"chain\"><b>复刻公式：</b>${E(x.formula)}<br><b>怎么玩：</b>${E(x.guide)}<br>来源 ${F(x.mentions)} 条（帖子 ${F(x.posts)} · 评论 ${F(x.comments)}）· 互动基数 ${F(x.engagement)}</div>${x.evidence.map(e=>`<blockquote><b>${e.url?'<a href=\"'+E(e.url)+'\" target=\"_blank\" rel=\"noopener\">'+E(e.source)+'</a>':E(e.source)}</b> · “${E(e.text)}” · 赞 ${F(e.likes)}</blockquote>`).join('')}</div>`).join('')||'<div class=\"insight\">当前样本未识别到达到热度门槛的可复刻玩梗。</div>',rows=s.top.map")
 template=template.replace('<section><p class="kicker">USER NEEDS</p><h2>用户关心点与问题链路</h2>', '<section><p class="kicker">REPLICABLE MEMES</p><h2>可复刻玩梗</h2><p class="sub">从高赞帖子及其高赞评论中识别，只展示能抽象出复刻公式的表达模板，并按互动热度排序。</p><article class="panel">${memeCards}</article></section><section><p class="kicker">USER NEEDS</p><h2>用户关心点与问题链路</h2>')
 search='''<div><form id="searchForm" style="display:flex;gap:6px;margin-bottom:10px"><input id="keyword" aria-label="监测关键词" placeholder="输入关键词" style="width:210px;padding:10px 12px;border:1px solid #ddd7ce;border-radius:10px;background:#fff;font:inherit"><button style="border:0;border-radius:10px;padding:10px 14px;background:#4a9d9a;color:#fff;cursor:pointer">快速监测</button><button id="deepBtn" type="button" style="border:1px solid #4a9d9a;border-radius:10px;padding:10px 14px;background:#fff;color:#397f7c;cursor:pointer">深度监测</button></form><div class="tabs" id="tabs"></div></div>'''
 search_js='''const CURRENT_KEYWORD=__CURRENT_KEYWORD__;async function poll(id){let s=document.querySelector('#status');for(;;){let r=await fetch('/api/status?id='+encodeURIComponent(id)),j=await r.json();s.textContent=j.message||j.status;if(j.status==='done'){location.href=j.result;return}if(j.status==='error')return;await new Promise(x=>setTimeout(x,2000))}}async function startRun(k,mode){let s=document.querySelector('#status');if(!k)return;if(location.protocol==='file:'){s.textContent='监测需要通过 Skill 的本地页面启动器打开。';return}s.textContent=mode==='deep'?'正在创建深度监测任务…':'正在创建快速监测任务…';let r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keyword:k,mode})}),j=await r.json();if(!r.ok){s.textContent=j.error||'任务创建失败';return}poll(j.id)}document.querySelector('#searchForm').onsubmit=e=>{e.preventDefault();startRun(document.querySelector('#keyword').value.trim(),'quick')};document.querySelector('#deepBtn').onclick=()=>startRun(CURRENT_KEYWORD,'deep');'''
 template=template.replace('<div class="tabs" id="tabs"></div>',search).replace('<div id="app"></div>','<div id="status" class="sub"></div><div id="app"></div>').replace('render(0);</script>',search_js+'render(0);</script>')
 keyword_json=json.dumps(current_keyword,ensure_ascii=False).replace("</","<\\/")
 return template.replace("__TITLE__",html.escape(title)).replace("__SUBTITLE__",html.escape(subtitle)).replace("__DATA__",payload).replace("__CURRENT_KEYWORD__",keyword_json)

def parser():
 p=argparse.ArgumentParser(description="用户评论监测：分析授权 JSONL，不执行网页采集")
 p.add_argument("--export-root",required=True);p.add_argument("--platform",choices=["dy"],default="dy",help="仅支持抖音");p.add_argument("--keywords",required=True);p.add_argument("--synonyms",default="");p.add_argument("--exclude-keywords",default="");p.add_argument("--target-type",choices=["domain","topic","creator","post"],default="topic");p.add_argument("--creator-id",default="");p.add_argument("--creator-scope",choices=["owned_posts","platform_mentions"],default="platform_mentions");p.add_argument("--post-url",action="append",default=[]);p.add_argument("--output",required=True,help="主输出页面 .html；若给其他后缀会自动改为 .html");p.add_argument("--markdown-output",help="可选 Markdown 追溯附件");p.add_argument("--review-output");p.add_argument("--six-month-days",type=int,default=180);p.add_argument("--seven-day-days",type=int,default=7);p.add_argument("--post-limit",type=int,default=100);p.add_argument("--comment-limit",type=int,default=100);p.add_argument("--comment-candidate-limit",type=int,default=500);p.add_argument("--like-weight",type=float,default=1);p.add_argument("--comment-weight",type=float,default=2);p.add_argument("--timezone",default="Asia/Shanghai");p.add_argument("--as-of");return p
def split(s):return [x.strip() for x in re.split(r"[,，]",s) if x.strip()]
def main(argv=None):
 p=parser();a=p.parse_args(argv);a.exclude=split(a.exclude_keywords);a.synonyms=split(a.synonyms);keys=split(a.keywords)
 for name in ("six_month_days","seven_day_days","post_limit","comment_limit","comment_candidate_limit"):
  if getattr(a,name)<=0:p.error(f"--{name.replace('_','-')} 必须大于 0")
 if a.comment_candidate_limit<a.comment_limit:p.error("--comment-candidate-limit 不能小于 --comment-limit")
 if a.target_type=="creator" and a.creator_scope=="owned_posts" and not (a.creator_id or a.post_url):p.error("达人内容评论需提供 --creator-id 或 --post-url，不能只用昵称")
 if a.target_type=="post" and not a.post_url:p.error("帖子监测需提供 --post-url")
 tz=ZoneInfo(a.timezone);now=dt(a.as_of).astimezone(tz) if a.as_of else datetime.now(tz);platforms=["dy"];S=snownlp();posts,comments,stats,warnings=load(pathlib.Path(a.export_root),platforms,set(keys+a.synonyms),a)
 sections=[analyze("dy",f"抖音｜近{a.six_month_days}天",a.six_month_days,posts,comments,a,now,S),analyze("dy",f"抖音｜近{a.seven_day_days}天",a.seven_day_days,posts,comments,a,now,S)]
 rc=review(pathlib.Path(a.review_output),sections) if a.review_output else 0
 L=["# 用户评论监测报告","","## 监测说明","",f"- 监测对象：{a.target_type}",f"- 关键词：{'、'.join(keys)}",f"- 平台：{'、'.join(platforms)}",f"- 执行时间：{now:%Y-%m-%d %H:%M} {a.timezone}","- 来源：授权导出；本脚本不进行网页采集",f"- 原始覆盖：帖子 {stats['raw_posts']}、评论 {stats['raw_comments']}、文件 {stats['files']}",f"- 清洗损耗：异常 {stats['invalid']}、缺 ID {stats['missing_id']}、目标不匹配 {stats['target_filtered']}、回复 {stats['replies']}、垃圾 {stats['spam']}、重复 {stats['duplicates']}",f"- 有效量：帖子 {len(posts)}、一级评论 {len(comments)}",f"- 情绪引擎：{'SnowNLP＋规则' if S else '词典规则（未安装 SnowNLP）'}；仅作辅助",f"- 人工抽检：{'已生成 '+str(rc)+' 条待复核记录' if a.review_output else '未执行；正式发布前应生成复核 CSV'}","","> 本报告反映已采集样本中的用户表达，不代表全平台用户总体。近7天是长周期子集。",""]
 for i,s in enumerate(sections):L+=render(s,"一二"[i],tz,a)
 L += ["## 三、跨时间窗洞察","","- 仅比较同口径且样本充分的时间窗；没有历史快照时不输出环比。","- 达人发布内容下的评论与全平台讨论达人属于不同样本域，不合并。","","## 附录：异常追溯",""]+[f"- {cell(x)}" for x in warnings]
 out=pathlib.Path(a.output).with_suffix(".html");out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(page(sections,"用户评论监测",f"抖音 · 关键词：{'、'.join(keys)} · {now:%Y-%m-%d %H:%M} · 来源明确的评论样本",",".join(keys)),encoding="utf-8")
 if a.markdown_output:
  md=pathlib.Path(a.markdown_output);md.parent.mkdir(parents=True,exist_ok=True);md.write_text("\n".join(L)+"\n",encoding="utf-8")
 print("page written:",out);return 0
if __name__=="__main__":raise SystemExit(main())

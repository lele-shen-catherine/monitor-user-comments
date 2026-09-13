#!/usr/bin/env python3
"""在本机启动抖音评论监测页面，并连接已安装的 MediaCrawler。"""
from __future__ import annotations
import argparse, json, os, pathlib, re, shutil, subprocess, sys, threading, uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

JOBS: dict[str, dict] = {}

HOME='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>用户评论监测</title><style>
:root{--bg:#f7f4ef;--ink:#263432;--teal:#4a9d9a;--soft:#e8f4f2;--line:#e9e4dc}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif}.shell{min-height:100vh;display:grid;place-items:center;padding:24px}.card{width:min(680px,100%);padding:42px;background:#fff;border:1px solid var(--line);border-radius:24px;box-shadow:0 20px 55px rgba(43,51,49,.08)}.mark{width:44px;height:44px;display:grid;place-items:center;border-radius:14px;background:var(--teal);color:#fff;font-weight:800}.eyebrow{margin:24px 0 8px;color:var(--teal);font-size:10px;font-weight:800;letter-spacing:.16em}h1{margin:0;font-size:30px}p{color:#8e9794;line-height:1.7;font-size:13px}form{display:flex;gap:8px;margin-top:28px}input{flex:1;min-width:0;padding:14px 16px;border:1px solid #ddd7ce;border-radius:12px;font:inherit;font-size:14px;outline:none}input:focus{border-color:var(--teal);box-shadow:0 0 0 3px rgba(74,157,154,.13)}button{border:0;border-radius:12px;padding:14px 20px;background:var(--teal);color:#fff;font-weight:700;cursor:pointer}.status{min-height:22px;margin-top:16px;color:#5c7470;font-size:12px}.scope{margin-top:26px;padding:14px;background:var(--soft);border-radius:12px;color:#4c7773;font-size:11px;line-height:1.7}</style></head><body><div class="shell"><main class="card"><div class="mark">评</div><p class="eyebrow">DOUYIN COMMENT MONITOR</p><h1>用户评论监测</h1><p>输入任何想监测的关键词。系统将采集抖音公开可见样本，分析用户关心点，并生成可视化页面。</p><form id="f"><input id="k" placeholder="例如：京东外卖、家政服务、即时零售" autofocus><button>开始监测</button></form><div class="status" id="s"></div><div class="scope">默认最多采集 100 个视频、每个视频 100 条一级评论。首次运行可能需要在浏览器中完成抖音登录或验证；程序不会读取或展示 Cookie。</div></main></div><script>const f=document.querySelector('#f'),s=document.querySelector('#s');async function poll(id){for(;;){let r=await fetch('/api/status?id='+id),j=await r.json();s.textContent=j.message||j.status;if(j.status==='done'){location.href=j.result;return}if(j.status==='error')return;await new Promise(x=>setTimeout(x,2000))}}f.onsubmit=async e=>{e.preventDefault();let keyword=document.querySelector('#k').value.trim();if(!keyword)return;s.textContent='正在创建监测任务…';let r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keyword})}),j=await r.json();if(!r.ok){s.textContent=j.error||'创建失败';return}poll(j.id)};</script></body></html>'''
HOME=HOME.replace("系统将采集抖音公开可见样本，分析用户关心点，并生成可视化页面。","系统会先分析 20 条高赞帖子及每帖最多 50 条高赞评论，识别用户关心点和可复刻玩梗，并生成可视化页面。")
HOME=HOME.replace("默认最多采集 100 个视频、每个视频 100 条一级评论。首次运行可能需要在浏览器中完成抖音登录或验证；程序不会读取或展示 Cookie。","默认执行快速监测（20 条高赞帖子 × 每帖最多 50 条评论）。结果页可选择深度监测。首次运行可能需要登录，之后复用本机登录状态；状态失效时才会再次要求登录。")
HOME=HOME.replace("<button>开始监测</button>","<button>快速监测</button>")

def command_for(root: pathlib.Path, run_dir: pathlib.Path, keyword: str, max_posts: int, max_comments: int):
    venv_python=root/".venv/bin/python"
    launch="import config,runpy;config.ENABLE_CDP_MODE=False;runpy.run_path('main.py',run_name='__main__')"
    base=[str(venv_python),"-c",launch] if venv_python.exists() else ([shutil.which("uv"),"run","python","-c",launch] if shutil.which("uv") else None)
    if not base: raise RuntimeError("未找到 MediaCrawler 的 .venv 或 uv")
    return base+["--platform","dy","--lt","qrcode","--type","search","--keywords",keyword,"--save_data_option","jsonl","--save_data_path",str(run_dir),"--get_comment","true","--get_sub_comment","false","--crawler_max_notes_count",str(max_posts),"--max_comments_count_singlenotes",str(max_comments),"--headless","false"]

def has_jsonl_record(paths):
    for path in paths:
        try:
            with path.open(encoding="utf-8-sig",errors="replace") as handle:
                if any(line.strip() for line in handle): return True
        except OSError:
            continue
    return False

def execute(job_id: str, cfg, keyword: str, mode: str):
    job=JOBS[job_id]
    try:
        max_posts,max_comments=(cfg.max_posts,cfg.max_comments) if mode=="deep" else (cfg.quick_posts,cfg.quick_comments)
        run_dir=cfg.workspace/job_id;run_dir.mkdir(parents=True,exist_ok=True)
        mode_name="深度监测" if mode=="deep" else "快速监测"
        job.update(status="collecting",message=f"正在执行{mode_name}：{max_posts} 条高赞帖子，每帖最多 {max_comments} 条评论；登录状态失效时请在浏览器中重新登录。")
        env=os.environ.copy();env["DY_SORT_TYPE"]="1";env["DY_PUBLISH_TIME_TYPE"]="180"
        mpl_cache=cfg.workspace/".matplotlib";mpl_cache.mkdir(parents=True,exist_ok=True);env["MPLCONFIGDIR"]=str(mpl_cache)
        log=run_dir/"collector.log"
        with log.open("w",encoding="utf-8") as handle:
            result=subprocess.run(command_for(cfg.collector_root,run_dir,keyword,max_posts,max_comments),cwd=cfg.collector_root,env=env,stdout=handle,stderr=subprocess.STDOUT,text=True,timeout=cfg.timeout)
        if result.returncode: raise RuntimeError(f"采集器退出码 {result.returncode}；请查看 {log.name}")
        if not has_jsonl_record(run_dir.glob("*/jsonl/*contents_*.jsonl")):
            raise RuntimeError("采集器未返回任何帖子；可能是登录、验证、风控或搜索失败，请查看 collector.log")
        job.update(status="analyzing",message="采集完成，正在清洗、脱敏和生成页面…")
        output=cfg.results/f"{job_id}.html";review=cfg.results/f"{job_id}-review.csv"
        cmd=[sys.executable,str(pathlib.Path(__file__).with_name("analyze_export.py")),"--export-root",str(run_dir),"--keywords",keyword,"--output",str(output),"--review-output",str(review),"--post-limit",str(max_posts),"--comment-limit",str(max_comments),"--comment-candidate-limit",str(max_comments)]
        done=subprocess.run(cmd,capture_output=True,text=True,timeout=600)
        if done.returncode: raise RuntimeError(done.stderr.strip() or "分析失败")
        job.update(status="done",message=f"{mode_name}完成，正在打开结果页面。",result=f"/results/{output.name}")
    except Exception as exc:
        job.update(status="error",message=f"任务失败：{exc}")

class Handler(BaseHTTPRequestHandler):
    cfg=None
    def send(self,status,body,ctype="application/json; charset=utf-8"):
        data=body.encode("utf-8");self.send_response(status);self.send_header("Content-Type",ctype);self.send_header("Content-Length",str(len(data)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(data)
    def do_GET(self):
        url=urlparse(self.path)
        if url.path=="/": return self.send(200,HOME,"text/html; charset=utf-8")
        if url.path=="/api/status":
            job=JOBS.get(parse_qs(url.query).get("id",[""])[0]);return self.send(200,json.dumps(job or {"status":"error","message":"任务不存在"},ensure_ascii=False))
        if url.path.startswith("/results/"):
            name=pathlib.Path(url.path).name;path=self.cfg.results/name
            if path.exists(): return self.send(200,path.read_text(encoding="utf-8"),"text/html; charset=utf-8")
        return self.send(404,json.dumps({"error":"未找到"},ensure_ascii=False))
    def do_POST(self):
        if self.path!="/api/run": return self.send(404,'{"error":"未找到"}')
        try:
            length=min(int(self.headers.get("Content-Length","0")),4096);payload=json.loads(self.rfile.read(length));keyword=str(payload.get("keyword","")).strip();mode=str(payload.get("mode","quick"))
            if not 1<=len(keyword)<=60 or re.search(r"[\x00-\x1f]",keyword): raise ValueError("关键词长度应为 1–60 个字符")
            if mode not in ("quick","deep"): raise ValueError("监测模式无效")
            if any(j["status"] in ("collecting","analyzing") for j in JOBS.values()): raise ValueError("已有任务运行中，请等待完成")
            job_id=datetime.now().strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:6];JOBS[job_id]={"status":"queued","message":"任务已排队","keyword":keyword,"mode":mode}
            threading.Thread(target=execute,args=(job_id,self.cfg,keyword,mode),daemon=True).start();return self.send(202,json.dumps({"id":job_id},ensure_ascii=False))
        except Exception as exc:return self.send(400,json.dumps({"error":str(exc)},ensure_ascii=False))
    def log_message(self,*_): pass

def main():
    p=argparse.ArgumentParser(description="启动用户评论监测本地页面")
    p.add_argument("--collector-root",type=pathlib.Path,required=True,help="MediaCrawler 项目目录")
    p.add_argument("--workspace",type=pathlib.Path,default=pathlib.Path("runs"));p.add_argument("--results",type=pathlib.Path,default=pathlib.Path("reports"));p.add_argument("--port",type=int,default=8765);p.add_argument("--quick-posts",type=int,default=20);p.add_argument("--quick-comments",type=int,default=50);p.add_argument("--max-posts",type=int,default=100);p.add_argument("--max-comments",type=int,default=100);p.add_argument("--timeout",type=int,default=3600)
    cfg=p.parse_args();cfg.collector_root=cfg.collector_root.resolve();cfg.workspace=cfg.workspace.resolve();cfg.results=cfg.results.resolve();cfg.results.mkdir(parents=True,exist_ok=True)
    if not (cfg.collector_root/"main.py").exists():p.error("--collector-root 不是有效的 MediaCrawler 目录")
    Handler.cfg=cfg;server=ThreadingHTTPServer(("127.0.0.1",cfg.port),Handler);print(f"open http://127.0.0.1:{cfg.port}");server.serve_forever()
if __name__=="__main__":main()

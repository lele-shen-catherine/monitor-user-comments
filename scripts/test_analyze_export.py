import json, pathlib, subprocess, sys, tempfile, unittest
from scripts.analyze_export import memes
from scripts.run_ui import HOME, command_for, has_jsonl_record

SCRIPT=pathlib.Path(__file__).with_name("analyze_export.py")
UI=pathlib.Path(__file__).with_name("run_ui.py")

class MonitorTests(unittest.TestCase):
 def write(self,root,platform,name,rows):
  d=root/platform/"jsonl";d.mkdir(parents=True,exist_ok=True)
  (d/name).write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in rows),encoding="utf-8")
 def test_help_without_snownlp(self):
  r=subprocess.run([sys.executable,str(SCRIPT),"--help"],capture_output=True,text=True)
  self.assertEqual(r.returncode,0);self.assertIn("不执行网页采集",r.stdout)
 def test_ui_launcher_help(self):
  r=subprocess.run([sys.executable,str(UI),"--help"],capture_output=True,text=True)
  self.assertEqual(r.returncode,0);self.assertIn("MediaCrawler",r.stdout);self.assertIn("快速监测",HOME);self.assertIn("20 条高赞帖子",HOME)
 def test_collector_reuses_local_browser_profile(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);py=root/".venv/bin/python";py.parent.mkdir(parents=True);py.write_text("")
   cmd=command_for(root,root/"run","外卖",20,50)
  self.assertIn("config.ENABLE_CDP_MODE=True",cmd[2]);self.assertIn("--crawler_max_notes_count",cmd);self.assertEqual(cmd[cmd.index("--crawler_max_notes_count")+1],"20");self.assertEqual(cmd[cmd.index("--max_comments_count_singlenotes")+1],"50")
 def test_empty_collector_output_is_not_success(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);empty=root/"dy/jsonl/a_contents_1.jsonl";empty.parent.mkdir(parents=True);empty.write_text("\n")
   self.assertFalse(has_jsonl_record(root.glob("*/jsonl/*contents_*.jsonl")))
   empty.write_text('{"aweme_id":"1"}\n');self.assertTrue(has_jsonl_record(root.glob("*/jsonl/*contents_*.jsonl")))
 def test_same_commenter_cannot_inflate_meme_mentions(self):
  base={"platform":"dy","source_type":"评论","creator_id":"same-user","text":"这谁顶得住","like_count":6,"engagement":6,"source_url":""}
  items=[dict(base,item_key=("评论","dy","c1")),dict(base,item_key=("评论","dy","c2"))]
  self.assertEqual(memes(items),[])
 def test_douyin_only_redaction_and_html_page(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);stamp="2026-09-01T12:00:00+08:00"
   self.write(root,"dy","a_contents_1.jsonl",[{"aweme_id":"same","desc":"外卖配送 联系13812345678","source_url":"javascript:alert(1)","create_time":stamp,"liked_count":10}])
   self.write(root,"dy","a_comments_1.jsonl",[{"comment_id":"samec","aweme_id":"same","content":"配送慢 联系我13812345678","create_time":stamp,"like_count":9}])
   self.write(root,"xhs","a_contents_1.jsonl",[{"note_id":"same","title":"外卖不错","time":stamp,"liked_count":1}])
   self.write(root,"xhs","a_comments_1.jsonl",[{"comment_id":"samec","note_id":"same","content":"很满意","create_time":stamp,"like_count":1}])
   report=root/"report.html";review=root/"review.csv"
   r=subprocess.run([sys.executable,str(SCRIPT),"--export-root",str(root),"--keywords","外卖","--output",str(report),"--review-output",str(review),"--as-of","2026-09-10T00:00:00+08:00","--comment-limit","1","--comment-candidate-limit","1"],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   text=report.read_text();self.assertIn("手机号已脱敏",text);self.assertIn("抖音数据总览",text);self.assertIn("<h1>用户评论监测</h1>",text);self.assertIn("关键词：外卖",text);self.assertNotIn("外卖 · 用户评论监测",text)
   self.assertIn("抖音｜近180天",text);self.assertNotIn("小红书｜近180天",text);self.assertNotIn("很满意",text)
   self.assertIn("快速监测",text);self.assertIn("深度监测",text);self.assertIn('CURRENT_KEYWORD="外卖"',text)
   self.assertNotIn("13812345678",text);self.assertNotIn("javascript:alert",text);self.assertIn("https://www.douyin.com/video/same",text);self.assertTrue(review.exists())
 def test_candidate_limit_validation(self):
  r=subprocess.run([sys.executable,str(SCRIPT),"--export-root","x","--keywords","x","--output","x","--comment-limit","10","--comment-candidate-limit","2"],capture_output=True,text=True)
  self.assertNotEqual(r.returncode,0);self.assertIn("不能小于",r.stderr)
 def test_meme_heat_section_and_threshold(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);stamp="2026-09-09T12:00:00+08:00"
   self.write(root,"dy","a_contents_1.jsonl",[
    {"aweme_id":"p1","desc":"外卖实测","create_time":stamp,"liked_count":50},
    {"aweme_id":"p2","desc":"外卖创意：奶来，妈妈接你回家","create_time":stamp,"liked_count":100,"comment_count":20}])
   self.write(root,"dy","a_comments_1.jsonl",[
    {"comment_id":"c1","aweme_id":"p1","content":"不是哥们，这也行","create_time":stamp,"like_count":12},
    {"comment_id":"c2","aweme_id":"p1","content":"不是哥们，这也行啊","create_time":stamp,"like_count":8},
    {"comment_id":"c3","aweme_id":"p1","content":"小丑竟是我自己","create_time":stamp,"like_count":20},
    {"comment_id":"c4","aweme_id":"p1","content":"主打一个随缘","create_time":stamp,"like_count":1},
    {"comment_id":"c5","aweme_id":"p1","content":"老师求图","create_time":stamp,"like_count":20},
    {"comment_id":"c6","aweme_id":"p1","content":"老师求图","create_time":stamp,"like_count":20},
    {"comment_id":"c7","aweme_id":"p1","content":"我嘞个豆","create_time":stamp,"like_count":0},
    {"comment_id":"c8","aweme_id":"p1","content":"我嘞个豆","create_time":stamp,"like_count":0}])
   report=root/"report.html"
   r=subprocess.run([sys.executable,str(SCRIPT),"--export-root",str(root),"--keywords","外卖","--output",str(report),"--as-of","2026-09-10T00:00:00+08:00","--comment-limit","5","--comment-candidate-limit","10"],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr);text=report.read_text()
   self.assertIn("<h2>可复刻玩梗</h2>",text);self.assertIn("不是哥们，XX",text);self.assertIn("小丑竟是我自己",text)
   self.assertIn("XX来，妈妈XX",text);self.assertIn('"posts": 1',text);self.assertIn("帖子 ${F(x.posts)} · 评论",text)
   self.assertNotIn('"name": "主打一个XX"',text);self.assertNotIn('"name": "我嘞个XX"',text);self.assertNotIn("高频复读：老师求图",text);self.assertIn('"heat": 30',text)

if __name__=="__main__":unittest.main()

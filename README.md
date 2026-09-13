# monitor-user-comments

用于抖音帖子与用户评论样本的监测和分析。支持任意关键词、快速与深度监测、隐私脱敏、用户关心点识别、可复刻玩梗分析，以及自包含 HTML 报告。

## 一键安装与启动

下载仓库 ZIP 并解压后：

- macOS：双击 `启动.command`
- Windows：双击 `启动.bat`

首次启动会自动配置 Python 3.11、项目虚拟环境、Node.js 和 MediaCrawler。SnowNLP 0.12.3 的离线安装包已经包含在 `vendor/`。首次安装 MediaCrawler 时需要阅读并接受其非商业学习许可证，下载量较大；以后启动会复用本机环境和抖音登录状态。

电脑需要已安装 Chrome 或 Edge。采集器会自动调用本机浏览器，避免额外下载一套 Chromium，也更便于复用登录状态。

安装完成后会自动打开 `http://127.0.0.1:8765`。输入关键词即可开始快速监测。

## 手动使用

完整的数据边界、运行方法和质量要求见 [`SKILL.md`](SKILL.md)。

运行本地页面：

```bash
python scripts/run_ui.py \
  --collector-root /path/to/MediaCrawler \
  --workspace runs \
  --results reports
```

默认快速监测 20 条高赞帖子、每帖最多 50 条一级评论。结果页可由用户选择深度监测，扩展到最多 100 条帖子、每帖 100 条评论。

第三方组件的来源、版本和授权限制见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

## 数据与合规

- 仅处理来源明确、获准使用的数据。
- 不绕过登录、验证码、访问控制、风控或平台条款。
- 浏览器登录状态只保存在本机，不上传到仓库。
- 安装器从 MediaCrawler 官方仓库下载固定版本并保留原许可证。该项目仅供非商业学习研究；商业使用前应获得版权所有者书面许可，或改用官方接口、企业后台导出或合规供应商。

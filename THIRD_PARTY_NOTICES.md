# 第三方组件说明

## SnowNLP 0.12.3

仓库在 `vendor/` 中包含 SnowNLP 0.12.3 的离线 wheel。SnowNLP 使用 MIT License：

Copyright (c) 2013-2014 isnowfy

完整许可证随 wheel 保存，也可在 [SnowNLP 官方仓库](https://github.com/isnowfy/snownlp) 查看。

## MediaCrawler

MediaCrawler 不复制进本仓库。一键安装器从其官方仓库下载并固定到提交
`d6f7c5bb906b6dac40ddf343ef9e26438a3de092`，原始版权和 LICENSE 均保留在
`.runtime/MediaCrawler/`。

MediaCrawler 使用 NON-COMMERCIAL LEARNING LICENSE 1.1，仅允许非商业学习和研究，禁止商业使用、大规模采集以及干扰平台运行。使用者首次安装时必须自行接受该许可证。

- 官方仓库：https://github.com/NanmiCoder/MediaCrawler
- 许可证：https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE

## Python、uv、Node.js 与浏览器

Python、uv 和 Node.js 不直接复制进仓库。一键安装器根据使用者的操作系统和 CPU 架构，通过官方安装渠道下载到本机，避免分发错误或过期的系统安装镜像。采集时调用使用者已安装的 Chrome 或 Edge。

- Python：https://www.python.org/
- uv：https://github.com/astral-sh/uv
- Node.js：https://nodejs.org/
- Playwright：https://playwright.dev/

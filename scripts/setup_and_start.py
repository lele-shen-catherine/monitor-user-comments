#!/usr/bin/env python3
"""Install the local runtime and launch the comment-monitoring UI."""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request
import zipfile


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNTIME_ROOT = APP_ROOT / ".runtime"
MEDIACRAWLER_ROOT = RUNTIME_ROOT / "MediaCrawler"
MEDIACRAWLER_COMMIT = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
MEDIACRAWLER_ARCHIVE = (
    "https://github.com/NanmiCoder/MediaCrawler/archive/"
    f"{MEDIACRAWLER_COMMIT}.zip"
)
MEDIACRAWLER_SHA256 = "dba5c67d39f3e69b24c00bbce28e11b7d30cd051ef104e3e0c7f8c490288dfd8"
SNOWNLP_SHA256 = "78e39631df5465544acb3ca1b419aa5e0ce05ebbb15e8b40b67dfaf2da9273ab"
SETUP_MARKER = RUNTIME_ROOT / ".setup-complete-v1"


def run(*args: str, cwd: pathlib.Path | None = None) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def python_in(venv: pathlib.Path) -> pathlib.Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def accept_mediacrawler_license(non_interactive: bool) -> None:
    if os.environ.get("ACCEPT_MEDIACRAWLER_LICENSE") == "1":
        return
    if non_interactive:
        raise RuntimeError(
            "安装 MediaCrawler 前必须接受其非商业学习许可证；"
            "设置 ACCEPT_MEDIACRAWLER_LICENSE=1 后重试。"
        )
    print(
        "\nMediaCrawler 仅授权非商业学习和研究使用，禁止商业使用、"
        "大规模采集或干扰平台运行。\n"
        "许可证：https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE\n"
    )
    answer = input("接受上述许可证并从官方仓库下载？[y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        raise RuntimeError("用户未接受 MediaCrawler 许可证，安装已取消。")


def download(url: str, destination: pathlib.Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "monitor-user-comments-installer"})
    context = ssl.create_default_context()
    try:
        import certifi  # type: ignore

        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    with urllib.request.urlopen(request, timeout=120, context=context) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def verify_sha256(path: pathlib.Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise RuntimeError(f"下载文件校验失败：{path.name}")


def install_mediacrawler(non_interactive: bool) -> None:
    marker = MEDIACRAWLER_ROOT / ".installed_commit"
    if (MEDIACRAWLER_ROOT / "main.py").exists() and marker.exists():
        if marker.read_text(encoding="utf-8").strip() == MEDIACRAWLER_COMMIT:
            return
    accept_mediacrawler_license(non_interactive)
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="monitor-user-comments-") as temporary:
        archive = pathlib.Path(temporary) / "MediaCrawler.zip"
        print("正在从 MediaCrawler 官方仓库下载固定版本…", flush=True)
        download(MEDIACRAWLER_ARCHIVE, archive)
        verify_sha256(archive, MEDIACRAWLER_SHA256)
        with zipfile.ZipFile(archive) as package:
            package.extractall(temporary)
        extracted = pathlib.Path(temporary) / f"MediaCrawler-{MEDIACRAWLER_COMMIT}"
        if MEDIACRAWLER_ROOT.exists():
            shutil.rmtree(MEDIACRAWLER_ROOT)
        shutil.move(str(extracted), MEDIACRAWLER_ROOT)
    marker.write_text(MEDIACRAWLER_COMMIT + "\n", encoding="utf-8")


def install_dependencies(uv: str) -> pathlib.Path:
    app_venv = APP_ROOT / ".venv"
    app_python = python_in(app_venv)
    wheel = APP_ROOT / "vendor" / "snownlp-0.12.3-py3-none-any.whl"
    if not wheel.exists():
        raise RuntimeError(f"缺少离线 SnowNLP 安装包：{wheel}")
    verify_sha256(wheel, SNOWNLP_SHA256)
    media_python = python_in(MEDIACRAWLER_ROOT / ".venv")
    media_node = (MEDIACRAWLER_ROOT / ".venv" / ("Scripts/node.exe" if os.name == "nt" else "bin/node"))
    if SETUP_MARKER.exists() and app_python.exists() and media_python.exists() and media_node.exists():
        return app_python
    if not app_python.exists():
        run(uv, "venv", str(app_venv), "--python", "3.11")
    run(uv, "pip", "install", "--python", str(app_python), str(wheel))
    run(uv, "sync", "--directory", str(MEDIACRAWLER_ROOT), "--frozen")
    if not media_node.exists():
        run(
            uv,
            "run",
            "--directory",
            str(MEDIACRAWLER_ROOT),
            "nodeenv",
            "-p",
            "--node=22.20.0",
        )
    SETUP_MARKER.write_text("Python 3.11; SnowNLP 0.12.3; Node 22.20.0\n", encoding="utf-8")
    return app_python


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="安装并启动用户评论监测")
    parser.add_argument("--install-only", action="store_true", help="只安装，不启动页面")
    parser.add_argument("--yes", action="store_true", help="非交互模式；需预先接受第三方许可证")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("未找到 uv；请重新运行仓库根目录的一键启动文件。")
    install_mediacrawler(args.yes)
    app_python = install_dependencies(uv)
    print("\n安装完成。请在自己的浏览器中登录自己的抖音账号。\n", flush=True)
    if args.install_only:
        return 0
    run(
        str(app_python),
        str(APP_ROOT / "scripts" / "run_ui.py"),
        "--collector-root",
        str(MEDIACRAWLER_ROOT),
        "--workspace",
        str(APP_ROOT / "runs"),
        "--results",
        str(APP_ROOT / "reports"),
        "--port",
        str(args.port),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"\n安装或启动失败：{exc}", file=sys.stderr)
        raise SystemExit(1)

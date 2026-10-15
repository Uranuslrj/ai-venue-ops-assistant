"""One-file local launcher for the script-kill demo and optional hybrid retrieval.

Edit only the CONFIG section below. Keep this file private after entering a real key.
"""
from __future__ import annotations

import os
import runpy
import sys
import threading
import webbrowser
from pathlib import Path

# ===================== CONFIG: edit these values =====================
# Paste your NEW DashScope key between the quotes. Do not send it in chat.
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

# Use the endpoint shown by your DashScope console.
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# Use the exact model name available in your DashScope console.
DASHSCOPE_EMBEDDING_MODEL = "text-embedding-v4"
DASHSCOPE_EMBEDDING_DIMENSION = "1024"

# Recommended initial hybrid weights for this project.
RAG_BM25_WEIGHT = "0.6"
RAG_EMBEDDING_WEIGHT = "0.4"

# Local demo port.
PORT = "8775"
# =================== end of CONFIG section ==========================

WORK_DIR = Path(__file__).resolve().parent
APP_FILE = WORK_DIR / "app.py"


def main() -> None:
    if not APP_FILE.is_file():
        raise SystemExit(f"Project app not found: {APP_FILE}")
    if not DASHSCOPE_API_KEY.strip():
        print("No DASHSCOPE_API_KEY found; starting with local/BM25 fallback mode.")
    if "{WorkspaceId}" in DASHSCOPE_BASE_URL:
        raise SystemExit("Replace DASHSCOPE_BASE_URL with a real endpoint first.")

    if DASHSCOPE_API_KEY.strip():
        os.environ["DASHSCOPE_API_KEY"] = DASHSCOPE_API_KEY.strip()
    os.environ.update({
        "DASHSCOPE_BASE_URL": DASHSCOPE_BASE_URL.strip(),
        "DASHSCOPE_EMBEDDING_MODEL": DASHSCOPE_EMBEDDING_MODEL.strip(),
        "DASHSCOPE_EMBEDDING_DIMENSION": DASHSCOPE_EMBEDDING_DIMENSION.strip(),
        "RAG_BM25_WEIGHT": RAG_BM25_WEIGHT.strip(),
        "RAG_EMBEDDING_WEIGHT": RAG_EMBEDDING_WEIGHT.strip(),
        "PORT": PORT.strip(),
    })
    url = f"http://127.0.0.1:{PORT}/"
    print(f"Starting the demo at {url}")
    print("Embedding retrieval is enabled when DASHSCOPE_API_KEY is set; otherwise the demo uses local/BM25 fallback mode.")
    print("Close this window only when you want to stop the demo.")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    os.chdir(WORK_DIR)
    sys.argv = [str(APP_FILE)]
    runpy.run_path(str(APP_FILE), run_name="__main__")


if __name__ == "__main__":
    main()




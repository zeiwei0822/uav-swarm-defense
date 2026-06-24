# -*- coding: utf-8 -*-
"""
Flask 後端：無人機機群攻防模擬 web 服務（本機用）
================================================
路由：
  GET  /                  首頁
  GET  /plotly.js         離線提供 plotly.min.js
  POST /api/run           跑一場模擬 → 回傳 {figure, report, events, ai}
  GET  /api/figures       列出 figures/ 內的分析圖
  GET  /api/figure/<f>    回傳分析圖 PNG
  POST /api/task          啟動背景任務 train / analyze / export
  GET  /api/task/log      輪詢背景任務輸出
  POST /api/task/stop     中止背景任務

預設只綁 127.0.0.1（本機）。背景任務會在伺服器主機上執行 subprocess，
因此請勿在未加保護的情況下對外（0.0.0.0）開放。
"""
import os
import sys
import json
import threading
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)   # 確保 models/ figures/ data/ 等相對路徑正確（不論從何處啟動）

# 不依賴 PYTHONUTF8 環境變數即可輸出中文（避免 cp950 終端錯誤）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from flask import (Flask, request, jsonify, Response, send_from_directory,
                   render_template)
import plotly.io as pio

from config import Config
from core.engine import Simulation
from run_sim import load_ai
from web.plotly_viz import build_figure

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["TEMPLATES_AUTO_RELOAD"] = True   # 本機工具：改模板即生效
app.jinja_env.auto_reload = True

# 背景任務狀態（單一任務，本機單人使用）
_task = {"proc": None, "log": [], "name": None, "lock": threading.Lock()}


# ---------------------------------------------------------------- 頁面
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/plotly.js")
def plotly_js():
    """離線提供 plotly.min.js（不依賴 CDN/網路）"""
    from plotly.offline import get_plotlyjs
    return Response(get_plotlyjs(), mimetype="application/javascript")


# ---------------------------------------------------------------- 模擬
@app.route("/api/run", methods=["POST"])
def api_run():
    p = request.get_json(force=True)
    cfg = Config()
    cfg.swarm.formation = p.get("formation", "vee")
    cfg.swarm.n_drones = int(p.get("n", 21))
    cfg.swarm.n_relays = int(p.get("relays", 3))
    cfg.defense.policy = p.get("policy", "ai")
    cfg.sim.seed = int(p.get("seed", 901))
    ident_kind = p.get("identifier", "auto")

    try:
        ident, lstm = load_ai(cfg, ident_kind, quiet=True)
        sim = Simulation(cfg, identifier=ident, lstm=lstm)
        result = sim.run(verbose=False)
    except Exception as e:
        return jsonify(error=str(e)), 500

    fig = build_figure(sim.rec, cfg)
    events = [{"t": round(t, 1), "msg": m} for t, m in sim.rec.events]
    ai_txt = (f"{ident.name} + {'LSTM' if lstm else '卡爾曼濾波'}"
              if ident else "無防空")
    return Response(json.dumps({
        "figure": json.loads(pio.to_json(fig)),
        "report": result,
        "events": events,
        "ai": ai_txt,
    }), mimetype="application/json")


# ---------------------------------------------------------------- 分析圖
@app.route("/api/figures")
def api_figures():
    fdir = os.path.join(ROOT, "figures")
    names = []
    if os.path.isdir(fdir):
        names = sorted(f for f in os.listdir(fdir) if f.endswith(".png"))
    return jsonify(figures=names)


@app.route("/api/figure/<path:fname>")
def api_figure(fname):
    return send_from_directory(os.path.join(ROOT, "figures"), fname)


# ---------------------------------------------------------------- 背景任務
def _spawn(cmd, name):
    with _task["lock"]:
        if _task["proc"] and _task["proc"].poll() is None:
            return False
        _task["log"] = [f"▶ {name}\n{'='*48}\n"]
        _task["name"] = name
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
                   MPLBACKEND="Agg")

        def worker():
            try:
                proc = subprocess.Popen(
                    cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                    errors="replace", bufsize=1)
                _task["proc"] = proc
                for line in proc.stdout:
                    _task["log"].append(line)
                proc.wait()
                _task["log"].append(f"\n✔ {name} 完成\n")
            except Exception as e:
                _task["log"].append(f"[錯誤] {e}\n")
            finally:
                _task["proc"] = None

        threading.Thread(target=worker, daemon=True).start()
        return True


@app.route("/api/task", methods=["POST"])
def api_task():
    p = request.get_json(force=True)
    kind = p.get("kind")
    if kind == "train":
        cmd = [sys.executable, "-u", "train.py",
               "--episodes", str(int(p.get("episodes", 40)))]
        name = "訓練 AI 模型"
    elif kind == "analyze":
        cmd = [sys.executable, "-u", "analyze.py"]
        name = "產生分析圖"
    elif kind == "export":
        out = os.path.join(ROOT, f"battle_{p.get('formation','vee')}_"
                           f"{p.get('seed',901)}.mp4")
        cmd = [sys.executable, "-u", "run_sim.py",
               "--formation", p.get("formation", "vee"),
               "--policy", p.get("policy", "ai"),
               "--identifier", p.get("identifier", "auto"),
               "--n", str(int(p.get("n", 21))),
               "--relays", str(int(p.get("relays", 3))),
               "--seed", str(int(p.get("seed", 901))),
               "--no-anim", "--save", out]
        name = f"匯出動畫 → {os.path.basename(out)}"
    else:
        return jsonify(error="未知任務"), 400
    ok = _spawn(cmd, name)
    return jsonify(started=ok, name=name)


@app.route("/api/task/log")
def api_task_log():
    running = _task["proc"] is not None and _task["proc"].poll() is None
    return jsonify(log="".join(_task["log"]), running=running,
                   name=_task["name"])


@app.route("/api/task/stop", methods=["POST"])
def api_task_stop():
    if _task["proc"] and _task["proc"].poll() is None:
        _task["proc"].terminate()
        _task["log"].append("\n[已中止]\n")
        return jsonify(stopped=True)
    return jsonify(stopped=False)


def _check_models():
    cfg = Config()
    return (os.path.exists(cfg.ai.rf_path) and os.path.exists(cfg.ai.lstm_path))


@app.route("/api/status")
def api_status():
    return jsonify(models_ready=_check_models())


def main(host="127.0.0.1", port=8000, open_browser=True):
    url = f"http://{host}:{port}"
    print("=" * 56)
    print("  無人機機群攻防模擬 — Web 控制台")
    print(f"  伺服器啟動： {url}")
    print("  (Ctrl+C 結束；僅綁本機 127.0.0.1)")
    print("=" * 56)
    if open_browser:
        import webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    main(args.host, args.port, not args.no_browser)

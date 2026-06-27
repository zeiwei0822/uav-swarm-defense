# -*- coding: utf-8 -*-
"""
無人機機群攻防模擬 — 整合控制台 (GUI)
==========================================
單一視窗整合全部功能：
  · 參數設定（陣型/機數/中繼機/防方策略/識別器/種子）
  · 一鍵開戰 → 內嵌 3D 戰場即時播放（可滑鼠旋轉視角、播放/暫停/進度條）
  · 即時戰報、事件時間軸
  · 分析圖表瀏覽（fig1~fig5）
  · 背景訓練 AI / 產生分析圖 / 匯出動畫（子行程，不卡介面）

執行：  python app.py
相依：  Python 標準庫 tkinter + 既有專案模組（無新套件）
"""
import os
import sys
import queue
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font as tkfont

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg, NavigationToolbar2Tk)
from matplotlib.animation import FuncAnimation
from PIL import Image, ImageTk  # Pillow 已隨 matplotlib 安裝

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from core.formations import (formation_traits, FORMATION_NAMES, FORMATION_DOC,
                             PARADIGM, PARADIGM_NAMES, FORMATION_NDEFAULT,
                             FORMATION_RELAYS, is_fiber, formation_ew,
                             FORMATIONS as FORM_KEYS)
from core.engine import Simulation
from viz import set_chinese_font
from viz.tactical2d import Tactical2D
from run_sim import load_ai

ROOT = os.path.dirname(os.path.abspath(__file__))
BG = "#0d1117"
PANEL = "#161b22"
FG = "#e6edf3"
ACCENT = "#FF6D00"
GREEN = "#2E7D32"
RED = "#D32F2F"
CJK = "Microsoft JhengHei"   # 微軟正黑體：避免 CJK 字掉到新細明體

# 陣型清單（依真實作戰準則，分兩流派；單一資料來源 core/formations.py）
PARA_TAG = {"wireless": "無線", "fiber": "光纖"}
FORMATIONS = [(k, f"〔{PARA_TAG[PARADIGM[k]]}〕{FORMATION_NAMES[k]}")
              for k in FORM_KEYS]
# 防方＝傳統 / AI 兩種模式（整合了原本的「火力策略」與「識別器」）
DEFENSE_MODES = [("trad", "傳統防空"), ("ai", "AI防空")]
# 要點2 失效處理策略（領機/中繼失效後的應變，依《集群戰術應急》報告四策略）
FAIL_MODES = [("chain", "繼承鏈"), ("health", "健康度"), ("bionic", "仿生")]
FAIL_NAME = {"chain": "階級繼承鏈", "health": "健康度自主篩選", "bionic": "仿生湧現"}
BRIEF_FAIL = {
    "chain": "策略①階級繼承鏈：開戰前就排好『繼任清單』，領機亡→下一順位(中繼優先)"
             "立即接管。反應快、開銷低；但繼任清單若被連續斬首耗盡→機群迷失癱瘓"
             "（剛性策略的二次失效）。終端會進入 ToT 同時彈著＋混沌規避。",
    "health": "策略②健康度自主篩選：領機亡→存活機依 S_node(電量0.4+網路中心性0.3+"
              "算力0.2+感測0.1)分散式選舉最強者接任。抗毀傷；中繼失→向心收縮改 LOS"
              "直控；大群指揮全失→集群分裂為2組各自續突。",
    "bionic": "策略③仿生湧現：完全去中心化(Boids 對齊/聚合/斥力＋向心遷移)，"
              "根本沒有固定領機——人人是領機、人人也不是。打掉任何一架都不影響群體"
              "→免單點故障，AI 斬首在此徹底失效。",
}

# ---- 開戰前「作戰簡報」文案（依選項即時切換；陣型解說取自 formations.py）----
FORM_NICK = {k: FORMATION_NAMES[k] for k in FORM_KEYS}
BRIEF_FORM = {k: FORMATION_DOC[k] for k in FORM_KEYS}

# 防方兩模式：標題、配色、整合解說（火力＋認領機＋軌跡預測一次講完）
DEF_TITLE = {"trad": "傳統防空", "ai": "AI 防空"}
DEF_COLOR = {"trad": "#8b949e", "ai": ACCENT}
BRIEF_DEFENSE = {
    "trad": "打最近　｜　規則認領機　｜　卡爾曼預測\n"
            "經典點防禦：永遠先打離防線最近的敵機，反應快、命中高。但只用最"
            "陽春的規則認領機（最前面那架當領機），遇到把領機藏起來的隊形就"
            "認錯——殺得到外圍從機，卻打不到指揮核心，機群照樣協調突防。",
    "ai": "指揮節點打擊　｜　GNN 圖神經網路　｜　SIGINT 火控鎖定延遲　｜　LSTM\n"
          "全套 AI：把機群當成圖、用 GNN 從網路結構認出領機（不靠手刻中心性，"
          "領機 Top-1≈0.87）；但受火控鎖定延遲約束——目標進接戰圈才開始鎖定，領機"
          "因 C2 流量最大→最先被鎖定才能斬首（鎖定前先攻最近的一般機），再用 LSTM 預測攔截。",
}
BRIEF_COMPARE_WIRELESS = (
    "無線大群有明確指揮鏈。把上方『防方』在傳統／AI 間切換、同陣同種子各跑一次，"
    "比右側『協調係數 C』與『突防數』。\n核心問題：AI 能否認出領機、打斷指揮鏈，"
    "做到傳統做不到的『斬首癱瘓整群』。")
BRIEF_COMPARE_FIBER = (
    "光纖精準群免疫電子干擾，且『領機被打掉、後機照航跡續突』。\n核心問題：AI 的"
    "斬首戰術在這裡會不會失效？切到 AI 看它能不能阻止突防——這正是行為識別(要點4)"
    "遇到去單點化、抗干擾流派的極限。")


class App:
    def __init__(self, root):
        self.root = root
        root.title("無人機機群攻防模擬 — 台灣海峽防衛戰")
        root.geometry("1600x980")
        try:
            root.state("zoomed")            # Windows：開啟即最大化
        except Exception:
            try:
                root.attributes("-zoomed", True)   # Linux fallback
            except Exception:
                pass
        root.configure(bg=BG)
        # 全域放大所有 tkinter 文字（含下拉選單清單）——比目前再大 35%
        try:
            cur = float(root.tk.call("tk", "scaling"))
            root.tk.call("tk", "scaling", max(cur, 1.33) * 1.35)
        except Exception:
            pass
        # 全域命名字型統一為微軟正黑體（messagebox/spinbox 等未指定字型者也吃得到）
        try:
            for _fn in ("TkDefaultFont", "TkTextFont", "TkMenuFont",
                        "TkHeadingFont", "TkTooltipFont", "TkIconFont",
                        "TkSmallCaptionFont", "TkCaptionFont"):
                tkfont.nametofont(_fn).configure(family=CJK)
        except Exception:
            pass
        set_chinese_font()

        self.sim = None
        self.anim = None
        self.animator = None
        self.playing = False
        self.proc = None
        self.log_q = queue.Queue()

        self._build_style()
        self._build_topbar()
        self._build_main()
        self._poll_log()
        self._check_models()

    # ============================================================ 樣式
    def _build_style(self):
        st = ttk.Style()
        st.theme_use("clam")
        st.configure(".", background=PANEL, foreground=FG,
                     fieldbackground="#0d1117", bordercolor="#30363d",
                     font=(CJK,15))
        st.configure("TFrame", background=PANEL)
        st.configure("Bg.TFrame", background=BG)
        st.configure("TLabel", background=PANEL, foreground=FG, font=(CJK,15))
        st.configure("Hdr.TLabel", background=BG, foreground=FG,
                     font=(CJK,16, "bold"))
        st.configure("TButton", font=(CJK,15), padding=7)
        st.configure("Go.TButton", font=(CJK,18, "bold"), padding=9)
        st.map("Go.TButton", background=[("active", "#FF8F33"),
                                         ("!active", ACCENT)],
               foreground=[("!active", "white")])
        st.configure("TCheckbutton", background=PANEL, foreground=FG,
                     font=(CJK,15))
        st.map("TCheckbutton", background=[("active", PANEL)],
               foreground=[("active", FG)])
        # 下拉選單：深底亮字（修白底白字看不到）
        st.configure("TCombobox", fieldbackground="#0d1117", foreground=FG,
                     font=(CJK,15), arrowsize=22, padding=4)
        st.map("TCombobox",
               fieldbackground=[("readonly", "#0d1117"),
                                ("disabled", "#0d1117")],
               foreground=[("readonly", FG), ("disabled", "#777")],
               selectbackground=[("readonly", "#0d1117")],
               selectforeground=[("readonly", FG)])
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", background=PANEL, foreground=FG,
                     padding=(24, 12), font=(CJK,15, "bold"))
        st.map("TNotebook.Tab", background=[("selected", ACCENT)],
               foreground=[("selected", "white")])
        st.configure("Horizontal.TScale", background=PANEL)
        st.configure("Sim.Horizontal.TProgressbar", background=ACCENT,
                     troughcolor="#0d1117", bordercolor="#30363d")
        # 下拉清單彈出視窗：深底亮字
        self.root.option_add("*TCombobox*Listbox.background", "#161b22")
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "white")
        self.root.option_add("*TCombobox*Listbox.font", (CJK, 15))

    # ============================================================ 頂部控制列
    def _build_topbar(self):
        bar = ttk.Frame(self.root, style="Bg.TFrame")
        bar.pack(side="top", fill="x", padx=10, pady=8)

        self.var_form = tk.StringVar(value="arrowhead")  # 無線群尖端領機，最能展示AI斬首
        self.var_n = tk.IntVar(value=FORMATION_NDEFAULT["arrowhead"])
        self.var_relay = tk.IntVar(value=FORMATION_RELAYS["arrowhead"])
        self.var_decoy = tk.IntVar(value=0)          # 誘餌數（攻方反制AI識別，0=關）
        self.var_def = tk.StringVar(value="ai")      # 防方：trad / ai
        self.var_fail = tk.StringVar(value="chain")  # 失效處理：chain/health/bionic
        self.var_groups = tk.IntVar(value=1)         # 並進組數（情境一多組）
        self.var_seed = tk.IntVar(value=23)  # 種子23：完整鏈(GNN斬首→繼承鏈遞補→再斬首)、0突防

        def combo(parent, label, var, options, width=10, on_change=None):
            ttk.Label(parent, text=label, style="Hdr.TLabel").pack(side="left",
                                                                   padx=(8, 3))
            names = [n for _, n in options]
            codes = [c for c, _ in options]
            cb = ttk.Combobox(parent, values=names, width=width,
                              state="readonly")
            cb.current(codes.index(var.get()))
            cb.pack(side="left", padx=2)

            def on_sel(_e, v=var, cc=codes, c=cb):
                v.set(cc[c.current()])
                if on_change:
                    on_change()
            cb.bind("<<ComboboxSelected>>", on_sel)
            return cb

        combo(bar, "陣型", self.var_form, FORMATIONS, 16,
              on_change=self._on_form_change)
        combo(bar, "防方", self.var_def, DEFENSE_MODES, 11,
              on_change=self._on_param_change)
        combo(bar, "失效", self.var_fail, FAIL_MODES, 8,
              on_change=self._on_param_change)

        ttk.Label(bar, text="機數", style="Hdr.TLabel").pack(side="left",
                                                            padx=(8, 3))
        tk.Spinbox(bar, from_=4, to=40, textvariable=self.var_n, width=4,
                   bg="#0d1117", fg=FG, buttonbackground=PANEL,
                   insertbackground=FG, font=(CJK,15)).pack(side="left")
        ttk.Label(bar, text="中繼", style="Hdr.TLabel").pack(side="left",
                                                            padx=(8, 3))
        tk.Spinbox(bar, from_=1, to=8, textvariable=self.var_relay, width=3,
                   bg="#0d1117", fg=FG, buttonbackground=PANEL,
                   insertbackground=FG, font=(CJK,15)).pack(side="left")
        ttk.Label(bar, text="組數", style="Hdr.TLabel").pack(side="left",
                                                            padx=(8, 3))
        tk.Spinbox(bar, from_=1, to=4, textvariable=self.var_groups, width=3,
                   bg="#0d1117", fg=FG, buttonbackground=PANEL,
                   insertbackground=FG, font=(CJK, 15),
                   command=self._on_param_change).pack(side="left")
        ttk.Label(bar, text="誘餌", style="Hdr.TLabel").pack(side="left",
                                                            padx=(8, 3))
        tk.Spinbox(bar, from_=0, to=4, textvariable=self.var_decoy, width=3,
                   bg="#0d1117", fg=FG, buttonbackground=PANEL,
                   insertbackground=FG, font=(CJK, 15),
                   command=self._on_param_change).pack(side="left")
        ttk.Label(bar, text="種子", style="Hdr.TLabel").pack(side="left",
                                                            padx=(8, 3))
        tk.Spinbox(bar, from_=0, to=99999, textvariable=self.var_seed, width=6,
                   bg="#0d1117", fg=FG, buttonbackground=PANEL,
                   insertbackground=FG, font=(CJK,15)).pack(side="left")

        self.btn_go = ttk.Button(bar, text="▶  開戰", style="Go.TButton",
                                 command=self.run_battle)
        self.btn_go.pack(side="left", padx=14)

        self.ai_badge = ttk.Label(bar, text="", style="Hdr.TLabel")
        self.ai_badge.pack(side="right", padx=10)

    # ============================================================ 主區
    def _build_main(self):
        main = ttk.Frame(self.root, style="Bg.TFrame")
        main.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # ---- 左：戰場地圖
        left = ttk.Frame(main)
        left.pack(side="left", fill="both", expand=True)
        self.left_frame = left
        self.fig = plt.figure(figsize=(8, 7), facecolor=BG)

        # 播放控制列：先 side="bottom" 佔住底部空間，否則畫布 expand 會把它擠出畫面
        pc = ttk.Frame(left)
        pc.pack(side="bottom", fill="x", pady=5)
        self.btn_prev = ttk.Button(pc, text="⏮ 上個重點", width=11,
                                   command=lambda: self.jump_beat(-1),
                                   state="disabled")
        self.btn_prev.pack(side="left", padx=2)
        self.btn_play = ttk.Button(pc, text="▶ 播放", width=9,
                                   command=self.toggle_play, state="disabled")
        self.btn_play.pack(side="left", padx=2)
        self.btn_next = ttk.Button(pc, text="下個重點 ⏭", width=11,
                                   command=lambda: self.jump_beat(1),
                                   state="disabled")
        self.btn_next.pack(side="left", padx=2)
        self.scrub = ttk.Scale(pc, from_=0, to=1, orient="horizontal",
                               command=self.on_scrub)
        self.scrub.pack(side="left", fill="x", expand=True, padx=8)
        self.lbl_time = ttk.Label(pc, text="T = --- s", width=11)
        self.lbl_time.pack(side="left", padx=2)
        self.var_guided = tk.BooleanVar(value=True)
        ttk.Checkbutton(pc, text="導覽模式", variable=self.var_guided).pack(
            side="left", padx=6)
        self.var_speed = tk.StringVar(value="0.5×")
        sp = ttk.Combobox(pc, values=["0.25×", "0.5×", "1.0×", "2.0×", "4.0×"],
                          textvariable=self.var_speed, width=6,
                          state="readonly")
        sp.pack(side="left", padx=2)

        # 畫布容器：佔據播放列以上的全部空間；簡報與進度條都覆蓋在它上面
        # （不放 matplotlib 工具列——白底座標條與深色主題衝突且用不到）
        holder = ttk.Frame(left)
        holder.pack(side="top", fill="both", expand=True)
        self.holder = holder
        self.canvas = FigureCanvasTkAgg(self.fig, master=holder)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self._draw_placeholder()

        # 開戰前的「作戰簡報」引導畫面（覆蓋在畫布上；開戰時 place_forget）
        self.brief_frame = tk.Frame(holder, bg=BG)
        self._brief_bodies = []
        self.brief_frame.bind("<Configure>", self._on_brief_resize)
        self._draw_briefing()

        # 模擬計算中的進度條（覆蓋在畫布上，預設隱藏）
        self.prog_frame = tk.Frame(holder, bg="#161b22",
                                   highlightbackground=ACCENT,
                                   highlightthickness=2)
        tk.Label(self.prog_frame, text="⚙  模擬計算中…", bg="#161b22",
                 fg=FG, font=(CJK,17, "bold")).pack(padx=44, pady=(22, 6))
        self.prog_sub = tk.Label(self.prog_frame, text="準備中", bg="#161b22",
                                 fg="#8b949e", font=(CJK,12))
        self.prog_sub.pack(pady=(0, 8))
        self.prog_var = tk.DoubleVar(value=0)
        ttk.Progressbar(self.prog_frame, variable=self.prog_var, maximum=100,
                        length=340, style="Sim.Horizontal.TProgressbar").pack(
            padx=44, pady=(0, 24))

        # ---- 右：分頁
        right = ttk.Notebook(main, width=520)
        right.pack(side="right", fill="both", padx=(10, 0))
        right.pack_propagate(False)
        self._build_tab_report(right)
        self._build_tab_figures(right)
        self._build_tab_tools(right)

    def _draw_placeholder(self):
        self.fig.clear()
        ax = self.fig.add_subplot(111, facecolor=BG)
        ax.set_facecolor(BG)
        ax.scatter([0.5], [0.58], marker="*", s=1100, c=ACCENT,
                   edgecolors="white", linewidths=1.2)
        ax.text(0.5, 0.42, "設定參數後按「開戰」開始模擬",
                transform=ax.transAxes, ha="center", color=FG, fontsize=18)
        ax.text(0.5, 0.33, "台灣海峽防衛戰　·　俯視戰術地圖",
                transform=ax.transAxes, ha="center", color="#8b949e",
                fontsize=13)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        self.canvas.draw()

    # ============================================================ 作戰簡報
    def _draw_briefing(self):
        """開戰前的引導畫面：依目前選的陣形/策略/識別器即時更新解說。"""
        f = self.brief_frame
        for w in f.winfo_children():
            w.destroy()
        self._brief_bodies = []
        tk.Label(f, text="作戰簡報", bg=BG, fg=FG,
                 font=(CJK,26, "bold")).pack(anchor="w", padx=26, pady=(16, 0))
        tk.Label(f, text="改下面任一個選項，解說即時更新；看懂後按上方「▶ 開戰」開始推演。",
                 bg=BG, fg="#8b949e", font=(CJK, 13), justify="left",
                 anchor="w").pack(anchor="w", padx=26, pady=(2, 10))

        fc = self.var_form.get()
        s, c, _ = formation_traits(fc)
        sw = "高" if s <= 0.85 else ("低" if s >= 1.1 else "中")
        para = PARADIGM_NAMES[PARADIGM[fc]]
        if is_fiber(fc):
            extra = "免疫電戰 · 抗斬首"
        else:
            ewp = int(round((1 - formation_ew(fc)) * 100))
            extra = (f"電戰壓制防空 −{ewp}%" if ewp > 0 else "無電戰") + " · 可斬首"
        self._brief_card("①　攻方陣形",
                         f"{para}／{FORM_NICK.get(fc, fc)}", "#58a6ff",
                         BRIEF_FORM.get(fc, ""),
                         stat=f"隱蔽性 {sw}　·　{extra}")

        dm = self.var_def.get()
        self._brief_card("②　防方", DEF_TITLE.get(dm, dm),
                         DEF_COLOR.get(dm, ACCENT), BRIEF_DEFENSE.get(dm, ""),
                         stat=("← 對照組" if dm == "trad" else "全套 AI →"))

        if is_fiber(fc):
            self._brief_card("③　這場在比什麼", "AI 斬首會失效嗎", GREEN,
                             BRIEF_COMPARE_FIBER)
        else:
            self._brief_card("③　這場在比什麼", "AI 能否斬首癱瘓", GREEN,
                             BRIEF_COMPARE_WIRELESS)

        fs = self.var_fail.get()
        ng = int(self.var_groups.get())
        gtag = f"　·　{ng} 組並進" if ng > 1 else ""
        self._brief_card("要點2　失效處理", FAIL_NAME.get(fs, fs) + gtag, "#d2a8ff",
                         BRIEF_FAIL.get(fs, ""),
                         stat="領機/中繼被打掉後怎麼辦")

        nd = int(self.var_decoy.get())
        if nd > 0:
            self._brief_card(
                "④　攻方反制", f"誘餌 ×{nd}（沉默領機）", "#ff7b72",
                f"攻方派 {nd} 架誘餌衝最前方扮『假領機』、帶全隊編隊，真正的領機"
                "退到隊形裡藏身。\nAI 只能從飛行行為認領機 → 很可能把火力打在誘餌"
                "上、真領機毫髮無傷。這示範了要點4『行為識別』的死穴——看 AI 會不會"
                "中計（右側識別信心會鎖在誘餌上）。")

        self.brief_frame.place(relx=0, rely=0, relwidth=1, relheight=1)

    def _brief_card(self, tag, title, color, body, stat=None):
        card = tk.Frame(self.brief_frame, bg=PANEL,
                        highlightbackground="#30363d", highlightthickness=1)
        card.pack(fill="x", padx=24, pady=6)
        tk.Frame(card, bg=color, width=6).pack(side="left", fill="y")
        inner = tk.Frame(card, bg=PANEL)
        inner.pack(side="left", fill="both", expand=True, padx=16, pady=11)
        head = tk.Frame(inner, bg=PANEL)
        head.pack(fill="x")
        tk.Label(head, text=tag, bg=PANEL, fg="#8b949e",
                 font=(CJK,15, "bold")).pack(side="left")
        tk.Label(head, text="　" + title, bg=PANEL, fg=color,
                 font=(CJK,20, "bold")).pack(side="left")
        if stat:
            tk.Label(head, text=stat, bg=PANEL, fg="#c9d1d9",
                     font=(CJK,14)).pack(side="right")
        lbl = tk.Label(inner, text=body, bg=PANEL, fg=FG, font=(CJK,15),
                       justify="left", anchor="w", wraplength=900)
        lbl.pack(fill="x", pady=(7, 0))
        self._brief_bodies.append(lbl)

    def _on_brief_resize(self, e):
        wl = max(420, e.width - 150)
        for lbl in getattr(self, "_brief_bodies", []):
            lbl.configure(wraplength=wl)

    def _on_form_change(self):
        """換陣型 → 依流派自動帶入合理機數/中繼數（無線大群 vs 光纖少量），
        再走一般的參數變更流程更新簡報。"""
        fc = self.var_form.get()
        self.var_n.set(FORMATION_NDEFAULT.get(fc, 21))
        self.var_relay.set(FORMATION_RELAYS.get(fc, 2))
        self._on_param_change()

    def _on_param_change(self):
        """改了陣形/策略/識別器 → 即時更新簡報；若已跑過戰役則收起動畫回到簡報。"""
        if getattr(self, "_sim_running", False):
            return
        if self.anim is not None:
            try:
                self.anim.event_source.stop()
            except Exception:
                pass
            self.anim = None
        self.animator = None
        for b in (self.btn_play, self.btn_prev, self.btn_next):
            b.configure(state="disabled")
        self.btn_play.configure(text="▶ 播放")
        self._draw_briefing()

    def _defense_spec(self):
        """把『防方』模式展開成 (火力policy, 識別器code, 是否用LSTM)。
        傳統＝打最近＋規則認領機＋卡爾曼；AI＝指揮節點打擊＋GNN＋LSTM＋SIGINT解碼延遲。"""
        if self.var_def.get() == "trad":
            return "nearest", "rule", False
        return "ai", "gnn", True       # GNN＝圖神經網路，離線/線上皆最佳的識別主力

    # ---- 分頁1：戰報
    def _build_tab_report(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text=" 戰報 ")
        # KPI 卡片列
        self.kpi = ttk.Frame(f)
        self.kpi.pack(fill="x", padx=6, pady=6)
        self.kpi_vars = {}
        for key, label in [("alive", "存活"), ("through", "突防"),
                           ("killed", "擊落"), ("ammo", "彈藥")]:
            card = tk.Frame(self.kpi, bg=PANEL, highlightbackground="#30363d",
                            highlightthickness=1)
            card.pack(side="left", expand=True, fill="x", padx=3)
            v = tk.StringVar(value="—")
            self.kpi_vars[key] = v
            tk.Label(card, textvariable=v, bg=PANEL, fg=FG,
                     font=(CJK,28, "bold")).pack(pady=(6, 0))
            tk.Label(card, text=label, bg=PANEL, fg="#8b949e",
                     font=(CJK,14)).pack(pady=(0, 6))

        ttk.Label(f, text="事件時間軸", style="Hdr.TLabel").pack(anchor="w",
                                                              padx=8)
        wrap = ttk.Frame(f)
        wrap.pack(fill="both", expand=True, padx=6, pady=4)
        self.report = tk.Text(wrap, bg="#0d1117", fg=FG, font=(CJK, 14),
                              wrap="none", borderwidth=0)
        sb = ttk.Scrollbar(wrap, command=self.report.yview)
        self.report.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.report.pack(side="left", fill="both", expand=True)
        for tag, col in [("leader", "#FFB300"), ("kill", RED),
                         ("through", GREEN), ("info", "#58a6ff")]:
            self.report.tag_config(tag, foreground=col)

    # ---- 分頁2：分析圖
    def _build_tab_figures(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text=" 分析圖 ")
        top = ttk.Frame(f)
        top.pack(fill="x", padx=6, pady=6)
        self.fig_list = {
            "要點1·陣型總覽": "fig1_陣型總覽.png",
            "要點1·3D航跡": "fig1_3D航跡.png",
            "要點1·陣型品質": "fig1_陣型品質.png",
            "要點2·失效重組": "fig2_失效重組.png",
            "要點3·軌跡預測": "fig3_軌跡預測.png",
            "要點4·角色識別": "fig4_角色識別.png",
            "總體·策略比較": "fig5_攻防策略比較.png",
        }
        self.var_fig = tk.StringVar()
        cb = ttk.Combobox(top, values=list(self.fig_list), width=24,
                          textvariable=self.var_fig, state="readonly")
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.show_figure())
        ttk.Button(top, text="↻", width=3,
                   command=self.show_figure).pack(side="left", padx=4)
        ttk.Button(top, text="開啟資料夾", command=lambda: self._open(
            os.path.join(ROOT, "figures"))).pack(side="right")
        self.fig_canvas = tk.Label(f, bg=BG, text="（選擇圖表；若無請先到"
                                   "「工具」分頁產生分析圖）", fg="#8b949e")
        self.fig_canvas.pack(fill="both", expand=True, padx=6, pady=6)
        self.fig_canvas.bind("<Configure>", lambda e: self._render_fig())
        self._cur_fig_img = None

    # ---- 分頁3：工具（訓練/分析/匯出）
    def _build_tab_tools(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text=" 工具 ")
        info = ("背景執行長任務（不影響上方模擬）。\n"
                "首次使用請先「訓練 AI 模型」產生 models/，\n"
                "再「產生分析圖」得到 figures/。")
        ttk.Label(f, text=info, style="TLabel",
                  foreground="#8b949e").pack(anchor="w", padx=8, pady=6)

        row = ttk.Frame(f)
        row.pack(fill="x", padx=6)
        self.btn_train = ttk.Button(row, text="🧠 訓練 AI 模型",
                                    command=self.do_train)
        self.btn_train.pack(side="left", padx=3)
        self.btn_anal = ttk.Button(row, text="📊 產生分析圖",
                                   command=self.do_analyze)
        self.btn_anal.pack(side="left", padx=3)
        self.btn_export = ttk.Button(row, text="🎬 匯出當前戰役動畫",
                                     command=self.do_export, state="disabled")
        self.btn_export.pack(side="left", padx=3)

        row2 = ttk.Frame(f)
        row2.pack(fill="x", padx=6, pady=4)
        ttk.Label(row2, text="訓練場數").pack(side="left")
        self.var_ep = tk.IntVar(value=40)
        tk.Spinbox(row2, from_=10, to=120, textvariable=self.var_ep, width=5,
                   bg="#0d1117", fg=FG, insertbackground=FG,
                   font=(CJK,12)).pack(side="left", padx=4)
        self.btn_stop = ttk.Button(row2, text="■ 中止", command=self.stop_proc,
                                   state="disabled")
        self.btn_stop.pack(side="right")

        ttk.Label(f, text="主控台輸出", style="Hdr.TLabel").pack(anchor="w",
                                                              padx=8,
                                                              pady=(8, 0))
        wrap = ttk.Frame(f)
        wrap.pack(fill="both", expand=True, padx=6, pady=4)
        self.console = tk.Text(wrap, bg="#0d1117", fg="#8b949e",
                               font=(CJK, 12), wrap="word",
                               borderwidth=0)
        sb = ttk.Scrollbar(wrap, command=self.console.yview)
        self.console.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.console.pack(side="left", fill="both", expand=True)

    # ============================================================ 開戰
    def run_battle(self):
        if getattr(self, "_sim_running", False):
            return
        cfg = Config()
        fc = self.var_form.get()
        cfg.swarm.formation = fc
        cfg.swarm.n_drones = int(self.var_n.get())
        cfg.swarm.n_relays = int(self.var_relay.get())
        cfg.swarm.n_decoys = int(self.var_decoy.get())   # 誘餌（攻方反制AI識別）
        cfg.swarm.fail_strategy = self.var_fail.get()    # 要點2 失效處理策略
        cfg.swarm.n_groups = int(self.var_groups.get())  # 並進組數（情境一）
        cfg.swarm.n_axes = 3 if fc == "encircle" else 1  # 包圍：多方位向心
        # 攔截彈數隨威脅規模調整（小型光纖突擊面對的攔截彈較少，較貼近真實）
        # 0.8：接戰範圍拉大→交戰窗口變長，略增彈藥維持防守平衡（仍 < 機群數，無法全殲）
        cfg.defense.n_missiles = max(6, int(round(cfg.swarm.n_drones * 0.8)))
        policy, ident_code, use_lstm = self._defense_spec()
        cfg.defense.policy = policy
        cfg.defense.mode = self.var_def.get()        # 供 tactical2d 切換旁白用
        self._ident_code = ident_code
        self._use_lstm = use_lstm
        cfg.sim.seed = int(self.var_seed.get())
        self.cfg = cfg
        if self.anim is not None:
            self.anim.event_source.stop()
            self.anim = None
        # 背景執行緒跑模擬，主線輪詢更新進度條（避免畫面凍住像當機）
        self.btn_go.configure(state="disabled", text="模擬中…")
        for b in (self.btn_play, self.btn_prev, self.btn_next):
            b.configure(state="disabled")
        self.animator = None
        self._sim_prog = 0.0
        self._sim_done = None
        self._sim_exc = None
        self._sim_running = True
        self.prog_var.set(0)
        self.prog_sub.configure(text="載入 AI 模型…")
        self.brief_frame.place_forget()     # 收起開戰前簡報
        self.prog_frame.place(relx=0.5, rely=0.5, anchor="center")
        self.root.update_idletasks()
        threading.Thread(target=self._sim_worker, args=(cfg,),
                         daemon=True).start()
        self.root.after(80, self._poll_sim)

    def _sim_worker(self, cfg):
        try:
            ident, lstm = load_ai(cfg, self._ident_code, quiet=True)
            if not self._use_lstm:
                lstm = None            # 傳統防空：用卡爾曼基準，不吃 LSTM
            sim = Simulation(cfg, identifier=ident, lstm=lstm)
            result = sim.run(verbose=False,
                             progress_cb=lambda f: setattr(self, "_sim_prog", f))
            self._sim_done = (sim, result)
        except Exception as e:
            self._sim_exc = e
        finally:
            self._sim_running = False

    def _poll_sim(self):
        if self._sim_running:
            self.prog_var.set(self._sim_prog * 100)
            self.prog_sub.configure(text=f"模擬推演中… {self._sim_prog*100:.0f}%")
            self.root.after(80, self._poll_sim)
            return
        self.prog_frame.place_forget()
        if self._sim_exc is not None:
            self.btn_go.configure(state="normal", text="▶  開戰")
            messagebox.showerror("模擬失敗", str(self._sim_exc))
            return
        self.sim, result = self._sim_done
        self.result = result
        self._fill_report(result)
        self._setup_animator()

    def _setup_animator(self):
        cfg = self.cfg
        self.fig.clear()
        self.animator = Tactical2D(self.sim.rec, cfg, stride=2, fig=self.fig)
        self.animator._build()
        self.n_frames = len(self.animator.frames)
        self.scrub.configure(to=self.n_frames - 1)
        self.cur_frame = 0
        self._pending = set(f for f in self.animator.beat_fis if f > 0)
        self.playing = False                 # 先暫停顯示開場簡報
        self.animator._update(0)
        self.animator.show_callout(self.animator.briefing)
        self.btn_play.configure(state="normal", text="▶ 開始")
        self.btn_prev.configure(state="normal")
        self.btn_next.configure(state="normal")
        self.btn_export.configure(state="normal")
        self.btn_go.configure(state="normal", text="▶  開戰")
        self.anim = FuncAnimation(self.fig, self._anim_step,
                                  interval=self._interval(), blit=False,
                                  cache_frame_data=False)
        self.canvas.draw()

    def _interval(self):
        # 初始間隔；實際倍速由 _anim_step 動態處理（快轉跳幀、慢動作加長間隔）
        mult = float(self.var_speed.get().rstrip("×"))
        return 15 if mult >= 1.0 else int(min(400, 33 / max(mult, 0.05)))

    def _anim_step(self, _i):
        if not self.playing:
            return []
        # 導覽模式：抵達關鍵時刻 → 自動暫停解說
        if self.var_guided.get() and self.cur_frame in self._pending:
            self._pending.discard(self.cur_frame)
            self.animator._update(self.cur_frame)
            self._sync_scrub()
            self.playing = False
            bi = self._beat_idx_at(self.cur_frame)
            self.animator.show_callout(self.animator.beat_text(bi))
            self.btn_play.configure(text="▶ 繼續")
            self.canvas.draw_idle()
            return []
        self.animator._update(self.cur_frame)
        self._sync_scrub()
        # 倍速：快轉用「一次跳多幀」（每幀重繪很重，只調間隔沒用），慢動作用加長間隔
        mult = float(self.var_speed.get().rstrip("×"))
        if (self.cur_frame + 1) in getattr(self.animator, "slowmo", set()):
            mult = min(mult, 0.5)             # 關鍵時刻附近自動放慢、逐幀
        if mult >= 1.0:
            step = max(1, int(round(mult)))
            self.anim.event_source.interval = 15
        else:
            step = 1
            self.anim.event_source.interval = int(min(400, 33 / max(mult, 0.05)))
        target = min(self.cur_frame + step, self.n_frames - 1)
        # 導覽模式快轉時不可跳過關鍵時刻 → 停在最近的待暫停 beat
        if self.var_guided.get() and step > 1:
            pend = [f for f in self._pending if self.cur_frame < f <= target]
            if pend:
                target = min(pend)
        self.cur_frame = target
        if self.cur_frame >= self.n_frames - 1:
            self.cur_frame = self.n_frames - 1
            self.playing = False
            self.btn_play.configure(text="↻ 重播")
        return []

    def _beat_idx_at(self, frame):
        """frame 對應的 beat 索引（最接近且 <= frame 的關鍵時刻）"""
        best = 0
        for i, bf in enumerate(self.animator.beat_fis):
            if bf <= frame:
                best = i
        # 若正好落在某 beat frame，用該 beat
        for i, bf in enumerate(self.animator.beat_fis):
            if bf == frame:
                return i
        return best

    def jump_beat(self, direction):
        if self.animator is None:
            return
        fis = self.animator.beat_fis
        if direction > 0:
            nxt = next((f for f in fis if f > self.cur_frame), fis[-1])
        else:
            nxt = next((f for f in reversed(fis) if f < self.cur_frame), fis[0])
        self.cur_frame = nxt
        self.playing = False
        self.animator._update(nxt)
        self.animator.show_callout(self.animator.beat_text(
            self._beat_idx_at(nxt)))
        self._sync_scrub()
        self.btn_play.configure(text="▶ 繼續")
        self.canvas.draw_idle()

    def _sync_scrub(self):
        self.scrub.set(self.cur_frame)
        k = self.animator.frames[min(self.cur_frame, self.n_frames - 1)]
        self.lbl_time.configure(text=f"T = {self.sim.rec.t[k]:6.1f} s")

    def toggle_play(self):
        if self.animator is None:
            return
        if self.cur_frame >= self.n_frames - 1:   # 重播
            self.cur_frame = 0
            self._pending = set(f for f in self.animator.beat_fis if f > 0)
        self.playing = not self.playing
        if self.playing:
            self.animator.hide_callout()          # 開始/繼續 → 收起解說卡
        self.btn_play.configure(text="⏸ 暫停" if self.playing else "▶ 播放")
        self.anim.event_source.interval = self._interval()

    def on_scrub(self, val):
        if self.animator is None:
            return
        f = int(float(val))
        if abs(f - self.cur_frame) >= 1:
            self.cur_frame = f
            self.playing = False
            self.animator.hide_callout()
            self.btn_play.configure(text="▶ 播放")
            self.animator._update(f)
            k = self.animator.frames[min(f, self.n_frames - 1)]
            self.lbl_time.configure(text=f"T = {self.sim.rec.t[k]:6.1f} s")
            self.canvas.draw_idle()

    # ============================================================ 戰報
    def _fill_report(self, r):
        self.kpi_vars["alive"].set(str(r["n_alive"]))
        self.kpi_vars["through"].set(str(r["n_through"]))
        self.kpi_vars["killed"].set(str(r["n_killed"]))
        self.kpi_vars["ammo"].set(str(r["ammo_left"]))
        self.report.delete("1.0", "end")
        verdict = "🛡️ 防方成功攔阻" if r["n_through"] == 0 else \
                  ("💥 攻方突防 %d 架" % r["n_through"])
        self.report.insert("end", f"  {verdict}　|　{r['end_reason']}\n",
                           "info")
        self.report.insert("end", "─" * 56 + "\n")
        for t, msg in self.sim.rec.events:
            tag = "leader" if ("領機" in msg or "遞補" in msg) else \
                  "kill" if "擊落" in msg else \
                  "through" if "突防" in msg else ""
            self.report.insert("end", f"  [{t:6.1f}s] {msg}\n", tag)
        self.report.see("1.0")

    # ============================================================ 分析圖
    def show_figure(self):
        name = self.var_fig.get()
        if not name:
            return
        path = os.path.join(ROOT, "figures", self.fig_list[name])
        if not os.path.exists(path):
            self.fig_canvas.configure(image="", text="找不到此圖。\n"
                                      "請先到「工具」分頁按「產生分析圖」。")
            self._cur_fig_path = None
            return
        self._cur_fig_path = path
        self._render_fig()

    def _render_fig(self):
        path = getattr(self, "_cur_fig_path", None)
        if not path or not os.path.exists(path):
            return
        w = max(self.fig_canvas.winfo_width(), 200)
        h = max(self.fig_canvas.winfo_height(), 200)
        img = Image.open(path)
        img.thumbnail((w - 10, h - 10), Image.LANCZOS)
        self._cur_fig_img = ImageTk.PhotoImage(img)
        self.fig_canvas.configure(image=self._cur_fig_img, text="")

    # ============================================================ 背景任務
    def do_train(self):
        ep = int(self.var_ep.get())
        if not messagebox.askyesno("訓練 AI",
                                   f"將以 {ep} 場隨機模擬重新生成資料並訓練 "
                                   "LSTM（軌跡）與 GNN（找領機）模型"
                                   "（含 RF/MLP 對照）。\n視 GPU 約需數分鐘，"
                                   "確定開始？"):
            return
        self._run_proc([sys.executable, "-u", "train.py", "--episodes",
                        str(ep)], "訓練 AI 模型", on_done=self._check_models)

    def do_analyze(self):
        self._run_proc([sys.executable, "-u", "analyze.py"], "產生分析圖",
                       on_done=lambda: self.console_log(
                           "\n[完成] 切到「分析圖」分頁即可瀏覽\n"))

    def do_export(self):
        if self.sim is None:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".mp4", initialdir=ROOT,
            initialfile=f"battle_{self.var_form.get()}_{self.var_seed.get()}.mp4",
            filetypes=[("MP4", "*.mp4"), ("GIF", "*.gif")])
        if not path:
            return
        policy, ident_code, use_lstm = self._defense_spec()
        cmd = [sys.executable, "-u", "run_sim.py",
               "--formation", self.var_form.get(),
               "--policy", policy,
               "--identifier", ident_code,
               "--n", str(self.var_n.get()),
               "--relays", str(self.var_relay.get()),
               "--seed", str(self.var_seed.get()),
               "--no-anim", "--save", path]
        if not use_lstm:
            cmd.append("--no-lstm")       # 傳統防空用卡爾曼，匯出也一致
        self._run_proc(cmd, "匯出動畫",
                       on_done=lambda: self._open(os.path.dirname(path)))

    def _run_proc(self, cmd, title, on_done=None):
        if self.proc is not None:
            messagebox.showwarning("忙碌中", "已有背景任務執行中，請先中止或等待。")
            return
        self.console_log(f"\n{'='*50}\n▶ {title}\n{'='*50}\n")
        self.btn_stop.configure(state="normal")
        for b in (self.btn_train, self.btn_anal, self.btn_export):
            b.configure(state="disabled")
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
                   MPLBACKEND="Agg")

        def worker():
            try:
                self.proc = subprocess.Popen(
                    cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                    errors="replace", bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                for line in self.proc.stdout:
                    self.log_q.put(line)
                self.proc.wait()
            except Exception as e:
                self.log_q.put(f"[錯誤] {e}\n")
            finally:
                self.log_q.put(("__DONE__", title, on_done))

        threading.Thread(target=worker, daemon=True).start()

    def stop_proc(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.console_log("\n[已中止]\n")

    def _poll_log(self):
        try:
            while True:
                item = self.log_q.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "__DONE__":
                    _, title, cb = item
                    self.console_log(f"\n✔ {title} 完成\n")
                    self.proc = None
                    self.btn_stop.configure(state="disabled")
                    self.btn_train.configure(state="normal")
                    self.btn_anal.configure(state="normal")
                    if self.sim is not None:
                        self.btn_export.configure(state="normal")
                    if cb:
                        try:
                            cb()
                        except Exception:
                            pass
                else:
                    self.console_log(item)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_log)

    def console_log(self, text):
        self.console.insert("end", text)
        self.console.see("end")

    # ============================================================ 雜項
    def _check_models(self):
        cfg = Config()
        has_gnn = os.path.exists(cfg.ai.gnn_path)
        has_lstm = os.path.exists(cfg.ai.lstm_path)
        if has_gnn and has_lstm:
            self.ai_badge.configure(text="● AI 模型就緒 (GNN+LSTM)",
                                    foreground=GREEN)
        else:
            self.ai_badge.configure(
                text="○ 尚未訓練 AI（用基準法；可到工具分頁訓練）",
                foreground="#d29922")

    def _open(self, path):
        try:
            os.startfile(path)
        except Exception:
            pass


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

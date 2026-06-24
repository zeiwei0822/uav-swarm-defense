# -*- coding: utf-8 -*-
"""
2D 俯視戰術地圖（桌面版）— 指揮所螢幕風格
============================================
左：台灣海峽俯視戰場（箭頭機群、通訊鏈、飛彈軌跡、AI預測線、識別標籤、爆炸）
右：即時遙測側欄（KPI、協調係數C＋預警狀態、存活曲線、AI識別信心、事件）

與 Animator3D 同介面（rec, cfg, stride, fig + _build/_update/frames/show/save/
snapshots），app 可直接抽換。
"""
import os
import re
import shutil
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.collections import PolyCollection, LineCollection
from matplotlib.animation import FuncAnimation, FFMpegWriter, PillowWriter

from config import ROLE_FOLLOWER, ROLE_RELAY, ROLE_LEADER
from viz import set_chinese_font
from viz.models3d import _TAIWAN
from core.formations import (formation_doc, formation_traits,
                             FORMATION_NAMES, is_fiber, PARADIGM_NAMES,
                             PARADIGM)

BG = "#0a0e14"
PANEL = "#10161f"
SEA = "#0d2438"
LAND = "#243024"
TAIWAN_C = "#2f4024"
C_LEADER = "#FFD700"
C_RELAY = "#FF8A30"
C_FOLLOW = "#E0544B"
C_DEAD = "#7a8694"
C_MISSILE = "#26C6DA"
C_COMM = "#3d7fb0"
C_PRED = "#00E5FF"
C_TARGET = "#46c84e"
C_FX = "#FF7000"
FG = "#e6edf3"
TRAIL = 70
FX_LIFE = 16

# 2D 機體/飛彈字形（局部，機頭朝 +x）
_DRONE_GLYPH = np.array([(1.15, 0), (-0.55, 0.62), (-0.25, 0), (-0.55, -0.62)])
_MISSILE_GLYPH = np.array([(1.3, 0), (-0.9, 0.22), (-0.9, -0.22)])
SC_DRONE = 34.0          # 固定視角下要看得到、但仍 < 陣型間距(38m) 才不致疊一坨
SC_MISSILE = 40.0
MULT_LEADER = 1.95       # 領機放大但不致蓋住鄰機
MULT_RELAY = 1.4


def _rot2d(glyph, yaw, scale, pos):
    c, s = np.cos(yaw), np.sin(yaw)
    R = np.array([[c, -s], [s, c]])
    return (glyph * scale) @ R.T + pos


# 事件訊息的 emoji 在 Windows 中文字型會變方塊 → 移除
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002190-\U000021FF"
    "\U00002B00-\U00002BFF\U0000FE0F\U0000274C\U0000203C\U00002049]")


def _clean(s):
    return _EMOJI.sub("", s).strip()


def _wrap_cn(s, width=24):
    """中文自動換行：每行約 width 個全形字，在標點處斷行；
    無標點時硬斷保底（避免長串溢出畫面）。"""
    out, cur = [], ""
    breakers = "，。；、）」』〕：—─　 "
    for ch in s:
        cur += ch
        if len(cur) >= width and ch in breakers:
            out.append(cur)
            cur = ""
        elif len(cur) >= width + 5:        # 硬斷保底
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return "\n".join(out)


class Tactical2D:
    def __init__(self, rec, cfg, stride=3, fig=None):
        set_chinese_font()
        self.rec = rec
        self.cfg = cfg
        self.stride = stride
        self.frames = list(range(0, len(rec.t), stride))
        self.n = rec.pos.shape[1]
        self.ext_fig = fig
        self._missile_hist = {}
        self._built = False
        self._scan_effects()
        self._scan_narrative()

    def _scan_effects(self):
        rec = self.rec
        self.explosions = []
        for i in range(self.n):
            a = rec.alive[:, i]
            for k in np.flatnonzero(a[:-1] & ~a[1:]):
                kind = "through" if rec.succeeded[k + 1, i] else "kill"
                self.explosions.append((k + 1, rec.pos[k + 1, i, :2].copy(),
                                        kind))
        self._frags = []
        for idx in range(len(self.explosions)):
            rng = np.random.default_rng(2000 + idx)
            d = rng.normal(size=(8, 2))
            d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-9
            self._frags.append(d)

    def _scan_narrative(self):
        """從戰役紀錄偵測『分幕』與『關鍵時刻』，產生引導旁白（資料驅動，
        任何種子皆適用）。focus 指示聚光燈要打在哪。"""
        rec = self.rec
        dt = self.cfg.sim.dt
        ev = rec.events
        T = len(rec.t)
        beats = []

        def evk(kw, kw2=None, after=0.0):
            for et, m in ev:
                if kw in m and (kw2 is None or kw2 in m) and et >= after:
                    return et, int(et / dt)
            return None

        is_ai = getattr(self.cfg.defense, "mode", None) == "ai" \
            or self.cfg.defense.policy == "ai"
        fiber = is_fiber(self.cfg.swarm.formation)   # 光纖群：抗斬首流派
        multi = int(getattr(self.cfg.swarm, "n_axes", 1)) > 1
        axes_note = "　機群分三路、向心夾擊推進（多軸戰術）。" if multi else ""
        beats.append(dict(k=0,
                          title="跨海峽進襲 · 三路夾擊" if multi else "跨海峽進襲",
                          focus="swarm",
                          cap=formation_doc(self.cfg.swarm.formation)
                              + axes_note + "　〔要點1：陣形＋戰術〕"))
        # AI 首次高信心鎖定真領機（只有 AI 防空會「認領機後鎖定打擊」）
        lock = None
        for k in range(T):
            bl = rec.believed_leader[k]
            ld = np.flatnonzero(rec.alive[k] & (rec.roles[k] == ROLE_LEADER))
            if bl >= 0 and len(ld) and bl == ld[0] and rec.leader_conf[k] >= 0.55:
                lock = k
                break
        if lock is not None and is_ai:
            beats.append(dict(k=lock, title="AI 鎖定領機", focus="leader",
                              cap="防方 AI 從飛行行為（誰先轉彎、居中轉發）"
                                  "推斷出領機，鎖定為優先打擊目標"
                                  "　〔要點4：AI找領機〕"))
        # 誘餌成功騙過 AI（AI 把誘餌當領機鎖定）→ 要點4 的死穴
        dm = getattr(rec, "is_decoy", None)
        if is_ai and dm is not None and dm.any():
            for k in range(T):
                bl = rec.believed_leader[k]
                if bl >= 0 and dm[bl] and rec.leader_conf[k] >= 0.5:
                    beats.append(dict(k=k, title="AI 中了誘餌", focus="leader",
                                      cap="攻方派誘餌衝前方扮『假領機』──AI 把火力"
                                          "鎖定誘餌，真領機藏在隊形裡毫髮無傷"
                                          "　〔要點4的死穴：行為識別會被騙〕"))
                    break
        fire = evk("發射")
        if fire:
            beats.append(dict(k=fire[1], title="首次接戰", focus="missile",
                              cap="攔截彈升空！領機在線→全網提早預警→"
                                  "機群蛇行閃避　〔領機=威脅預警大腦〕"))
        ld = evk("領機", "擊落")
        lost = evk("迷失")
        seam = evk("無縫接替")          # 光纖：領機亡→即時接替
        if ld and fiber:
            # 光纖群：領機被打掉，後機沿既有航跡無縫續突 → 斬首失效
            beats.append(dict(k=ld[1], title="領機被擊殺 · 但鏈路不斷",
                              focus="leader",
                              cap="領機被狙殺，但光纖群早把航線存進每架機──"
                                  "後機沿既有航跡無縫續突，協調係數 C 幾乎不掉"
                                  "　〔要點4的極限：斬首對光纖群失效〕"))
        elif ld:
            cap_kill = ("領機被精準狙殺──看右側『協調係數 C』即將崩落、"
                        "『全網預警』翻紅　〔要點4→要點2〕" if is_ai else
                        "領機剛好被擊落（傳統只追打最近、並非刻意鎖定它）──看"
                        "右側『協調係數 C』即將崩落、『全網預警』翻紅"
                        "　〔領機＝關鍵節點〕")
            beats.append(dict(k=ld[1], title="領機遭擊殺 · 指揮中斷",
                              focus="cgauge", cap=cap_kill))
        # 機群迷失=指揮鏈瓦解的高潮；但要在「大量突防之前」癱瘓才算防守成效
        # （否則領機帶隊突防後殘兵才迷失，會誤導成防守成功）
        meaningful_lost = False
        if lost:
            succ_at = int(rec.succeeded[min(lost[1], T - 1)].sum())
            meaningful_lost = succ_at < self.n * 0.5
        if meaningful_lost:
            beats.append(dict(k=lost[1], title="指揮鏈瓦解 · 機群癱瘓",
                              focus="cgauge",
                              cap="指揮鏈被打斷、無人遞補，協調瓦解、"
                                  "機群迷失盤旋──癱瘓指揮鏈的效果〔要點2的反證〕"))
        elif ld:   # 領機被殺但成功遞補 → 凸顯韌性
            sup = evk("遞補", after=ld[0])
            if sup:
                beats.append(dict(k=sup[1], title="遞補重組", focus="leader",
                                  cap="中繼機升任新領機，機群恢復協調與編隊"
                                      "──機群的韌性〔要點2：失效重組〕"))
        thru = evk("突防成功")
        if thru and thru[1] < T - 30:
            beats.append(dict(k=thru[1], title="首架突防", focus="target",
                              cap="有無人機穿透防線抵達目標〔攻方得分〕"))
        # 傳統沒能斬首原始領機（它存活或帶隊突防）→ 認不出指揮核心（要點4 反面對照）
        if not is_ai:
            li0 = np.flatnonzero(rec.roles[0] == ROLE_LEADER)
            killed0 = len(li0) and (not rec.alive[-1, li0[0]]) \
                and (not rec.succeeded[-1, li0[0]])
            if len(li0) and not killed0:
                beats.append(dict(k=max(1, T - 12), title="領機未被擊殺",
                                  focus="leader",
                                  cap="傳統防空只追著最近的目標打、認不出藏在陣形"
                                      "裡的指揮核心──領機毫髮無傷，帶著機群突防"
                                      "　〔對照：要點4的價值〕"))
        na = int(rec.alive[-1].sum())
        ns = int(rec.succeeded[-1].sum())
        verdict = "機群癱瘓，防守成功" if ns == 0 else f"攻方突防 {ns} 架"
        if fiber:
            cap_end = (f"{verdict}。光纖群把航線存進每架機、又免疫電子干擾──"
                       f"領機被打掉後機照樣突防，AI 斬首在此失效〔要點4 的極限："
                       f"去單點化反制流派〕" if is_ai else
                       f"{verdict}。光纖精準群少量、抗干擾、抗斬首〔攻方反制流派〕")
        else:
            cap_end = (f"{verdict}。鎖定並擊殺指揮節點，是唯一能癱瘓整個機群的"
                       f"策略〔總結：要點1-4〕" if is_ai else
                       f"{verdict}。傳統只追打最近、認不出指揮核心：殺得到外圍、"
                       f"卻打不斷指揮鏈——這正是 AI 斬首的價值〔對照組〕")
        beats.append(dict(k=T - 1, title="結局", focus="none", cap=cap_end))
        beats.sort(key=lambda b: b["k"])
        # 去除過近重複
        dedup = []
        for b in beats:
            if dedup and b["k"] - dedup[-1]["k"] < 8 and b["title"] != "結局":
                continue
            dedup.append(b)
        self.beats = dedup
        # 取「≥ beat 時刻」的第一幀，確保該幀的旁白正好對應此 beat（避免 stride 造成差一幀）
        self.beat_fis = [
            next((f for f in range(len(self.frames))
                  if self.frames[f] >= b["k"]), len(self.frames) - 1)
            for b in dedup]
        self.slowmo = set()
        for fi in self.beat_fis:
            for f in range(max(0, fi - 6), min(len(self.frames), fi + 12)):
                self.slowmo.add(f)
        fdoc = _wrap_cn(formation_doc(self.cfg.swarm.formation), width=24)
        mode_line = ("〔本場防方〕AI 防空：認領機 → 指揮節點打擊 → LSTM 預測"
                     if is_ai else
                     "〔本場防方〕傳統防空：打最近目標 ＋ 規則認領機 ＋ 卡爾曼預測")
        watch = ("觀戰重點：AI 鎖定領機後，右側『協調係數 C』會在領機被擊殺時"
                 "崩落、『全網預警』翻紅——這就是癱瘓指揮鏈的效果。" if is_ai else
                 "觀戰重點：傳統只追打最近的目標，多半傷不到指揮核心——"
                 "對照右側『協調係數 C』守不守得住、突防數多不多。")
        self.briefing = (
            "◆ 台灣海峽防衛戰 ‧ 觀戰導覽\n\n"
            "本模擬示範四個要點：\n"
            "①機群陣形與航路　②領機失效→遞補重組\n"
            "③AI 軌跡預測　④AI 從飛行行為找出領機\n\n"
            f"{mode_line}\n〔本場陣形〕\n{fdoc}\n\n"
            f"{watch}\n\n"
            "（按「開始」播放；開『導覽模式』會在關鍵時刻自動暫停解說）")

    # ------------------------------------------------------------ 建場景
    def _build(self):
        if self._built:
            return
        self._built = True
        rec = self.rec
        self.fig = self.ext_fig if self.ext_fig is not None \
            else plt.figure(figsize=(15, 8.5))
        self.fig.patch.set_facecolor(BG)
        gs = self.fig.add_gridspec(1, 2, width_ratios=[2.65, 1.0],
                                   left=0.02, right=0.985, top=0.97,
                                   bottom=0.03, wspace=0.04)
        self.ax = self.fig.add_subplot(gs[0])
        self._build_map()
        self._build_telemetry(gs[1])

    def _build_map(self):
        ax = self.ax
        rec = self.rec
        ax.set_facecolor(SEA)
        allp = rec.pos.reshape(-1, 3)
        allp = allp[np.isfinite(allp).all(axis=1)]
        self._xr = (min(allp[:, 0].min() - 200, -3200),
                    max(allp[:, 0].max() + 200, 450))
        self._yr = (min(allp[:, 1].min() - 250, -1300),
                    max(allp[:, 1].max() + 250, 1300))

        # 地形（俯視多邊形）
        ys = np.linspace(self._yr[0], self._yr[1], 60)
        coast = -2800 + 70 * np.sin(ys / 320) + 25 * np.sin(ys / 90)
        mainland = np.column_stack([np.r_[coast, self._xr[0], self._xr[0]],
                                    np.r_[ys, self._yr[1], self._yr[0]]])
        ax.add_patch(plt.Polygon(mainland, closed=True, facecolor=LAND,
                                 edgecolor="#3f5142", lw=1.0, zorder=1))
        tw = _TAIWAN.copy()
        tw[:, 0] = tw[:, 0] * 260 + 150
        tw[:, 1] = tw[:, 1] * 560
        ax.add_patch(plt.Polygon(tw, closed=True, facecolor=TAIWAN_C,
                                 edgecolor="#5a7038", lw=1.4, zorder=1))
        midx = (-2800 + 157) / 2
        ax.axvline(midx, color="#5a6b7a", ls="--", lw=1.2, alpha=0.6, zorder=1)
        ax.text(-3000, self._yr[1] - 180, "中國大陸\n（攻方起飛）",
                color="#9db89d", fontsize=12, weight="bold", ha="center",
                va="top", zorder=4)
        ax.text(180, 700, "台灣", color="#9cc46a", fontsize=14,
                weight="bold", ha="center", zorder=4)
        ax.text(midx, self._yr[0] + 90, "海峽中線", color="#8aa0b5",
                fontsize=10, ha="center", zorder=4)

        # 防守目標（不畫接戰圈虛線圓）
        ax.scatter([0], [0], marker="*", s=620, c=C_TARGET,
                   edgecolors="white", linewidths=1.2, zorder=6)
        ax.text(0, -130, "防守目標", color=C_TARGET, fontsize=12,
                weight="bold", ha="center", zorder=6)

        # 動態 collections
        self.comm_lc = LineCollection([], colors=C_COMM, alpha=0.35, lw=1.0,
                                      zorder=3)
        ax.add_collection(self.comm_lc)
        self.trail_lc = LineCollection([], colors=C_FOLLOW, alpha=0.32, lw=0.8,
                                       zorder=3)
        ax.add_collection(self.trail_lc)
        self.mtrail_lc = LineCollection([], colors=C_MISSILE, alpha=0.45,
                                        lw=1.0, zorder=4)
        ax.add_collection(self.mtrail_lc)
        self.pred_lc = LineCollection([], colors=C_PRED, alpha=0.85, lw=1.6,
                                      linestyles="--", zorder=5)
        ax.add_collection(self.pred_lc)
        self.drone_pc = PolyCollection([], zorder=7, edgecolors="#101010",
                                       linewidths=0.4)
        ax.add_collection(self.drone_pc)
        self.missile_pc = PolyCollection([], facecolors=C_MISSILE, zorder=7,
                                         edgecolors="#0a3a40", linewidths=0.4)
        ax.add_collection(self.missile_pc)
        self.sc_dead = ax.scatter([], [], marker="x", s=60, c=C_DEAD,
                                  zorder=6, linewidths=1.6)
        self.sc_ai = ax.scatter([], [], s=720, facecolors="none",
                                edgecolors=C_PRED, linewidths=2.2, zorder=8)
        self.fx = ax.scatter([], [], s=[], c=[], zorder=9, edgecolors="none")
        self.leader_txt = ax.text(0, 0, "", color=C_LEADER, fontsize=12,
                                  weight="bold", ha="center", zorder=10)
        # 誘餌標籤（最多 6 架；衝前方扮假領機）
        self.decoy_txts = [ax.text(0, 0, "", color="#ff7b72", fontsize=10.5,
                                   weight="bold", ha="center", zorder=11,
                                   visible=False) for _ in range(6)]

        ax.set_xlim(*self._xr)
        ax.set_ylim(*self._yr)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_color("#30363d")
        # HUD（地圖左上）
        self.hud = ax.text(0.012, 0.985, "", transform=ax.transAxes,
                           color=FG, fontsize=16.5, va="top", weight="bold",
                           bbox=dict(boxstyle="round,pad=0.5", fc=PANEL,
                                     ec="#30363d", alpha=0.85), zorder=11)
        self._legend(ax)
        # 常駐陣形說明（左下角，回答「這個陣形在幹嘛」）
        s, c, note = formation_traits(self.cfg.swarm.formation)
        fn = FORMATION_NAMES.get(self.cfg.swarm.formation,
                                 self.cfg.swarm.formation)
        ax.text(0.012, 0.045, f"陣形 {fn}：{note}", transform=ax.transAxes,
                ha="left", va="bottom", color="#9fc0d4", fontsize=12,
                zorder=11, bbox=dict(boxstyle="round,pad=0.32", fc="#0c1622",
                                     ec="#2f5a7a", alpha=0.85))
        # 引導敘事：分幕橫幅（上中）、旁白字幕（下中）、聚光燈、解說卡
        self.spot = ax.scatter([], [], s=[], facecolors="none",
                               edgecolors=C_PRED, linewidths=2.8, zorder=8)
        # 橫幅放 HUD(左上3行)下方，避免與 HUD 重疊
        self.banner = ax.text(
            0.5, 0.82, "", transform=ax.transAxes, ha="center", va="top",
            color="#fff3c4", fontsize=20, weight="bold", zorder=12,
            bbox=dict(boxstyle="round,pad=0.5", fc="#1a1206", ec=C_LEADER,
                      alpha=0.93))
        self.subtitle = ax.text(
            0.5, 0.105, "", transform=ax.transAxes, ha="center", va="bottom",
            color=FG, fontsize=15.5, zorder=12, wrap=True,
            bbox=dict(boxstyle="round,pad=0.55", fc="#0c1622", ec="#2f5a7a",
                      alpha=0.93))
        self.callout = ax.text(
            0.5, 0.52, "", transform=ax.transAxes, ha="center", va="center",
            color=FG, fontsize=16.5, zorder=20, linespacing=1.75,
            visible=False, bbox=dict(boxstyle="round,pad=0.95", fc="#0c1622",
                                     ec=C_LEADER, alpha=0.97))
        self._dc = {ROLE_LEADER: mcolors.to_rgba(C_LEADER),
                    ROLE_RELAY: mcolors.to_rgba(C_RELAY),
                    ROLE_FOLLOWER: mcolors.to_rgba(C_FOLLOW)}

    def _legend(self, ax):
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
        is_ai = getattr(self.cfg.defense, "mode", None) == "ai" \
            or self.cfg.defense.policy == "ai"
        h = [
            Line2D([], [], marker="*", color="none", markerfacecolor=C_LEADER,
                   markeredgecolor="w", markersize=15, label="領機（放大）"),
            Patch(facecolor=C_RELAY, label="中繼機"),
            Patch(facecolor=C_FOLLOW, label="從機"),
            Patch(facecolor=C_MISSILE, label="攔截彈"),
            Line2D([], [], marker="o", color="none", markeredgecolor=C_PRED,
                   markersize=12,
                   label="AI判定領機" if is_ai else "規則判定領機"),
            Line2D([], [], color=C_COMM, label="通訊鏈"),
            Line2D([], [], color=C_PRED, ls="--",
                   label="AI預測軌跡" if is_ai else "卡爾曼預測"),
        ]
        ax.legend(handles=h, loc="upper right", facecolor=PANEL,
                  labelcolor=FG, edgecolor="#30363d", fontsize=12,
                  framealpha=0.85)

    def _build_telemetry(self, gs_cell):
        sub = gs_cell.subgridspec(5, 1, height_ratios=[1.0, 1.0, 1.3, 1.3, 1.4],
                                  hspace=0.55)
        f = self.fig
        # KPI（大數字）
        self.ax_kpi = f.add_subplot(sub[0])
        self.ax_kpi.axis("off")
        self.kpi_txt = self.ax_kpi.text(
            0.5, 0.5, "", transform=self.ax_kpi.transAxes, ha="center",
            va="center", color=FG, fontsize=19, weight="bold", linespacing=1.9)
        # 協調係數 + 預警
        self.ax_coord = f.add_subplot(sub[1])
        self._style_panel(self.ax_coord, "領機機制：協調係數 C ＋ 全網預警")
        self.ax_coord.set_xlim(0, 1)
        self.ax_coord.set_ylim(0, 1)
        self.coord_bar = self.ax_coord.barh([0.62], [0], height=0.42,
                                            color=C_TARGET)[0]
        self.ax_coord.text(0.0, 0.62, "", va="center", ha="left", fontsize=1)
        self.coord_lbl = self.ax_coord.text(0.98, 0.62, "", va="center",
                                            ha="right", color=FG, fontsize=15,
                                            weight="bold")
        self.warn_lbl = self.ax_coord.text(0.02, 0.12, "", va="center",
                                           ha="left", fontsize=13.5,
                                           weight="bold")
        # 存活/突防 曲線
        self.ax_surv = f.add_subplot(sub[2])
        self._style_panel(self.ax_surv, "兵力消長")
        (self.ln_alive,) = self.ax_surv.plot([], [], color=C_FOLLOW, lw=2,
                                             label="存活")
        (self.ln_thru,) = self.ax_surv.plot([], [], color=C_TARGET, lw=2,
                                            label="突防")
        self.ax_surv.legend(loc="upper right", fontsize=11, labelcolor=FG,
                            facecolor=PANEL, edgecolor="#30363d")
        self.ax_surv.set_xlim(0, self.rec.t[-1])
        self.ax_surv.set_ylim(0, self.n)
        # 識別信心 曲線（標題隨防方模式：AI / 規則法）
        self.ax_conf = f.add_subplot(sub[3])
        _is_ai = getattr(self.cfg.defense, "mode", None) == "ai" \
            or self.cfg.defense.policy == "ai"
        self._style_panel(self.ax_conf, "AI 對領機的識別信心" if _is_ai else
                          "規則法 對領機的識別信心")
        (self.ln_conf,) = self.ax_conf.plot([], [], color=C_PRED, lw=2)
        self.ax_conf.axhline(self.cfg.defense.ident_conf_fire, color="#ffae3b",
                             ls=":", lw=1.2, alpha=0.7)
        self.ax_conf.set_xlim(0, self.rec.t[-1])
        self.ax_conf.set_ylim(0, 1)
        self.conf_lbl = self.ax_conf.text(0.98, 0.9, "", transform=
                                          self.ax_conf.transAxes, ha="right",
                                          va="top", color=FG, fontsize=13.5,
                                          weight="bold")
        # 事件
        self.ax_ev = f.add_subplot(sub[4])
        self.ax_ev.axis("off")
        self.ax_ev.text(0.0, 1.0, "戰場事件", transform=self.ax_ev.transAxes,
                        color="#8aa0b5", fontsize=13, va="top", weight="bold")
        self.ev_txt = self.ax_ev.text(
            0.0, 0.84, "", transform=self.ax_ev.transAxes, color="#ffd54f",
            fontsize=12.5, va="top", linespacing=1.5, family="sans-serif")

    def _style_panel(self, ax, title):
        ax.set_facecolor(PANEL)
        ax.set_title(title, color="#8aa0b5", fontsize=13, loc="left",
                     weight="bold", pad=4)
        ax.tick_params(colors="#6a7785", labelsize=10)
        for sp in ax.spines.values():
            sp.set_color("#30363d")

    # ------------------------------------------------------------ 更新
    def _update(self, fi):
        rec = self.rec
        k = self.frames[fi]
        t = rec.t[k]
        pos = rec.pos[k, :, :2]
        alive = rec.alive[k]
        succ = rec.succeeded[k]
        roles = rec.roles[k]
        kp = max(0, k - 2)
        vel = pos - rec.pos[kp, :, :2]

        flying = np.flatnonzero(alive & ~succ)
        polys, cols = [], []
        beam = None
        for i in flying:
            yaw = np.arctan2(vel[i, 1], vel[i, 0]) if np.linalg.norm(vel[i]) > 1e-6 else 0.0
            if roles[i] == ROLE_LEADER:
                sc = SC_DRONE * MULT_LEADER
            elif roles[i] == ROLE_RELAY:
                sc = SC_DRONE * MULT_RELAY
            else:
                sc = SC_DRONE
            polys.append(_rot2d(_DRONE_GLYPH, yaw, sc, pos[i]))
            cols.append(self._dc[int(roles[i])])
        self.drone_pc.set_verts(polys)
        self.drone_pc.set_facecolors(cols if cols else [(0, 0, 0, 0)])

        # 領機標籤
        tl = np.flatnonzero(alive & (roles == ROLE_LEADER))
        if len(tl):
            li = tl[0]
            self.leader_txt.set_position((pos[li, 0], pos[li, 1] + 110))
            self.leader_txt.set_text("◤領機")
        else:
            self.leader_txt.set_text("")

        # 誘餌標籤（衝前方扮假領機）
        dmask = getattr(rec, "is_decoy", None)
        di = 0
        if dmask is not None and dmask.any():
            for i in np.flatnonzero(dmask & alive & ~succ):
                if di < len(self.decoy_txts):
                    self.decoy_txts[di].set_position((pos[i, 0], pos[i, 1] + 85))
                    self.decoy_txts[di].set_text("誘餌")
                    self.decoy_txts[di].set_visible(True)
                    di += 1
        for j in range(di, len(self.decoy_txts)):
            self.decoy_txts[j].set_visible(False)

        # 被擊落
        dead = pos[~alive & ~succ]
        self.sc_dead.set_offsets(dead if len(dead) else np.empty((0, 2)))

        # 尾跡
        k0 = max(0, k - TRAIL)
        trails = []
        for i in range(self.n):
            if alive[i]:
                m = rec.alive[k0:k + 1, i]
                seg = rec.pos[k0:k + 1, i, :2][m]
                if len(seg) >= 2:
                    trails.append(seg)
        self.trail_lc.set_segments(trails)

        # 通訊鏈
        self.comm_lc.set_segments([[pos[i], pos[j]]
                                   for i, j in rec.comm_edges[k]
                                   if alive[i] and alive[j]])

        # 飛彈
        mlist = rec.missiles[k]
        mpolys, mtrails, live = [], [], set()
        for mid, p, tid in mlist:
            live.add(mid)
            h = self._missile_hist.setdefault(mid, [])
            d = p[:2] - h[-1][1] if h else (pos[tid] - p[:2] if tid < self.n
                                            else np.array([1.0, 0]))
            yaw = np.arctan2(d[1], d[0]) if np.linalg.norm(d) > 1e-6 else 0.0
            mpolys.append(_rot2d(_MISSILE_GLYPH, yaw, SC_MISSILE, p[:2]))
            h.append((k, p[:2].copy()))
        self.missile_pc.set_verts(mpolys)
        for mid in list(self._missile_hist):
            h = [(kk, pp) for kk, pp in self._missile_hist[mid] if k - kk <= 20]
            if mid not in live and (not h or k - h[-1][0] > 5):
                del self._missile_hist[mid]
                continue
            self._missile_hist[mid] = h
            if len(h) >= 2:
                mtrails.append(np.array([pp for _, pp in h]))
        self.mtrail_lc.set_segments(mtrails)

        # AI 預測線 + 判定領機
        psegs = []
        for _tid, path in rec.pred_paths[k].items():
            psegs.append(path[::3, :2])
        self.pred_lc.set_segments(psegs)
        bl = rec.believed_leader[k]
        if bl >= 0 and alive[bl] and rec.leader_conf[k] > 0.25:
            self.sc_ai.set_offsets([pos[bl]])
        else:
            self.sc_ai.set_offsets(np.empty((0, 2)))

        self._draw_fx(k)
        self._draw_hud(k, t, alive, succ, roles, bl)
        self._update_telemetry(k, t, alive, succ, roles)
        self._update_narrative(k, pos, alive, roles, mlist)
        return []

    _CN = "〇一二三四五六七八九十"

    def _update_narrative(self, k, pos, alive, roles, mlist):
        """分幕橫幅 + 旁白字幕 + 聚光燈（資料驅動引導）"""
        idx = -1
        for i, b in enumerate(self.beats):
            if b["k"] <= k:
                idx = i
            else:
                break
        if idx < 0:
            self.banner.set_text("")
            self.subtitle.set_text("")
            self.spot.set_offsets(np.empty((0, 2)))
            self.spot.set_sizes([])
            return
        b = self.beats[idx]
        n = idx + 1
        num = self._CN[n] if n < len(self._CN) else str(n)
        self.banner.set_text(f"第{num}幕　{b['title']}")
        self.subtitle.set_text(_wrap_cn(b["cap"]))
        # 聚光燈
        focus = b["focus"]
        pulse = 1 + 0.35 * np.sin(k * 0.4)
        p = None
        col = C_PRED
        if focus == "swarm":
            ap = pos[alive]
            p = ap.mean(axis=0) if len(ap) else None
        elif focus == "leader":
            ll = np.flatnonzero(alive & (roles == ROLE_LEADER))
            p = pos[ll[0]] if len(ll) else None
            col = C_LEADER
        elif focus == "missile":
            p = mlist[-1][1][:2] if mlist else None
            col = C_MISSILE
        elif focus == "target":
            p = np.array([0.0, 0.0])
            col = C_TARGET
        if p is not None:
            self.spot.set_offsets([p])
            self.spot.set_sizes([1500 * pulse])
            self.spot.set_edgecolors([col])
        else:
            self.spot.set_offsets(np.empty((0, 2)))
            self.spot.set_sizes([])
        # 協調儀表閃爍（斬首/崩潰時把注意力導到 C）
        flash = focus == "cgauge" and abs(k - b["k"]) < 28 and int(k * 0.3) % 2 == 0
        self.ax_coord.set_facecolor("#3a1820" if flash else PANEL)

    def show_callout(self, text):
        """顯示置中解說卡（開場簡報 / 導覽暫停）"""
        self.callout.set_text(_clean(text))
        self.callout.set_visible(True)

    def hide_callout(self):
        self.callout.set_visible(False)

    def beat_text(self, idx):
        """取第 idx 個 beat 的解說（給 app 暫停卡用）"""
        if 0 <= idx < len(self.beats):
            b = self.beats[idx]
            n = idx + 1
            num = self._CN[n] if n < len(self._CN) else str(n)
            return f"◆ 第{num}幕　{b['title']}\n\n{b['cap']}\n\n（按「繼續」往下）"
        return ""

    def _draw_fx(self, k):
        pts, sizes, cols = [], [], []
        for idx, (ke, pe, kind) in enumerate(self.explosions):
            age = k - ke
            if not (0 <= age < FX_LIFE):
                continue
            f = age / FX_LIFE
            if kind == "kill":
                pts.append(pe); sizes.append(800 * (0.5 + 1.5 * f))
                cols.append((1.0, 0.5, 0.05, max(0, 1 - f)))
                for d in self._frags[idx]:
                    pts.append(pe + d * age * 14); sizes.append(120 * (1 - f))
                    cols.append((1.0, 0.8, 0.3, max(0, 1 - f * 1.2)))
            else:
                pts.append(pe); sizes.append(1100 * (0.4 + 1.4 * f))
                cols.append((0.3, 1.0, 0.45, max(0, 1 - f)))
        if pts:
            self.fx.set_offsets(np.array(pts))
            self.fx.set_sizes(sizes)
            self.fx.set_facecolors(cols)
        else:
            self.fx.set_offsets(np.empty((0, 2)))
            self.fx.set_sizes([])

    def _draw_hud(self, k, t, alive, succ, roles, bl):
        na, ns = int(alive.sum()), int(succ.sum())
        nd = self.n - na - ns
        tl = np.flatnonzero(alive & (roles == ROLE_LEADER))
        tli = tl[0] if len(tl) else -1
        ok = "（命中）" if bl == tli and tli >= 0 else \
             ("（誤判）" if bl >= 0 else "")
        fn = FORMATION_NAMES.get(self.cfg.swarm.formation,
                                 self.cfg.swarm.formation)
        pn = {"ai": "指揮節點打擊", "nearest": "最近目標",
              "random": "隨機"}.get(self.cfg.defense.policy,
                                   self.cfg.defense.policy)
        is_ai = getattr(self.cfg.defense, "mode", None) == "ai" \
            or self.cfg.defense.policy == "ai"
        mode_tag = "AI" if is_ai else "傳統"
        ident_word = "AI判定領機" if is_ai else "規則判定領機"
        self.hud.set_text(
            f"台灣海峽防衛戰    T = {t:6.1f} s\n"
            f"攻方 {fn}陣　vs　防方 {mode_tag}·{pn}\n"
            f"{ident_word} {('#'+str(bl)) if bl>=0 else '—'} "
            f"(conf={self.rec.leader_conf[k]:.2f}){ok}")

    def _update_telemetry(self, k, t, alive, succ, roles):
        rec = self.rec
        na, ns = int(alive.sum()), int(succ.sum())
        nd = self.n - na - ns
        ammo = self._ammo_at(k)
        self.kpi_txt.set_text(
            f"存活 {na:2d}     突防 {ns:2d}\n損失 {nd:2d}     彈藥 {ammo:2d}")
        # 協調 C + 預警
        C = rec.coord_C[k]
        self.coord_bar.set_width(C)
        self.coord_bar.set_color(C_TARGET if C > 0.6 else
                                 ("#ffae3b" if C > 0.35 else C_FOLLOW))
        self.coord_lbl.set_text(f"C = {C:.2f}")
        if rec.warn_active[k]:
            self.warn_lbl.set_text("● 全網預警：生效")
            self.warn_lbl.set_color(C_TARGET)
        else:
            self.warn_lbl.set_text("● 全網預警：失效（領機失聯）")
            self.warn_lbl.set_color(C_FOLLOW)
        # 兵力曲線（到目前）
        ts = rec.t[:k + 1]
        self.ln_alive.set_data(ts, rec.alive[:k + 1].sum(axis=1))
        self.ln_thru.set_data(ts, rec.succeeded[:k + 1].sum(axis=1))
        # 識別信心曲線
        self.ln_conf.set_data(ts, rec.leader_conf[:k + 1])
        self.conf_lbl.set_text(f"目前 {rec.leader_conf[k]:.2f}")
        # 事件（去除 emoji 避免方塊）
        evs = [f"[{et:5.0f}s] {_clean(m)}" for et, m in rec.events
               if et <= t][-6:]
        self.ev_txt.set_text("\n".join(evs))

    def _ammo_at(self, k):
        n0 = self.cfg.defense.n_missiles
        fired = sum(1 for et, m in self.rec.events
                    if "發射" in m and et <= self.rec.t[k])
        return max(0, n0 - fired)

    # ------------------------------------------------------------ 輸出
    def show(self):
        self._build()
        self.anim = FuncAnimation(self.fig, self._update,
                                  frames=len(self.frames), interval=40,
                                  blit=False, repeat=False)
        plt.show()

    def save(self, filename, fps=20):
        self._build()
        anim = FuncAnimation(self.fig, self._update, frames=len(self.frames),
                             interval=1000 / fps, blit=False)
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".mp4" and shutil.which("ffmpeg"):
            writer = FFMpegWriter(fps=fps, bitrate=3200)
        else:
            if ext == ".mp4":
                filename = filename.replace(".mp4", ".gif")
            writer = PillowWriter(fps=min(fps, 14))
        print(f"[viz2d] 輸出動畫 {filename}（{len(self.frames)} 幀）…")
        anim.save(filename, writer=writer)
        print(f"[viz2d] 完成 -> {filename}")
        if self.ext_fig is None:
            plt.close(self.fig)

    def snapshots(self, outdir, times=None):
        self._build()
        os.makedirs(outdir, exist_ok=True)
        rec = self.rec
        if times is None:
            tt = [rec.t[0], rec.t[len(rec.t) // 3]]
            lk = [et for et, m in rec.events if "領機" in m and "擊落" in m]
            if lk:
                tt.append(lk[0] + 3)
            tt += [rec.t[int(len(rec.t) * 0.8)], rec.t[-1]]
            times = sorted(set(min(rec.t[-1], x) for x in tt))
        files = []
        for x in times:
            k = min(int(np.searchsorted(rec.t, x)), len(rec.t) - 1)
            fi = min(range(len(self.frames)),
                     key=lambda ff: abs(self.frames[ff] - k))
            self._missile_hist = {}
            for f0 in range(max(0, fi - 6), fi + 1):
                self._update(f0)
            fn = os.path.join(outdir, f"map_t{rec.t[self.frames[fi]]:.0f}s.png")
            self.fig.savefig(fn, dpi=110, facecolor=BG)
            files.append(fn)
        print(f"[viz2d] 已輸出 {len(files)} 張 -> {outdir}")
        if self.ext_fig is None:
            plt.close(self.fig)
        return files

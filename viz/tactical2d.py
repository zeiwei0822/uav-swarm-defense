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
                             PARADIGM, formation_paradigm)

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
C_SEAD = "#E64DFF"        # 反輻射(SEAD)機：醒目紫紅，衝防空撕破口
C_COMM = "#3d7fb0"
C_PRED = "#00E5FF"
C_TARGET = "#46c84e"
C_FX = "#FF7000"
FG = "#e6edf3"
TRAIL = 70
FX_LIFE = 16
# SIGINT/ESM 未解碼機體的灰藍色（看得到形體、尚未被火控鎖定）
UNDECODED = (0.42, 0.52, 0.60, 0.9)
# 要點2：領機/中繼失效處理策略顯示名稱（與 app.py FAIL_MODES 對應）
FAIL_NAMES = {"chain": "繼承鏈", "health": "健康度選舉", "bionic": "仿生湧現"}
# 要點1 慢動作視窗半徑（步）：關鍵時刻前後各放慢這麼多步
SLOWMO_WIN = 32

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
    def __init__(self, rec, cfg, stride=3, fig=None, clean=False,
                 slowmo_card=None, slowmo_at=None, tactic_overlay=None,
                 timed_cards=None):
        set_chinese_font()
        self.rec = rec
        self.cfg = cfg
        self.stride = stride
        self.n = rec.pos.shape[1]
        self.ext_fig = fig
        self.clean = clean        # 要點1 純陣型模式：地圖放大、不畫右側 AI 儀表
        self.tactic_overlay = tactic_overlay   # 戰術可見化：None / "tot"(接戰飽和)
        self._missile_hist = {}
        self._built = False
        # ★ 要點1：關鍵時刻放慢＋戰術字卡。slowmo_card=字卡文字（觸發慢動作），
        #   slowmo_at=慢動作中心步(None→自動抓首次突防)。其餘段落用 fast 快轉。
        # timed_cards=[(t_center, duration_s, title, body), ...] 定時浮現旁白。
        self._slowmo_card = slowmo_card
        self._timed_cards = timed_cards or []
        T = len(rec.t)
        if slowmo_card:
            k_key = slowmo_at if slowmo_at is not None else self._find_key_moment()
            self.frames = self._build_frames_slowmo(k_key, T)
            self._slowmo_fi = set(i for i, k in enumerate(self.frames)
                                  if abs(k - k_key) <= SLOWMO_WIN)
            self._key_k = k_key
        else:
            self.frames = list(range(0, T, stride))
            self._slowmo_fi = set()
        self._scan_effects()
        self._scan_narrative()

    def _find_key_moment(self):
        """戰術高潮＝首次突防（無突防則取機群質心最接近目標的時刻）。"""
        rec = self.rec
        for k in range(len(rec.t)):
            if rec.succeeded[k].any():
                return k
        best_k, best_d = 0, 1e18
        for k in range(len(rec.t)):
            m = rec.alive[k]
            if m.any():
                d = float(np.linalg.norm(rec.pos[k, m, :2].mean(axis=0)))
                if d < best_d:
                    best_d, best_k = d, k
        return best_k

    def _build_frames_slowmo(self, k_key, T, fast=4):
        """非均勻幀表：慢動作視窗(±SLOWMO_WIN)每步取樣、其餘 fast 快轉。"""
        frames, k = [], 0
        while k < T:
            frames.append(k)
            k += 1 if (k_key - SLOWMO_WIN <= k <= k_key + SLOWMO_WIN) else fast
        return frames

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
        bionic = getattr(self.cfg.swarm, "fail_strategy", "chain") == "bionic"
        multi = int(getattr(self.cfg.swarm, "n_axes", 1)) > 1
        axes_note = "　機群分三路、向心夾擊推進（多軸戰術）。" if multi else ""
        beats.append(dict(k=0,
                          title="跨海峽進襲 · 三路夾擊" if multi else "跨海峽進襲",
                          focus="swarm",
                          cap=formation_doc(self.cfg.swarm.formation)
                              + axes_note + "　〔要點1：陣形＋戰術〕"))
        # SIGINT 解碼延遲：領機因 C2 流量最大→最先被 ESM 解碼現身（只 AI 防方）
        dec = getattr(rec, "decode", None)
        if is_ai and dec is not None \
                and getattr(self.cfg.defense, "decode_enable", False):
            cf_b = getattr(self.cfg.defense, "decode_confirm", 0.3)
            for k in range(T):
                ldd = np.flatnonzero(rec.alive[k] & (rec.roles[k] == ROLE_LEADER))
                if len(ldd) and dec[k, ldd[0]] >= cf_b:
                    beats.append(dict(k=k, title="SIGINT 射頻確認：領機現身",
                                      focus="leader",
                                      cap="領機進接戰圈！GNN 早認出它『怎麼飛』，現在 SIGINT "
                                          "再從它最強的 C2 射頻『獨立確認』身分（灰轉金、紅星"
                                          "現身）──兩個感測器都點頭，火控才鎖定斬首〔要點4："
                                          "運動＋射頻雙確認，飛得像的誘餌也騙不過〕"))
                    break
        # AI 首次高信心鎖定真領機（只有 AI 防空會「認領機後鎖定打擊」）
        lock = None
        for k in range(T):
            bl = rec.believed_leader[k]
            ld = np.flatnonzero(rec.alive[k] & (rec.roles[k] == ROLE_LEADER))
            if bl >= 0 and len(ld) and bl == ld[0] and rec.leader_conf[k] >= 0.55:
                lock = k
                break
        if lock is not None and is_ai:
            beats.append(dict(k=lock, title="GNN 認出領機", focus="leader",
                              cap="防方 GNN 圖神經網路從『飛行關係』（誰居中轉發、誰被"
                                  "眾機跟隨）認出領機──但它藏在陣形中心、火控暫時搆不到，"
                                  "先標記為頭號目標、等它進圈再用 SIGINT 射頻獨立確認"
                                  "〔要點4：GNN 看運動、SIGINT 看射頻〕"))
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
            cap_fire = ("攔截彈升空！領機藏在陣形中心、ESM 還沒解碼鎖定到它──AI 先用"
                        "LSTM 預測攔截逐一清除外圍中繼／從機，逼領機暴露〔要點3 導引＋"
                        "要點4：先剝護衛、再斬首〕" if is_ai else
                        "攔截彈升空！領機在線→全網提早預警→機群蛇行閃避"
                        "　〔領機＝威脅預警大腦〕")
            beats.append(dict(k=fire[1],
                              title="首次接戰 · 清剿外圍" if is_ai else "首次接戰",
                              focus="missile", cap=cap_fire))
        ld = evk("領機", "擊落")
        lost = evk("迷失")
        seam = evk("無縫接替")          # 光纖：領機亡→即時接替
        if ld and bionic:
            # 仿生湧現：無固定領機，打掉任一架鄰機自動補位
            beats.append(dict(k=ld[1], title="打掉一架 · 群體無感", focus="swarm",
                              cap="仿生湧現根本沒有固定領機——打掉任何一架，鄰機靠"
                                  "對齊/聚合自動補位、群體照常推進〔策略③：免單點故障，"
                                  "AI 斬首徹底失效〕"))
        elif ld and fiber:
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
        # 遞補重組（韌性）：只要領機死後出現遞補事件就 narrate，即使機群最終仍被壓垮。
        # （舊版用 if/elif 與「最終癱瘓」互斥 → succession 發生卻不顯示，誤導成「沒有遞補」）
        sup = evk("遞補", after=ld[0]) if ld else None
        if sup:
            beats.append(dict(k=sup[1], title="遞補重組 · 攻防拉鋸",
                              focus="leader",
                              cap="順位中繼機升任新領機、機群恢復協調與編隊；但防方 GNN "
                                  "立刻又認出新領機→可再次斬首──這就是攻防拉鋸"
                                  "〔要點2 韌性 ↔ 要點4 再獵殺〕"))
        # 最終癱瘓：繼任者也被連續狙殺、繼承順位耗盡 → 無人再遞補（須在大量突防前才算成效）
        meaningful_lost = False
        if lost:
            succ_at = int(rec.succeeded[min(lost[1], T - 1)].sum())
            meaningful_lost = succ_at < self.n * 0.5
        if meaningful_lost:
            cap_lost = ("繼任領機也被 GNN 認出、接連狙殺──繼承順位耗盡、無人再遞補，"
                        "協調徹底瓦解、機群迷失盤旋〔要點2 的極限：連續斬首壓垮繼承鏈〕"
                        if sup else
                        "指揮鏈被打斷、無人遞補，協調瓦解、機群迷失盤旋──癱瘓指揮鏈的"
                        "效果〔要點2 的反證〕")
            beats.append(dict(k=lost[1], title="指揮鏈瓦解 · 機群癱瘓",
                              focus="cgauge", cap=cap_lost))
        # 要點2 失效應變情境（依失效策略觸發；報告四策略＋情境一/二）
        for kw, ttl, cap in [
            ("健康度選舉", "健康度選舉",
             "領機失效→存活機依 S_node（電量/網路中心性/算力/感測）分散式選最強者接任〔策略②〕"),
            ("向心收縮", "向心收縮",
             "中繼失效→全隊縮短間距、改由領機 LOS 直接控制，跳過需要中繼〔情境二·3〕"),
            ("集群分裂", "集群分裂",
             "大群指揮全失→分裂為 2 組、各自健康度選領機、互為犄角續突〔情境二·1〕"),
            ("跨組", "跨組自癒",
             "某組指揮全失→孤兒機併入最近一組的指揮網〔情境一·跨組 mesh 自癒〕"),
        ]:
            e = evk(kw)
            if e:
                beats.append(dict(k=e[1], title=ttl, focus="cgauge", cap=cap))
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
        if bionic:
            cap_end = (f"{verdict}。仿生湧現無固定領機、人人是領機也都不是——"
                       f"打掉任一架都不影響群體，AI 斬首在此徹底失效〔策略③："
                       f"免單點故障〕" if is_ai else
                       f"{verdict}。仿生湧現去中心化群飛、免單點故障。")
        elif fiber:
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
        mode_line = ("〔本場防方〕AI 防空：GNN 認領機(運動) → SIGINT 射頻確認 → "
                     "指揮節點斬首 → LSTM 預測導引"
                     if is_ai else
                     "〔本場防方〕傳統防空：打最近目標 ＋ 規則認領機 ＋ 卡爾曼預測")
        watch = ("觀戰四要點如何串起來：GNN 一開始就認出領機（青圈），但它藏在陣形"
                 "中心、火控搆不到→AI 先用預測攔截剝掉外圍護衛，等領機進接戰圈被 ESM "
                 "解碼鎖定（灰轉金）才斬首；領機一死、右側『協調係數 C』崩落、『全網"
                 "預警』翻紅，接著繼承鏈遞補新領機、GNN 再認、AI 再獵殺。" if is_ai else
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
        if self.clean:                       # 要點1：地圖佔滿、不建右側儀表
            gs = self.fig.add_gridspec(1, 1, left=0.015, right=0.985,
                                       top=0.97, bottom=0.03)
            self.ax = self.fig.add_subplot(gs[0])
            self._build_map()
            _pos = self.ax.get_position()
            _fw, _fh = self.fig.get_size_inches()
            self._cam_aspect = (_pos.width * _fw) / (_pos.height * _fh)
        else:
            gs = self.fig.add_gridspec(1, 2, width_ratios=[2.65, 1.0],
                                       left=0.02, right=0.985, top=0.97,
                                       bottom=0.03, wspace=0.04)
            self.ax = self.fig.add_subplot(gs[0])
            self._build_map()
            self._build_telemetry(gs[1])
            _pos = self.ax.get_position()
            _fw, _fh = self.fig.get_size_inches()
            self._cam_aspect = (_pos.width * _fw) / (_pos.height * _fh)

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
        # 常駐「攻方檔案」卡（左下角）：陣形＋流派＋失效處理策略
        s, c, note = formation_traits(self.cfg.swarm.formation)
        fn = FORMATION_NAMES.get(self.cfg.swarm.formation,
                                 self.cfg.swarm.formation)
        para = PARADIGM_NAMES.get(formation_paradigm(self.cfg.swarm.formation),
                                  "")
        if self.clean:        # 要點1：只談陣型＋戰術＋航路，不提失效處理(要點2)
            card = f"攻方　{fn}·{para}\n戰術：{note}"
        elif is_fiber(self.cfg.swarm.formation):
            card = f"攻方　{fn}·{para}　｜　失效處理：光纖無縫遞補（後機續突）" \
                   f"\n戰術：{note}"
        else:
            fs = getattr(self.cfg.swarm, "fail_strategy", "chain")
            card = f"攻方　{fn}·{para}　｜　失效處理：{FAIL_NAMES.get(fs, fs)}" \
                   f"\n戰術：{note}"
        self._atk_card = ax.text(
                0.012, 0.045, card,
                transform=ax.transAxes, ha="left", va="bottom",
                color="#9fc0d4", fontsize=12 if self.clean else 11.5, zorder=11,
                linespacing=1.5, bbox=dict(boxstyle="round,pad=0.4", fc="#0c1622",
                                           ec="#2f5a7a", alpha=0.88))
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
            0.5, 0.15, "", transform=ax.transAxes, ha="center", va="bottom",
            color=FG, fontsize=15.5, zorder=12, wrap=True,
            bbox=dict(boxstyle="round,pad=0.55", fc="#0c1622", ec="#2f5a7a",
                      alpha=0.93))
        self.callout = ax.text(
            0.5, 0.52, "", transform=ax.transAxes, ha="center", va="center",
            color=FG, fontsize=16.5, zorder=20, linespacing=1.75,
            visible=False, bbox=dict(boxstyle="round,pad=0.95", fc="#0c1622",
                                     ec=C_LEADER, alpha=0.97))
        # 要點1 戰術字卡（slow-mo 關鍵時刻於下中浮現，聚焦「這是什麼戰術」）
        self.tactic_card = ax.text(
            0.5, 0.07, "", transform=ax.transAxes, ha="center", va="bottom",
            color="#fff3c4", fontsize=22, weight="bold", zorder=21,
            linespacing=1.45, visible=False,
            bbox=dict(boxstyle="round,pad=0.7", fc="#1a1206", ec=C_LEADER,
                      alpha=0.97))
        # SEAD 撕破口：防空火力遭壓制時的紅色警示（要點1 arrowhead）
        self.suppress_lbl = ax.text(
            0.5, 0.965, "", transform=ax.transAxes, ha="center", va="top",
            color="#ffffff", fontsize=18, weight="bold", zorder=22,
            visible=False, bbox=dict(boxstyle="round,pad=0.5", fc="#7a0010",
                                     ec="#ff5252", alpha=0.95))
        self._dc = {ROLE_LEADER: mcolors.to_rgba(C_LEADER),
                    ROLE_RELAY: mcolors.to_rgba(C_RELAY),
                    ROLE_FOLLOWER: mcolors.to_rgba(C_FOLLOW)}

    def _legend(self, ax):
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
        if self.clean:        # 要點1：只留陣型與航路相關，不放 AI 識別/預測
            h = [
                Line2D([], [], marker="*", color="none", markerfacecolor=C_LEADER,
                       markeredgecolor="w", markersize=15, label="領機（放大）"),
                Patch(facecolor=C_RELAY, label="中繼機"),
                Patch(facecolor=C_FOLLOW, label="從機"),
                Patch(facecolor=C_MISSILE, label="攔截彈"),
                Line2D([], [], color=C_FOLLOW, alpha=0.6, label="飛行航跡"),
                Line2D([], [], color=C_COMM, label="通訊鏈"),
            ]
            ax.legend(handles=h, loc="upper right", facecolor=PANEL,
                      labelcolor=FG, edgecolor="#30363d", fontsize=13,
                      framealpha=0.85)
            return
        is_ai = getattr(self.cfg.defense, "mode", None) == "ai" \
            or self.cfg.defense.policy == "ai"
        show_dec = is_ai and getattr(self.cfg.defense, "decode_enable", False)
        h = [
            Line2D([], [], marker="*", color="none", markerfacecolor=C_LEADER,
                   markeredgecolor="w", markersize=15, label="領機（放大）"),
            Patch(facecolor=C_RELAY, label="中繼機"),
            Patch(facecolor=C_FOLLOW, label="從機"),
        ]
        if show_dec:
            h.append(Patch(facecolor=UNDECODED[:3],
                           label="未確認（SIGINT截獲中）"))
        h += [
            Patch(facecolor=C_MISSILE, label="攔截彈"),
            Line2D([], [], marker="o", color="none", markeredgecolor=C_PRED,
                   markersize=12,
                   label="GNN鎖定領機" if is_ai else "規則判定領機"),
            Line2D([], [], color=C_COMM, label="通訊鏈"),
            Line2D([], [], color=C_PRED, ls="--",
                   label="AI預測軌跡" if is_ai else "卡爾曼預測"),
        ]
        ax.legend(handles=h, loc="upper right", facecolor=PANEL,
                  labelcolor=FG, edgecolor="#30363d", fontsize=12,
                  framealpha=0.85)

    def _build_telemetry(self, gs_cell):
        sub = gs_cell.subgridspec(
            6, 1, height_ratios=[0.9, 0.9, 1.1, 1.1, 1.15, 1.2], hspace=0.62)
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
        self._style_panel(self.ax_conf, "GNN 對領機的識別信心" if _is_ai else
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
        # SIGINT 射頻確認：各機確認值爬向其『發射量上限』(領機1.0/中繼0.5/從機0.1)，
        # 越過確認線(decode_confirm)才可斬首→從機/誘餌封頂在 0.1、永遠過不了線
        self.ax_lock = f.add_subplot(sub[4])
        self._is_ai_lock = _is_ai and \
            getattr(self.cfg.defense, "decode_enable", False)
        self._style_panel(self.ax_lock, "SIGINT 射頻確認（領機 C2 最強→最先確認）")
        cf0 = getattr(self.cfg.defense, "decode_confirm", 0.3)
        self.ax_lock.set_xlim(0, 1)
        self.ax_lock.set_ylim(-0.5, 5.5)
        self.ax_lock.set_yticks([])
        self.ax_lock.set_xticks([0, cf0, 1.0])
        self.ax_lock.set_xticklabels(["0", "確認線", "領機滿"], fontsize=9)
        self.ax_lock.axvline(cf0, color=C_TARGET, ls=":", lw=1.3, alpha=0.85)
        self.lock_bars, self.lock_lbls = [], []
        for r in range(6):
            yy = 5 - r                       # 由上到下排列
            b = self.ax_lock.barh([yy], [0], height=0.62, color=C_FOLLOW,
                                  align="center")[0]
            self.lock_bars.append(b)
            self.lock_lbls.append(self.ax_lock.text(
                0.02, yy, "", va="center", ha="left", color=FG,
                fontsize=10.5, weight="bold"))
        self.lock_note = self.ax_lock.text(
            0.5, 2.5, "", va="center", ha="center", color="#8aa0b5",
            fontsize=11.5)
        # 事件
        self.ax_ev = f.add_subplot(sub[5])
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

        # SIGINT 解碼延遲：AI 防方下，未解碼的敵機只顯示灰藍(看得到形體、尚未解析)
        dec = getattr(rec, "decode", None)
        _is_ai = getattr(self.cfg.defense, "mode", None) == "ai" \
            or self.cfg.defense.policy == "ai"
        show_dec = _is_ai and getattr(self.cfg.defense, "decode_enable", False) \
            and dec is not None

        sead_mask = getattr(rec, "is_sead", None)     # 反輻射機遮罩（靜態）
        sead_rgba = mcolors.to_rgba(C_SEAD)
        flying = np.flatnonzero(alive & ~succ)
        polys, cols = [], []
        beam = None
        for i in flying:
            yaw = np.arctan2(vel[i, 1], vel[i, 0]) if np.linalg.norm(vel[i]) > 1e-6 else 0.0
            undec = show_dec and dec[k, i] < 1.0
            is_sead_i = sead_mask is not None and i < len(sead_mask) \
                and sead_mask[i]
            if is_sead_i:
                sc = SC_DRONE * 1.2                  # 反輻射機略大、醒目
            elif roles[i] == ROLE_LEADER and not undec:
                sc = SC_DRONE * MULT_LEADER
            elif roles[i] == ROLE_RELAY and not undec:
                sc = SC_DRONE * MULT_RELAY
            else:
                sc = SC_DRONE                       # 未解碼一律顯示為一般大小(未識別)
            polys.append(_rot2d(_DRONE_GLYPH, yaw, sc, pos[i]))
            if is_sead_i:
                cols.append(sead_rgba)
            else:
                cols.append(UNDECODED if undec else self._dc[int(roles[i])])
        self.drone_pc.set_verts(polys)
        self.drone_pc.set_facecolors(cols if cols else [(0, 0, 0, 0)])

        # 領機文字標籤已移除（依使用者要求；多領機/遞補時會亂跳）。
        # 領機仍以「放大金色機體」標示，AI 判定領機則以青色圈標示。
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

        # AI 預測線 + 判定領機（要點3/4）；clean 模式(要點1)全部不畫
        bl = rec.believed_leader[k]
        if self.clean:
            self.pred_lc.set_segments([])
            self.sc_ai.set_offsets(np.empty((0, 2)))
        else:
            psegs = []
            for _tid, path in rec.pred_paths[k].items():
                psegs.append(path[::3, :2])
            self.pred_lc.set_segments(psegs)
            cf = getattr(self.cfg.defense, "decode_confirm", 0.3)
            bl_dec = (not show_dec) or (bl >= 0 and dec[k, bl] >= cf)
            if bl >= 0 and alive[bl] and rec.leader_conf[k] > 0.25 and bl_dec:
                self.sc_ai.set_offsets([pos[bl]])
            else:
                self.sc_ai.set_offsets(np.empty((0, 2)))

        self._draw_fx(k)
        self._draw_hud(k, t, alive, succ, roles, bl)
        if not self.clean:
            self._update_telemetry(k, t, alive, succ, roles)
        self._update_narrative(k, pos, alive, roles, mlist)
        # 要點1：關鍵時刻 鏡頭拉近 + 放慢 + 戰術字卡聚焦
        if getattr(self, "_slowmo_card", None):
            self._focus_zoom(k, pos, alive, succ)
        # 戰術可見化警示橫幅：SEAD 撕破口（防空遭壓制）/ ToT 接戰飽和（同時湧入塞爆）
        alert = ""
        supp = getattr(rec, "suppressed", None)
        if supp is not None and k < len(supp) and bool(supp[k]):
            alert = "● 防空火力遭壓制 · 雷達破口開啟 ●"
        elif self.tactic_overlay == "tot":
            nz = self._zone_count(k, alive, succ)
            nl = int(getattr(self.cfg.defense, "n_launchers", 2))
            if nz > nl:
                alert = (f"● 防空接戰飽和：同時 {nz} 架湧入接戰圈 · "
                         f"只有 {nl} 座發射器攔不完 ●")
        self.suppress_lbl.set_text(alert)
        self.suppress_lbl.set_visible(bool(alert))
        return []

    def _zone_count(self, k, alive, succ):
        """同時進入目標近域(接戰圈內)的存活敵機數——ToT 同時到達塞爆防空的可見指標。"""
        m = alive & ~succ
        if not m.any():
            return 0
        d = np.linalg.norm(self.rec.pos[k, m, :2], axis=1)   # 距目標(原點)
        return int((d < 900).sum())

    def _focus_zoom(self, k, pos, alive, succ):
        """要點1 慢動作視窗：鏡頭平滑拉近機群、淡出 HUD/檔案卡、浮現戰術字卡，
        讓觀眾在關鍵時刻清楚看見『這是什麼戰術』。視窗外回全景。"""
        z = max(0.0, 1.0 - abs(k - self._key_k) / float(SLOWMO_WIN))
        z = z * z * (3 - 2 * z)              # smoothstep 平滑進出
        fx, fy = self._xr, self._yr
        if z <= 0.02:                        # 全景
            self.ax.set_xlim(*fx); self.ax.set_ylim(*fy)
            self.tactic_card.set_visible(False)
            self.hud.set_visible(True); self._atk_card.set_visible(True)
            return
        m = alive & ~succ
        p = pos[m] if m.any() else pos[alive]
        if len(p) == 0:
            return
        cx, cy = float(p[:, 0].mean()), float(p[:, 1].mean())
        hw_d = max((p[:, 0].max() - p[:, 0].min()) / 2,
                   (p[:, 1].max() - p[:, 1].min()) / 2 * self._cam_aspect, 340)
        hw = hw_d * 1.7
        hh = hw / self._cam_aspect
        zx, zy = (cx - hw, cx + hw), (cy - hh, cy + hh)
        self.ax.set_xlim(fx[0] * (1 - z) + zx[0] * z, fx[1] * (1 - z) + zx[1] * z)
        self.ax.set_ylim(fy[0] * (1 - z) + zy[0] * z, fy[1] * (1 - z) + zy[1] * z)
        deep = z > 0.35                      # 拉近夠深 → 換上戰術字卡、淡出邊框
        self.tactic_card.set_visible(deep)
        if deep:
            self.tactic_card.set_text(self._slowmo_card)
        self.hud.set_visible(not deep)
        self._atk_card.set_visible(not deep)

    _CN = "〇一二三四五六七八九十"

    def _update_narrative(self, k, pos, alive, roles, mlist):
        """分幕橫幅 + 旁白字幕 + 聚光燈（資料驅動引導）"""
        if self.clean:        # 要點1：不放通用分幕旁白，改用 slow-mo 戰術字卡聚焦
            if self._timed_cards:
                t_now = self.rec.t[k] if k < len(self.rec.t) else self.rec.t[-1]
                active = None
                for (t_cen, dur, title, body) in self._timed_cards:
                    if t_cen - dur / 2 <= t_now <= t_cen + dur / 2:
                        active = (title, body)
                if active:
                    self.banner.set_text(active[0])
                    self.subtitle.set_text(active[1])
                    self.subtitle.set_visible(True)
                else:
                    self.banner.set_text("")
                    self.subtitle.set_text("")
                    self.subtitle.set_visible(False)
            else:
                self.banner.set_text("")
                self.subtitle.set_text("")
                self.subtitle.set_visible(False)
            return
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
        # 暫停解說卡顯示時隱藏底部字幕，避免兩塊文字重疊（破圖）
        self.subtitle.set_visible(not self.callout.get_visible())
        # 聚光燈圈圈已移除（依使用者要求）；保留 focus 供協調儀表閃爍判斷
        focus = b["focus"]
        self.spot.set_offsets(np.empty((0, 2)))
        self.spot.set_sizes([])
        # 協調儀表閃爍（斬首/崩潰時把注意力導到 C）；clean 模式無此面板
        if not self.clean:
            flash = focus == "cgauge" and abs(k - b["k"]) < 28 \
                and int(k * 0.3) % 2 == 0
            self.ax_coord.set_facecolor("#3a1820" if flash else PANEL)

    def show_callout(self, text):
        """顯示置中解說卡（開場簡報 / 導覽暫停）；同時隱藏底部字幕避免重疊破圖"""
        self.callout.set_text(_clean(text))
        self.callout.set_visible(True)
        self.subtitle.set_visible(False)

    def hide_callout(self):
        self.callout.set_visible(False)
        self.subtitle.set_visible(True)

    def beat_text(self, idx):
        """取第 idx 個 beat 的解說（給 app 暫停卡用）；cap 先換行避免單行溢出畫面"""
        if 0 <= idx < len(self.beats):
            b = self.beats[idx]
            n = idx + 1
            num = self._CN[n] if n < len(self._CN) else str(n)
            return (f"◆ 第{num}幕　{b['title']}\n\n"
                    f"{_wrap_cn(b['cap'], 22)}\n\n（按「繼續」往下）")
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
        fn = FORMATION_NAMES.get(self.cfg.swarm.formation,
                                 self.cfg.swarm.formation)
        para = PARADIGM_NAMES.get(formation_paradigm(self.cfg.swarm.formation),
                                  "")
        if self.clean:        # 要點1：聚焦陣型＋航路＋突防，不提 AI 識別
            self.hud.set_text(
                f"要點1 · 機群陣型與飛行路徑　　T = {t:5.1f} s\n"
                f"攻方 {fn}·{para}　vs　防方 傳統防空\n"
                f"突防 {ns}　　存活 {na}　　損失 {nd}")
            return
        tl = np.flatnonzero(alive & (roles == ROLE_LEADER))
        tli = tl[0] if len(tl) else -1
        ok = "（命中）" if bl == tli and tli >= 0 else \
             ("（誤判）" if bl >= 0 else "")
        pn = {"ai": "指揮節點打擊", "nearest": "最近目標",
              "random": "隨機"}.get(self.cfg.defense.policy,
                                   self.cfg.defense.policy)
        is_ai = getattr(self.cfg.defense, "mode", None) == "ai" \
            or self.cfg.defense.policy == "ai"
        mode_tag = "AI" if is_ai else "傳統"
        ident_word = "GNN認領機" if is_ai else "規則判定領機"
        # 火控鎖定狀態（ESM 解碼）：只在 AI 防方且啟用解碼時顯示
        lock_txt = ""
        show_dec = is_ai and getattr(self.cfg.defense, "decode_enable", False) \
            and getattr(self.rec, "decode", None) is not None
        if show_dec and bl >= 0 and alive[bl]:
            dv = float(self.rec.decode[k, bl])
            cf = getattr(self.cfg.defense, "decode_confirm", 0.3)
            lock_txt = " · SIGINT已確認" if dv >= cf \
                else f" · SIGINT確認中{int(dv * 100)}%"
        self.hud.set_text(
            f"台灣海峽防衛戰    T = {t:6.1f} s\n"
            f"攻方 {fn}·{para}　vs　防方 {mode_tag}·{pn}\n"
            f"{ident_word} {('#'+str(bl)) if bl>=0 else '—'} "
            f"(conf={self.rec.leader_conf[k]:.2f}){lock_txt}{ok}")

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
        # 火控鎖定進度條（ESM 解碼）
        self._update_lock(k, alive, roles)
        # 事件（去除 emoji 避免方塊）
        evs = [f"[{et:5.0f}s] {_clean(m)}" for et, m in rec.events
               if et <= t][-6:]
        self.ev_txt.set_text("\n".join(evs))

    def _update_lock(self, k, alive, roles):
        """火控鎖定面板：接戰圈內(解碼>0)各機鎖定進度，GNN 懷疑領機列最上。"""
        if not getattr(self, "_is_ai_lock", False):
            for b in self.lock_bars:
                b.set_width(0)
            for tt in self.lock_lbls:
                tt.set_text("")
            self.lock_note.set_text("傳統防空：無 ESM 鎖定階段（看到即接戰）")
            return
        dec = self.rec.decode[k]
        bl = int(self.rec.believed_leader[k])
        cf = getattr(self.cfg.defense, "decode_confirm", 0.3)
        cand = [i for i in range(self.n) if alive[i] and dec[i] > 1e-3]
        # GNN 懷疑領機優先排最上，其餘依 SIGINT 確認值遞減
        cand.sort(key=lambda i: (i != bl, -float(dec[i])))
        cand = cand[:6]
        for r in range(6):
            b, tt = self.lock_bars[r], self.lock_lbls[r]
            if r < len(cand):
                i = cand[r]
                v = float(min(1.0, dec[i]))
                is_bl = (i == bl and bl >= 0)
                confirmed = v >= cf          # SIGINT 確認為指揮鏈節點(可斬首)
                b.set_width(v)
                b.set_color(C_LEADER if is_bl else
                            (C_RELAY if roles[i] == ROLE_RELAY else C_FOLLOW))
                b.set_alpha(1.0 if confirmed else 0.4)
                lab = f"#{i}  {int(round(v * 100)):3d}%"
                if is_bl and confirmed:
                    lab += "  〔GNN+SIGINT 雙確認〕"
                elif is_bl:
                    lab += "  〔GNN認·SIGINT未確認〕"
                elif confirmed:
                    lab += "  已確認"
                tt.set_text(lab)
            else:
                b.set_width(0)
                tt.set_text("")
        # 確認門檻參考線（越過才可斬首）
        self.lock_note.set_text("" if cand else "尚無敵機進入接戰圈")

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

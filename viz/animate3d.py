# -*- coding: utf-8 -*-
"""
3D 戰場動畫（桌面版）：台灣海峽跨海進攻 — 跟拍鏡頭 + 交戰特效
==============================================================
· 地形：海面、對岸大陸、台灣島、中央山脈、海峽中線（viz/models3d.py）
· 無人機 / 攔截彈：低多邊形 3D 實體，依航向旋轉；領機放大＋光柱＋亮金，一眼可辨
· 交戰特效：擊落火球＋碎片、突防綠光、飛彈尾焰
· 跟拍鏡頭緊跟交火；放大加框的 HUD 與事件時間軸
"""
import os
import shutil
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.animation import FuncAnimation, FFMpegWriter, PillowWriter
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection

from config import ROLE_FOLLOWER, ROLE_RELAY, ROLE_LEADER
from viz import set_chinese_font
from viz.models3d import (drone_template, missile_template,
                          missile_flame_template, transform_meshes,
                          heading_angles, build_strait_terrain)

C_LEADER = "#FFD700"     # 亮金 — 領機（放大）
C_RELAY = "#FF8A30"      # 橙 — 中繼機（略大）
C_FOLLOW = "#C62828"     # 暗紅 — 從機
C_DEAD = "#9E9E9E"
C_MISSILE = "#26C6DA"
C_FLAME = "#FFB300"
C_COMM = "#4FC3F7"
C_PRED = "#00E5FF"
C_DEFENSE = "#1565C0"
C_TARGET = "#43A047"
TRAIL_LEN = 90
SCALE_DRONE = 56.0
SCALE_MISSILE = 40.0
MULT_LEADER = 2.1        # 領機機體放大倍率
MULT_RELAY = 1.4
FX_LIFE = 16             # 爆炸特效壽命（幀）


class Animator3D:
    def __init__(self, rec, cfg, stride=3, fig=None):
        set_chinese_font()
        self.rec = rec
        self.cfg = cfg
        self.stride = stride
        self.frames = list(range(0, len(rec.t), stride))
        self.n = rec.pos.shape[1]
        self._missile_hist = {}
        self._built = False
        self.ext_fig = fig
        self.drone_tmpl = drone_template()
        self.missile_tmpl = missile_template()
        self.flame_tmpl = missile_flame_template()
        self.nfd = len(self.drone_tmpl)
        self._cam = None
        self._scan_effects()

    def _scan_effects(self):
        """預掃描擊落/突防事件 → 爆炸特效資料（位置、時刻、類型、碎片方向）"""
        rec = self.rec
        self.explosions = []          # (k, pos3, kind)  kind: 'kill'/'through'
        self._frags = []
        for i in range(self.n):
            a = rec.alive[:, i]
            deaths = np.flatnonzero(a[:-1] & ~a[1:])
            for k in deaths:
                kind = "through" if rec.succeeded[k + 1, i] else "kill"
                self.explosions.append((k + 1, rec.pos[k + 1, i].copy(), kind))
        for idx in range(len(self.explosions)):
            rng = np.random.default_rng(1000 + idx)
            d = rng.normal(size=(9, 3))
            d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-9
            d[:, 2] = np.abs(d[:, 2]) * 0.6 + 0.15      # 碎片偏向上飛
            self._frags.append(d)

    # ------------------------------------------------------------ 場景建立
    def _build(self):
        if self._built:
            return
        self._built = True
        rec = self.rec
        self.fig = self.ext_fig if self.ext_fig is not None \
            else plt.figure(figsize=(13, 8))
        self.fig.patch.set_facecolor("#0d1117")
        ax = self.fig.add_subplot(111, projection="3d")
        self.ax = ax
        ax.set_facecolor("#0d1117")
        for pane in (ax.xaxis, ax.yaxis, ax.zaxis):
            pane.set_pane_color((0.04, 0.07, 0.12, 1.0))
            pane.label.set_color("#dddddd")
            pane.set_tick_params(colors="#888888")
        ax.grid(False)
        ax.set_xlabel("← 西（對岸）   東（台灣）→  X(m)", fontsize=12,
                      labelpad=8)
        ax.set_ylabel("Y (m)", fontsize=12)
        ax.set_zlabel("高度 (m)", fontsize=12)
        ax.tick_params(labelsize=9)

        # 全場地形範圍（涵蓋對岸→台灣；跟拍鏡頭在此之上移動）
        allp = rec.pos.reshape(-1, 3)
        allp = allp[np.isfinite(allp).all(axis=1)]
        xr = (min(allp[:, 0].min() - 200, -3200),
              max(allp[:, 0].max() + 200, 450))
        yr = (min(allp[:, 1].min() - 250, -1300),
              max(allp[:, 1].max() + 250, 1300))
        self._full_xr, self._full_yr = xr, yr
        ax.set_box_aspect((1, 1, 0.5))
        ax.view_init(elev=20, azim=-58)

        arts, labels = build_strait_terrain(np.zeros(3), xr, yr)
        for _name, art in arts:
            ax.add_collection3d(art)
        self._terrain_labels = []
        for x, y, z, txt, col in labels:
            self._terrain_labels.append(
                ax.text(x, y, z, txt, color=col, fontsize=11, weight="bold",
                        ha="center"))

        # 防守目標
        ax.scatter([0], [0], [6], marker="*", s=560, c=C_TARGET,
                   edgecolors="white", linewidths=1.0, zorder=6,
                   depthshade=False)
        ax.text(0, 0, 80, "防守目標", color=C_TARGET, fontsize=12,
                ha="center", weight="bold")
        ax.scatter([0], [0], [10], marker="^", s=220, c=C_DEFENSE,
                   edgecolors="white", linewidths=0.7, depthshade=False)
        th = np.linspace(0, 2 * np.pi, 90)
        R = self.cfg.defense.engage_range
        ax.plot(R * np.cos(th), R * np.sin(th), 2, color=C_DEFENSE,
                alpha=0.5, lw=1.3, ls="--")

        # 動態實體
        dummy = np.zeros((1, 3, 3))
        self.drone_mesh = Poly3DCollection(dummy, edgecolors="#141414",
                                           linewidths=0.3, zsort="average")
        ax.add_collection3d(self.drone_mesh)
        self.missile_mesh = Poly3DCollection(dummy, facecolor=C_MISSILE,
                                             edgecolors="#0a3a40",
                                             linewidths=0.25)
        ax.add_collection3d(self.missile_mesh)
        self.flame_mesh = Poly3DCollection(dummy, facecolor=C_FLAME,
                                           edgecolors="none", alpha=0.9)
        ax.add_collection3d(self.flame_mesh)

        dl = [[(0, 0, 0), (0, 0, 0)]]
        self.leader_beams = Line3DCollection(dl, colors=C_LEADER, alpha=0.55,
                                             linewidths=2.4)
        ax.add_collection3d(self.leader_beams)
        self.comm_lines = Line3DCollection(dl, colors=C_COMM, alpha=0.30,
                                           linewidths=0.9)
        ax.add_collection3d(self.comm_lines)
        self.pred_lines = Line3DCollection(dl, colors=C_PRED, alpha=0.85,
                                           linewidths=1.6, linestyles="--")
        ax.add_collection3d(self.pred_lines)
        self.missile_trails = Line3DCollection(dl, colors=C_MISSILE,
                                               alpha=0.42, linewidths=0.9)
        ax.add_collection3d(self.missile_trails)
        self.drone_trails = [ax.plot([], [], [], lw=0.7, alpha=0.4,
                                     color=C_FOLLOW)[0] for _ in range(self.n)]
        self.sc_dead = ax.scatter([], [], [], marker="x", s=46, c=C_DEAD,
                                  depthshade=False, zorder=5)
        self.sc_aiguess = ax.scatter([], [], [], marker="o", s=620,
                                     facecolors="none", edgecolors=C_PRED,
                                     linewidths=2.2, depthshade=False)
        # 交戰特效（火球/碎片/突防綠光）
        self.fx = ax.scatter([], [], [], s=[], c=[], depthshade=False,
                             zorder=8, edgecolors="none")
        # 領機頭頂標籤
        self.leader_label = ax.text(0, 0, 0, "", color=C_LEADER, fontsize=12,
                                    weight="bold", ha="center", zorder=9)
        self.leader_label.set_visible(False)

        self._legend(ax)
        self.hud = self.fig.text(
            0.012, 0.978, "", color="#f0f6fc", fontsize=16, va="top",
            linespacing=1.55, weight="bold",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#0d1117",
                      edgecolor="#30363d", alpha=0.82))
        self.ticker = self.fig.text(
            0.012, 0.022, "", color="#ffd54f", fontsize=13, va="bottom",
            linespacing=1.5,
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#0d1117",
                      edgecolor="#30363d", alpha=0.7))
        self._dc_leader = mcolors.to_rgba(C_LEADER)
        self._dc_relay = mcolors.to_rgba(C_RELAY)
        self._dc_follow = mcolors.to_rgba(C_FOLLOW)

    def _legend(self, ax):
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
        handles = [
            Line2D([], [], marker="*", color="none", markerfacecolor=C_LEADER,
                   markeredgecolor="w", markersize=18, label="領機（放大＋光柱）"),
            Patch(facecolor=C_RELAY, label="中繼機"),
            Patch(facecolor=C_FOLLOW, label="從機"),
            Patch(facecolor=C_MISSILE, label="攔截彈"),
            Line2D([], [], marker="o", color="none", markeredgecolor=C_PRED,
                   markersize=13, label="AI判定領機"),
            Line2D([], [], marker="o", color="none", markerfacecolor="#FF7000",
                   markersize=13, label="擊落爆炸"),
            Line2D([], [], color=C_COMM, label="通訊鏈"),
            Line2D([], [], color=C_PRED, ls="--", label="AI預測軌跡"),
        ]
        ax.legend(handles=handles, loc="upper right", facecolor="#161b22",
                  labelcolor="#e6edf3", edgecolor="#30363d", fontsize=11)

    # ------------------------------------------------------------ 每幀更新
    def _update(self, fi):
        rec, ax = self.rec, self.ax
        k = self.frames[fi]
        t = rec.t[k]
        pos = rec.pos[k]
        alive = rec.alive[k]
        succ = rec.succeeded[k]
        roles = rec.roles[k]
        kp = max(0, k - 2)
        vel_all = pos - rec.pos[kp]

        # ---- 無人機實體（領機放大 + 光柱 + 顏色）
        flying = np.flatnonzero(alive & ~succ)
        beams = []
        if len(flying):
            p = pos[flying]
            yaw, pitch = heading_angles(vel_all[flying])
            scales = np.full(len(flying), SCALE_DRONE)
            cols = []
            for j, i in enumerate(flying):
                if roles[i] == ROLE_LEADER:
                    scales[j] = SCALE_DRONE * MULT_LEADER
                    cols.extend([self._dc_leader] * self.nfd)
                    beams.append([(pos[i, 0], pos[i, 1], pos[i, 2]),
                                  (pos[i, 0], pos[i, 1], pos[i, 2] + 95)])
                elif roles[i] == ROLE_RELAY:
                    scales[j] = SCALE_DRONE * MULT_RELAY
                    cols.extend([self._dc_relay] * self.nfd)
                else:
                    cols.extend([self._dc_follow] * self.nfd)
            faces = transform_meshes(self.drone_tmpl, p, yaw, pitch, scales)
            self.drone_mesh.set_verts(list(faces))
            self.drone_mesh.set_facecolor(cols)
        else:
            self.drone_mesh.set_verts(list(np.zeros((1, 3, 3))))
            self.drone_mesh.set_facecolor([(0, 0, 0, 0)])
        self.leader_beams.set_segments(beams if beams else
                                       [[(0, 0, 0), (0, 0, 0)]])

        # 領機頭頂標籤
        tl_arr = np.flatnonzero(alive & (roles == ROLE_LEADER))
        if len(tl_arr):
            li = tl_arr[0]
            self.leader_label.set_visible(True)
            self.leader_label.set_position((pos[li, 0], pos[li, 1]))
            self.leader_label.set_3d_properties(pos[li, 2] + 120, zdir="z")
            self.leader_label.set_text("◤ 領機")
        else:
            self.leader_label.set_visible(False)

        # ---- 被擊落
        dead = pos[~alive & ~succ]
        self.sc_dead._offsets3d = ((dead[:, 0], dead[:, 1], dead[:, 2])
                                   if len(dead) else ([], [], []))

        # ---- 尾跡
        k0 = max(0, k - TRAIL_LEN)
        for i in range(self.n):
            ln = self.drone_trails[i]
            if alive[i]:
                seg = rec.pos[k0:k + 1, i]
                m = rec.alive[k0:k + 1, i]
                seg = seg[m] if m.any() else seg[:0]
                ln.set_data_3d(seg[:, 0], seg[:, 1], seg[:, 2])
                ln.set_color(C_LEADER if roles[i] == ROLE_LEADER else C_FOLLOW)
            else:
                ln.set_data_3d([], [], [])

        # ---- 通訊鏈
        segs = [(pos[i], pos[j]) for i, j in rec.comm_edges[k]
                if alive[i] and alive[j]]
        self.comm_lines.set_segments(segs)

        # ---- 飛彈 + 尾焰 + 尾跡
        mlist = rec.missiles[k]
        mfaces, ffaces, trails = [], [], []
        live_ids = set()
        if mlist:
            mpos = np.array([p for _, p, _ in mlist])
            mvel = np.zeros_like(mpos)
            for idx, (mid, p, _tid) in enumerate(mlist):
                live_ids.add(mid)
                h = self._missile_hist.setdefault(mid, [])
                if h:
                    d = p - h[-1][1]
                    if np.linalg.norm(d) > 1e-6:
                        mvel[idx] = d
                h.append((k, p))
            for idx, (mid, p, tid) in enumerate(mlist):
                if np.linalg.norm(mvel[idx]) < 1e-6:
                    mvel[idx] = (pos[tid] - p if tid < self.n
                                 else np.array([1.0, 0, 0]))
            yaw, pitch = heading_angles(mvel)
            mfaces = transform_meshes(self.missile_tmpl, mpos, yaw, pitch,
                                      SCALE_MISSILE)
            ffaces = transform_meshes(self.flame_tmpl, mpos, yaw, pitch,
                                      SCALE_MISSILE)
        self.missile_mesh.set_verts(list(mfaces) if len(mfaces)
                                    else list(np.zeros((1, 3, 3))))
        self.flame_mesh.set_verts(list(ffaces) if len(ffaces)
                                  else list(np.zeros((1, 3, 3))))
        for mid in list(self._missile_hist):
            h = [(kk, p) for kk, p in self._missile_hist[mid] if k - kk <= 22]
            if mid not in live_ids and (not h or k - h[-1][0] > 6):
                del self._missile_hist[mid]
                continue
            self._missile_hist[mid] = h
            if len(h) >= 2:
                pts = np.array([p for _, p in h])
                trails += [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        self.missile_trails.set_segments(trails)

        # ---- 交戰特效（火球/碎片/突防綠）
        self._draw_effects(k)

        # ---- AI 預測軌跡 + 判定領機
        psegs = []
        for _tid, path in rec.pred_paths[k].items():
            pts = path[::3]
            psegs += [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        self.pred_lines.set_segments(psegs)
        bl = rec.believed_leader[k]
        if bl >= 0 and alive[bl] and rec.leader_conf[k] > 0.25:
            self.sc_aiguess._offsets3d = ([pos[bl, 0]], [pos[bl, 1]],
                                          [pos[bl, 2]])
        else:
            self.sc_aiguess._offsets3d = ([], [], [])

        # ---- 跟拍鏡頭
        self._follow_camera(k, pos, alive, succ, mlist)

        # ---- HUD
        self._draw_hud(k, t, alive, succ, roles, bl)
        return []

    def _draw_effects(self, k):
        pts, sizes, cols = [], [], []
        for idx, (ke, pe, kind) in enumerate(self.explosions):
            age = k - ke
            if not (0 <= age < FX_LIFE):
                continue
            f = age / FX_LIFE
            if kind == "kill":
                pts.append(pe)
                sizes.append(720 * (0.5 + 1.5 * f))
                cols.append((1.0, 0.52, 0.06, max(0, 1 - f)))
                for d in self._frags[idx]:
                    pts.append(pe + d * age * 13)
                    sizes.append(110 * (1 - f))
                    cols.append((1.0, 0.82, 0.32, max(0, 1 - f * 1.2)))
            else:
                pts.append(pe)
                sizes.append(900 * (0.4 + 1.4 * f))
                cols.append((0.30, 1.0, 0.45, max(0, 1 - f)))
        # 直接設底層 3D 屬性：3D scatter 的投影排序用 _sizes3d/_facecolor3d，
        # 用 set_sizes(list) 會在 do_3d_projection 的 fancy-index 掛掉
        if pts:
            a = np.array(pts)
            fc = np.asarray(cols, float).reshape(-1, 4)
            self.fx._offsets3d = (a[:, 0], a[:, 1], a[:, 2])
            self.fx._sizes3d = np.asarray(sizes, float)
            self.fx._facecolor3d = fc
            self.fx._edgecolor3d = fc
        else:
            self.fx._offsets3d = ([], [], [])
            self.fx._sizes3d = np.array([])
            self.fx._facecolor3d = np.empty((0, 4))
            self.fx._edgecolor3d = np.empty((0, 4))

    def _follow_camera(self, k, pos, alive, succ, mlist):
        # 範圍只由機群本身決定（飛彈不放大範圍，只把鏡頭略朝來襲方向）
        swarm = pos[alive & ~succ]
        if len(swarm):
            center = swarm.mean(axis=0)
            span = (swarm.max(axis=0) - swarm.min(axis=0))[:2].max()
            half = max(span * 0.58 + 105, 300)
            if len(mlist):
                mc = np.array([p for _, p, _ in mlist]).mean(axis=0)
                center = 0.80 * center + 0.20 * mc
        else:
            center = np.array([0, 0, 100.0])
            half = 600
        if self._cam is None:
            self._cam = [center.copy(), half]
        # EMA 平滑，避免鏡頭抖動
        self._cam[0] = 0.86 * self._cam[0] + 0.14 * center
        self._cam[1] = 0.86 * self._cam[1] + 0.14 * half
        c, h = self._cam[0], self._cam[1]
        ax = self.ax
        ax.set_xlim(c[0] - h, c[0] + h)
        ax.set_ylim(c[1] - h, c[1] + h)
        ax.set_zlim(0, max(c[2] + h * 0.5, 260))

    def _draw_hud(self, k, t, alive, succ, roles, bl):
        n_alive = int(alive.sum())
        n_succ = int(succ.sum())
        n_dead = self.n - n_alive - n_succ
        tl_arr = np.flatnonzero(alive & (roles == ROLE_LEADER))
        tl = tl_arr[0] if len(tl_arr) else -1
        guess = f"#{bl}" if bl >= 0 else "—"
        ok = "（命中）" if bl == tl and tl >= 0 else \
             ("（誤判）" if bl >= 0 else "")
        fname = {"vee": "V字", "wedge": "楔形", "column": "縱隊",
                 "grid": "方陣", "ring": "環形"}.get(self.cfg.swarm.formation,
                                                   self.cfg.swarm.formation)
        pname = {"ai": "AI斬首", "nearest": "最近目標",
                 "random": "隨機"}.get(self.cfg.defense.policy,
                                      self.cfg.defense.policy)
        self.hud.set_text(
            f"台灣海峽防衛戰　T = {t:6.1f} s\n"
            f"攻方 {fname}陣　存活 {n_alive:2d}  突防 {n_succ:2d}  "
            f"損失 {n_dead:2d}      防方 {pname}　彈藥 {self._ammo_at(k):2d}\n"
            f"AI 判定領機 {guess} (conf={self.rec.leader_conf[k]:.2f}) {ok}"
            f"    真實領機 {'#' + str(tl) if tl >= 0 else '—'}")
        evs = [f"[{et:6.1f}s] {msg}" for et, msg in self.rec.events
               if et <= t][-4:]
        self.ticker.set_text("\n".join(evs))

    def _death_step(self, i):
        a = self.rec.alive[:, i]
        idx = np.flatnonzero(~a)
        return idx[0] if len(idx) else 10 ** 9

    def _ammo_at(self, k):
        n0 = self.cfg.defense.n_missiles
        fired = sum(1 for et, msg in self.rec.events
                    if "發射" in msg and et <= self.rec.t[k])
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
                print("[viz] 找不到 ffmpeg，改存 GIF")
                filename = filename.replace(".mp4", ".gif")
            writer = PillowWriter(fps=min(fps, 14))
        print(f"[viz] 輸出動畫 {filename}（{len(self.frames)} 幀）…")
        anim.save(filename, writer=writer)
        print(f"[viz] 完成 -> {filename}")
        if self.ext_fig is None:
            plt.close(self.fig)

    def snapshots(self, outdir, times=None):
        self._build()
        os.makedirs(outdir, exist_ok=True)
        rec = self.rec
        if times is None:
            tt = [rec.t[0], rec.t[len(rec.t) // 3]]
            launch = [et for et, m in rec.events if "發射" in m]
            lead_k = [et for et, m in rec.events if "領機" in m and "擊落" in m]
            if launch:
                tt.append(launch[0] + 1.0)
            if lead_k:
                tt.append(lead_k[0] + 3.0)
            tt += [rec.t[int(len(rec.t) * 0.8)], rec.t[-1]]
            times = sorted(set(min(rec.t[-1], x) for x in tt))
        files = []
        for x in times:
            k = int(np.searchsorted(rec.t, x))
            k = min(k, len(rec.t) - 1)
            fi = min(range(len(self.frames)),
                     key=lambda f: abs(self.frames[f] - k))
            self._missile_hist = {}
            self._cam = None
            for f0 in range(max(0, fi - 8), fi + 1):
                self._update(f0)
            f = os.path.join(outdir, f"snap_t{rec.t[self.frames[fi]]:.0f}s.png")
            self.fig.savefig(f, dpi=110, facecolor=self.fig.get_facecolor())
            files.append(f)
        print(f"[viz] 已輸出 {len(files)} 張截圖 -> {outdir}")
        if self.ext_fig is None:
            plt.close(self.fig)
        return files

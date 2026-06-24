# -*- coding: utf-8 -*-
"""
web 版 3D 戰場視覺化：Recorder → Plotly Figure（含動畫 frames）
================================================================
與桌面版 viz/animate3d.py 對應，但改用 Plotly 在瀏覽器渲染：
  · 原生 3D 互動（旋轉/縮放）
  · play/pause 按鈕 + 進度條 slider
  · 固定視窗範圍（涵蓋整場），視角由使用者自由控制

每幀固定 9 個動態 trace（無資料時放空），確保 plotly frame 對齊：
  0領機 1中繼 2從機 3被擊落 4飛彈 5通訊鏈 6預測線 7AI判定圈 8領機尾跡
靜態 trace（目標/發射器/接戰圈/計畫航線）放在動態之後、不進 frames。
"""
import numpy as np
import plotly.graph_objects as go

from config import ROLE_LEADER, ROLE_RELAY, ROLE_FOLLOWER, ROLE_NAMES

C_LEADER = "#FFB300"
C_RELAY = "#FF6D00"
C_FOLLOW = "#D32F2F"
C_DEAD = "#7d8590"
C_MISSILE = "#00B8D4"
C_COMM = "#42A5F5"
C_PRED = "#00E5FF"
C_TARGET = "#2E7D32"
C_DEFENSE = "#1565C0"
BG = "#0d1117"
N_DYN = 9          # 動態 trace 數
TRAIL = 60         # 領機尾跡長度（步）


def _empty():
    return dict(x=[], y=[], z=[])


def _scatter(coords, **kw):
    return go.Scatter3d(x=coords["x"], y=coords["y"], z=coords["z"], **kw)


def _ammo_series(rec, n0):
    """每步剩餘彈藥（由事件推算）"""
    fired = np.zeros(len(rec.t), dtype=int)
    for et, msg in rec.events:
        if "發射" in msg:
            k = int(np.searchsorted(rec.t, et))
            if k < len(fired):
                fired[k:] += 1
    return np.clip(n0 - fired, 0, None)


def build_figure(rec, cfg, max_frames=120):
    T = len(rec.t)
    if T == 0:
        return go.Figure()
    stride = max(1, T // max_frames)
    fidx = list(range(0, T, stride))
    if fidx[-1] != T - 1:
        fidx.append(T - 1)
    n = rec.pos.shape[1]
    ammo = _ammo_series(rec, cfg.defense.n_missiles)

    # 固定視窗範圍：涵蓋整場所有位置 + 目標
    allp = rec.pos.reshape(-1, 3)
    allp = allp[np.isfinite(allp).all(axis=1)]
    lo = np.minimum(allp.min(axis=0), [-50, -50, 0])
    hi = np.maximum(allp.max(axis=0), [50, 50, 50])
    pad = 80
    xr = [lo[0] - pad, hi[0] + pad]
    yr = [lo[1] - pad, hi[1] + pad]
    zr = [0, hi[2] + pad]

    # ---- 每幀動態 traces
    def dyn_traces(k):
        pos, alive = rec.pos[k], rec.alive[k]
        succ = rec.succeeded[k]
        roles = rec.roles[k]

        def pick(mask):
            p = pos[mask]
            return dict(x=p[:, 0], y=p[:, 1], z=p[:, 2]) if len(p) else _empty()

        t0 = pick(alive & (roles == ROLE_LEADER))
        t1 = pick(alive & (roles == ROLE_RELAY))
        t2 = pick(alive & (roles == ROLE_FOLLOWER))
        t3 = pick(~alive & ~succ)

        # 飛彈
        ms = rec.missiles[k]
        if ms:
            mp = np.array([p for _, p, _ in ms])
            t4 = dict(x=mp[:, 0], y=mp[:, 1], z=mp[:, 2])
        else:
            t4 = _empty()

        # 通訊鏈（用 None 分段）
        cx, cy, cz = [], [], []
        for i, j in rec.comm_edges[k]:
            if alive[i] and alive[j]:
                cx += [pos[i, 0], pos[j, 0], None]
                cy += [pos[i, 1], pos[j, 1], None]
                cz += [pos[i, 2], pos[j, 2], None]
        t5 = dict(x=cx, y=cy, z=cz)

        # 預測線
        px, py, pz = [], [], []
        for _tid, path in rec.pred_paths[k].items():
            pp = path[::3]
            px += list(pp[:, 0]) + [None]
            py += list(pp[:, 1]) + [None]
            pz += list(pp[:, 2]) + [None]
        t6 = dict(x=px, y=py, z=pz)

        # AI 判定領機圈
        bl = rec.believed_leader[k]
        if bl >= 0 and alive[bl] and rec.leader_conf[k] > 0.25:
            t7 = dict(x=[pos[bl, 0]], y=[pos[bl, 1]], z=[pos[bl, 2]])
        else:
            t7 = _empty()

        # 領機尾跡
        lead = np.flatnonzero(alive & (roles == ROLE_LEADER))
        if len(lead):
            li = lead[0]
            k0 = max(0, k - TRAIL)
            seg = rec.pos[k0:k + 1, li]
            m = rec.alive[k0:k + 1, li]
            seg = seg[m]
            t8 = dict(x=seg[:, 0], y=seg[:, 1], z=seg[:, 2]) if len(seg) \
                else _empty()
        else:
            t8 = _empty()
        return [t0, t1, t2, t3, t4, t5, t6, t7, t8]

    styles = [
        dict(mode="markers", marker=dict(size=7, color=C_LEADER,
             symbol="diamond", line=dict(color="white", width=1)), name="領機"),
        dict(mode="markers", marker=dict(size=5, color=C_RELAY,
             symbol="diamond"), name="中繼機"),
        dict(mode="markers", marker=dict(size=3.5, color=C_FOLLOW),
             name="從機"),
        dict(mode="markers", marker=dict(size=3, color=C_DEAD,
             symbol="x"), name="被擊落"),
        dict(mode="markers", marker=dict(size=4, color=C_MISSILE,
             symbol="diamond-open"), name="攔截彈"),
        dict(mode="lines", line=dict(color=C_COMM, width=1.5),
             opacity=0.45, name="通訊鏈"),
        dict(mode="lines", line=dict(color=C_PRED, width=3, dash="dot"),
             name="AI預測軌跡"),
        dict(mode="markers", marker=dict(size=11, color="rgba(0,229,255,0)",
             line=dict(color=C_PRED, width=3)), name="AI判定領機"),
        dict(mode="lines", line=dict(color=C_LEADER, width=2),
             opacity=0.6, name="領機航跡"),
    ]

    def make_traces(k, show_legend):
        dt = dyn_traces(k)
        return [_scatter(dt[i], showlegend=show_legend, **styles[i])
                for i in range(N_DYN)]

    base = make_traces(fidx[0], True)

    # ---- 靜態 traces
    static = [
        go.Scatter3d(x=[0], y=[0], z=[0], mode="markers+text",
                     marker=dict(size=8, color=C_TARGET, symbol="circle",
                                 line=dict(color="white", width=1)),
                     text=["防守目標"], textposition="top center",
                     textfont=dict(color=C_TARGET), name="目標"),
    ]
    # 接戰圈
    th = np.linspace(0, 2 * np.pi, 60)
    R = cfg.defense.engage_range
    static.append(go.Scatter3d(
        x=R * np.cos(th), y=R * np.sin(th), z=np.zeros_like(th),
        mode="lines", line=dict(color=C_DEFENSE, width=2, dash="dash"),
        opacity=0.5, name="接戰半徑"))
    # 計畫航線
    if rec.wp is not None:
        p0 = rec.pos[0, 0]
        path = np.vstack([p0, rec.wp])
        static.append(go.Scatter3d(
            x=path[:, 0], y=path[:, 1], z=path[:, 2], mode="lines+markers",
            line=dict(color=C_TARGET, width=2, dash="dot"),
            marker=dict(size=3, color=C_TARGET), opacity=0.5, name="計畫航線"))

    # ---- frames
    frames = []
    for k in fidx:
        n_alive = int(rec.alive[k].sum())
        n_succ = int(rec.succeeded[k].sum())
        title = (f"T = {rec.t[k]:6.1f}s　存活 {n_alive}　"
                 f"突防 {n_succ}　彈藥 {int(ammo[k])}")
        frames.append(go.Frame(
            data=make_traces(k, True),
            traces=list(range(N_DYN)),
            name=f"{k}",
            layout=go.Layout(title=dict(text=title))))

    # ---- slider & 按鈕
    steps = [dict(method="animate", label=f"{rec.t[k]:.0f}",
                  args=[[f"{k}"], dict(mode="immediate",
                        frame=dict(duration=0, redraw=True),
                        transition=dict(duration=0))]) for k in fidx]
    play = dict(type="buttons", showactive=False, x=0.02, y=0.05,
                xanchor="left", yanchor="bottom",
                bgcolor="#21262d", font=dict(color="white"),
                buttons=[
        dict(label="▶ 播放", method="animate",
             args=[None, dict(frame=dict(duration=45, redraw=True),
                              fromcurrent=True,
                              transition=dict(duration=0))]),
        dict(label="⏸ 暫停", method="animate",
             args=[[None], dict(mode="immediate",
                               frame=dict(duration=0, redraw=False))])])

    fig = go.Figure(data=base + static, frames=frames)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG, plot_bgcolor=BG,
        margin=dict(l=0, r=0, t=36, b=0),
        title=dict(text=f"T = {rec.t[0]:6.1f}s", x=0.5, font=dict(size=14)),
        scene=dict(
            xaxis=dict(title="X (m)", range=xr, backgroundcolor=BG,
                       gridcolor="#30363d"),
            yaxis=dict(title="Y (m)", range=yr, backgroundcolor=BG,
                       gridcolor="#30363d"),
            zaxis=dict(title="高度 (m)", range=zr, backgroundcolor=BG,
                       gridcolor="#30363d"),
            aspectmode="manual",
            aspectratio=dict(x=1, y=1, z=0.35),
            camera=dict(eye=dict(x=1.6, y=1.6, z=0.9))),
        updatemenus=[play],
        sliders=[dict(active=0, x=0.12, y=0.05, len=0.84,
                      xanchor="left", yanchor="bottom",
                      currentvalue=dict(prefix="t = ", suffix=" s",
                                        font=dict(color="white")),
                      steps=steps)],
        legend=dict(x=0.99, y=0.99, xanchor="right",
                    bgcolor="rgba(22,27,34,0.7)"))
    return fig


def figure_json(rec, cfg, max_frames=170):
    import plotly.io as pio
    return pio.to_json(build_figure(rec, cfg, max_frames))

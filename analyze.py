# -*- coding: utf-8 -*-
"""
專題分析圖表產生器 — 對應四大要點
====================================
  fig1_*  要點1：機群陣型與飛行路徑分析
  fig2_*  要點2：領機/中繼機失效處理
  fig3_*  要點3：AI 軌跡預測（卡爾曼 vs LSTM）
  fig4_*  要點4：AI 識別領機/中繼機（規則 vs RF vs MLP）
  fig5_*  總體：防方策略蒙地卡羅對抗實驗

用法：
  python analyze.py            # 全部（蒙地卡羅 10 場景/策略）
  python analyze.py --quick    # 快速版（6 場景/策略）
  python analyze.py --only 1,2 # 只跑指定圖
輸出 -> figures/
"""
import argparse
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config, ROLE_FOLLOWER, ROLE_RELAY, ROLE_LEADER
from core.engine import Simulation
from core.formations import (FORMATIONS, FORMATION_NAMES, make_formation,
                             pick_relay_slots)
from viz import set_chinese_font

FIG_DIR = "figures"
C_L, C_R, C_F = "#FFB300", "#FF6D00", "#D32F2F"
C_KAL, C_LSTM = "#1976D2", "#D32F2F"
SUMMARY = []


def log(msg):
    print(msg)
    SUMMARY.append(msg)


def savefig(fig, name):
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [圖] {path}")


# ================================================================ 要點 1
def fig1_formation_gallery():
    """五種陣型的槽位配置（領機/中繼機/從機）"""
    fig, axes = plt.subplots(1, 5, figsize=(17, 3.6))
    for ax, f in zip(axes, FORMATIONS):
        slots = make_formation(f, 21, 38.0)
        relays = pick_relay_slots(slots, 3)
        for i, s in enumerate(slots):
            if i == 0:
                ax.scatter(s[1], s[0], marker="*", s=300, c=C_L, zorder=3,
                           edgecolors="k", linewidths=0.5)
            elif i in relays:
                ax.scatter(s[1], s[0], marker="D", s=90, c=C_R, zorder=2,
                           edgecolors="k", linewidths=0.4)
            else:
                ax.scatter(s[1], s[0], marker="o", s=40, c=C_F, zorder=1)
        ax.annotate("", xy=(0, 80), xytext=(0, 30),
                    arrowprops=dict(arrowstyle="->", color="gray"))
        ax.set_title(f"{FORMATION_NAMES[f]} ({f})", fontsize=12)
        ax.set_aspect("equal")
        ax.grid(alpha=0.3)
        ax.tick_params(labelsize=7)
    axes[0].scatter([], [], marker="*", s=140, c=C_L, label="領機")
    axes[0].scatter([], [], marker="D", s=60, c=C_R, label="中繼機")
    axes[0].scatter([], [], marker="o", s=30, c=C_F, label="從機")
    axes[0].legend(loc="lower left", fontsize=9)
    fig.suptitle("機群陣型槽位配置（箭頭=飛行方向；中繼機=k-means 子群中心）",
                 fontsize=13)
    savefig(fig, "fig1_陣型總覽.png")


def fig1_path_and_quality():
    """各陣型純編隊飛行：3D 航跡 + 陣型品質時間序列"""
    cfg0 = Config()
    recs = {}
    for f in FORMATIONS:
        cfg = Config()
        cfg.swarm.formation = f
        cfg.sim.seed = 11
        sim = Simulation(cfg, defense_on=False)
        sim.run()
        recs[f] = sim.rec

    # --- 3D 航跡（vee 示範）
    rec = recs["vee"]
    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection="3d")
    roles0 = rec.roles[0]
    for i in range(rec.pos.shape[1]):
        m = rec.alive[:, i]
        p = rec.pos[m, i]
        c = C_L if roles0[i] == ROLE_LEADER else \
            C_R if roles0[i] == ROLE_RELAY else C_F
        lw = 1.8 if roles0[i] == ROLE_LEADER else 0.6
        ax.plot(p[:, 0], p[:, 1], p[:, 2], color=c, lw=lw, alpha=0.75)
    wp = rec.wp
    p0 = rec.pos[0, 0]
    path = np.vstack([p0, wp])
    ax.plot(path[:, 0], path[:, 1], path[:, 2], "g--", lw=1.6, alpha=0.9,
            label="計畫航線")
    ax.scatter(wp[:, 0], wp[:, 1], wp[:, 2], marker="D", c="g", s=50)
    ax.scatter([0], [0], [0], marker="*", s=300, c="g")
    ax.set_xlabel("X (m)"); ax.set_ylabel("Y (m)"); ax.set_zlabel("高度 (m)")
    ax.set_title("V 字陣編隊飛行航跡（金=領機、橙=中繼機、紅=從機）")
    ax.legend()
    ax.set_box_aspect((1, 1, 0.25))
    savefig(fig, "fig1_3D航跡.png")

    # --- 陣型品質曲線
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
    for f in FORMATIONS:
        r = recs[f]
        axes[0].plot(r.t, r.form_err, label=FORMATION_NAMES[f], lw=1.2)
        axes[1].plot(r.t, r.min_spacing, lw=1.2)
        axes[2].plot(r.t, r.conn_ratio * 100, lw=1.2)
    axes[0].set_ylabel("陣型保持誤差 RMS (m)")
    axes[0].legend(ncol=5, fontsize=10)
    axes[0].set_title("各陣型飛行品質比較（含中途航點轉彎）")
    axes[1].set_ylabel("最小機間距 (m)")
    axes[1].axhline(14, color="r", ls=":", alpha=0.6)
    axes[1].annotate("避碰下限", xy=(5, 15), color="r", fontsize=9)
    axes[2].set_ylabel("通訊連線率 (%)")
    axes[2].set_xlabel("時間 (s)")
    for a in axes:
        a.grid(alpha=0.3)
    savefig(fig, "fig1_陣型品質.png")

    for f in FORMATIONS:
        r = recs[f]
        cruise = ~r.succeeded.any(axis=1)   # 終端俯衝逐架突防會污染統計 → 只取巡航段
        e = r.form_err[cruise]
        e = e[~np.isnan(e)]
        log(f"  [要點1] {FORMATION_NAMES[f]:3s}: 巡航陣型誤差 平均 "
            f"{np.mean(e):5.1f} / P95 {np.percentile(e, 95):5.1f} m, "
            f"最小間距 {np.nanmin(r.min_spacing[cruise]):5.1f} m, "
            f"連線率 {np.nanmean(r.conn_ratio[cruise])*100:5.1f}%")


# ================================================================ 要點 2
def fig2_failover():
    """劇本式打擊：領機/中繼機輪番被擊落 → 觀察重組過程"""
    cfg = Config()
    cfg.sim.seed = 11
    kills = [(60.0, "leader"), (95.0, "relay"), (130.0, "leader"),
             (165.0, "relay")]
    sim = Simulation(cfg, defense_on=False, scripted_kills=kills)
    sim.run()
    rec = sim.rec

    # 只畫到首架突防為止（終端俯衝段會污染重組分析）
    succ = rec.succeeded.any(axis=1)
    t_end = rec.t[np.argmax(succ)] if succ.any() else rec.t[-1]

    fig, axes = plt.subplots(2, 1, figsize=(12, 7.5), sharex=True)
    axes[0].plot(rec.t, rec.form_err, color="#333", lw=1.3)
    axes[0].set_ylabel("陣型保持誤差 RMS (m)")
    axes[0].set_title("失效處理：領機/中繼機被擊落 → 偵測 → 選舉/提拔 → 編隊重組")
    axes[1].plot(rec.t, rec.conn_ratio * 100, color="#1976D2", lw=1.3)
    axes[1].set_ylabel("通訊連線率 (%)")
    axes[1].set_xlabel("時間 (s)")
    vis_max = np.nanmax(rec.form_err[:int(t_end / 0.1)])
    axes[0].set_ylim(0, vis_max * 1.18)
    for t0, who in kills:
        for a in axes:
            a.axvline(t0, color="r", ls="--", alpha=0.65)
        axes[0].annotate(f"擊落{'領機' if who == 'leader' else '中繼機'}",
                         xy=(t0, vis_max * 1.05), color="r", fontsize=9,
                         ha="center", xytext=(t0, vis_max * 1.05))
    for et, msg in rec.events:
        if "遞補" in msg:
            axes[0].axvline(et, color="#FF8F00", ls=":", alpha=0.8)
    for a in axes:
        a.grid(alpha=0.3)
        a.set_xlim(0, t_end)

    # 恢復時間統計：誤差回落至 max(尖峰15%, 5 m) 視為重組完成
    rts = []
    for t0, _ in kills:
        k0 = int(t0 / 0.1)
        seg = rec.form_err[k0:int(t_end / 0.1)]
        if not len(seg):
            continue
        peak = np.nanmax(seg[:int(20 / 0.1)])
        thr = max(peak * 0.15, 5.0)
        rec_k = np.flatnonzero(seg[int(3 / 0.1):] < thr)
        if len(rec_k):
            rts.append(rec_k[0] * 0.1 + 3)
    if rts:
        log(f"  [要點2] 四次打擊平均重組恢復時間 {np.mean(rts):.1f} s "
            f"(各次: {', '.join(f'{x:.1f}' for x in rts)} s)")
        axes[0].annotate(f"平均重組恢復時間 約 {np.mean(rts):.1f} s",
                         xy=(0.02, 0.92), xycoords="axes fraction",
                         ha="left", fontsize=11, color="#333",
                         bbox=dict(fc="#FFF8E1", ec="#FFB300"))
    savefig(fig, "fig2_失效重組.png")


# ================================================================ 要點 3
def fig3_predict():
    cfg = Config()
    if not os.path.exists(cfg.ai.lstm_path) or \
            not os.path.exists("data/traj_test.npz"):
        print("  [跳過] 找不到 LSTM 模型或測試資料，請先跑 python train.py")
        return
    from ai.trajectory import kalman_predict_batch, ade_fde, LSTMPredictor
    d = np.load("data/traj_test.npz")
    X, Y = d["X"], d["Y"]
    rng = np.random.default_rng(0)
    sel = rng.choice(len(X), min(3000, len(X)), replace=False)
    X, Y = X[sel], Y[sel]
    H = Y.shape[1]
    kal = kalman_predict_batch(X, H, cfg.sim.dt)
    lstm = LSTMPredictor(cfg.ai.lstm_path, cfg.sim.dt, cfg.swarm.max_speed)
    prd = lstm.predict(X)

    ek = np.linalg.norm(kal - Y, axis=2)    # (B,H)
    el = np.linalg.norm(prd - Y, axis=2)
    a1, f1 = ek.mean(), ek[:, -1].mean()
    a2, f2 = el.mean(), el[:, -1].mean()
    log(f"  [要點3] 卡爾曼CV: ADE={a1:.2f} FDE={f1:.2f} m │ "
        f"LSTM: ADE={a2:.2f} FDE={f2:.2f} m │ "
        f"FDE改善 {100*(1-f2/f1):.1f}%（n={len(X)}, 時域 {H*cfg.sim.dt:.1f}s）")

    fig = plt.figure(figsize=(15, 4.6))
    # (a) ADE/FDE 柱狀
    ax = fig.add_subplot(131)
    xb = np.arange(2)
    ax.bar(xb - 0.18, [a1, f1], 0.36, label="卡爾曼CV（基準）", color=C_KAL)
    ax.bar(xb + 0.18, [a2, f2], 0.36, label="LSTM（AI）", color=C_LSTM)
    for x, v in zip(xb - 0.18, [a1, f1]):
        ax.text(x, v + 0.3, f"{v:.1f}", ha="center", fontsize=10)
    for x, v in zip(xb + 0.18, [a2, f2]):
        ax.text(x, v + 0.3, f"{v:.1f}", ha="center", fontsize=10)
    ax.set_xticks(xb, ["ADE 平均誤差", "FDE 終點誤差"])
    ax.set_ylabel("誤差 (m)")
    ax.set_title(f"預測誤差（{H*cfg.sim.dt:.1f} s 時域）")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    # (b) 逐步誤差
    ax = fig.add_subplot(132)
    ts = (np.arange(H) + 1) * cfg.sim.dt
    ax.plot(ts, ek.mean(0), color=C_KAL, lw=2, label="卡爾曼CV")
    ax.fill_between(ts, np.percentile(ek, 25, 0), np.percentile(ek, 75, 0),
                    color=C_KAL, alpha=0.15)
    ax.plot(ts, el.mean(0), color=C_LSTM, lw=2, label="LSTM")
    ax.fill_between(ts, np.percentile(el, 25, 0), np.percentile(el, 75, 0),
                    color=C_LSTM, alpha=0.15)
    ax.set_xlabel("預測時間 (s)")
    ax.set_ylabel("位置誤差 (m)")
    ax.set_title("誤差 vs 預測時域（實線=平均，帶=IQR）")
    ax.legend()
    ax.grid(alpha=0.3)
    # (c) 機動情境示例（LSTM 優勢最大樣本）
    ax = fig.add_subplot(133)
    gain = ek[:, -1] - el[:, -1]
    b = int(np.argmax(gain))
    ax.plot(X[b, :, 0], X[b, :, 1], "k.-", ms=3, lw=0.8, label="觀測歷史(含噪)")
    ax.plot(Y[b, :, 0], Y[b, :, 1], "g-", lw=2.2, label="真實未來")
    ax.plot(kal[b, :, 0], kal[b, :, 1], "--", color=C_KAL, lw=2,
            label="卡爾曼CV")
    ax.plot(prd[b, :, 0], prd[b, :, 1], "--", color=C_LSTM, lw=2,
            label="LSTM")
    ax.set_title("機動目標預測示例（俯視）")
    ax.set_xlabel("X (m)"); ax.set_ylabel("Y (m)")
    ax.axis("equal")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    savefig(fig, "fig3_軌跡預測.png")


# ================================================================ 要點 4
def fig4_identify():
    cfg = Config()
    if not os.path.exists(cfg.ai.rf_path) or \
            not os.path.exists("data/ident_test.npz"):
        print("  [跳過] 找不到識別模型或測試資料，請先跑 python train.py")
        return
    from ai.identify import (RuleIdentifier, RFIdentifier, MLPIdentifier,
                             extract_features)
    from train import leader_top1
    d = np.load("data/ident_test.npz")
    X, y, grp, form = d["X"], d["y"], d["grp"], d["form"]
    models = [RuleIdentifier(),
              RFIdentifier(cfg.ai.rf_path, cfg.ai.scaler_path),
              MLPIdentifier(cfg.ai.mlp_path, cfg.ai.scaler_path)]
    colors = ["#9E9E9E", "#2E7D32", "#D32F2F"]

    fig = plt.figure(figsize=(15.5, 8.6))
    # (a) 總準確率
    ax = fig.add_subplot(231)
    accs, top1s, scores_all = [], [], []
    for m in models:
        s = m.identify(None, feats=X)
        scores_all.append(s)
        accs.append((s.argmax(1) == y).mean())
        top1s.append(leader_top1(s, y, grp))
    xb = np.arange(3)
    ax.bar(xb - 0.18, accs, 0.36, label="三類角色準確率", color="#1976D2")
    ax.bar(xb + 0.18, top1s, 0.36, label="領機 Top-1 準確率", color="#FFB300")
    for i, (a_, t_) in enumerate(zip(accs, top1s)):
        ax.text(i - 0.18, a_ + 0.012, f"{a_:.2f}", ha="center", fontsize=9)
        ax.text(i + 0.18, t_ + 0.012, f"{t_:.2f}", ha="center", fontsize=9)
    ax.set_xticks(xb, [m.name for m in models])
    ax.set_ylim(0, 1.12)
    ax.set_title("識別準確率（測試集）")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    log("  [要點4] " + " │ ".join(
        f"{m.name}: 三類={a_:.3f} 領機Top1={t_:.3f}"
        for m, a_, t_ in zip(models, accs, top1s)))

    # (b-d) 混淆矩陣
    names = ["從機", "中繼", "領機"]
    for mi, m in enumerate(models):
        ax = fig.add_subplot(2, 3, 2 + mi if mi < 2 else 6)
        pred = scores_all[mi].argmax(1)
        cm = np.zeros((3, 3))
        for a_, b_ in zip(y, pred):
            cm[a_, b_] += 1
        cmn = cm / cm.sum(axis=1, keepdims=True)
        im = ax.imshow(cmn, cmap="Blues", vmin=0, vmax=1)
        for i in range(3):
            for j in range(3):
                ax.text(j, i, f"{cmn[i, j]:.2f}", ha="center", va="center",
                        color="white" if cmn[i, j] > 0.55 else "black",
                        fontsize=10)
        ax.set_xticks(range(3), names)
        ax.set_yticks(range(3), names)
        ax.set_xlabel("AI 判定")
        if mi == 0:
            ax.set_ylabel("真實角色")
        ax.set_title(f"混淆矩陣 — {m.name}")

    # (e) 各陣型領機 Top-1（規則法在環形陣會失效 → ML 價值）
    ax = fig.add_subplot(234)
    width = 0.26
    for mi, m in enumerate(models):
        vals = []
        for fc in range(len(FORMATIONS)):
            sel = form == fc
            vals.append(leader_top1(scores_all[mi][sel], y[sel], grp[sel])
                        if sel.sum() else np.nan)
        ax.bar(np.arange(5) + (mi - 1) * width, vals, width,
               label=m.name, color=colors[mi])
    ax.set_xticks(range(5), [FORMATION_NAMES[f] for f in FORMATIONS])
    ax.set_ylabel("領機 Top-1 準確率")
    ax.set_title("各陣型識別表現（環形陣：領機居中 → 規則法失效）")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)

    # (f) 觀測時間 vs 準確率（新鮮場景、變動視窗長度）
    ax = fig.add_subplot(235)
    from ai.datagen import run_episode
    rng = np.random.default_rng(3)
    windows = [20, 40, 60, 90, 120]
    hits = {m.name: {w: [0, 0] for w in windows} for m in models}
    for ep in range(5):
        rec, ecfg = run_episode(9000 + ep)
        sigma = ecfg.defense.radar_sigma
        T = len(rec.t)
        for k in range(130, T - 5, 60):
            for w in windows:
                aw = rec.alive[k - w:k]
                ids = np.flatnonzero(aw.all(axis=0))
                if len(ids) < 4:
                    continue
                truth = rec.roles[k - 1][ids]
                if (truth == ROLE_LEADER).sum() != 1:
                    continue
                win = rec.pos[k - w:k][:, ids] + \
                    rng.normal(0, sigma, (w, len(ids), 3))
                feats = extract_features(win)
                for m in models:
                    s = m.identify(None, feats=feats)
                    hits[m.name][w][1] += 1
                    if truth[np.argmax(s[:, ROLE_LEADER])] == ROLE_LEADER:
                        hits[m.name][w][0] += 1
    for mi, m in enumerate(models):
        xs = [w * cfg.sim.dt for w in windows]
        ys = [hits[m.name][w][0] / max(hits[m.name][w][1], 1)
              for w in windows]
        ax.plot(xs, ys, "o-", color=colors[mi], label=m.name, lw=2)
    ax.set_xlabel("觀測視窗長度 (s)")
    ax.set_ylabel("領機 Top-1 準確率")
    ax.set_title("需要觀察多久才能鎖定領機？")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    savefig(fig, "fig4_角色識別.png")


# ================================================================ 總體攻防
def fig5_battle_mc(n_scen=10):
    cfg0 = Config()
    have_ml = os.path.exists(cfg0.ai.rf_path)
    from ai.identify import RuleIdentifier
    lstm = None
    if os.path.exists(cfg0.ai.lstm_path):
        from ai.trajectory import LSTMPredictor
        lstm = LSTMPredictor(cfg0.ai.lstm_path, cfg0.sim.dt,
                             cfg0.swarm.max_speed)
    configs = [("random", "隨機目標", None),
               ("nearest", "最近目標", None),
               ("ai", "AI斬首(規則)", "rule")]
    if have_ml:
        from ai.identify import RFIdentifier
        configs.append(("ai", "AI斬首(RF)", "rf"))

    forms = ["vee", "wedge", "grid", "ring", "column"]
    scens = [(900 + i, forms[i % 5]) for i in range(n_scen)]
    results = {}
    reident = []
    for pol, label, ident_kind in configs:
        rows = []
        for seed, f in scens:
            cfg = Config()
            cfg.defense.policy = pol
            cfg.swarm.formation = f
            cfg.sim.seed = seed
            if ident_kind == "rule":
                ident = RuleIdentifier()
            elif ident_kind == "rf":
                from ai.identify import RFIdentifier
                ident = RFIdentifier(cfg.ai.rf_path, cfg.ai.scaler_path)
            else:
                ident = RuleIdentifier() if pol == "ai" else None
            sim = Simulation(cfg, identifier=ident, lstm=lstm)
            r = sim.run()
            rows.append(r)
            if ident_kind == "rf":
                reident += _reident_delays(sim.rec)
            print(f"    {label:10s} {f:6s} seed={seed}: "
                  f"突防 {r['n_through']:2d}, 擊殺 {r['kills']:2d}, "
                  f"{r['end_reason']}")
        results[label] = rows

    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.6))
    labels = [c[1] for c in configs]
    colors = ["#9E9E9E", "#1976D2", "#7B1FA2", "#D32F2F"]
    thr = [[r["n_through"] for r in results[l]] for l in labels]
    stop = [[100.0 * (r["n_through"] == 0) for r in results[l]]
            for l in labels]
    eff = [[100.0 * r["kills"] / max(r["shots"], 1) for r in results[l]]
           for l in labels]
    for ax, data, title, ylab in [
            (axes[0], thr, "攻方平均突防架數（↓防得越好）", "架"),
            (axes[1], stop, "任務攔阻率：0 架突防 (%)", "%"),
            (axes[2], eff, "攔截效率：擊殺/射彈 (%)", "%")]:
        means = [np.mean(x) for x in data]
        sems = [np.std(x) / np.sqrt(len(x)) for x in data]
        ax.bar(range(len(labels)), means, yerr=sems, capsize=4,
               color=colors[:len(labels)])
        for i, v in enumerate(means):
            ax.text(i, v + 0.02 * max(means + [1]), f"{v:.1f}",
                    ha="center", fontsize=10)
        ax.set_xticks(range(len(labels)), labels, fontsize=9)
        ax.set_title(title)
        ax.set_ylabel(ylab)
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle(f"防方策略蒙地卡羅對抗（{n_scen} 場景 × {len(labels)} 策略，"
                 f"同場景同種子配對比較）", fontsize=13)
    fig.tight_layout()
    savefig(fig, "fig5_攻防策略比較.png")

    for l in labels:
        rows = results[l]
        log(f"  [總體] {l:12s} 平均突防 {np.mean([r['n_through'] for r in rows]):4.1f} 架"
            f" │ 攔阻率 {np.mean([r['n_through'] == 0 for r in rows])*100:5.1f}%"
            f" │ 攔截效率 {np.mean([r['kills']/max(r['shots'],1) for r in rows])*100:5.1f}%"
            f" │ 斬首癱瘓 {sum(r['decap'] for r in rows)}/{len(rows)} 場")
    if reident:
        log(f"  [總體] 領機遞補後防方重新識別平均延遲 "
            f"{np.mean(reident):.1f} s（n={len(reident)}）")


def _reident_delays(rec, conf=0.45):
    """領機更替後，防方多久重新鎖定新領機"""
    out = []
    T = len(rec.t)
    cur = -1
    for k in range(T):
        lead = np.flatnonzero(rec.alive[k] & (rec.roles[k] == ROLE_LEADER))
        if len(lead) != 1:
            continue
        L = lead[0]
        if L != cur:
            cur = L
            if k == 0:
                continue
            for k2 in range(k, T):
                if rec.believed_leader[k2] == L and rec.leader_conf[k2] >= conf:
                    out.append(rec.t[k2] - rec.t[k])
                    break
    return out


# ================================================================ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only", default=None, help="例: 1,2,5")
    args = ap.parse_args()
    set_chinese_font()
    only = set(args.only.split(",")) if args.only else None

    def want(x):
        return only is None or x in only

    if want("1"):
        print("[要點1] 陣型與飛行路徑分析…")
        fig1_formation_gallery()
        fig1_path_and_quality()
    if want("2"):
        print("[要點2] 失效處理分析…")
        fig2_failover()
    if want("3"):
        print("[要點3] 軌跡預測評估…")
        fig3_predict()
    if want("4"):
        print("[要點4] 角色識別評估…")
        fig4_identify()
    if want("5"):
        print("[總體] 攻防蒙地卡羅…")
        fig5_battle_mc(6 if args.quick else 10)

    os.makedirs(FIG_DIR, exist_ok=True)
    with open(os.path.join(FIG_DIR, "summary.txt"), "a",
              encoding="utf-8") as f:
        f.write("\n".join(SUMMARY) + "\n")
    print(f"\n[完成] 數據摘要 -> {FIG_DIR}/summary.txt")


if __name__ == "__main__":
    main()

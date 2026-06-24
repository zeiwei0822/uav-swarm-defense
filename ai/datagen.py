# -*- coding: utf-8 -*-
"""
訓練資料生成：大量隨機化攻防模擬 → 軌跡預測資料集 + 角色識別資料集
================================================================
隨機化維度：陣型、機數、中繼機數、航線幾何、速度、雷達噪聲、
防方策略（無/最近/隨機 — 不用 ai 策略避免循環依賴）
→ 資料涵蓋：編隊巡航、轉彎、迴避機動、失效重組、角色遞補
"""
import os
import numpy as np

from config import Config, ROLE_LEADER
from core.engine import Simulation
from ai.trajectory import make_training_windows
from ai.identify import extract_features
from core.formations import FORMATIONS

FORM_CODE = {f: i for i, f in enumerate(FORMATIONS)}


def random_config(rng) -> Config:
    cfg = Config()
    cfg.swarm.formation = FORMATIONS[rng.integers(len(FORMATIONS))]
    cfg.swarm.n_drones = int(rng.integers(15, 31))
    cfg.swarm.n_relays = int(rng.integers(2, 5))
    cfg.swarm.cruise_speed = float(rng.uniform(15.0, 21.0))
    cfg.swarm.spacing = float(rng.uniform(32.0, 46.0))
    cfg.swarm.spawn_distance = float(rng.uniform(2600.0, 3400.0))
    cfg.swarm.n_waypoints = int(rng.integers(1, 4))
    cfg.swarm.waypoint_lateral = float(rng.uniform(400.0, 900.0))
    # 多軸夾擊：訓練涵蓋 1~3 股與不同車道寬，讓識別器對單軸/多軸都穩健
    cfg.swarm.n_axes = int(rng.integers(1, 4))
    cfg.swarm.axis_spread = float(rng.uniform(120.0, 220.0))
    cfg.swarm.fixed_bearing = None   # 訓練資料用隨機方位（多樣化，避免過擬合單一方向）
    cfg.defense.policy = ["nearest", "random"][rng.integers(2)]
    cfg.defense.radar_sigma = float(rng.uniform(4.0, 10.0))
    return cfg


def run_episode(seed: int):
    """跑一場隨機場景，回傳 (recorder, cfg)"""
    rng = np.random.default_rng(seed)
    cfg = random_config(rng)
    cfg.sim.seed = seed
    defense_on = rng.random() > 0.3        # 30% 純編隊飛行（乾淨資料）
    sim = Simulation(cfg, identifier=None, lstm=None, defense_on=defense_on)
    sim.run(verbose=False)
    return sim.rec, cfg


def harvest_identification(rec, cfg, rng, window=60, every_s=4.0,
                           t_warmup=8.0):
    """從一場紀錄抽取識別樣本：(特徵, 角色標籤, 群組id, 陣型code)"""
    dt = cfg.sim.dt
    sigma = cfg.defense.radar_sigma
    T = len(rec.t)
    step = int(every_s / dt)
    k0 = max(window, int(t_warmup / dt))
    Xs, ys, grps, forms = [], [], [], []
    gid_base = rng.integers(1 << 30)
    for g, k in enumerate(range(k0, T, step)):
        alive_win = rec.alive[k - window:k]          # (W,N)
        ok = alive_win.all(axis=0)
        ids = np.flatnonzero(ok)
        if len(ids) < 4:
            continue
        win = rec.pos[k - window:k][:, ids] \
            + rng.normal(0, sigma, (window, len(ids), 3))
        feats = extract_features(win)
        labels = rec.roles[k - 1][ids]
        Xs.append(feats)
        ys.append(labels)
        grps.append(np.full(len(ids), gid_base + g))
        forms.append(np.full(len(ids), FORM_CODE[cfg.swarm.formation]))
    if not Xs:
        return None
    return (np.concatenate(Xs), np.concatenate(ys),
            np.concatenate(grps), np.concatenate(forms))


def generate(n_episodes=40, out_dir="data", seed0=1000, test_frac=0.15,
             hist_len=20, horizon=25, max_traj_per_ep=1500, verbose=True):
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(7)
    n_test = max(2, int(n_episodes * test_frac))
    buckets = {"train": {"tx": [], "ty": [], "ix": [], "iy": [], "ig": [],
                         "if": []},
               "test": {"tx": [], "ty": [], "ix": [], "iy": [], "ig": [],
                        "if": []}}

    for ep in range(n_episodes):
        which = "test" if ep >= n_episodes - n_test else "train"
        rec, cfg = run_episode(seed0 + ep)
        # --- 軌跡預測資料
        X, Y = make_training_windows(rec.pos, rec.alive, hist_len, horizon,
                                     stride=5, rng=rng)
        if len(X) > max_traj_per_ep:
            sel = rng.choice(len(X), max_traj_per_ep, replace=False)
            X, Y = X[sel], Y[sel]
        buckets[which]["tx"].append(X)
        buckets[which]["ty"].append(Y)
        # --- 識別資料
        h = harvest_identification(rec, cfg, rng)
        if h is not None:
            buckets[which]["ix"].append(h[0])
            buckets[which]["iy"].append(h[1])
            buckets[which]["ig"].append(h[2])
            buckets[which]["if"].append(h[3])
        if verbose:
            print(f"  episode {ep+1:3d}/{n_episodes} [{which:5s}] "
                  f"{cfg.swarm.formation:6s} n={cfg.swarm.n_drones:2d} "
                  f"traj+{len(X):4d}  ident+{0 if h is None else len(h[0]):4d}")

    for which in ("train", "test"):
        b = buckets[which]
        np.savez_compressed(
            os.path.join(out_dir, f"traj_{which}.npz"),
            X=np.concatenate(b["tx"]), Y=np.concatenate(b["ty"]))
        np.savez_compressed(
            os.path.join(out_dir, f"ident_{which}.npz"),
            X=np.concatenate(b["ix"]), y=np.concatenate(b["iy"]),
            grp=np.concatenate(b["ig"]), form=np.concatenate(b["if"]))
        if verbose:
            nt = sum(len(x) for x in b["tx"])
            ni = sum(len(x) for x in b["ix"])
            print(f"[datagen] {which}: 軌跡視窗 {nt}、識別樣本 {ni} -> {out_dir}/")

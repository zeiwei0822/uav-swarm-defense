# -*- coding: utf-8 -*-
"""
AI 模型訓練入口
================
  python train.py                    # 生成資料(40場) + 訓練全部模型 + 測試集評估
  python train.py --episodes 60      # 更多資料
  python train.py --skip-datagen     # 重用既有 data/*.npz
"""
import argparse
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config, ROLE_LEADER
from ai import datagen
from ai.trajectory import (train_lstm, train_mlp_traj, train_transformer_traj,
                           kalman_predict_batch, ade_fde,
                           LSTMPredictor, MLPTrajPredictor, TransformerPredictor)
from ai.identify import (train_rf, train_gbm, train_mlp, RuleIdentifier,
                         RFIdentifier, GBMIdentifier, MLPIdentifier)
from ai.gnn import train_gnn, GNNIdentifier, NODE_FEAT_IDX


def leader_top1(scores, y, grp):
    """每個視窗（同 grp）內：p_leader 最高者 == 真領機？"""
    ok, tot = 0, 0
    for g in np.unique(grp):
        m = grp == g
        if (y[m] == ROLE_LEADER).sum() != 1:
            continue
        tot += 1
        if y[m][np.argmax(scores[m][:, ROLE_LEADER])] == ROLE_LEADER:
            ok += 1
    return ok / max(tot, 1)


def evaluate(cfg, verbose=True):
    print("\n========== 測試集評估 ==========")
    # ---- 軌跡預測：Kalman / MLP / Transformer / LSTM 四方對比
    d = np.load("data/traj_test.npz")
    X, Y = d["X"], d["Y"]
    sel = np.random.default_rng(0).choice(len(X), min(2500, len(X)), replace=False)
    X, Y = X[sel], Y[sel]
    print(f"  軌跡預測（{Y.shape[1]*cfg.sim.dt:.1f}s 預測時域, n={len(X)}）")
    results_traj = []

    kal = kalman_predict_batch(X, Y.shape[1], cfg.sim.dt)
    a, f = ade_fde(kal, Y)
    results_traj.append(("卡爾曼CV（基準）", a, f))
    print(f"    卡爾曼CV（基準）  ADE={a:6.2f} m   FDE={f:6.2f} m")

    for name, cls, path in [
            ("MLP",         MLPTrajPredictor,     cfg.ai.mlp_traj_path),
            ("Transformer", TransformerPredictor,  cfg.ai.transformer_path),
            ("LSTM",        LSTMPredictor,         cfg.ai.lstm_path)]:
        try:
            pred = cls(path, cfg.sim.dt, cfg.swarm.max_speed).predict(X)
            a, f = ade_fde(pred, Y)
            imp_a = 100 * (1 - a / results_traj[0][1])
            imp_f = 100 * (1 - f / results_traj[0][2])
            results_traj.append((name, a, f))
            print(f"    {name:12s}  ADE={a:6.2f} m   FDE={f:6.2f} m"
                  f"   （vs Kalman: ADE改善{imp_a:+.1f}% FDE改善{imp_f:+.1f}%）")
        except FileNotFoundError:
            print(f"    {name:12s}  (未找到模型，跳過)")

    # ---- 識別：規則 vs RF vs MLP
    d = np.load("data/ident_test.npz")
    Xi, yi, gi = d["X"], d["y"], d["grp"]
    models = [RuleIdentifier(),
              RFIdentifier(cfg.ai.rf_path, cfg.ai.scaler_path),
              GBMIdentifier(cfg.ai.gbm_path, cfg.ai.scaler_path),
              MLPIdentifier(cfg.ai.mlp_path, cfg.ai.scaler_path)]
    print(f"  角色識別（n={len(Xi)} 樣本 / {len(np.unique(gi))} 視窗）")
    for m in models:
        s = m.identify(None, feats=Xi)
        acc = (s.argmax(1) == yi).mean()
        top1 = leader_top1(s, yi, gi)
        print(f"    {m.name:12s} 三類準確率={acc:.3f}   領機Top-1={top1:.3f}")

    # ---- GNN vs 規則/RF：同一批『圖』的領機 Top-1（圖結構學習公平對比）
    try:
        graphs_te = list(np.load("data/graphs_test.npz",
                                 allow_pickle=True)["graphs"])
    except FileNotFoundError:
        print("  (無 graphs_test.npz，跳過 GNN 評估)")
        return
    gnn = GNNIdentifier(cfg.ai.gnn_path)
    rf = RFIdentifier(cfg.ai.rf_path, cfg.ai.scaler_path)
    rule = RuleIdentifier()
    res = {"規則法": [0, 0], "RandomForest": [0, 0], "GNN(圖)": [0, 0]}
    for feats, adj, labels in graphs_te:
        if (labels == ROLE_LEADER).sum() != 1:
            continue
        for name, sc in [
                ("規則法", rule.identify(None, feats=feats)),
                ("RandomForest", rf.identify(None, feats=feats)),
                ("GNN(圖)", gnn.score_graph(feats[:, NODE_FEAT_IDX], adj))]:
            ok = labels[sc[:, ROLE_LEADER].argmax()] == ROLE_LEADER
            res[name][0] += int(ok)
            res[name][1] += 1
    print(f"  ── 圖測試集 領機Top-1（{res['GNN(圖)'][1]} 張單領機圖，同圖比較）")
    for name in ("規則法", "RandomForest", "GNN(圖)"):
        ok, tot = res[name]
        print(f"    {name:12s} 領機Top-1={ok / max(tot, 1):.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=40)
    ap.add_argument("--skip-datagen", action="store_true")
    ap.add_argument("--skip-train", action="store_true")
    args = ap.parse_args()

    cfg = Config()
    if not args.skip_datagen:
        print(f"[1/3] 生成訓練資料（{args.episodes} 場隨機模擬）…")
        datagen.generate(args.episodes, hist_len=cfg.ai.hist_len,
                         horizon=cfg.ai.pred_horizon)
    if not args.skip_train:
        print("[2/3] 訓練模型…")
        d = np.load("data/traj_train.npz")
        print(f"  軌跡預測（{len(d['X'])} 視窗）— 訓練 MLP / Transformer / LSTM")
        train_mlp_traj(d["X"], d["Y"], cfg.sim.dt, cfg.swarm.max_speed,
                       cfg.ai.mlp_traj_path)
        train_transformer_traj(d["X"], d["Y"], cfg.sim.dt, cfg.swarm.max_speed,
                               cfg.ai.transformer_path)
        train_lstm(d["X"], d["Y"], cfg.sim.dt, cfg.swarm.max_speed,
                   cfg.ai.lstm_hidden, cfg.ai.lstm_layers, cfg.ai.lstm_path)
        d = np.load("data/ident_train.npz")
        print(f"  角色識別器（{len(d['X'])} 樣本）")
        train_rf(d["X"], d["y"], cfg.ai.rf_path, cfg.ai.scaler_path)
        train_gbm(d["X"], d["y"], cfg.ai.gbm_path, cfg.ai.scaler_path)
        train_mlp(d["X"], d["y"], cfg.ai.mlp_path, cfg.ai.scaler_path)
        graphs_tr = list(np.load("data/graphs_train.npz",
                                 allow_pickle=True)["graphs"])
        print(f"  GNN 圖識別器（{len(graphs_tr)} 張圖）")
        train_gnn(graphs_tr, cfg.ai.gnn_path)
    print("[3/3] 評估…")
    evaluate(cfg)


if __name__ == "__main__":
    main()

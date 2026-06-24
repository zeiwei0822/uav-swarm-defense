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
from ai.trajectory import train_lstm, kalman_predict_batch, ade_fde, LSTMPredictor
from ai.identify import (train_rf, train_mlp, RuleIdentifier, RFIdentifier,
                         MLPIdentifier)


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
    # ---- 軌跡預測：Kalman vs LSTM
    d = np.load("data/traj_test.npz")
    X, Y = d["X"], d["Y"]
    sel = np.random.default_rng(0).choice(len(X), min(2500, len(X)),
                                          replace=False)
    X, Y = X[sel], Y[sel]
    kal = kalman_predict_batch(X, Y.shape[1], cfg.sim.dt)
    a1, f1 = ade_fde(kal, Y)
    lstm = LSTMPredictor(cfg.ai.lstm_path, cfg.sim.dt, cfg.swarm.max_speed)
    pred = lstm.predict(X)
    a2, f2 = ade_fde(pred, Y)
    print(f"  軌跡預測（{Y.shape[1]*cfg.sim.dt:.1f}s 預測時域, n={len(X)}）")
    print(f"    卡爾曼CV  ADE={a1:6.2f} m   FDE={f1:6.2f} m")
    print(f"    LSTM      ADE={a2:6.2f} m   FDE={f2:6.2f} m"
          f"   （改善 {100*(1-a2/a1):.1f}% / {100*(1-f2/f1):.1f}%）")

    # ---- 識別：規則 vs RF vs MLP
    d = np.load("data/ident_test.npz")
    Xi, yi, gi = d["X"], d["y"], d["grp"]
    models = [RuleIdentifier(),
              RFIdentifier(cfg.ai.rf_path, cfg.ai.scaler_path),
              MLPIdentifier(cfg.ai.mlp_path, cfg.ai.scaler_path)]
    print(f"  角色識別（n={len(Xi)} 樣本 / {len(np.unique(gi))} 視窗）")
    for m in models:
        s = m.identify(None, feats=Xi)
        acc = (s.argmax(1) == yi).mean()
        top1 = leader_top1(s, yi, gi)
        print(f"    {m.name:12s} 三類準確率={acc:.3f}   領機Top-1={top1:.3f}")


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
        print(f"  LSTM 軌跡預測（{len(d['X'])} 視窗）")
        train_lstm(d["X"], d["Y"], cfg.sim.dt, cfg.swarm.max_speed,
                   cfg.ai.lstm_hidden, cfg.ai.lstm_layers, cfg.ai.lstm_path)
        d = np.load("data/ident_train.npz")
        print(f"  角色識別器（{len(d['X'])} 樣本）")
        train_rf(d["X"], d["y"], cfg.ai.rf_path, cfg.ai.scaler_path)
        train_mlp(d["X"], d["y"], cfg.ai.mlp_path, cfg.ai.scaler_path)
    print("[3/3] 評估…")
    evaluate(cfg)


if __name__ == "__main__":
    main()

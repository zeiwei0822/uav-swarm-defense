# -*- coding: utf-8 -*-
"""
主程式：跑一場無人機機群 vs 防空系統的攻防戰
================================================
用法範例：
  python run_sim.py                          # 預設: AI策略 + 3D動畫
  python run_sim.py --policy nearest         # 防方改用最近目標策略
  python run_sim.py --formation ring --n 24  # 環形陣 24 架
  python run_sim.py --no-anim                # 只跑模擬印戰報（最快）
  python run_sim.py --save battle.mp4        # 動畫存檔（mp4 或 gif）
  python run_sim.py --no-defense             # 純編隊飛行展示
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from core.engine import Simulation


def load_ai(cfg, prefer="auto", quiet=False):
    """載入訓練好的 AI 模型；沒有就用基準法（規則識別 + 卡爾曼預測）"""
    from ai.identify import RuleIdentifier
    identifier, lstm = RuleIdentifier(), None
    if prefer == "rule":
        return identifier, lstm
    if os.path.exists(cfg.ai.rf_path) and os.path.exists(cfg.ai.scaler_path) \
            and prefer in ("auto", "rf"):
        from ai.identify import RFIdentifier
        identifier = RFIdentifier(cfg.ai.rf_path, cfg.ai.scaler_path)
    if os.path.exists(cfg.ai.mlp_path) and os.path.exists(cfg.ai.scaler_path) \
            and prefer == "mlp":
        from ai.identify import MLPIdentifier
        identifier = MLPIdentifier(cfg.ai.mlp_path, cfg.ai.scaler_path)
    if os.path.exists(cfg.ai.lstm_path):
        from ai.trajectory import LSTMPredictor
        lstm = LSTMPredictor(cfg.ai.lstm_path, cfg.sim.dt,
                             cfg.swarm.max_speed)
    if not quiet:
        print(f"[AI] 識別器: {identifier.name}   "
              f"軌跡預測: {'LSTM' if lstm else '卡爾曼濾波(基準)'}")
    return identifier, lstm


def main():
    ap = argparse.ArgumentParser(description="無人機機群攻防模擬")
    ap.add_argument("--policy", default="ai",
                    choices=["ai", "nearest", "random"], help="防方火控策略")
    ap.add_argument("--formation", default="vee",
                    choices=["vee", "wedge", "column", "grid", "ring"])
    ap.add_argument("--n", type=int, default=21, help="機群數量 (15~30)")
    ap.add_argument("--relays", type=int, default=3, help="中繼機數量")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--identifier", default="auto",
                    choices=["auto", "rule", "rf", "mlp"], help="識別器選擇")
    ap.add_argument("--no-anim", action="store_true", help="不播動畫")
    ap.add_argument("--no-lstm", action="store_true",
                    help="不用 LSTM，改用卡爾曼基準（傳統防空）")
    ap.add_argument("--no-defense", action="store_true", help="關閉防空（純編隊）")
    ap.add_argument("--save", default=None, metavar="FILE",
                    help="動畫存檔 (.mp4/.gif)")
    ap.add_argument("--snapshot", default=None, metavar="DIR",
                    help="輸出數張關鍵時刻截圖到資料夾")
    args = ap.parse_args()

    cfg = Config()
    cfg.defense.policy = args.policy
    cfg.swarm.formation = args.formation
    cfg.swarm.n_drones = args.n
    cfg.swarm.n_relays = args.relays
    cfg.sim.seed = args.seed

    identifier, lstm = (None, None) if args.no_defense \
        else load_ai(cfg, args.identifier)
    if args.no_lstm:
        lstm = None        # 傳統防空：卡爾曼基準

    print(f"[SIM] 開始模擬：{args.formation} 陣型 {args.n} 架 "
          f"vs 防方'{args.policy}'策略  (seed={args.seed})")
    sim = Simulation(cfg, identifier=identifier, lstm=lstm,
                     defense_on=not args.no_defense)
    sim.run(verbose=True)

    if args.no_anim and not args.save and not args.snapshot:
        return

    from viz.tactical2d import Tactical2D
    anim = Tactical2D(sim.rec, cfg)
    if args.snapshot:
        anim.snapshots(args.snapshot)
    if args.save:
        anim.save(args.save)
    if not args.no_anim and not args.save and not args.snapshot:
        anim.show()


if __name__ == "__main__":
    main()

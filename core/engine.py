# -*- coding: utf-8 -*-
"""
攻防模擬引擎：機群 vs 防空系統 的主循環 + 全程資料記錄
"""
import numpy as np

from config import Config, ROLE_LEADER, ROLE_RELAY
from core.swarm import Swarm
from core.defense import Defense
from core.formations import slot_world_positions, formation_error, spacing_stats


class Recorder:
    """逐步記錄完整狀態，供 3D 動畫與分析使用"""

    def __init__(self, n):
        self.n = n
        self.t = []
        self.pos = []          # (N,3)
        self.alive = []        # (N,)
        self.succeeded = []    # (N,) 已突防
        self.roles = []        # (N,)
        self.connected = []    # (N,)
        self.comm_edges = []   # list[(i,j)]
        self.ident_probs = []  # (N,3)
        self.believed_leader = []
        self.leader_conf = []
        self.missiles = []     # list[(pos(3,), target_id)]
        self.pred_paths = []   # dict{tid: (H,3)}
        self.form_err = []     # 陣型保持誤差
        self.min_spacing = []
        self.conn_ratio = []   # 連線比例
        self.coord_C = []      # ★協調係數（領機角色機制）
        self.warn_active = []  # ★全網預警是否生效
        self.wp = None         # 任務航線
        self.events = []       # (t, 文字)

    def snap(self, t, swarm: Swarm, defense):
        self.t.append(t)
        # 誘餌遮罩（靜態，記一次即可；供視覺化標示與「AI誤判誘餌」旁白）
        self.is_decoy = np.array([getattr(d, "is_decoy", False)
                                  for d in swarm.drones])
        self.pos.append(swarm.positions().copy())
        self.alive.append(swarm.alive_mask().copy())
        self.succeeded.append(np.array([d.succeeded for d in swarm.drones]))
        self.roles.append(swarm.roles().copy())
        self.connected.append(np.array([d.connected and d.alive
                                        for d in swarm.drones]))
        self.comm_edges.append(list(getattr(swarm, "comm_edges", [])))
        self.coord_C.append(float(getattr(swarm, "coord_C", 1.0)))
        self.warn_active.append(bool(getattr(swarm, "warn_active", True)))

        # 陣型品質（要點1 指標）
        leader = swarm.get_leader()
        alive = swarm.alive_drones()
        if leader is not None and len(alive) > 1:
            sw = slot_world_positions(leader.pos, swarm.form_heading,
                                      swarm.slots)
            dp, tp = [], []
            for d in alive:
                si = swarm.assignment.get(d.id)
                if si is not None and si < len(sw):
                    dp.append(d.pos)
                    tp.append(sw[si])
            self.form_err.append(formation_error(np.array(dp), np.array(tp))
                                 if dp else np.nan)
        else:
            self.form_err.append(np.nan)
        if len(alive) > 1:
            mn, _ = spacing_stats(np.array([d.pos for d in alive]))
            self.min_spacing.append(mn)
            self.conn_ratio.append(np.mean([d.connected for d in alive]))
        else:
            self.min_spacing.append(np.nan)
            self.conn_ratio.append(np.nan)

        if defense is not None:
            self.ident_probs.append(defense.ident_probs.copy())
            self.believed_leader.append(defense.believed_leader)
            self.leader_conf.append(defense.leader_conf)
            self.missiles.append([(m.id, m.pos.copy(), m.target_id)
                                  for m in defense.missiles])
            self.pred_paths.append({k: v.copy()
                                    for k, v in defense.pred_paths.items()})
        else:
            self.ident_probs.append(np.zeros((self.n, 3)))
            self.believed_leader.append(-1)
            self.leader_conf.append(0.0)
            self.missiles.append([])
            self.pred_paths.append({})

    def finalize(self):
        self.t = np.array(self.t)
        self.pos = np.array(self.pos)            # (T,N,3)
        self.alive = np.array(self.alive)        # (T,N)
        self.succeeded = np.array(self.succeeded)
        self.roles = np.array(self.roles)
        self.connected = np.array(self.connected)
        self.ident_probs = np.array(self.ident_probs)
        self.believed_leader = np.array(self.believed_leader)
        self.leader_conf = np.array(self.leader_conf)
        self.form_err = np.array(self.form_err)
        self.min_spacing = np.array(self.min_spacing)
        self.conn_ratio = np.array(self.conn_ratio)
        self.coord_C = np.array(self.coord_C)
        self.warn_active = np.array(self.warn_active)
        return self


class Simulation:
    """一場完整攻防戰。defense_on=False 可跑純編隊飛行（分析/資料生成用）"""

    def __init__(self, cfg: Config, identifier=None, lstm=None,
                 defense_on=True, scripted_kills=None, seed=None):
        self.cfg = cfg
        seed = cfg.sim.seed if seed is None else seed
        self.rng = np.random.default_rng(seed)
        self.swarm = Swarm(cfg.swarm, target_pos=np.zeros(3), rng=self.rng,
                           dt=cfg.sim.dt)
        self.defense = None
        if defense_on:
            self.defense = Defense(cfg.defense, cfg.ai, cfg.swarm.n_drones,
                                   site=np.zeros(3), dt=cfg.sim.dt,
                                   rng=self.rng, identifier=identifier,
                                   lstm_predictor=lstm)
        # scripted_kills: [(時刻, "leader"/"relay"/機編號)] 無防空時的劇本式打擊
        self.scripted = sorted(scripted_kills or [], key=lambda x: x[0])
        self.rec = Recorder(cfg.swarm.n_drones)
        self.rec.wp = None

    def _apply_scripted(self, t):
        while self.scripted and self.scripted[0][0] <= t:
            _, who = self.scripted.pop(0)
            if who == "leader":
                ld = self.swarm.get_leader()
                tid = ld.id if ld else None
            elif who == "relay":
                rs = [d for d in self.swarm.alive_drones()
                      if d.role == ROLE_RELAY]
                tid = rs[0].id if rs else None
            else:
                tid = int(who)
            if tid is not None and self.swarm.drones[tid].alive:
                self.swarm.kill(tid, t)

    def run(self, verbose=False, progress_cb=None):
        cfg = self.cfg
        dt = cfg.sim.dt
        n_steps = int(cfg.sim.t_max / dt)
        self.rec.wp = self.swarm.waypoints.copy()
        end_reason = "時間到"

        for k in range(n_steps):
            t = k * dt
            if progress_cb is not None and k % 15 == 0:
                progress_cb(k / n_steps)      # 回報模擬進度（GUI 進度條用）
            self._apply_scripted(t)
            missiles = self.defense.missiles if self.defense else []
            self.swarm.step(t, missiles)
            if self.defense:
                self.defense.step(t, self.swarm)
            self.rec.snap(t, self.swarm, self.defense)

            alive = self.swarm.alive_mask().sum()
            if alive == 0:
                end_reason = ("攻方全數突防" if self.swarm.n_through > 0
                              and self.swarm.n_through == cfg.swarm.n_drones
                              else "機群全滅")
                break
            if self.swarm.lost_mode and self.defense and \
                    (self.defense.ammo <= 0 or
                     t - max((e[0] for e in self.swarm.events), default=0) > 45):
                end_reason = "機群迷失（任務癱瘓）"
                break

        # 彙整事件
        ev = list(self.swarm.events)
        if self.defense:
            ev += self.defense.events
        ev.sort(key=lambda x: x[0])
        self.rec.events = ev

        result = {
            "end_reason": end_reason,
            "t_end": float(self.rec.t[-1]) if len(self.rec.t) else 0.0,
            "n_through": self.swarm.n_through,
            "n_killed": int((~self.swarm.alive_mask()).sum()
                            - self.swarm.n_through),
            "n_alive": int(self.swarm.alive_mask().sum()),
            "lost_mode": self.swarm.lost_mode,
            "decap": bool(self.swarm.lost_mode and
                          getattr(self.swarm, "lost_at_dist", 0) > 300.0),
            "shots": self.defense.shots_fired if self.defense else 0,
            "kills": self.defense.kills if self.defense else 0,
            "ammo_left": self.defense.ammo if self.defense else 0,
            "policy": cfg.defense.policy if self.defense else "無防空",
        }
        if verbose:
            self._print_report(result)
        self.rec.finalize()
        return result

    def report_text(self, r) -> str:
        cfg = self.cfg
        L = ["=" * 62, "  ⚔️  攻防戰報", "=" * 62,
             f"  陣型: {cfg.swarm.formation:8s}  機群: {cfg.swarm.n_drones} 架"
             f"（中繼機 {cfg.swarm.n_relays}）  防方策略: {r['policy']}",
             "-" * 62]
        L += [f"  [{t:7.1f}s] {msg}" for t, msg in self.rec.events]
        L += ["-" * 62,
              f"  結束原因: {r['end_reason']}（{r['t_end']:.1f}s）",
              f"  攻方突防: {r['n_through']} 架   被擊落: {r['n_killed']} 架"
              f"   存活未突防: {r['n_alive']} 架"]
        if self.defense:
            eff = r['kills'] / r['shots'] if r['shots'] else 0
            L += [f"  防方射彈: {r['shots']} 發   擊殺: {r['kills']} 架"
                  f"   剩餘彈藥: {r['ammo_left']}",
                  f"  攔截效率: {eff:.1%}"]
        L.append("=" * 62)
        return "\n".join(L)

    def _print_report(self, r):
        print("\n" + self.report_text(r))

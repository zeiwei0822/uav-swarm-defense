# -*- coding: utf-8 -*-
"""
防方（藍隊）：雷達觀測 → AI 識別關鍵節點 → 軌跡預測 → 火控攔截
================================================================
攻防閉環：
  雷達（含噪聲）→ 識別器每秒推斷各機角色（要點4）→ 火控依策略選目標
  → 攔截彈以「預測攔截點」導引（要點3 的軌跡預測直接用於武器導引）
  → 擊落領機/中繼機 → 攻方觸發失效重組（要點2）→ 防方須重新識別

三種火控策略（蒙地卡羅比較用）：
  ai      : 優先打識別出的領機 → 中繼機 → 最近目標（斬首戰術）
  nearest : 永遠打最近的（傳統點防禦）
  random  : 隨機選目標（對照組）
"""
import numpy as np

from config import (DefenseConfig, AIConfig,
                    ROLE_FOLLOWER, ROLE_RELAY, ROLE_LEADER)
from ai.trajectory import KalmanCV
from ai.identify import extract_features


class Missile:
    _next_id = 0

    def __init__(self, pos, vel, target_id, launch_t):
        self.id = Missile._next_id
        Missile._next_id += 1
        self.pos = np.asarray(pos, float).copy()
        self.vel = np.asarray(vel, float).copy()
        self.target_id = target_id
        self.launch_t = launch_t
        self.alive = True


class Radar:
    """對所有存活且在涵蓋範圍內的目標，每步產生含噪聲量測 + 卡爾曼追蹤"""

    def __init__(self, n_drones, sigma, rng, dt, site):
        self.sigma = sigma
        self.rng = rng
        self.site = site
        self.meas = [[] for _ in range(n_drones)]   # 每機量測歷史 (list of (3,))
        self.tracks = [KalmanCV(dt, sigma_meas=sigma) for _ in range(n_drones)]
        self.visible = np.zeros(n_drones, bool)

    def update(self, swarm, radar_range):
        for d in swarm.drones:
            if not d.alive:
                self.visible[d.id] = False
                continue
            if np.linalg.norm(d.pos - self.site) > radar_range:
                self.visible[d.id] = False
                continue
            z = d.pos + self.rng.normal(0, self.sigma, 3)
            self.meas[d.id].append(z)
            self.tracks[d.id].update(z)
            self.visible[d.id] = True

    def history(self, drone_id, length):
        h = self.meas[drone_id]
        if len(h) < length:
            return None
        return np.array(h[-length:])


class Defense:
    def __init__(self, cfg: DefenseConfig, ai_cfg: AIConfig, n_drones: int,
                 site, dt: float, rng, identifier, lstm_predictor=None):
        self.cfg = cfg
        self.ai_cfg = ai_cfg
        self.dt = dt
        self.rng = rng
        self.site = np.asarray(site, float)
        self.radar = Radar(n_drones, cfg.radar_sigma, rng, dt, self.site)
        self.identifier = identifier          # 規則 / RF / MLP（統一介面）
        self.lstm = lstm_predictor            # None → 用卡爾曼外推
        self.events = []

        self.launch_ready = [0.0] * cfg.n_launchers
        self.ammo = cfg.n_missiles
        self.missiles = []

        # 識別狀態（EMA 平滑）
        self.n = n_drones
        self.ident_probs = np.zeros((n_drones, 3))
        self.ident_probs[:, ROLE_FOLLOWER] = 1.0
        self.believed_leader = -1
        self.leader_conf = 0.0
        self.next_ident_t = ai_cfg.feat_window * dt   # 蒐集滿視窗才開始識別
        self.pred_paths = {}                  # target_id -> (H,3) 最新預測軌跡
        self.shots_fired = 0
        self.kills = 0
        # ★ SIGINT 解碼進度（0~1）：在雷達範圍累積，領機(流量大)解碼最快，滿才能鎖定
        self.decode = np.zeros(n_drones)
        # ★ SEAD 壓制：反輻射機進近距→火力被壓制(撕開破口)，期間無法發射
        self.suppress_until = -1e9
        self.suppressed = False

    # ------------------------------------------------------------ 識別（要點4）
    def _run_identification(self, t, swarm):
        W = self.ai_cfg.feat_window
        ids = [d.id for d in swarm.drones
               if d.alive and self.radar.history(d.id, W) is not None]
        if len(ids) < 3:
            return
        win = np.stack([self.radar.history(i, W) for i in ids], axis=1)  # (W,k,3)
        feats = extract_features(win, self.ai_cfg.max_lag)
        scores = self.identifier.identify(win, feats)                    # (k,3)
        a = self.ai_cfg.ema_alpha
        for j, i in enumerate(ids):
            self.ident_probs[i] = a * scores[j] + (1 - a) * self.ident_probs[i]
        # 死亡目標歸零
        for d in swarm.drones:
            if not d.alive:
                self.ident_probs[d.id] = 0.0
        lead_p = self.ident_probs[:, ROLE_LEADER].copy()
        self.believed_leader = int(np.argmax(lead_p)) if lead_p.max() > 0 else -1
        self.leader_conf = float(lead_p.max())

    # ------------------------------------------------------------ SIGINT 射頻確認（要點4·獨立感測）
    def _update_decode(self, swarm):
        """SIGINT/ESM 射頻確認 —— ★與 GNN『看怎麼飛』完全獨立的第二感測器★。
        目標進接戰 envelope 後開始截獲其 C2 射頻；decode 是『SIGINT 確認這是指揮鏈
        節點的信心』，會朝該機的真實發射量 c2_emission『上限』累積、發射越強累積越快：
          領機 emission=1.0→爬到 1.0；中繼 0.5→只到 0.5；從機/誘餌 0.1→只到 0.1。
        ★關鍵★：這是上限封頂、不是延遲——從機/誘餌的 decode 永遠到不了確認門檻
        (decode_confirm)，所以『飛得像領機卻不發真 C2 的誘餌』再久也不會被 SIGINT
        確認、不會被斬首。雷達看得到形體、SIGINT 未確認者(<門檻)顯示灰色。"""
        engage_R = self.cfg.engage_range * getattr(swarm, "stealth", 1.0) \
            * getattr(swarm, "ew", 1.0)
        rate = self.dt / max(self.cfg.decode_full_t, 1e-3)
        for d in swarm.drones:
            if d.alive and self.radar.visible[d.id] \
                    and np.linalg.norm(d.pos - self.site) <= engage_R:
                cap = float(getattr(d, "c2_emission", 0.1))   # 確認上限=真實發射量
                if self.decode[d.id] < cap:
                    self.decode[d.id] = min(cap, self.decode[d.id] + rate * cap)

    # ------------------------------------------------------------ 軌跡預測（要點3）
    def predict_path(self, target_id) -> np.ndarray:
        """預測目標未來軌跡 (H,3)：LSTM（若有）否則卡爾曼 CV 外推"""
        H = self.ai_cfg.pred_horizon
        if self.lstm is not None:
            hist = self.radar.history(target_id, self.ai_cfg.hist_len)
            if hist is not None:
                return self.lstm.predict(hist)
        return self.radar.tracks[target_id].predict_ahead(H)

    def _aim_point(self, missile, target_id):
        """迭代求攔截點：用預測軌跡找『飛彈可同時抵達』的位置"""
        path = self.pred_paths.get(target_id)
        if path is None:
            path = self.predict_path(target_id)
            self.pred_paths[target_id] = path
        H = len(path)
        # 預測時域外 → 以預測末段速度線性外插
        end_v = (path[-1] - path[-2]) / self.dt if H >= 2 else np.zeros(3)

        def pos_at(t_go):
            k = t_go / self.dt
            if k < H:
                i = int(k)
                f = k - i
                return path[min(i, H - 1)] * (1 - f) + path[min(i + 1, H - 1)] * f
            return path[-1] + end_v * (t_go - H * self.dt)

        t_go = np.linalg.norm(self.pred_paths[target_id][0] - missile.pos) \
            / self.cfg.missile_speed
        for _ in range(4):
            aim = pos_at(t_go)
            t_go = np.linalg.norm(aim - missile.pos) / self.cfg.missile_speed
        return pos_at(t_go)

    # ------------------------------------------------------------ 火控
    def _in_range_targets(self, swarm):
        # ★陣形隱蔽性 + 電子干擾：低 RCS / 電戰壓制 → 防空被咬得晚、接戰距離縮短
        engage_R = self.cfg.engage_range * getattr(swarm, "stealth", 1.0) \
            * getattr(swarm, "ew", 1.0)
        out = []
        for d in swarm.drones:
            if d.alive and self.radar.visible[d.id] and \
                    np.linalg.norm(d.pos - self.site) <= engage_R:
                out.append(d.id)
        return out

    def _engaged_counts(self):
        c = {}
        for m in self.missiles:
            if m.alive:
                c[m.target_id] = c.get(m.target_id, 0) + 1
        return c

    def _select_target(self, t, swarm, mass_only=False):
        cand = self._in_range_targets(swarm)        # 接戰圈內、可被雷達追蹤者
        if not cand:
            return None, ""
        engaged = self._engaged_counts()

        def nearest(pool_ids, why):
            free = [i for i in pool_ids if engaged.get(i, 0) == 0]
            p = free if free else pool_ids
            dists = [np.linalg.norm(swarm.drones[i].pos - self.site) for i in p]
            return p[int(np.argmin(dists))], why

        pol = self.cfg.policy
        # ★ 分層火力：mass_only 的發射器專責攔截『最逼近目標的一般機』(防飽和突防)，
        #   不追指揮鏈——和斬首發射器分工，AI 才不會把彈都倒在指揮鏈、放任人海突防。
        #   AI 模式下 mass 發射器同樣受 SIGINT 篩選：不確認的從機/誘餌不開火，
        #   傳統則直接打最近——誘餌場景的核心差異點（傳統浪費彈在誘餌，AI 不吃誘餌）。
        if mass_only and pol == "ai":
            gate = self.cfg.decode_enable
            confirmed = [i for i in cand
                         if (not gate) or self.decode[i] >= self.cfg.decode_confirm]
            if confirmed:
                return nearest(confirmed, "攔截最逼近(SIGINT確認)·防飽和")
            return None, ""   # 尚無 SIGINT 確認目標，暫緩（不浪費彈在誘餌/從機）
        if mass_only or pol == "nearest":
            return nearest(cand, "攔截最逼近·防飽和" if mass_only else "最近目標")
        if pol == "ai":
            # ★ 感測融合斬首：GNN(看運動)決定「該打誰」、SIGINT(看 C2 射頻)確認「能不能打」。
            #   只有 SIGINT 已確認(decode>=1)的目標才允許斬首→領機射頻最強、最先被確認先斬；
            #   誘餌飛得像領機卻不發真 C2→永遠卡在未確認、AI 不被它牽走。攔截彈仍可打任何被
            #   追蹤的一般機(不需 SIGINT 確認)→AI 不空等、邊清外圍邊等領機被確認。
            gate = self.cfg.decode_enable
            decoded = [i for i in cand
                       if (not gate) or self.decode[i] >= self.cfg.decode_confirm]
            free_d = [i for i in decoded if engaged.get(i, 0) == 0]
            pool_d = free_d if free_d else decoded
            if pool_d:
                chain = self.ident_probs[:, ROLE_LEADER] \
                    + 0.9 * self.ident_probs[:, ROLE_RELAY]
                mask = np.zeros(self.n, bool)
                mask[pool_d] = True
                chain[~mask] = -1
                best = int(np.argmax(chain))
                if chain[best] >= self.cfg.ident_conf_fire * 0.5:
                    pl = self.ident_probs[best, ROLE_LEADER]
                    pr = self.ident_probs[best, ROLE_RELAY]
                    kind = "領機" if pl >= pr else "中繼機"
                    return best, f"AI指揮鏈打擊:{kind}(L={pl:.2f},R={pr:.2f})"
            # 領機尚未鎖定(解碼中) → 先攻最近的一般目標(不需解碼)
            return nearest(cand, "最近目標(領機鎖定中)")
        elif pol == "nearest":
            return nearest(cand, "最近目標")
        else:  # random
            free = [i for i in cand if engaged.get(i, 0) == 0]
            return int(self.rng.choice(free if free else cand)), "隨機目標"

    def _launch(self, t, target_id, why):
        d0 = self.site + np.array([0, 0, 3.0])
        path = self.predict_path(target_id)
        self.pred_paths[target_id] = path
        aim = path[min(len(path) - 1, 5)]
        v = aim - d0
        v = v / (np.linalg.norm(v) + 1e-9) * self.cfg.missile_speed
        m = Missile(d0, v, target_id, t)
        self.missiles.append(m)
        self.ammo -= 1
        self.shots_fired += 1
        self.events.append((t, f"🚀 發射攔截彈 → #{target_id}（{why}）"
                               f"［剩 {self.ammo} 彈］"))

    # ------------------------------------------------------------ 飛彈導引與毀傷
    def _guide_missiles(self, t, swarm):
        cfg = self.cfg
        refresh = self._step % 3 == 0          # 每 0.3 s 更新預測與攔截點
        if refresh:
            engaged = {m.target_id for m in self.missiles
                       if m.alive and swarm.drones[m.target_id].alive}
            self.pred_paths = {tid: self.predict_path(tid) for tid in engaged}
        for m in self.missiles:
            if not m.alive:
                continue
            tgt = swarm.drones[m.target_id]
            if not tgt.alive:
                m.alive = False    # 目標已毀 → 自毀
                continue
            if refresh:
                m._aim = self._aim_point(m, m.target_id)
            aim = getattr(m, "_aim", tgt.pos)
            want = aim - m.pos
            want = want / (np.linalg.norm(want) + 1e-9) * cfg.missile_speed
            a = (want - m.vel) * 2.5
            an = np.linalg.norm(a)
            if an > cfg.missile_accel:
                a = a * (cfg.missile_accel / an)
            m.vel = m.vel + a * self.dt
            m.vel = m.vel / (np.linalg.norm(m.vel) + 1e-9) * cfg.missile_speed
            m.pos = m.pos + m.vel * self.dt

            dist = np.linalg.norm(m.pos - tgt.pos)
            if dist < cfg.kill_radius:
                m.alive = False
                if self.rng.random() < cfg.p_kill:
                    swarm.kill(tgt.id, t)
                    self.kills += 1
                else:
                    self.events.append((t, f"🌀 攔截彈近炸失效（#{tgt.id} 倖存）"))
            elif t - m.launch_t > cfg.missile_life or m.pos[2] < 0:
                m.alive = False
                self.events.append((t, f"🌫️ 攔截彈失的（目標 #{tgt.id}）"))
        self.missiles = [m for m in self.missiles if m.alive]

    # ------------------------------------------------------------ 主步進
    def step(self, t, swarm):
        self._step = int(round(t / self.dt))
        self.radar.update(swarm, self.cfg.radar_range)
        if self.cfg.decode_enable:
            self._update_decode(swarm)        # SIGINT 解碼進度（領機先現身）

        if self.identifier is not None and t >= self.next_ident_t:
            self._run_identification(t, swarm)
            self.next_ident_t = t + self.cfg.ident_interval

        # ★ SEAD 壓制：任一反輻射機進 sead_range → 防空火力遭壓制(撕開雷達破口)，
        #   壓制窗口內無法發射，主力鑽過缺口突防。
        sr = getattr(self.cfg, "sead_range", 0.0)
        if sr > 0:
            for d in swarm.drones:
                if d.alive and getattr(d, "is_sead", False) and \
                        np.linalg.norm(d.pos - self.site) <= sr:
                    self.suppress_until = max(
                        self.suppress_until, t + self.cfg.sead_suppress_t)
                    break
        self.suppressed = t < self.suppress_until

        # 發射決策 ── ★分層火力：多座發射器時，奇數座專責攔截最逼近的一般機(防飽和
        #   突防)、其餘座專責指揮鏈斬首；單座則全力斬首。避免 AI 把彈全倒在指揮鏈、
        #   放任人海突防（SIGINT 封頂後從機不可斬，這層攔截才補得回防守）。
        for li in range(self.cfg.n_launchers):
            if self.suppressed or self.ammo <= 0 or t < self.launch_ready[li]:
                continue
            mass = (self.cfg.n_launchers > 1 and li % 2 == 1)
            target, why = self._select_target(t, swarm, mass_only=mass)
            if target is None:
                continue
            self._launch(t, target, why)
            self.launch_ready[li] = t + self.cfg.reload_time

        self._guide_missiles(t, swarm)

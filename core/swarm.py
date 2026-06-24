# -*- coding: utf-8 -*-
"""
要點 2：攻方機群 — 階層式通訊架構與失效處理
=============================================
階層架構：
  領機 (Leader)   ── 持有完整任務航線，廣播自身狀態（心跳）
  中繼機 (Relay)  ── 轉發領機訊號給超出通訊範圍的從機；備援任務航線
  從機 (Follower) ── 依領機狀態保持陣型槽位；不轉發

失效處理機制（本模組核心）：
  A. 領機失效：心跳逾時偵測 → 選舉延遲 → 由「持有任務的中繼機」依序遞補
     → 重新產生陣型槽位並以最小移動量重新指派（貪婪指派）
  B. 中繼機失效：孤兒從機斷線推算飛行（dead-reckoning）→ 確認失效後
     提拔從機為新中繼機 → 任務資料於重新連線時同步
  C. 斬首成功（領機+所有持任務節點皆失效）→ 機群進入「迷失模式」
     原地盤旋，任務失敗 —— 這正是防方 AI 優先打擊關鍵節點的理由
"""
import numpy as np

from config import SwarmConfig, ROLE_FOLLOWER, ROLE_RELAY, ROLE_LEADER, ROLE_NAMES
from core.drone import Drone
from core.formations import (make_formation, pick_relay_slots,
                             slot_world_positions, rotation_xy,
                             formation_traits, is_fiber, formation_ew,
                             formation_paradigm)


def _greedy_assign(drone_pos: np.ndarray, slot_pos: np.ndarray) -> list:
    """不等數量貪婪指派（機數 <= 槽數）：回傳每架機對應的槽索引"""
    m, k = len(drone_pos), len(slot_pos)
    D = np.linalg.norm(drone_pos[:, None, :] - slot_pos[None, :, :], axis=2)
    out = [-1] * m
    used_d = np.zeros(m, bool)
    used_s = np.zeros(k, bool)
    for _ in range(m):
        Dm = D.copy()
        Dm[used_d, :] = np.inf
        Dm[:, used_s] = np.inf
        i, j = np.unravel_index(np.argmin(Dm), Dm.shape)
        out[i] = int(j)
        used_d[i] = True
        used_s[j] = True
    return out


class Swarm:
    def __init__(self, cfg: SwarmConfig, target_pos, rng: np.random.Generator,
                 dt: float):
        self.cfg = cfg
        self.dt = dt
        self.rng = rng
        self.target = np.asarray(target_pos, float)
        self.events = []          # (t, 文字) 事件紀錄
        self.lost_mode = False
        self.lost_center = None
        self.n_through = 0        # 突防成功數

        # ★ 陣形戰術取捨 + 領機角色機制狀態
        self.stealth, self.comm_mult, self.form_note = \
            formation_traits(cfg.formation)
        # ★ 兩大流派：光纖群免疫電子干擾且抗斬首；無線群帶電戰壓制但有指揮鏈
        self.fiber = is_fiber(cfg.formation)
        self.ew = formation_ew(cfg.formation)     # 電戰對防空接戰距離壓制(<1)
        self.paradigm = formation_paradigm(cfg.formation)
        self.fiber_lag = 24      # 蛇形尾隨：後機落後前機幾步(×rank)複製航跡
        self.leader_trail = []   # 領機航跡緩衝（一字蛇形沿跡尾隨用）
        self.coord_C = 1.0        # 協調係數（領機在→高，死→驟降，遞補→緩升）
        self.coord_ready_t = 0.0  # 協調重建完成時刻
        self.warn_active = True   # 全網預警是否生效（領機在線）
        self._leader_ok = True    # 本步領機是否在線（供 _evade_accel）

        # ---- 任務航線：出發點 → 中途航點（含側偏轉彎）→ 目標
        # 跨海峽場景：fixed_bearing=0 → 自西向東（對岸→台灣）；None → 隨機(訓練用)
        fb = getattr(cfg, "fixed_bearing", None)
        if fb is None:
            bearing = rng.uniform(0, 2 * np.pi)
        else:
            bearing = fb + rng.uniform(-0.12, 0.12)   # 小擾動，保留隨機性
        u = np.array([np.cos(bearing), np.sin(bearing), 0.0])
        side = np.array([-u[1], u[0], 0.0])
        spawn = self.target - u * cfg.spawn_distance
        spawn[2] = cfg.spawn_alt
        wps = []
        for k in range(1, cfg.n_waypoints + 1):
            frac = k / (cfg.n_waypoints + 1)
            lateral = rng.uniform(-1, 1) * cfg.waypoint_lateral
            wp = spawn + u * cfg.spawn_distance * frac + side * lateral
            wp[2] = cfg.spawn_alt + rng.uniform(-25, 25)
            wps.append(wp)
        wps.append(self.target + np.array([0, 0, cfg.spawn_alt * 0.4]))
        self.waypoints = np.array(wps)
        self.wp_i = 0             # 任務進度（由持任務節點共享）

        # ---- 生成陣型與機隊
        n = cfg.n_drones
        self.formation = cfg.formation
        self.slots = make_formation(cfg.formation, n, cfg.spacing)
        self.relay_slot_idx = pick_relay_slots(self.slots, cfg.n_relays, rng)

        # ★ 多軸夾擊：依槽位左右把各機分到 左/中/右 股（領機固定中央股）。
        #   出發時各股橫向分開(drone_lane)，接近目標時 converge_frac→0 向心收攏。
        self.spawn_dist = float(np.linalg.norm(self.target - spawn))
        self.n_axes_eff = max(1, int(getattr(cfg, "n_axes", 1)))
        spread = float(getattr(cfg, "axis_spread", 0.0))
        self.drone_lane = {i: 0.0 for i in range(n)}
        if self.n_axes_eff > 1 and spread > 0:
            lanes = np.linspace(-spread, spread, self.n_axes_eff)
            ymax = max(float(np.abs(self.slots[:, 1]).max()), 1e-6)
            for i in range(1, n):                       # i=0 領機 → 中央(0)
                frac = self.slots[i, 1] / ymax          # 槽位左右 -1..1
                j = int(round((frac + 1) / 2 * (self.n_axes_eff - 1)))
                self.drone_lane[i] = float(lanes[min(max(j, 0),
                                                     self.n_axes_eff - 1)])
        self._cf = 1.0                                  # 當前收攏係數（step 內更新）

        heading0 = (self.waypoints[0] - spawn)[:2]
        heading0 = heading0 / np.linalg.norm(heading0)
        self.form_heading = heading0.copy()   # 陣型框架航向（低通限速旋轉）
        slots0 = self.slots.copy().astype(float)
        for i in range(n):
            slots0[i, 1] += self.drone_lane[i]          # 出發即分股（frac=1）
        slot_world = slot_world_positions(spawn, heading0, slots0)
        v0 = np.array([heading0[0], heading0[1], 0.0]) * cfg.cruise_speed

        self.drones = []
        relay_ids = []
        for i in range(n):
            if i == 0:
                role = ROLE_LEADER
            elif i in [self._slot_owner_init(s, n) for s in self.relay_slot_idx]:
                role = ROLE_RELAY
            else:
                role = ROLE_FOLLOWER
            d = Drone(i, slot_world[i], v0, role)
            d.evade_phase = rng.uniform(0, 2 * np.pi)   # 種子化 → 可重現
            d.has_mission = role in (ROLE_LEADER, ROLE_RELAY)
            d.last_leader_pos = slot_world[0].copy()
            d.last_leader_vel = v0.copy()
            d.last_form_heading = heading0.copy()
            self.drones.append(d)
            if role == ROLE_RELAY:
                relay_ids.append(i)
        # 初始指派 = 各機就位於自己的槽
        self.assignment = {i: i for i in range(n)}

        # ★ 光纖群：每架都經實體光纖持有完整航線 → 全員任務備援，
        #   領機被打掉可「即時無縫接替」，後機照航跡續突（抗斬首的關鍵）。
        if self.fiber:
            for d in self.drones:
                d.has_mission = True

        # ★ 誘餌＋沉默領機：首要誘餌頂到隊形最顯眼處(slot0)當「空間領頭」、
        #   負責導航讓全隊繞它編隊；真領機與它對調、退到邊緣槽位「藏身」，
        #   但仍是通訊/協調的真指揮。AI 只能從飛行行為認領機→把誘餌當領機打→
        #   真領機存活。這是行為式識別(要點4)的死穴。n_decoys=0 完全不影響。
        nd = int(getattr(cfg, "n_decoys", 0))
        self.anchor_id = 0                  # 空間領頭(隊形錨點+導航)，預設=領機
        if nd > 0:
            foll = [d for d in self.drones if d.role == ROLE_FOLLOWER]
            decoys = foll[-nd:]
            for d in decoys:
                d.is_decoy = True
            lead, dec0 = self.drones[0], decoys[0]
            lead.pos, dec0.pos = dec0.pos.copy(), lead.pos.copy()      # 對調位置
            self.assignment[0], self.assignment[dec0.id] = \
                self.assignment[dec0.id], self.assignment[0]           # 對調槽位
            self.drone_lane[0], self.drone_lane[dec0.id] = \
                self.drone_lane[dec0.id], self.drone_lane[0]
            self.anchor_id = dec0.id        # 誘餌當空間領頭

        # ---- 失效處理狀態
        self.leader_id = 0
        self.leader_death_t = None     # 領機陣亡時刻（真實）
        self.election_done_t = None    # 選舉完成時刻（偵測+延遲後）
        self.pending_confirm = []      # [(確認時刻, 陣亡機id)] 非領機損失確認佇列

    @staticmethod
    def _slot_owner_init(slot_idx, n):
        """初始時槽位 i 由編號 i 的無人機進駐"""
        return slot_idx if slot_idx < n else -1

    # ------------------------------------------------------------ 查詢
    def get(self, i) -> Drone:
        return self.drones[i]

    def alive_drones(self):
        return [d for d in self.drones if d.alive]

    def get_leader(self):
        if self.leader_id is not None and self.drones[self.leader_id].alive \
                and self.drones[self.leader_id].role == ROLE_LEADER:
            return self.drones[self.leader_id]
        return None

    def positions(self):
        return np.array([d.pos for d in self.drones])

    def roles(self):
        return np.array([d.role for d in self.drones])

    def alive_mask(self):
        return np.array([d.alive for d in self.drones])

    # ------------------------------------------------------------ 被擊落（由 engine 呼叫）
    def kill(self, drone_id: int, t: float):
        d = self.drones[drone_id]
        if not d.alive:
            return
        d.alive = False
        self.events.append((t, f"💥 {ROLE_NAMES[d.role]} #{drone_id} 被擊落"))
        if d.role == ROLE_LEADER:
            self.leader_death_t = t      # 機群須經心跳逾時才會「發現」
        else:
            # 鄰機目視/鏈路很快發現非領機損失 → 0.8s 後確認並重組
            self.pending_confirm.append((t + 0.8, drone_id))

    # ------------------------------------------------------------ 通訊連線計算
    def _update_comm(self, t: float):
        """廣播樹：領機 → (鏈式)中繼機 → 從機。回傳連線布林陣列。
        同時記錄通訊邊 self.comm_edges（視覺化用）。"""
        leader = self.get_leader()
        alive = self.alive_drones()
        connected = {d.id: False for d in self.drones}
        self.comm_edges = []
        if leader is None:
            for d in alive:
                d.connected = False
            return connected
        # ★ 光纖群：實體光纖鏈路，不受距離/電子干擾影響 → 全員恆連線。
        if self.fiber:
            for d in alive:
                d.connected = connected[d.id] = True
                d.last_heard = t
                d.last_leader_pos = leader.pos.copy()
                d.last_leader_vel = leader.vel.copy()
                d.last_form_heading = self.form_heading.copy()
                if d.role == ROLE_RELAY and not d.has_mission:
                    d.has_mission = True
            self.comm_edges = [(leader.id, d.id) for d in alive
                               if d.id != leader.id]
            return connected
        # 通訊半徑套用陣形 comm_mult（密集陣通訊強、散開陣吃緊）
        comm_R = self.cfg.comm_range * self.comm_mult
        # BFS：中繼機在任一已連線廣播節點範圍內 → 加入廣播樹
        broadcasters = [leader]
        connected[leader.id] = True
        changed = True
        while changed:
            changed = False
            for d in alive:
                if d.role == ROLE_RELAY and not connected[d.id]:
                    for b in broadcasters:
                        if np.linalg.norm(d.pos - b.pos) <= comm_R:
                            connected[d.id] = True
                            broadcasters.append(d)
                            self.comm_edges.append((b.id, d.id))
                            changed = True
                            break
        # 從機：在任一廣播節點範圍內即可收訊
        for d in alive:
            if d.role == ROLE_FOLLOWER and not connected[d.id]:
                for b in broadcasters:
                    if np.linalg.norm(d.pos - b.pos) <= comm_R:
                        connected[d.id] = True
                        self.comm_edges.append((b.id, d.id))
                        break
        # 更新各機收到的領機狀態（心跳）；新中繼機需時間同步任務資料
        for d in alive:
            d.connected = connected[d.id]
            if connected[d.id]:
                d.last_heard = t
                d.last_leader_pos = leader.pos.copy()
                d.last_leader_vel = leader.vel.copy()
                d.last_form_heading = self.form_heading.copy()
                if d.role == ROLE_RELAY and not d.has_mission \
                        and d.mission_sync_t is not None \
                        and t >= d.mission_sync_t:
                    d.has_mission = True
                    self.events.append(
                        (t, f"📥 中繼機 #{d.id} 任務資料同步完成"))
        return connected

    def _update_form_heading(self):
        """陣型框架航向以限速旋轉追隨領機航向（避免轉彎時外側槽位掃掠過快）"""
        leader = self.get_leader()
        if leader is None:
            return
        h = leader.heading_xy()
        cur = np.arctan2(self.form_heading[1], self.form_heading[0])
        tgt = np.arctan2(h[1], h[0])
        diff = (tgt - cur + np.pi) % (2 * np.pi) - np.pi
        max_d = np.deg2rad(self.cfg.form_turn_rate) * self.dt
        cur += np.clip(diff, -max_d, max_d)
        self.form_heading = np.array([np.cos(cur), np.sin(cur)])

    # ------------------------------------------------------------ 失效處理
    def _handle_failures(self, t: float):
        cfg = self.cfg
        # --- A. 領機失效：心跳逾時 → 選舉
        leader = self.get_leader()
        if leader is None and not self.lost_mode:
            if self.fiber:
                # 光纖：實體鏈路斷線「即時」被偵測，無縫接替、無選舉延遲
                if self.leader_death_t is not None:
                    self._elect_leader(t)
                    self.election_done_t = None
                    self.leader_death_t = None
            else:
                if self.leader_death_t is not None \
                        and self.election_done_t is None:
                    detect_t = self.leader_death_t + cfg.heartbeat_timeout
                    if t >= detect_t:
                        self.election_done_t = detect_t + cfg.election_delay
                        self.events.append((t, "⚠️ 機群偵測到領機失聯，啟動選舉"))
                if self.election_done_t is not None \
                        and t >= self.election_done_t:
                    self._elect_leader(t)
                    self.election_done_t = None
                    self.leader_death_t = None

        # --- B. 非領機損失確認 → 重組
        due = [x for x in self.pending_confirm if x[0] <= t]
        if due:
            self.pending_confirm = [x for x in self.pending_confirm if x[0] > t]
            for _, dead_id in due:
                dead_role = self.drones[dead_id].role
                if dead_role == ROLE_RELAY:
                    self._promote_relay(t, near_id=dead_id)
            if self.get_leader() is not None:
                self._regen_formation(t, reason="編隊重組")

    def _elect_leader(self, t: float):
        """選舉：持有任務資料者優先（中繼機 → 其他），否則機群迷失"""
        cand = [d for d in self.alive_drones() if d.has_mission]
        cand.sort(key=lambda d: (0 if d.role == ROLE_RELAY else 1, d.id))
        if not cand:
            self.lost_mode = True
            alive = self.alive_drones()
            self.lost_center = (np.mean([d.pos for d in alive], axis=0)
                                if alive else self.target * 0)
            # 距目標尚遠時被癱瘓才算「斬首成功」（終端突防耗盡節點不算）
            self.lost_at_dist = float(
                np.linalg.norm(self.lost_center - self.target))
            self.events.append((t, "❌ 無任務備援節點存活 — 機群迷失，任務癱瘓"
                                   f"（距目標 {self.lost_at_dist:.0f} m）"))
            return
        new = cand[0]
        old_role = new.role
        new.role = ROLE_LEADER
        self.leader_id = new.id
        if self.fiber:
            # 光纖：航線早經實體鏈路共享 → 無縫接替，協調不需重建
            self.coord_ready_t = t
            self.events.append(
                (t, f"🔗 光纖無縫接替：#{new.id} 即時續飛航線（後機照常突防）"))
        else:
            self.coord_ready_t = t + self.cfg.coord_rebuild_time  # 協調須重建
            self.events.append(
                (t, f"👑 {ROLE_NAMES[old_role]} #{new.id} 遞補為新領機"
                    f"（協調重建中…）"))
        # 領機從原中繼機升任 → 中繼機數量不足 → 提拔從機
        self._promote_relay(t, near_id=new.id)
        self._regen_formation(t, reason="新領機重整編隊")

    def _promote_relay(self, t: float, near_id: int = None):
        """維持中繼機數量：優先提拔『孤兒』或距離缺口最近的從機"""
        alive = self.alive_drones()
        n_relay = sum(1 for d in alive if d.role == ROLE_RELAY)
        need = min(self.cfg.n_relays, max(len(alive) - 1, 0)) - n_relay
        ref = self.drones[near_id].pos if near_id is not None else None
        for _ in range(max(need, 0)):
            followers = [d for d in alive if d.role == ROLE_FOLLOWER]
            if not followers:
                return
            orphans = [d for d in followers if not d.connected]
            pool = orphans if orphans else followers
            if ref is not None:
                pool.sort(key=lambda d: np.linalg.norm(d.pos - ref))
            chosen = pool[0]
            chosen.role = ROLE_RELAY
            # 任務資料須耗時同步（_update_comm 於同步完成後賦予備援資格）；
            # 光纖群經實體鏈路即時取得航線 → 無同步延遲。
            chosen.mission_sync_t = t + (0.0 if self.fiber
                                         else self.cfg.mission_sync_time)
            self.events.append(
                (t, f"🔁 從機 #{chosen.id} 提拔為中繼機（任務同步中…）"))

    def _regen_formation(self, t: float, reason: str = ""):
        """依存活機數重生槽位模板，並以最小移動量重新指派"""
        leader = self.get_leader()
        alive = self.alive_drones()
        n = len(alive)
        if leader is None or n == 0:
            return
        self.slots = make_formation(self.formation, n, self.cfg.spacing)
        self.relay_slot_idx = pick_relay_slots(
            self.slots, min(self.cfg.n_relays, n - 1), self.rng)
        slot_world = slot_world_positions(leader.pos, self.form_heading,
                                          self.slots)
        self.assignment = {leader.id: 0}
        relays = [d for d in alive if d.role == ROLE_RELAY]
        followers = [d for d in alive if d.role == ROLE_FOLLOWER]
        # 中繼機 → 中繼槽位（子群中心），其餘 → 剩餘槽位
        r_idx = list(self.relay_slot_idx)
        if relays and r_idx:
            pos = np.array([d.pos for d in relays])
            sp = slot_world[r_idx]
            a = _greedy_assign(pos, sp)
            for d, j in zip(relays, a):
                self.assignment[d.id] = r_idx[j]
        rest_idx = [i for i in range(1, n)
                    if i not in set(self.assignment.values())]
        rest = followers + [d for d in relays
                            if d.id not in self.assignment]
        if rest and rest_idx:
            pos = np.array([d.pos for d in rest])
            sp = slot_world[rest_idx]
            a = _greedy_assign(pos, sp)
            for d, j in zip(rest, a):
                self.assignment[d.id] = rest_idx[j]
        if reason:
            self.events.append((t, f"🛠️ {reason}（存活 {n} 架）"))

    # ------------------------------------------------------------ 控制律
    def _leader_control(self, d: Drone, t, missiles):
        cfg = self.cfg
        wp = self.waypoints[self.wp_i]
        to_wp = wp - d.pos
        if np.linalg.norm(to_wp) < 60.0 and self.wp_i < len(self.waypoints) - 1:
            self.wp_i += 1
            wp = self.waypoints[self.wp_i]
            to_wp = wp - d.pos
        v_des = to_wp / (np.linalg.norm(to_wp) + 1e-9) * cfg.cruise_speed
        a = (v_des - d.vel) * 1.2
        return a + self._evade_accel(d, t, missiles)

    def _follower_control(self, d: Drone, t, missiles, leader_alive):
        """從機/中繼機：追蹤陣型槽位（依自身所知的領機狀態）"""
        cfg = self.cfg
        # 誘餌模式：全隊（含沉默真領機）繞「空間領頭(誘餌)」編隊
        if getattr(self, "_anchor_live", self.leader_id) != self.leader_id:
            anc = self.drones[self._anchor_live]
            Lp, Lv = anc.pos, anc.vel
            hh = Lv[:2]
            nn = np.linalg.norm(hh)
            h = hh / nn if nn > 1e-6 else self.form_heading
            slot = self.slots[self.assignment.get(d.id, 0)].copy()
            slot[1] += self.drone_lane.get(d.id, 0.0) * self._cf
            target = Lp + rotation_xy(h) @ slot
            a = cfg.kp * (target - d.pos) + cfg.kd * (Lv - d.vel)
            return a + self._evade_accel(d, t, missiles)
        # ★ 一字蛇形：後機沿「領機數秒前的航跡」尾隨 → 真正的蛇行軌跡；
        #   領機亡→新領機續寫航跡、後機照跟（抗斬首的具體呈現）。
        if self.formation == "snake" and len(self.leader_trail) > 2:
            rank = max(1, self.assignment.get(d.id, 1))
            idx = max(0, len(self.leader_trail) - 1 - rank * self.fiber_lag)
            tgt = self.leader_trail[idx].copy()
            tgt[2] = cfg.spawn_alt
            idx2 = min(len(self.leader_trail) - 1, idx + 1)
            tang = self.leader_trail[idx2] - self.leader_trail[idx]
            nt = np.linalg.norm(tang)
            vdes = tang / nt * cfg.cruise_speed if nt > 1e-6 else d.vel
            a = cfg.kp * 1.5 * (tgt - d.pos) + cfg.kd * (vdes - d.vel)
            return a + self._evade_accel(d, t, missiles)
        # 自身認知的領機狀態：連線 → 即時；斷線 → 航位推算 (dead-reckoning)
        if not d.connected and d.last_leader_pos is not None:
            d.last_leader_pos = d.last_leader_pos + d.last_leader_vel * self.dt
        Lp, Lv = d.last_leader_pos, d.last_leader_vel
        if Lp is None:
            return self._evade_accel(d, t, missiles)
        if d.last_form_heading is not None:
            h = d.last_form_heading
        else:
            h = Lv[:2]
            n = np.linalg.norm(h)
            h = h / n if n > 1e-6 else np.array([1.0, 0.0])
        slot = self.slots[self.assignment.get(d.id, 0)].copy()
        slot[1] += self.drone_lane.get(d.id, 0.0) * self._cf   # 多軸車道（收攏）
        R = rotation_xy(h)
        target = Lp + R @ slot
        a = cfg.kp * (target - d.pos) + cfg.kd * (Lv - d.vel)
        return a + self._evade_accel(d, t, missiles)

    def _lost_control(self, d: Drone, t, missiles):
        """迷失模式：繞失聯點盤旋（被斬首機群的典型行為）"""
        c = self.lost_center
        r_vec = d.pos - c
        r_vec[2] = 0
        r = np.linalg.norm(r_vec) + 1e-9
        out_u = r_vec / r
        tang = np.array([-out_u[1], out_u[0], 0.0])
        v_des = tang * self.cfg.cruise_speed * 0.7 + out_u * (180.0 - r) * 0.05
        v_des[2] = (self.cfg.spawn_alt - d.pos[2]) * 0.05
        a = (v_des - d.vel) * 1.0
        return a + self._evade_accel(d, t, missiles)

    def _anchor_drone(self, leader):
        """空間領頭(隊形錨點+導航)：首要誘餌活著就用它；死了換下一個活誘餌續扮；
        都沒了才由真領機自己領頭（此時真領機才暴露）。"""
        a = self.drones[self.anchor_id]
        if a.alive:
            return a
        for d in self.drones:
            if d.is_decoy and d.alive:
                return d
        return leader

    def _decoy_control(self, d: Drone, t, missiles):
        """誘餌：衝到機群質心前方當『假領機點』，誘 AI 把識別/火力導過來，
        掩護真領機。正面性是防方識別第一大特徵，故衝最前方最能騙過 AI。"""
        cfg = self.cfg
        alive = self.alive_drones()
        cen = (np.mean([dd.pos for dd in alive], axis=0)
               if alive else d.pos.copy())
        to_t = self.target - cen
        u = to_t / (np.linalg.norm(to_t) + 1e-9)
        false_pos = cen + u * cfg.decoy_lead
        false_pos[2] = cfg.spawn_alt
        v_des = false_pos - d.pos
        v_des = v_des / (np.linalg.norm(v_des) + 1e-9) * cfg.cruise_speed
        a = (v_des - d.vel) * 1.1
        return a + self._evade_accel(d, t, missiles)

    def _converge_frac(self, leader):
        """多軸夾擊收攏係數：1 = 出發(各股最分散) → 0 = 抵達目標(向心收攏)。"""
        if self.n_axes_eff <= 1:
            return 0.0
        if leader is not None:
            ref = leader.pos
        else:
            alive = self.alive_drones()
            ref = (np.mean([d.pos for d in alive], axis=0)
                   if alive else self.target)
        dist = float(np.linalg.norm((self.target - ref)[:2]))
        return float(np.clip(dist / max(self.spawn_dist, 1e-6), 0.0, 1.0))

    def _separation_accel(self):
        """機間避碰（一次算全部，O(N^2)）"""
        cfg = self.cfg
        alive = self.alive_drones()
        out = {d.id: np.zeros(3) for d in alive}
        for i, di in enumerate(alive):
            for dj in alive[i + 1:]:
                diff = di.pos - dj.pos
                dist = np.linalg.norm(diff)
                if 1e-9 < dist < cfg.sep_dist:
                    f = cfg.sep_gain * (1 - dist / cfg.sep_dist) * diff / dist
                    out[di.id] += f
                    out[dj.id] -= f
        return out

    def _evade_accel(self, d: Drone, t, missiles):
        """偵測到來襲飛彈 → 蛇行規避。
        ★領機=預警大腦：在線且本機連線 → 全網大預警範圍；否則短視。
        ★領機=協調   ：規避效能隨協調係數 C 縮放（C 低 → 各自為政、閃不掉）。"""
        cfg = self.cfg
        warn_R = (cfg.warn_radius_leader if (self._leader_ok and d.connected)
                  else cfg.warn_radius_self)
        threat = None
        best = warn_R
        for m in missiles:
            if m.target_id != d.id and np.linalg.norm(m.pos - d.pos) > 120:
                continue   # 只對鎖定自己或極近的飛彈反應
            dist = np.linalg.norm(m.pos - d.pos)
            closing = np.dot(m.vel, d.pos - m.pos)
            if dist < best and closing > 0:
                best = dist
                threat = m
        if threat is None:
            return np.zeros(3)
        eff = cfg.evade_min_eff + (1 - cfg.evade_min_eff) * self.coord_C
        h = d.heading_xy()
        lateral = np.array([-h[1], h[0], 0.0])
        s = np.sin(2 * np.pi * t / cfg.evade_period + d.evade_phase)
        return lateral * cfg.evade_accel * eff * np.sign(s) \
            + np.array([0, 0, 1.0]) * cfg.evade_accel * eff * 0.35 * np.cos(
                2 * np.pi * t / cfg.evade_period + d.evade_phase)

    def _update_coordination(self, t):
        """更新協調係數 C 與預警狀態（領機角色機制的核心狀態）。"""
        alive = self.alive_drones()
        leader = self.get_leader()
        self.warn_active = leader is not None
        if not alive:
            self.coord_C = 0.0
            return
        conn = float(np.mean([d.connected for d in alive]))
        if self.fiber:
            target = max(conn, 0.7)            # 光纖：協調靠預規劃航線，不依賴領機
        elif leader is None:
            target = 0.15                      # 無領機 → 協調崩潰
        elif t < self.coord_ready_t:           # 遞補後協調重建中 → 緩升
            span = self.cfg.coord_rebuild_time
            ramp = float(np.clip(1 - (self.coord_ready_t - t) / span, 0.2, 1))
            target = conn * ramp
        else:
            target = conn
        self.coord_C += (target - self.coord_C) * 0.12   # 平滑
        self.coord_C = float(np.clip(self.coord_C, 0.0, 1.0))

    # ------------------------------------------------------------ 主步進
    def step(self, t: float, missiles):
        cfg = self.cfg
        self._update_form_heading()
        self._update_comm(t)
        self._handle_failures(t)
        self._update_coordination(t)
        leader = self.get_leader()
        self._leader_ok = leader is not None    # 供 _evade_accel 判斷預警
        self._cf = self._converge_frac(leader)  # 多軸向心收攏係數（1→0）
        if leader is not None:                  # 一字蛇形：緩存領機航跡供後機沿跡尾隨
            self.leader_trail.append(leader.pos.copy())
            if len(self.leader_trail) > 600:
                self.leader_trail.pop(0)
        anchor = self._anchor_drone(leader)     # 空間領頭(領機或誘餌)
        self._anchor_live = anchor.id if anchor is not None else self.leader_id
        sep = self._separation_accel()

        for d in self.alive_drones():
            if self.lost_mode:
                a = self._lost_control(d, t, missiles)
            elif d.id == self._anchor_live:
                a = self._leader_control(d, t, missiles)   # 空間領頭導航
            elif d.is_decoy:
                a = self._decoy_control(d, t, missiles)     # 其餘誘餌：前方佯動
            else:
                a = self._follower_control(d, t, missiles,
                                           leader is not None)  # 含沉默真領機
            a = a + sep[d.id]
            d.step(a, self.dt, cfg.max_accel, cfg.max_speed)

            # 突防判定
            if not self.lost_mode and \
                    np.linalg.norm(d.pos - self.target) < cfg.strike_radius:
                d.alive = False
                d.succeeded = True
                self.n_through += 1
                self.events.append(
                    (t, f"🎯 {ROLE_NAMES[d.role]} #{d.id} 突防成功！"))
                if d.role == ROLE_LEADER:
                    self.leader_death_t = t   # 領機衝過去也算失聯，須遞補

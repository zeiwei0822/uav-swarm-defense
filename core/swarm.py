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

        # ★ 反輻射(SEAD)機：標記最前方(尖端,槽位最 +x)的 n_sead 架從機，衝防空壓制
        #   火力撕破口、可拋棄；領機/中繼不當 SEAD。
        ns = int(getattr(cfg, "n_sead", 0))
        if ns > 0:
            foll = sorted((d for d in self.drones if d.role == ROLE_FOLLOWER),
                          key=lambda d: -float(self.slots[d.id][0]))
            for d in foll[:ns]:
                d.is_sead = True

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

        # ★★ 要點2 失效處理策略 + S_node 健康度（種子化→可重現）
        self.fail_strategy = getattr(cfg, "fail_strategy", "chain")
        for d in self.drones:                       # 各機個體健康度差異
            d.soc = float(rng.uniform(0.72, 1.0))
            d.computing = float(rng.uniform(0.55, 1.0))
            d.sensor = float(rng.uniform(0.55, 1.0))
        self.contracted = False        # 向心收縮(中繼全失→LOS直控)旗標
        self.bionic = (self.fail_strategy == "bionic")  # 仿生湧現：無固定領機
        self.terminal = False          # 終端自殺階段(ToT同時彈著+混沌規避)
        # 多組並進(情境一)：每組各有獨立指揮域；group_leader[gid]=該組領機 id
        self.n_groups = max(1, int(getattr(cfg, "n_groups", 1)))
        self.group_leader = {0: 0}
        self.wp_i_of = {0: 0}
        self._fissioned = False
        if self.bionic:
            self.coord_C = 0.8         # 仿生：無領機，但個體規則維持中等協調
        if self.n_groups > 1:
            self._init_groups()

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
        if self.bionic:                       # 仿生：對等網狀，個體只看鄰居
            for d in alive:
                d.connected = connected[d.id] = True
                d.last_heard = t
            return connected
        if self._is_multi():                  # 多組/分裂：各機連到本組領機
            cr = self.cfg.comm_range * self.comm_mult
            for d in alive:
                gl = self.get_group_leader(d.group_id)
                if gl is not None and (d.id == gl.id
                                       or np.linalg.norm(d.pos - gl.pos) <= cr):
                    d.connected = connected[d.id] = True
                    d.last_heard = t
                    d.last_leader_pos = gl.pos.copy()
                    d.last_leader_vel = gl.vel.copy()
                    if d.id != gl.id:
                        self.comm_edges.append((gl.id, d.id))
                else:
                    d.connected = False
            return connected
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
        if self.bionic:
            return                       # 策略三 仿生：無領機，無失效處理
        if self._is_multi():
            self._handle_failures_multi(t)
            return
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
            relay_lost = False
            for _, dead_id in due:
                if self.drones[dead_id].role == ROLE_RELAY:
                    self._promote_relay(t, near_id=dead_id)
                    relay_lost = True
            leader = self.get_leader()
            # 情境二·3：健康度策略下中繼失→向心收縮，全隊縮短間距改領機 LOS 直控
            if (self.fail_strategy == "health" and relay_lost
                    and leader is not None and not self.contracted
                    and not self.fiber):
                self.contracted = True
                self.events.append(
                    (t, "🪢 中繼失效 → 向心收縮，全隊縮短間距改 LOS 直控"))
            if leader is not None:
                self._regen_formation(t, reason="編隊重組")

    def _centrality_map(self):
        """各存活機的拓撲中心度近似(0~1)：越靠機群質心越高(代理 betweenness)。"""
        alive = self.alive_drones()
        if not alive:
            return {}
        P = np.array([d.pos for d in alive])
        c = P.mean(axis=0)
        dist = np.linalg.norm(P - c, axis=1)
        mx = float(dist.max()) + 1e-6
        return {alive[i].id: float(1.0 - dist[i] / mx) for i in range(len(alive))}

    def _snode_score(self, d, cen_map):
        """S_node 健康度 = 電量0.4 + 中心性0.3 + 算力0.2 + 感測0.1（要點2策略二）。"""
        w = self.cfg.snode_w
        cen = cen_map.get(d.id, 0.5)
        return w[0] * d.soc + w[1] * cen + w[2] * d.computing + w[3] * d.sensor

    def _on_total_command_loss(self, t: float):
        """無可接任指揮節點：機群迷失癱瘓。繼承鏈策略下＝斬首成功，
        凸顯剛性繼任清單耗盡後的『二次失效』。"""
        alive = self.alive_drones()
        self.lost_mode = True
        self.lost_center = (np.mean([d.pos for d in alive], axis=0)
                            if alive else self.target * 0)
        self.lost_at_dist = float(np.linalg.norm(self.lost_center - self.target))
        self.events.append((t, "❌ 無備援指揮節點存活 — 機群迷失，任務癱瘓"
                               f"（距目標 {self.lost_at_dist:.0f} m）"))

    def _elect_leader(self, t: float, gid: int = 0):
        """選舉新領機。chain=繼任清單(僅持任務者,中繼優先,順位)；
        health=S_node 健康度(任一存活機可接任)。指揮節點全失：chain→癱瘓(二次失效)、
        health 大群→集群分裂、health 小群→最健康者接任。bionic 無固定領機→不選舉。"""
        if self.bionic:
            return
        members = [d for d in self.alive_drones() if d.group_id == gid]
        mission_cand = [d for d in members if d.has_mission]
        if self.fail_strategy == "health":
            # 健康度策略：指揮節點全失 + 大群 → 集群分裂(情境二·1)
            if (not mission_cand and not self._fissioned and not self.fiber
                    and len(members) >= self.cfg.fission_min):
                self._fission(t)
                return
            cand = members                  # 任一存活機可依健康度接任(抗毀傷)
        else:
            cand = mission_cand             # 繼承鏈：僅繼任清單(持任務者)
        if not cand:
            self._on_total_command_loss(t)  # 清單耗盡/全滅 → 迷失癱瘓
            return
        if self.fail_strategy == "health":
            cen = self._centrality_map()
            new = max(cand, key=lambda d: self._snode_score(d, cen))
            note = f"健康度選舉 S_node={self._snode_score(new, cen):.2f}"
        else:
            cand.sort(key=lambda d: (0 if d.role == ROLE_RELAY else 1, d.id))
            new = cand[0]
            note = "繼任清單順位"
        old_role = new.role
        new.role = ROLE_LEADER
        new.has_mission = True
        self.leader_id = new.id
        self.group_leader[gid] = new.id
        if self.fiber:
            self.coord_ready_t = t
            self.events.append(
                (t, f"🔗 光纖無縫接替：#{new.id} 即時續飛航線（後機照常突防）"))
        else:
            self.coord_ready_t = t + self.cfg.coord_rebuild_time
            self.events.append(
                (t, f"👑 {ROLE_NAMES[old_role]} #{new.id} 遞補為新領機（{note}）"))
        # ★ 斬首→癱瘓的關鍵：繼承鏈(僵化)不補充中繼——原始指揮鏈(領機+原中繼)被逐一
        #   斬殺耗盡後即『二次失效』迷失癱瘓，正是剛性繼任清單的代價。健康度/光纖則動態
        #   補位(從機升中繼)維持韌性、抗斬首。這讓無線繼承鏈群真的「斬得死」。
        if self.fail_strategy == "health" or self.fiber:
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
        if self.contracted:                  # 向心收縮：縮短間距改 LOS 直控
            self.slots = self.slots * self.cfg.contract_factor
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
    def _leader_control(self, d: Drone, t, missiles, gid=None):
        cfg = self.cfg
        wi = self.wp_i if gid is None else self.wp_i_of.get(gid, 0)
        wp = self.waypoints[wi]
        to_wp = wp - d.pos
        if np.linalg.norm(to_wp) < 60.0 and wi < len(self.waypoints) - 1:
            wi += 1
            if gid is None:
                self.wp_i = wi
            else:
                self.wp_i_of[gid] = wi
            wp = self.waypoints[wi]
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
        """誘餌：全速衝向目標充當肉盾——不閃避，讓傳統防空把彈藥耗在誘餌上，
        掩護真群突防。用 max_speed 超越主群、形成視覺上清晰的前導犧牲層。"""
        cfg = self.cfg
        v_des = self.target - d.pos
        v_des = v_des / (np.linalg.norm(v_des) + 1e-9) * cfg.max_speed
        a = (v_des - d.vel) * 1.5
        return a  # 不閃避，讓攔截彈鎖定

    def _sead_control(self, d: Drone, t, missiles):
        """反輻射(SEAD)機：全速直撲防空（目標），進近距即壓制其火力、撕開雷達破口。
        衝在主力前方、可拋棄；正面承受攔截為後方開路（故規避減半、更敢衝）。"""
        to_t = self.target - d.pos
        u = to_t / (np.linalg.norm(to_t) + 1e-9)
        v_des = u * self.cfg.max_speed              # 全速直取防空、不繞
        a = (v_des - d.vel) * 1.5
        return a + self._evade_accel(d, t, missiles) * 0.5

    # ------------------------------- 失效應變：仿生 / 多組 / 集群分裂 / 終端（要點2）
    def _is_multi(self):
        return self.n_groups > 1 or self._fissioned

    def _boids_control(self, d, t, missiles):
        """策略三 仿生湧現(Boids)：無領機，靠斥力/對齊/聚合＋向心遷移湧現群體行為。
        人人是領機、人人也不是→打掉任何一架都不影響群體（AI 斬首在此失效）。"""
        cfg = self.cfg
        nbrs = [o for o in self.alive_drones()
                if o.id != d.id and np.linalg.norm(o.pos - d.pos) < cfg.comm_range]
        nbrs.sort(key=lambda o: np.linalg.norm(o.pos - d.pos))
        nbrs = nbrs[:6]                                   # 只看最近 6 個鄰居
        v_des = np.zeros(3)
        if nbrs:
            cen = np.mean([o.pos for o in nbrs], axis=0)
            v_align = np.mean([o.vel for o in nbrs], axis=0)
            v_des += 0.6 * (cen - d.pos)                  # 聚合 Cohesion
            v_des += 0.5 * (v_align - d.vel)              # 對齊 Alignment（斥力另由分離力處理）
        to_t = self.target - d.pos                        # 向心遷移：共同目標
        v_des += to_t / (np.linalg.norm(to_t) + 1e-9) * cfg.cruise_speed
        nn = np.linalg.norm(v_des)
        if nn > cfg.cruise_speed:
            v_des = v_des / nn * cfg.cruise_speed
        return (v_des - d.vel) * 1.0 + self._evade_accel(d, t, missiles)

    def _update_terminal(self, t):
        """策略四 終端自殺：機群質心進目標近域→ToT 同時彈著＋末端混沌規避。"""
        if self.terminal:
            return
        alive = self.alive_drones()
        if alive and np.linalg.norm(np.mean([d.pos for d in alive], axis=0)
                                    - self.target) < self.cfg.terminal_dist:
            self.terminal = True
            self.events.append((t, "🔻 進入終端自殺階段：同時彈著(ToT)＋末端混沌規避"))

    def get_group_leader(self, gid):
        lid = self.group_leader.get(gid)
        if lid is not None and self.drones[lid].alive \
                and self.drones[lid].role == ROLE_LEADER:
            return self.drones[lid]
        return None

    def _multi_control(self, d, t, missiles):
        """多組並進／集群分裂：各機跟隨『本組領機』，組領機各自導航突擊。"""
        cfg = self.cfg
        gl = self.get_group_leader(d.group_id)
        if gl is None:
            return self._boids_control(d, t, missiles)     # 本組無領機→退化仿生
        if d.id == gl.id:
            return self._leader_control(d, t, missiles, gid=d.group_id)
        h = gl.heading_xy()
        back = np.array([-h[0], -h[1], 0.0]) * cfg.spacing * 1.1
        side = np.array([-h[1], h[0], 0.0]) * ((d.id % 5 - 2) * cfg.spacing * 0.6)
        target = gl.pos + back + side
        a = cfg.kp * (target - d.pos) + cfg.kd * (gl.vel - d.vel)
        return a + self._evade_accel(d, t, missiles)

    def _make_group(self, t, gid, members, reason):
        """把 members 設為獨立一組：健康度選領機、提拔一中繼、繼承當前航點進度。"""
        if not members:
            return
        cen = self._centrality_map()
        for d in members:
            d.group_id = gid
            d.role = ROLE_FOLLOWER
            d.has_mission = False
        lead = max(members, key=lambda d: self._snode_score(d, cen))
        lead.role = ROLE_LEADER
        lead.has_mission = True
        self.group_leader[gid] = lead.id
        self.wp_i_of[gid] = getattr(self, "wp_i", 0)
        rest = [d for d in members if d.id != lead.id]
        if rest:                                           # 提拔最健康從機為組內中繼
            r = max(rest, key=lambda d: self._snode_score(d, cen))
            r.role = ROLE_RELAY
            r.has_mission = True

    def _fission(self, t):
        """情境二·1：大群核心雙失→集群分裂為 2 組，各自健康度選領機、互為犄角續突。"""
        alive = self.alive_drones()
        P = np.array([d.pos[:2] for d in alive])
        c0 = P[int(np.argmax(np.linalg.norm(P - P.mean(0), axis=1)))]
        c1 = P[int(np.argmax(np.linalg.norm(P - c0, axis=1)))]
        centers = np.array([c0, c1], float)
        lab = np.zeros(len(P), int)
        for _ in range(8):
            lab = np.argmin(np.linalg.norm(P[:, None, :] - centers[None, :, :],
                                           axis=2), axis=1)
            for j in range(2):
                if (lab == j).any():
                    centers[j] = P[lab == j].mean(0)
        self.group_leader, self.wp_i_of = {}, {}
        for gid in (0, 1):
            self._make_group(t, gid, [alive[i] for i in range(len(alive))
                                      if lab[i] == gid], "分裂")
        self._fissioned = True
        self.leader_id = self.group_leader.get(0, self.leader_id)
        self.events.append(
            (t, f"✂️ 集群分裂：{len(alive)} 架裂為 2 組，各組健康度選領機、互為犄角續突"))

    def _init_groups(self):
        """情境一：開場即分 n_groups 個獨立指揮域（依出發橫向位置分帶）。"""
        alive = self.alive_drones()
        order = np.argsort([d.pos[1] for d in alive])
        self.group_leader, self.wp_i_of = {}, {}
        for gid, idx in enumerate(np.array_split(order, self.n_groups)):
            self._make_group(0.0, gid, [alive[i] for i in idx], "多組")
        self.leader_id = self.group_leader.get(0, 0)

    def _handle_failures_multi(self, t):
        """多組失效處理：各組領機亡→健康度重選；組過小/指揮全失→併入最近組(跨組自癒)。"""
        for gid in sorted(self.group_leader.keys()):
            members = [d for d in self.alive_drones() if d.group_id == gid]
            if not members:
                self.group_leader.pop(gid, None)
                self.wp_i_of.pop(gid, None)
                continue
            if self.get_group_leader(gid) is None:
                if len(members) <= 2 and len(self.group_leader) > 1:
                    others = [g for g in self.group_leader if g != gid]
                    mc = np.mean([d.pos for d in members], axis=0)
                    best = min(others, key=lambda g: np.linalg.norm(
                        self.drones[self.group_leader[g]].pos - mc))
                    for d in members:
                        d.group_id = best
                    self.group_leader.pop(gid, None)
                    self.wp_i_of.pop(gid, None)
                    self.events.append(
                        (t, f"🌐 第{gid}組指揮全失→孤兒併入第{best}組（跨組 mesh 自癒）"))
                else:
                    self._make_group(t, gid, members, "重選")
                    self.events.append(
                        (t, f"👑 第{gid}組領機失效→健康度重選新領機"))

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
        swing = np.sign(s)
        if self.terminal:        # 策略四 末端混沌：高頻不規則擺動→防空前置量算不準
            swing = float(np.clip(swing + 0.7 * np.sin(7.3 * t + 3.1 * d.evade_phase)
                                  * np.cos(3.7 * t + d.id), -1.4, 1.4))
        return lateral * cfg.evade_accel * eff * swing \
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
        if self.bionic:
            target = max(conn, 0.75)           # 仿生：去中心化，協調不依賴任何單機
        elif self._is_multi():
            target = max(conn, 0.6)            # 多組：各組獨立，整體協調不全崩
        elif self.fiber:
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
        # 預警大腦：有領機、或仿生/多組(對等網狀/各組獨立)皆維持全網預警
        self._leader_ok = (leader is not None) or self.bionic or self._is_multi()
        self._cf = self._converge_frac(leader)  # 多軸向心收攏係數（1→0）
        if leader is not None:                  # 一字蛇形：緩存領機航跡供後機沿跡尾隨
            self.leader_trail.append(leader.pos.copy())
            if len(self.leader_trail) > 600:
                self.leader_trail.pop(0)
        anchor = self._anchor_drone(leader)     # 空間領頭(領機或誘餌)
        self._anchor_live = anchor.id if anchor is not None else self.leader_id
        sep = self._separation_accel()
        self._multi = (self.n_groups > 1) or self._fissioned   # 多組/分裂模式
        self._update_terminal(t)                # 終端自殺階段偵測(ToT+混沌)

        for d in self.alive_drones():
            # ★ S_node 電量隨飛行遞減；指揮節點(領機/中繼)負載重→耗更快(健康度會更替)
            d.soc = max(0.0, d.soc - cfg.soc_decay *
                        (2.5 if d.role != ROLE_FOLLOWER else 1.0))
            if self.bionic:
                a = self._boids_control(d, t, missiles)        # 策略三：仿生湧現
            elif self.lost_mode:
                a = self._lost_control(d, t, missiles)
            elif self._multi:
                a = self._multi_control(d, t, missiles)        # 多組/集群分裂
            elif d.id == self._anchor_live:
                a = self._leader_control(d, t, missiles)       # 空間領頭導航
            elif d.is_sead and not self.lost_mode:
                a = self._sead_control(d, t, missiles)         # 反輻射機：衝防空壓制
            elif d.is_decoy:
                a = self._decoy_control(d, t, missiles)        # 其餘誘餌：前方佯動
            else:
                a = self._follower_control(d, t, missiles,
                                           leader is not None)  # 含沉默真領機
            a = a + sep[d.id]
            d.step(a, self.dt, cfg.max_accel, cfg.max_speed)

            # 突防判定（誘餌不攜戰鬥部，不計突防）
            if not self.lost_mode and \
                    not getattr(d, "is_decoy", False) and \
                    np.linalg.norm(d.pos - self.target) < cfg.strike_radius:
                d.alive = False
                d.succeeded = True
                self.n_through += 1
                self.events.append(
                    (t, f"🎯 {ROLE_NAMES[d.role]} #{d.id} 突防成功！"))
                if d.role == ROLE_LEADER:
                    self.leader_death_t = t   # 領機衝過去也算失聯，須遞補

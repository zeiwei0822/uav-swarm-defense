# -*- coding: utf-8 -*-
"""
無人機個體 — 二階積分動力學模型
state: 位置 pos(3,)、速度 vel(3,)；控制輸入為加速度指令（受 max_accel 限制）
"""
import numpy as np
from config import ROLE_FOLLOWER, ROLE_RELAY, ROLE_LEADER


class Drone:
    def __init__(self, drone_id: int, pos, vel, role: int = ROLE_FOLLOWER):
        self.id = drone_id
        self.pos = np.asarray(pos, dtype=float).copy()
        self.vel = np.asarray(vel, dtype=float).copy()
        self.role = role
        self.alive = True
        self.succeeded = False        # 已抵達目標（突防成功）
        self.is_decoy = False         # 誘餌：衝最前方扮假領機，誘騙 AI 識別/火力
        self.is_sead = False          # 反輻射(SEAD)機：衝防空壓制火力、撕開雷達破口

        # 通訊 / 任務狀態
        self.connected = True         # 本步是否收得到領機資訊
        self.has_mission = False      # 是否持有完整任務航線（領機/中繼機才有）
        self.last_leader_pos = None   # 最後收到的領機位置（斷線時推算用）
        self.last_leader_vel = None
        self.last_heard = 0.0         # 最後一次收到領機心跳的時間
        self.mission_sync_t = None    # 任務資料同步完成時刻（新提拔中繼機用）
        self.last_form_heading = None # 最後收到的陣型框架航向

        # 迴避機動相位（每架不同，避免全體同步蛇行）
        # 由 Swarm 以種子化 rng 覆寫，確保實驗可重現
        self.evade_phase = 0.0

        # ★ S_node 健康度（要點2「健康度自主篩選機制」；由 Swarm 種子化設定）
        #   電量隨飛行/規避遞減；算力/感測器為個體差異。選舉時加權成 S_node。
        self.soc = 1.0            # 剩餘電量 / 航時 (0~1)
        self.computing = 1.0      # 機載 AI 算力餘裕 (0~1)
        self.sensor = 1.0         # 感測器完好度 (GPS/IMU/光學) (0~1)
        self.group_id = 0         # 所屬子群（多組並進 / 集群分裂用）

    def step(self, accel_cmd, dt: float, max_accel: float, max_speed: float):
        """套用加速度指令並前進一步"""
        a = np.asarray(accel_cmd, dtype=float)
        norm = np.linalg.norm(a)
        if norm > max_accel:
            a = a * (max_accel / norm)
        self.vel = self.vel + a * dt
        spd = np.linalg.norm(self.vel)
        if spd > max_speed:
            self.vel = self.vel * (max_speed / spd)
        self.pos = self.pos + self.vel * dt
        if self.pos[2] < 2.0:          # 不准撞地
            self.pos[2] = 2.0
            if self.vel[2] < 0:
                self.vel[2] = 0.0

    @property
    def c2_emission(self):
        """★ C2 射頻發射強度 (0~1)：防方 SIGINT/ESM 可量測的『物理訊號』，
        與 GNN『看怎麼飛』完全獨立。指揮機要對全網廣播命令→發射最強(1.0)；
        中繼機轉發→中等(0.5)；從機只接收、不發真 C2→最弱(0.1)。
        ★誘餌的死穴★：誘餌是『飛得像領機的從機』(role=FOLLOWER)，運動上能騙過
        GNN，但發不出真 C2 → 此值仍是 0.1 → SIGINT 不會把它確認成領機。
        遞補時某中繼升任領機→role 變 LEADER→此值自動跳 1.0（新領機開始廣播）。"""
        if self.role == ROLE_LEADER:
            return 1.0
        if self.role == ROLE_RELAY:
            return 0.5
        return 0.1

    @property
    def speed(self):
        return float(np.linalg.norm(self.vel))

    def heading_xy(self):
        """水平航向單位向量（速度太小時回傳 +x）"""
        v = self.vel[:2]
        n = np.linalg.norm(v)
        if n < 1e-6:
            return np.array([1.0, 0.0])
        return v / n

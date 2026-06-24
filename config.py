# -*- coding: utf-8 -*-
"""
全域設定檔 — 無人機機群攻防模擬
=================================
所有單位：距離 m、時間 s、速度 m/s、加速度 m/s^2
座標系：x/y 水平面，z 高度（地面 z=0）

四大要點對應模組：
  1. 機群陣型與飛行路徑分析   -> core/formations.py, analyze.py
  2. 領機/中繼機失效處理       -> core/swarm.py
  3. AI 機群軌跡預測           -> ai/trajectory.py (Kalman vs LSTM)
  4. AI 找出領機/中繼機        -> ai/identify.py  (規則 vs RF/MLP)
"""
from dataclasses import dataclass, field


# ---------------------------------------------------------------- 模擬基本
@dataclass
class SimConfig:
    dt: float = 0.1            # 模擬步長 (s)，10 Hz
    t_max: float = 260.0       # 最長模擬時間 (s)
    seed: int = 42             # 隨機種子


# ---------------------------------------------------------------- 攻方機群
@dataclass
class SwarmConfig:
    n_drones: int = 21         # 機群總數（含領機與中繼機）
    n_relays: int = 3          # 中繼機數量
    formation: str = "vee"     # 初始陣型: vee / wedge / column / grid / ring
    spacing: float = 38.0      # 陣型基準間距 (m)

    # ★ 多軸夾擊戰術：機群分 n_axes 股縱隊（領機在中央股），出發橫向分開、
    #   接近目標時逐漸向心收攏夾擊。1=單股(舊行為)。領機仍是唯一總指揮。
    n_axes: int = 3
    axis_spread: float = 170.0  # 出發時兩翼股相對中央的橫向偏移 (m，<comm_range 才連得上)

    # ★ 誘餌戰術（攻方反制 AI 識別）：n_decoys 架從機衝最前方扮「假領機」，
    #   引 AI 把火力打在誘餌上、保護真領機。0=關閉。
    n_decoys: int = 0
    decoy_lead: float = 220.0   # 誘餌衝在機群質心前方多遠 (m)

    cruise_speed: float = 18.0  # 巡航速度
    max_speed: float = 25.0     # 速度上限（勿改：LSTM 正規化 scale 綁此值）
    max_accel: float = 11.0     # 加速度上限（高=閃避更靈活，打得出拉鋸）

    # 編隊控制 PD 增益
    kp: float = 0.55
    kd: float = 1.55
    form_turn_rate: float = 6.0  # 陣型框架最大旋轉速率 (deg/s)
                                 # 領機急轉時陣型「慢慢轉」，避免外側槽位掃掠過快
    sep_dist: float = 14.0      # 避碰距離（小於此距離產生分離力）
    sep_gain: float = 9.0

    # 通訊
    comm_range: float = 350.0       # 通訊半徑（領機/中繼機廣播範圍）
    heartbeat_timeout: float = 1.2  # 失去領機訊號多久後判定失效 (s)
    election_delay: float = 0.6     # 判定失效後選出新領機所需時間 (s)
    mission_sync_time: float = 24.0 # 新中繼機同步任務資料所需時間 (s)
                                    # → 防方若能在同步完成前連續擊殺持任務節點，
                                    #   即可達成「斬首」讓機群迷失（指揮能力無法再生）

    # 任務
    spawn_distance: float = 3000.0  # 出發點距離目標 (m)
    spawn_alt: float = 120.0        # 飛行高度
    fixed_bearing: float | None = 0.0  # 出發方位(rad)：0=自西向東（對岸跨海峽攻台）
                                       # 設 None 則隨機（datagen 訓練用，增加多樣性）
    strike_radius: float = 100.0    # 距目標多近視為「突防成功」
    n_waypoints: int = 2            # 中途航點數（會產生轉彎，利於識別分析）
    waypoint_lateral: float = 700.0 # 中途航點側向偏移幅度

    # 迴避機動（偵測到來襲飛彈時）—— 拉鋸感的關鍵：早反應、猛蛇行、甩得掉一部分
    evade_accel: float = 11.0       # 迴避側向加速度（猛=甩得掉轉彎較差的飛彈）
    evade_period: float = 1.6       # 蛇行週期 (s)（短=急促難預測）

    # ★ 領機=威脅預警大腦：在線時全網共享領機大偵測範圍，提早規避；
    #   領機死/失聯→各機只能自己短視看到才閃→被擊落率暴增（斬首的真實代價）
    warn_radius_leader: float = 460.0   # 領機在線：全網預警範圍
    warn_radius_self: float = 110.0     # 失去領機/失聯：自身短視範圍（反應極晚）

    # ★ 領機=協調/火力分配：協調係數 C(0~1)；領機在→C高、規避有效、扇形分散逼近；
    #   領機死→C驟降、各自為政擠成一團、幾乎閃不掉→防方收割；遞補後緩升
    coord_rebuild_time: float = 11.0    # 領機遞補後重建協調所需時間 (s)
    evade_min_eff: float = 0.15         # C 最低時規避效能比例（C=0→0.15倍≈挨打）
    strike_spread: float = 220.0        # 高協調時終端扇形分散幅度 (m)


# ---------------------------------------------------------------- 防方
@dataclass
class DefenseConfig:
    radar_sigma: float = 8.0        # 雷達量測噪聲（每軸標準差 m）
    radar_range: float = 3500.0     # 雷達涵蓋半徑
    engage_range: float = 1500.0    # 飛彈接戰半徑
    n_launchers: int = 2            # 發射器數量
    reload_time: float = 5.5        # 單發射器再裝填 (s)（密=交戰更密集）
    n_missiles: int = 18            # 彈藥總數（補償命中率下降，仍不足以全殲）

    missile_speed: float = 82.0     # 攔截彈速度（略降，給無人機反應時間、看得到追逐）
    missile_accel: float = 20.0     # 攔截彈最大側向加速度（降=蛇行甩得掉一部分）
    missile_life: float = 30.0      # 攔截彈最長飛行時間
    kill_radius: float = 13.0       # 近炸引信半徑
    p_kill: float = 0.58            # 進入引信半徑後的擊殺機率（降=驚險、常擦過）

    policy: str = "ai"              # 目標選擇策略: ai / nearest / random
    mode: str = "ai"               # 防方模式: trad（傳統）/ ai（供視覺化切換旁白）
    ident_conf_fire: float = 0.40   # AI 策略：識別信心超過此值才優先打領機
    ident_interval: float = 0.5     # 每隔多久重算一次識別 (s)


# ---------------------------------------------------------------- AI
@dataclass
class AIConfig:
    # 軌跡預測
    hist_len: int = 20          # 預測模型輸入長度（步）= 2.0 s
    pred_horizon: int = 25      # 預測未來長度（步）= 2.5 s
    lstm_hidden: int = 96
    lstm_layers: int = 2

    # 領機/中繼機識別
    feat_window: int = 60       # 特徵計算視窗（步）= 6.0 s
    max_lag: int = 15           # 領先-跟隨互相關最大延遲（步）
    ema_alpha: float = 0.45     # 識別機率指數移動平均係數（高=更快鎖定新領機）

    # 模型檔
    model_dir: str = "models"
    lstm_path: str = "models/lstm_traj.pt"
    rf_path: str = "models/rf_identify.joblib"
    mlp_path: str = "models/mlp_identify.pt"
    scaler_path: str = "models/feat_scaler.npz"


# ---------------------------------------------------------------- 彙總
@dataclass
class Config:
    sim: SimConfig = field(default_factory=SimConfig)
    swarm: SwarmConfig = field(default_factory=SwarmConfig)
    defense: DefenseConfig = field(default_factory=DefenseConfig)
    ai: AIConfig = field(default_factory=AIConfig)


# 角色代碼（全專案共用）
ROLE_FOLLOWER = 0   # 從機
ROLE_RELAY = 1      # 中繼機
ROLE_LEADER = 2     # 領機
ROLE_NAMES = {ROLE_FOLLOWER: "從機", ROLE_RELAY: "中繼機", ROLE_LEADER: "領機"}

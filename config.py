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
    n_drones: int = 24         # 機群總數（含領機與中繼機）
    n_relays: int = 3          # 中繼機數量
    # 初始陣型（兩流派，見 core/formations.py）：
    #   無線大群: echelon / arrowhead / encircle
    #   光纖精準: snake / vstack / relay_island / fan
    formation: str = "arrowhead"
    spacing: float = 38.0      # 陣型基準間距 (m)

    # ★ 多軸夾擊戰術：機群分 n_axes 股縱隊（領機在中央股），出發橫向分開、
    #   接近目標時逐漸向心收攏夾擊。1=單股。新陣型幾何已自帶展開，預設 1，
    #   僅 encircle（向心多弧包圍）會調高以呈現多方位向心。
    n_axes: int = 1
    axis_spread: float = 170.0  # 出發時兩翼股相對中央的橫向偏移 (m，<comm_range 才連得上)

    # ★ 誘餌戰術（攻方反制 AI 識別）：n_decoys 架從機衝最前方扮「假領機」，
    #   引 AI 把火力打在誘餌上、保護真領機。0=關閉。
    n_decoys: int = 0
    decoy_lead: float = 220.0   # 誘餌衝在機群質心前方多遠 (m)

    # ★ 反輻射(SEAD)戰術（重疊錐形 arrowhead 的尖端）：n_sead 架可拋棄反輻射機衝最前方，
    #   進防空近距即『壓制其火力』(撕開雷達破口)，掩護主力鑽過缺口突防。0=關。
    n_sead: int = 0

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

    # ★★ 要點2：領機/中繼機失效處理策略（依《集群戰術應急》報告四策略）
    #   chain  = 階級繼承鏈：預設繼任清單(編號順位)，反應快、開銷低、但僵化
    #   health = 健康度自主篩選：分散式選舉，S_node=電量0.4+中心性0.3+算力0.2+感測0.1
    #   bionic = 仿生湧現：完全去中心化(Boids)，無固定領機 → 免單點故障(AI斬首失效)
    fail_strategy: str = "chain"
    snode_w: tuple = (0.40, 0.30, 0.20, 0.10)   # S_node 權重(電量/中心性/算力/感測)
    n_groups: int = 1               # 多組並進(情境一)；>1 分 N 個獨立指揮域、可跨組自癒
    fission_min: int = 16           # 領機+中繼全失：機數≥此→集群分裂2組各選；否則→仿生退化
    contract_factor: float = 0.5    # 向心收縮：中繼失→陣型間距×此(縮短到 LOS 直控)
    soc_decay: float = 0.0008       # 每步電量遞減(巡航)
    soc_evade_cost: float = 0.004   # 規避額外耗電(每步,規避中)
    terminal_dist: float = 600.0    # 距目標<此→終端自殺階段(ToT同時彈著+混沌規避)

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
    coord_rebuild_time: float = 22.0    # 領機遞補後重建協調所需時間 (s)
    evade_min_eff: float = 0.04         # C 最低時規避效能比例（C=0→0.04倍≈幾乎無閃避）
    strike_spread: float = 220.0        # 高協調時終端扇形分散幅度 (m)
    # ★ 斬首→癱瘓：見 core/swarm.py —— 繼承鏈(僵化)不補充中繼，原始指揮鏈被逐一斬殺
    #   耗盡後即迷失癱瘓（健康度/光纖則動態補位、抗斬首）。配合防方分層火力(defense.py)。


# ---------------------------------------------------------------- 防方
@dataclass
class DefenseConfig:
    radar_sigma: float = 8.0        # 雷達量測噪聲（每軸標準差 m）
    radar_range: float = 3500.0     # 雷達涵蓋半徑
    engage_range: float = 2200.0    # 飛彈接戰半徑（拉大→戰鬥提早約30s開打、獵殺迴圈攤開）
                                    # ★ 必須搭配夠快的飛彈(下方 missile_speed)才打得到，
                                    #   否則飛彈在抵達前就過期(life)→突防暴增。
    n_launchers: int = 2            # 發射器數量
    reload_time: float = 5.5        # 單發射器再裝填 (s)（密=交戰更密集）
    n_missiles: int = 18            # 彈藥總數（補償命中率下降，仍不足以全殲）

    missile_speed: float = 110.0    # 攔截彈速度（配合 engage_range 2200 才搆得到；
                                    #   仍慢到看得到追逐。調回 82 則須把 engage_range 收回 ~1500）
    missile_accel: float = 20.0     # 攔截彈最大側向加速度（降=蛇行甩得掉一部分）
    missile_life: float = 30.0      # 攔截彈最長飛行時間
    kill_radius: float = 13.0       # 近炸引信半徑
    p_kill: float = 0.58            # 進入引信半徑後的擊殺機率（降=驚險、常擦過）

    policy: str = "ai"              # 目標選擇策略: ai / nearest / random
    mode: str = "ai"               # 防方模式: trad（傳統）/ ai（供視覺化切換旁白）
    # ★ SEAD 壓制：反輻射機(swarm.is_sead)進此距離→防空火力遭壓制(無法發射)一段時間，
    #   形成『雷達破口』讓主力鑽過。撕破口戰術的核心機制。
    sead_range: float = 1300.0      # 反輻射機進此距離(m)即壓制防空（須夠大,否則SEAD先被打掉）
    sead_suppress_t: float = 9.0    # 每次壓制持續 (s)
    ident_conf_fire: float = 0.40   # AI 策略：識別信心超過此值才優先打領機
    ident_interval: float = 0.5     # 每隔多久重算一次識別 (s)

    # ★ 要點4：SIGINT/ESM 射頻確認 —— 與 GNN 獨立的『第二感測器』（不是重複的識別器）
    #   GNN 看『怎麼飛』(運動)，SIGINT 看『發什麼』(C2 射頻發射量 drone.c2_emission)。
    #   目標進接戰 envelope 後才開始截獲其射頻；指揮機廣播最多→最先被確認鎖定；
    #   確認滿(=1)才允許斬首。兩感測器都點頭才開火 → 誘餌飛得像領機能騙 GNN，但發不出
    #   真 C2 → SIGINT 不確認它 → AI 不上當（要點4 的反誘餌價值）。僅 AI 防方啟用。
    decode_enable: bool = True      # 在接戰 envelope 內才開始 SIGINT 截獲確認
    decode_full_t: float = 0.3      # 射頻最強(emission=1.0)截獲到滿所需(s)；確認值上限=該機發射量
    decode_confirm: float = 0.30    # ★SIGINT 確認門檻★：decode≥此才算「確認為指揮鏈節點、可斬首」。
                                    #   領機(上限1.0)、中繼(0.5)會越過；從機/誘餌(上限0.1)永遠到不了
                                    #   →無論飛得多像領機，發不出真 C2 就不會被斬首（反誘餌的關鍵）


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
    ema_alpha: float = 0.65     # 識別機率指數移動平均係數（高=更快鎖定新領機）

    # 模型檔
    model_dir: str = "models"
    lstm_path: str        = "models/lstm_traj.pt"
    mlp_traj_path: str    = "models/mlp_traj.pt"
    transformer_path: str = "models/transformer_traj.pt"
    rf_path: str = "models/rf_identify.joblib"
    gbm_path: str = "models/gbm_identify.joblib"   # 梯度提升樹（benchmark 對照）
    mlp_path: str = "models/mlp_identify.pt"
    gnn_path: str = "models/gnn_identify.pt"       # 圖神經網路（要點4 主力，學圖中心性）
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

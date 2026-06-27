# -*- coding: utf-8 -*-
"""
要點 3：AI 機群軌跡預測
========================
兩種方法對照（專題報告核心比較）：
  1. 基準法：卡爾曼濾波 + 等速 (CV) 模型外推 —— 傳統追蹤標準作法
  2. AI 法：LSTM 序列模型 —— 從大量模擬資料學習機動模式（轉彎、蛇行迴避）

評估指標（軌跡預測領域標準）：
  ADE = 預測期間平均位移誤差、FDE = 預測終點位移誤差
"""
import os
import numpy as np
import torch
import torch.nn as nn


# ================================================================ 卡爾曼濾波（基準法）
class KalmanCV:
    """等速模型卡爾曼濾波器，狀態 = [x y z vx vy vz]
    防方雷達用它平滑量測並外推未來軌跡。"""

    def __init__(self, dt: float, sigma_meas: float = 8.0, sigma_acc: float = 3.5):
        self.dt = dt
        I3 = np.eye(3)
        self.F = np.block([[I3, dt * I3], [np.zeros((3, 3)), I3]])
        self.H = np.hstack([I3, np.zeros((3, 3))])
        # 程序噪聲：白噪聲加速度模型
        q11 = dt ** 4 / 4 * I3
        q12 = dt ** 3 / 2 * I3
        q22 = dt ** 2 * I3
        self.Q = np.block([[q11, q12], [q12, q22]]) * sigma_acc ** 2
        self.R = np.eye(3) * sigma_meas ** 2
        self.x = None
        self.P = None

    def init(self, z0):
        self.x = np.concatenate([z0, np.zeros(3)])
        self.P = np.diag([self.R[0, 0]] * 3 + [25.0] * 3)

    def update(self, z):
        """一步預測 + 量測更新"""
        if self.x is None:
            self.init(np.asarray(z, float))
            return
        # predict
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        # update
        y = np.asarray(z, float) - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(6) - K @ self.H) @ self.P

    @property
    def pos(self):
        return self.x[:3].copy()

    @property
    def vel(self):
        return self.x[3:].copy()

    def predict_ahead(self, n_steps: int) -> np.ndarray:
        """CV 外推未來 n_steps 位置，回傳 (n_steps, 3)"""
        out = np.empty((n_steps, 3))
        x = self.x.copy()
        for k in range(n_steps):
            x = self.F @ x
            out[k] = x[:3]
        return out


def kalman_predict_batch(meas_hist: np.ndarray, horizon: int, dt: float,
                         sigma_meas: float = 8.0) -> np.ndarray:
    """對一批量測歷史 (B, T, 3) 各自跑 KF 再外推，回傳 (B, horizon, 3)。
    用於離線評估（與 LSTM 同條件比較）。"""
    B = meas_hist.shape[0]
    out = np.empty((B, horizon, 3))
    for b in range(B):
        kf = KalmanCV(dt, sigma_meas=sigma_meas)
        for z in meas_hist[b]:
            kf.update(z)
        out[b] = kf.predict_ahead(horizon)
    return out


# ================================================================ LSTM（AI 法）
class TrajLSTM(nn.Module):
    """編碼器 LSTM：輸入過去位移序列 → 一次輸出未來 horizon 步位移"""

    def __init__(self, horizon: int, hidden: int = 96, layers: int = 2):
        super().__init__()
        self.horizon = horizon
        self.lstm = nn.LSTM(input_size=3, hidden_size=hidden,
                            num_layers=layers, batch_first=True, dropout=0.1)
        self.head = nn.Sequential(
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, horizon * 3),
        )

    def forward(self, x):                  # x: (B, T-1, 3) 正規化位移
        out, _ = self.lstm(x)
        h = out[:, -1, :]                  # 取最後時間步
        y = self.head(h)
        return y.view(-1, self.horizon, 3)


class LSTMPredictor:
    """包裝訓練好的 TrajLSTM：吃絕對位置歷史，輸出絕對位置預測。
    前處理：位移正規化 + 航向旋轉對齊（旋轉不變性 → 大幅提升泛化）"""

    def __init__(self, model_path: str, dt: float, max_speed: float = 25.0,
                 device: str = None):
        self.dt = dt
        self.scale = max_speed * dt        # 一步最大位移，用於正規化
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        ckpt = torch.load(model_path, map_location=self.device, weights_only=True)
        self.horizon = ckpt["horizon"]
        self.model = TrajLSTM(self.horizon, ckpt["hidden"], ckpt["layers"])
        self.model.load_state_dict(ckpt["state_dict"])
        self.model.to(self.device).eval()

    @staticmethod
    def _heading_rot(deltas: np.ndarray) -> np.ndarray:
        """由最近幾步位移估計航向，回傳世界→機體 2D 旋轉矩陣 (B,2,2)"""
        v = deltas[:, -5:, :2].mean(axis=1)          # (B,2)
        n = np.linalg.norm(v, axis=1, keepdims=True)
        n[n < 1e-8] = 1.0
        c = (v[:, 0:1] / n).ravel()
        s = (v[:, 1:2] / n).ravel()
        R = np.zeros((len(v), 2, 2))
        R[:, 0, 0] = c
        R[:, 0, 1] = s      # row0 = [c, s]
        R[:, 1, 0] = -s
        R[:, 1, 1] = c      # row1 = [-s, c]  （世界→機體）
        return R

    def predict(self, pos_hist: np.ndarray) -> np.ndarray:
        """pos_hist: (B, T, 3) 絕對位置（含雷達噪聲）→ (B, horizon, 3) 絕對位置預測"""
        single = pos_hist.ndim == 2
        if single:
            pos_hist = pos_hist[None]
        deltas = np.diff(pos_hist, axis=1)                 # (B, T-1, 3)
        R = self._heading_rot(deltas)                      # (B,2,2)
        d_body = deltas.copy()
        d_body[..., :2] = np.einsum("bij,btj->bti", R, deltas[..., :2])
        x = torch.tensor(d_body / self.scale, dtype=torch.float32,
                         device=self.device)
        with torch.no_grad():
            y = self.model(x).cpu().numpy() * self.scale   # (B,H,3) 機體位移
        y_world = y.copy()
        Rinv = np.transpose(R, (0, 2, 1))                  # 機體→世界
        y_world[..., :2] = np.einsum("bij,bhj->bhi", Rinv, y[..., :2])
        pred = pos_hist[:, -1:, :] + np.cumsum(y_world, axis=1)
        return pred[0] if single else pred


# ================================================================ MLP（AI 法 baseline）
class TrajMLP(nn.Module):
    """扁平化 MLP：把過去位移序列拉直 → 一次輸出未來 horizon 步位移"""

    def __init__(self, hist_len: int, horizon: int, hidden: int = 256):
        super().__init__()
        self.horizon = horizon
        self.hist_len = hist_len
        self.net = nn.Sequential(
            nn.Linear((hist_len - 1) * 3, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, horizon * 3),
        )

    def forward(self, x):       # x: (B, T-1, 3)
        B = x.shape[0]
        return self.net(x.reshape(B, -1)).view(B, self.horizon, 3)


class MLPTrajPredictor:
    """推論包裝：吃絕對位置歷史 → 輸出絕對位置預測（前處理與 LSTM 相同）"""

    def __init__(self, model_path: str, dt: float, max_speed: float = 25.0):
        self.dt = dt
        self.scale = max_speed * dt
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        ckpt = torch.load(model_path, map_location=device, weights_only=True)
        self.horizon  = ckpt["horizon"]
        self.hist_len = ckpt["hist_len"]
        self.model = TrajMLP(self.hist_len, self.horizon, ckpt["hidden"])
        self.model.load_state_dict(ckpt["state_dict"])
        self.model.to(device).eval()

    def predict(self, pos_hist: np.ndarray) -> np.ndarray:
        single = pos_hist.ndim == 2
        if single:
            pos_hist = pos_hist[None]
        deltas = np.diff(pos_hist, axis=1)
        R = LSTMPredictor._heading_rot(deltas)
        d_body = deltas.copy()
        d_body[..., :2] = np.einsum("bij,btj->bti", R, deltas[..., :2])
        x = torch.tensor(d_body / self.scale, dtype=torch.float32, device=self.device)
        with torch.no_grad():
            y = self.model(x).cpu().numpy() * self.scale
        y_world = y.copy()
        Rinv = np.transpose(R, (0, 2, 1))
        y_world[..., :2] = np.einsum("bij,bhj->bhi", Rinv, y[..., :2])
        pred = pos_hist[:, -1:, :] + np.cumsum(y_world, axis=1)
        return pred[0] if single else pred


# ================================================================ Transformer（AI 法）
class TrajTransformer(nn.Module):
    """Transformer 編碼器：對時間步做自注意力 → 輸出未來 horizon 步位移"""

    def __init__(self, horizon: int, d_model: int = 64, nhead: int = 4,
                 num_layers: int = 2):
        super().__init__()
        self.horizon = horizon
        self.input_proj = nn.Linear(3, d_model)
        enc_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead,
            dim_feedforward=256, batch_first=True, dropout=0.1)
        self.encoder = nn.TransformerEncoder(enc_layer, num_layers=num_layers)
        self.head = nn.Sequential(
            nn.Linear(d_model, 128), nn.ReLU(),
            nn.Linear(128, horizon * 3),
        )

    def forward(self, x):       # x: (B, T-1, 3)
        h = self.encoder(self.input_proj(x))
        return self.head(h[:, -1, :]).view(-1, self.horizon, 3)


class TransformerPredictor:
    """推論包裝（前處理與 LSTM 相同，方便公平比較）"""

    def __init__(self, model_path: str, dt: float, max_speed: float = 25.0):
        self.dt = dt
        self.scale = max_speed * dt
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        ckpt = torch.load(model_path, map_location=device, weights_only=True)
        self.horizon = ckpt["horizon"]
        self.model = TrajTransformer(
            ckpt["horizon"], ckpt["d_model"], ckpt["nhead"], ckpt["num_layers"])
        self.model.load_state_dict(ckpt["state_dict"])
        self.model.to(device).eval()

    def predict(self, pos_hist: np.ndarray) -> np.ndarray:
        single = pos_hist.ndim == 2
        if single:
            pos_hist = pos_hist[None]
        deltas = np.diff(pos_hist, axis=1)
        R = LSTMPredictor._heading_rot(deltas)
        d_body = deltas.copy()
        d_body[..., :2] = np.einsum("bij,btj->bti", R, deltas[..., :2])
        x = torch.tensor(d_body / self.scale, dtype=torch.float32, device=self.device)
        with torch.no_grad():
            y = self.model(x).cpu().numpy() * self.scale
        y_world = y.copy()
        Rinv = np.transpose(R, (0, 2, 1))
        y_world[..., :2] = np.einsum("bij,bhj->bhi", Rinv, y[..., :2])
        pred = pos_hist[:, -1:, :] + np.cumsum(y_world, axis=1)
        return pred[0] if single else pred


# ================================================================ 通用訓練核心（MLP / Transformer 共用）
def _train_traj_model(model: nn.Module, X: np.ndarray, Y: np.ndarray,
                      scale: float, epochs: int = 12, batch: int = 512,
                      lr: float = 1e-3, val_split: float = 0.1,
                      label: str = "model", verbose: bool = True):
    """前處理（heading-rotation + 正規化）後訓練任意軌跡模型。"""
    device = next(model.parameters()).device
    deltas = np.diff(X, axis=1)
    R = LSTMPredictor._heading_rot(deltas)
    d_body = deltas.copy()
    d_body[..., :2] = np.einsum("bij,btj->bti", R, deltas[..., :2])
    y_world = np.diff(np.concatenate([X[:, -1:, :], Y], axis=1), axis=1)
    y_body = y_world.copy()
    y_body[..., :2] = np.einsum("bij,bhj->bhi", R, y_world[..., :2])

    Xt = torch.tensor(d_body / scale, dtype=torch.float32)
    Yt = torch.tensor(y_body / scale, dtype=torch.float32)
    n_val = max(1, int(len(Xt) * val_split))
    perm = torch.randperm(len(Xt))
    Xt, Yt = Xt[perm], Yt[perm]
    Xv, Yv = Xt[:n_val].to(device), Yt[:n_val].to(device)
    Xtr, Ytr = Xt[n_val:], Yt[n_val:]

    opt   = torch.optim.Adam(model.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.StepLR(opt, step_size=4, gamma=0.5)
    loss_fn = nn.MSELoss()
    for ep in range(epochs):
        model.train()
        idx = torch.randperm(len(Xtr))
        tot = 0.0
        for k in range(0, len(Xtr), batch):
            b = idx[k:k + batch]
            xb, yb = Xtr[b].to(device), Ytr[b].to(device)
            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            opt.step()
            tot += loss.item() * len(b)
        sched.step()
        model.eval()
        with torch.no_grad():
            vloss = loss_fn(model(Xv), Yv).item()
        if verbose:
            print(f"  [{label}] epoch {ep+1:2d}/{epochs}"
                  f"  train={tot/len(Xtr):.5f}  val={vloss:.5f}")


def train_mlp_traj(X: np.ndarray, Y: np.ndarray, dt: float, max_speed: float,
                   save_path: str, hidden: int = 256,
                   epochs: int = 12, batch: int = 512, verbose: bool = True):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    hist_len = X.shape[1]
    horizon  = Y.shape[1]
    model = TrajMLP(hist_len, horizon, hidden).to(device)
    _train_traj_model(model, X, Y, max_speed * dt, epochs=epochs,
                      batch=batch, label="MLP", verbose=verbose)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "horizon": horizon,
                "hist_len": hist_len, "hidden": hidden}, save_path)
    if verbose:
        print(f"  [MLP] 模型已存檔 -> {save_path}")


def train_transformer_traj(X: np.ndarray, Y: np.ndarray, dt: float,
                           max_speed: float, save_path: str,
                           d_model: int = 64, nhead: int = 4,
                           num_layers: int = 2, epochs: int = 12,
                           batch: int = 512, verbose: bool = True):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    horizon = Y.shape[1]
    model = TrajTransformer(horizon, d_model, nhead, num_layers).to(device)
    _train_traj_model(model, X, Y, max_speed * dt, epochs=epochs,
                      batch=batch, label="Transformer", verbose=verbose)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "horizon": horizon,
                "d_model": d_model, "nhead": nhead,
                "num_layers": num_layers}, save_path)
    if verbose:
        print(f"  [Transformer] 模型已存檔 -> {save_path}")


# ================================================================ 訓練
def make_training_windows(positions: np.ndarray, alive: np.ndarray,
                          hist_len: int, horizon: int, stride: int = 4,
                          noise_sigma_range=(0.0, 10.0), rng=None):
    """從一場模擬的位置紀錄切出訓練視窗。
    positions: (T, N, 3)、alive: (T, N) bool
    輸入加雷達等級噪聲（資料增強），標籤為未來「真實」位置 → 模型同時學去噪與預測。
    回傳 X:(B, hist, 3) 噪聲位置歷史, Y:(B, horizon, 3) 真實未來位置"""
    rng = rng or np.random.default_rng(0)
    T, N, _ = positions.shape
    L = hist_len + horizon
    Xs, Ys = [], []
    for i in range(N):
        ok = alive[:, i]
        t = 0
        while t + L <= T:
            if ok[t:t + L].all():
                seg = positions[t:t + L, i]
                sig = rng.uniform(*noise_sigma_range)
                noisy = seg[:hist_len] + rng.normal(0, sig, (hist_len, 3))
                Xs.append(noisy)
                Ys.append(seg[hist_len:])
                t += stride
            else:
                t += 1
    if not Xs:
        return (np.empty((0, hist_len, 3)), np.empty((0, horizon, 3)))
    return np.array(Xs), np.array(Ys)


def train_lstm(X: np.ndarray, Y: np.ndarray, dt: float, max_speed: float,
               hidden: int, layers: int, save_path: str,
               epochs: int = 12, batch: int = 512, lr: float = 1e-3,
               val_split: float = 0.1, verbose: bool = True):
    """訓練 TrajLSTM。X:(B,hist,3) 噪聲位置、Y:(B,H,3) 真實未來位置"""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    scale = max_speed * dt
    horizon = Y.shape[1]

    # 前處理（與推論一致）：位移 + 航向旋轉 + 正規化
    deltas = np.diff(X, axis=1)
    R = LSTMPredictor._heading_rot(deltas)
    d_body = deltas.copy()
    d_body[..., :2] = np.einsum("bij,btj->bti", R, deltas[..., :2])
    y_world = np.diff(np.concatenate([X[:, -1:, :], Y], axis=1), axis=1)
    y_body = y_world.copy()
    y_body[..., :2] = np.einsum("bij,bhj->bhi", R, y_world[..., :2])

    Xt = torch.tensor(d_body / scale, dtype=torch.float32)
    Yt = torch.tensor(y_body / scale, dtype=torch.float32)
    n_val = max(1, int(len(Xt) * val_split))
    perm = torch.randperm(len(Xt))
    Xt, Yt = Xt[perm], Yt[perm]
    Xv, Yv = Xt[:n_val].to(device), Yt[:n_val].to(device)
    Xtr, Ytr = Xt[n_val:], Yt[n_val:]

    model = TrajLSTM(horizon, hidden, layers).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.StepLR(opt, step_size=4, gamma=0.5)
    loss_fn = nn.MSELoss()

    for ep in range(epochs):
        model.train()
        idx = torch.randperm(len(Xtr))
        tot = 0.0
        for k in range(0, len(Xtr), batch):
            b = idx[k:k + batch]
            xb, yb = Xtr[b].to(device), Ytr[b].to(device)
            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            opt.step()
            tot += loss.item() * len(b)
        sched.step()
        model.eval()
        with torch.no_grad():
            vloss = loss_fn(model(Xv), Yv).item()
        if verbose:
            print(f"  [LSTM] epoch {ep+1:2d}/{epochs}  train={tot/len(Xtr):.5f}  val={vloss:.5f}")

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "horizon": horizon,
                "hidden": hidden, "layers": layers}, save_path)
    if verbose:
        print(f"  [LSTM] 模型已存檔 -> {save_path}")
    return model


# ================================================================ 評估
def ade_fde(pred: np.ndarray, truth: np.ndarray):
    """ADE/FDE：pred, truth 形狀 (B, H, 3)"""
    err = np.linalg.norm(pred - truth, axis=2)   # (B,H)
    return float(err.mean()), float(err[:, -1].mean())

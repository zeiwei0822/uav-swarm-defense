# -*- coding: utf-8 -*-
"""
要點 4：AI 找出領機 / 中繼機
=============================
防方「看不到」機群內部通訊，只能從雷達軌跡的【行為特徵】推斷誰是關鍵節點：

  領機特徵：位於陣型幾何要位、轉彎時「先動」（領先-跟隨互相關）、航跡平滑
  中繼機特徵：位於子群中心、鄰近圖中介中心性 (betweenness) 高

三種方法對照：
  1. 規則基準法：手工加權（正面性 + 領先量 → 領機；中介中心性 → 中繼機）
  2. Random Forest（sklearn）
  3. MLP 神經網路（PyTorch）

統一介面：identify(pos_window) -> scores (N,3)，欄位 = [從機, 中繼機, 領機] 信心
"""
import os
import numpy as np

from config import ROLE_FOLLOWER, ROLE_RELAY, ROLE_LEADER

FEATURE_NAMES = [
    "正面性",        # 沿飛行方向的相對位置（領機通常在前；環形陣會失效→ML價值）
    "離心距",        # 與群中心距離（正規化）
    "最近鄰距",      # 局部密度（正規化）
    "度中心性",      # 鄰近圖 degree
    "中介中心性",    # 鄰近圖 betweenness（中繼機的招牌特徵）
    "領先延遲",      # 航向互相關最佳延遲（+ = 比群體先轉）
    "領先相關",      # 上述最佳延遲的相關值
    "加速度變異",    # 航跡平滑度（從機修正抖動較大）
    "相對速度",      # 平均速度 / 群體平均
]
N_FEATURES = len(FEATURE_NAMES)


# ================================================================ 特徵工程
def _smooth(pos: np.ndarray, k: int = 9) -> np.ndarray:
    """位置序列移動平均去噪。pos: (W, N, 3)"""
    if len(pos) < k:
        return pos
    kernel = np.ones(k) / k
    out = np.empty_like(pos)
    for n in range(pos.shape[1]):
        for d in range(3):
            out[:, n, d] = np.convolve(pos[:, n, d], kernel, mode="same")
    # 卷積邊界以原值補
    h = k // 2
    out[:h] = pos[:h]
    out[-h:] = pos[-h:]
    return out


def _betweenness(adj: np.ndarray) -> np.ndarray:
    """Brandes 演算法（無權圖），adj: (N,N) bool。N<=30，純 Python 足夠快。"""
    N = len(adj)
    bc = np.zeros(N)
    neighbors = [np.flatnonzero(adj[v]) for v in range(N)]
    for s in range(N):
        stack, pred = [], [[] for _ in range(N)]
        sigma = np.zeros(N)
        sigma[s] = 1
        dist = np.full(N, -1)
        dist[s] = 0
        queue = [s]
        while queue:
            v = queue.pop(0)
            stack.append(v)
            for w in neighbors[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = np.zeros(N)
        while stack:
            w = stack.pop()
            for v in pred[w]:
                if sigma[w] > 0:
                    delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                bc[w] += delta[w]
    norm = (N - 1) * (N - 2)
    return bc / norm if norm > 0 else bc


def extract_features(pos_window: np.ndarray, max_lag: int = 15) -> np.ndarray:
    """從位置視窗計算每架無人機的行為特徵。
    pos_window: (W, N, 3) 雷達量測位置（可含噪聲，內部會去噪）
    回傳 (N, N_FEATURES)"""
    W, N, _ = pos_window.shape
    p = _smooth(pos_window)
    dt_span = 4
    vel = np.zeros_like(p)
    vel[dt_span:] = (p[dt_span:] - p[:-dt_span]) / dt_span   # 跨步差分降噪
    vel[:dt_span] = vel[dt_span]

    centroid = p.mean(axis=1)                                # (W,3)
    v_mean = vel.mean(axis=1)                                # (W,3)
    spread = np.linalg.norm(p - centroid[:, None, :], axis=2).mean() + 1e-6

    # --- 逐機幾何特徵
    rel = p - centroid[:, None, :]                           # (W,N,3)
    vm_norm = v_mean / (np.linalg.norm(v_mean, axis=1, keepdims=True) + 1e-9)
    frontness = np.einsum("wnd,wd->wn", rel, vm_norm).mean(axis=0) / spread
    dist_c = np.linalg.norm(rel, axis=2).mean(axis=0) / spread

    # 取數個取樣frame算鄰近圖（省時）
    frames = np.linspace(0, W - 1, 6).astype(int)
    deg = np.zeros(N)
    btw = np.zeros(N)
    nn_d = np.zeros(N)
    for f in frames:
        D = np.linalg.norm(p[f][:, None] - p[f][None, :], axis=2)
        np.fill_diagonal(D, np.inf)
        nn = D.min(axis=1)
        nn_d += nn
        thr = 2.3 * np.median(nn)                            # 自適應連邊門檻
        adj = D < thr
        deg += adj.sum(axis=1)
        btw += _betweenness(adj)
    deg /= len(frames) * max(N - 1, 1)
    btw /= len(frames)
    nn_d /= len(frames)
    nn_d = nn_d / (np.median(nn_d) + 1e-6)

    # --- 領先-跟隨互相關（誰先轉彎）
    head = np.arctan2(vel[..., 1], vel[..., 0])              # (W,N)
    head_m = np.arctan2(v_mean[:, 1], v_mean[:, 0])          # (W,)
    L = min(max_lag, W // 3)
    lead_lag = np.zeros(N)
    lead_corr = np.zeros(N)
    t0, t1 = L, W - L
    for i in range(N):
        best, best_l = -2.0, 0
        for lag in range(-L, L + 1):
            c = np.cos(head[t0 - lag:t1 - lag, i] - head_m[t0:t1]).mean()
            if c > best:
                best, best_l = c, lag
        lead_lag[i] = best_l / max(L, 1)
        lead_corr[i] = best

    # --- 平滑度與速度
    acc = np.diff(vel, axis=0)
    acc_std = np.linalg.norm(acc, axis=2).std(axis=0)
    acc_std = acc_std / (np.median(acc_std) + 1e-9)
    spd = np.linalg.norm(vel, axis=2).mean(axis=0)
    spd = spd / (spd.mean() + 1e-9)

    feats = np.column_stack([frontness, dist_c, nn_d, deg, btw,
                             lead_lag, lead_corr, acc_std, spd])
    return feats.astype(np.float32)


# ================================================================ 1) 規則基準法
class RuleIdentifier:
    """手工規則：依領域知識加權特徵。
    弱點：假設「領機在前方」—— 環形護衛陣（領機在中央）會誤判，
    這正是 ML 方法的價值所在（從資料自動學特徵組合）。"""
    name = "規則基準"

    def identify(self, pos_window: np.ndarray, feats: np.ndarray = None) -> np.ndarray:
        if feats is None:
            feats = extract_features(pos_window)
        N = len(feats)
        frontness, btw = feats[:, 0], feats[:, 4]
        lead_lag, lead_corr = feats[:, 5], feats[:, 6]
        leader_score = 1.2 * frontness + 1.0 * lead_lag + 0.4 * lead_corr
        relay_score = 1.5 * btw + 0.3 * (1 - np.abs(feats[:, 2] - 1))

        def softmax(z, tau=3.0):
            e = np.exp((z - z.max()) * tau)
            return e / e.sum()

        p_lead = softmax(leader_score)
        p_relay = relay_score / (relay_score.max() + 1e-9) * 0.8
        scores = np.zeros((N, 3))
        scores[:, ROLE_LEADER] = p_lead
        scores[:, ROLE_RELAY] = np.clip(p_relay * (1 - p_lead), 0, 1)
        scores[:, ROLE_FOLLOWER] = np.clip(1 - scores[:, 1] - scores[:, 2], 0, 1)
        return scores


# ================================================================ 2) Random Forest
class RFIdentifier:
    name = "RandomForest"

    def __init__(self, model_path: str, scaler_path: str):
        import joblib
        self.clf = joblib.load(model_path)
        sc = np.load(scaler_path)
        self.mu, self.sd = sc["mu"], sc["sd"]

    def identify(self, pos_window: np.ndarray, feats: np.ndarray = None) -> np.ndarray:
        if feats is None:
            feats = extract_features(pos_window)
        X = (feats - self.mu) / self.sd
        proba = self.clf.predict_proba(X)
        # predict_proba 欄位順序對應 clf.classes_，重排到 [0,1,2]
        out = np.zeros((len(X), 3))
        for k, c in enumerate(self.clf.classes_):
            out[:, int(c)] = proba[:, k]
        return out


# ============================================== 2b) 梯度提升樹 GBM（benchmark 最佳）
class GBMIdentifier(RFIdentifier):
    """與 RF 同介面（joblib 模型＋scaler＋predict_proba 重排）；
    benchmark 領機 Top-1 最高（GBM 79% > RF 73%），設為主力識別器。"""
    name = "GradientBoosting"


# ================================================================ 3) MLP（PyTorch）
def _build_mlp(n_in: int):
    import torch.nn as nn
    return nn.Sequential(
        nn.Linear(n_in, 64), nn.ReLU(), nn.Dropout(0.15),
        nn.Linear(64, 64), nn.ReLU(),
        nn.Linear(64, 3),
    )


class MLPIdentifier:
    name = "MLP"

    def __init__(self, model_path: str, scaler_path: str, device: str = None):
        import torch
        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = _build_mlp(N_FEATURES)
        ckpt = torch.load(model_path, map_location=self.device, weights_only=True)
        self.model.load_state_dict(ckpt)
        self.model.to(self.device).eval()
        sc = np.load(scaler_path)
        self.mu, self.sd = sc["mu"], sc["sd"]

    def identify(self, pos_window: np.ndarray, feats: np.ndarray = None) -> np.ndarray:
        if feats is None:
            feats = extract_features(pos_window)
        X = (feats - self.mu) / self.sd
        xt = self.torch.tensor(X, dtype=self.torch.float32, device=self.device)
        with self.torch.no_grad():
            logits = self.model(xt)
            proba = self.torch.softmax(logits, dim=1).cpu().numpy()
        return proba


# ================================================================ 訓練
def train_rf(X, y, save_path: str, scaler_path: str, verbose=True):
    from sklearn.ensemble import RandomForestClassifier
    import joblib
    mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-9
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    np.savez(scaler_path, mu=mu, sd=sd)
    Xs = (X - mu) / sd
    clf = RandomForestClassifier(
        n_estimators=300, max_depth=14, class_weight="balanced",
        n_jobs=-1, random_state=0)
    clf.fit(Xs, y)
    joblib.dump(clf, save_path)
    if verbose:
        acc = clf.score(Xs, y)
        print(f"  [RF] 訓練完成 train_acc={acc:.3f} -> {save_path}")
        imp = clf.feature_importances_
        order = np.argsort(imp)[::-1]
        print("  [RF] 特徵重要度: " +
              ", ".join(f"{FEATURE_NAMES[i]}={imp[i]:.3f}" for i in order))
    return clf


def train_gbm(X, y, save_path: str, scaler_path: str, verbose=True):
    """梯度提升樹（HistGradientBoosting）——benchmark 領機 Top-1 最佳。"""
    from sklearn.ensemble import HistGradientBoostingClassifier
    import joblib
    mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-9
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    np.savez(scaler_path, mu=mu, sd=sd)
    Xs = (X - mu) / sd
    clf = HistGradientBoostingClassifier(
        class_weight="balanced", max_iter=300, learning_rate=0.1,
        max_depth=None, random_state=0)
    clf.fit(Xs, y)
    joblib.dump(clf, save_path)
    if verbose:
        print(f"  [GBM] 訓練完成 train_acc={clf.score(Xs, y):.3f} -> {save_path}")
    return clf


def train_mlp(X, y, save_path: str, scaler_path: str,
              epochs=80, batch=256, lr=1e-3, verbose=True):
    import torch
    import torch.nn as nn
    device = "cuda" if torch.cuda.is_available() else "cpu"
    sc = np.load(scaler_path)                     # 沿用 RF 的 scaler（先訓 RF）
    Xs = (X - sc["mu"]) / sc["sd"]
    Xt = torch.tensor(Xs, dtype=torch.float32)
    yt = torch.tensor(y, dtype=torch.long)
    # 類別不平衡：1 領機 vs 3 中繼 vs ~17 從機 → 平方根反頻率加權（過強會亂槍打領機）
    counts = np.bincount(y, minlength=3).astype(float)
    w = np.sqrt(counts.sum() / (counts + 1e-9))
    w = w / w.sum() * 3
    model = _build_mlp(N_FEATURES).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    loss_fn = nn.CrossEntropyLoss(weight=torch.tensor(w, dtype=torch.float32,
                                                      device=device))
    for ep in range(epochs):
        perm = torch.randperm(len(Xt))
        tot = 0.0
        model.train()
        for k in range(0, len(Xt), batch):
            b = perm[k:k + batch]
            xb, yb = Xt[b].to(device), yt[b].to(device)
            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            opt.step()
            tot += loss.item() * len(b)
        if verbose and (ep + 1) % 10 == 0:
            model.eval()
            with torch.no_grad():
                pred = model(Xt.to(device)).argmax(1).cpu().numpy()
            print(f"  [MLP] epoch {ep+1}/{epochs} loss={tot/len(Xt):.4f} "
                  f"train_acc={(pred == y).mean():.3f}")
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    torch.save(model.state_dict(), save_path)
    if verbose:
        print(f"  [MLP] 模型已存檔 -> {save_path}")
    return model

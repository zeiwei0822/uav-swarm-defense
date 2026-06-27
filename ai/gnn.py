# -*- coding: utf-8 -*-
"""
要點 4（GNN 版）：圖神經網路找領機 / 中繼機
=============================================
把機群當成一張圖：節點＝無人機、邊＝鄰近/通訊關係。
與樹模型的關鍵差異：

  樹模型 (RF)  ：要『手刻』度中心性、中介中心性等圖結構特徵餵進去。
  GNN         ：節點只給 7 維『局部運動學』特徵（不含任何中心性），
                靠多層訊息傳遞(message passing)『自己學出』誰是網路樞紐 → 中繼/領機。

架構：3 層 GraphSAGE（mean 聚合）+ 節點分類頭 → 每節點 3 類(從機/中繼/領機)。
純 PyTorch 從頭實作（不需 torch_geometric）；機群圖小(5~30節點)，批次以
block-diagonal 鄰接一次前傳。
"""
import os
import numpy as np
import torch
import torch.nn as nn

from config import ROLE_LEADER
from ai.identify import extract_features, _smooth

# 節點局部特徵：取 extract_features 的 9 維中『非圖結構』的 7 維
#   (drop 度中心性[3]、中介中心性[4] → 這正是要讓 GNN 自己從圖學的東西)
NODE_FEAT_IDX = [0, 1, 2, 5, 6, 7, 8]   # 正面性/離心距/最近鄰/領先延遲/領先相關/加速度變異/相對速度
GNN_IN = len(NODE_FEAT_IDX)


# ================================================================ 建圖
def build_adjacency(pos_window: np.ndarray) -> np.ndarray:
    """位置視窗 → 鄰近圖(無向, 0/1)。多取樣frame＋自適應門檻，多數frame相鄰才連邊。"""
    p = _smooth(pos_window)
    W, N, _ = p.shape
    if N <= 1:
        return np.zeros((N, N), np.float32)
    frames = np.linspace(0, W - 1, 6).astype(int)
    A = np.zeros((N, N))
    for f in frames:
        D = np.linalg.norm(p[f][:, None] - p[f][None, :], axis=2)
        np.fill_diagonal(D, np.inf)
        nn = D.min(axis=1)
        thr = 2.3 * np.median(nn)
        A += (D < thr).astype(float)
    return (A >= 3).astype(np.float32)          # 至少半數frame相鄰


def build_graph(pos_window: np.ndarray, max_lag: int = 15):
    """位置視窗 → (節點特徵 (N,7), 鄰接 (N,N))。"""
    feats = extract_features(pos_window, max_lag)[:, NODE_FEAT_IDX]
    return feats.astype(np.float32), build_adjacency(pos_window)


def norm_adj(adj: np.ndarray) -> np.ndarray:
    """加自環 + 行正規化（mean 聚合）。"""
    A = adj + np.eye(len(adj), dtype=adj.dtype)
    d = A.sum(1, keepdims=True)
    d[d == 0] = 1.0
    return (A / d).astype(np.float32)


# ================================================================ 模型
class SAGELayer(nn.Module):
    """GraphSAGE(mean 聚合)：h_i' = W·[h_i ‖ mean_{j∈N(i)} h_j]"""

    def __init__(self, in_dim, out_dim):
        super().__init__()
        self.lin = nn.Linear(in_dim * 2, out_dim)

    def forward(self, h, An):                   # An: 正規化鄰接(含自環, mean)
        neigh = An @ h                          # 鄰居均值聚合（block-diagonal→不跨圖）
        return self.lin(torch.cat([h, neigh], dim=-1))


class SwarmGNN(nn.Module):
    def __init__(self, in_dim=GNN_IN, hidden=64, layers=3, n_cls=3, dropout=0.1):
        super().__init__()
        self.convs = nn.ModuleList()
        d = in_dim
        for _ in range(layers):
            self.convs.append(SAGELayer(d, hidden))
            d = hidden
        self.drop = nn.Dropout(dropout)
        self.head = nn.Sequential(nn.Linear(hidden, hidden), nn.ReLU(),
                                  nn.Dropout(dropout), nn.Linear(hidden, n_cls))

    def forward(self, h, An):
        for conv in self.convs:
            h = self.drop(torch.relu(conv(h, An)))
        return self.head(h)                     # (N, 3) logits


# ================================================================ 批次（block-diagonal）
def _collate(graphs, mu, sd, device):
    """一批圖 → 串接節點特徵 + block-diagonal 正規化鄰接 + 串接標籤。"""
    feats, labels, blocks = [], [], []
    for nf, adj, y in graphs:
        feats.append((nf - mu) / sd)
        labels.append(y)
        blocks.append(norm_adj(adj))
    H = torch.tensor(np.concatenate(feats, 0), dtype=torch.float32, device=device)
    Y = torch.tensor(np.concatenate(labels, 0), dtype=torch.long, device=device)
    tot = H.shape[0]
    A = np.zeros((tot, tot), np.float32)
    o = 0
    for b in blocks:
        n = len(b)
        A[o:o + n, o:o + n] = b
        o += n
    return H, torch.tensor(A, device=device), Y


# ================================================================ 訓練
def train_gnn(graphs, save_path, in_dim=GNN_IN, hidden=64, layers=3,
              epochs=60, batch=48, lr=2e-3, val_split=0.1, verbose=True):
    """graphs: list of (node_feats, adj(N,N), labels(N,))。
    node_feats 可為完整 9 維(資料端存的)；此處取 NODE_FEAT_IDX 的 7 維局部特徵。"""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    rng = np.random.default_rng(0)
    if graphs and graphs[0][0].shape[1] != in_dim:        # 9維→取7維局部特徵
        graphs = [(nf[:, NODE_FEAT_IDX], adj, y) for nf, adj, y in graphs]
    # 節點特徵標準化
    allf = np.concatenate([g[0] for g in graphs], 0)
    mu, sd = allf.mean(0), allf.std(0) + 1e-6
    # 類別權重（領機/中繼稀少）
    ally = np.concatenate([g[2] for g in graphs])
    freq = np.bincount(ally, minlength=3).astype(float)
    w = (1.0 / np.sqrt(freq + 1e-6)); w = w / w.sum() * 3
    cls_w = torch.tensor(w, dtype=torch.float32, device=device)

    idx = rng.permutation(len(graphs))
    n_val = max(1, int(len(graphs) * val_split))
    val_g = [graphs[i] for i in idx[:n_val]]
    tr_g = [graphs[i] for i in idx[n_val:]]

    model = SwarmGNN(in_dim, hidden, layers).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.StepLR(opt, step_size=20, gamma=0.5)
    loss_fn = nn.CrossEntropyLoss(weight=cls_w)

    def run_epoch(gs, train):
        model.train(train)
        order = rng.permutation(len(gs)) if train else np.arange(len(gs))
        tot, nseen = 0.0, 0
        for s in range(0, len(gs), batch):
            chunk = [gs[i] for i in order[s:s + batch]]
            H, A, Y = _collate(chunk, mu, sd, device)
            if train:
                opt.zero_grad()
            with torch.set_grad_enabled(train):
                logit = model(H, A)
                loss = loss_fn(logit, Y)
                if train:
                    loss.backward(); opt.step()
            tot += loss.item() * len(Y); nseen += len(Y)
        return tot / max(nseen, 1)

    for ep in range(epochs):
        tl = run_epoch(tr_g, True)
        sched.step()
        if verbose and (ep + 1) % 10 == 0:
            vl = run_epoch(val_g, False)
            print(f"  [GNN] epoch {ep+1:2d}/{epochs}  train={tl:.4f}  val={vl:.4f}")

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "in_dim": in_dim,
                "hidden": hidden, "layers": layers,
                "mu": mu.astype(np.float32), "sd": sd.astype(np.float32)},
               save_path)
    if verbose:
        print(f"  [GNN] 模型已存檔 -> {save_path}")
    return model


# ================================================================ 識別器（統一介面）
class GNNIdentifier:
    name = "GNN"

    def __init__(self, model_path, scaler_path=None, device=None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        ck = torch.load(model_path, map_location=self.device, weights_only=False)
        self.model = SwarmGNN(ck["in_dim"], ck["hidden"], ck["layers"])
        self.model.load_state_dict(ck["state_dict"])
        self.model.to(self.device).eval()
        self.mu = np.asarray(ck["mu"], np.float32)
        self.sd = np.asarray(ck["sd"], np.float32)

    def score_graph(self, node_feats, adj):
        """node_feats (N,7)、adj (N,N) → (N,3) 機率。"""
        if len(node_feats) == 0:
            return np.zeros((0, 3), np.float32)
        nf = (node_feats - self.mu) / self.sd
        An = norm_adj(adj)
        with torch.no_grad():
            H = torch.tensor(nf, dtype=torch.float32, device=self.device)
            A = torch.tensor(An, dtype=torch.float32, device=self.device)
            p = torch.softmax(self.model(H, A), dim=-1).cpu().numpy()
        return p.astype(np.float32)

    def identify(self, win, feats=None):
        """防方介面：win=雷達位置視窗 (W,N,3)；建圖→GNN→(N,3) 機率。
        feats(預算好的9維)若有則取其7維節點特徵、省一次計算。"""
        if win is None:
            raise ValueError("GNNIdentifier 需要位置視窗 win 來建圖")
        nf = (feats[:, NODE_FEAT_IDX] if feats is not None
              else extract_features(win)[:, NODE_FEAT_IDX]).astype(np.float32)
        return self.score_graph(nf, build_adjacency(win))

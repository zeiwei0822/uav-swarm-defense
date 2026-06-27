"use strict";
const pptxgen = require("pptxgenjs");

const OUT = String.raw`C:\Users\User\Desktop\UAV\UAV_intro_slides.pptx`;

const BG    = "0A0E14";
const PANEL = "111820";
const PNL2  = "0d1a28";
const GOLD  = "FFD700";
const FG    = "E6EDF3";
const MUTED = "8AA0B5";
const RED   = "FF5555";
const GREEN = "39D353";
const BLUE  = "4488FF";
const CYAN  = "00E5FF";
const ORANGE= "FF9900";

function secHdr(s, pres, title, sub) {
  s.background = { color: BG };
  s.addShape(pres.shapes.OVAL, {x:0.25,y:0.12,w:0.52,h:0.52, fill:{color:GOLD},line:{color:GOLD}});
  s.addText("00", {x:0.25,y:0.12,w:0.52,h:0.52, align:"center",valign:"middle",fontSize:14,bold:true,color:BG,margin:0});
  s.addText(title, {x:0.88,y:0.13,w:8.7,h:0.44, fontSize:19,bold:true,color:FG,fontFace:"Calibri",valign:"middle",margin:0});
  s.addText(sub,   {x:0.88,y:0.58,w:8.7,h:0.24, fontSize:10.5,color:MUTED,fontFace:"Calibri",valign:"top",margin:0});
}

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";

  // ── Slide 1: 封面 ──────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: BG };

    // 雷達環 + 無人機陣型裝飾（右側）
    const CX = 7.8, CY = 2.65, R = 1.25;
    [R*1.45, R, R*0.58].forEach(r => {
      s.addShape(pres.shapes.OVAL, {x:CX-r,y:CY-r,w:r*2,h:r*2,
        fill:{color:"0c1420"}, line:{color:"1a3050",pt:0.75}});
    });
    // 外環 6 架僚機
    for (let i = 0; i < 6; i++) {
      const a = (i*60-90)*Math.PI/180;
      const x = CX+R*Math.cos(a), y = CY+R*Math.sin(a);
      s.addShape(pres.shapes.OVAL, {x:x-0.10,y:y-0.10,w:0.20,h:0.20, fill:{color:CYAN},line:{color:CYAN}});
    }
    // 中環 6 架中繼
    for (let i = 0; i < 6; i++) {
      const a = (i*60-60)*Math.PI/180;
      const x = CX+R*0.5*Math.cos(a), y = CY+R*0.5*Math.sin(a);
      s.addShape(pres.shapes.OVAL, {x:x-0.07,y:y-0.07,w:0.14,h:0.14, fill:{color:BLUE},line:{color:BLUE}});
    }
    // 領機（中心，金色）
    s.addShape(pres.shapes.OVAL, {x:CX-0.15,y:CY-0.15,w:0.30,h:0.30, fill:{color:GOLD},line:{color:GOLD}});

    // 「專題報告」標籤
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:0.45,y:0.72,w:1.45,h:0.30, fill:{color:PANEL},line:{color:GOLD,pt:1},rectRadius:0.04});
    s.addText("專題報告", {x:0.45,y:0.72,w:1.45,h:0.30,
      fontSize:10,bold:true,color:GOLD,fontFace:"Calibri",align:"center",valign:"middle",margin:0});

    // 主標題
    s.addText("無人機機群攻防模擬系統", {
      x:0.45,y:1.38,w:6.7,h:1.28,
      fontSize:32,bold:true,color:FG,fontFace:"Calibri",align:"left",valign:"middle",margin:0});

    // 副標題
    s.addText("AI 整合防空  ×  機群拓樸識別  ×  軌跡預測", {
      x:0.45,y:2.78,w:6.7,h:0.42,
      fontSize:14,color:CYAN,fontFace:"Calibri",align:"left",valign:"middle",margin:0});

    // 技術標籤
    ["Python 3.10","PyTorch 2.x","PyTorch Geometric","FFmpeg"].forEach((t,i) => {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x:0.45+i*1.54,y:3.36,w:1.44,h:0.28, fill:{color:PANEL},line:{color:MUTED,pt:0.75},rectRadius:0.04});
      s.addText(t, {x:0.45+i*1.54,y:3.36,w:1.44,h:0.28,
        fontSize:9,color:MUTED,fontFace:"Calibri",align:"center",valign:"middle",margin:0});
    });

    // 日期
    s.addText("2026-06-27", {x:8.0,y:5.22,w:1.75,h:0.26,
      fontSize:11,color:MUTED,fontFace:"Calibri",align:"right",margin:0});
  }

  // ── Slide 2: 目錄 ──────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: BG };
    s.addText("目  錄", {x:0.30,y:0.10,w:9.40,h:0.58,
      fontSize:26,bold:true,color:GOLD,fontFace:"Calibri",align:"center",valign:"middle",margin:0});
    s.addText("CONTENTS", {x:0.30,y:0.66,w:9.40,h:0.22,
      fontSize:11,color:MUTED,fontFace:"Calibri",align:"center",margin:0});

    const secs = [
      {n:"00",title:"系統架構 & 實作流程",  sub:"模擬引擎 · AI模組 · 四階段研發流程 · 技術棧",    c:GOLD},
      {n:"01",title:"攻擊陣型 × 防空弱點",    sub:"兩種陣型 · 注意力上限 × 彈藥上限 · 針對傳統防空設計", c:CYAN},
      {n:"02",title:"指揮繼承鏈遞補",        sub:"心跳偵測 1.2 s · 選舉 0.6 s · 重組 ~13 s",       c:ORANGE},
      {n:"03",title:"LSTM 軌跡預測防空",     sub:"FDE −45% · 機動閃避場景優勢最大",                 c:GREEN},
      {n:"04",title:"GNN 領機識別斬首",      sub:"Top-1 準確率 87.1% · 攔阻率 0% → 40%",           c:BLUE},
      {n:"05",title:"AI 整合 vs 傳統防空",   sub:"同場景對比 · 突防 16 → 0 架 · AI 全面優勝",       c:RED},
    ];
    secs.forEach((sec, i) => {
      const col = i%2, row = Math.floor(i/2);
      const x = 0.30+col*4.88, y = 1.00+row*1.52;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {x,y,w:4.56,h:1.38,
        fill:{color:PANEL},line:{color:sec.c,pt:1.5},rectRadius:0.07});
      s.addShape(pres.shapes.OVAL, {x:x+0.12,y:y+0.43,w:0.52,h:0.52,
        fill:{color:sec.c},line:{color:sec.c}});
      s.addText(sec.n, {x:x+0.12,y:y+0.43,w:0.52,h:0.52,
        fontSize:13,bold:true,color:BG,fontFace:"Calibri",align:"center",valign:"middle",margin:0});
      s.addText(sec.title, {x:x+0.76,y:y+0.14,w:3.68,h:0.42,
        fontSize:13.5,bold:true,color:FG,fontFace:"Calibri",valign:"middle",margin:0});
      s.addText(sec.sub,   {x:x+0.76,y:y+0.58,w:3.68,h:0.68,
        fontSize:9.5,color:MUTED,fontFace:"Calibri",valign:"top",margin:2,lineSpacingMultiple:1.35});
    });
  }

  // ── Slide 3: 系統架構 — 攻防核心機制 ────────────────────────
  {
    const s = pres.addSlide();
    secHdr(s, pres, "系統架構 | 攻防核心機制", "攻擊機群行為引擎 × 防守方傳統/AI 策略 × 共同場景設定");

    // ── 左卡：機群攻擊方（CYAN）──────────────────
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:0.28, y:0.88, w:4.60, h:3.36,
      fill:{color:PNL2}, line:{color:CYAN, pt:1.5}, rectRadius:0.06
    });
    s.addText("機群攻擊方", {
      x:0.38, y:0.94, w:1.60, h:0.26,
      fontSize:11.5, bold:true, color:CYAN, fontFace:"Calibri", margin:0
    });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:4.04, y:0.96, w:0.74, h:0.22,
      fill:{color:CYAN, transparency:85}, line:{color:CYAN, pt:0.75}, rectRadius:0.03
    });
    s.addText("24 + 4 架", {
      x:4.04, y:0.96, w:0.74, h:0.22,
      fontSize:8.5, bold:true, color:CYAN, fontFace:"Calibri", align:"center", valign:"middle", margin:0
    });
    [
      {lbl:"兵  力",  val:"24 攻擊機 + 4 中繼節點",                              c:CYAN},
      {lbl:"行為引擎", val:"Boids 凝聚／分離／對齊 三力 + PID 位置控制器",         c:CYAN},
      {lbl:"陣  型",  val:"向心多弧包圍  ·  重疊錐形＋誘餌",                       c:CYAN},
      {lbl:"通訊拓撲", val:"無線（指揮藏中心）  /  光纖（後機續突，抗斬首）",        c:CYAN},
      {lbl:"失效策略", val:"消融就地  ·  蛇形尾隨前機  ·  向心收縮補位",             c:CYAN},
      {lbl:"誘餌機制", val:"6 架誘餌機獨立角色，全速衝前引耗防空彈藥",               c:ORANGE},
    ].forEach((r, j) => {
      const y = 1.28 + j * 0.46;
      s.addText(r.lbl, {
        x:0.36, y, w:0.90, h:0.36,
        fontSize:9, bold:true, color:r.c, fontFace:"Calibri", valign:"middle", margin:0
      });
      s.addText(r.val, {
        x:1.28, y, w:3.50, h:0.36,
        fontSize:9.5, color:FG, fontFace:"Calibri", valign:"middle", margin:0, lineSpacingMultiple:1.2
      });
    });

    // ── 右卡：防空防守方（RED/GREEN）────────────────
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:5.12, y:0.88, w:4.60, h:3.36,
      fill:{color:PNL2}, line:{color:RED, pt:1.5}, rectRadius:0.06
    });
    s.addText("防空防守方", {
      x:5.22, y:0.94, w:1.60, h:0.26,
      fontSize:11.5, bold:true, color:RED, fontFace:"Calibri", margin:0
    });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:8.98, y:0.96, w:0.64, h:0.22,
      fill:{color:GREEN, transparency:85}, line:{color:GREEN, pt:0.75}, rectRadius:0.03
    });
    s.addText("AI", {
      x:8.98, y:0.96, w:0.64, h:0.22,
      fontSize:8.5, bold:true, color:GREEN, fontFace:"Calibri", align:"center", valign:"middle", margin:0
    });
    [
      {lbl:"卡爾曼 CV", val:"卡爾曼濾波（等速模型）預測軌跡 → 計算攔截點 → 派遣攔截",  c:MUTED},
      {lbl:"LSTM",    val:"序列軌跡預測未來位置 → 精準攔截（FDE −45%）",             c:GREEN},
      {lbl:"GNN 斬首", val:"通訊圖識別領機（準確率 87.1%）→ 優先攻擊殺傷",           c:GREEN},
      {lbl:"彈藥上限", val:"防空彈藥有限制，誘餌耗彈策略可使其提前用盡",               c:ORANGE},
      {lbl:"斬首連鎖", val:"領機陣亡 → 指揮繼承鏈觸發 → 隊形重組 ~13 s",             c:ORANGE},
    ].forEach((r, j) => {
      const y = 1.28 + j * 0.56;
      s.addText(r.lbl, {
        x:5.20, y, w:0.98, h:0.44,
        fontSize:9, bold:true, color:r.c, fontFace:"Calibri", valign:"middle", margin:0
      });
      s.addText(r.val, {
        x:6.20, y, w:3.42, h:0.44,
        fontSize:9.5, color:FG, fontFace:"Calibri", valign:"middle", margin:0, lineSpacingMultiple:1.2
      });
    });

    // ── 底部：關鍵數字 banner（GOLD）─────────────────
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:0.28, y:4.32, w:9.44, h:1.18,
      fill:{color:"0d1520"}, line:{color:GOLD, pt:1.5}, rectRadius:0.06
    });
    s.addText("關鍵數字", {
      x:0.40, y:4.36, w:1.10, h:0.24,
      fontSize:10, bold:true, color:GOLD, fontFace:"Calibri", margin:0
    });
    [
      {v:"多場景", l:"統計基準"},
      {v:"24 + 4",  l:"攻擊+中繼"},
      {v:"16 → 0",  l:"突防架數\n傳統 vs AI"},
      {v:"87.1%",   l:"GNN 領機\n識別準確率"},
      {v:"−45%",    l:"LSTM FDE\n終點誤差"},
      {v:"~13 s",   l:"斬首後\n隊形重組"},
    ].forEach((k, i) => {
      const kx = 0.40 + i * 1.52;
      s.addText(k.v, {
        x:kx, y:4.58, w:1.40, h:0.32,
        fontSize:15, bold:true, color:GOLD, fontFace:"Calibri", align:"center", margin:0
      });
      s.addText(k.l, {
        x:kx, y:4.92, w:1.40, h:0.46,
        fontSize:8, color:MUTED, fontFace:"Calibri", align:"center", valign:"top", margin:0, lineSpacingMultiple:1.15
      });
    });
  }

  // ── Slide 4: 系統架構 — 研究執行流程 ──────────────────────
  {
    const s = pres.addSlide();
    secHdr(s, pres, "系統架構 | 研究執行流程", "從場景設定到結果量化的完整執行路徑");

    // 頂部四步驟
    const steps = [
      {n:"1", title:"場景設定",     sub:"陣型／兵力／策略\nseed 基準參數",     c:GOLD,   x:0.28, w:1.90},
      {n:"2", title:"攻防步進模擬", sub:"逐幀更新機群行為\n防空即時決策",      c:CYAN,   x:2.52, w:2.40},
      {n:"3", title:"全程資料記錄", sub:"位置·存活·角色\n每幀狀態快照",        c:ORANGE, x:5.26, w:2.00},
      {n:"4", title:"結果量化統計", sub:"突防率·攔截率\n隊形重組效能",          c:GREEN,  x:7.60, w:2.12},
    ];
    steps.forEach((st, i) => {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {x:st.x,y:0.88,w:st.w,h:1.10,
        fill:{color:PANEL},line:{color:st.c,pt:1.5},rectRadius:0.06});
      s.addShape(pres.shapes.OVAL, {x:st.x+0.08,y:0.96,w:0.32,h:0.32,
        fill:{color:st.c},line:{color:st.c}});
      s.addText(st.n, {x:st.x+0.08,y:0.96,w:0.32,h:0.32,
        fontSize:10,bold:true,color:BG,fontFace:"Calibri",align:"center",valign:"middle",margin:0});
      s.addText(st.title, {x:st.x+0.46,y:0.91,w:st.w-0.54,h:0.36,
        fontSize:11,bold:true,color:st.c,fontFace:"Calibri",valign:"middle",margin:0});
      s.addText(st.sub, {x:st.x+0.08,y:1.30,w:st.w-0.14,h:0.62,
        fontSize:9,color:FG,fontFace:"Calibri",valign:"top",margin:2,lineSpacingMultiple:1.35});
      if (i < 3) s.addShape(pres.shapes.RIGHT_ARROW, {x:st.x+st.w+0.04,y:1.30,w:0.22,h:0.26,
        fill:{color:MUTED},line:{color:MUTED}});
    });

    // 每幀攻防循環說明
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {x:2.52,y:2.10,w:5.10,h:1.16,
      fill:{color:"0d1830"},line:{color:CYAN,pt:1},rectRadius:0.06});
    s.addText("每幀攻防循環（5 個步驟）", {x:2.52,y:2.12,w:5.10,h:0.28,
      fontSize:11,bold:true,color:CYAN,fontFace:"Calibri",align:"center",margin:0});
    [
      "① 機群 Boids 行為 + 向目標逼近",
      "② 識別當前領機（GNN / 規則）",
      "③ 預測攻擊軌跡（LSTM / CV）",
      "④ 計算攔截點 + 傷亡判定",
      "⑤ 領機陣亡 → 觸發指揮繼承鏈",
    ].forEach((ls, i) => {
      s.addText(ls, {x:2.62+(i>2?2.52:0), y:2.44+(i>2?i-3:i)*0.22, w:2.40, h:0.20,
        fontSize:9.5,color:FG,fontFace:"Calibri",margin:0});
    });

    // 分叉箭頭
    s.addText("▼",{x:1.30,y:3.32,w:0.30,h:0.18, fontSize:10,color:MUTED,fontFace:"Calibri",align:"center",margin:0});
    s.addText("▼",{x:7.20,y:3.32,w:0.30,h:0.18, fontSize:10,color:MUTED,fontFace:"Calibri",align:"center",margin:0});

    // AI 模型訓練路徑
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {x:0.28,y:3.54,w:4.20,h:1.90,
      fill:{color:PANEL},line:{color:BLUE,pt:1.5},rectRadius:0.06});
    s.addText("AI 模型訓練路徑", {x:0.28,y:3.56,w:4.20,h:0.32,
      fontSize:11.5,bold:true,color:BLUE,fontFace:"Calibri",align:"center",margin:0});
    [
      "50,000 條模擬軌跡 → 訓練 LSTM 軌跡預測模型",
      "10,000 通訊拓撲圖 → 訓練 GNN 領機識別模型",
      "多場景 seed 隨機化，8:1:1 訓練/驗證/測試",
      "LSTM 終點誤差 FDE −45%  ·  GNN 準確率 87.1%",
      "模型離線訓練，完成後載入即時推理",
    ].forEach((t, i) => {
      s.addText("· " + t, {x:0.40,y:3.92+i*0.28,w:3.98,h:0.26,
        fontSize:9.5,color:FG,fontFace:"Calibri",margin:0});
    });

    // 成果視覺化路徑
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {x:5.50,y:3.54,w:4.22,h:1.90,
      fill:{color:PANEL},line:{color:GREEN,pt:1.5},rectRadius:0.06});
    s.addText("成果視覺化路徑", {x:5.50,y:3.56,w:4.22,h:0.32,
      fontSize:11.5,bold:true,color:GREEN,fontFace:"Calibri",align:"center",margin:0});
    [
      "攻防過程 2D 俯視戰術地圖 + 分幕旁白解說",
      "同場景傳統 vs AI 並排影片對比",
      "突防架數 / 攔截率 / 重組時間 量化標注",
      "每要點 2 支對比影片，共 10 支輸出",
      "結果數據整合，自動嵌入簡報呈現",
    ].forEach((v, i) => {
      s.addText("· " + v, {x:5.62,y:3.92+i*0.28,w:4.00,h:0.26,
        fontSize:9.5,color:FG,fontFace:"Calibri",margin:0});
    });
  }

  // ── Slide 5: 實作流程 — 四階段研發 ───────────────────────
  {
    const s = pres.addSlide();
    secHdr(s,pres,"實作流程 | 四階段研發流程","從模擬環境建構到 AI 整合驗證的完整開發路徑");

    const phases = [
      {n:"Phase 1",title:"模擬環境建構",c:CYAN, items:[
        "7 種陣型幾何（encircle/arrowhead/echelon/grid/vee/snake/diamond）",
        "Boids 仿生物理 + PID 位置控制器",
        "3 種失效策略：chain / reassign / split",
        "CV 攔截計算 + 指揮繼承鏈機制",
      ]},
      {n:"Phase 2",title:"資料生成 & 標注",c:ORANGE, items:[
        "LSTM 訓練集：50,000 條模擬軌跡（巡航/機動/閃避）",
        "GNN 訓練集：10,000 通訊拓樸圖，節點角色標注",
        "多 seed 隨機化確保模型泛化性",
        "8:1:1 訓練/驗證/測試集切分",
      ]},
      {n:"Phase 3",title:"AI 模型訓練",c:GREEN, items:[
        "LSTM：2層×128 units · MSE Loss · Adam · 100 Epochs",
        "GNN：GraphSAGE 3層×128/128/64 · CrossEntropy",
        "多模型橫向比較（規則 / 隨機森林 / GNN）",
        "驗證結果：FDE −45%，Top-1 87.1%",
      ]},
      {n:"Phase 4",title:"整合驗證 & 輸出",c:BLUE, items:[
        "同場景對比：卡爾曼 CV vs AI 全整合（突防 16→0）",
        "headless 模擬 × 多場景 × 多陣型驗證",
        "Tactical2D 視覺化輸出 + 分幕旁白卡片",
        "FFmpeg 剪輯 + pptxgenjs 自動建立簡報",
      ]},
    ];

    phases.forEach((ph,i)=>{
      const x=0.28+(i%2)*4.88, y=0.88+Math.floor(i/2)*2.36, w=4.60,h=2.24;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {x,y,w,h,
        fill:{color:PANEL},line:{color:ph.c,pt:1.5},rectRadius:0.07});
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {x:x+0.12,y:y+0.12,w:1.10,h:0.28,
        fill:{color:ph.c},line:{color:ph.c},rectRadius:0.04});
      s.addText(ph.n,    {x:x+0.12,y:y+0.12,w:1.10,h:0.28, fontSize:9.5,bold:true,color:BG,fontFace:"Calibri",align:"center",valign:"middle",margin:0});
      s.addText(ph.title,{x:x+1.30,y:y+0.12,w:w-1.42,h:0.30, fontSize:12.5,bold:true,color:ph.c,fontFace:"Calibri",valign:"middle",margin:0});
      ph.items.forEach((it,j)=>{
        s.addText("·  "+it, {x:x+0.14,y:y+0.50+j*0.40,w:w-0.28,h:0.38,
          fontSize:9.5,color:FG,fontFace:"Calibri",valign:"middle",margin:2,lineSpacingMultiple:1.2});
      });
    });
  }

  // ── Slide 6: 實作流程 — 技術棧 ────────────────────────────
  {
    const s = pres.addSlide();
    secHdr(s,pres,"實作流程 | 技術棧 & 開發工具","本專題使用之程式語言、深度學習框架、視覺化工具與部署平台");

    const stacks = [
      {cat:"程式語言 & 核心運算",c:CYAN, items:[
        ["Python 3.10+",   "主要開發語言；模擬引擎、AI、視覺化全套"],
        ["NumPy / SciPy",  "向量運算、幾何計算、Boids 物理模型"],
        ["Matplotlib",     "靜態圖表輸出（ADE/FDE/模型比較圖）"],
      ]},
      {cat:"深度學習框架",c:GREEN, items:[
        ["PyTorch 2.x",         "LSTM 軌跡預測網路訓練與推理"],
        ["PyTorch Geometric",   "GNN（GraphSAGE）圖神經網路"],
        ["scikit-learn","基線模型比較（規則 / RF / GNN）"],
      ]},
      {cat:"視覺化 & 媒體處理",c:ORANGE, items:[
        ["Matplotlib Animation","Tactical2D 戰術地圖動畫渲染"],
        ["FFmpeg",              "MP4 剪輯、裁切、hstack 並排合併"],
        ["pptxgenjs (Node.js)", "自動化簡報建立、影片嵌入"],
      ]},
      {cat:"部署 & 擴充",c:BLUE, items:[
        ["GitHub / GitHub Pages","原始碼版控 + 互動 Demo 線上部署"],
        ["Three.js",             "前端 3D UAV 群體飛行互動展示"],
        ["ESP32-S3 / LSM9DS1",   "實機擴充：IMU慣性導航 + 姿態估測"],
      ]},
    ];

    stacks.forEach((st,si)=>{
      const col=si%2, row=Math.floor(si/2);
      const x=0.28+col*4.88, y=0.88+row*2.36, w=4.60,h=2.24;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {x,y,w,h,
        fill:{color:PANEL},line:{color:st.c,pt:1.5},rectRadius:0.07});
      s.addText(st.cat, {x:x+0.14,y:y+0.12,w:w-0.28,h:0.30,
        fontSize:12,bold:true,color:st.c,fontFace:"Calibri",margin:0});
      st.items.forEach(([n,d],j)=>{
        const iy=y+0.52+j*0.54;
        s.addText(n, {x:x+0.14,y:iy,      w:w-0.28,h:0.26, fontSize:10.5,bold:true,color:FG,fontFace:"Calibri",margin:0});
        s.addText(d, {x:x+0.14,y:iy+0.26, w:w-0.28,h:0.24, fontSize:9,color:MUTED,fontFace:"Calibri",margin:0});
      });
    });
  }

  await pres.writeFile({ fileName: OUT });
  console.log("done:", OUT);
}

main().catch(e=>{console.error(e);process.exit(1);});

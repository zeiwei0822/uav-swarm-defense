// make_p5_slides.js — 大標5：兩支獨立影片（標籤已烤入）並排
"use strict";
const pptxgen = require("pptxgenjs");
const path    = require("path");

const VID5 = String.raw`C:\Users\User\Desktop\UAV\slides_p5`;
const OUT   = String.raw`C:\Users\User\Desktop\UAV\UAV_大標5_影片_v5.pptx`;

const BG    = "0A0E14";
const PANEL = "111820";
const GOLD  = "FFD700";
const FG    = "E6EDF3";
const MUTED = "8AA0B5";
const RED   = "FF5555";
const GREEN = "39D353";
const BLUE  = "4488FF";
const CYAN  = "00E5FF";

// 每支影片原始像素 1500×850  → 比例 850/1500
// 投影片可用寬 9.58"（兩支各 4.75" + 間距 0.08"）
// 高度 = 4.75 × (850/1500) = 2.6917" ≈ 2.69"
// 合併影片 2308×800，單支播放同步兩側
const MW = 9.7;                                          // 影片寬度（填滿）
const MH = parseFloat((MW * 800 / 2308).toFixed(4));    // 3.3624"（精確比例）
const MX = (10 - MW) / 2;                               // 水平居中
const MY = 0.92;                                         // 標題下方

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.title  = "大標5 AI防空整合成果";

  // ── Slide 5a：兩支影片並排 ─────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: BG };

    // 標題區
    s.addShape(pres.shapes.OVAL, { x:0.25,y:0.15,w:0.52,h:0.52,
      fill:{color:GOLD}, line:{color:GOLD} });
    s.addText("5", { x:0.25,y:0.15,w:0.52,h:0.52,
      align:"center",valign:"middle",fontSize:18,bold:true,color:"0A0E14",margin:0 });

    s.addText("AI 整合防空 vs 傳統防空 — 同場景左右對比", {
      x:0.88,y:0.16,w:8.7,h:0.45,
      fontSize:20,bold:true,color:FG,fontFace:"Calibri",valign:"middle",margin:0 });
    s.addText(
      `向心多弧包圍（24架） ·  左：卡爾曼 CV 預測（16 架突防）  ·  右：LSTM + GNN 斬首（0 架突防）`,
      { x:0.88,y:0.61,w:8.7,h:0.28,
        fontSize:11,color:MUTED,fontFace:"Calibri",valign:"top",margin:0 });

    // 合併影片（一支同步播放，左=傳統 右=AI）
    s.addMedia({ type:"video",
      path: path.join(VID5,"p5_merged.mp4"),
      x: MX, y: MY, w: MW, h: MH });

    // 結果標注（影片正下方，左右各半）
    const BY = MY + MH + 0.06;
    const HW = MW / 2;
    s.addText("突防：16 / 24 架", {
      x: MX, y: BY, w: HW, h: 0.32,
      fontSize:13,bold:true,color:RED,fontFace:"Calibri",
      align:"center",valign:"middle",margin:0 });
    s.addText("突防：0 / 24 架", {
      x: MX + HW, y: BY, w: HW, h: 0.32,
      fontSize:13,bold:true,color:GREEN,fontFace:"Calibri",
      align:"center",valign:"middle",margin:0 });
  }

  // ── Slide 5b：四要點成果摘要 ────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: BG };

    s.addText("AI 防空整合成果摘要", {
      x:0.3,y:0.08,w:9.4,h:0.55,
      fontSize:26,bold:true,color:GOLD,fontFace:"Calibri",align:"center",valign:"middle",margin:0 });

    const cards = [
      { tag:"要點1", color:CYAN,    title:"攻擊陣型設計",  stat:"2 種",    desc:"攻擊陣型",
        body:"注意力上限 + 彈藥上限\n向心多弧 → 16/24 突防\n錐形誘餌 → 彈藥 100% 耗盡", x:0.25 },
      { tag:"要點2", color:"FF9900",title:"繼承鏈遞補",    stat:"≤ 13 s", desc:"重組恢復時間",
        body:"領機陣亡後繼承鏈自動啟動\n心跳逾時1.2s偵測 + 選舉0.6s\n約13s恢復完整編隊",x:2.65 },
      { tag:"要點3", color:GREEN,   title:"LSTM 軌跡預測", stat:"−45%",   desc:"FDE 終點誤差",
        body:"LSTM vs 卡爾曼CV\nFDE: 19.45m → 10.61m\n機動閃避場景優勢最大",            x:5.05 },
      { tag:"要點4", color:BLUE,    title:"GNN 領機識別",  stat:"87.1%",  desc:"Top-1 準確率",
        body:"GNN 攔阻率 40% vs 卡爾曼 CV 0%\n突防減少 61%（16→6.2 架）\nRF 20% → GNN 40% (+20pp)",x:7.45 },
    ];

    for (const c of cards) {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x:c.x, y:0.75, w:2.2, h:4.6,
        fill:{color:PANEL}, line:{color:c.color, pt:1.5}, rectRadius:0.08 });
      s.addText(c.tag,   { x:c.x+0.08,y:0.85, w:2.04,h:0.36, fontSize:12,bold:true,color:c.color,fontFace:"Calibri",align:"center",margin:0 });
      s.addText(c.title, { x:c.x+0.06,y:1.21, w:2.08,h:0.48, fontSize:15,bold:true,color:FG,fontFace:"Calibri",align:"center",margin:0 });
      s.addText(c.stat,  { x:c.x+0.06,y:1.69, w:2.08,h:0.72, fontSize:30,bold:true,color:c.color,fontFace:"Calibri",align:"center",margin:0 });
      s.addText(c.desc,  { x:c.x+0.06,y:2.41, w:2.08,h:0.30, fontSize:11,color:MUTED,fontFace:"Calibri",align:"center",margin:0 });
      s.addText(c.body,  { x:c.x+0.10,y:2.85, w:2.00,h:2.30, fontSize:11,color:FG,fontFace:"Calibri",
                           align:"left",valign:"top",margin:4,lineSpacingMultiple:1.35 });
    }

    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:0.25, y:5.42, w:9.5, h:0.50,
      fill:{color:"1a2535"}, line:{color:GREEN, pt:1}, rectRadius:0.06 });
    s.addText(
      "結論：AI 整合防空（LSTM 預測 + GNN 斬首）使任務攔阻率 0%→40%，突防減少 61%（16→6.2 架），全面優於卡爾曼 CV 傳統防空",
      { x:0.30,y:5.44,w:9.40,h:0.46,
        fontSize:12.5,bold:true,color:GREEN,fontFace:"Calibri",
        align:"center",valign:"middle",margin:0 });
  }

  await pres.writeFile({ fileName: OUT });
  console.log("done:", OUT);
  console.log(`  合併影片 2308×800 → ${MW}" × ${MH.toFixed(3)}"  (比例精確)`);
}

main().catch(e => { console.error(e); process.exit(1); });

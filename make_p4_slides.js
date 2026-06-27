// make_p4_slides.js — 要點4 投影片（GNN 領機辨識）
"use strict";
const pptxgen = require("pptxgenjs");
const path    = require("path");

const VID  = String.raw`C:\Users\User\Desktop\UAV\slides_p4`;
const FIG  = String.raw`C:\Users\User\Desktop\UAV\figures`;
const OUT  = String.raw`C:\Users\User\Desktop\UAV\UAV_要點4_影片.pptx`;

const BG    = "0A0E14";
const GOLD  = "FFD700";
const FG    = "E6EDF3";
const MUTED = "8AA0B5";
const GREEN = "39D353";
const BLUE  = "4488FF";

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.title  = "要點4 AI GNN 領機辨識";

  // ── Slide 4a：GNN 影片（SIGINT + 斬首） ──────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: BG };

    s.addShape(pres.shapes.OVAL, { x:0.25,y:0.12,w:0.48,h:0.48,
      fill:{color:GREEN}, line:{color:GREEN} });
    s.addText("4a", { x:0.25,y:0.12,w:0.48,h:0.48,
      align:"center",valign:"middle",fontSize:16,bold:true,color:"0A0E14",margin:0 });

    s.addText("AI 精準斬首：GNN 圖神經網路領機辨識", {
      x:0.84,y:0.13,w:8.7,h:0.45,
      fontSize:22,bold:true,color:FG,fontFace:"Calibri",valign:"middle",margin:0 });
    s.addText("GNN 分析圖結構拓樸 → SIGINT 確認 C² 訊號 → 精準鎖定領機斬首", {
      x:0.84,y:0.56,w:8.7,h:0.28,
      fontSize:13,color:MUTED,fontFace:"Calibri",valign:"top",margin:0 });

    s.addMedia({ type:"video", path:path.join(VID,"p4_gnn.mp4"),
      x:0.25,y:0.9,w:9.5,h:4.65 });
  }

  // ── Slide 4b：多模型識別準確率排行 ───────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: BG };

    s.addShape(pres.shapes.OVAL, { x:0.25,y:0.12,w:0.48,h:0.48,
      fill:{color:GOLD}, line:{color:GOLD} });
    s.addText("4b", { x:0.25,y:0.12,w:0.48,h:0.48,
      align:"center",valign:"middle",fontSize:16,bold:true,color:"0A0E14",margin:0 });

    s.addText("多模型比較：領機 Top-1 識別準確率", {
      x:0.84,y:0.13,w:8.7,h:0.45,
      fontSize:22,bold:true,color:FG,fontFace:"Calibri",valign:"middle",margin:0 });
    s.addText("規則法 26.8% → GNN 87.1%，準確率提升 +60pp（新測試集）", {
      x:0.84,y:0.56,w:8.7,h:0.28,
      fontSize:13,color:MUTED,fontFace:"Calibri",valign:"top",margin:0 });

    s.addImage({ path:path.join(VID,"chart_model_rank.png"),
      x:0.25,y:0.88,w:9.5,h:4.65 });
  }

  // ── Slide 4c：三模型混淆矩陣 + 陣型細目（fig4 現成）──────────
  {
    const s = pres.addSlide();
    s.background = { color: BG };

    s.addShape(pres.shapes.OVAL, { x:0.25,y:0.12,w:0.48,h:0.48,
      fill:{color:BLUE}, line:{color:BLUE} });
    s.addText("4c", { x:0.25,y:0.12,w:0.48,h:0.48,
      align:"center",valign:"middle",fontSize:16,bold:true,color:"0A0E14",margin:0 });

    s.addText("角色識別分析：規則法 vs RF vs GNN 混淆矩陣", {
      x:0.84,y:0.13,w:8.7,h:0.45,
      fontSize:22,bold:true,color:FG,fontFace:"Calibri",valign:"middle",margin:0 });
    s.addText("環形護衛陣規則法 Top-1 ≈ 0（居中難以用距離判斷）；GNN 圖結構辨識不受陣型影響", {
      x:0.84,y:0.56,w:8.7,h:0.28,
      fontSize:12,color:MUTED,fontFace:"Calibri",valign:"top",margin:0 });

    s.addImage({ path:path.join(FIG,"fig4_角色識別.png"),
      x:0.2,y:0.88,w:9.6,h:4.65 });
  }

  // ── Slide 4d：線上模擬戰果 RF vs GNN ────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: BG };

    s.addShape(pres.shapes.OVAL, { x:0.25,y:0.12,w:0.48,h:0.48,
      fill:{color:GREEN}, line:{color:GREEN} });
    s.addText("4d", { x:0.25,y:0.12,w:0.48,h:0.48,
      align:"center",valign:"middle",fontSize:16,bold:true,color:"0A0E14",margin:0 });

    s.addText("線上模擬戰果：RF 識別 vs GNN 識別", {
      x:0.84,y:0.13,w:8.7,h:0.45,
      fontSize:22,bold:true,color:FG,fontFace:"Calibri",valign:"middle",margin:0 });
    s.addText("箭頭陣型：GNN 突防 6.2 vs RF 9.2（-33%）；攔阻率 40% vs 20%（+20pp）", {
      x:0.84,y:0.56,w:8.7,h:0.28,
      fontSize:13,color:MUTED,fontFace:"Calibri",valign:"top",margin:0 });

    s.addImage({ path:path.join(VID,"chart_online.png"),
      x:0.3,y:0.88,w:9.4,h:4.65 });
  }

  await pres.writeFile({ fileName: OUT });
  console.log("done:", OUT);
}

main().catch(e => { console.error(e); process.exit(1); });

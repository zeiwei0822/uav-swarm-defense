// make_p3_slides.js — 要點3 投影片（CV vs LSTM + 圖表）
"use strict";
const pptxgen = require("pptxgenjs");
const path    = require("path");
const fs      = require("fs");

const VID  = String.raw`C:\Users\User\Desktop\UAV\slides_p3`;
const FIG  = String.raw`C:\Users\User\Desktop\UAV\figures`;
const OUT  = String.raw`C:\Users\User\Desktop\UAV\UAV_要點3_影片.pptx`;

const BG    = "0A0E14";
const GOLD  = "FFD700";
const FG    = "E6EDF3";
const MUTED = "8AA0B5";
const RED   = "FF4444";
const GREEN = "39D353";

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.title  = "要點3 AI 軌跡預測 CV vs LSTM";

  // ── Slide 1：傳統 CV 影片 ─────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: BG };

    s.addShape(pres.shapes.OVAL, { x:0.25,y:0.12,w:0.48,h:0.48,
      fill:{color:RED}, line:{color:RED} });
    s.addText("3a", { x:0.25,y:0.12,w:0.48,h:0.48,
      align:"center",valign:"middle",fontSize:16,bold:true,color:"0A0E14",margin:0 });

    s.addText("傳統防空：卡爾曼 CV 預測", {
      x:0.84,y:0.13,w:8.7,h:0.45,
      fontSize:22,bold:true,color:FG,fontFace:"Calibri",valign:"middle",margin:0 });
    s.addText("假設無人機直線等速 → 一閃避即脫靶 → 16 / 24 架突防", {
      x:0.84,y:0.56,w:8.7,h:0.28,
      fontSize:13,color:MUTED,fontFace:"Calibri",valign:"top",margin:0 });

    s.addMedia({ type:"video", path:path.join(VID,"p3_1_cv.mp4"),
      x:0.25,y:0.9,w:9.5,h:4.65 });
  }

  // ── Slide 2：AI LSTM 影片 ─────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: BG };

    s.addShape(pres.shapes.OVAL, { x:0.25,y:0.12,w:0.48,h:0.48,
      fill:{color:GREEN}, line:{color:GREEN} });
    s.addText("3b", { x:0.25,y:0.12,w:0.48,h:0.48,
      align:"center",valign:"middle",fontSize:16,bold:true,color:"0A0E14",margin:0 });

    s.addText("AI 防空：LSTM 軌跡預測", {
      x:0.84,y:0.13,w:8.7,h:0.45,
      fontSize:22,bold:true,color:FG,fontFace:"Calibri",valign:"middle",margin:0 });
    s.addText("學習機動規律、預判閃避路徑 → 0 / 24 架突防", {
      x:0.84,y:0.56,w:8.7,h:0.28,
      fontSize:13,color:MUTED,fontFace:"Calibri",valign:"top",margin:0 });

    s.addMedia({ type:"video", path:path.join(VID,"p3_2_lstm.mp4"),
      x:0.25,y:0.9,w:9.5,h:4.65 });
  }

  // ── Slide 3：軌跡預測誤差分析（現成 fig3）────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: BG };

    s.addShape(pres.shapes.OVAL, { x:0.25,y:0.12,w:0.48,h:0.48,
      fill:{color:GOLD}, line:{color:GOLD} });
    s.addText("3c", { x:0.25,y:0.12,w:0.48,h:0.48,
      align:"center",valign:"middle",fontSize:16,bold:true,color:"0A0E14",margin:0 });

    s.addText("軌跡預測誤差分析：卡爾曼CV vs LSTM", {
      x:0.84,y:0.13,w:8.7,h:0.45,
      fontSize:22,bold:true,color:FG,fontFace:"Calibri",valign:"middle",margin:0 });
    s.addText("測試集 n=3000，預測時域 2.5s，雷達噪聲 σ≈4–10m　│　FDE 改善 45.4%", {
      x:0.84,y:0.56,w:8.7,h:0.28,
      fontSize:13,color:MUTED,fontFace:"Calibri",valign:"top",margin:0 });

    s.addImage({ path:path.join(FIG,"fig3_軌跡預測.png"),
      x:0.2,y:0.88,w:9.6,h:4.65 });
  }

  await pres.writeFile({ fileName: OUT });
  console.log("done:", OUT);
}

main().catch(e => { console.error(e); process.exit(1); });

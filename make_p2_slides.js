// make_p2_slides.js — 要點2 投影片（繼承鏈遞補）
"use strict";
const pptxgen = require("pptxgenjs");
const path = require("path");

const BASE = String.raw`C:\Users\User\Desktop\UAV\slides_p2`;
const OUT  = String.raw`C:\Users\User\Desktop\UAV\UAV_要點2_影片.pptx`;

const BG    = "0A0E14";
const GOLD  = "FFD700";
const FG    = "E6EDF3";
const MUTED = "8AA0B5";

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.title  = "要點2 領機失效 × 繼承鏈遞補";

  const slide = pres.addSlide();
  slide.background = { color: BG };

  // 編號圓圈
  slide.addShape(pres.shapes.OVAL, {
    x: 0.25, y: 0.12, w: 0.48, h: 0.48,
    fill: { color: GOLD }, line: { color: GOLD },
  });
  slide.addText("2", {
    x: 0.25, y: 0.12, w: 0.48, h: 0.48,
    align: "center", valign: "middle",
    fontSize: 20, bold: true, color: "0A0E14", margin: 0,
  });

  // 標題
  slide.addText("領機失效 → 繼承鏈遞補（Chain Fail）", {
    x: 0.84, y: 0.13, w: 8.7, h: 0.45,
    fontSize: 22, bold: true, color: FG,
    fontFace: "Calibri", valign: "middle", margin: 0,
  });

  // 副標題
  slide.addText("向心多弧陣型　×　4次連續斬首　×　繼承鏈逐步消耗", {
    x: 0.84, y: 0.56, w: 8.7, h: 0.28,
    fontSize: 13, color: MUTED,
    fontFace: "Calibri", valign: "top", margin: 0,
  });

  // 影片
  slide.addMedia({
    type: "video",
    path: path.join(BASE, "p2_ai.mp4"),
    x: 0.25, y: 0.9, w: 9.5, h: 4.65,
  });

  await pres.writeFile({ fileName: OUT });
  console.log("done:", OUT);
}

main().catch(e => { console.error(e); process.exit(1); });

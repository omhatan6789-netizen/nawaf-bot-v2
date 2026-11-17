(function(){
const memoryStyle=document.createElement("style");
memoryStyle.id="casual-memory-card-styles";
memoryStyle.textContent=".memory-card{position:relative;min-height:66px!important;overflow:hidden;border:1px solid rgba(255,255,255,.13)!important;border-radius:14px!important;background:linear-gradient(145deg,#341116,#17090d)!important;color:#fff!important;box-shadow:0 5px 12px rgba(0,0,0,.24);transition:transform .45s cubic-bezier(.2,.75,.25,1),background .4s ease,border-color .4s ease,box-shadow .4s ease;transform-style:preserve-3d}\n.memory-card:not(:disabled){cursor:pointer}\n.memory-card:not(:disabled):active{transform:scale(.96)}\n.memory-card .memory-face{display:block;transition:transform .42s cubic-bezier(.2,.75,.25,1);backface-visibility:hidden}\n.memory-card.revealed{background:linear-gradient(145deg,#fff1f2,#e7c5ca)!important;color:#351016!important;border-color:#fff!important;box-shadow:0 0 14px rgba(255,190,200,.22)}\n.memory-card.flip-in{animation:memoryFlipIn .42s cubic-bezier(.2,.75,.25,1) both}\n.memory-card.flip-out{animation:memoryFlipOut .48s cubic-bezier(.2,.75,.25,1) both}\n.memory-card.matched{background:linear-gradient(145deg,#236b4a,#123c2b)!important;color:#fff!important;border:1px solid #7df0b2!important;box-shadow:0 0 16px rgba(80,230,150,.3);opacity:1}\n.memory-card.just-matched{animation:memoryMatch .42s ease both}\n.memory-owner{position:absolute;top:3px;left:4px;right:4px;display:block;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:9px;line-height:12px;font-weight:700;color:#d8ffe8;text-align:center;pointer-events:none}\n.memory-card.matched .memory-face{padding-top:9px}\n@keyframes memoryFlipIn{0%{transform:perspective(500px) rotateY(88deg) scale(.96)}65%{transform:perspective(500px) rotateY(-8deg) scale(1.02)}100%{transform:perspective(500px) rotateY(0) scale(1)}}\n@keyframes memoryFlipOut{0%{transform:perspective(500px) rotateY(0) scale(1)}55%{transform:perspective(500px) rotateY(82deg) scale(.97)}100%{transform:perspective(500px) rotateY(0) scale(1)}}\n@keyframes memoryMatch{0%{transform:scale(.92)}65%{transform:scale(1.05)}100%{transform:scale(1)}}";
if(!document.getElementById(memoryStyle.id)) document.head.append(memoryStyle);
const findStyle=document.createElement("style");
findStyle.id="find-match-styles";
findStyle.textContent=".find-duel{display:flex;flex-direction:column;gap:22px;align-items:center;margin:14px auto 24px;max-width:560px}.find-side{text-align:center;width:100%;min-width:0}.find-side-title{font-size:15px;font-weight:900;color:#ffe1e4;margin:0 0 9px}.find-circle{width:min(82vw,340px);aspect-ratio:1;margin:auto;border-radius:50%;padding:12%;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-template-rows:repeat(3,minmax(0,1fr));gap:7px;align-items:center;justify-items:center;background:radial-gradient(circle at 35% 25%,#6a9fff,#2055a8 58%,#102d68);border:4px solid #b9dcff;box-shadow:inset 0 8px 22px #ffffff44,inset 0 -12px 24px #001b55aa,0 10px 24px #0008}.find-item{width:100%;height:100%;min-width:0;min-height:0;padding:5px;border:1px solid #ffffff40;border-radius:20px;background:linear-gradient(145deg,#ffffff38,#ffffff12);display:grid;place-items:center;touch-action:manipulation;box-shadow:inset 0 1px 5px #ffffff35,0 3px 7px #001b5540;transition:transform .12s,background .12s}.find-item svg{width:88%;height:88%;max-width:76px;max-height:76px;display:block;pointer-events:none;filter:drop-shadow(0 3px 2px #001b5555)}.find-item:active{transform:scale(.88);background:#ffffff65}.find-status{margin:10px 0;padding:12px;border-radius:13px;background:#ffffff12;text-align:center;font-weight:900}.find-score{font-size:14px;font-weight:900;display:flex;justify-content:center;flex-wrap:wrap;gap:9px}.find-round-banner{margin:12px 0 5px;padding:13px 15px;border:1px solid #9ed0ff88;border-radius:14px;background:linear-gradient(135deg,#173f79,#10274d);color:#fff;text-align:center;font-weight:900;box-shadow:0 6px 16px #0004}.find-item:disabled{opacity:.82}.find-footer{margin:18px auto 4px;text-align:center;color:#c8d8f2;font-size:13px}@media(max-width:390px){.find-duel{gap:18px}.find-circle{width:88vw;padding:11%;gap:5px}.find-item{border-radius:16px;padding:3px}.find-item svg{width:94%;height:94%}}";
if(!document.getElementById(findStyle.id))document.head.append(findStyle);
const findShapes={
 car:'<path d="M7 28h50l-5-16H17l-7 16Z" fill="#ffb52e" stroke="#57330b" stroke-width="3" stroke-linejoin="round"/><path d="M4 29h56v14H4z" fill="#ef6b36" stroke="#57330b" stroke-width="3"/><circle cx="17" cy="44" r="7" fill="#263447" stroke="#dcecff" stroke-width="3"/><circle cx="48" cy="44" r="7" fill="#263447" stroke="#dcecff" stroke-width="3"/><path d="m20 15-4 11h16V15zM36 15v11h15l-4-11z" fill="#bdeaff"/>',
 plane:'<path d="m32 3 7 23 21 12v6L38 39l-2 17-4 4-4-4-2-17L4 44v-6l21-12z" fill="#f2f7ff" stroke="#31527f" stroke-width="3" stroke-linejoin="round"/>',
 kite:'<path d="m32 4 24 25-24 25L8 29z" fill="#ff6e9c" stroke="#69284c" stroke-width="3"/><path d="m32 4 0 50M8 29h48" stroke="#fff" stroke-width="2"/><path d="m32 54 5 8-6 2-4-6" fill="none" stroke="#ffe28a" stroke-width="3"/>',
 boat:'<path d="M7 39h50L47 54H19z" fill="#ef754a" stroke="#63351f" stroke-width="3"/><path d="M31 8v30H12z" fill="#fff0bd" stroke="#72502b" stroke-width="3"/><path d="M35 13v25h17z" fill="#5bd3d0" stroke="#245d68" stroke-width="3"/>',
 bike:'<circle cx="15" cy="43" r="11" fill="none" stroke="#eaf4ff" stroke-width="4"/><circle cx="51" cy="43" r="11" fill="none" stroke="#eaf4ff" stroke-width="4"/><path d="m15 43 13-20 12 20H15l9-14h16l11 14M25 23h-8m18 0h8" fill="none" stroke="#ffca55" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>',
 bus:'<rect x="8" y="8" width="48" height="40" rx="8" fill="#ffcc43" stroke="#754c16" stroke-width="3"/><path d="M14 15h14v13H14zm19 0h16v13H33z" fill="#b9edff"/><path d="M8 34h48" stroke="#754c16" stroke-width="3"/><circle cx="19" cy="49" r="6" fill="#263447" stroke="#e5f2ff" stroke-width="2"/><circle cx="46" cy="49" r="6" fill="#263447" stroke="#e5f2ff" stroke-width="2"/>',
 train:'<rect x="13" y="5" width="38" height="43" rx="8" fill="#70c7ff" stroke="#244c77" stroke-width="3"/><path d="M19 13h10v12H19zm16 0h10v12H35z" fill="#f1fbff"/><path d="M13 33h38" stroke="#244c77" stroke-width="3"/><circle cx="22" cy="49" r="5" fill="#263447"/><circle cx="42" cy="49" r="5" fill="#263447"/>',
 truck:'<path d="M5 15h34v30H5z" fill="#58b6f1" stroke="#244c77" stroke-width="3"/><path d="M39 26h12l9 11v8H39z" fill="#ffbd4a" stroke="#74491b" stroke-width="3"/><path d="M45 29h5l6 8H45z" fill="#dff6ff"/><circle cx="18" cy="47" r="6" fill="#263447" stroke="#e8f4ff" stroke-width="2"/><circle cx="49" cy="47" r="6" fill="#263447" stroke="#e8f4ff" stroke-width="2"/>',
 rocket:'<path d="M32 4c15 10 19 27 10 42H22C13 31 17 14 32 4Z" fill="#ff795f" stroke="#713a38" stroke-width="3"/><circle cx="32" cy="25" r="7" fill="#bcefff" stroke="#315b78" stroke-width="3"/><path d="m21 35-12 12 14-2m19-10 12 12-14-2" fill="#ffd34f" stroke="#74431c" stroke-width="3"/><path d="M27 47 32 62l5-15" fill="#ffcb45"/>',
 helicopter:'<ellipse cx="30" cy="35" rx="20" ry="12" fill="#74d3a2" stroke="#285a4a" stroke-width="3"/><path d="M47 33 61 23v5L48 39M30 22V12M9 12h43" stroke="#315b78" stroke-width="4" stroke-linecap="round"/><path d="M12 47h36M20 49l-5 7m25-7 5 7" stroke="#315b78" stroke-width="3"/>',
 balloon:'<ellipse cx="32" cy="25" rx="17" ry="21" fill="#ff7195" stroke="#74324e" stroke-width="3"/><path d="m26 45 6 6 6-6M32 51v10" fill="none" stroke="#fff0bd" stroke-width="3"/>',
 umbrella:'<path d="M5 30a27 27 0 0 1 54 0H5Z" fill="#ffce4e" stroke="#72501b" stroke-width="3"/><path d="M32 30v23q0 8 8 5" fill="none" stroke="#e8f4ff" stroke-width="4" stroke-linecap="round"/>',
 camera:'<rect x="6" y="15" width="52" height="36" rx="7" fill="#8c9fb9" stroke="#35445b" stroke-width="3"/><path d="M18 15 23 8h17l5 7" fill="#ffcf52" stroke="#35445b" stroke-width="3"/><circle cx="33" cy="33" r="12" fill="#5bd3d0" stroke="#253c5a" stroke-width="4"/><circle cx="33" cy="33" r="5" fill="#eafaff"/>',
 clock:'<circle cx="32" cy="32" r="25" fill="#fff0bb" stroke="#80552b" stroke-width="4"/><path d="M32 15v18l13 8" fill="none" stroke="#4b5061" stroke-width="4" stroke-linecap="round"/>',
 headphones:'<path d="M10 35V29a22 22 0 0 1 44 0v6" fill="none" stroke="#83d6ff" stroke-width="8" stroke-linecap="round"/><rect x="7" y="31" width="13" height="23" rx="6" fill="#ffbd4b" stroke="#70451d" stroke-width="3"/><rect x="44" y="31" width="13" height="23" rx="6" fill="#ffbd4b" stroke="#70451d" stroke-width="3"/>',
 key:'<circle cx="20" cy="25" r="12" fill="none" stroke="#ffd35b" stroke-width="7"/><path d="M30 33 54 56m-9-9 7-7m-14 0 7-7" stroke="#ffd35b" stroke-width="7" stroke-linecap="round"/>',
 crown:'<path d="m7 20 14 11 11-22 11 22 14-11-5 34H12z" fill="#ffcf43" stroke="#80551c" stroke-width="3" stroke-linejoin="round"/><path d="M14 44h36" stroke="#fff0ad" stroke-width="4"/>',
 gift:'<rect x="9" y="25" width="46" height="31" rx="4" fill="#ff7188" stroke="#78344c" stroke-width="3"/><path d="M32 25v31M7 18h50v10H7z" fill="#ffd052" stroke="#80521d" stroke-width="3"/><path d="M32 18c-18 2-19-14-8-13 7 0 8 13 8 13Zm0 0c18 2 19-14 8-13-7 0-8 13-8 13Z" fill="#71d4c0" stroke="#286c65" stroke-width="2"/>',
 house:'<path d="m5 30 27-23 27 23v29H5z" fill="#ffce88" stroke="#784b32" stroke-width="3"/><path d="M2 30 32 5l30 25" fill="none" stroke="#d95d56" stroke-width="7"/><rect x="25" y="38" width="14" height="21" fill="#7bb7e8" stroke="#784b32" stroke-width="2"/>',
 flower:'<path d="M32 29v31" stroke="#398b59" stroke-width="5"/><path d="M32 43q-16-15-18-3 5 10 18 5m0 5q14-14 18-4-4 9-18 5" fill="#68c982"/><g fill="#ff85b5" stroke="#8e426b" stroke-width="2"><circle cx="32" cy="17" r="10"/><circle cx="19" cy="25" r="10"/><circle cx="45" cy="25" r="10"/><circle cx="24" cy="38" r="10"/><circle cx="40" cy="38" r="10"/></g><circle cx="32" cy="28" r="8" fill="#ffd34f"/>',
 tree:'<path d="M27 37h11v23H27z" fill="#a86b42"/><circle cx="32" cy="20" r="19" fill="#6bd18b" stroke="#286d4a" stroke-width="3"/><circle cx="18" cy="31" r="11" fill="#82df8f"/><circle cx="46" cy="31" r="11" fill="#82df8f"/>',
 sun:'<circle cx="32" cy="32" r="14" fill="#ffcf4b" stroke="#a56b1e" stroke-width="3"/><path d="M32 3v9m0 40v9M3 32h9m40 0h9M11 11l7 7m28 28 7 7m0-42-7 7m-28 28-7 7" stroke="#ffcf4b" stroke-width="5" stroke-linecap="round"/>',
 moon:'<path d="M47 10A25 25 0 1 0 54 49 22 22 0 0 1 47 10Z" fill="#e7edff" stroke="#6c83b3" stroke-width="3"/>',
 star:'<path d="m32 4 8 19 21 2-16 14 5 21-18-11-18 11 5-21L3 25l21-2z" fill="#ffd34d" stroke="#9a6923" stroke-width="3" stroke-linejoin="round"/>',
 diamond:'<path d="M32 4 59 24 32 60 5 24Z" fill="#7be3ef" stroke="#286d88" stroke-width="3"/><path d="M5 24h54M20 24l12 36 12-36M20 24l12-20 12 20" fill="none" stroke="#d8ffff" stroke-width="2"/>',
 guitar:'<path d="M27 36q-15-8-19 5-5 16 11 17 13 0 13-15l7-7-7-7z" fill="#f2a64e" stroke="#70431d" stroke-width="3"/><path d="m32 33 22-22 5 5-22 22" fill="#c78b4c" stroke="#70431d" stroke-width="3"/><circle cx="20" cy="48" r="5" fill="#fff0bd"/>',
 football:'<path d="M32 5c18 0 27 12 27 27S50 59 32 59 5 47 5 32 14 5 32 5Z" fill="#f4f5f8" stroke="#384b68" stroke-width="3"/><path d="m32 19 9 7-4 11H27l-4-11z" fill="#33445c"/><path d="m23 26-12-5m30 5 12-5M27 37l-7 13m17-13 7 13" stroke="#33445c" stroke-width="3"/>',
 basketball:'<circle cx="32" cy="32" r="26" fill="#f28a3b" stroke="#713b1c" stroke-width="3"/><path d="M32 6v52M6 32h52M13 13q19 19 38 38M51 13Q32 32 13 51" fill="none" stroke="#713b1c" stroke-width="3"/>',
 pizza:'<path d="m8 12 49 13-29 35z" fill="#ffd36a" stroke="#9c5a2b" stroke-width="3" stroke-linejoin="round"/><path d="m8 12 49 13-6 8-40-11z" fill="#e96d4f"/><circle cx="30" cy="30" r="4" fill="#e85d4f"/><circle cx="40" cy="42" r="4" fill="#e85d4f"/>',
 icecream:'<path d="m18 34 14 27 14-27z" fill="#d69a54" stroke="#80542d" stroke-width="3"/><circle cx="32" cy="25" r="16" fill="#ff9bb8" stroke="#8e4d6c" stroke-width="3"/><circle cx="27" cy="20" r="4" fill="#fff1bd"/>',
 sailboat:'<path d="M6 43h52L46 56H18z" fill="#64c8dc" stroke="#285a70" stroke-width="3"/><path d="M31 5v36H11z" fill="#ffda70" stroke="#805d2c" stroke-width="3"/><path d="M36 14v27h17z" fill="#fff" stroke="#607c9a" stroke-width="3"/>',
 scooter:'<path d="M13 49h40M21 49l7-20h13l5 20M29 29V9h12" fill="none" stroke="#ffbf4d" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="17" cy="51" r="6" fill="#263447"/><circle cx="52" cy="51" r="6" fill="#263447"/>',
 ship:'<path d="M7 38h50L47 54H18z" fill="#e87958" stroke="#653e35" stroke-width="3"/><path d="M16 12h32v20H16z" fill="#fff0bc" stroke="#765b35" stroke-width="3"/><path d="M23 18h8v8h-8zm12 0h8v8h-8z" fill="#79c9e8"/>',
 trophy:'<path d="M18 8h28v16q0 18-14 18T18 24z" fill="#ffd24f" stroke="#80541b" stroke-width="3"/><path d="M18 14H7v8q0 12 14 12m25-20h11v8q0 12-14 12M32 42v12m-13 5h26" fill="none" stroke="#e8b44a" stroke-width="5" stroke-linecap="round"/>',
 lamp:'<path d="m20 8 24 0 8 20H12z" fill="#ffda70" stroke="#815c2d" stroke-width="3"/><path d="M32 28v25m-13 5h26" stroke="#b4c8e6" stroke-width="5" stroke-linecap="round"/>',
 book:'<path d="M7 12q14-7 25 3 11-10 25-3v42q-14-7-25 3-11-10-25-3z" fill="#72c9a0" stroke="#285b4a" stroke-width="3"/><path d="M32 15v42M13 22q8-3 14 1m-14 8q8-3 14 1m19-10q7-4 13-1" stroke="#fff" stroke-width="3" fill="none"/>',
 glasses:'<circle cx="18" cy="32" r="13" fill="none" stroke="#6bd6ed" stroke-width="5"/><circle cx="46" cy="32" r="13" fill="none" stroke="#6bd6ed" stroke-width="5"/><path d="M31 30h2M5 28 2 22m57 6 3-6" stroke="#6bd6ed" stroke-width="4"/>',
 bell:'<path d="M12 44h40l-5-7V25a15 15 0 0 0-30 0v12z" fill="#ffcf52" stroke="#80561d" stroke-width="3"/><path d="M26 50q6 12 12 0" fill="none" stroke="#80561d" stroke-width="4"/>',
 anchor:'<circle cx="32" cy="10" r="6" fill="none" stroke="#91d7ef" stroke-width="4"/><path d="M32 16v38M18 27h28M8 39q0 18 24 18t24-18M8 39l-5 8m54-8 5 8" fill="none" stroke="#91d7ef" stroke-width="5" stroke-linecap="round"/>',
 pencil:'<path d="m12 48 5-15L45 5l14 14-28 28-15 5z" fill="#ffcf4e" stroke="#80521e" stroke-width="3"/><path d="m45 5 14 14M17 33l14 14" stroke="#fff1bd" stroke-width="3"/>',
 watch:'<path d="M24 4h16l3 15H21zM21 45h22l-3 15H24z" fill="#f4c65a" stroke="#805d2d" stroke-width="3"/><rect x="14" y="17" width="36" height="30" rx="8" fill="#78cfe8" stroke="#315c78" stroke-width="3"/><circle cx="32" cy="32" r="10" fill="#fff2c8" stroke="#315c78" stroke-width="2"/>',
 camera2:'<rect x="6" y="16" width="52" height="36" rx="7" fill="#82d6c0" stroke="#285e58" stroke-width="3"/><circle cx="32" cy="34" r="12" fill="#5a779b" stroke="#fff" stroke-width="4"/><path d="M18 16 23 9h18l5 7" fill="#ffd45c" stroke="#285e58" stroke-width="3"/>'
};
function findIcon(name){
 const shape=findShapes[name]||findShapes.star;
 return '<svg viewBox="0 0 64 64" role="img" aria-label="'+safe(name)+'" xmlns="http://www.w3.org/2000/svg">'+shape+'</svg>';
}
/* Number-room form layout: keep every label and input on its own clear row. */
const casualFormStyle=document.createElement("style");
casualFormStyle.id="casual-number-form-layout";
casualFormStyle.textContent=`
#casual-shell .c4-panel > label.c4-label{display:block;width:100%;margin:15px 0 7px;line-height:1.45;text-align:right}
#casual-shell .c4-panel > input#casual-min,
#casual-shell .c4-panel > input#casual-max,
#casual-shell .c4-panel > input#casual-attempts,
#casual-shell .c4-panel > input#casual-turn-seconds{display:block;width:100%;min-height:49px;margin:0 0 12px;padding:12px 15px;border:1px solid #ffffff45;border-radius:12px;background:#17090b;color:#fff;font:inherit;font-size:17px;text-align:center;direction:ltr;outline:none;box-shadow:inset 0 2px 6px #0005}
#casual-shell .c4-panel > input#casual-min:focus,
#casual-shell .c4-panel > input#casual-max:focus,
#casual-shell .c4-panel > input#casual-attempts:focus,
#casual-shell .c4-panel > input#casual-turn-seconds:focus{border-color:#ff9aa2;box-shadow:0 0 0 2px #ff596933}
#casual-shell #casual-levels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:8px 0 15px}
#casual-shell #casual-levels .c4-level{min-height:62px;padding:10px 8px;line-height:1.4}
#casual-shell #casual-levels .c4-level small{display:block;margin-top:4px}
#casual-shell .c4-panel > .c4-label{font-size:14px}
`;
if(!document.getElementById(casualFormStyle.id))document.head.append(casualFormStyle);


const api=async(action,game_id="",extra={})=>{
 const r=await fetch("/api/casual-games",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({initData:tg?.initData||"",action,game_id,...extra})});
 const d=await r.json().catch(()=>({}));if(!r.ok||!d.ok)throw new Error(d.error||"تعذر تنفيذ الطلب");return d.result;
};
let current=null,gameType="",poll=null,lock=false,hideTimer=null,countdown=null,memoryLastCards={};
const shell=()=>{document.body.classList.add("c4-active");pageContent.innerHTML='<div class="c4-shell" id="casual-shell"></div>';return document.getElementById("casual-shell");};
const err=e=>{const root=document.getElementById("casual-shell");if(root){let x=root.querySelector(".c4-error");if(!x){x=document.createElement("div");x.className="c4-error";root.append(x);}x.textContent=e?.message||"حدث خطأ";}};
const stop=()=>{if(poll)clearTimeout(poll);if(hideTimer)clearTimeout(hideTimer);if(countdown)clearInterval(countdown);poll=hideTimer=countdown=null;current=null;lock=false;memoryLastCards={};const mainBackButton=document.getElementById("back-home");if(mainBackButton)mainBackButton.hidden=false;};
const request=async(action,extra={})=>{const result=await api(action,current?.id||"",extra);current=result;return result;};
function heading(title,sub){return '<div class="c4-heading"><h2>'+title+'</h2><p>'+sub+'</p></div>';}
window.startCasualSetup=function(type){
 stop();gameType=type;const root=shell();
 const isMatch=type==="match",isFind=type==="find";
 root.innerHTML=heading(isFind?"Find Match 🔎":isMatch?"تطابق البطاقات 🃏":"خمن الرقم 🔢",isFind?"اكتشف الغرض المشترك قبل خصمك":"اختر طريقة اللعب والإعدادات")+
 '<div class="c4-panel"><div class="c4-label">طريقة اللعب</div><div class="c4-levels"><button class="c4-level active" data-mode="bot">🤖 ضد البوت</button><button class="c4-level" data-mode="online">👥 أونلاين</button></div>'+
 (isFind?'<label class="c4-label">النقاط المطلوبة للفوز</label><select id="casual-target-score" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white">'+Array.from({length:10},(_,i)=>'<option value="'+(i+1)+'"'+(i===4?' selected':'')+'>'+(i+1)+' نقاط</option>').join('')+'</select>':(isMatch?'<label class="c4-label">عدد البطاقات</label><select id="casual-count" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white"><option>12</option><option selected>16</option><option>20</option><option>24</option><option>30</option></select>':
 '<label class="c4-label">أقل رقم</label><input id="casual-min" type="number" value="1" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white"><label class="c4-label">أعلى رقم</label><input id="casual-max" type="number" value="100" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white"><label class="c4-label">عدد المحاولات</label><input id="casual-attempts" type="number" min="1" max="30" value="7" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white">'))+
 (isFind?'':'<label class="c4-label">مدة الدور (5–60 ثانية)</label><input id="casual-turn-seconds" type="number" min="5" max="60" step="5" value="20" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white">')+'<div class="c4-label" style="margin-top:15px">مستوى التحدي</div><div class="c4-levels" id="casual-levels"></div><button class="c4-start" id="casual-create">ابدأ اللعب</button><button class="c4-secondary" id="casual-back">رجوع للألعاب</button><div class="c4-hint">'+(isFind?'اختر عدد النقاط للفوز، وأسرع لاعب يخطف النقطة في كل جولة':'كل لاعب ينافس بشكل فردي · بدون نقاط أو رهانات')+'</div></div>';
 let mode="bot",difficulty="متوسط";
 root.querySelectorAll("[data-mode]").forEach(b=>b.onclick=()=>{mode=b.dataset.mode;root.querySelectorAll("[data-mode]").forEach(x=>x.classList.toggle("active",x===b));});
 const levels=root.querySelector("#casual-levels");
 [["سهل","تحدي بسيط"],["متوسط","متوازن"],["صعب","أذكى"],["مستحيل","أعلى صعوبة"]].forEach(([v,d])=>{const b=document.createElement("button");b.className="c4-level"+(v===difficulty?" active":"");b.innerHTML=v+"<small>"+d+"</small>";b.onclick=()=>{difficulty=v;if(!isMatch&&!isFind){root.querySelector("#casual-attempts").value=({"سهل":12,"متوسط":7,"صعب":5,"مستحيل":3})[v];}levels.querySelectorAll("button").forEach(x=>x.classList.toggle("active",x===b));};levels.append(b);});
 root.querySelector("#casual-create").onclick=async()=>{try{const settings=isFind?{difficulty,target_score:Number(root.querySelector("#casual-target-score").value)}:(isMatch?{card_count:Number(root.querySelector("#casual-count").value),difficulty}:{min:Number(root.querySelector("#casual-min").value),max:Number(root.querySelector("#casual-max").value),attempts:Number(root.querySelector("#casual-attempts").value),difficulty});if(!isFind)settings.turn_seconds=Math.min(60,Math.max(5,Number(root.querySelector("#casual-turn-seconds").value)||20));current=await api("create","",{game_type:type,mode,settings});if(mode==="online")renderLobby();else renderGame();}catch(e){err(e);}};
 root.querySelector("#casual-back").onclick=showGames;
};
function shareRoom(){const link="https://t.me/"+botUsername+"?startapp=casual_"+gameType+"_"+current.id;const share="https://t.me/share/url?url="+encodeURIComponent(link);if(tg?.openTelegramLink)tg.openTelegramLink(share);else if(navigator.clipboard)navigator.clipboard.writeText(link);}
function renderLobby(){
 const root=shell(),owner=current.is_owner,players=current.players||[],isMatch=gameType==="match",isFind=gameType==="find";
 root.innerHTML=heading(isFind?"غرفة Find Match 🔎":isMatch?"غرفة تطابق البطاقات 🃏":"غرفة خمن الرقم 🔢",isFind?"انضم لاعب واحد لتبدأ المنافسة":"انضموا للغرفة (حتى 4 لاعبين)، وكل لاعب ينافس لحاله")+
 '<div class="c4-panel"><div class="c4-label">اللاعبون ('+players.length+(isFind?'/2':'/4')+')</div><div class="mg-score">'+players.map(p=>'<span>'+safe(p.name)+'</span>').join("")+'</div>'+
 (owner?(isFind?'<label class="c4-label">النقاط المطلوبة للفوز</label><select id="casual-target-score" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white">'+Array.from({length:10},(_,i)=>'<option value="'+(i+1)+'"'+(Number(current.settings.target_score||5)===i+1?' selected':'')+'>'+(i+1)+' نقاط</option>').join('')+'</select>':(isMatch?'<label class="c4-label">عدد البطاقات</label><select id="casual-count" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white"><option>12</option><option selected>16</option><option>20</option><option>24</option><option>30</option></select>':
 '<label class="c4-label">أقل رقم</label><input id="casual-min" type="number" value="'+current.settings.min+'"><label class="c4-label">أعلى رقم</label><input id="casual-max" type="number" value="'+current.settings.max+'"><label class="c4-label">عدد المحاولات</label><input id="casual-attempts" type="number" value="'+current.settings.attempts+'">'))+(isFind?'':'<label class="c4-label">مدة الدور (5–60 ثانية)</label><input id="casual-turn-seconds" type="number" min="5" max="60" step="5" value="'+(current.settings.turn_seconds||20)+'" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white">')+'<button class="c4-secondary" id="casual-save">حفظ الإعدادات</button>':'')+
 (owner?'<button class="c4-start" id="casual-start" style="display:block;width:100%;min-height:54px;margin:12px 0 0" '+(players.length<2?"disabled":"")+'>ابدأ اللعبة</button>':'<div class="c4-hint">بانتظار صاحب الغرفة لبدء اللعبة</div>')+
 '<button class="c4-secondary" id="casual-share">مشاركة الغرفة</button><button class="c4-secondary" id="casual-back">رجوع للألعاب</button><div class="c4-hint">بدون نقاط أو رهانات</div></div>';
 root.querySelector("#casual-back").onclick=()=>{stop();showGames();};
 const share=root.querySelector("#casual-share");if(share)share.onclick=shareRoom;
 const save=root.querySelector("#casual-save");if(save)save.onclick=async()=>{try{const settings=isFind?{difficulty:current.settings.difficulty,target_score:Number(root.querySelector("#casual-target-score").value)}:(isMatch?{card_count:Number(root.querySelector("#casual-count").value)}:{min:Number(root.querySelector("#casual-min").value),max:Number(root.querySelector("#casual-max").value),attempts:Number(root.querySelector("#casual-attempts").value)});if(!isFind)settings.turn_seconds=Number(root.querySelector("#casual-turn-seconds").value);current=await request("configure",{settings});renderLobby();}catch(e){err(e);}};
 const start=root.querySelector("#casual-start");if(start)start.onclick=async()=>{try{current=await request("start");renderGame();}catch(e){err(e);}};
 schedulePoll();
}
function addTurnControls(root,isPlayer,myTurn){
 if(!isPlayer)return;
 const wrap=document.createElement("div");
 wrap.style.cssText="display:flex;justify-content:flex-end;align-items:center;position:relative;width:100%;min-height:38px;margin:8px 0 12px";
 const timer=document.createElement("span");
 timer.id="casual-turn-timer";
 timer.style.cssText="position:absolute;left:50%;transform:translateX(-50%);font-weight:800;color:#ffd6d6;font-size:14px;white-space:nowrap;text-align:center";
 const leave=document.createElement("button");
 leave.textContent="انسحاب";
 leave.style.cssText="margin-left:auto;background:#d92332;color:#fff;border:0;border-radius:10px;padding:8px 16px;font-weight:800";
 leave.onclick=async()=>{if(!confirm("هل أنت متأكد من الانسحاب؟ سيُعلن فوز اللاعب الآخر."))return;leave.disabled=true;try{current=await request("leave");finishGame();}catch(e){leave.disabled=false;err(e);}};
 if(myTurn){
  if(countdown)clearInterval(countdown);
  const tick=()=>{const left=Math.max(0,Number(current?.turn_deadline||0)-Math.floor(Date.now()/1000));timer.textContent="⏳ "+left+" ثانية";timer.style.color=left<=5?"#ff5555":"#ffd6d6";};
  tick();countdown=setInterval(tick,250);
 }else{
  if(countdown)clearInterval(countdown);countdown=null;
  timer.textContent="بانتظار دورك";
  timer.style.color="#aaa";
 }
 wrap.append(timer,leave);
 const score=root.querySelector(".mg-score");
 if(score)score.insertAdjacentElement("afterend",wrap);else root.prepend(wrap);
}
function safe(v){return String(v||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function schedulePoll(){
 if(poll)clearTimeout(poll);
 const delay=current?.game_type==="find"?(current?.mode==="bot"?300:700):1400;
 poll=setTimeout(async()=>{try{if(!current)return;let next=await api("state",current.id);if(next.game_type==="find"&&next.mode==="bot"&&next.status==="playing")next=await api("bot-turn",next.id);if(JSON.stringify(next)!==JSON.stringify(current)){current=next;if(current.status==="waiting")renderLobby();else renderGame();return;}}catch(e){}if(current&&current.status!=="finished")schedulePoll();},delay);
}
function renderGame(){
 const root=shell(),isMatch=gameType==="match",isFind=gameType==="find";
 const mainBackButton=document.getElementById("back-home");
 if(mainBackButton)mainBackButton.hidden=gameType==="number";
 if(current.status==="finished"){finishGame();return;}
 if(isFind){renderFind(root);schedulePoll();return;}
 if(isMatch){
  const me=Number(tg?.initDataUnsafe?.user?.id||0),players=current.players||[],turn=players[current.turn_index]||players[0],isPlayer=players.some(p=>Number(p.id)===me),myTurn=isPlayer&&Number(turn?.id)===me;
  root.innerHTML=heading("تطابق البطاقات 🃏","طابق الأزواج واجمع أكبر عدد")+
  '<div class="mg-score">'+players.map((p,i)=>'<span>'+safe(p.name)+': '+(current.scores?.[i]||0)+'</span>').join("")+'</div>'+
  '<div class="c4-panel"><div class="c4-result show" id="casual-status">'+(!isPlayer?"👀 أنت متفرج على المباراة":(current.bot_pending?"البوت يفكر...":(myTurn?"دورك، اختر بطاقتين":"دور "+safe(turn?.name))))+'</div><div id="casual-board" style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:7px;margin-top:12px"></div><button class="c4-secondary" id="casual-back">رجوع للألعاب</button></div>';
  addTurnControls(root,isPlayer,myTurn);const board=root.querySelector("#casual-board");
  board.style.gridTemplateColumns="repeat("+(current.cards.length<=16?4:5)+",minmax(0,1fr))";
  const botBusy=!!current.bot_revealing;
  const nextMemoryVisual={};
  current.cards.forEach(card=>{
   const b=document.createElement("button");
   const key=String(current.id)+":"+String(card.index);
   const previous=memoryLastCards[key]||{value:null,matched:false};
   const isRevealed=card.value!==null;
   const justFlippedIn=isRevealed&&previous.value===null&&!previous.matched;
   const justFlippedOut=!isRevealed&&previous.value!==null&&!card.matched;
   const justMatched=!!card.matched&&!previous.matched;
   b.className="c4-level memory-card"+(card.matched?" matched":"")+(isRevealed?" revealed":" face-down")+(justFlippedIn?" flip-in":"")+(justFlippedOut?" flip-out":"")+(justMatched?" just-matched":"");
   b.style.minHeight="58px";b.style.padding="4px";b.style.fontSize="25px";
   const face=document.createElement("span");face.className="memory-face";face.textContent=card.value||"❔";b.append(face);
   if(card.matched&&card.matched_by){
    const owner=document.createElement("small");owner.className="memory-owner";owner.textContent=card.matched_by;b.append(owner);
   }
   b.disabled=!!card.matched||!myTurn||current.bot_pending||botBusy||lock||card.value!==null;
   b.onclick=()=>flip(card.index);board.append(b);
   nextMemoryVisual[key]={value:card.value,matched:!!card.matched};
  });
  memoryLastCards=nextMemoryVisual;
  root.querySelector("#casual-back").onclick=()=>{stop();showGames();};
  if(!hideTimer && current.first!==null && current.second!==null){
   hideTimer=setTimeout(async()=>{
    hideTimer=null;
    try{current=await request("action",{move:{action:"continue"}});renderGame();}
    catch(e){err(e);}
   },1300);
  }else if(!hideTimer && current.bot_revealing && current.bot_step===1){
   hideTimer=setTimeout(async()=>{
    hideTimer=null;
    try{current=await api("bot-turn",current.id);renderGame();}
    catch(e){err(e);}
   },1000);
  }else if(!hideTimer && current.bot_revealing && current.bot_step===2){
   hideTimer=setTimeout(async()=>{
    hideTimer=null;
    try{current=await request("action",{move:{action:"continue"}});renderGame();}
    catch(e){err(e);}
   },1400);
  }else if(!hideTimer && current.bot_pending && !current.bot_revealing && current.first===null){
   hideTimer=setTimeout(async()=>{
    hideTimer=null;
    try{current=await api("bot-turn",current.id);renderGame();}
    catch(e){err(e);}
   },2000);
  }
 }else{
  const me=Number(tg?.initDataUnsafe?.user?.id||0),guesses=current.guesses||[],players=current.players||[];
  const isPlayer=players.some(p=>Number(p.id)===me);
  const myTurn=isPlayer&&(current.mode!=="online"||Number(players[current.turn_index||0]?.id)===me);
  root.innerHTML=heading("خمن الرقم 🔢","اختر رقمًا بين "+current.min+" و "+current.max)+
  '<div class="mg-score">'+players.map((p)=>'<span>'+safe(p.name)+'</span>').join("")+'</div>'+
  '<div class="c4-panel"><div class="c4-result show" id="casual-hint">'+(current.hint||"بانتظار أول تخمين")+'</div><div class="c4-label">المحاولات: '+current.attempts_used+' / '+current.max_attempts+'</div><input id="casual-guess" type="number" min="'+current.min+'" max="'+current.max+'" placeholder="اكتب رقمك" style="width:100%;padding:14px;border-radius:12px;background:#17090b;color:white;font-size:18px;text-align:center"><div class="word-history" id="casual-history"></div><button class="c4-start" id="casual-guess-btn" style="display:block;width:100%;min-height:52px;margin-top:14px;font-size:18px">تخمين</button><button class="c4-secondary" id="casual-back" style="margin-top:82px">↩️ الرجوع للألعاب</button><button class="c4-secondary" id="casual-home" style="margin-top:16px">↩️ الرجوع للقائمة الرئيسية</button></div>';
  addTurnControls(root,isPlayer,myTurn);root.querySelector("#casual-history").innerHTML=guesses.map(g=>'<div class="custom-card">'+safe(g.name)+' — '+g.guess+' : '+safe(g.hint)+'</div>').join("");
  const input=root.querySelector("#casual-guess"),btn=root.querySelector("#casual-guess-btn");
  if(!isPlayer){input.disabled=true;btn.disabled=true;root.querySelector("#casual-hint").textContent="👀 أنت متفرج على المباراة.";}
  else if(current.mode==="online"&&Number((current.players||[]).findIndex(p=>Number(p.id)===me))!==Number(current.turn_index||0)){input.disabled=true;btn.disabled=true;root.querySelector("#casual-hint").textContent="انتظر دور "+safe(current.players?.[current.turn_index]?.name||"اللاعب");}
  else if(current.attempts_used>=current.max_attempts){input.disabled=true;btn.disabled=true;root.querySelector("#casual-hint").textContent="انتهت محاولاتك، انتظر بقية اللاعبين.";}
  btn.onclick=async()=>{if(lock||input.disabled)return;lock=true;btn.disabled=true;try{current=await request("action",{move:{guess:Number(input.value)}});renderGame();}catch(e){err(e);btn.disabled=false;}finally{lock=false;}};
  input.addEventListener("keydown",e=>{if(e.key==="Enter")btn.click();});
  root.querySelector("#casual-back").onclick=()=>{stop();showGames();};
  root.querySelector("#casual-home").onclick=()=>{stop();showHome();};

 }
 schedulePoll();
}
function renderFind(root){
 const me=Number(tg?.initDataUnsafe?.user?.id||0),players=current.players||[],isPlayer=players.some(p=>Number(p.id)===me);
 const score=(current.scores||[]).map((v,i)=>'<span>'+safe(players[i]?.name||"لاعب")+': '+v+' / '+current.target_score+'</span>').join("");
 const roundWinner=players.find(p=>Number(p.id)===Number(current.round_winner_id));
 const waiting=!!current.round_winner_id;
 const banner=waiting?'<div class="find-round-banner">'+safe(roundWinner?.name||"أحد اللاعبين")+' خطف النقطة! 🏆<br><small>استعدوا للجولة التالية...</small></div>':'';
 const status=waiting?"تم حسم الجولة":(isPlayer?(current.wrong_by===me?"مو هذا الغرض، جرّب مرة ثانية":"اضغط على الغرض المشترك في أي دائرة أولًا"):"مشاهدة المباراة");
 root.innerHTML=heading("Find Match","ابحث عن الشكل المتكرر واضغط عليه قبل خصمك")+
 '<div class="mg-score find-score">'+score+'</div>'+banner+'<div class="find-status" id="find-status">'+status+'</div>'+
 '<div class="find-duel"><div class="find-side"><div class="find-side-title">الدائرة الأولى</div><div class="find-circle" id="find-left"></div></div><div class="find-side"><div class="find-side-title">الدائرة الثانية</div><div class="find-circle" id="find-right"></div></div></div>'+
 '<div class="find-footer">الجولة '+current.round+' · الفوز عند الوصول إلى '+current.target_score+' نقاط</div>';
 const add=(id,items)=>{const board=root.querySelector("#"+id);(items||[]).forEach(value=>{const b=document.createElement("button");b.className="find-item";b.type="button";b.setAttribute("aria-label","اختر الشكل");b.innerHTML=findIcon(value);b.disabled=!isPlayer||lock||waiting;b.onclick=()=>findPick(value);board.append(b);});};
 add("find-left",current.left_items);add("find-right",current.right_items);
}
async function findPick(value){if(lock||current?.status!=="playing"||current?.round_winner_id)return;lock=true;try{current=await request("action",{move:{value,round:current.round}});lock=false;renderGame();}catch(e){lock=false;err(e);}}
async function flip(index){if(lock)return;lock=true;try{current=await request("action",{move:{index}});lock=false;renderGame();}catch(e){lock=false;err(e);}}
function finishGame(){
 if(poll)clearTimeout(poll);poll=null;
 if(gameType==="find"){
  const players=current.players||[],winner=players.find(p=>Number(p.id)===Number(current.winner_id));
  const win=Number(current.winner_id)===Number(tg?.initDataUnsafe?.user?.id||0);
  showGameEndOverlay({winnerName:winner?.name||"الفائز",isDraw:false,gameType,title:"🏆 انتهت Find Match",subtitle:win?"فزت! أسرع عين 👀🏆":"فاز "+(winner?.name||"خصمك")+"! حاول مرة ثانية"});
 }else if(gameType==="match"){
  const players=current.players||[],scores=current.scores||[],high=Math.max(...scores),winners=players.filter((p,i)=>scores[i]===high);
  if(current.winner_id!==null&&current.winner_id!==undefined){const winner=players.find(p=>Number(p.id)===Number(current.winner_id));const reason=current.end_reason==="timeout"?"لأن خصمه انتهى وقته ⏰":current.end_reason==="withdraw"?"بعد انسحاب خصمه 🏳️":"فاز بالمباراة";showGameEndOverlay({winnerName:winner?.name||"الفائز",isDraw:false,gameType,subtitle:"فاز "+(winner?.name||"اللاعب")+" "+reason+" 🏆"});}
  else {const draw=winners.length!==1;showGameEndOverlay({winnerName:draw?"":winners[0]?.name,isDraw:draw,gameType,subtitle:draw?"تعادل! أحسنتم جميعًا 👏":("أبدع "+winners[0].name+" وجمع "+high+" أزواج 🏆")});}
 }else{
  const win=Number(current.winner_id)===Number(tg?.initDataUnsafe?.user?.id||0);if(countdown)clearInterval(countdown);countdown=null;
  showGameEndOverlay({winnerName:win?telegramDisplayName():(current.players||[]).find(p=>Number(p.id)===Number(current.winner_id))?.name||"لم يفز أحد",isDraw:false,gameType,title:current.winner_id?"🎉 انتهت اللعبة":"انتهت اللعبة",subtitle:win?"عرفت الرقم الصحيح! مبروك 🎉":(current.winner_id?"سبقك لاعب آخر للرقم الصحيح":"انتهت المحاولات، الرقم كان "+current.secret)});
 }
}
window.startCasualGame=async function(startParam){
 stop();const parts=String(startParam||"").split("_");gameType=parts[1];const id=parts[2];
 home.hidden=true;page.hidden=false;pageTitle.textContent=gameType==="find"?"Find Match":gameType==="match"?"تطابق البطاقات":"خمن الرقم";
 try{current=await api("join",id);if(current.status==="waiting")renderLobby();else renderGame();}catch(e){const root=shell();root.innerHTML='<div class="c4-panel"></div>';err(e);}
};
window.stopCasualGame=stop;
})();
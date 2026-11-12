(function(){
const memoryStyle=document.createElement("style");
memoryStyle.id="casual-memory-card-styles";
memoryStyle.textContent=".memory-card{position:relative;min-height:66px!important;overflow:hidden;border:1px solid rgba(255,255,255,.13)!important;border-radius:14px!important;background:linear-gradient(145deg,#341116,#17090d)!important;color:#fff!important;box-shadow:0 5px 12px rgba(0,0,0,.24);transition:transform .45s cubic-bezier(.2,.75,.25,1),background .4s ease,border-color .4s ease,box-shadow .4s ease;transform-style:preserve-3d}\n.memory-card:not(:disabled){cursor:pointer}\n.memory-card:not(:disabled):active{transform:scale(.96)}\n.memory-card .memory-face{display:block;transition:transform .42s cubic-bezier(.2,.75,.25,1);backface-visibility:hidden}\n.memory-card.revealed{background:linear-gradient(145deg,#fff1f2,#e7c5ca)!important;color:#351016!important;border-color:#fff!important;box-shadow:0 0 14px rgba(255,190,200,.22)}\n.memory-card.flip-in{animation:memoryFlipIn .42s cubic-bezier(.2,.75,.25,1) both}\n.memory-card.flip-out{animation:memoryFlipOut .48s cubic-bezier(.2,.75,.25,1) both}\n.memory-card.matched{background:linear-gradient(145deg,#236b4a,#123c2b)!important;color:#fff!important;border:1px solid #7df0b2!important;box-shadow:0 0 16px rgba(80,230,150,.3);opacity:1}\n.memory-card.just-matched{animation:memoryMatch .42s ease both}\n.memory-owner{position:absolute;top:3px;left:4px;right:4px;display:block;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:9px;line-height:12px;font-weight:700;color:#d8ffe8;text-align:center;pointer-events:none}\n.memory-card.matched .memory-face{padding-top:9px}\n@keyframes memoryFlipIn{0%{transform:perspective(500px) rotateY(88deg) scale(.96)}65%{transform:perspective(500px) rotateY(-8deg) scale(1.02)}100%{transform:perspective(500px) rotateY(0) scale(1)}}\n@keyframes memoryFlipOut{0%{transform:perspective(500px) rotateY(0) scale(1)}55%{transform:perspective(500px) rotateY(82deg) scale(.97)}100%{transform:perspective(500px) rotateY(0) scale(1)}}\n@keyframes memoryMatch{0%{transform:scale(.92)}65%{transform:scale(1.05)}100%{transform:scale(1)}}";
if(!document.getElementById(memoryStyle.id)) document.head.append(memoryStyle);

const api=async(action,game_id="",extra={})=>{
 const r=await fetch("/api/casual-games",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({initData:tg?.initData||"",action,game_id,...extra})});
 const d=await r.json().catch(()=>({}));if(!r.ok||!d.ok)throw new Error(d.error||"تعذر تنفيذ الطلب");return d.result;
};
let current=null,gameType="",poll=null,lock=false,hideTimer=null,countdown=null,memoryLastCards={};
const shell=()=>{document.body.classList.add("c4-active");pageContent.innerHTML='<div class="c4-shell" id="casual-shell"></div>';return document.getElementById("casual-shell");};
const err=e=>{const root=document.getElementById("casual-shell");if(root){let x=root.querySelector(".c4-error");if(!x){x=document.createElement("div");x.className="c4-error";root.append(x);}x.textContent=e?.message||"حدث خطأ";}};
const stop=()=>{if(poll)clearTimeout(poll);if(hideTimer)clearTimeout(hideTimer);if(countdown)clearInterval(countdown);poll=hideTimer=countdown=null;current=null;lock=false;memoryLastCards={};};
const request=async(action,extra={})=>{const result=await api(action,current?.id||"",extra);current=result;return result;};
function heading(title,sub){return '<div class="c4-heading"><h2>'+title+'</h2><p>'+sub+'</p></div>';}
window.startCasualSetup=function(type){
 stop();gameType=type;const root=shell();
 const isMatch=type==="match";
 root.innerHTML=heading(isMatch?"تطابق البطاقات 🃏":"خمن الرقم 🔢","اختر طريقة اللعب والإعدادات")+
 '<div class="c4-panel"><div class="c4-label">طريقة اللعب</div><div class="c4-levels"><button class="c4-level active" data-mode="bot">🤖 ضد البوت</button><button class="c4-level" data-mode="online">👥 أونلاين</button></div>'+
 (isMatch?'<label class="c4-label">عدد البطاقات</label><select id="casual-count" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white"><option>12</option><option selected>16</option><option>20</option><option>24</option><option>30</option></select>':
 '<label class="c4-label">أقل رقم</label><input id="casual-min" type="number" value="1" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white"><label class="c4-label">أعلى رقم</label><input id="casual-max" type="number" value="100" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white"><label class="c4-label">عدد المحاولات</label><input id="casual-attempts" type="number" min="1" max="30" value="7" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white">')+
 '<div class="c4-label" style="margin-top:15px">مستوى التحدي</div><div class="c4-levels" id="casual-levels"></div><button class="c4-start" id="casual-create">ابدأ اللعب</button><button class="c4-secondary" id="casual-back">رجوع للألعاب</button><div class="c4-hint">اللعبتان بدون نقاط أو رهانات نهائيًا</div></div>';
 let mode="bot",difficulty="متوسط";
 root.querySelectorAll("[data-mode]").forEach(b=>b.onclick=()=>{mode=b.dataset.mode;root.querySelectorAll("[data-mode]").forEach(x=>x.classList.toggle("active",x===b));});
 const levels=root.querySelector("#casual-levels");
 [["سهل","تحدي بسيط"],["متوسط","متوازن"],["صعب","أذكى"],["مستحيل","أعلى صعوبة"]].forEach(([v,d])=>{const b=document.createElement("button");b.className="c4-level"+(v===difficulty?" active":"");b.innerHTML=v+"<small>"+d+"</small>";b.onclick=()=>{difficulty=v;if(!isMatch){root.querySelector("#casual-attempts").value=({"سهل":12,"متوسط":7,"صعب":5,"مستحيل":3})[v];}levels.querySelectorAll("button").forEach(x=>x.classList.toggle("active",x===b));};levels.append(b);});
 root.querySelector("#casual-create").onclick=async()=>{try{const settings=isMatch?{card_count:Number(root.querySelector("#casual-count").value),difficulty}:{min:Number(root.querySelector("#casual-min").value),max:Number(root.querySelector("#casual-max").value),attempts:Number(root.querySelector("#casual-attempts").value),difficulty};current=await api("create","",{game_type:type,mode,settings});if(mode==="online")renderLobby();else renderGame();}catch(e){err(e);}};
 root.querySelector("#casual-back").onclick=showGames;
};
function shareRoom(){const link="https://t.me/"+botUsername+"?startapp=casual_"+gameType+"_"+current.id;const share="https://t.me/share/url?url="+encodeURIComponent(link);if(tg?.openTelegramLink)tg.openTelegramLink(share);else if(navigator.clipboard)navigator.clipboard.writeText(link);}
function renderLobby(){
 const root=shell(),owner=current.is_owner,players=current.players||[],isMatch=gameType==="match";
 root.innerHTML=heading(isMatch?"غرفة تطابق البطاقات 🃏":"غرفة خمن الرقم 🔢","انضموا للغرفة ثم يبدأ صاحبها اللعبة")+
 '<div class="c4-panel"><div class="c4-label">اللاعبون ('+players.length+'/2)</div><div class="mg-score">'+players.map(p=>'<span>'+safe(p.name)+'</span>').join("")+'</div>'+
 (owner?(isMatch?'<label class="c4-label">عدد البطاقات</label><select id="casual-count" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white"><option>12</option><option selected>16</option><option>20</option><option>24</option><option>30</option></select>':
 '<label class="c4-label">أقل رقم</label><input id="casual-min" type="number" value="'+current.settings.min+'"><label class="c4-label">أعلى رقم</label><input id="casual-max" type="number" value="'+current.settings.max+'"><label class="c4-label">عدد المحاولات</label><input id="casual-attempts" type="number" value="'+current.settings.attempts+'">')+'<button class="c4-secondary" id="casual-save">حفظ الإعدادات</button>':'')+
 '<button class="c4-start" id="casual-share">مشاركة رابط الغرفة</button>'+(owner?'<button class="c4-start" id="casual-start" '+(players.length<2?"disabled":"")+'>ابدأ اللعبة</button>':'<div class="c4-hint">بانتظار صاحب الغرفة لبدء اللعبة</div>')+
 '<button class="c4-secondary" id="casual-back">رجوع للألعاب</button><div class="c4-hint">بدون نقاط أو رهانات</div></div>';
 root.querySelector("#casual-share").onclick=shareRoom;
 root.querySelector("#casual-back").onclick=()=>{stop();showGames();};
 const save=root.querySelector("#casual-save");if(save)save.onclick=async()=>{try{const settings=isMatch?{card_count:Number(root.querySelector("#casual-count").value)}:{min:Number(root.querySelector("#casual-min").value),max:Number(root.querySelector("#casual-max").value),attempts:Number(root.querySelector("#casual-attempts").value)};current=await request("configure",{settings});renderLobby();}catch(e){err(e);}};
 const start=root.querySelector("#casual-start");if(start)start.onclick=async()=>{try{current=await request("start");renderGame();}catch(e){err(e);}};
 schedulePoll();
}
function addTurnControls(root,isPlayer){if(!isPlayer)return;const wrap=document.createElement("div");wrap.style.cssText="display:flex;justify-content:flex-end;align-items:center;gap:8px;margin:0 0 10px";const timer=document.createElement("span");timer.id="casual-turn-timer";timer.style.cssText="font-weight:800;color:#ffd6d6;font-size:14px";const leave=document.createElement("button");leave.textContent="انسحاب";leave.style.cssText="background:#d92332;color:#fff;border:0;border-radius:10px;padding:8px 16px;font-weight:800";leave.onclick=async()=>{if(!confirm("هل أنت متأكد من الانسحاب؟ سيُعلن فوز اللاعب الآخر."))return;leave.disabled=true;try{current=await request("leave");finishGame();}catch(e){leave.disabled=false;err(e);}};wrap.append(timer,leave);root.prepend(wrap);if(countdown)clearInterval(countdown);const tick=()=>{const left=Math.max(0,Number(current?.turn_deadline||0)-Math.floor(Date.now()/1000));timer.textContent="⏳ "+left+" ثانية";timer.style.color=left<=5?"#ff5555":"#ffd6d6";};tick();countdown=setInterval(tick,250);}
function safe(v){return String(v||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function schedulePoll(){
 if(poll)clearTimeout(poll);poll=setTimeout(async()=>{try{if(!current)return;const next=await api("state",current.id);if(JSON.stringify(next)!==JSON.stringify(current)){current=next;if(current.status==="waiting")renderLobby();else renderGame();return;}}catch(e){}if(current&&current.status!=="finished")schedulePoll();},1400);
}
function renderGame(){
 const root=shell(),isMatch=gameType==="match";
 if(current.status==="finished"){finishGame();return;}
 if(isMatch){
  const me=Number(tg?.initDataUnsafe?.user?.id||0),players=current.players||[],turn=players[current.turn_index]||players[0],isPlayer=players.some(p=>Number(p.id)===me),myTurn=isPlayer&&Number(turn?.id)===me;
  root.innerHTML=heading("تطابق البطاقات 🃏","طابق الأزواج واجمع أكبر عدد")+
  '<div class="mg-score">'+players.map((p,i)=>'<span>'+safe(p.name)+': '+(current.scores?.[i]||0)+'</span>').join("")+'</div>'+
  '<div class="c4-panel"><div class="c4-result show" id="casual-status">'+(!isPlayer?"👀 أنت متفرج على المباراة":(current.bot_pending?"البوت يفكر...":(myTurn?"دورك، اختر بطاقتين":"دور "+safe(turn?.name))))+'</div><div id="casual-board" style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:7px;margin-top:12px"></div><button class="c4-secondary" id="casual-back">رجوع للألعاب</button></div>';
  addTurnControls(root,isPlayer);const board=root.querySelector("#casual-board");
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
  const me=Number(tg?.initDataUnsafe?.user?.id||0),guesses=current.guesses||[];
  root.innerHTML=heading("خمن الرقم 🔢","اختر رقمًا بين "+current.min+" و "+current.max)+
  '<div class="c4-panel"><div class="c4-result show" id="casual-hint">'+(current.hint||"بانتظار أول تخمين")+'</div><div class="c4-label">المحاولات: '+current.attempts_used+' / '+current.max_attempts+'</div><input id="casual-guess" type="number" min="'+current.min+'" max="'+current.max+'" placeholder="اكتب رقمك" style="width:100%;padding:14px;border-radius:12px;background:#17090b;color:white;font-size:18px;text-align:center"><div class="word-history" id="casual-history"></div><button class="c4-start" id="casual-guess-btn" style="display:block;width:100%;min-height:52px;margin-top:14px;font-size:18px">تخمين</button><button class="c4-secondary" id="casual-back">رجوع للألعاب</button><button class="c4-secondary" id="casual-home">الرجوع للقائمة الرئيسية</button></div>';
  addTurnControls(root,isPlayer&&((current.players||[]).findIndex(p=>Number(p.id)===me)===Number(current.turn_index||0)));root.querySelector("#casual-history").innerHTML=guesses.map(g=>'<div class="custom-card">'+safe(g.name)+' — '+g.guess+' : '+safe(g.hint)+'</div>').join("");
  const input=root.querySelector("#casual-guess"),btn=root.querySelector("#casual-guess-btn");
  const isPlayer=(current.players||[]).some(p=>Number(p.id)===me);
  if(!isPlayer){input.disabled=true;btn.disabled=true;root.querySelector("#casual-hint").textContent="👀 أنت متفرج على المباراة.";}
  else if(current.attempts_used>=current.max_attempts){input.disabled=true;btn.disabled=true;root.querySelector("#casual-hint").textContent="انتهت محاولاتك، انتظر بقية اللاعبين.";}
  btn.onclick=async()=>{if(lock||input.disabled)return;lock=true;btn.disabled=true;try{current=await request("action",{move:{guess:Number(input.value)}});renderGame();}catch(e){err(e);btn.disabled=false;}finally{lock=false;}};
  input.addEventListener("keydown",e=>{if(e.key==="Enter")btn.click();});
  root.querySelector("#casual-back").onclick=()=>{stop();showGames();};
  root.querySelector("#casual-home").onclick=()=>{stop();showHome();};
 }
 schedulePoll();
}
async function flip(index){if(lock)return;lock=true;try{current=await request("action",{move:{index}});lock=false;renderGame();}catch(e){lock=false;err(e);}}
function finishGame(){
 if(poll)clearTimeout(poll);poll=null;
 if(gameType==="match"){
  const players=current.players||[],scores=current.scores||[],high=Math.max(...scores),winners=players.filter((p,i)=>scores[i]===high);
  const draw=winners.length!==1;showGameEndOverlay({winnerName:draw?"":winners[0]?.name,isDraw:draw,subtitle:draw?"تعادل! أحسنتم جميعًا 👏":("أبدع "+winners[0].name+" وجمع "+high+" أزواج 🏆")});
 }else{
  const win=Number(current.winner_id)===Number(tg?.initDataUnsafe?.user?.id||0);if(countdown)clearInterval(countdown);countdown=null;
  showGameEndOverlay({winnerName:win?telegramDisplayName():(current.players||[]).find(p=>Number(p.id)===Number(current.winner_id))?.name||"لم يفز أحد",isDraw:false,title:current.winner_id?"🎉 انتهت اللعبة":"انتهت اللعبة",subtitle:win?"عرفت الرقم الصحيح! مبروك 🎉":(current.winner_id?"سبقك لاعب آخر للرقم الصحيح":"انتهت المحاولات، الرقم كان "+current.secret)});
 }
}
window.startCasualGame=async function(startParam){
 stop();const parts=String(startParam||"").split("_");gameType=parts[1];const id=parts[2];
 home.hidden=true;page.hidden=false;pageTitle.textContent=gameType==="match"?"تطابق البطاقات":"خمن الرقم";
 try{current=await api("join",id);if(current.status==="waiting")renderLobby();else renderGame();}catch(e){const root=shell();root.innerHTML='<div class="c4-panel"></div>';err(e);}
};
window.stopCasualGame=stop;
})();
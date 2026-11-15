(function(){
const $=s=>document.querySelector(s),safe=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let game="",room=null,poll=null,lock=false,shownRound=0,animationTimer=null;
const tg=window.Telegram?.WebApp;
const api=async(action,extra={})=>{const r=await fetch("/api/quick-games",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({initData:tg?.initData||"",action,game_id:room?.id||"",...extra})});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||"تعذر تنفيذ الحركة");return d.result;};
function shell(){document.body.classList.add("c4-active");const page=document.getElementById("page"),home=document.getElementById("home");home.hidden=true;page.hidden=false;document.getElementById("page-title").textContent=game==="cups"?"الأكواب 🥤":"المؤقت ⏱️";const root=document.getElementById("page-content");root.innerHTML='<div id="quick-shell" class="c4-shell"></div>';return $("#quick-shell");}
function heading(title,sub){return '<div class="c4-heading"><h2>'+title+'</h2><p>'+sub+'</p></div>';}
function stop(){if(poll)clearTimeout(poll);if(animationTimer)clearTimeout(animationTimer);poll=animationTimer=null;room=null;lock=false;shownRound=0;document.body.classList.remove("c4-active");}
function schedule(){if(poll)clearTimeout(poll);poll=setTimeout(async()=>{try{if(!room)return;let next=await api("state");const changed=JSON.stringify(next)!==JSON.stringify(room);room=next;if(changed)render();}catch(e){}if(room&&room.status!=="finished")schedule();},800);}
window.startQuickGameSetup=function(type){stop();game=type;const root=shell();root.innerHTML=heading(type==="cups"?"الأكواب 🥤":"المؤقت ⏱️","اختر طريقة اللعب والإعدادات")+'<div class="c4-panel"><div class="c4-label">طريقة اللعب</div><div class="c4-levels"><button class="c4-level active" data-mode="bot">🤖 ضد البوت</button><button class="c4-level" data-mode="online">👥 أونلاين</button></div><div id="q-settings"></div><button class="c4-start" id="q-create">إنشاء اللعبة</button><button class="c4-secondary" id="q-back">رجوع للألعاب</button></div>';
let mode="bot",difficulty="متوسط";root.querySelectorAll("[data-mode]").forEach(b=>b.onclick=()=>{mode=b.dataset.mode;root.querySelectorAll("[data-mode]").forEach(x=>x.classList.toggle("active",x===b));});
const settings=root.querySelector("#q-settings");
if(type==="cups")settings.innerHTML='<label class="c4-label">عدد الأكواب</label><input id="q-cups" type="number" min="3" max="12" value="6" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white"><div class="c4-label">الصعوبة</div><div class="c4-levels" id="q-levels"></div>';
else settings.innerHTML='<label class="c4-label">النقاط المطلوبة للفوز</label><input id="q-points" type="number" min="1" max="20" value="5" style="width:100%;padding:13px;border-radius:12px;background:#17090b;color:white"><div class="c4-levels" id="q-levels"></div>';
if(type==="cups"||type==="timer")["سهل","متوسط","صعب","مستحيل"].forEach(x=>{let b=document.createElement("button");b.className="c4-level"+(x===difficulty?" active":"");b.textContent=x;b.onclick=()=>{difficulty=x;root.querySelectorAll("#q-levels button").forEach(y=>y.classList.toggle("active",y===b));};settings.querySelector("#q-levels").append(b);});
root.querySelector("#q-create").onclick=async()=>{try{room=await api("create",{game_type:game,mode,settings:type==="cups"?{cups:Number($("#q-cups").value),difficulty}:{win_target:Number($("#q-points").value),difficulty}});if(mode==="online")renderLobby();else{room=await api("start");render();}}catch(e){error(root,e);}};
root.querySelector("#q-back").onclick=()=>{stop();window.showGames?.();};};
function error(root,e){let x=root.querySelector(".q-error");if(!x){x=document.createElement("div");x.className="q-error c4-result show";root.append(x);}x.textContent=e.message;}
function renderLobby(){
 const root=shell(),p=room.players||[];
 const fields=room.is_owner?(game==="cups"
  ? '<label class="c4-label">عدد الأكواب</label><input id="q-cups" type="number" min="3" max="12" value="'+room.settings.cups+'"><div class="c4-label">الصعوبة</div><select id="q-diff"><option>سهل</option><option>متوسط</option><option>صعب</option><option>مستحيل</option></select>'
  : '<label class="c4-label">النقاط المطلوبة للفوز</label><input id="q-points" type="number" min="1" max="20" value="'+room.settings.win_target+'">') : '';
 const controls=room.is_owner
  ? '<button id="q-save" class="c4-secondary">حفظ الإعدادات</button><button id="q-start" class="c4-start" '+(p.length<2?"disabled":"")+'>ابدأ اللعب</button>'
  : '<div class="c4-hint">بانتظار صاحب الغرفة</div>';
 root.innerHTML=heading(game==="cups"?"غرفة الأكواب 🥤":"غرفة المؤقت ⏱️","انضمام حتى 4 لاعبين")
  + '<div class="c4-panel"><div class="c4-label">اللاعبون ('+p.length+'/4)</div><div class="mg-score">'+p.map(x=>'<span>'+safe(x.name)+'</span>').join("")+'</div>'
  + fields + controls + '<button id="q-back" class="c4-secondary">رجوع للألعاب</button></div>';
 const diff=$("#q-diff");if(diff)diff.value=room.settings.difficulty||"متوسط";
 const save=$("#q-save");if(save)save.onclick=async()=>{try{room=await api("configure",{settings:game==="cups"?{cups:Number($("#q-cups").value),difficulty:$("#q-diff").value}:{win_target:Number($("#q-points").value)}});renderLobby();}catch(e){error(root,e);}};
 const startButton=$("#q-start");if(startButton)startButton.onclick=async()=>{try{room=await api("start");render();}catch(e){error(root,e);}};
 $("#q-back").onclick=()=>{stop();window.showGames?.();};
 const share=document.createElement("button");share.className="c4-secondary";share.textContent="مشاركة رابط الغرفة";
 share.onclick=()=>{const u="https://t.me/lnll0bot?startapp=quick_"+game+"_"+room.id;const link="https://t.me/share/url?url="+encodeURIComponent(u);tg?.openTelegramLink?tg.openTelegramLink(link):navigator.clipboard?.writeText(u);};
 root.querySelector(".c4-panel").append(share);schedule();
}
function scores(){return '<div class="mg-score">'+room.players.map(p=>'<span>'+safe(p.name)+' · '+(room.scores?.[String(p.id)]||0)+' نقطة</span>').join("")+'</div>';}
function render(){if(!room)return;if(room.status==="waiting"){renderLobby();return;}if(room.status==="finished"){const win=room.players.find(p=>Number(p.id)===Number(room.winner_id));const root=shell();let finalRows="";if(game==="timer"&&room.results?.length){const sorted=[...room.results].sort((a,b)=>(a.difference_ms??1e12)-(b.difference_ms??1e12));finalRows='<div class="timer-target">نتائج الجولة الأخيرة<small>الوقت المطلوب: '+format(room.target_ms)+'</small></div>'+sorted.map((x,i)=>'<div class="q-result '+(i===0&&x.difference_ms!==null?"winner":"")+'"><b>'+safe(x.name)+'</b><span>'+(x.elapsed_ms===null?"مستبعد":format(x.elapsed_ms))+'</span><small>'+(x.difference_ms===null?"—":"الفارق "+(x.difference_ms/1000).toFixed(3)+" ث")+' · '+x.score+' نقطة</small></div>').join("");}root.innerHTML=heading("انتهت اللعبة 🏆",win?"الفائز: "+safe(win.name):"انتهت الجولة")+'<div class="c4-panel">'+scores()+finalRows+'<button class="c4-start" onclick="window.showGames()">العودة للألعاب</button></div>';return;}
const root=shell(),me=Number(tg?.initDataUnsafe?.user?.id||0),mine=room.players.some(p=>Number(p.id)===me)&&(room.active_players||[]).includes(me);root.innerHTML=heading(game==="cups"?"الأكواب 🥤":"المؤقت ⏱️","الجولة "+room.round)+scores()+'<div class="c4-panel" id="q-stage"></div><button class="c4-secondary" id="q-back">رجوع للألعاب</button>';const stage=$("#q-stage");
if(game==="cups"){
 if(room.phase==="shuffle"){stage.innerHTML='<div class="wood-table"><div class="cup-row" id="cup-row">'+Array.from({length:room.cups},(_,i)=>'<div class="red-cup" data-cup="'+i+'"><span></span></div>').join("")+'<i class="cup-ball" id="cup-ball"></i></div><div class="c4-result show" id="cup-message">ركز على الكرة…</div></div>';if(shownRound!==room.round){shownRound=room.round;animateCupShuffle(stage,room);}}
 else {const done=room.my_choice!==null&&room.my_choice!==undefined;stage.innerHTML='<div class="wood-table"><div class="cup-row">'+Array.from({length:room.cups},(_,i)=>'<button class="red-cup" data-cup="'+i+'" '+(done||!mine?"disabled":"")+'><span></span></button>').join("")+'</div><div class="c4-result show">'+(done?"تم تسجيل اختيارك، انتظر بقية اللاعبين":"اختر الكوب الذي تعتقد أن الكرة تحته")+'</div></div>';stage.querySelectorAll("[data-cup]").forEach(b=>b.onclick=async()=>{if(lock)return;lock=true;try{room=await api("action",{move:{cup:Number(b.dataset.cup)}});render();}catch(e){error(root,e);}finally{lock=false;}});}
}else{
 if(room.phase==="show_target"){stage.innerHTML='<div class="timer-target">وقفها على<br><strong>'+format(room.target_ms)+'</strong></div><div class="c4-hint">احفظ الوقت — يختفي بعد 4 ثوانٍ</div>';}
 else if(room.phase==="playing"){const done=room.my_elapsed_ms!==null&&room.my_elapsed_ms!==undefined;stage.innerHTML='<div class="timer-target"><strong>بدأ العد</strong></div><button id="q-stop" class="timer-stop" '+(done||!mine?"disabled":"")+'>إيقاف</button><div class="c4-hint">'+(done?"تم تسجيل وقتك، انتظر البقية":"لا يظهر العداد أثناء التحدي")+'</div>';const btn=$("#q-stop");if(btn)btn.onclick=async()=>{if(lock)return;lock=true;try{room=await api("action",{move:{stop:true}});render();}catch(e){error(root,e);}finally{lock=false;}};}
 else if(room.phase==="results"){const sorted=[...room.results].sort((a,b)=>(a.difference_ms??1e12)-(b.difference_ms??1e12));stage.innerHTML='<div class="timer-target">نتائج الجولة '+room.round+'<small>الوقت المطلوب: '+format(room.target_ms)+'</small></div>'+sorted.map((x,i)=>'<div class="q-result '+(i===0&&x.difference_ms!==null?"winner":"")+'"><b>'+safe(x.name)+'</b><span>'+(x.elapsed_ms===null?"مستبعد":format(x.elapsed_ms))+'</span><small>'+(x.difference_ms===null?"—":"الفارق "+(x.difference_ms/1000).toFixed(3)+" ث")+' · '+x.score+' نقطة</small></div>').join("")+'<div class="c4-hint">تبدأ الجولة التالية تلقائيًا</div>';}
}

if(room.phase==="show_target"&&shownRound!==room.round){shownRound=room.round;animationTimer=setTimeout(async()=>{try{room=await api("state");render();}catch(e){}},4200);}
$("#q-back").onclick=()=>{stop();window.showGames?.();};schedule();}
async function animateCupShuffle(stage,state){
 const row=stage.querySelector("#cup-row"),ball=stage.querySelector("#cup-ball"),message=stage.querySelector("#cup-message");
 if(!row)return;
 const count=Number(state.cups)||6,steps=state.shuffle||[],cups=[...row.querySelectorAll(".red-cup")],atSlot=Array.from({length:count},(_,i)=>i);
 const initialBall=Number(state.ball_start??0);
 const slotWidth=row.getBoundingClientRect().width/count;
 const place=(cup,slot)=>{cup.style.left=((slot+.5)/count*100)+"%";cup.style.transform="translateX(-50%)";};
 cups.forEach((cup,i)=>place(cup,i));
 ball.style.left=((initialBall+.5)/count*100)+"%";
 await new Promise(r=>setTimeout(r,220));
 if(!row.isConnected)return;
 const first=cups[initialBall];
 if(first){await first.animate([{transform:"translate(-50%,0)"},{transform:"translate(-50%,-28px)"},{transform:"translate(-50%,-28px)"}],{duration:650,easing:"ease-out",fill:"forwards"}).finished.catch(()=>{}); }
 ball.classList.add("visible");
 if(message)message.textContent="ظهرت الكرة… احفظ مكانها!";
 await new Promise(r=>setTimeout(r,650));
 if(first){await first.animate([{transform:"translate(-50%,-28px)"},{transform:"translate(-50%,0)"}],{duration:380,easing:"ease-in-out"}).finished.catch(()=>{});place(first,initialBall);}
 ball.classList.remove("visible");
 if(message)message.textContent="بدأ الخلط! تابع الكوب الصحيح 👀";
 for(let k=0;k<steps.length;k++){
  if(!row.isConnected)return;
  const a=Number(steps[k].a),b=Number(steps[k].b);
  if(a===b||!Number.isInteger(a)||!Number.isInteger(b)||a<0||b<0||a>=count||b>=count)continue;
  const cupA=cups[atSlot[a]],cupB=cups[atSlot[b]];
  const duration=k<3?560:k<7?390:235;
  const delta=(b-a)*slotWidth;
  const animate=(cup,d)=>cup.animate(
   [{transform:"translate(-50%,0) rotate(0deg)"},{transform:"translate(calc(-50% + "+d+"px),-17px) rotate("+(d>0?7:-7)+"deg)"},{transform:"translate(calc(-50% + "+d+"px),0) rotate(0deg)"}],
   {duration,easing:"cubic-bezier(.22,.72,.24,1)"}
  ).finished.catch(()=>{});
  await Promise.all([animate(cupA,delta),animate(cupB,-delta)]);
  place(cupA,b);place(cupB,a);
  [atSlot[a],atSlot[b]]=[atSlot[b],atSlot[a]];
  await new Promise(r=>setTimeout(r,k<3?100:35));
 }
 if(message&&row.isConnected)message.textContent="انتهى الخلط! تحت أي كوب الكرة؟";
}
function format(ms){ms=Math.max(0,Number(ms)||0);let s=ms/1000;return (s>=60?String(Math.floor(s/60)).padStart(2,"0")+":":"")+String(Math.floor(s%60)).padStart(2,"0")+"."+String(Math.floor(ms%1000)).padStart(3,"0");}
window.startQuickGame=async function(param){stop();const parts=String(param).split("_");game=parts[1];try{room=await api("join",{game_id:parts[2]});render();}catch(e){const root=shell();error(root,e);}};
window.stopQuickGame=stop;
const style=document.createElement("style");style.textContent='.wood-table{padding:28px 10px;border-radius:18px;background:repeating-linear-gradient(3deg,#95602f 0px,#a66d38 13px,#80502b 25px,#ad7844 39px);box-shadow:inset 0 2px 9px #f6c68b55,inset 0 -8px 18px #32180c88,0 8px 20px #0008;min-height:210px;display:flex;flex-direction:column;justify-content:center;gap:24px;overflow:hidden}.cup-row{position:relative;display:block;width:100%;height:126px;min-height:126px;direction:ltr}.red-cup{position:absolute;left:0;bottom:10px;display:block;width:min(13vw,58px);height:76px;border:0;border-radius:8px 8px 18px 18px;background:linear-gradient(90deg,#850b13,#e32632 32%,#b80e1d 70%,#720812);box-shadow:0 10px 12px #2a100b99,inset 5px 0 8px #ffffff28;z-index:2;will-change:left,transform;}.red-cup span{position:absolute;top:-5px;left:-4px;right:-4px;height:12px;border-radius:50%;background:linear-gradient(#fff,#d9d9d9);box-shadow:0 2px 3px #0006}.cup-ball{position:absolute;top:91px;width:16px;height:16px;border-radius:50%;left:50%;transform:translateX(-50%);background:radial-gradient(circle at 32% 25%,#fff5b4,#ffc928 45%,#b66b00);box-shadow:0 2px 7px #0009;opacity:0;z-index:1;transition:opacity .2s}.cup-ball.visible{opacity:1}.timer-target{text-align:center;font-size:24px;font-weight:900;padding:22px}.timer-target strong{display:block;font-size:42px;color:#ffd7d7;direction:ltr}.timer-stop{display:block;width:190px;height:190px;border-radius:50%;margin:20px auto;border:8px solid #fff;background:radial-gradient(circle at 35% 25%,#ff5969,#a50c1a 65%,#5c0710);color:white;font-size:28px;font-weight:1000;box-shadow:0 12px 0 #4b070d,0 18px 24px #0008}.q-result{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;padding:13px;margin:8px 0;border-radius:13px;background:#ffffff12}.q-result.winner{border:2px solid #22c55e}.q-result small{width:100%;color:#ddd}.wood-table .red-cup{cursor:pointer}';
document.head.append(style);
})();

/* ============ 종목 상세 창 ============
   티커·회사명을 누르면 뜨는 창. 미국 실적발표 정리(us-earnings-screening/
   template.py)에서 이미 라이브로 검증된 코드를 그대로 옮겨 왔다 — 차트 엔진,
   분기/연간 실적, 뉴스, 기업 개요, 보고서 링크. 여기에 '스크리너 진단' 탭을
   맨 앞에 더했다(이 도구가 그 종목을 어떻게 봤는지).

   원본과 달라진 곳(전부 이 파일 안에서 '원본과 다름' 으로 표시):
   - 전체를 즉시 실행 함수로 감쌌다. 대시보드의 다른 스크립트와 이름이 겹치지 않게.
   - 색은 문서 루트가 아니라 창(#ov)에서 읽는다 — 대시보드 색 변수가
     .viz-root 안에만 있어서다. 상승 초록·하락 빨강(TradingView 톤).
   - 원화 환산·작업공간 메모·표 클릭은 대시보드에 없어서 뺐다.
   외부 스크립트 없이 차트를 직접 그린다. 시세는 Worker 의 /api/ohlcv 가
   야후에서 받아 정규화해 준다 — 야후는 CORS 헤더를 주지 않아 브라우저가
   직접 부르면 막힌다. */
(function(){
"use strict";
const SCR=window.SCR_DETAIL||{stocks:{},themes:{}};
const $=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));
// 원본의 load/save(분기별)·loadG/saveG(공용)를 한 가지 접두로 합쳤다.
const KEY="scr.detail.";
const load=(n,d)=>{try{const v=localStorage.getItem(KEY+n);return v==null?d:JSON.parse(v)}catch(e){return d}};
const save=(n,v)=>{try{localStorage.setItem(KEY+n,JSON.stringify(v))}catch(e){}};
const loadG=load, saveG=save;

const FWD=26;                 // 일목 선행 이동일수
// 이동평균 기간은 화면에서 바꿀 수 있다. 색은 자리 순서로 붙인다.
let MAP=load("ma",[5,20,60,120]);
const MACLR=["#f0a13a","#d24fa4","#2f9e6a","#8a6fd4","#1f8ecd","#b0733a"];
const CLR={tk:"#1f8ecd",kj:"#c0392b",sa:"#4caf82",sb:"#c9973f",ch:"#8d8b85"};
const SHOW=Object.assign({ichi:1,cloud:1,ch:1,vol:1},load("show",null)||{});
MAP.forEach(p=>{if(SHOW["ma"+p]==null)SHOW["ma"+p]=1});
const ohlcvCache=new Map();
// dBars = 화면에 보이는 칸 수(앞으로 나간 구름대 26칸 포함),
// dEnd  = 오른쪽 끝 칸의 위치. 이 둘로 확대·이동을 다 표현한다.
let dRow=null,dRows=null,dInd=null,dBars=740+FWD,dEnd=null,
    dHover=null,dRaf=0,geo=null,dLog=false;
// 받아온 것은 늘 일봉이다. 주봉·월봉은 그것을 묶어서 만든다 — 서버를 다시
// 부르지 않고, 어느 시장이든 같은 방식으로 동작한다.
let dRaw=null,dTF=loadG("tf","d"),dDays=1095;

/* 한 봉이 될 구간의 이름. 주는 그 주 월요일, 월은 연월. */
function bucketOf(ymd,tf){
 if(tf==="m")return ymd.slice(0,6);
 const dt=new Date(Date.UTC(+ymd.slice(0,4),+ymd.slice(4,6)-1,+ymd.slice(6,8)));
 dt.setUTCDate(dt.getUTCDate()-((dt.getUTCDay()+6)%7));   // 월요일로 당긴다
 return dt.toISOString().slice(0,10).replace(/-/g,"")}

/* 일봉을 주·월봉으로 묶는다. 시가는 첫날, 종가는 마지막날, 고·저는 구간
   전체, 거래량은 합. 날짜는 '그 구간의 마지막 거래일' 로 붙인다 — 아직
   안 끝난 이번 주·이번 달도 지금까지의 값으로 한 봉이 된다. */
function aggregate(rows,tf){
 if(tf==="d")return rows;
 const out=[];let key=null,cur=null;
 for(const r of rows){
  const k=bucketOf(r[0],tf);
  if(k!==key){if(cur)out.push(cur);key=k;cur=r.slice()}
  else{
   if(r[2]>cur[2])cur[2]=r[2];
   if(r[3]<cur[3])cur[3]=r[3];
   cur[4]=r[4];cur[5]+=r[5];cur[0]=r[0]}}
 if(cur)out.push(cur);
 return out}

/* 기간 단추는 '3년' 처럼 달력 기준이다. 시간축마다 봉 수로 바꿔 준다. */
function barsFor(days,tf){
 return tf==="m"?Math.max(6,Math.round(days/30.44))
      :tf==="w"?Math.max(8,Math.round(days/7))
      :Math.max(20,Math.round(days*252/365))}

/* 시간축·기간이 바뀌면 봉을 다시 묶고 지표도 그 위에서 다시 계산한다.
   MA·일목의 숫자(5·20·60·120·9·26·52)는 '봉 수' 라서, 주봉이면 주 단위로
   읽힌다 — 차트 관행 그대로다. */
function applyTF(){
 if(!dRaw)return;
 dRows=aggregate(dRaw,dTF);
 dInd=indicators(dRows);
 dBars=barsFor(dDays,dTF)+FWD;
 dEnd=null;dHover=null;
 scheduleDraw()}

const nf=v=>Number(v).toLocaleString("ko-KR",{maximumFractionDigits:0});
const nf1=v=>Number(v).toLocaleString("ko-KR",{maximumFractionDigits:1});
const dtx=s=>s.slice(0,4)+"."+s.slice(4,6)+"."+s.slice(6,8);
// 월봉은 날짜까지 적으면 '그 달의 마지막 거래일' 로 오해된다 — 연월만 쓴다.
const barLabel=s=>dTF==="m"?s.slice(0,4)+"."+s.slice(4,6)
                :dTF==="w"?dtx(s)+" 주":dtx(s);
// 차트는 늘 원화 아닌 현지 통화(달러)다. 표의 원화 전환과 헷갈리지 않게 붙인다.
const money=v=>"$"+nf1(v);
// 원본과 다름: 범례·툴팁의 가격은 센트까지(원본은 정수 — 미국 소형주에서 값이 뭉개졌다)
const px2=v=>Number(v).toLocaleString("ko-KR",{minimumFractionDigits:2,maximumFractionDigits:2});
function volTxt(v){
 if(v>=1e8)return nf1(v/1e8)+"억주";
 if(v>=1e4)return nf(v/1e4)+"만주";
 return nf(v)+"주"}

// ---- 지표 ----
function sma(a,n){const o=new Array(a.length).fill(null);let s=0;
 for(let i=0;i<a.length;i++){s+=a[i];if(i>=n)s-=a[i-n];if(i>=n-1)o[i]=s/n}
 return o}
// 일목의 선들은 평균이 아니라 기간 내 고가·저가의 중간값이다.
function mid(rows,n){const o=new Array(rows.length).fill(null);
 for(let i=n-1;i<rows.length;i++){let hi=-Infinity,lo=Infinity;
  for(let j=i-n+1;j<=i;j++){if(rows[j][2]>hi)hi=rows[j][2];if(rows[j][3]<lo)lo=rows[j][3]}
  o[i]=(hi+lo)/2}
 return o}
function indicators(rows){
 const n=rows.length,close=rows.map(r=>r[4]),ma={};
 MAP.forEach(p=>{ma[p]=sma(close,p)});
 const tk=mid(rows,9),kj=mid(rows,26),b52=mid(rows,52);
 // 선행스팬은 26일 앞에 그린다 — 배열을 뒤로 26칸 늘려 그 자리에 넣는다.
 const sa=new Array(n+FWD).fill(null),sb=new Array(n+FWD).fill(null),
       ch=new Array(n+FWD).fill(null);
 for(let i=0;i<n;i++){
  if(tk[i]!=null&&kj[i]!=null)sa[i+FWD]=(tk[i]+kj[i])/2;
  if(b52[i]!=null)sb[i+FWD]=b52[i];
  if(i>=FWD)ch[i-FWD]=close[i];          // 후행스팬은 26일 뒤로
 }
 return {ma,tk,kj,sa,sb,ch}}

// ---- 그리기 ----
// 원본과 다름: 색 변수가 창(#ov)에 있어 거기서 읽는다(원본은 문서 루트).
const cssv=v=>getComputedStyle($("#ov")).getPropertyValue(v).trim();
function niceStep(x){
 const e=Math.pow(10,Math.floor(Math.log10(Math.max(x,1e-9)))),m=x/e;
 return (m<1.5?1:m<3?2:m<7?5:10)*e}
function scheduleDraw(){if(!dRaf)dRaf=requestAnimationFrame(draw)}

function draw(){
 dRaf=0;
 const cv=$("#cv");
 if(!dRows||!dRows.length||!cv.clientWidth)return;
 const dpr=window.devicePixelRatio||1;
 const W=cv.clientWidth;
 const H=Math.max(300,Math.min(760,Math.round(window.innerHeight*0.46)));
 cv.width=Math.round(W*dpr);cv.height=Math.round(H*dpr);cv.style.height=H+"px";
 const g=cv.getContext("2d");
 g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,W,H);
 g.font='11px "Noto Sans KR",Roboto,"맑은 고딕",system-ui,sans-serif';
 g.textBaseline="middle";
 const sub=cssv("--sub")||"#888",line=cssv("--line")||"#ddd";
 // 원본과 다름: 대시보드(TradingView 톤)에 맞춰 상승 초록·하락 빨강
 const upC=cssv("--up")||"#089981",dnC=cssv("--down")||"#f23645";

 const padL=10,padR=64,padT=8,gapY=10,axisH=18;
 // 거래량을 끄면 그만큼 주가 칸이 넓어진다.
 const volH=SHOW.vol?Math.round((H-padT-axisH-gapY)*0.24):0;
 const priceH=H-padT-axisH-(SHOW.vol?gapY:0)-volH;
 const y0=padT,y1=padT+priceH,v0=y1+gapY,v1=v0+volH;
 // 축은 [실제 거래일 n개 + 앞으로 나간 구름대 26칸]. 보이는 창을 잘라 쓴다.
 const n=dRows.length,T=n+FWD;
 if(dEnd==null)dEnd=T-1;
 const win=Math.max(20,Math.min(dBars,T));
 let i1=Math.min(dEnd,T-1),i0=i1-win+1;
 if(i0<0){i0=0;i1=Math.min(T-1,win-1)}
 dEnd=i1;
 const nv=Math.min(i1,n-1);              // 창 안의 마지막 실제 거래일
 const bw=(W-padL-padR)/(i1-i0+1);
 const X=i=>padL+(i-i0+0.5)*bw;

 let lo=Infinity,hi=-Infinity;
 const push=v=>{if(v==null||!isFinite(v))return;if(v<lo)lo=v;if(v>hi)hi=v};
 for(let i=i0;i<=nv;i++){push(dRows[i][2]);push(dRows[i][3])}
 for(let i=i0;i<=i1;i++){
  if(SHOW.cloud){push(dInd.sa[i]);push(dInd.sb[i])}
  if(SHOW.ch)push(dInd.ch[i])}
 MAP.forEach(p=>{if(SHOW["ma"+p])for(let i=i0;i<=nv;i++)push(dInd.ma[p][i])});
 if(SHOW.ichi)for(let i=i0;i<=nv;i++){push(dInd.tk[i]);push(dInd.kj[i])}
 if(!isFinite(lo)||!isFinite(hi))return;
 if(hi<=lo){hi=lo+1;lo=lo-1}
 const pad=(hi-lo)*0.06;
 // 주가는 음수가 없다. 여백을 그대로 빼면 축에 '-0' 이 찍힌다.
 lo=Math.max(dLog?lo/1.08:0,lo-pad);hi+=pad;
 // 3년처럼 긴 구간에서 몇 배씩 오른 종목은 선형 축이면 초반이 바닥에 붙는다.
 const lg=v=>Math.log(Math.max(v,1e-6));
 const L0=lg(lo),L1=lg(hi);
 const Y=dLog?(v=>y1-(lg(v)-L0)/(L1-L0)*priceH)
             :(v=>y1-(v-lo)/(hi-lo)*priceH);
 let vmax=0;
 for(let i=i0;i<=nv;i++)if(dRows[i][5]>vmax)vmax=dRows[i][5];
 const VY=v=>v1-(vmax?v/vmax:0)*volH;

 // 가로 눈금·가격 라벨 (로그 축은 1·2·5 배수로 찍는다)
 const ticks=[];
 // 원본과 다름: 미국 소형주는 눈금 간격이 1달러보다 좁을 수 있다 —
 // 정수로만 찍으면 같은 숫자가 여러 번 찍힌다. 간격에 맞춰 소수점을 붙인다.
 const tstep=dLog?lo:niceStep((hi-lo)/5);
 const tlab=v=>tstep<1?Number(v).toFixed(tstep<0.1?2:1):nf(v);
 if(dLog){
  for(let e=Math.floor(Math.log10(Math.max(lo,1e-6)));e<=Math.ceil(Math.log10(hi));e++)
   for(const m of [1,2,5]){const v=m*Math.pow(10,e);if(v>=lo&&v<=hi)ticks.push(v)}
 }else{
  const step=niceStep((hi-lo)/5);
  for(let v=Math.ceil(lo/step)*step;v<=hi;v+=step)ticks.push(v)}
 g.lineWidth=1;g.textAlign="left";
 ticks.forEach(v=>{
  const y=Math.round(Y(v))+0.5;
  g.strokeStyle=line;g.globalAlpha=.55;
  g.beginPath();g.moveTo(padL,y);g.lineTo(W-padR,y);g.stroke();g.globalAlpha=1;
  g.fillStyle=sub;g.fillText(tlab(v),W-padR+6,y)});
 if(SHOW.vol){g.fillStyle=sub;g.fillText(volTxt(vmax),W-padR+6,v0+6)}

 // 세로 눈금(최대 7개). 일·주봉은 달이 바뀌는 곳, 월봉은 해가 바뀌는 곳.
 const gw=dTF==="m"?4:6;               // 날짜 앞 몇 자리로 구간을 볼지
 const firsts=[];let pm="";
 for(let i=i0;i<=nv;i++){const m=dRows[i][0].slice(0,gw);if(m!==pm){firsts.push(i);pm=m}}
 const kstep=Math.max(1,Math.ceil(firsts.length/7));
 g.textAlign="center";
 firsts.forEach((i,j)=>{if(j%kstep)return;
  const x=Math.round(X(i))+0.5,d=dRows[i][0];
  g.strokeStyle=line;g.globalAlpha=.5;
  g.beginPath();g.moveTo(x,y0);g.lineTo(x,v1);g.stroke();g.globalAlpha=1;
  g.fillStyle=sub;
  g.fillText(dTF==="m"?d.slice(0,4):d.slice(2,4)+"."+d.slice(4,6),x,v1+9)});

 // 구름대 — 선행1·2 사이를 세로 막대로 채운다(교차점 계산 없이 색이 바뀐다)
 const bwf=Math.max(bw,1)+0.6;
 if(SHOW.cloud)for(let i=i0;i<=i1;i++){
  const a=dInd.sa[i],b=dInd.sb[i];
  if(a==null||b==null)continue;
  const ya=Y(a),yb=Y(b);
  g.fillStyle=a>=b?"rgba(47,158,106,.17)":"rgba(200,60,60,.15)";
  g.fillRect(X(i)-bw/2,Math.min(ya,yb),bwf,Math.abs(ya-yb)+0.5)}

 function poly(arr,color,dash,from,to){
  g.save();if(dash)g.setLineDash([4,3]);
  g.strokeStyle=color;g.lineWidth=1.2;g.beginPath();let on=false;
  for(let i=from;i<=to;i++){const v=arr[i];
   if(v==null||!isFinite(v)){on=false;continue}
   const x=X(i),y=Y(v);if(on)g.lineTo(x,y);else{g.moveTo(x,y);on=true}}
  g.stroke();g.restore()}

 // 거래량
 if(SHOW.vol){
  for(let i=i0;i<=nv;i++){
   const r=dRows[i],p=i>0?dRows[i-1][4]:r[4],y=VY(r[5]);
   g.fillStyle=r[4]>=p?upC:dnC;g.globalAlpha=.5;
   const w=Math.max(bw*0.72,0.8);
   g.fillRect(X(i)-w/2,y,w,v1-y)}
  g.globalAlpha=1}

 // 캔들 — 폭이 3px 미만이면 몸통을 그려도 안 보인다. 고가·저가 선만 남긴다.
 const body=bw>=3.2,cw=Math.max(1,Math.floor(bw*0.68));
 for(let i=i0;i<=nv;i++){
  const r=dRows[i],rise=r[4]>=r[1],x=Math.round(X(i))+0.5;
  g.strokeStyle=g.fillStyle=rise?upC:dnC;
  g.beginPath();g.moveTo(x,Y(r[2]));g.lineTo(x,Y(r[3]));g.stroke();
  if(body){const yo=Y(r[1]),yc=Y(r[4]);
   g.fillRect(Math.round(X(i)-cw/2),Math.min(yo,yc),cw,Math.max(1,Math.abs(yo-yc)))}}

 if(SHOW.cloud){poly(dInd.sa,CLR.sa,false,i0,i1);poly(dInd.sb,CLR.sb,false,i0,i1)}
 if(SHOW.ichi){poly(dInd.tk,CLR.tk,false,i0,nv);poly(dInd.kj,CLR.kj,false,i0,nv)}
 if(SHOW.ch)poly(dInd.ch,CLR.ch,true,i0,i1);
 MAP.forEach((p,k)=>{
  if(SHOW["ma"+p])poly(dInd.ma[p],MACLR[k%MACLR.length],false,i0,nv)});

 // 테두리
 g.strokeStyle=line;g.globalAlpha=.9;
 g.strokeRect(padL+.5,y0+.5,W-padL-padR-1,priceH);
 if(SHOW.vol)g.strokeRect(padL+.5,v0+.5,W-padL-padR-1,volH);
 g.globalAlpha=1;

 if(dHover!=null&&dHover>=i0&&dHover<=nv){
  const x=Math.round(X(dHover))+0.5;
  g.save();g.setLineDash([4,3]);g.strokeStyle=sub;g.globalAlpha=.85;
  g.beginPath();g.moveTo(x,y0);g.lineTo(x,v1);g.stroke();g.restore()}

 geo={i0,i1,nv,bw,padL,X,Y,y0,v1,W,H};
 legend(dHover!=null&&dHover<=nv?dHover:nv);
 tipAt(dHover);
 // 처음 열 때 세로 스크롤바가 생겼다 사라지면 폭이 달라진다. 그대로 두면
 // 캔버스가 늘어나 글씨가 흐려지므로 한 번 더 그린다(높이는 안 바뀌어 반복되지 않는다).
 if(Math.abs(cv.clientWidth-W)>0.5)scheduleDraw();
}

// ---- 지표 고르기 ----
// 어떤 선을 볼지, 이동평균을 몇 일로 볼지 여기서 정한다. 고른 것은 저장된다.
function indBar(){
 const b=(key,label,color)=>'<button data-k="'+key+'" class="'+(SHOW[key]?"on":"")+'">'+
  (color?'<span class="sw2" style="background:'+color+'"></span>':"")+label+"</button>";
 let h='<span class="lbl2">지표</span>';
 MAP.forEach((p,k)=>{h+=b("ma"+p,"MA"+p,MACLR[k%MACLR.length])});
 h+=b("ichi","전환·기준",CLR.tk)+b("cloud","구름대",CLR.sa)+
    b("ch","후행",CLR.ch)+b("vol","거래량","");
 h+='<span class="lbl2">이동평균(일)</span><input class="ma" id="maset" value="'+
    MAP.join(",")+'" title="쉼표로 구분 — 예: 5,20,60,120 (최대 6개)">';
 $("#dind").innerHTML=h;
 document.querySelectorAll("#dind button").forEach(el=>el.onclick=()=>{
  SHOW[el.dataset.k]=SHOW[el.dataset.k]?0:1;
  save("show",SHOW);indBar();scheduleDraw()});
 $("#maset").onchange=()=>{
  const v=[...new Set($("#maset").value.split(/[^0-9]+/).map(Number)
   .filter(x=>x>=2&&x<=400))].sort((a,b)=>a-b).slice(0,6);
  if(!v.length){indBar();return}          // 못 알아들으면 되돌린다
  MAP=v;save("ma",MAP);
  MAP.forEach(p=>{if(SHOW["ma"+p]==null)SHOW["ma"+p]=1});
  save("show",SHOW);
  if(dRows)dInd=indicators(dRows);
  indBar();scheduleDraw()}}

// ---- 범례(가리키는 날의 값) ----
function legend(i){
 if(!dRows||!dInd)return;
 const r=dRows[i],chg=i>0?(r[4]/dRows[i-1][4]-1)*100:null;
 const it=(label,color,val)=>'<span><span class="sw" style="background:'+color+
  '"></span><i>'+label+'</i> <b>'+(val==null?"-":px2(val))+"</b></span>";
 let h='<span><i>'+barLabel(r[0])+'</i> <b>'+money(r[4])+"</b>"+
  (chg==null?"":' <b class="'+(chg>0?"pos":chg<0?"neg":"")+'">'+
   (chg>0?"+":"")+chg.toFixed(2)+"%</b>")+
  (SHOW.vol?' <i>거래량 '+volTxt(r[5])+"</i>":"")+"</span>";
 MAP.forEach((p,k)=>{
  if(SHOW["ma"+p])h+=it("MA"+p,MACLR[k%MACLR.length],dInd.ma[p][i])});
 if(SHOW.ichi)h+=it("전환",CLR.tk,dInd.tk[i])+it("기준",CLR.kj,dInd.kj[i]);
 if(SHOW.cloud)h+=it("선행1",CLR.sa,dInd.sa[i])+it("선행2",CLR.sb,dInd.sb[i]);
 if(SHOW.ch)h+=it("후행",CLR.ch,dInd.ch[i]);
 $("#dleg").innerHTML=h}

// ---- 십자선 툴팁 ----
function tipAt(i){
 const t=$("#tip");
 if(i==null||!dRows||!geo||i<geo.i0||i>geo.nv){t.style.display="none";return}
 const r=dRows[i],pv=i>0?dRows[i-1][4]:r[4],chg=(r[4]/pv-1)*100;
 const ln=(a,b)=>b==null?"":"<div><i>"+a+"</i> <b>"+px2(b)+"</b></div>";
 t.innerHTML="<div><b>"+barLabel(r[0])+"</b></div>"+
  "<div>시 "+px2(r[1])+" 고 "+px2(r[2])+" 저 "+px2(r[3])+"</div>"+
  "<div>종 <b>"+px2(r[4])+"</b> <span class='"+(chg>0?"pos":chg<0?"neg":"")+"'>"+
  (chg>0?"+":"")+chg.toFixed(2)+"%</span></div>"+
  "<div>거래량 "+volTxt(r[5])+"</div>"+
  MAP.map(p=>ln("MA"+p,(dInd.ma[p]||[])[i])).join("")+
  ln("전환",dInd.tk[i])+ln("기준",dInd.kj[i])+
  ln("선행1",dInd.sa[i])+ln("선행2",dInd.sb[i]);
 t.style.display="block";
 const x=geo.X(i),w=t.offsetWidth,h=t.offsetHeight;
 t.style.left=Math.max(2,Math.min(geo.W-w-2,x+14))+"px";
 t.style.top=Math.max(2,Math.min(geo.H-h-2,geo.Y(r[2])-8))+"px";
}

// ---- 시세 받아오기 ----
async function loadOhlcv(code){
 if(ohlcvCache.has(code))return ohlcvCache.get(code);
 let r;
 try{r=await fetch("/api/ohlcv?ticker="+code)}
 catch(e){throw new Error("시세 서버에 연결하지 못했습니다")}
 const d=await r.json().catch(()=>({}));
 if(!r.ok||!d.rows||!d.rows.length)
  throw new Error(d.message||("시세를 불러오지 못했습니다 ("+r.status+")"));
 // 원본과 다름: 거래소 이름(d.ex)도 기억해 둔다 — 보고서 링크용.
 if(d.ex)exCache.set(code,d.ex);
 ohlcvCache.set(code,d.rows);
 return d.rows}
const exCache=new Map();

function chartMsg(t){
 $("#cmsg").style.display=t?"block":"none";
 $("#cmsg").textContent=t||"";
 $("#cv").style.display=t?"none":"block";
 if(t)$("#tip").style.display="none"}

// ---- 보고서 탭: 볼 것을 한자리에 모아 고르게 한다 ----
function links(r){
 const nm=encodeURIComponent(r.name_full||r.name);
 const t=encodeURIComponent(r.code), lo=r.code.toLowerCase();
 const cik=String(r.cik||"").padStart(10,"0");
 const a=(href,ic,label,note)=>'<a href="'+href+'" target="_blank" rel="noopener">'+
  '<span class="ic">'+ic+'</span><span>'+label+'</span>'+
  (note?'<span class="sub2">'+esc(note)+"</span>":"")+"</a>";
 // SEC 는 CIK 를 알면 그 회사 제출목록으로 바로 들어간다. 없으면 회사명 검색.
 const ed=(type,note,ic,label)=>a(
  "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&"+
  (r.cik?("CIK="+cik):("company="+nm))+"&type="+type+
  "&dateb=&owner=include&count=20", ic, label, note);
 let h='<div class="lgroup"><h3>공시 (SEC EDGAR)</h3>';
 h+=ed("10-", r.cik?("CIK "+cik):"회사명 검색", "📄", "정기보고서 10-Q·10-K");
 h+=ed("8-K", "실적발표·수시공시", "📢", "8-K");
 h+=ed("", r.cik?("CIK "+cik):"회사명 검색", "🗂", "전체 공시 목록");
 h+='</div><div class="lgroup"><h3>리서치</h3>';
 h+=a("https://finance.yahoo.com/quote/"+t+"/analysis","📊","애널리스트 추정치",
      "야후 · EPS·매출 컨센서스");
 h+=a("https://stockanalysis.com/stocks/"+lo+"/forecast/","🏦","목표주가·전망",
      "StockAnalysis");
 h+=a("https://stockanalysis.com/stocks/"+lo+"/financials/","🏢","재무제표","분기·연간");
 h+='</div><div class="lgroup"><h3>어닝콜 전문</h3>';
 // 실적발표 콜 원문. Motley Fool 이 로그인 없이 전문을 준다.
 // 원본과 다름: 거래소는 주가를 받아 온 뒤에 알 수 있다(그 전엔 NYSE 로 가정하고,
 // 주가가 오면 이 탭을 다시 그린다 — openStock 참고).
 h+=a("https://www.fool.com/quote/"+
      ((r.market||"").indexOf("Nasdaq")>=0?"nasdaq":"nyse")+"/"+lo+"/",
      "🎙","어닝콜 전문","Motley Fool · 로그인 없이 열림");
 h+=a("https://seekingalpha.com/symbol/"+t+"/earnings/transcripts",
      "🗣","어닝콜 목록","Seeking Alpha · 가입 필요할 수 있음");
 h+=a("https://roic.ai/quote/"+t,"📝","전문·재무","roic.ai");
 h+='</div><div class="lgroup"><h3>시세</h3>';
 h+=a("https://finance.yahoo.com/quote/"+t,"📈","야후 파이낸스",r.code);
 h+=a("https://www.google.com/finance/quote/"+t+":"+
      ((r.market||"").indexOf("Nasdaq")>=0?"NASDAQ":"NYSE"),"🔎","구글 파이낸스",
      r.market||"");
 $("#dlinks").innerHTML=h+"</div>"}

/* ---- 분기 실적 탭 ----
   최근 6개 분기의 매출액·매출총이익·영업이익·당기순이익과 이익률, 그리고
   그 분기 컨센서스 대비 서프라이즈. Worker 의 /api/fin 이 모아서 준다.
   매출총이익은 무료로 열려 있는 데이터에 잘 없어서, 받아온 분기만 채운다. */
const finCache=new Map();
// 표에 담을 줄. chg 는 증감률 줄(앞 칸·4칸 전과 견준다).
const FIN_ROWS=[
 ["sales","매출액"],["sales","매출 YoY","yoy"],["sales","매출 QoQ","qoq"],
 ["gp","매출총이익"],["gpm","GPM"],
 ["op","영업이익"],["op","OP YoY","yoy"],["op","OP QoQ","qoq"],["opm","OPM"],
 ["np","당기순이익"],["nim","NIM"]];
const RATE=new Set(["gpm","opm","nim"]);
/* 증감률: 분모가 0 이하면 계산하지 않는다(적자 기저에서 나온 +9999% 는 뜻이 없다).
   화면에 있는 분기가 6개뿐이라 YoY 는 뒤쪽 두 칸에서만 나온다 — 없는 칸은 비운다. */
function chgAt(qs,i,k,back){
 const a=qs[i]&&qs[i][k], b=qs[i-back]&&qs[i-back][k];
 if(a==null||b==null||b<=0)return null;
 return (a-b)/b*100}

async function loadFin(code,corp,annual){
 const ck=(annual?"Y":"Q")+code;
 if(finCache.has(ck))return finCache.get(ck);
 let r;
 try{r=await fetch("/api/fin?ticker="+code+(corp?"&cik="+corp:"")+
                   (annual?"&period=year":""))}
 catch(e){throw new Error("실적 서버에 연결하지 못했습니다")}
 const d=await r.json().catch(()=>({}));
 if(!r.ok||!d.q||!d.q.length)
  throw new Error(d.message||("실적을 불러오지 못했습니다 ("+r.status+")"));
 finCache.set(ck,d);
 return d}

// 표에는 소수점을 쓰지 않는다.
function finCell(v,cls){
 if(v==null)return '<td class="miss">-</td>';
 return '<td'+(cls?' class="'+cls+'"':"")+">"+
  Number(v).toLocaleString("ko-KR",{maximumFractionDigits:0})+"</td>"}
function surpCell(v){
 if(v==null)return '<td class="miss">-</td>';
 const cls=v>0?"up":v<0?"dn2":"";
 return '<td class="'+cls+'"><b>'+(v>0?"서프 +":v<0?"쇼크 ":"")+
  Math.round(v)+"%</b></td>"}

function finHtml(d,annual){
 const qs=d.q;
 let h='<table><tr><th class="it">항목 (백만달러)</th>'+
  qs.map(q=>'<th class="q'+(q.est?" est":"")+'">'+esc(q.label)+(q.est?"(E)":"")+"</th>").join("")+
  "</tr>";
 FIN_ROWS.forEach(([k,label,chg])=>{
  if(chg==="qoq"&&annual)return;              // 연간표에 직전분기는 없다
  const back=chg==="yoy"?(annual?1:4):1;
  const sub=chg||RATE.has(k);
  h+='<tr'+(sub?' class="sub"':"")+'><td class="it">'+label+
   (chg||RATE.has(k)?" (%)":"")+"</td>"+
   qs.map((q,i)=>{
    if(!chg)return finCell(q[k]);
    const v=chgAt(qs,i,k,back);
    if(v==null)return '<td class="miss">-</td>';
    return '<td class="'+(v>0?"up":v<0?"dn2":"")+'">'+
     (v>0?"+":"")+Math.round(v)+"</td>"}).join("")+"</tr>"});
 /* 컨센서스 — 분기는 대비 서프라이즈까지, 연간은 전망치만.
    한국판은 이익 컨센이 영업이익인데 미국은 EPS 다(영업이익 컨센은 무료로
    열려 있는 곳이 없다 — Finnhub·FMP 유료, TradingView 는 값이 어긋난다).
    매출 서프라이즈는 기간 정합이 증명된 종목에만 값이 있다. */
 if(!annual){
  h+='<tr class="gap"><td class="it">컨센 대비 매출</td>'+
   qs.map(q=>surpCell(q.surp_s)).join("")+"</tr>";
  h+='<tr><td class="it">컨센 대비 (EPS)</td>'+
   qs.map(q=>surpCell(q.surp)).join("")+"</tr>";}
 h+='<tr class="'+(annual?"gap ":"")+'sub"><td class="it">컨센 매출</td>'+
  qs.map(q=>finCell(annual&&!q.est?null:q.cons_s)).join("")+"</tr>";
 h+='<tr class="sub"><td class="it">EPS 실적 / 컨센 ($)</td>'+
  qs.map(q=>{
   if(q.eps_a==null&&q.eps_e==null)return '<td class="miss">-</td>';
   const f=v=>v==null?"-":Number(v).toFixed(2);
   return "<td>"+f(q.eps_a)+" / "+f(q.eps_e)+"</td>"}).join("")+"</tr></table>";
 return h}

function finNote(d,annual){
 const qs=d.q;
 const src=annual
  ? "단위 백만달러 · 실적: 야후 연간 재무"
  // 원본과 다름: 원본은 매출 컨센을 TradingView 수집분에서 받았는데, 여기는
  // 그 수집이 없어 야후 earningsTrend 의 (E) 열만 있다.
  : "단위 백만달러 · 실적: 야후 분기 재무 · 컨센서스: 야후(EPS, 매출은 앞 분기 (E)만)";
 const gpMiss=qs.every(q=>q.gp==null);
 if(gpMiss)
  return src+"<br>이 종목은 매출총이익이 비어 있습니다 — 금융업처럼 그 계정이 "+
   "없는 회사이거나, 보고서에 따로 표시하지 않는 경우입니다.";
 const miss=FIN_ROWS.filter(([k])=>qs.every(q=>q[k]==null)).map(f=>f[1]);
 return src+
  (miss.length?"<br>받아오지 못한 항목: "+esc(miss.join(", "))+
   " — 그 보고서에 해당 계정이 없습니다(금융업 등).":"")}

/* 한국판은 매출총이익을 수집 단계에서 미리 받아 실어 보낸다(DART 전체
   재무제표에만 있어서 Worker 가 그때그때 부르려면 키가 필요하다). 미국은
   야후가 분기 손익에 매출총이익을 같이 주므로 그럴 필요가 없다 — 이 함수는
   행에 gpq·gpy 가 실려 온 경우에만 동작하고, 없으면 조용히 지나간다. */
function mergeGP(row,d,annual){
 const src=annual?row.gpy:row.gpq;
 if(!src)return;
 d.q.forEach(q=>{
  const k=annual?q.key.slice(0,4):q.key;
  if(q.gp==null&&src[k]!=null){
   q.gp=src[k];
   if(q.sales)q.gpm=q.gp/q.sales*100}})}

async function openFin(row,annual){
 const box=annual?"#yeardata":"#findata", note=annual?"#yearnote":"#finnote";
 $(box).innerHTML='<div class="finnote">실적을 불러오는 중…</div>';
 $(note).textContent="";
 try{
  const d=await loadFin(row.code,row.cik,annual);
  if(!dRow||dRow.code!==row.code)return;
  mergeGP(row,d,annual);
  $(box).innerHTML=finHtml(d,annual);
  $(note).innerHTML=finNote(d,annual);
 }catch(e){
  if(!dRow||dRow.code!==row.code)return;
  $(box).innerHTML="";
  $(note).textContent=e.message+" — ‘보고서’ 탭의 StockAnalysis 재무제표에서 볼 수 있습니다."}}

// ---- 메모 탭 ----
// 원본과 다름: 스크리너에는 서버 저장(작업공간)·비고 칸이 없다. 이 브라우저에만 남긴다.
function openMemo(row){
 const el=$("#dmemo");
 const memos=load("memos",{});
 el.value=memos[row.code]||"";
 $("#dmemomsg").textContent="적는 대로 이 브라우저에만 저장됩니다(다른 기기·브라우저에는 안 보입니다).";
 el.oninput=()=>{
  const m=load("memos",{}),v=el.value.trim();
  if(v)m[row.code]=v; else delete m[row.code];
  save("memos",m)}}

/* ---- 뉴스 탭 ----
   주가와 나란히 보는 것이라 '지금' 이 아니면 쓸모가 없다. Worker 가 최근
   7일치만 받아 시각 내림차순으로 정렬해 준다(구글뉴스 한국어 + 야후 영문).
   캐시는 종목당 5분 — 열 때마다 새로 받되 연타에는 서버를 덜 부른다. */
const newsCache=new Map();
const NEWS_TTL=5*60*1000;

function ago(ms){
 const m=Math.floor((Date.now()-ms)/60000);
 if(m<1)return "방금";
 if(m<60)return m+"분 전";
 const h=Math.floor(m/60);
 if(h<24)return h+"시간 전";
 return Math.floor(h/24)+"일 전"}

async function loadNews(t){
 const c=newsCache.get(t);
 if(c&&Date.now()-c.at<NEWS_TTL)return c.d;
 let r;
 try{r=await fetch("/api/news?ticker="+encodeURIComponent(t))}
 catch(e){throw new Error("뉴스 서버에 연결하지 못했습니다")}
 const d=await r.json().catch(()=>({}));
 if(!r.ok)throw new Error(d.message||("뉴스를 불러오지 못했습니다 ("+r.status+")"));
 newsCache.set(t,{d,at:Date.now()});
 return d}

async function openNews(row){
 $("#newsbox").innerHTML='<div class="abnote">뉴스를 불러오는 중…</div>';
 try{
  const d=await loadNews(row.code);
  if(!dRow||dRow.code!==row.code)return;
  const it=d.items||[];
  if(!it.length){
   $("#newsbox").innerHTML='<div class="abnote">최근 '+(d.days||7)+
    '일 안에 올라온 기사가 없습니다.</div>';
   return}
  $("#newsbox").innerHTML='<div class="nlist">'+it.map(x=>
   '<a href="'+esc(x.u)+'" target="_blank" rel="noopener">'+
   '<span class="nwhen">'+esc(ago(x.w))+"</span>"+
   '<span class="ntitle"'+(x.k?' title="'+esc(x.t)+'"':"")+">"+
   esc(x.k||x.t)+"</span>"+
   '<span class="nsrc">'+esc(x.s||"Yahoo Finance")+"</span></a>").join("")+
   '</div><div class="abnote">최근 '+(d.days||7)+
   '일치만 최신순 · 출처: 야후 파이낸스(종목 뉴스) · 제목은 기계 번역이라 '+
   '어색할 수 있습니다(원문은 제목에 마우스를 올리면 보입니다)</div>';
 }catch(e){
  if(!dRow||dRow.code!==row.code)return;
  $("#newsbox").innerHTML='<div class="abnote">'+esc(e.message)+"</div>"}}

/* ---- 기업 개요 탭 ----
   무슨 사업을 하는 회사인지. 네이버가 미국 종목도 한국어 개요를 주므로 그걸
   우선 쓰고, 없는 종목은 야후 영문을 번역해서 보여준다. 전 종목 설명을 페이지에
   심으면 수 MB 가 늘어나므로 열 때 그 종목만 받아온다. */
const aboutCache=new Map();

async function loadAbout(t){
 if(aboutCache.has(t))return aboutCache.get(t);
 let r;
 try{r=await fetch("/api/profile?ticker="+encodeURIComponent(t))}
 catch(e){throw new Error("개요 서버에 연결하지 못했습니다")}
 const d=await r.json().catch(()=>({}));
 if(!r.ok)throw new Error(d.message||("개요를 불러오지 못했습니다 ("+r.status+")"));
 aboutCache.set(t,d);
 return d}

function renderAbout(d,row){
 const m=[];
 const put=(k,v)=>{if(v)m.push("<span><b>"+esc(k)+"</b> "+esc(String(v))+"</span>")};
 put("섹터",d.sector||row.sector);
 put("업종",d.industry);
 if(d.nameKo&&d.nameKo!==row.name)put("한글명",d.nameKo);
 put("임직원",d.employees!=null?Number(d.employees).toLocaleString("ko-KR")+"명":null);
 put("본사",[d.city,d.state,d.country].filter(Boolean).join(", "));
 put("거래소",row.market);
 let h='<div class="abmeta">'+m.join("")+"</div>";
 if(d.website)h+='<div class="abmeta"><span><a href="'+esc(d.website)+
  '" target="_blank" rel="noopener">🌐 '+esc(d.website.replace(/^https?:[/][/]/,""))+
  "</a></span></div>";
 h+=d.summary
  ? '<div class="abs">'+esc(d.summary)+"</div>"
  : '<div class="abnote">사업 설명이 제공되지 않는 종목입니다.</div>';
 h+='<div class="abnote">출처: '+(
  d.lang==="ko" ? "네이버 금융 기업개요(한국어)"
  : d.lang==="ko-mt" ? "야후 파이낸스 기업 개요 — 기계 번역이라 표현이 어색할 수 있습니다"
  : "야후 파이낸스 기업 개요 — 번역에 실패해 영문 원문입니다")+"</div>";
 $("#aboutbox").innerHTML=h}

async function openAbout(row){
 $("#aboutbox").innerHTML='<div class="abnote">개요를 불러오는 중…</div>';
 try{
  const d=await loadAbout(row.code);
  if(!dRow||dRow.code!==row.code)return;
  renderAbout(d,row);
 }catch(e){
  if(!dRow||dRow.code!==row.code)return;
  $("#aboutbox").innerHTML='<div class="abnote">'+esc(e.message)+
   " — ‘보고서’ 탭의 야후 파이낸스에서 볼 수 있습니다.</div>"}}

function showPane(p){
 document.querySelectorAll("#dtabs button").forEach(b=>
  b.className=b.dataset.p===p?"on":"");
 document.querySelectorAll("#dlg .pane").forEach(el=>
  el.className="pane"+(el.id==="p-"+p?" on":""));
 if(!dRow)return;
 if(p==="diag")$("#diagbox").innerHTML=diagHtml(dRow.code);
 if(p==="chart"&&dRows)scheduleDraw();
 if(p==="fin")openFin(dRow,false);
 if(p==="year")openFin(dRow,true);
 if(p==="news")openNews(dRow);
 if(p==="about")openAbout(dRow);
 if(p==="memo")openMemo(dRow)}

// ---- 열기·닫기 ----
async function openStock(row){
 dRow=row;dRows=null;dInd=null;dHover=null;geo=null;dEnd=null;
 $("#dtitle").innerHTML=esc(row.name_full||row.name)+"<span>"+esc(row.code)+"</span>";
 // 원본과 다름: 머리줄은 스크리너가 가진 것(테마·판정·주가·12개월)으로 채운다.
 const s=SCR.stocks[row.code]||{},th=SCR.themes[s.theme]||{};
 $("#dsub").textContent=[s.theme?s.theme+" 테마":"",th.v||"",
  s.last!=null?"주가 $"+px2(s.last):"",
  s.abs_12m!=null?"12개월 "+(s.abs_12m>0?"+":"")+s.abs_12m.toFixed(1)+"%":"",
  s.pick?"추천 "+s.pick+"번":""].filter(Boolean).join(" · ");
 links(row);
 $("#dleg").innerHTML="";
 indBar();
 // 원본과 다름: 첫 탭은 '스크리너 진단'. 주가는 뒤에서 미리 받아 둔다.
 showPane("diag");
 $("#ov").hidden=false;
 document.body.style.overflow="hidden";
 chartMsg("주가를 불러오는 중…");
 try{
  const rows=await loadOhlcv(row.code);
  if(!dRow||dRow.code!==row.code)return;   // 그 사이 다른 종목을 열었으면 버린다
  dRaw=rows;chartMsg(null);applyTF();
  // 원본과 다름: 거래소를 알게 됐으니 보고서 링크(Motley Fool·구글)를 다시 만든다.
  const ex=exCache.get(row.code);
  if(ex&&!row.market){row.market=ex;links(row)}
 }catch(e){
  if(!dRow||dRow.code!==row.code)return;
  chartMsg(e.message+" — ‘보고서’ 탭의 야후 파이낸스에서 볼 수 있습니다.")}
}
function closeStock(){
 $("#ov").hidden=true;document.body.style.overflow="";
 dRow=null;dRows=null;dHover=null;$("#tip").style.display="none"}

// 원본과 다름: 표 대신 대시보드 곳곳의 data-tk(티커) 요소를 누르면 연다.
// 카드 머리·종목표가 다시 그려져도 되도록 문서 전체에 한 번만 건다.
document.addEventListener("click",e=>{
 const el=e.target.closest&&e.target.closest("[data-tk]");
 if(el&&!el.closest("#ov")){
  e.preventDefault();
  openByTicker(el.dataset.tk);
  return}
 // 진단 탭의 '테마 카드 보기' 는 대시보드 탭 전환(#tN)으로 넘어간다 — 창은 닫는다.
 const a=e.target.closest&&e.target.closest('#ov a[href^="#t"]');
 if(a)closeStock()});
$("#dclose").onclick=closeStock;
$("#ov").onclick=e=>{if(e.target.id==="ov")closeStock()};
document.addEventListener("keydown",e=>{
 if(e.key==="Escape"&&!$("#ov").hidden)closeStock()});
document.querySelectorAll("#dtabs button").forEach(b=>
 b.onclick=()=>showPane(b.dataset.p));
document.querySelectorAll("#rng button").forEach(b=>b.onclick=()=>{
 dDays=+b.dataset.d;
 dBars=barsFor(dDays,dTF)+FWD;
 dEnd=null;                               // 오른쪽 끝(최근)으로 되돌린다
 document.querySelectorAll("#rng button").forEach(x=>x.className=x===b?"on":"");
 dHover=null;scheduleDraw()});
document.querySelectorAll("#tf button").forEach(b=>b.onclick=()=>{
 dTF=b.dataset.t;saveG("tf",dTF);
 document.querySelectorAll("#tf button").forEach(x=>x.className=x===b?"on":"");
 applyTF()});
document.querySelectorAll("#tf button").forEach(b=>{
 if(b.dataset.t===dTF)b.className="on";else b.className=""});
$("#dlog").onclick=()=>{
 dLog=!dLog;$("#dlog").className="tab"+(dLog?" on":"");scheduleDraw()};

/* ---- 확대·이동 ----
   휠은 마우스가 가리키는 날을 붙잡은 채 창을 넓히고 좁힌다(그 자리가 안 밀린다).
   끌면 좌우로 움직이고, 더블클릭이면 처음 상태로. */
const clampEnd=(v,win,T)=>Math.max(win-1,Math.min(T-1,v));
let panX=null,panEnd=null;
$("#cv").addEventListener("wheel",e=>{
 if(!dRows||!geo)return;
 e.preventDefault();
 const T=dRows.length+FWD,cur=geo.i1-geo.i0+1;
 const rect=$("#cv").getBoundingClientRect();
 const at=Math.max(geo.i0,Math.min(geo.i1,
  Math.round((e.clientX-rect.left-geo.padL)/geo.bw-0.5)+geo.i0));
 const win=Math.max(20,Math.min(T,Math.round(cur*(e.deltaY>0?1.2:1/1.2))));
 let i0=Math.round(at-(at-geo.i0)*win/cur);
 i0=Math.max(0,Math.min(T-win,i0));
 dBars=win;dEnd=i0+win-1;
 scheduleDraw()},{passive:false});
$("#cv").addEventListener("mousedown",e=>{
 if(!geo)return;
 panX=e.clientX;panEnd=geo.i1;$("#cv").style.cursor="grabbing"});
window.addEventListener("mouseup",()=>{
 if(panX==null)return;panX=null;$("#cv").style.cursor=""});
$("#cv").addEventListener("dblclick",()=>{
 // 원본과 다름: 원본은 없는 속성(data-b)을 읽어 칸 수가 NaN 이 되고 차트가
 // 비었다. 지금 고른 기간(data-d)으로 되돌린다.
 dBars=barsFor(dDays,dTF)+FWD;dEnd=null;dHover=null;scheduleDraw()});
$("#cv").addEventListener("mousemove",e=>{
 if(!geo)return;
 const rect=$("#cv").getBoundingClientRect();
 if(panX!=null){                          // 끌어서 이동 — 이때는 십자선을 안 옮긴다
  const T=dRows.length+FWD,win=geo.i1-geo.i0+1;
  const shift=Math.round((panX-e.clientX)/geo.bw);
  const nx=clampEnd(panEnd+shift,win,T);
  if(nx!==dEnd){dEnd=nx;scheduleDraw()}
  return}
 const i=Math.round((e.clientX-rect.left-geo.padL)/geo.bw-0.5)+geo.i0;
 const c=Math.max(geo.i0,Math.min(geo.nv,i));
 if(c!==dHover){dHover=c;scheduleDraw()}});
$("#cv").addEventListener("mouseleave",()=>{
 if(dHover==null)return;dHover=null;scheduleDraw()});
window.addEventListener("resize",()=>{if(dRows)scheduleDraw()});

/* ---- 스크리너 진단 탭 (이 도구에만 있는 탭) ----
   이 종목을 스크리너가 어떻게 봤는지 — 소속 테마와 판정, 수혜·여력·종합 점수,
   실적·주가 숫자, '왜 아직 안 올랐나' 진단. 숫자는 페이지에 심어 둔 것
   (window.SCR_DETAIL, 대시보드를 만들 때 같이 생성)이라 서버를 부르지 않는다. */
function sgn(v,d,suf){
 if(v==null||!isFinite(v))return '<span class="miss">—</span>';
 const c=v>0?"pos":v<0?"neg":"";
 return '<span class="'+c+'">'+(v>0?"+":"")+Number(v).toFixed(d)+suf+"</span>"}
const sc=v=>v==null?"—":String(Math.round(v));
function diagHtml(code){
 const s=SCR.stocks[code];
 if(!s)return '<div class="abnote">이 종목은 스크리너 데이터가 없습니다.</div>';
 const th=SCR.themes[s.theme]||{};
 let h='<div class="dgtop">'+
  '<div class="dgbox"><span>종합</span><strong>'+sc(s.total)+'</strong><em>√(수혜 × 여력)</em></div>'+
  '<div class="dgbox"><span>수혜</span><strong>'+sc(s.benefit)+'</strong><em>실적으로 확인된 정도</em></div>'+
  '<div class="dgbox"><span>여력</span><strong>'+sc(s.upside)+'</strong><em>아직 덜 오른 정도</em></div>'+
  '<div class="dgbox"><span>테마 안 순위</span><strong>'+(s.rank||"—")+
   '<small style="font-size:13px;font-weight:600"> / '+(s.n||"—")+'</small></strong>'+
   '<em>'+(s.pick?"한눈에 탭 추천 "+s.pick+"번":"수혜 × 여력 순")+'</em></div></div>';
 h+='<div class="dgsec"><h3>소속 테마</h3><div class="dgtheme">'+
  '<span class="dgchip">'+esc(s.theme||"—")+'</span>'+
  (th.v?'<span class="dgchip">'+esc(th.v)+'</span>':"")+
  (th.vt?esc(th.vt)+" ":"")+
  '<br>촉매 '+sc(th.cs)+' · 미반영 '+sc(th.us)+
  (th.rel!=null?' · 테마 주가 12개월 시장 대비 '+sgn(th.rel,0,"%p"):"")+
  (th.i?' · <a href="#t'+th.i+'">테마 카드 보기 ›</a>':"")+'</div></div>';
 const row=(label,val,note)=>'<tr><th>'+label+'</th><td class="v">'+val+
  '</td><td class="n">'+(note||"")+'</td></tr>';
 let t='';
 t+=row("매출 증가율",sgn(s.rev_yoy,1,"%"),
  "최근 4개 분기 합을 1년 전과 비교"+(s.rev_accel!=null?" · 직전 분기보다 "+
  (s.rev_accel>=0?"빨라짐 ":"느려짐 ")+sgn(s.rev_accel,1,"%p"):""));
 t+=row("이익률 개선",sgn(s.opm_delta,1,"%p"),
  s.op_margin!=null?"영업이익률 "+Number(s.op_margin).toFixed(1)+"% (1년 전 대비 변화)":"");
 t+=row("주가 1개월",sgn(s.ret_1m,1,"%"),"");
 t+=row("주가 3개월",sgn(s.ret_3m,1,"%"),"");
 t+=row("주가 12개월",sgn(s.abs_12m,1,"%"),
  s.rel_12m!=null?"S&amp;P500 대비 "+sgn(s.rel_12m,1,"%p"):"");
 if(s.drawdown!=null)t+=row("1년 고점 대비",sgn(-s.drawdown,1,"%"),"최근 1년 최고가에서 얼마나 내려와 있나");
 if(s.derate!=null)t+=row("멀티플 변화",sgn(s.derate,0,"%"),
  "주가 ÷ 영업이익 배수의 1년 변화 — 마이너스면 이익에 비해 주가가 덜 올랐다는 뜻");
 t+=row("최근 실적 발표",s.earn_date?esc(s.earn_date):'<span class="miss">—</span>',
  "SEC 8-K(실적) 제출일");
 t+=row("발표 반응",sgn(s.earn_react,1,"%p"),
  "발표 전후 며칠 주가의 시장 대비 움직임"+(s.eps_surprise!=null?
  " · EPS 서프라이즈 "+sgn(s.eps_surprise,1,"%"):""));
 h+='<div class="dgsec"><h3>숫자로 본 이 종목</h3><table class="dgtbl">'+t+'</table>'+
  (s.annual_basis?'<div class="abnote">분기 재무가 없어 연간 재무로 계산했습니다(1년 늦은 숫자일 수 있음).</div>':"")+
  '</div>';
 h+='<div class="dgsec"><h3>왜 아직 안 올랐나 — 데이터로 판별되는 것만</h3>';
 if(s.why&&s.why.length)
  h+='<ul class="dgwhy">'+s.why.map(x=>"<li>"+esc(x)+"</li>").join("")+"</ul>";
 else
  h+='<div class="abnote">12개월 '+sgn(s.abs_12m,0,"%")+' 오른 종목이라 '+
   '‘안 오른 이유’ 진단은 해당하지 않습니다.</div>';
 h+='</div><div class="abnote" style="margin-top:16px">수혜·여력은 <b>같은 테마 안에서의 상대 순위</b>(0~100)입니다 — '+
  '수혜 100은 ‘이 테마 종목 중 실적이 가장 좋다’는 뜻이지 절대 평가가 아닙니다. '+
  '종합은 둘을 곱해 제곱근을 낸 값이라 한쪽이 낮으면 같이 낮아집니다. 이 숫자는 대시보드를 만든 시점 기준입니다.</div>';
 return h}

/* 티커로 연다 — 대시보드 클릭과 테스트가 함께 쓴다. */
function openByTicker(tk){
 tk=String(tk||"").toUpperCase();
 const s=SCR.stocks[tk]||{};
 openStock({code:tk,name:s.name||tk,cik:s.cik||null,market:""})}
window.openStockDetail=openByTicker;
})();

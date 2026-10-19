/* Figura 1 do painel: óbitos observados x esperados sem calor, semanal e diária.
   Os modelos (GAM + DLNM, um por segmento) são ajustados em R (calcular_figura1.R); o navegador só escolhe o recorte e desenha. */
(function(){
"use strict";
const $ = id => document.getElementById(id);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fn = (v,d=0) => v.toLocaleString("pt-BR",{minimumFractionDigits:d,maximumFractionDigits:d});
const fr = r => r.toFixed(2).replace(".",",");
const pct = r => (r-1)*100;
const fp = (v,d=1) => (v>=0?"+":"−")+Math.abs(v).toFixed(d).replace(".",",")+"%";
const b64 = s => Uint8Array.from(atob(s), c=>c.charCodeAt(0));
const dBR = s => s.split("-").reverse().join("/");
const SEMANA=["dom","seg","ter","qua","qui","sex","sáb"], MESES=["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"];
const NOMELOC = {"Outros estabelecimentos de saúde":"Outros estabelecimentos"};
const nm = l => NOMELOC[l] || l;
function fillSel(el, opts, val){ el.innerHTML = opts.map(o=>`<option value="${o.v??o}">${o.t??o}</option>`).join(""); if(val!==undefined) el.value = val; }

async function lerDados(){
  const el = $("dados-b64"); if(!el) throw new Error("Dados não encontrados na página.");
  if(typeof DecompressionStream==="undefined") throw new Error("Este navegador não lê os dados compactados; use uma versão recente do Chrome, Edge, Firefox ou Safari.");
  const txt = await new Response(new Blob([b64(el.textContent.trim())]).stream().pipeThrough(new DecompressionStream("deflate"))).text();
  return JSON.parse(txt);
}

/* ---------- abas ---------- */
document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>{
  document.querySelectorAll("nav button").forEach(x=>x.setAttribute("aria-selected",x===b));
  ["serie","sobre"].forEach(t=>{ const e=$("tab-"+t); if(e) e.classList.toggle("hide",t!==b.dataset.tab) });
  if(b.dataset.tab==="serie" && window.__desenhar) window.__desenhar();
});

lerDados().then(iniciar).catch(e=>{ $("s-note").textContent = e.message });

function iniciar(D){
const M = D.meta, sem = D.sem, dias = D.dias, cl = D.cl, fl = D.fl;
const nSem = sem.ini.length;
/* Modo Shiny (M.sob_demanda): a página traz só o calendário e o clima; cada recorte e medida de calor chega do servidor quando é escolhido e
   fica guardado aqui (D.k, D.o, D.m, D.So, D.S têm o mesmo formato do JSON completo do Quarto, preenchido aos poucos). */
const SH = !!(M.sob_demanda && window.Shiny);
let ELEG = new Set(M.elegiveis||[]), POP = M.pop, CHAVE = M.dados && M.dados.chave, nPedidos = 0;
const PEND = new Set(), idPedido = (pop,key,ex) => pop+"|"+ex+"|"+key;
const ix = new Map();
const zerar = () => { D.k=[]; D.o=[]; D.m={}; D.S={}; D.So={}; Object.keys(M.exposicoes).forEach(e=>{ D.m[e]={f:[],d:[],rr:[],e:[]}; D.S[e]={} }); ix.clear() };
if(SH) zerar(); else D.k.forEach((k,i)=>ix.set(k,i));
const cd = {hi_max:cl.hi_max, hi_med:{o:cl.hi_med}, t_med:{o:cl.t_med}, nc:cl.nc};
const diaIx = new Map(dias.map((d,i)=>[d,i]));
const anos = [...new Set(sem.ano)].sort();
// dia de calor = pelo menos 4 h com índice de calor >= 36 °C (NC2 ou mais); exposto = dia de calor em t, t-1, t-2 ou t-3
const EV = cl.h36.map(v=>v!=null&&v>=4?1:0);
const XW = EV.map((_,i)=>{ for(let k=0;k<4;k++) if(i-k>=0&&EV[i-k]) return 1; return 0 });
const EXP = M.exposicoes;
const KEXP = Object.keys(EXP);
const REF_TXT = {horas:(v,u)=>`${fn(v)} ${u} por dia de índice de calor ≥ 36 °C`, haat:(v,u)=>`${fn(v)} ${u} por dia acima de 36 °C`};
const COR_ACIMA=()=>css("--acima"), COR_ABAIXO=()=>css("--abaixo");

$("sub").textContent = `Óbitos por causas naturais (SIM/DATASUS) de ${dBR(M.inicio)} a ${dBR(M.fim)}, contra o número esperado sem calor, por local do óbito, faixa etária (UNICEF) e raça/cor. Estudo ecológico de séries temporais, descritivo e exploratório. O esperado vem de um modelo próprio para cada recorte (GAM com defasagens distribuídas, o modelo do João).`;

fillSel($("s-local"), M.locais.map(l=>({v:l,t:nm(l)})), "Todos os locais");
fillSel($("s-faixa"), M.faixas, "Todas as idades");
fillSel($("s-raca"), [{v:"Todas",t:"Todas"},{v:"Branca",t:"Branca (referência)"},{v:"Preta",t:"Preta"},{v:"Parda",t:"Parda"},{v:"PPI",t:"Pretos, pardos e indígenas (PPI)"}], "Todas");
fillSel($("s-exp"), KEXP.map(k=>({v:k,t:EXP[k].nome})), KEXP[0]);
fillSel($("s-ini"), anos, anos[0]); fillSel($("s-fim"), anos, anos[anos.length-1]);

const keyF1 = () => $("s-local").value+"|"+$("s-faixa").value+($("s-raca").value!=="Todas"?"|"+$("s-raca").value:"");
function racaSync(){ const r=$("s-raca").value!=="Todas"; if(r) $("s-faixa").value="Todas as idades"; $("s-faixa").disabled=r;
  $("s-faixa").title=r?"As séries por raça/cor são calculadas para todas as idades; volte a Todas em raça/cor para escolher uma faixa etária.":"" }
function racaNota(){ const rc=D.rc; if(!rc){ $("s-raca-nota").textContent=""; return }
  const tot=Object.values(rc).reduce((a,b)=>a+b,0), pc=v=>fn(100*(v||0)/tot,1)+"%", n=k=>rc[k]||0;
  $("s-raca-nota").textContent=`Raça/cor (campo RACACOR do SIM) nos ${fn(tot)} óbitos naturais da série: branca ${pc(n("Branca"))}, parda ${pc(n("Parda"))}, preta ${pc(n("Preta"))}, amarela ${pc(n("Amarela"))}, indígena ${pc(n("Indígena"))} e sem cor informada ${pc(n("Ignorada"))}. Indígena (${fn(n("Indígena"))} óbitos) e amarela (${fn(n("Amarela"))}) não têm óbitos suficientes para uma série própria. Os indígenas entram no agregado PPI (preta, parda e indígena), e amarela e sem cor informada entram só em Todas. As séries por raça/cor valem para todas as idades.` }

["s-local","s-faixa","s-exp","s-crit","s-ini","s-fim","s-bar","s-lim","s-cor"].forEach(i=>$(i).onchange=desenhar);
$("s-raca").onchange=()=>{ racaSync(); desenhar() };
$("s-esc").onchange=()=>{ if($("s-esc").value==="dia"){ const f=+$("s-fim").value, i=+$("s-ini").value;      // escala diária: começa com os 3 últimos anos
    if(f-i+1>3){ const novo=Math.max(f-2,anos[0]); if([...$("s-ini").options].some(o=>+o.value===novo)) $("s-ini").value=novo } }
  desenhar() };
$("s-lim").oninput=desenhar;

/* ---------- plugins do gráfico ---------- */
const hachura=ctx=>{const c=document.createElement("canvas");c.width=c.height=8;const g=c.getContext("2d");g.strokeStyle=css("--cinza");g.lineWidth=1.3;g.beginPath();g.moveTo(-1,9);g.lineTo(9,-1);g.stroke();return ctx.createPattern(c,"repeat")};
const covPlugin={id:"covid",beforeDatasetsDraw(c,_a,o){const {ctx,chartArea:a,scales:{x}}=c;if(!o)return;ctx.save();
  const w=x.getPixelForValue(1)-x.getPixelForValue(0);
  const runs=(arr,f)=>{let i=0;while(i<arr.length){if(arr[i]){let j=i;while(j+1<arr.length&&arr[j+1])j++;f(x.getPixelForValue(i)-w/2,x.getPixelForValue(j)+w/2);i=j+1}else i++}};
  if(o.inc){ctx.fillStyle=css("--cinza");ctx.globalAlpha=.16;runs(o.inc,(l,r)=>ctx.fillRect(l,a.top,r-l,a.bottom-a.top))}
  if(o.nc){ctx.fillStyle=hachura(ctx);ctx.globalAlpha=.6;runs(o.nc,(l,r)=>ctx.fillRect(l,a.top,r-l,a.bottom-a.top))}
  if(o.cov){ctx.fillStyle=css("--cinza");ctx.globalAlpha=.55;runs(o.cov,(l,r)=>ctx.fillRect(l,a.bottom-5,r-l,5))}
  ctx.restore()}};
const BARRA_NOME={t_med:"Temperatura média do dia",hi_max:"Índice de calor máx. do dia",hi_med:"Índice de calor médio do dia"};
const NC_COR={1:null,2:"rgba(224,138,80,.42)",3:"rgba(205,102,36,.75)",4:"rgba(196,60,43,.85)",5:"rgba(98,24,70,.92)"};
const barPlugin={id:"barras",beforeDatasetsDraw(c,_a,o){ if(!o||!o.vals) return;
  const {ctx,chartArea:a,scales:{x,yt}}=c; if(!yt) return;
  const w=x.getPixelForValue(1)-x.getPixelForValue(0), nk=(o.vals[0]||[]).length||7, dw=w/nk, base=yt.getPixelForValue(0);
  ctx.save(); ctx.beginPath(); ctx.rect(a.left,a.top,a.right-a.left,a.bottom-a.top); ctx.clip();
  o.vals.forEach((wk,i)=>{ const x0=x.getPixelForValue(i)-w/2;
    for(let k=0;k<nk;k++){ const v=wk[k]; if(v==null||isNaN(v)) continue; const y=yt.getPixelForValue(v);
      let f=o.cor0; if(o.nc){ const n=o.nc[i][k]; f=n>1?NC_COR[n]:o.cor0 } else if(v>o.lim) f=o.cor1;
      ctx.fillStyle=f; ctx.fillRect(x0+k*dw, y, Math.max(dw*.9,.7), base-y) } });
  ctx.strokeStyle=o.corL; ctx.lineWidth=1; ctx.setLineDash([5,4]); ctx.fillStyle=o.corL; ctx.font="11px Inter, system-ui, sans-serif"; ctx.textAlign="right";
  (o.linhas||[]).forEach(l=>{ const yl=yt.getPixelForValue(l.v); ctx.beginPath(); ctx.moveTo(a.left,yl); ctx.lineTo(a.right,yl); ctx.stroke(); ctx.fillText(l.t, a.right-4, yl-4) });
  ctx.setLineDash([]); ctx.restore() }};
const pontoPlugin={id:"traco",beforeDatasetsDraw(c,_a,o){ if(!o) return;
  const {ctx,chartArea:a,scales:{x,y}}=c; ctx.save(); ctx.beginPath(); ctx.rect(a.left,a.top,a.right-a.left,a.bottom-a.top); ctx.clip(); ctx.lineWidth=o.lw; ctx.lineCap="butt";
  for(let i=0;i<o.ob.length;i++){ const v=o.ob[i], e=o.es[i]; if(v==null||e==null) continue;
    ctx.strokeStyle=v>e?o.acima:o.abaixo; ctx.globalAlpha=o.al; const px=x.getPixelForValue(i); ctx.beginPath(); ctx.moveTo(px,y.getPixelForValue(v)); ctx.lineTo(px,y.getPixelForValue(e)); ctx.stroke() }
  ctx.restore() }};

/* ---------- RR do modelo do segmento ---------- */
function rrDoModelo(k, ex){
  const r=D.m[ex].rr[k], e=EXP[ex], t=i=>`${fr(r[i])} (IC 95%: ${fr(r[i+1])} a ${fr(r[i+2])})`;
  return [0,3].map((i,j)=>[t(i), `RR acumulado em 0 a ${M.lag} dias com ${REF_TXT[ex](e.ref[j],e.unidade)} em todos os ${M.lag+1} dias`]) }
const modeloTxt = (k, ex) => { const f=D.m[ex].f[k], d=D.m[ex].d[k];
  return f==="nb"?`binomial negativa (theta = ${fn(d,1)})`:`quase-Poisson (dispersão φ = ${fn(d,2)}; a binomial negativa não convergiu)` };

let chS=null;
function desenhar(){
  if($("tab-serie").classList.contains("hide")) return;
  const dia=$("s-esc").value==="dia";
  $("s-critw").classList.toggle("hide",dia);
  $("s-h2").textContent=(dia?"Óbitos diários por causas naturais: cada dia em relação ao esperado sem calor":"Óbitos semanais por causas naturais: observados, esperados sem calor e semanas de calor")+($("s-raca").value!=="Todas"?` (raça/cor: ${({PPI:"preta, parda e indígena"})[$("s-raca").value]||$("s-raca").value.toLowerCase()})`:"");
  racaNota();
  const key=keyF1(), ex=$("s-exp").value;
  if(SH && ELEG.has(key) && !carregado(key,ex)){ pedir(key,ex); return }       // mantém a figura anterior, esmaecida, até o servidor responder
  quadros(false);
  if(chS){chS.destroy();chS=null}
  const k=ix.get(key);
  if(k==null){ $("s-kpis").innerHTML=""; $("s-leg").innerHTML=""; $("i-serie").innerHTML=""; $("s-note").textContent=`Menos de ${M.min_obitos} óbitos nesta combinação de filtros: série não estimada.`; return }
  dia?desenharDia(k):desenharSemana(k)
}
window.__desenhar=desenhar;

/* ---------- modo Shiny: pedir recortes ao servidor ---------- */
const quadros = on => { $("s-kpis").classList.toggle("calc",on); $("s-chart").parentNode.classList.toggle("calc",on) };
const carregado = (key,ex) => ix.has(key) && D.m[ex] && D.m[ex].f[ix.get(key)]!==undefined && D.S[ex][key]!==undefined;
function pedir(key,ex){
  quadros(true);
  $("s-note").textContent="Calculando o modelo deste recorte (de 3 a 15 segundos na primeira vez; depois o resultado fica guardado no servidor)…";
  const id=idPedido(POP,key,ex); if(PEND.has(id)) return; PEND.add(id);
  window.Shiny.setInputValue("pedido",{key,ex,pop:POP,chave:CHAVE,n:++nPedidos},{priority:"event"});
}
function mesclar(key,ex,p){
  let k=ix.get(key); if(k==null){ k=D.k.length; D.k.push(key); ix.set(key,k) }
  D.o[k]=p.o; const m=D.m[ex]; m.f[k]=p.f; m.d[k]=p.d; m.rr[k]=p.rr; m.e[k]=p.e;
  D.So[key]=p.So; D.S[ex][key]=p.S;
}
function registrarShiny(){
  const S=window.Shiny;
  S.addCustomMessageHandler("segmento", msg=>{
    PEND.delete(idPedido(msg.pop,msg.key,msg.ex));
    if(msg.pop!==POP || msg.chave!==CHAVE) return;                                // resposta de outra população ou de uma versão antiga dos dados
    mesclar(msg.key,msg.ex,JSON.parse(msg.json));
    if(msg.key===keyF1() && msg.ex===$("s-exp").value) desenhar();
  });
  S.addCustomMessageHandler("base", msg=>{                                         // troca de população
    const b=JSON.parse(msg.json);
    if(b.meta.n_dias!==dias.length){ location.reload(); return }                   // calendário diferente: recarrega a página
    Object.assign(M,b.meta); D.rc=b.rc; ELEG=new Set(M.elegiveis); POP=M.pop; CHAVE=M.dados.chave; PEND.clear(); zerar(); desenhar();
  });
  S.addCustomMessageHandler("erro_segmento", msg=>{
    PEND.delete(idPedido(msg.pop,msg.key,msg.ex));
    if(msg.pop!==POP || msg.key!==keyF1() || msg.ex!==$("s-exp").value) return;     // erro de um pedido que o usuário já deixou para trás
    quadros(false);
    $("s-note").innerHTML = msg.codigo==="dados_mudaram"
      ? 'Os dados foram atualizados no servidor. <a href="">Recarregue a página</a> para ver a versão nova.'
      : "Não foi possível ajustar o modelo deste recorte: "+String(msg.mensagem||"erro desconhecido").replace(/[<>&]/g,"");
  });
  const sel=$("s-pop");
  if(sel){ sel.value=POP;
    sel.onchange=()=>{ POP=sel.value; CHAVE=null; ELEG=new Set(); PEND.clear(); zerar(); quadros(true);
      $("s-note").textContent="Carregando a população selecionada…"; S.setInputValue("pop",POP,{priority:"event"}) } }
}

/* ---------- barras de clima ao fundo (comum às duas escalas) ---------- */
function barrasClima(idxDias, porSemana){
  const bv=$("s-bar").value, lim=isFinite(parseFloat($("s-lim").value))?parseFloat($("s-lim").value):32, modoNC=$("s-cor").value==="nc";
  $("s-limw").classList.toggle("hide",modoNC);
  let bars=null, ncs=null, bmax=0, bDias=0, bAcima=0; const nNC={1:0,2:0,3:0,4:0,5:0};
  if(bv!=="no"){ const arr=bv==="hi_max"?cd.hi_max:cd[bv].o;
    const v1=j=>{ const v=j==null?null:arr[j]; return (v==null||isNaN(v))?null:v };
    const tr=v=>{ if(v==null) return null; bDias++; if(v>lim) bAcima++; if(v>bmax) bmax=v; return v };
    if(porSemana){ bars=idxDias.map(j0=>[0,1,2,3,4,5,6].map(k=>tr(v1(j0==null?null:j0+k))));
      ncs=idxDias.map(j0=>[0,1,2,3,4,5,6].map(k=>{const n=j0==null?null:cd.nc[j0+k]; if(n!=null) nNC[n]++; return n??null})) }
    else { bars=idxDias.map(j=>[tr(v1(j))]); ncs=idxDias.map(j=>{const q=cd.nc[j]; if(q!=null) nNC[q]++; return [q??null]}) } }
  const tmax=Math.ceil(Math.max(bmax,modoNC?(bv==="hi_max"?44:0):lim,10)/10)*10;
  const linhas=!bars?[]:modoNC?(bv==="hi_max"?[{v:36,t:"36 °C"},{v:40,t:"40 °C"},{v:44,t:"44 °C"}]:[]):[{v:lim,t:lim.toString().replace(".",",")+" °C"}];
  return {bv,lim,modoNC,bars,ncs,bmax,bAcima,bDias,nNC,tmax,linhas} }
function legendaBarras(B,cz,la,mk){
  if(!B.bars) return "";
  return `<span><i style="background:${mk(cz,.30)}"></i>${BARRA_NOME[B.bv]} (coluna diária, eixo da direita)</span>`+(B.modoNC?[2,3,4,5].map(n=>`<span><i style="background:${NC_COR[n]}"></i>NC${n} (${fn(B.nNC[n])} dias)</span>`).join("")+`<span><i style="background:${mk(cz,.30)}"></i>NC1 (${fn(B.nNC[1])} dias)</span>`:`<span><i style="background:${mk(la,.62)}"></i>dia acima de ${fn(B.lim,1)} °C</span>`) }
const mkCor=(c,al)=>{const m=c.match(/#(..)(..)(..)/);return m?`rgba(${parseInt(m[1],16)},${parseInt(m[2],16)},${parseInt(m[3],16)},${al})`:c};
const NOTA_BARRAS = B => B.bars?` Colunas ao fundo: ${BARRA_NOME[B.bv].toLowerCase()} de cada dia, no eixo da direita (°C). `+
  (B.modoNC?"A cor é o Nível de Calor (NC) do protocolo da Prefeitura, reconstruído a partir das horas por dia com índice de calor acima de 36, 40 e 44 °C: NC2 = ao menos 4 h acima de 36 °C em 1 ou 2 dias seguidos; NC3 = o mesmo por 3 dias ou mais; NC4 = ao menos 4 h acima de 40 °C dentro de uma sequência de NC3; NC5 = ao menos 2 h acima de 44 °C dentro de uma sequência de NC3. Usa só o observado (o decreto também admite a previsão) e não substitui o nível divulgado pelo COR-Rio; como o nível vem das horas de pico, a cor não acompanha a altura da coluna quando ela mostra o valor médio ou a temperatura média."
   :`Em laranja, os dias acima de ${fn(B.lim,1)} °C: ${fn(B.bAcima)} de ${fn(B.bDias)} dias no período mostrado (${fn(100*B.bAcima/Math.max(B.bDias,1),1)}%).`):"";
const kpiHtml = lista => lista.map(([v,l])=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
const baixar = (nome, conteudo) => { const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([conteudo],{type:"text/csv"}));a.download=nome;a.click() };

/* ---------- semanal ---------- */
function desenharSemana(k){
  const ex=$("s-exp").value, crit=$("s-crit").value, key=keyF1();
  const S=D.S[ex][key], O=D.So[key];
  const y0=+$("s-ini").value, y1=Math.max(+$("s-fim").value,y0);
  const idx=[...Array(nSem).keys()].filter(i=>sem.ano[i]>=y0&&sem.ano[i]<=y1);
  const pick=arr=>idx.map(i=>arr[i]);
  const labels=idx.map(i=>`SE ${sem.se[i]}/${sem.ano[i]}`);
  const es=pick(S.e), lo=pick(S.l), up=pick(S.u);
  const nb=pick(sem.nb), nn=pick(sem.nn), cov=pick(sem.cov), inc=pick(sem.inc), nc=pick(sem.nc);
  const ob=pick(O).map((v,q)=>inc[q]?null:v);
  let dark=[],light=[];
  if(crit==="ic"){dark=nb.map(v=>v>=3?1:null);light=nb.map(v=>v>=1&&v<3?1:null)}
  if(crit==="nc"){dark=nn.map(v=>v>=1?1:null)}
  const calor = crit==="ic"? nb.map(v=>v>=3) : crit==="nc"? nn.map(v=>v>=1) : nb.map(()=>false);
  const acima=ob.map((v,i)=>!cov[i]&&v!=null&&up[i]!=null&&v>up[i]?v:null);
  const tickc=css("--mut"), gridc=css("--grid"), az=css("--azul"), la=css("--laranja"), cz=css("--cinza"), ink=css("--ink");
  const B=barrasClima(idx.map(i=>diaIx.get(sem.ini[i])), true);
  chS=new Chart($("s-chart"),{type:"bar",data:{labels,datasets:[
    {label:"darkcol",type:"bar",data:dark,yAxisID:"yb",backgroundColor:mkCor(la,.40),borderWidth:0,barPercentage:1,categoryPercentage:1,order:9},
    {label:"lightcol",type:"bar",data:light,yAxisID:"yb",backgroundColor:mkCor(la,.16),borderWidth:0,barPercentage:1,categoryPercentage:1,order:9},
    {label:"lo",type:"line",data:lo,borderWidth:0,pointRadius:0,order:6},
    {label:"Faixa esperada (95%)",type:"line",data:up,borderWidth:0,pointRadius:0,fill:"-1",backgroundColor:mkCor(az,.17),order:6},
    {label:"Observado",type:"line",data:ob,borderColor:cz,borderWidth:1.1,pointRadius:0,pointHoverRadius:4,order:3},
    {label:"Esperado sem calor",type:"line",data:es,borderColor:az,borderWidth:2,pointRadius:0,order:2},
    {label:"Acima da faixa",type:"line",data:acima,showLine:false,pointRadius:3,pointBackgroundColor:ink,pointBorderColor:css("--card"),pointBorderWidth:1,order:1},
    {label:"_eixo_t",type:"line",data:idx.map(()=>null),yAxisID:"yt",borderWidth:0,pointRadius:0}
  ]},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:"index",intersect:false},
    scales:{x:{grid:{display:false},ticks:{color:tickc,autoSkip:false,maxRotation:0,callback:function(v){const i=idx[v];return sem.se[i]===1?sem.ano[i]:""}}},
      y:{beginAtZero:true,grid:{color:gridc},ticks:{color:tickc},title:{display:true,text:"Óbitos por semana",color:tickc}},
      yb:{display:false,min:0,max:1},
      yt:{display:!!B.bars,position:"right",min:0,max:B.tmax*1.7,grid:{display:false},ticks:{color:tickc,stepSize:10,callback:v=>v<=B.tmax?v:""},title:{display:!!B.bars,text:B.bars?BARRA_NOME[B.bv]+" (°C)":"",color:tickc}}},
    plugins:{legend:{display:false},covid:{cov,inc,nc},barras:B.bars?{vals:B.bars,nc:B.modoNC?B.ncs:null,lim:B.lim,cor0:mkCor(cz,.30),cor1:mkCor(la,.62),corL:la,linhas:B.linhas}:null,
      tooltip:{filter:i=>["Observado","Esperado sem calor","Faixa esperada (95%)"].includes(i.dataset.label),
        callbacks:{label:c=>c.dataset.label==="Faixa esperada (95%)"?`Faixa 95%: ${lo[c.dataIndex]==null?"–":fn(lo[c.dataIndex])+" a "+fn(up[c.dataIndex])}`:`${c.dataset.label}: ${fn(c.parsed.y,c.dataset.label==="Observado"?0:1)}`,
          afterBody:it=>{const i=idx[it[0].dataIndex], q=it[0].dataIndex, L=[`Início da semana: ${dBR(sem.ini[i])}`,`Índice de calor máx.: ${sem.mxh[i]==null?"–":fn(sem.mxh[i],1)} °C · dias ≥ 36 °C: ${sem.nb[i]} · dias em NC2 a NC5: ${sem.nn[i]}`,`Temp. média: ${sem.mt[i]==null?"–":fn(sem.mt[i],1)} °C`];
            if(ob[q]!=null&&es[q]!=null) L.push(`Observado ÷ esperado sem calor: ${fr(ob[q]/es[q])}`);
            if(B.bars){const v=B.bars[q].filter(z=>z!=null);if(v.length){ let t=`${BARRA_NOME[B.bv]}: ${fn(Math.min(...v),1)} a ${fn(Math.max(...v),1)} °C na semana; `;
              if(B.modoNC&&B.ncs){const c={};B.ncs[q].forEach(n=>{if(n!=null&&n>1)c[n]=(c[n]||0)+1});const l=Object.keys(c).map(n=>`${c[n]} dia(s) em NC${n}`);t+=l.length?l.join(", "):"nenhum dia acima de NC1"}
              else t+=`${v.filter(z=>z>B.lim).length} dia(s) acima de ${fn(B.lim,1)} °C`; L.push(t)}}
            if(!sem.cl[i]) L.push("Sem dados de clima nesta semana");
            if(cov[q]) L.push("Período COVID (o modelo inclui um termo para o período; fora dos indicadores)");
            if(inc[q]) L.push("Sem registro de óbitos no SIM (fora do ajuste)");
            if(nc[q]) L.push("Registro não consolidado (semana no ajuste; o observado pode estar abaixo do real)");
            return L}}}}},
    plugins:[covPlugin,barPlugin]});
  $("s-leg").innerHTML=`<span><i class="ln" style="background:${cz}"></i>Observado</span><span><i class="ln" style="background:${az};height:3px"></i>Esperado sem calor</span><span><i style="background:${mkCor(az,.17)}"></i>Faixa 95%</span><span><i class="dt" style="background:${ink}"></i>Observado acima da faixa</span>`+
   (crit==="ic"?`<span><i style="background:${mkCor(la,.40)}"></i>≥ 3 dias com IC ≥ 36 °C</span><span><i style="background:${mkCor(la,.16)}"></i>1 a 2 dias</span>`:"")+(crit==="nc"?`<span><i style="background:${mkCor(la,.40)}"></i>Semana com dia em NC2 a NC5</span>`:"")+
   legendaBarras(B,cz,la,mkCor)+`<span><i style="background:${cz}"></i>COVID (termo próprio no modelo)</span>`+(inc.some(Boolean)?`<span><i style="background:${cz};opacity:.3"></i>Sem registro no SIM (fora do ajuste)</span>`:"")+(nc.some(Boolean)?`<span><i style="background:repeating-linear-gradient(135deg,${cz} 0 1.3px,transparent 1.3px 4px)"></i>Registro não consolidado (no ajuste)</span>`:"");
  // indicadores: sem COVID, sem semanas sem registro e sem semanas sem clima (semanas de registro não consolidado entram)
  const ok=idx.map((_,q)=>!(cov[q]||inc[q]||!sem.cl[idx[q]]||es[q]==null));
  const grp=f=>{let Oo=0,E=0,n=0,ab=0;ob.forEach((v,q)=>{if(ok[q]&&f(q)){Oo+=v;E+=es[q];n++;ab+=v>up[q]?1:0}});return {n,O:Oo,E,raz:E?Oo/E:NaN,ac:n?100*ab/n:NaN}};
  const H=grp(q=>calor[q]), N=grp(q=>!calor[q]);
  const tot=ob.reduce((x,y)=>x+(y||0),0);
  $("s-kpis").innerHTML=kpiHtml([
    [fn(tot),"óbitos na série selecionada"+(nc.some(Boolean)?` (inclui ${fn(nc.filter(Boolean).length)} semana(s) com registro não consolidado)`:"")],
    ...rrDoModelo(k,ex),
    [isFinite(H.raz)?fr(H.raz):"–","observado ÷ esperado sem calor nas "+H.n+" semanas de calor (soma dos óbitos ÷ soma dos esperados)"],
    [isFinite(N.raz)?fr(N.raz):"–","observado ÷ esperado sem calor nas "+N.n+" demais semanas"],
    [isFinite(H.ac)?fn(H.ac)+"%":"–","das semanas de calor com óbitos acima do limite superior de 95%"],
    [isFinite(N.ac)?fn(N.ac)+"%":"–","das demais semanas acima do limite (≈ 2,5% se o modelo estiver calibrado)"]
  ].concat(B.ncs&&B.bars?[[fn(B.nNC[2]+B.nNC[3]+B.nNC[4]+B.nNC[5]),`dias em nível de calor 2 a 5 do protocolo (NC4: ${fn(B.nNC[4])}; NC5: ${fn(B.nNC[5])})`]]:[]));
  const critTxt=crit==="ic"?"semanas com pelo menos 3 dias de índice de calor máximo ≥ 36 °C":"semanas com ao menos um dia em NC2 a NC5";
  $("i-serie").innerHTML=`<span class="t">Interpretação</span>`+(crit==="no"?`A linha azul é o número de óbitos esperado sem calor pelo modelo deste recorte (tendência de longo prazo, sazonalidade anual e período COVID, com o efeito do calor retirado); a faixa é o intervalo de 95% para uma semana. Pontos escuros marcam semanas em que o observado superou o limite superior. Escolha um critério de calor para comparar semanas com e sem calor.`:
   (H.n&&N.n?`Nas <b>${H.n}</b> ${critTxt}, foram observados <b>${fn(H.O)}</b> óbitos contra <b>${fn(H.E,0)}</b> esperados sem calor (observado ÷ esperado = <b>${fr(H.raz)}</b>, ou ${fp(pct(H.raz))}). Nas outras <b>${N.n}</b> semanas, <b>${fn(N.O)}</b> contra <b>${fn(N.E,0)}</b> (razão <b>${fr(N.raz)}</b>). Óbitos acima do limite superior da faixa de 95%: <b>${fn(H.ac)}%</b> das semanas de calor e <b>${fn(N.ac)}%</b> das demais; se o modelo estiver bem calibrado, cerca de 2,5% das semanas passam do limite por acaso. Esses percentuais contam semanas atípicas; a parcela de óbitos atribuída ao calor é outra medida. ${H.raz>N.raz?"A razão é maior nas semanas de calor.":"A razão não é maior nas semanas de calor."} O esperado vem de um modelo ajustado só a esta combinação de filtros, então a razão muda quando o recorte muda. A comparação é descritiva e não traz intervalo de confiança; a medida de associação é o RR acumulado do modelo, nos dois primeiros quadros.`:`Poucas semanas de calor no recorte selecionado para comparar.`));
  $("s-note").textContent=notaModelo(k,ex)+" Os indicadores excluem o período COVID (barra cinza na base; o modelo tem um termo próprio para ele) e as semanas sem nenhum óbito registrado no SIM (faixa cinza clara), onde o esperado não é traçado. As semanas de meses com registro não consolidado (hachuradas) entram no modelo e nos indicadores, e o registro nelas pode estar abaixo do real. Semana de calor = sombreada em tom escuro. Faixa de 95% = esperado semanal ± 1,96 × raiz da soma das variâncias diárias do modelo, multiplicada pela dispersão semanal φ = "+fr(S.phi)+" (estimada nos resíduos semanais; a faixa não inclui a incerteza dos coeficientes)."+(S.phi>3?" Atenção: φ alto indica que o modelo não acompanha bem a tendência de longo prazo desta série (por exemplo, uma mudança na forma de registrar o local do óbito), e por isso a faixa é larga.":"")+" A série começa em 2006 (SIM); o clima existe desde abril de 2007, e semanas sem clima não entram na comparação semanas de calor × demais."+NOTA_BARRAS(B);
  $("s-csv").onclick=()=>{let t="semana_inicio;ano_epi;se;observado;esperado_sem_calor;lim_inf;lim_sup;dias_ic36;dias_nc2_a_nc5;registro_sim\n";const c1=v=>v==null?"":v.toFixed(1).replace(".",",");
    idx.forEach((i,q)=>{t+=[sem.ini[i],sem.ano[i],sem.se[i],ob[q]??"",c1(es[q]),c1(lo[q]),c1(up[q]),nb[q],nn[q],inc[q]?"sem_registro":nc[q]?"nao_consolidado":""].join(";")+"\n"});
    baixar(`serie_semanal_${ex}_${key.replace(/[^a-z0-9]+/gi,"_")}.csv`,"﻿"+t)};
}

function notaModelo(k,ex){
  const e=EXP[ex];
  return `O esperado sem calor vem de um GAM com família ${modeloTxt(k,ex)}, ajustado só a este recorte, com uma cross-basis do pacote dlnm para ${e.nome.toLowerCase()} (${e.fun==="ns"?"spline natural com 1 grau de liberdade":"spline penalizado com 15 graus de liberdade"}) e defasagem de 0 a ${M.lag} dias (spline natural com 3 gl), mais um spline de tempo (${M.k_tempo} nós), um spline cíclico do dia do ano e um spline cíclico para o período COVID. Não há termo de dia da semana. O esperado de cada dia é o preditor do modelo com o calor zerado.`
}

/* ---------- diária ---------- */
function desenharDia(k){
  const ex=$("s-exp").value, key=keyF1();
  const y0=+$("s-ini").value, y1=Math.max(+$("s-fim").value,y0);
  const idx=[]; for(let j=0;j<dias.length;j++){ const a=+dias[j].slice(0,4); if(a>=y0&&a<=y1) idx.push(j) }
  const n=idx.length, fam=D.m[ex].f[k], disp=D.m[ex].d[k], O=D.o[k], E=D.m[ex].e[k];
  const ob=idx.map(j=>fl.inc[j]?null:O[j]), es=idx.map(j=>E[j]==null?null:E[j]/10);
  const sd=e=>Math.sqrt(fam==="nb"?e+e*e/disp:disp*e);
  const lo=es.map(e=>e==null?null:Math.max(e-1.96*sd(e),0)), up=es.map(e=>e==null?null:e+1.96*sd(e));
  const inc=idx.map(j=>!!fl.inc[j]), nc=idx.map(j=>!!fl.nc[j]), cov=idx.map(j=>!!fl.cov[j]), exp_=idx.map(j=>!!XW[j]);
  const acima=ob.map((v,i)=>v!=null&&es[i]!=null&&v>es[i]?v:null), abaixo=ob.map((v,i)=>v!=null&&es[i]!=null&&v<=es[i]?v:null);
  const tickc=css("--mut"), gridc=css("--grid"), ink=css("--ink"), cz=css("--cinza"), la=css("--laranja"), ac=COR_ACIMA(), ab=COR_ABAIXO(), card=css("--card");
  const B=barrasClima(idx, false);
  const vals=ob.concat(es).filter(v=>v!=null), ymin=vals.length?Math.max(0,Math.floor(Math.min(...vals)*0.9/10)*10):0;   // eixo sem valores negativos
  const r=n<=450?3.2:n<=1100?2.4:n<=2200?1.7:1.2, lw=n<=450?1.5:n<=1100?1.1:n<=2200?.8:.6, curto=n<=1100;
  const bordaC=c=>exp_[c.dataIndex]?ink:card, bordaW=c=>exp_[c.dataIndex]?(curto?1.8:1):(curto?.8:0);
  chS=new Chart($("s-chart"),{type:"line",data:{labels:idx.map(j=>dias[j]),datasets:[
    {label:"Observado",data:ob,borderColor:mkCor(cz,.75),borderWidth:.8,pointRadius:0,pointHoverRadius:0,order:4},
    {label:"Esperado",data:es,borderColor:ink,borderWidth:2,pointRadius:0,pointHoverRadius:0,order:3},
    {label:"Acima do esperado",data:acima,showLine:false,pointRadius:r,pointHoverRadius:r+2,pointBackgroundColor:ac,pointBorderColor:bordaC,pointBorderWidth:bordaW,order:1},
    {label:"Abaixo do esperado",data:abaixo,showLine:false,pointRadius:r,pointHoverRadius:r+2,pointBackgroundColor:ab,pointBorderColor:bordaC,pointBorderWidth:bordaW,order:1},
    {label:"_eixo_t",data:idx.map(()=>null),yAxisID:"yt",borderWidth:0,pointRadius:0}
  ]},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:"index",intersect:false},
    scales:{x:{grid:{display:false},ticks:{color:tickc,autoSkip:false,maxRotation:0,callback:function(v){const d=idx[v]==null?"":dias[idx[v]];
        if(!d) return ""; if(d.slice(5)==="01-01") return d.slice(0,4); return (n<=1100&&d.slice(8)==="01")?MESES[+d.slice(5,7)-1]:"" }}},
      y:{beginAtZero:false,min:ymin,grace:"6%",grid:{color:gridc},ticks:{color:tickc},title:{display:true,text:"Óbitos por dia",color:tickc}},
      yt:{display:!!B.bars,position:"right",min:0,max:B.tmax*1.7,grid:{display:false},ticks:{color:tickc,stepSize:10,callback:v=>v<=B.tmax?v:""},title:{display:!!B.bars,text:B.bars?BARRA_NOME[B.bv]+" (°C)":"",color:tickc}}},
    plugins:{legend:{display:false},covid:{cov,inc,nc},barras:B.bars?{vals:B.bars,nc:B.modoNC?B.ncs:null,lim:B.lim,cor0:mkCor(cz,.30),cor1:mkCor(la,.62),corL:la,linhas:B.linhas}:null,
      traco:{ob,es,acima:ac,abaixo:ab,lw,al:curto?.85:.6},
      tooltip:{filter:i=>["Observado","Esperado"].includes(i.dataset.label),
        callbacks:{title:it=>{const d=dias[idx[it[0].dataIndex]]; return `${SEMANA[new Date(d+"T12:00:00").getDay()]}, ${dBR(d)}`},
          label:c=>c.dataset.label==="Esperado"?`Esperado sem calor: ${fn(c.parsed.y,1)}`:`Observado: ${fn(c.parsed.y)}`,
          afterBody:it=>{const i=it[0].dataIndex, j=idx[i], v=ob[i], e=es[i], L=[];
            if(v!=null&&e!=null){ const dif=v-e; L.push(`${dif>=0?"Acima":"Abaixo"} do esperado em ${fn(Math.abs(dif),1)} (observado ÷ esperado = ${fr(v/e)})`); if(v>up[i]) L.push("Acima do limite superior de 95%"); else if(v<lo[i]) L.push("Abaixo do limite inferior de 95%") }
            else if(inc[i]) L.push("Sem registro de óbitos no SIM (fora do ajuste, sem esperado)");
            if(cov[i]) L.push("Período COVID (o modelo inclui um termo para o período; fora dos indicadores)");
            if(nc[i]) L.push("Registro não consolidado (dia no ajuste; o observado pode estar abaixo do real)");
            L.push(cl.ok[j]?`Horas com índice de calor ≥ 36 °C: ${cl.h36[j]==null?"–":fn(cl.h36[j])} · dia de calor (≥ 4 h): ${EV[j]?"sim":"não"} · exposto (calor em t a t−3): ${XW[j]?"sim":"não"}`:"Sem dados de clima neste dia: tratado como dia sem calor");
            const h=cd.hi_max[j], hm=cd.hi_med.o[j], tm=cd.t_med.o[j]; if(h!=null) L.push(`Índice de calor: máx. ${fn(h,1)} °C · médio ${hm==null?"–":fn(hm,1)} °C · temp. média ${tm==null?"–":fn(tm,1)} °C`);
            if(cd.nc[j]!=null) L.push(`Nível de calor do protocolo: NC${cd.nc[j]}`); return L}}}}},
    plugins:[covPlugin,barPlugin,pontoPlugin]});
  $("s-leg").innerHTML=`<span><i class="dt" style="background:${ac}"></i>Observado acima do esperado</span><span><i class="dt" style="background:${ab}"></i>Observado abaixo do esperado</span><span><i class="ln" style="background:${ink};height:3px"></i>Esperado sem calor</span><span><i class="ln" style="background:${cz}"></i>Linha do observado</span>`+
   `<span><i class="dt" style="background:transparent;border:2px solid ${ink};width:9px;height:9px"></i>Dia exposto (dia de calor em t a t−3)</span>`+
   legendaBarras(B,cz,la,mkCor)+`<span><i style="background:${cz}"></i>COVID (termo próprio no modelo)</span>`+(inc.some(Boolean)?`<span><i style="background:${cz};opacity:.3"></i>Sem registro no SIM (fora do ajuste)</span>`:"")+(nc.some(Boolean)?`<span><i style="background:repeating-linear-gradient(135deg,${cz} 0 1.3px,transparent 1.3px 4px)"></i>Registro não consolidado (no ajuste)</span>`:"");
  // indicadores: dias com esperado, com clima e fora de COVID; dias de mês não consolidado entram
  const ok=ob.map((v,i)=>v!=null&&es[i]!=null&&!!cl.ok[idx[i]]&&!cov[i]);
  const grp=f=>{let Oo=0,Ee=0,nn=0,ac_=0,sup=0;ob.forEach((v,i)=>{if(ok[i]&&f(i)){Oo+=v;Ee+=es[i];nn++;if(v>es[i])ac_++;if(v>up[i])sup++}});return {n:nn,O:Oo,E:Ee,raz:Ee?Oo/Ee:NaN,ac:nn?100*ac_/nn:NaN,sup:nn?100*sup/nn:NaN}};
  const T=grp(()=>true), H=grp(i=>exp_[i]), N=grp(i=>!exp_[i]);
  $("s-kpis").innerHTML=kpiHtml([
    [fn(ob.reduce((x,v)=>x+(v||0),0)),"óbitos nos dias mostrados"+(nc.some(Boolean)?` (inclui ${fn(nc.filter(Boolean).length)} dia(s) de mês com registro não consolidado)`:"")],
    ...rrDoModelo(k,ex),
    [isFinite(H.raz)?fr(H.raz):"–","observado ÷ esperado sem calor nos "+fn(H.n)+" dias expostos (dia de calor em t a t−3) do período mostrado"],
    [isFinite(N.raz)?fr(N.raz):"–","observado ÷ esperado sem calor nos "+fn(N.n)+" demais dias"],
    [isFinite(T.ac)?fn(T.ac)+"%":"–","dos "+fn(T.n)+" dias ficaram acima do esperado; "+(isFinite(T.sup)?fn(T.sup,1)+"% acima do limite de 95% (≈ 2,5% se calibrado)":"")]
  ]);
  $("i-serie").innerHTML=`<span class="t">Interpretação</span>`+(H.n&&N.n?`Cada ponto é um dia: <b style="color:${ac}">vermelho</b> quando o número de óbitos ficou acima do esperado e <b style="color:${ab}">azul</b> quando ficou abaixo; o traço vertical liga o ponto ao esperado do dia. O <b>esperado é o que o modelo prevê sem calor</b>: tendência de longo prazo, sazonalidade anual e período COVID, com o efeito do calor (dia e 10 dias anteriores) estimado e depois retirado. Nos dias expostos (contorno escuro), o observado fica acima do esperado na medida do efeito estimado para este recorte: <b>${fn(H.O)}</b> óbitos contra <b>${fn(H.E,0)}</b> esperados no período mostrado (observado ÷ esperado = <b>${fr(H.raz)}</b>, ou ${fp(pct(H.raz))}); nos outros <b>${fn(N.n)}</b> dias, <b>${fn(N.O)}</b> contra <b>${fn(N.E,0)}</b> (<b>${fr(N.raz)}</b>). Como o modelo usa defasagem de até 10 dias e o contorno marca só 4, parte do efeito aparece também nos dias não expostos, e a razão deles pode ficar um pouco acima de 1. Um dia isolado varia por acaso; só a diferença sistemática entre grupos de dias tem leitura. A exposição inclui o dia e os três anteriores, então um dia de calor aparece ligado a até quatro pontos com contorno escuro.`:`Poucos dias expostos no período mostrado para comparar.`);
  $("s-note").textContent="Escala diária desde 2006 (o clima existe desde abril de 2007; antes disso o calor é tratado como ausente). O eixo vertical não começa em zero, para que as diferenças apareçam. "+notaModelo(k,ex)+" Faixa de 95% de um dia = esperado ± 1,96 × raiz da variância do modelo (aparece ao passar o mouse; não inclui a incerteza dos coeficientes). Os indicadores excluem COVID (barra cinza na base) e dias sem nenhum óbito registrado no SIM (faixa cinza clara), onde o esperado não é traçado. Dias de meses com registro não consolidado (hachurados) entram no modelo e nos indicadores."+NOTA_BARRAS(B)+
    (n>2200?" Período longo: escolha menos anos em De e Até para ver os pontos com mais nitidez.":"");
  $("s-csv").onclick=()=>{let t="dia;observado;esperado_sem_calor;lim_inf;lim_sup;horas_ic36;dia_de_calor;exposto_t_a_t3;indice_calor_max;indice_calor_medio;temp_media;nivel_calor;registro_sim\n";const c1=v=>v==null?"":v.toFixed(1).replace(".",",");
    idx.forEach((j,i)=>{t+=[dias[j],ob[i]??"",c1(es[i]),c1(lo[i]),c1(up[i]),cl.h36[j]??"",EV[j],XW[j],cd.hi_max[j]??"",cd.hi_med.o[j]??"",cd.t_med.o[j]??"",cd.nc[j]??"",inc[i]?"sem_registro":nc[i]?"nao_consolidado":""].join(";")+"\n"});
    baixar(`serie_diaria_${ex}_${key.replace(/[^a-z0-9]+/gi,"_")}.csv`,"﻿"+t)};
}

if(SH){ registrarShiny();
  const go=()=>{ racaSync(); window.__desenhar() };
  (window.Shiny.shinyapp && window.Shiny.shinyapp.isConnected && window.Shiny.shinyapp.isConnected()) ? go() : window.jQuery(document).one("shiny:connected",go) }
else { racaSync(); window.__desenhar() }
}
})();

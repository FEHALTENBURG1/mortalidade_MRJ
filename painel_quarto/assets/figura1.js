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
  document.querySelectorAll("[id^=tab-]").forEach(e=>e.classList.toggle("hide",e.id!=="tab-"+b.dataset.tab));
  const f=window.__abas && window.__abas[b.dataset.tab]; if(f) f();
});

lerDados().then(iniciar).catch(e=>{ $("s-note").textContent = e.message });

function iniciar(D){
const M = D.meta, sem = D.sem, dias = D.dias, cl = D.cl, fl = D.fl;
const nSem = sem.ini.length;
/* Modo Shiny (M.sob_demanda): a página traz só o calendário e o clima; cada recorte e medida de calor chega do servidor quando é escolhido e
   fica guardado aqui (D.k, D.o, D.m, D.So, D.S têm o mesmo formato do JSON completo do Quarto, preenchido aos poucos). */
const SH = !!(M.sob_demanda && window.Shiny);
let POP = M.pop, CHAVE = M.dados && M.dados.chave, nPedidos = 0;
const PEND = new Set(), idPedido = (pop,key,ex,causa,cod) => [pop,causa,cod,ex,key].join("|");
/* Causa do óbito e retiradas do ajuste (só no app): a causa e três caixas (COVID, meses não consolidados, dias sem clima) formam o código "000" a "111". */
const CAUSA_POR = {naturais:"por causas naturais", todas_sem_covid:"por todas as causas, exceto COVID-19", todas:"por todas as causas, com COVID-19", externas:"por causas externas"};
const CAUSA_ROT = {todas_sem_covid:"todas as causas, exceto COVID-19", todas:"todas as causas, com COVID-19", externas:"causas externas"};
/* Cada aba tem o seu próprio conjunto de filtros; o prefixo dos ids (s = Figura 1, x = exposição-resposta, ...) diz de qual aba se lê o estado. */
const modo = (p="s") => (SH && $(p+"-causa")) ? {covid:$(p+"-r-covid").checked, nc:$(p+"-r-nc").checked, clima:$(p+"-r-clima").checked, causa:$(p+"-causa").value} : {covid:false,nc:false,clima:false,causa:"naturais"};
const codOpc = (p="s") => { const m=modo(p); return (m.covid?"1":"0")+(m.nc?"1":"0")+(m.clima?"1":"0") };
const OUV = {seg:[], erro:[], base:[]};                                          // ouvintes das outras abas: recorte recebido, erro do servidor, população trocada
const ELEGC = new Map();
const eleg = (c=modo().causa, o=codOpc()) => { const id=c+"|"+o; if(!ELEGC.has(id)) ELEGC.set(id,new Set((((M.elegiveis||{})[c])||{})[o]||[])); return ELEGC.get(id) };
const ix = new Map();
const zerar = () => { D.k=[]; D.o=[]; D.m={}; D.S={}; D.So={}; D.cv={}; D.cb={}; D.mp={}; D.cd={}; D.dg={}; D.aj={}; ELEGC.clear(); Object.keys(M.exposicoes).forEach(e=>{ D.m[e]={f:[],d:[],rr:[],e:[]}; D.S[e]={} }); ix.clear() };
if(SH) zerar(); else D.k.forEach((k,i)=>ix.set(k,i));
const cd = {hi_max:cl.hi_max, hi_med:{o:cl.hi_med}, t_med:{o:cl.t_med}, nc:cl.nc};
const diaIx = new Map(dias.map((d,i)=>[d,i]));
const anos = [...new Set(sem.ano)].sort();
// dia de calor = pelo menos 4 h com índice de calor >= 36 °C (NC2 ou mais); exposto = dia de calor em t, t-1, t-2 ou t-3
const EV = cl.h36.map(v=>v!=null&&v>=4?1:0);
const XW = EV.map((_,i)=>{ for(let k=0;k<4;k++) if(i-k>=0&&EV[i-k]) return 1; return 0 });
const EXP = M.exposicoes;
const KEXP = Object.keys(EXP);
const REF_TXT = {horas:(v,u)=>`${fn(v)} ${u} por dia com índice de calor ≥ 36 °C`, haat:(v,u)=>`${fn(v)} ${u} por dia acima de 36 °C`};
const COR_ACIMA=()=>css("--acima"), COR_ABAIXO=()=>css("--abaixo");

const subtitulo = () => { $("sub").textContent = `Óbitos ${CAUSA_POR[modo().causa]} (SIM/DATASUS), de ${dBR(M.inicio)} a ${dBR(M.fim)}: observados e esperados sem calor, por local do óbito, faixa etária e raça/cor. Estudo ecológico de séries temporais, descritivo e exploratório. O número esperado é estimado por um modelo ajustado a cada recorte: modelo aditivo generalizado (GAM) com defasagens distribuídas (DLNM), adaptado do modelo de referência de Morais et al. (ver Métodos e fontes).` };
subtitulo();
if(SH && $("s-r-covid-t") && M.covid) $("s-r-covid-t").textContent=`Período da COVID-19 (${dBR(M.covid[0])} a ${dBR(M.covid[1])})`;

fillSel($("s-local"), M.locais.map(l=>({v:l,t:nm(l)})), "Todos os locais");
fillSel($("s-faixa"), M.faixas, "Todas as idades");
fillSel($("s-raca"), [{v:"Todas",t:"Todas"},{v:"Branca",t:"Branca (referência)"},{v:"Preta",t:"Preta"},{v:"Parda",t:"Parda"},{v:"PPI",t:"Preta, parda e indígena (PPI)"}], "Todas");
fillSel($("s-exp"), KEXP.map(k=>({v:k,t:EXP[k].nome})), KEXP[0]);
fillSel($("s-ini"), anos, anos[0]); fillSel($("s-fim"), anos, anos[anos.length-1]);

const keyF1 = () => $("s-local").value+"|"+$("s-faixa").value+($("s-raca").value!=="Todas"?"|"+$("s-raca").value:"");
const keyD = () => SH ? modo().causa+"~"+codOpc()+"~"+keyF1() : keyF1();                // chave dos dados guardados no navegador
const codPadrao = () => (M.cod_padrao||"000");
const sufixoArq = () => SH ? "_"+modo().causa+(codOpc()!==codPadrao()?"_retirada"+codOpc():"") : "";
function racaSync(){ const r=$("s-raca").value!=="Todas"; if(r) $("s-faixa").value="Todas as idades"; $("s-faixa").disabled=r;
  $("s-faixa").title=r?"As séries por raça/cor são calculadas para todas as idades. Para selecionar uma faixa etária, defina Raça/cor como Todas.":"" }
function racaNota(){ const rc=(SH&&D.rcs)?D.rcs[modo().causa]:D.rc; if(!rc){ $("s-raca-nota").textContent=""; return }
  const tot=Object.values(rc).reduce((a,b)=>a+b,0), pc=v=>fn(100*(v||0)/tot,1)+"%", n=k=>rc[k]||0;
  $("s-raca-nota").textContent=`Distribuição da raça/cor (campo RACACOR do SIM) nos ${fn(tot)} ${modo().causa==="naturais"?"óbitos por causas naturais da série":"óbitos da série ("+CAUSA_ROT[modo().causa]+")"}: branca ${pc(n("Branca"))}, parda ${pc(n("Parda"))}, preta ${pc(n("Preta"))}, amarela ${pc(n("Amarela"))}, indígena ${pc(n("Indígena"))} e raça/cor ignorada ou não informada ${pc(n("Ignorada"))}. As categorias indígena (${fn(n("Indígena"))} óbitos) e amarela (${fn(n("Amarela"))}) não têm óbitos suficientes para série própria. Os óbitos indígenas compõem o agregado PPI (preta, parda e indígena), e os de raça/cor amarela, ignorada ou não informada entram apenas em Todas. As séries por raça/cor são calculadas para todas as idades.` }

["s-local","s-faixa","s-exp","s-crit","s-ini","s-fim","s-bar","s-lim","s-cor"].forEach(i=>$(i).onchange=desenhar);
["s-causa","s-r-covid","s-r-nc","s-r-clima"].forEach(i=>{ const e=$(i); if(e) e.onchange=desenhar });
$("s-raca").onchange=()=>{ racaSync(); desenhar() };
$("s-esc").onchange=()=>{ if($("s-esc").value==="dia"){ const f=+$("s-fim").value, i=+$("s-ini").value;      // escala diária: começa com os 3 últimos anos
    if(f-i+1>3){ const novo=Math.max(f-2,anos[0]); if([...$("s-ini").options].some(o=>+o.value===novo)) $("s-ini").value=novo } }
  desenhar() };
$("s-lim").oninput=desenhar;

/* ---------- plugins do gráfico ---------- */
const hachura=ctx=>{const c=document.createElement("canvas");c.width=c.height=8;const g=c.getContext("2d");g.strokeStyle=css("--cinza");g.lineWidth=1.3;g.beginPath();g.moveTo(-1,9);g.lineTo(9,-1);g.stroke();return ctx.createPattern(c,"repeat")};
const hachuraV=ctx=>{const c=document.createElement("canvas");c.width=c.height=8;const g=c.getContext("2d");g.strokeStyle=css("--azul");g.globalAlpha=.55;g.lineWidth=1;g.beginPath();g.moveTo(2,0);g.lineTo(2,8);g.stroke();return ctx.createPattern(c,"repeat")};
const covPlugin={id:"covid",beforeDatasetsDraw(c,_a,o){const {ctx,chartArea:a,scales:{x}}=c;if(!o)return;ctx.save();
  const w=x.getPixelForValue(1)-x.getPixelForValue(0);
  const runs=(arr,f)=>{let i=0;while(i<arr.length){if(arr[i]){let j=i;while(j+1<arr.length&&arr[j+1])j++;f(x.getPixelForValue(i)-w/2,x.getPixelForValue(j)+w/2);i=j+1}else i++}};
  if(o.inc){ctx.fillStyle=css("--cinza");ctx.globalAlpha=.16;runs(o.inc,(l,r)=>ctx.fillRect(l,a.top,r-l,a.bottom-a.top))}
  if(o.sc){ctx.fillStyle=hachuraV(ctx);ctx.globalAlpha=.55;runs(o.sc,(l,r)=>ctx.fillRect(l,a.top,r-l,a.bottom-a.top))}
  if(o.nc){ctx.fillStyle=hachura(ctx);ctx.globalAlpha=.6;runs(o.nc,(l,r)=>ctx.fillRect(l,a.top,r-l,a.bottom-a.top))}
  if(o.cov){ctx.fillStyle=css("--cinza");ctx.globalAlpha=.55;runs(o.cov,(l,r)=>ctx.fillRect(l,a.bottom-5,r-l,5))}
  ctx.restore()}};
const BARRA_NOME={t_med:"Temperatura média do dia",hi_max:"Índice de calor máximo do dia",hi_med:"Índice de calor médio do dia"};
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
  const quad = ex==="horas" ? " Na reta imposta pelo modelo (1 grau de liberdade), este RR é o de 4 h elevado ao quadrado, e não uma estimativa independente." : "";
  return [0,3].map((i,j)=>[t(i), `RR acumulado nas defasagens de 0 a ${M.lag} dias, para exposição de ${REF_TXT[ex](e.ref[j],e.unidade)} em todos os ${M.lag+1} dias.`+(j===1?quad:"")]) }
const modeloTxt = (k, ex) => { const f=D.m[ex].f[k], d=D.m[ex].d[k];
  return f==="nb"?`binomial negativa (θ = ${fn(d,1)})`:`quase-Poisson (dispersão φ = ${fn(d,2)}; a binomial negativa não convergiu)` };

let chS=null;
function desenhar(){
  if($("tab-serie").classList.contains("hide")) return;
  const dia=$("s-esc").value==="dia";
  $("s-critw").classList.toggle("hide",dia);
  subtitulo();
  $("s-h2").textContent=(dia?`Óbitos diários ${CAUSA_POR[modo().causa]}: cada dia em relação ao esperado sem calor`:`Óbitos semanais ${CAUSA_POR[modo().causa]}: observados, esperados sem calor e semanas de calor`)+($("s-raca").value!=="Todas"?` (raça/cor: ${({PPI:"preta, parda e indígena"})[$("s-raca").value]||$("s-raca").value.toLowerCase()})`:"");
  racaNota();
  const key=keyF1(), ex=$("s-exp").value, kd=keyD();
  if(SH && eleg().has(key) && !carregado(kd,ex)){ pedir(key,ex); return }      // mantém a figura anterior, esmaecida, até o servidor responder
  quadros(false);
  if(chS){chS.destroy();chS=null}
  const k=ix.get(kd);
  const aj=(D.aj||{})[kd]; if(aj) $("s-h2").textContent+=` (ajuste estimado de ${dBR(aj.ini)} a ${dBR(aj.fim)})`;
  if(k==null){ $("s-kpis").innerHTML=""; $("s-leg").innerHTML=""; $("i-serie").innerHTML=""; $("s-note").textContent=`Menos de ${M.min_obitos} óbitos ${SH?"no ajuste ":""}neste recorte: série não estimada.`; $("s-sensw").classList.add("hide"); return }
  dia?desenharDia(k):desenharSemana(k);
  atualizarSens()
}
window.__desenhar=desenhar; window.__abas={serie:desenhar};

/* ---------- modo Shiny: pedir recortes ao servidor ---------- */
const quadros = on => { $("s-kpis").classList.toggle("calc",on); $("s-chart").parentNode.classList.toggle("calc",on) };
const carregado = (kd,ex) => ix.has(kd) && D.m[ex] && D.m[ex].f[ix.get(kd)]!==undefined && D.S[ex][kd]!==undefined;
function enviar(key,ex,causa,cod){
  const id=idPedido(POP,key,ex,causa,cod); if(PEND.has(id)) return; PEND.add(id);
  window.Shiny.setInputValue("pedido",{key,ex,pop:POP,chave:CHAVE,causa,opc:cod,n:++nPedidos},{priority:"event"});
}
function pedir(key,ex){
  quadros(true);
  $("s-note").textContent="Calculando o modelo deste recorte (3 a 15 segundos na primeira solicitação; o resultado é armazenado no servidor)…";
  enviar(key,ex,modo().causa,codOpc());
}
function mesclar(key,ex,p){
  let k=ix.get(key); if(k==null){ k=D.k.length; D.k.push(key); ix.set(key,k) }
  D.o[k]=p.o; const m=D.m[ex]; m.f[k]=p.f; m.d[k]=p.d; m.rr[k]=p.rr; m.e[k]=p.e;
  D.So[key]=p.So; D.S[ex][key]=p.S;
  if(p.cv){ (D.cv[ex]||(D.cv[ex]={}))[key]=p.cv }
  if(p.aj){ D.aj[key]=p.aj }
  if(p.cb){ (D.cb[ex]||(D.cb[ex]={}))[key]=p.cb }                               // colunas e graus de liberdade efetivos da base cruzada
}
function registrarShiny(){
  const S=window.Shiny;
  S.addCustomMessageHandler("segmento", msg=>{
    PEND.delete(idPedido(msg.pop,msg.key,msg.ex,msg.causa,msg.opc));
    if(msg.pop!==POP || msg.chave!==CHAVE) return;                                // resposta de outra população ou de uma versão antiga dos dados
    const kd=msg.causa+"~"+msg.opc+"~"+msg.key;
    if(/^mapa\d+$/.test(msg.ex)){ const q=JSON.parse(msg.json); (D.mp[kd]||(D.mp[kd]={}))[q.limiar]=q; OUV.seg.forEach(f=>f(kd,msg.ex)); return }     // coluna do mapa de horas por limiar (Figura 4)
    if(/^(diag|sens|flex)_/.test(msg.ex)){ (D.dg[kd]||(D.dg[kd]={}))[msg.ex]=JSON.parse(msg.json); OUV.seg.forEach(f=>f(kd,msg.ex)); return }     // aba de diagnósticos (ajuste principal com diagnósticos e análises de sensibilidade) e aba de exposição-resposta (reta imposta contra curva flexível)
    if(/^cid/.test(msg.ex)){ (D.cd[kd]||(D.cd[kd]={}))[msg.ex]=JSON.parse(msg.json); OUV.seg.forEach(f=>f(kd,msg.ex)); return }     // aba de causas específicas: lista de causas, RR e série semanal de cada causa
    mesclar(kd,msg.ex,JSON.parse(msg.json));
    if(kd===keyD() && msg.ex===$("s-exp").value) desenhar();
    else if(msg.ex===$("s-exp").value && msg.key===keyF1() && msg.causa===modo().causa) atualizarSens();     // chegou o modelo da outra linha da tabela de sensibilidade
    OUV.seg.forEach(f=>f(kd,msg.ex));
  });
  S.addCustomMessageHandler("base", msg=>{                                         // troca de população
    const b=JSON.parse(msg.json);
    if(b.meta.n_dias!==dias.length){ location.reload(); return }                   // calendário diferente: recarrega a página
    Object.assign(M,b.meta); D.rc=b.rc; D.rcs=b.rcs; POP=M.pop; CHAVE=M.dados.chave; PEND.clear(); zerar(); desenhar(); OUV.base.forEach(f=>f());
  });
  S.addCustomMessageHandler("erro_segmento", msg=>{
    PEND.delete(idPedido(msg.pop,msg.key,msg.ex,msg.causa,msg.opc));
    OUV.erro.forEach(f=>f(msg));
    if(msg.pop!==POP || msg.key!==keyF1() || msg.ex!==$("s-exp").value || msg.causa!==modo().causa || msg.opc!==codOpc()) return;     // erro de um pedido que o usuário já deixou para trás
    quadros(false);
    $("s-note").innerHTML = msg.codigo==="dados_mudaram"
      ? 'Os dados foram atualizados no servidor. <a href="">Recarregue a página</a> para acessar a versão mais recente.'
      : "Não foi possível ajustar o modelo deste recorte: "+String(msg.mensagem||"erro não identificado").replace(/[<>&]/g,"");
  });
  const sel=$("s-pop");
  if(sel){ sel.value=POP;
    sel.onchange=()=>{ POP=sel.value; CHAVE=null; M.elegiveis={}; PEND.clear(); zerar(); quadros(true);
      $("s-note").textContent="Carregando a população selecionada…"; S.setInputValue("pop",POP,{priority:"event"}) } }
}

/* ---------- ajuste principal x sensibilidade com meses não consolidados (tabela fixa abaixo dos indicadores) ---------- */
const sensCod = nc => { const m=modo(); return (m.covid?"1":"0")+(nc?"1":"0")+(m.clima?"1":"0") };
function atualizarSens(){
  const box=$("s-sensw"); if(!box) return;
  if(!SH || $("tab-serie").classList.contains("hide")){ box.classList.add("hide"); return }
  const ex=$("s-exp").value, key=keyF1(), causa=modo().causa, e=EXP[ex];
  const cabec=`<thead><tr><th>Análise</th><th>Período estimado</th><th class="n">Dias no ajuste</th><th class="n">Óbitos no ajuste</th><th class="n">RR com ${fn(e.ref[0])} ${e.unidade} por dia (IC 95%)</th><th class="n">RR com ${fn(e.ref[1])} ${e.unidade} por dia (IC 95%)</th></tr></thead>`;
  const linhas=[[true,"Principal: meses não consolidados retirados"],[false,"Sensibilidade: meses não consolidados mantidos"]].map(([nc,rot])=>{
    const cod=sensCod(nc), kd=causa+"~"+cod+"~"+key;
    if(!eleg(causa,cod).has(key)) return `<tr><td>${rot}</td><td colspan="5">menos de ${M.min_obitos} óbitos no ajuste: modelo não estimado</td></tr>`;
    if(!carregado(kd,ex)){ enviar(key,ex,causa,cod); return `<tr><td>${rot}</td><td colspan="5">calculando o modelo…</td></tr>` }
    const k=ix.get(kd), a=D.aj[kd], r=D.m[ex].rr[k], t=i=>`${fr(r[i])} (${fr(r[i+1])} a ${fr(r[i+2])})`;
    return `<tr><td>${rot}</td><td>${a?dBR(a.ini)+" a "+dBR(a.fim):"–"}</td><td class="n">${a?fn(a.nd):"–"}</td><td class="n">${a?fn(a.no):"–"}</td><td class="n">${t(0)}</td><td class="n">${t(3)}</td></tr>` });
  $("s-sens").innerHTML=cabec+"<tbody>"+linhas.join("")+"</tbody>";
  const meses=(M.meses_nc||[]).map(m=>m.slice(5)+"/"+m.slice(0,4)).join(", ")||"nenhum";
  $("s-sens-n").textContent=`RR acumulado em 0 a ${M.lag} dias para a exposição indicada mantida em todos os ${M.lag+1} dias, em relação à ausência dessa exposição. As duas linhas usam o mesmo recorte, a mesma causa do óbito e as mesmas demais retiradas do ajuste; só muda a inclusão dos meses de registro não consolidado (${meses}). O critério de completude não depende do resultado do modelo: taxa diária abaixo de 80% da mediana dos 12 meses de referência, mês com dia sem nenhum óbito registrado ou último mês do arquivo incompleto.`;
  box.classList.remove("hide");
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
const NOTA_BARRAS = B => B.bars?` Colunas ao fundo: ${BARRA_NOME[B.bv].toLowerCase()}, no eixo da direita (°C). `+
  (B.modoNC?"A cor das colunas indica o nível de calor (NC) do protocolo de calor da Prefeitura do Rio de Janeiro (Decreto Rio nº 54.740/2024), reconstruído a partir do número de horas por dia com índice de calor igual ou superior a 36, 40 e 44 °C (o decreto usa a expressão “acima de”; aqui o corte inclui o próprio limiar). NC2: pelo menos 4 h com índice de calor igual ou superior a 36 °C em 1 ou 2 dias seguidos. NC3: o mesmo critério por 3 dias seguidos ou mais. NC4: pelo menos 4 h com índice igual ou superior a 40 °C dentro de uma sequência de NC3. NC5: pelo menos 2 h com índice igual ou superior a 44 °C dentro de uma sequência de NC3. A reconstrução usa apenas valores observados (o decreto admite também a previsão) e não substitui o nível divulgado pelo Centro de Operações Rio (COR-Rio). Como o nível depende das horas nos limiares, a cor pode não acompanhar a altura da coluna quando esta representa o índice de calor médio ou a temperatura média."
   :`Em laranja, os dias acima de ${fn(B.lim,1)} °C: ${fn(B.bAcima)} de ${fn(B.bDias)} dias no período mostrado (${fn(100*B.bAcima/Math.max(B.bDias,1),1)}%).`):"";
const kpiHtml = lista => lista.map(([v,l])=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
/* Textos que dependem do que foi retirado do ajuste (sem as caixas marcadas, saem idênticos aos da página do Quarto). */
const rotCov = (m=modo()) => m.covid ? "Período da COVID-19 (fora do ajuste)" : "Período da COVID-19 (termo próprio no modelo)";
const rotNC = (m=modo()) => m.nc ? "Registro não consolidado (fora do ajuste)" : "Registro não consolidado (no ajuste)";
const linhaCov = (m=modo()) => m.covid ? "Período da COVID-19 (retirado do ajuste; sem esperado e fora dos indicadores)" : "Período da COVID-19 (o modelo inclui um termo para o período; fora dos indicadores)";
const linhaNC = (u,m=modo()) => m.nc ? `Registro não consolidado (${u} retirado do ajuste; sem esperado)` : `Registro não consolidado (${u} no ajuste; o observado pode estar abaixo do real)`;
const compExp = (m=modo()) => m.covid ? "tendência de longo prazo e sazonalidade anual" : "tendência de longo prazo, sazonalidade anual e período da COVID-19";
const notaClima = (m=modo()) => m.clima ? " Os dias sem dados de clima e os 10 dias seguintes foram retirados do ajuste, e o esperado não é traçado nesses dias (nesses dias a exposição ao calor não foi observada; não são dias sem calor)." : " Atenção: os dias sem dados de clima foram mantidos no ajuste como dias sem calor, que era a especificação anterior do painel e só deve ser usada como sensibilidade.";
const ORDEM_MOTIVOS = ["sem_registro","clima","nc","covid"];
const notaAjuste = kd => { const a=(D.aj||{})[kd]; if(!a) return "";
  const rot=ORDEM_MOTIVOS.map((m,i)=>a.xd[i]>0?`${fn(a.xd[i])} dia(s) ${(M.motivos_fora||{})[m]||m} (${fn(a.xo[i])} óbitos)`:null).filter(Boolean);
  return ` Amostra do ajuste: ${fn(a.nd)} dias e ${fn(a.no)} óbitos, de ${dBR(a.ini)} a ${dBR(a.fim)}.`+(rot.length?` Fora do ajuste: ${rot.join("; ")}.`:" Nenhum dia fora do ajuste.") };
const notaCausa = (m=modo()) => { const c=m.causa; return c==="naturais" ? "" : " Causa do óbito: "+(c==="externas" ? "causas externas, sem COVID-19 (óbitos fora dos códigos A00 a R99 da CID-10)" : c==="todas" ? "todas as causas, com COVID-19" : "todas as causas, exceto COVID-19")+"." };
const baixar = (nome, conteudo) => { const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([conteudo],{type:"text/csv"}));a.download=nome;a.click() };

/* ---------- semanal ---------- */
function desenharSemana(k){
  const ex=$("s-exp").value, crit=$("s-crit").value, key=keyF1(), kd=keyD();
  const S=D.S[ex][kd], O=D.So[kd];
  const y0=+$("s-ini").value, y1=Math.max(+$("s-fim").value,y0);
  const idx=[...Array(nSem).keys()].filter(i=>sem.ano[i]>=y0&&sem.ano[i]<=y1);
  const pick=arr=>idx.map(i=>arr[i]);
  const labels=idx.map(i=>`SE ${sem.se[i]}/${sem.ano[i]}`);
  const es=pick(S.e), lo=pick(S.l), up=pick(S.u);
  const nb=pick(sem.nb), nn=pick(sem.nn), cov=pick(sem.cov), inc=pick(sem.inc), nc=pick(sem.nc), sc=pick(sem.sc||sem.nb.map(()=>false));
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
    plugins:{legend:{display:false},covid:{cov,inc,nc,sc},barras:B.bars?{vals:B.bars,nc:B.modoNC?B.ncs:null,lim:B.lim,cor0:mkCor(cz,.30),cor1:mkCor(la,.62),corL:la,linhas:B.linhas}:null,
      tooltip:{filter:i=>["Observado","Esperado sem calor","Faixa esperada (95%)"].includes(i.dataset.label),
        callbacks:{label:c=>c.dataset.label==="Faixa esperada (95%)"?`Faixa de 95%: ${lo[c.dataIndex]==null?"–":fn(lo[c.dataIndex])+" a "+fn(up[c.dataIndex])}`:`${c.dataset.label}: ${fn(c.parsed.y,c.dataset.label==="Observado"?0:1)}`,
          afterBody:it=>{const i=idx[it[0].dataIndex], q=it[0].dataIndex, L=[`Início da semana: ${dBR(sem.ini[i])}`,`Índice de calor máximo: ${sem.mxh[i]==null?"–":fn(sem.mxh[i],1)} °C · dias com máximo ≥ 36 °C: ${sem.nb[i]} · dias em NC2 a NC5: ${sem.nn[i]}`,`Temperatura média: ${sem.mt[i]==null?"–":fn(sem.mt[i],1)} °C`];
            if(ob[q]!=null&&es[q]!=null) L.push(`Observado ÷ esperado sem calor: ${fr(ob[q]/es[q])}`);
            if(B.bars){const v=B.bars[q].filter(z=>z!=null);if(v.length){ let t=`${BARRA_NOME[B.bv]}: ${fn(Math.min(...v),1)} a ${fn(Math.max(...v),1)} °C na semana; `;
              if(B.modoNC&&B.ncs){const c={};B.ncs[q].forEach(n=>{if(n!=null&&n>1)c[n]=(c[n]||0)+1});const l=Object.keys(c).map(n=>`${c[n]} dia(s) em NC${n}`);t+=l.length?l.join(", "):"nenhum dia acima de NC1"}
              else t+=`${v.filter(z=>z>B.lim).length} dia(s) acima de ${fn(B.lim,1)} °C`; L.push(t)}}
            if(!sem.cl[i]) L.push("Sem dados de clima nesta semana (exposição não observada)");
            if(cov[q]) L.push(linhaCov());
            if(inc[q]) L.push("Sem registro de óbitos no SIM (fora do ajuste)");
            if(nc[q]) L.push(linhaNC("semana"));
            return L}}}}},
    plugins:[covPlugin,barPlugin]});
  $("s-leg").innerHTML=`<span><i class="ln" style="background:${cz}"></i>Observado</span><span><i class="ln" style="background:${az};height:3px"></i>Esperado sem calor</span><span><i style="background:${mkCor(az,.17)}"></i>Faixa de 95%</span><span><i class="dt" style="background:${ink}"></i>Observado acima da faixa</span>`+
   (crit==="ic"?`<span><i style="background:${mkCor(la,.40)}"></i>≥ 3 dias com índice de calor máximo ≥ 36 °C</span><span><i style="background:${mkCor(la,.16)}"></i>1 a 2 dias</span>`:"")+(crit==="nc"?`<span><i style="background:${mkCor(la,.40)}"></i>Semana com dia em NC2 a NC5</span>`:"")+
   legendaBarras(B,cz,la,mkCor)+`<span><i style="background:${cz}"></i>${rotCov()}</span>`+(inc.some(Boolean)?`<span><i style="background:${cz};opacity:.3"></i>Sem registro no SIM (fora do ajuste)</span>`:"")+(nc.some(Boolean)?`<span><i style="background:repeating-linear-gradient(135deg,${cz} 0 1.3px,transparent 1.3px 4px)"></i>${rotNC()}</span>`:"")+(sc.some(Boolean)?`<span><i style="background:repeating-linear-gradient(90deg,${az} 0 1px,transparent 1px 4px);opacity:.7"></i>Sem dado de clima (exposição não observada)</span>`:"");
  // indicadores: sem COVID, sem semanas sem registro e sem semanas sem clima (semanas de registro não consolidado entram)
  const ok=idx.map((_,q)=>!(cov[q]||inc[q]||!sem.cl[idx[q]]||es[q]==null));
  const grp=f=>{let Oo=0,E=0,n=0,ab=0;ob.forEach((v,q)=>{if(ok[q]&&f(q)){Oo+=v;E+=es[q];n++;ab+=v>up[q]?1:0}});return {n,O:Oo,E,raz:E?Oo/E:NaN,ac:n?100*ab/n:NaN}};
  const H=grp(q=>calor[q]), N=grp(q=>!calor[q]);
  const tot=ob.reduce((x,y)=>x+(y||0),0);
  $("s-kpis").innerHTML=kpiHtml([
    [fn(tot),"óbitos na série selecionada"+(nc.some(Boolean)?` (inclui ${fn(nc.filter(Boolean).length)} semana(s) com registro não consolidado${modo().nc?", fora do ajuste":""})`:"")],
    ...rrDoModelo(k,ex),
    [isFinite(H.raz)?fr(H.raz):"–","observado ÷ esperado sem calor nas "+H.n+" semanas de calor (soma dos óbitos observados ÷ soma dos esperados sem calor)"],
    [isFinite(N.raz)?fr(N.raz):"–","observado ÷ esperado sem calor nas "+N.n+" demais semanas"],
    [isFinite(H.ac)?fn(H.ac)+"%":"–","das semanas de calor com óbitos acima do limite superior da faixa de 95%"],
    [isFinite(N.ac)?fn(N.ac)+"%":"–","das demais semanas acima do limite superior (≈ 2,5% se o modelo estiver bem calibrado)"]
  ].concat(B.ncs&&B.bars?[[fn(B.nNC[2]+B.nNC[3]+B.nNC[4]+B.nNC[5]),`dias em nível de calor 2 a 5 do protocolo (NC4: ${fn(B.nNC[4])}; NC5: ${fn(B.nNC[5])})`]]:[]));
  const critTxt=crit==="ic"?"semanas com pelo menos 3 dias de índice de calor máximo ≥ 36 °C":"semanas com ao menos um dia em NC2 a NC5";
  $("i-serie").innerHTML=`<span class="t">Interpretação</span>`+(crit==="no"?`A linha azul indica o número de óbitos esperado sem calor segundo o modelo deste recorte (${compExp()}, com o efeito do calor retirado), e a faixa sombreada corresponde ao intervalo de 95% para uma semana. Pontos escuros marcam as semanas em que o observado superou o limite superior. Para comparar semanas com e sem calor, selecione um critério de calor em Sombrear semanas com.`:
   (H.n&&N.n?`Nas ${H.n} ${critTxt}, foram observados ${fn(H.O)} óbitos, contra ${fn(H.E,0)} esperados sem calor (observado ÷ esperado = ${fr(H.raz)}, ou ${fp(pct(H.raz))}). Nas demais ${N.n} semanas, foram ${fn(N.O)} óbitos contra ${fn(N.E,0)} esperados (razão ${fr(N.raz)}). Os óbitos superaram o limite superior da faixa de 95% em ${fn(H.ac)}% das semanas de calor e em ${fn(N.ac)}% das demais; com o modelo bem calibrado, cerca de 2,5% das semanas ultrapassam esse limite por acaso. Esses percentuais descrevem a frequência de semanas atípicas; a fração de óbitos atribuível ao calor é outra medida. ${H.raz>N.raz?"A razão é maior nas semanas de calor.":"A razão não é maior nas semanas de calor."} O esperado provém de um modelo ajustado apenas a este recorte, de modo que a razão varia conforme o recorte. A comparação é descritiva e não inclui intervalo de confiança; a medida de associação é o RR acumulado do modelo, apresentado nos indicadores de RR acima da figura.`:`Há poucas semanas de calor no recorte selecionado para realizar a comparação.`));
  $("s-note").textContent=notaModelo(k,ex)+(modo().covid?" O período da COVID-19 (barra cinza na base) foi retirado do ajuste: nele, o esperado não é traçado e a semana fica fora dos indicadores. As semanas sem nenhum óbito registrado no SIM (faixa cinza clara) também ficam sem esperado.":" Os indicadores excluem o período da COVID-19 (barra cinza na base; o modelo tem um termo próprio para ele) e as semanas sem nenhum óbito registrado no SIM (faixa cinza clara), nas quais o esperado não é traçado.")+(modo().nc?" As semanas de meses com registro não consolidado (hachuradas) foram retiradas do ajuste e ficam sem esperado.":" As semanas de meses com registro não consolidado (hachuradas) entram no modelo e nos indicadores, e o registro nelas pode estar abaixo do real.")+notaClima()+notaAjuste(kd)+notaCausa()+" Semanas de calor: sombreadas em tom escuro. Faixa de 95%: esperado semanal ± 1,96 × √(φ × soma das variâncias diárias do modelo), com dispersão semanal φ = "+fr(S.phi)+" (estimada nos resíduos semanais); a faixa não inclui a incerteza dos coeficientes."+(S.phi>3?" Atenção: φ elevado indica que o modelo não acompanha bem a tendência de longo prazo desta série (por exemplo, por mudança na forma de registrar o local do óbito), o que alarga a faixa.":"")+" A série começa em 2006 (SIM); há dados de clima a partir de abril de 2007, e as semanas sem clima não entram na comparação entre semanas de calor e as demais."+NOTA_BARRAS(B);
  $("s-csv").onclick=()=>{let t="semana_inicio;ano_epidemiologico;semana_epidemiologica;observado;esperado_sem_calor;limite_inferior_95;limite_superior_95;dias_indice_calor_max_36;dias_nc2_a_nc5;registro_sim\n";const c1=v=>v==null?"":v.toFixed(1).replace(".",",");
    idx.forEach((i,q)=>{t+=[sem.ini[i],sem.ano[i],sem.se[i],ob[q]??"",c1(es[q]),c1(lo[q]),c1(up[q]),nb[q],nn[q],inc[q]?"sem_registro":nc[q]?"nao_consolidado":""].join(";")+"\n"});
    baixar(`serie_semanal_${ex}_${key.replace(/[^a-z0-9]+/gi,"_")}${sufixoArq()}.csv`,"﻿"+t)};
}

function notaModelo(k,ex,m=modo()){
  const e=EXP[ex];
  return `O esperado sem calor é estimado por um modelo aditivo generalizado (GAM) com família ${modeloTxt(k,ex)}, ajustado apenas a este recorte, com uma base cruzada (cross-basis) do pacote dlnm para a medida de calor selecionada (${e.nome}; ${e.fun==="ns"?"spline natural com 1 grau de liberdade, que impõe log-RR em linha reta nas horas, de modo que RR(8 h) = RR(4 h)²; a aba Exposição-resposta compara com uma curva flexível":"spline penalizado com 15 graus de liberdade, cujos graus de liberdade efetivos aparecem na aba Exposição-resposta"}) e defasagem de 0 a ${M.lag} dias (spline natural com 3 graus de liberdade), mais um spline de tempo (base de dimensão k = ${M.k_tempo}), um spline cíclico do dia do ano${m.covid?". O período da COVID-19 foi retirado do ajuste, de modo que o modelo não tem termo para ele.":" e um spline cíclico para o período da COVID-19."} O modelo não inclui termo de dia da semana. O esperado de cada dia é o preditor do modelo com a exposição ao calor igual a zero.`
}

/* ---------- diária ---------- */
function desenharDia(k){
  const ex=$("s-exp").value, key=keyF1(), kd=keyD();
  const y0=+$("s-ini").value, y1=Math.max(+$("s-fim").value,y0);
  const idx=[]; for(let j=0;j<dias.length;j++){ const a=+dias[j].slice(0,4); if(a>=y0&&a<=y1) idx.push(j) }
  const n=idx.length, fam=D.m[ex].f[k], disp=D.m[ex].d[k], O=D.o[k], E=D.m[ex].e[k];
  const ob=idx.map(j=>fl.inc[j]?null:O[j]), es=idx.map(j=>E[j]==null?null:E[j]/10);
  const sd=e=>Math.sqrt(fam==="nb"?e+e*e/disp:disp*e);
  const lo=es.map(e=>e==null?null:Math.max(e-1.96*sd(e),0)), up=es.map(e=>e==null?null:e+1.96*sd(e));
  const inc=idx.map(j=>!!fl.inc[j]), nc=idx.map(j=>!!fl.nc[j]), cov=idx.map(j=>!!fl.cov[j]), sc=idx.map(j=>!!(fl.sc&&fl.sc[j])), exp_=idx.map(j=>!!XW[j]);
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
    plugins:{legend:{display:false},covid:{cov,inc,nc,sc},barras:B.bars?{vals:B.bars,nc:B.modoNC?B.ncs:null,lim:B.lim,cor0:mkCor(cz,.30),cor1:mkCor(la,.62),corL:la,linhas:B.linhas}:null,
      traco:{ob,es,acima:ac,abaixo:ab,lw,al:curto?.85:.6},
      tooltip:{filter:i=>["Observado","Esperado"].includes(i.dataset.label),
        callbacks:{title:it=>{const d=dias[idx[it[0].dataIndex]]; return `${SEMANA[new Date(d+"T12:00:00").getDay()]}, ${dBR(d)}`},
          label:c=>c.dataset.label==="Esperado"?`Esperado sem calor: ${fn(c.parsed.y,1)}`:`Observado: ${fn(c.parsed.y)}`,
          afterBody:it=>{const i=it[0].dataIndex, j=idx[i], v=ob[i], e=es[i], L=[];
            if(v!=null&&e!=null){ const dif=v-e; L.push(`${dif>=0?"Acima":"Abaixo"} do esperado em ${fn(Math.abs(dif),1)} óbitos (observado ÷ esperado = ${fr(v/e)})`); if(v>up[i]) L.push("Acima do limite superior de 95%"); else if(v<lo[i]) L.push("Abaixo do limite inferior de 95%") }
            else if(inc[i]) L.push("Sem registro de óbitos no SIM (fora do ajuste, sem esperado)");
            if(cov[i]) L.push(linhaCov());
            if(nc[i]) L.push(linhaNC("dia"));
            L.push(cl.ok[j]?`Horas com índice de calor ≥ 36 °C: ${cl.h36[j]==null?"–":fn(cl.h36[j])} · dia de calor (≥ 4 h): ${EV[j]?"sim":"não"} · dia exposto: ${XW[j]?"sim":"não"}`:"Sem dado de clima neste dia: exposição não observada (fora do ajuste principal)");
            const h=cd.hi_max[j], hm=cd.hi_med.o[j], tm=cd.t_med.o[j]; if(h!=null) L.push(`Índice de calor: máximo ${fn(h,1)} °C · médio ${hm==null?"–":fn(hm,1)} °C · temperatura média ${tm==null?"–":fn(tm,1)} °C`);
            if(cd.nc[j]!=null) L.push(`Nível de calor do protocolo: NC${cd.nc[j]}`); return L}}}}},
    plugins:[covPlugin,barPlugin,pontoPlugin]});
  $("s-leg").innerHTML=`<span><i class="dt" style="background:${ac}"></i>Observado acima do esperado</span><span><i class="dt" style="background:${ab}"></i>Observado abaixo do esperado</span><span><i class="ln" style="background:${ink};height:3px"></i>Esperado sem calor</span><span><i class="ln" style="background:${cz}"></i>Linha do observado</span>`+
   `<span><i class="dt" style="background:transparent;border:2px solid ${ink};width:9px;height:9px"></i>Dia exposto (dia de calor no próprio dia ou em um dos 3 dias anteriores)</span>`+
   legendaBarras(B,cz,la,mkCor)+`<span><i style="background:${cz}"></i>${rotCov()}</span>`+(inc.some(Boolean)?`<span><i style="background:${cz};opacity:.3"></i>Sem registro no SIM (fora do ajuste)</span>`:"")+(nc.some(Boolean)?`<span><i style="background:repeating-linear-gradient(135deg,${cz} 0 1.3px,transparent 1.3px 4px)"></i>${rotNC()}</span>`:"")+(sc.some(Boolean)?`<span><i style="background:repeating-linear-gradient(90deg,${css("--azul")} 0 1px,transparent 1px 4px);opacity:.7"></i>Sem dado de clima (exposição não observada)</span>`:"");
  // indicadores: dias com esperado, com clima e fora de COVID; dias de mês não consolidado entram
  const ok=ob.map((v,i)=>v!=null&&es[i]!=null&&!!cl.ok[idx[i]]&&!cov[i]);
  const grp=f=>{let Oo=0,Ee=0,nn=0,ac_=0,sup=0;ob.forEach((v,i)=>{if(ok[i]&&f(i)){Oo+=v;Ee+=es[i];nn++;if(v>es[i])ac_++;if(v>up[i])sup++}});return {n:nn,O:Oo,E:Ee,raz:Ee?Oo/Ee:NaN,ac:nn?100*ac_/nn:NaN,sup:nn?100*sup/nn:NaN}};
  const T=grp(()=>true), H=grp(i=>exp_[i]), N=grp(i=>!exp_[i]);
  $("s-kpis").innerHTML=kpiHtml([
    [fn(ob.reduce((x,v)=>x+(v||0),0)),"óbitos nos dias mostrados"+(nc.some(Boolean)?` (inclui ${fn(nc.filter(Boolean).length)} dia(s) de mês com registro não consolidado${modo().nc?", fora do ajuste":""})`:"")],
    ...rrDoModelo(k,ex),
    [isFinite(H.raz)?fr(H.raz):"–","observado ÷ esperado sem calor nos "+fn(H.n)+" dias expostos (dia de calor no próprio dia ou em um dos 3 dias anteriores) do período mostrado"],
    [isFinite(N.raz)?fr(N.raz):"–","observado ÷ esperado sem calor nos "+fn(N.n)+" demais dias"],
    [isFinite(T.ac)?fn(T.ac)+"%":"–","dos "+fn(T.n)+" dias ficaram acima do esperado; "+(isFinite(T.sup)?fn(T.sup,1)+"% acima do limite superior de 95% (≈ 2,5% se o modelo estiver bem calibrado)":"")]
  ]);
  $("i-serie").innerHTML=`<span class="t">Interpretação</span>`+(H.n&&N.n?`Cada ponto é um dia: <span style="color:${ac}">vermelho</span> quando o número de óbitos ficou acima do esperado e <span style="color:${ab}">azul</span> quando ficou abaixo; o traço vertical liga o ponto ao esperado do dia. O esperado é o número de óbitos previsto pelo modelo sem calor (${compExp()}), com o efeito do calor (do dia e dos 10 dias anteriores) estimado e depois retirado. Nos dias expostos (contorno escuro), o observado fica acima do esperado na medida do efeito estimado para este recorte: ${fn(H.O)} óbitos contra ${fn(H.E,0)} esperados no período mostrado (observado ÷ esperado = ${fr(H.raz)}, ou ${fp(pct(H.raz))}); nos demais ${fn(N.n)} dias, ${fn(N.O)} contra ${fn(N.E,0)} (razão ${fr(N.raz)}). Como o modelo usa defasagens de até 10 dias e o contorno marca apenas 4, parte do efeito também aparece nos dias não expostos, e a razão destes pode ficar um pouco acima de 1. A contagem de um dia isolado varia ao acaso; a interpretação apoia-se na diferença sistemática entre grupos de dias. A exposição inclui o próprio dia e os três anteriores, de modo que um dia de calor aparece ligado a até quatro pontos com contorno escuro.`:`Há poucos dias expostos no período mostrado para realizar a comparação.`);
  $("s-note").textContent="Escala diária desde 2006 (há dados de clima a partir de abril de 2007; antes disso, o calor é tratado como ausente). O eixo vertical não parte de zero, para tornar visíveis as diferenças. "+notaModelo(k,ex)+" Faixa de 95% de um dia: esperado ± 1,96 × raiz da variância do modelo (a posição do observado em relação a ela é indicada ao passar o cursor; a faixa não inclui a incerteza dos coeficientes). "+(modo().covid?"O período da COVID-19 (barra cinza na base) foi retirado do ajuste e fica sem esperado; os dias sem nenhum óbito registrado no SIM (faixa cinza clara) também ficam sem esperado.":"Os indicadores excluem o período da COVID-19 (barra cinza na base) e os dias sem nenhum óbito registrado no SIM (faixa cinza clara), nos quais o esperado não é traçado.")+(modo().nc?" Dias de meses com registro não consolidado (hachurados) foram retirados do ajuste e ficam sem esperado.":" Dias de meses com registro não consolidado (hachurados) entram no modelo e nos indicadores.")+notaClima()+notaAjuste(kd)+notaCausa()+NOTA_BARRAS(B)+
    (n>2200?" Período longo: reduzir o intervalo entre Ano inicial e Ano final melhora a visualização dos pontos.":"");
  $("s-csv").onclick=()=>{let t="dia;observado;esperado_sem_calor;limite_inferior_95;limite_superior_95;horas_indice_calor_36;dia_de_calor;dia_exposto;indice_calor_maximo;indice_calor_medio;temperatura_media;nivel_calor;registro_sim\n";const c1=v=>v==null?"":v.toFixed(1).replace(".",",");
    idx.forEach((j,i)=>{t+=[dias[j],ob[i]??"",c1(es[i]),c1(lo[i]),c1(up[i]),cl.h36[j]??"",EV[j],XW[j],cd.hi_max[j]??"",cd.hi_med.o[j]??"",cd.t_med.o[j]??"",cd.nc[j]??"",inc[i]?"sem_registro":nc[i]?"nao_consolidado":""].join(";")+"\n"});
    baixar(`serie_diaria_${ex}_${key.replace(/[^a-z0-9]+/gi,"_")}${sufixoArq()}.csv`,"﻿"+t)};
}

/* Interface das outras abas (assets/aba_*.js): cada uma se registra em window.PainelAbas e recebe este objeto. */
const P = {$, css, fn, fr, fp, dBR, fillSel, nm, mkCor, M, D, SH, EXP, KEXP, ix, modo, cod:codOpc, eleg, enviar, ouvir:OUV, abas:window.__abas,
  kd:(c,o,k)=>c+"~"+o+"~"+k, cv:(kd,ex)=>(D.cv&&D.cv[ex]&&D.cv[ex][kd])||null, cb:(kd,ex)=>(D.cb&&D.cb[ex]&&D.cb[ex][kd])||null, mapa:kd=>(D.mp&&D.mp[kd])||{}, cid:kd=>(D.cd&&D.cd[kd])||{}, dg:kd=>(D.dg&&D.dg[kd])||{}, pop:()=>POP,
  rrKpi:(kd,ex)=>rrDoModelo(ix.get(kd),ex), notaModelo:(kd,ex,m)=>notaModelo(ix.get(kd),ex,m), modeloTxt:(kd,ex)=>modeloTxt(ix.get(kd),ex),
  texto:{rotCov, rotNC, linhaCov, linhaNC, compExp, notaClima, notaCausa, causaPor:c=>CAUSA_POR[c], causaRot:c=>CAUSA_ROT[c]}};
if(SH) (window.PainelAbas||[]).forEach(f=>f(P));
if(SH){ registrarShiny();
  const go=()=>{ racaSync(); window.__desenhar() };
  (window.Shiny.shinyapp && window.Shiny.shinyapp.isConnected && window.Shiny.shinyapp.isConnected()) ? go() : window.jQuery(document).one("shiny:connected",go) }
else { racaSync(); window.__desenhar() }
}
})();

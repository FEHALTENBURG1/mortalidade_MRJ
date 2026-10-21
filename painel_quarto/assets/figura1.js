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
const minus1 = t => /^[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]/.test(t) ? t[0].toLowerCase()+t.slice(1) : t;      // primeira letra minúscula, exceto siglas (UPA)
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
const COD0 = M.cod_padrao || "000";                                               // ajuste principal (covid, nc, clima); a página estática só traz esse ajuste
const modo = (p="s") => (SH && $(p+"-causa")) ? {covid:$(p+"-r-covid").checked, nc:$(p+"-r-nc").checked, clima:$(p+"-r-clima").checked, causa:$(p+"-causa").value} : {covid:COD0[0]==="1",nc:COD0[1]==="1",clima:COD0[2]==="1",causa:"naturais"};
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
// dia com >= 4 h de IC >= 36 °C (NC 2 ou mais); dia com exposição em t a t-3 = esse dia em t, t-1, t-2 ou t-3
const EV = cl.h36.map(v=>v!=null&&v>=4?1:0);
const XW = EV.map((_,i)=>{ for(let k=0;k<4;k++) if(i-k>=0&&EV[i-k]) return 1; return 0 });
const EXP = M.exposicoes;
const KEXP = Object.keys(EXP);
const REF_TXT = {horas:(v,u)=>`${fn(v)} ${u} diárias com IC ≥ 36 °C`, haat:(v,u)=>`${fn(v)} ${u} por dia acima de 36 °C de IC`};
const COR_ACIMA=()=>css("--acima"), COR_ABAIXO=()=>css("--abaixo");

const subtitulo = () => { $("sub").textContent = `Óbitos ocorridos no município do Rio de Janeiro e exposição ao calor, de ${M.inicio.slice(0,4)} a ${M.fim.slice(0,4)}. Estudo ecológico de série temporal, com componente analítico. Os modelos estimam a associação entre o Índice de Calor (IC) e a contagem diária de óbitos, após ajuste para os fatores descritos em Métodos e fontes. Série exibida: óbitos ${CAUSA_POR[modo().causa]} (SIM/DATASUS), observados e esperados sem calor pelo modelo, por local do óbito, faixa etária e raça/cor. Os resultados são retrospectivos e não são alertas operacionais.` };
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
/* Período exibido: a seleção de anos altera só o que se mostra (gráfico, óbitos, razões O/E e frequências acima da faixa); os RR e as curvas vêm do modelo ajustado com a série completa. */
function periodoExibido(){ const y0=+$("s-ini").value, y1=Math.max(+$("s-fim").value,y0), completo=y0===anos[0]&&y1===anos[anos.length-1];
  return {y0,y1,completo,txt:y0===y1?String(y0):y0+" a "+y1} }
function notaPeriodo(){
  const pe=periodoExibido(), aj=(D.aj||{})[keyD()], ajTxt=aj?`de ${dBR(aj.ini)} a ${dBR(aj.fim)}`:`de ${dBR(M.inicio)} a ${dBR(M.fim)}`;
  $("s-per-nota").textContent=`Período exibido: ${pe.txt}${pe.completo?" (série completa)":""}. O modelo foi ajustado com a série completa (${ajTxt}), e a seleção de anos altera só o que é mostrado. Os cartões "${TAG_MOD}" (RR) ficam iguais em qualquer período exibido. Os cartões "${TAG_PER}" (óbitos, razões observado/esperado sem calor e frequências acima da faixa) e a Figura 1 acompanham a seleção.` }
function racaNota(){ const rc=(SH&&D.rcs)?D.rcs[modo().causa]:D.rc; if(!rc){ $("s-raca-nota").textContent=""; return }
  const tot=Object.values(rc).reduce((a,b)=>a+b,0), pc=v=>fn(100*(v||0)/tot,1)+"%", n=k=>rc[k]||0;
  $("s-raca-nota").textContent=`Distribuição da raça/cor (campo RACACOR do SIM) nos ${fn(tot)} ${modo().causa==="naturais"?"óbitos por causas naturais da série":"óbitos da série ("+CAUSA_ROT[modo().causa]+")"}: branca ${pc(n("Branca"))}, parda ${pc(n("Parda"))}, preta ${pc(n("Preta"))}, amarela ${pc(n("Amarela"))}, indígena ${pc(n("Indígena"))} e raça/cor ignorada ou não informada ${pc(n("Ignorada"))}. As categorias indígena (${fn(n("Indígena"))} óbitos) e amarela (${fn(n("Amarela"))}) não têm óbitos suficientes para série própria. Os óbitos indígenas compõem o agregado PPI (preta, parda e indígena), e os de raça/cor amarela, ignorada ou não informada entram apenas em Todas. As séries por raça/cor são calculadas para todas as idades.` }

["s-local","s-faixa","s-exp","s-crit","s-ini","s-fim","s-bar","s-lim","s-cor","s-disp"].forEach(i=>$(i).onchange=desenhar);
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
const BARRA_NOME={t_med:"Temperatura média do ar do dia",hi_max:"IC máximo do dia",hi_med:"IC médio do dia"};
const BARRA_CURTO={t_med:"Temp. média (°C)",hi_max:"IC máximo (°C)",hi_med:"IC médio (°C)"};      // título do eixo do painel de clima, que é baixo
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
  const a=(D.aj||{})[D.k[k]], per=a?`${dBR(a.ini)} a ${dBR(a.fim)}`:`${dBR(M.inicio)} a ${dBR(M.fim)}`;
  return [0,3].map((i,j)=>[t(i), `RR acumulado em 0 a ${M.lag} dias: exposição de ${REF_TXT[ex](e.ref[j],e.unidade)} mantida por ${M.lag+1} dias, em comparação com ausência dessa exposição no mesmo intervalo. Estimativa do modelo ajustado para o período ${per}.`+(j===1?quad:""), TAG_MOD, "mod"]) }
const modeloTxt = (k, ex) => { const f=D.m[ex].f[k], d=D.m[ex].d[k];
  return f==="nb"?`binomial negativa (θ = ${fn(d,1)})`:`quase-Poisson (dispersão φ = ${fn(d,2)}; a binomial negativa não convergiu)` };

let chS=null, chC=null;                                   // chS: óbitos; chC: painel de clima (disposição alinhada)
const FAIXA = "Faixa aproximada de variação de 95%";
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
  if(chC){chC.destroy();chC=null}
  $("s-box2").classList.add("hide"); $("s-leg2").classList.add("hide"); $("s-box1").classList.remove("curto");
  const k=ix.get(kd);
  const aj=(D.aj||{})[kd], pe=periodoExibido(), partes=[];
  if(aj) partes.push(`ajuste estimado de ${dBR(aj.ini)} a ${dBR(aj.fim)}`);
  if(!pe.completo) partes.push(`período exibido: ${pe.txt}`);
  if(partes.length) $("s-h2").textContent+=` (${partes.join("; ")})`;
  notaPeriodo(); fichaEm("s-ficha", fichaFig1(kd,ex));
  if(k==null){ $("s-per-nota").textContent=""; $("s-kpis").innerHTML=""; $("s-leg").innerHTML=""; $("i-serie").innerHTML=""; $("s-note").textContent=`Menos de ${M.min_obitos} óbitos ${SH?"no ajuste ":""}neste recorte: série não estimada.`; $("s-sensw").classList.add("hide"); $("s-cobw").classList.add("hide"); return }
  dia?desenharDia(k):desenharSemana(k);
  atualizarSens(); quadroCob()
}
window.__desenhar=desenhar; window.__abas={serie:desenhar};

/* ---------- modo Shiny: pedir recortes ao servidor ---------- */
const quadros = on => { $("s-kpis").classList.toggle("calc",on); $("s-chart").parentNode.classList.toggle("calc",on); $("s-box2").classList.toggle("calc",on); $("s-cobw").classList.toggle("calc",on) };
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
    if(/^(diag|sens|flex|sup|cob)_/.test(msg.ex)){ (D.dg[kd]||(D.dg[kd]={}))[msg.ex]=JSON.parse(msg.json); if(/^cob_/.test(msg.ex)) quadroCob(); OUV.seg.forEach(f=>f(kd,msg.ex)); return }     // aba de diagnósticos (ajuste principal com diagnósticos e análises de sensibilidade) e aba de exposição-resposta (reta imposta contra curva flexível)
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
    if(/^cob_/.test(msg.ex)){ falhaCob.set(msg.causa+"~"+msg.opc+"~"+msg.key+"|"+msg.ex, String(msg.mensagem||"erro não identificado").replace(/[<>&]/g,"")); quadroCob() }
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

/* ---------- Quadro 5: cobertura da faixa semanal por período e grupo de semanas ---------- */
// Cobertura = semanas com o observado entre o limite inferior e o superior da faixa. Conta as semanas dos indicadores (com esperado, com clima, fora da COVID-19 e
// com registro no SIM) de todos os anos, sem a seleção de anos da figura. "Ajuste com a série completa" usa a faixa da Figura 1; "fora da amostra" usa a
// faixa do pedido cob_<medida> (modelo refeito sem cada período), pedida só quando o usuário clica.
const falhaCob = new Map();
const wilson = (a,n) => { if(!n) return [NaN,NaN]; const z=1.96, p=a/n, d=1+z*z/n, c=p+z*z/(2*n), r=z*Math.sqrt(p*(1-p)/n+z*z/(4*n*n)); return [(c-r)/d,(c+r)/d] };
const somaCob = (x,y) => ({n:x.n+y.n,d:x.d+y.d,a:x.a+y.a,b:x.b+y.b});
function contarCob(src,O,grupoF,p){
  const c={n:0,d:0,a:0,b:0};
  for(let i=0;i<nSem;i++){
    if(sem.ano[i]<p.de||sem.ano[i]>p.ate||!grupoF(i)) continue;
    const o=O[i], e=src.e[i], l=src.l[i], u=src.u[i];
    if(o==null||e==null||l==null||u==null||sem.cov[i]||sem.inc[i]||!sem.cl[i]) continue;
    c.n++; if(o>u) c.a++; else if(o<l) c.b++; else c.d++ }
  return c }
function quadroCob(){
  const box=$("s-cobw"); if(!box) return;
  const ex=$("s-exp").value, kd=keyD(), key=keyF1();
  if($("tab-serie").classList.contains("hide") || $("s-esc").value==="dia" || !D.S[ex] || D.S[ex][kd]===undefined || !(M.periodos_cob||[]).length){ box.classList.add("hide"); return }
  const S=D.S[ex][kd], O=D.So[kd], crit=$("s-crit").value, per=M.periodos_cob, causa=modo().causa, cod=codOpc(), idc="cob_"+ex;
  const C=((D.dg||{})[kd]||{})[idc], erro=falhaCob.get(kd+"|"+idc), voando=!C&&PEND.has(idPedido(POP,key,idc,causa,cod));
  const ehExt=pi=>!!(C&&C.refeitos&&C.refeitos[pi]&&C.refeitos[pi].extrapola);        // período previsto por extrapolação (sem anos de ajuste de um dos lados)
  const calor = crit==="ic" ? sem.nb.map(v=>v>=3) : crit==="nc" ? sem.nn.map(v=>v>=1) : sem.nb.map(()=>false);
  const grupos = crit==="no" ? [{t:"Todas as semanas",f:()=>true}] : [{t:"Semanas de calor",f:i=>calor[i]},{t:"Demais semanas",f:i=>!calor[i]}];
  const tot = grupos.map(()=>({a:{n:0,d:0,a:0,b:0},o:{n:0,d:0,a:0,b:0}})), porPer = per.map(()=>grupos.map(()=>null));
  per.forEach((p,pi)=>grupos.forEach((g,gi)=>{ const a=contarCob(S,O,g.f,p), o=C?contarCob(C,O,g.f,p):null; porPer[pi][gi]={a,o}; tot[gi].a=somaCob(tot[gi].a,a); if(o) tot[gi].o=somaCob(tot[gi].o,o) }));
  const cel = (c,pri) => { if(!c||!c.n) return `<td class="n${pri?" gr2":""}">${c?"0":"–"}</td><td class="n">–</td><td class="n">–</td><td class="n">–</td>`;
    const w=wilson(c.d,c.n), tt=`Intervalo binomial de 95% (Wilson) da cobertura: ${fn(100*w[0],1)}% a ${fn(100*w[1],1)}%. Ignora a dependência entre semanas vizinhas.`;
    return `<td class="n${pri?" gr2":""}">${fn(c.n)}</td><td class="n" title="${tt}">${fn(100*c.d/c.n,1)}%</td><td class="n">${fn(100*c.a/c.n,1)}%</td><td class="n">${fn(100*c.b/c.n,1)}%</td>` };
  const linhas=[]; 
  per.forEach((p,pi)=>{ const vis=grupos.map((g,gi)=>gi).filter(gi=>porPer[pi][gi].a.n||(porPer[pi][gi].o&&porPer[pi][gi].o.n)); vis.forEach((gi,q)=>
    linhas.push(`<tr>${q===0?`<td rowspan="${vis.length}">${p.rot}${ehExt(pi)?" †":""}</td>`:""}<td>${grupos[gi].t}</td>${cel(porPer[pi][gi].a,true)}${cel(C?porPer[pi][gi].o:null,true)}</tr>`)) });
  grupos.forEach((g,gi)=>linhas.push(`<tr class="ext">${gi===0?`<td rowspan="${grupos.length}">Todos os períodos</td>`:""}<td>${g.t}</td>${cel(tot[gi].a,true)}${cel(C?tot[gi].o:null,true)}</tr>`));
  $("s-cob").innerHTML=`<thead><tr><th rowspan="2">Período</th><th rowspan="2">Grupo</th><th class="n gr2" colspan="4">Ajuste com a série completa</th><th class="n gr2" colspan="4">Fora da amostra (período retirado do ajuste)</th></tr>`+
    `<tr><th class="n gr2">Semanas</th><th class="n">Dentro da faixa</th><th class="n">Acima</th><th class="n">Abaixo</th><th class="n gr2">Semanas</th><th class="n">Dentro da faixa</th><th class="n">Acima</th><th class="n">Abaixo</th></tr></thead><tbody>${linhas.join("")}</tbody>`;
  const btn=$("s-cob-btn"), st=$("s-cob-st");
  btn.classList.toggle("hide", !SH || !!C || voando);
  st.textContent = !SH ? "A cobertura fora da amostra só está disponível no painel online." : C ? "Fora da amostra calculado: o modelo foi refeito sem cada período." : voando ? "Calculando: o modelo é refeito sem cada período (cerca de 1 a 3 minutos na primeira solicitação; o resultado fica armazenado no servidor)…" : erro ? "Não foi possível calcular: "+erro : "Fora da amostra: ainda não calculado. O cálculo refaz o modelo deste recorte sem cada período (cerca de 1 a 3 minutos).";
  btn.disabled=false; btn.onclick=()=>{ falhaCob.delete(kd+"|"+idc); enviar(key,idc,causa,cod); quadroCob() };
  $("s-cob-n").textContent="Cobertura: proporção das semanas com o número de óbitos observado entre o limite inferior e o limite superior da faixa. Contam as mesmas semanas dos indicadores da figura (com esperado estimado, com dados de clima, fora do período da COVID-19 e com registro no SIM), de todos os anos, sem a seleção de anos da figura. Os períodos usam o ano epidemiológico da semana. Ajuste com a série completa: o modelo e o φ foram estimados com todas as semanas do quadro. Fora da amostra: cada período é retirado do ajuste, o modelo é refeito com os demais anos e o φ é estimado só nas semanas que ficaram; os períodos do meio são previstos pela tendência dos vizinhos (interpolação), e o primeiro e o último, por extrapolação da tendência (†). A especificação do modelo foi definida com a série completa, de modo que este quadro não é uma validação independente. Nas semanas de calor, os óbitos acima do limite superior misturam falta de calibração e efeito do calor, e a calibração se lê nas demais semanas. Ao passar o cursor sobre a cobertura aparece o intervalo binomial de 95% (Wilson), que ignora a dependência entre semanas vizinhas.";
  $("s-cob-n2").textContent="Três intervalos diferentes: o intervalo de confiança do esperado descreve a incerteza dos coeficientes sobre o número médio de óbitos sem calor; o intervalo preditivo descreve onde pode cair o número de óbitos de uma semana (variação aleatória e incerteza dos coeficientes); a faixa mostrada na Figura 1 aproxima o segundo com a variação aleatória e o φ semanal, e deixa de fora a incerteza dos coeficientes."+
    (C&&C.inc&&C.inc.n ? ` No ajuste principal deste recorte, somar a incerteza dos coeficientes alargaria a faixa em ${fn(100*(C.inc.mediana-1),1)}% na mediana das ${fn(C.inc.n)} semanas (até ${fn(100*(C.inc.maxima-1),1)}%).` : "");
  // leitura: calibração nas semanas sem calor (ou em todas, sem critério); intervalos de períodos só com pelo menos 20 semanas
  const gc=grupos.length-1, MIN_N=20, pc=c=>100*c.d/c.n, pct=c=>c.n?fn(pc(c),1)+"%":"–", lista=a=>a.length>1?a.slice(0,-1).join(", ")+" e "+a[a.length-1]:a.join("");
  const gt=grupos[gc].t.toLowerCase();
  const entre=(pis,campo)=>{ const v=pis.map(pi=>({rot:per[pi].rot,c:porPer[pi][gc][campo]})).filter(z=>z.c&&z.c.n>=MIN_N).sort((x,y)=>pc(x.c)-pc(y.c));
    return v.length>1 ? `, de ${fn(pc(v[0].c),1)}% (${v[0].rot}) a ${fn(pc(v[v.length-1].c),1)}% (${v[v.length-1].rot}) entre os períodos com pelo menos ${MIN_N} semanas` : "" };
  const acBa=c=>`; ficaram acima do limite superior ${fn(100*c.a/c.n,1)}% e abaixo do limite inferior ${fn(100*c.b/c.n,1)}%`;
  const todos=per.map((_,pi)=>pi), T=tot[gc].a;
  let leit = T.n ? `No ajuste com a série completa, a faixa cobriu ${pct(T)} das ${fn(T.n)} ${gt}${entre(todos,"a")}${acBa(T)}. ` : "";
  if(C){ const pi_i=todos.filter(pi=>!ehExt(pi)), pi_e=todos.filter(pi=>ehExt(pi)), soma=pis=>pis.reduce((x,pi)=>somaCob(x,porPer[pi][gc].o||{n:0,d:0,a:0,b:0}),{n:0,d:0,a:0,b:0});
    const Ti=soma(pi_i), Te=soma(pi_e);
    if(Ti.n) leit+=`Fora da amostra, nos períodos previstos por interpolação (${lista(pi_i.filter(pi=>porPer[pi][gc].o&&porPer[pi][gc].o.n).map(pi=>per[pi].rot))}), a faixa cobriu ${pct(Ti)} das ${fn(Ti.n)} ${gt}${entre(pi_i,"o")}${acBa(Ti)}. `;
    if(Te.n) leit+=`Nos períodos das pontas da série, previstos por extrapolação da tendência, a cobertura foi de ${lista(pi_e.filter(pi=>porPer[pi][gc].o&&porPer[pi][gc].o.n).map(pi=>`${pct(porPer[pi][gc].o)} em ${per[pi].rot}`))}; a extrapolação soma o erro de tendência ao erro da faixa. ` }
  $("s-cob-i").innerHTML=`<span class="t">Interpretação</span>`+(leit?leit+"Uma faixa bem calibrada cobriria cerca de 95% das semanas em cada período. A diferença em relação a 95% pode vir de dispersão que o φ único não captura, de mudança de tendência dentro do período ou de dependência entre semanas vizinhas, e o quadro não separa essas causas. Os percentuais não validam o modelo e não são a medida de associação do calor, que é o RR acumulado do modelo."
    :"Não há semanas suficientes com esperado estimado para calcular a cobertura neste recorte.");
  box.classList.remove("hide");
}

/* ---------- barras de clima ao fundo (comum às duas escalas) ---------- */
/* Disposição alinhada: o clima sai do gráfico de óbitos e vai para um painel logo abaixo, com o mesmo eixo do tempo e a mesma largura do eixo vertical. */
const LARG_Y = 64, larguraY = sc => { sc.width = LARG_Y }, eixoX = sc => { sc.paddingLeft = 0; sc.paddingRight = 10 };
const alinhado = B => !!B.bars && $("s-disp").value==="alinhado";
function infoClimaSemana(B,q){
  const v=(B.bars[q]||[]).filter(z=>z!=null&&!isNaN(z)); if(!v.length) return null;
  let t=`${BARRA_NOME[B.bv]}: ${fn(Math.min(...v),1)} a ${fn(Math.max(...v),1)} °C na semana; `;
  if(B.modoNC&&B.ncs){ const c={}; B.ncs[q].forEach(n=>{ if(n!=null&&n>1) c[n]=(c[n]||0)+1 }); const l=Object.keys(c).map(n=>`${c[n]} dia(s) em NC ${n}`); t+=l.length?l.join(", "):"nenhum dia acima de NC 1" }
  else t+=`${v.filter(z=>z>B.lim).length} dia(s) acima de ${fn(B.lim,1)} °C`;
  return t }
function painelClima(B,labels,tickCb,tip){
  $("s-box1").classList.add("curto"); $("s-box2").classList.remove("hide"); $("s-leg2").classList.remove("hide");
  if(chS) chS.resize();
  const tickc=css("--mut"), gridc=css("--grid"), cz=css("--cinza"), la=css("--laranja");
  const topo=B.bars.map(w=>{ const v=w.filter(z=>z!=null&&!isNaN(z)); return v.length?Math.max(...v):null });
  $("s-leg2").innerHTML=legendaBarras(B,cz,la,mkCor,true);
  chC=new Chart($("s-chart2"),{type:"line",data:{labels,datasets:[{label:BARRA_NOME[B.bv],data:topo.map(v=>v==null?0:v),yAxisID:"yt",borderWidth:0,pointRadius:0,pointHoverRadius:0}]},
    options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:"index",intersect:false},
      scales:{x:{grid:{display:false},afterFit:eixoX,ticks:{color:tickc,autoSkip:false,maxRotation:0,callback:tickCb}},
        yt:{position:"left",min:0,max:B.tmax,grid:{color:gridc},ticks:{color:tickc,stepSize:10},title:{display:true,text:BARRA_CURTO[B.bv],color:tickc},afterFit:larguraY}},
      plugins:{legend:{display:false},barras:{vals:B.bars,nc:B.modoNC?B.ncs:null,lim:B.lim,cor0:mkCor(cz,.30),cor1:mkCor(la,.62),corL:la,linhas:B.linhas},
        tooltip:{callbacks:{title:it=>tip.titulo(it[0].dataIndex),label:c=>topo[c.dataIndex]==null?"Sem dado de clima (exposição não observada)":`${tip.rotulo}: ${fn(topo[c.dataIndex],1)} °C`,
          afterBody:it=>{ const t=tip.extra(it[0].dataIndex); return t?[t]:[] }}}}},
    plugins:[barPlugin]}) }

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
function legendaBarras(B,cz,la,mk,AL){
  if(!B.bars) return "";
  return `<span><i style="background:${mk(cz,.30)}"></i>${BARRA_NOME[B.bv]} (coluna diária${AL?" do painel de clima":", eixo da direita"})</span>`+(B.modoNC?[2,3,4,5].map(n=>`<span><i style="background:${NC_COR[n]}"></i>NC ${n} (${fn(B.nNC[n])} dias)</span>`).join("")+`<span><i style="background:${mk(cz,.30)}"></i>NC 1 (${fn(B.nNC[1])} dias)</span>`:`<span><i style="background:${mk(la,.62)}"></i>dia acima de ${fn(B.lim,1)} °C</span>`) }
const mkCor=(c,al)=>{const m=c.match(/#(..)(..)(..)/);return m?`rgba(${parseInt(m[1],16)},${parseInt(m[2],16)},${parseInt(m[3],16)},${al})`:c};
const NOTA_BARRAS = (B,AL) => B.bars?` ${AL?"Painel de clima, alinhado ao gráfico de óbitos pelo eixo do tempo":"Colunas ao fundo"}: ${minus1(BARRA_NOME[B.bv])}, ${AL?"com a escala em °C à esquerda":"no eixo da direita (°C)"}. `+
  (B.modoNC?"Níveis de Calor (NC 1 a NC 5) estimados retrospectivamente a partir das horas observadas de IC. Esta reconstrução não incorpora previsão meteorológica e pode diferir do NC monitorado e divulgado pelo Centro de Operações e Resiliência do Rio (COR). Critérios usados, segundo o Protocolo de Enfrentamento ao Calor Extremo da SMS-Rio (Quadro 1) e o Decreto Rio nº 54.740/2024: NC 2, pelo menos 4 h com IC ≥ 36 °C em 1 ou 2 dias seguidos; NC 3, o mesmo critério por 3 dias seguidos ou mais; NC 4, pelo menos 4 h com IC ≥ 40 °C dentro de uma sequência de NC 3; NC 5, pelo menos 2 h com IC ≥ 44 °C dentro de uma sequência de NC 3. O protocolo usa “acima de” 36, 40 e 44 °C, e o painel usa “≥”. O protocolo usa dados do Alerta Rio, do INMET e da REDMET; o painel usa o Alerta Rio e o INMET. Os NC do painel não são alertas operacionais. Como o nível depende das horas nos limiares, a cor pode não acompanhar a altura da coluna quando esta representa o IC médio ou a temperatura média do ar."
   :`Em laranja, os dias acima de ${fn(B.lim,1)} °C: ${fn(B.bAcima)} de ${fn(B.bDias)} dias no período mostrado (${fn(100*B.bAcima/Math.max(B.bDias,1),1)}%).`):"";
/* Etiqueta de cada cartão: o que muda com o período exibido (seleção de anos) e o que vem do modelo ajustado com a série completa. */
const TAG_MOD = "Modelo ajustado com a série completa", TAG_PER = "Período exibido";
/* tipo: "mod" = RR estimado pelo modelo; "desc" = medida descritiva (razão O/E, frequência acima da faixa), que não é um RR e não tem intervalo de confiança. A etiqueta e a borda diferenciam os dois. */
const TIPO_KPI = {mod:"RR do modelo", desc:"Descritivo, não é RR"};
const kpiHtml = lista => lista.map(([v,l,tag,tipo])=>`<div class="kpi${tipo?" "+tipo:""}">${(tag||tipo)?`<div class="tg">${tipo?`<span class="tp">${TIPO_KPI[tipo]}</span>`:""}${tag||""}</div>`:""}<div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
/* Textos que dependem do que foi retirado do ajuste (sem as caixas marcadas, saem idênticos aos da página do Quarto). */
const rotCov = (m=modo()) => m.covid ? "Período da COVID-19 (fora do ajuste)" : "Período da COVID-19 (termo próprio no modelo)";
const rotNC = (m=modo()) => m.nc ? "Registro não consolidado (fora do ajuste)" : "Registro não consolidado (no ajuste)";
const linhaCov = (m=modo()) => m.covid ? "Período da COVID-19 (retirado do ajuste; sem esperado e fora dos indicadores)" : "Período da COVID-19 (o modelo inclui um termo para o período; fora dos indicadores)";
const linhaNC = (u,m=modo()) => m.nc ? `Registro não consolidado (${u} retirado do ajuste; sem esperado)` : `Registro não consolidado (${u} no ajuste; o observado pode estar abaixo do real)`;
const compExp = (m=modo()) => m.covid ? "tendência de longo prazo e sazonalidade anual" : "tendência de longo prazo, sazonalidade anual e período da COVID-19";
const notaClima = (m=modo()) => m.clima ? ` Os dias sem dados de clima e os ${M.lag} dias seguintes foram retirados do ajuste, e o esperado não é traçado nesses dias (nesses dias a exposição ao calor não foi observada; não são dias sem calor).` : " Atenção: os dias sem dados de clima foram mantidos no ajuste como dias sem calor, que era a especificação anterior do painel e só deve ser usada como sensibilidade.";
const ORDEM_MOTIVOS = ["sem_registro","clima","nc","covid"];
const notaAjuste = kd => { const a=(D.aj||{})[kd]; if(!a) return "";
  const rot=ORDEM_MOTIVOS.map((m,i)=>a.xd[i]>0?`${fn(a.xd[i])} dia(s) ${(M.motivos_fora||{})[m]||m} (${fn(a.xo[i])} óbitos)`:null).filter(Boolean);
  return ` Amostra do ajuste: ${fn(a.nd)} dias e ${fn(a.no)} óbitos, de ${dBR(a.ini)} a ${dBR(a.fim)}.`+(rot.length?` Fora do ajuste: ${rot.join("; ")}.`:" Nenhum dia fora do ajuste.") };
const notaCausa = (m=modo()) => { const c=m.causa; return c==="naturais" ? "" : " Causa do óbito: "+(c==="externas" ? "causas externas (V01 a Y98 da CID-10)" : c==="todas" ? "todas as causas, com COVID-19" : "todas as causas, exceto COVID-19")+"." };
/* ---------- ficha do resultado ----------
   Junto de cada resultado: versão dos dados, população, recorte, causa, período do ajuste, exposição e defasagem, retiradas do ajuste, família do modelo e ressalvas.
   Uma só função monta o texto para todas as abas e para o CSV; cada aba informa o seu recorte e, quando há modelo, a chave dos dados (kd) e a medida de calor (ex). */
const POP_TXT = {res:"residentes no município do Rio de Janeiro com óbito ocorrido no próprio município", todos:"todos os óbitos ocorridos no município do Rio de Janeiro, residentes ou não"};
const CAUSA_FICHA = {naturais:"causas naturais (A00 a R99 da CID-10, exceto COVID-19)", todas_sem_covid:"todas as causas, exceto COVID-19", todas:"todas as causas, com COVID-19", externas:"causas externas (V01 a Y98 da CID-10)"};
const RESSALVAS = "estudo ecológico de série temporal; a exposição é uma série municipal agregada, e a mudança da rede de estações ao longo da série não é ajustada; o confundimento residual não está excluído; o local do óbito não é a residência; o RR descreve associação em dados agregados e não risco individual.";
const GRUPOS_TXT = "O local corresponde ao lugar de ocorrência do óbito. Diferenças entre grupos devem ser avaliadas com teste de interação; os RR apresentados separadamente não estabelecem, por si só, que um grupo tenha associação maior. Os grupos também diferem em composição (por exemplo, idade e causa), que a comparação não ajusta.";
const recorteTxt = (local,faixa,raca) => `local do óbito: ${minus1(nm(local))}; faixa etária: ${faixa==="Todas as idades"?"todas as idades":faixa+" anos"}; raça/cor: ${raca==="Todas"?"todas":({PPI:"preta, parda e indígena (PPI)",Branca:"branca",Preta:"preta",Parda:"parda"})[raca]||String(raca).toLowerCase()}`;
const recorteFiltrado = (local,faixa,raca) => local!=="Todos os locais" || faixa!=="Todas as idades" || raca!=="Todas";
const dadosTxt = () => { const d=M.dados, serie=`série de ${dBR(M.inicio)} a ${dBR(M.fim)}`;
  return d ? `SIM atualizado em ${d.sim_atualizado} (${d.repo_sim}); clima atualizado em ${d.clima_atualizado}; ${serie}; dados gerados em ${d.gerado_em}${d.chave?"; versão "+String(d.chave).slice(0,8):""}` : `${serie}; página gerada em ${M.gerado_em}` };
const retiradasTxt = (m=modo()) => { const fora=["dias sem registro no SIM"], dentro=[];
  (m.covid?fora:dentro).push(m.covid?"período da COVID-19 (o modelo não tem o termo s(COVID))":"período da COVID-19 (com o termo s(COVID))");
  (m.nc?fora:dentro).push("meses de registro não consolidado");
  (m.clima?fora:dentro).push(m.clima?`dias sem dado de clima e os ${M.lag} seguintes`:"dias sem dado de clima (contados como dias sem calor)");
  return `retirados do ajuste: ${fora.join("; ")}${dentro.length?". Mantidos no ajuste: "+dentro.join("; "):""}` };
const expTxt = ex => { const E=EXP[ex];
  return `${E.nome.replace("IC","Índice de Calor (IC)")}; ${E.fun==="ns"?"spline natural":"spline penalizado"} com ${E.df} ${E.df===1?"grau":"graus"} de liberdade; defasagem de 0 a ${M.lag} dias (spline natural com 3 graus de liberdade); níveis de referência de ${E.ref.map(v=>fn(v)).join(" e ")} ${E.unidade} por dia` };
const ajusteTxt = kd => { const a=(D.aj||{})[kd]; return a ? `${dBR(a.ini)} a ${dBR(a.fim)} (${fn(a.nd)} dias e ${fn(a.no)} óbitos)` : null };
/* o: {recorte, kd, ex, m, modelo, filtrado, linhas}. modelo (texto) substitui a família lida do ajuste; linhas acrescenta pares [rótulo, texto]. */
function fichaLinhas(o){
  const m=o.m||modo(), L=[["Dados",dadosTxt()],["População",POP_TXT[POP]||POP],["Recorte",o.recorte],["Causa do óbito",CAUSA_FICHA[m.causa]]];
  if(o.kd!=null){ const a=ajusteTxt(o.kd); L.push(["Período do ajuste",a||"ajuste ainda não disponível para este recorte"]) }
  if(o.ex) L.push(["Exposição e defasagem",expTxt(o.ex)]);
  L.push(["Retiradas",retiradasTxt(m)]);
  if(o.modelo) L.push(["Modelo",o.modelo]);
  else if(o.kd!=null&&o.ex){ const k=ix.get(o.kd); if(k!=null&&D.m[o.ex]&&D.m[o.ex].f[k]!==undefined) L.push(["Modelo",`GAM com defasagens distribuídas (DLNM), ajustado por REML; família ${modeloTxt(k,o.ex)}; spline do tempo com base de dimensão k = ${M.k_tempo}`]) }
  (o.linhas||[]).forEach(l=>L.push(l));
  if(o.filtrado) L.push(["Comparação entre grupos",GRUPOS_TXT]);
  L.push(["Ressalvas",RESSALVAS]);
  return L }
const fichaHtml = L => `<div class="ficha-t">Ficha do resultado</div><dl>`+L.map(([r,t])=>`<div${["Ressalvas","Comparação entre grupos","Família de testes"].includes(r)?' class="larga"':""}><dt>${r}</dt><dd>${t}</dd></div>`).join("")+`</dl>`;
const fichaEm = (id,o) => { const el=$(id); if(!el) return; if(!o){ el.innerHTML=""; el.classList.add("hide"); return } el.innerHTML=fichaHtml(fichaLinhas(o)); el.classList.remove("hide") };
const fichaFig1 = (kd,ex) => { const pe=periodoExibido(), dia=$("s-esc").value==="dia", crit=$("s-crit").value;
  const lin=[["Período exibido",`${pe.txt}${pe.completo?" (série completa)":""}; a seleção de anos altera só o que é mostrado, e o modelo é ajustado com a série completa do recorte`]];
  if(dia) lin.push(["Dia com exposição em t a t−3","dia com ≥ 4 h de IC ≥ 36 °C no próprio dia ou em um dos 3 dias anteriores"]);
  else lin.push(["Semana de calor",crit==="ic"?"semana com pelo menos 3 dias com IC máximo ≥ 36 °C":crit==="nc"?"semana com ao menos um dia em NC 2 a NC 5, estimado retrospectivamente pelo painel":"sem sombreamento"]);
  const [l,f,r]=[$("s-local").value,$("s-faixa").value,$("s-raca").value];
  return {recorte:recorteTxt(l,f,r), kd, ex, filtrado:recorteFiltrado(l,f,r), linhas:lin} };
const fichaCsv = o => fichaLinhas(o).map(([r,t])=>`# ${r}: ${String(t).replace(/<[^>]*>/g,"").replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&amp;/g,"&")}`).join("\n")+"\n";
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
  const B=barrasClima(idx.map(i=>diaIx.get(sem.ini[i])), true), AL=alinhado(B);
  chS=new Chart($("s-chart"),{type:"bar",data:{labels,datasets:[
    {label:"darkcol",type:"bar",data:dark,yAxisID:"yb",backgroundColor:mkCor(la,.40),borderWidth:0,barPercentage:1,categoryPercentage:1,order:9},
    {label:"lightcol",type:"bar",data:light,yAxisID:"yb",backgroundColor:mkCor(la,.16),borderWidth:0,barPercentage:1,categoryPercentage:1,order:9},
    {label:"lo",type:"line",data:lo,borderWidth:0,pointRadius:0,order:6},
    {label:FAIXA,type:"line",data:up,borderWidth:0,pointRadius:0,fill:"-1",backgroundColor:mkCor(az,.17),order:6},
    {label:"Observado",type:"line",data:ob,borderColor:cz,borderWidth:1.1,pointRadius:0,pointHoverRadius:4,order:3},
    {label:"Esperado sem calor",type:"line",data:es,borderColor:az,borderWidth:2,pointRadius:0,order:2},
    {label:"Acima da faixa",type:"line",data:acima,showLine:false,pointRadius:3,pointBackgroundColor:ink,pointBorderColor:css("--card"),pointBorderWidth:1,order:1},
    {label:"_eixo_t",type:"line",data:idx.map(()=>null),yAxisID:"yt",borderWidth:0,pointRadius:0}
  ]},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:"index",intersect:false},
    scales:{x:{grid:{display:false},afterFit:AL?eixoX:undefined,ticks:{color:tickc,autoSkip:false,maxRotation:0,callback:function(v){const i=idx[v];return sem.se[i]===1?sem.ano[i]:""}}},
      y:{beginAtZero:true,grid:{color:gridc},ticks:{color:tickc},title:{display:true,text:"Óbitos por semana",color:tickc},afterFit:AL?larguraY:undefined},
      yb:{display:false,min:0,max:1},
      yt:AL?{display:false,min:0,max:1}:{display:!!B.bars,position:"right",min:0,max:B.tmax*1.7,grid:{display:false},ticks:{color:tickc,stepSize:10,callback:v=>v<=B.tmax?v:""},title:{display:!!B.bars,text:B.bars?BARRA_NOME[B.bv]+" (°C)":"",color:tickc}}},
    plugins:{legend:{display:false},covid:{cov,inc,nc,sc},barras:B.bars&&!AL?{vals:B.bars,nc:B.modoNC?B.ncs:null,lim:B.lim,cor0:mkCor(cz,.30),cor1:mkCor(la,.62),corL:la,linhas:B.linhas}:null,
      tooltip:{filter:i=>["Observado","Esperado sem calor",FAIXA].includes(i.dataset.label),
        callbacks:{label:c=>c.dataset.label===FAIXA?`${FAIXA}: ${lo[c.dataIndex]==null?"–":fn(lo[c.dataIndex])+" a "+fn(up[c.dataIndex])}`:`${c.dataset.label}: ${fn(c.parsed.y,c.dataset.label==="Observado"?0:1)}`,
          afterBody:it=>{const i=idx[it[0].dataIndex], q=it[0].dataIndex, L=[`Início da semana: ${dBR(sem.ini[i])}`,`IC máximo: ${sem.mxh[i]==null?"–":fn(sem.mxh[i],1)} °C · dias com IC máximo ≥ 36 °C: ${sem.nb[i]} · dias em NC 2 a NC 5 (estimados retrospectivamente): ${sem.nn[i]}`,`Temperatura média do ar: ${sem.mt[i]==null?"–":fn(sem.mt[i],1)} °C`];
            if(ob[q]!=null&&es[q]!=null) L.push(`Razão observado/esperado sem calor (O/E): ${fr(ob[q]/es[q])}`);
            if(B.bars){ const t=infoClimaSemana(B,q); if(t) L.push(t) }
            if(!sem.cl[i]) L.push("Sem dados de clima nesta semana (exposição não observada)");
            if(cov[q]) L.push(linhaCov());
            if(inc[q]) L.push("Sem registro de óbitos no SIM (fora do ajuste)");
            if(nc[q]) L.push(linhaNC("semana"));
            return L}}}}},
    plugins:[covPlugin,barPlugin]});
  if(AL) painelClima(B,labels,chS.options.scales.x.ticks.callback,{titulo:q=>`SE ${sem.se[idx[q]]}/${sem.ano[idx[q]]} (início em ${dBR(sem.ini[idx[q]])})`,rotulo:"Maior valor da semana",extra:q=>infoClimaSemana(B,q)});
  $("s-leg").innerHTML=`<span><i class="ln" style="background:${cz}"></i>Observado</span><span><i class="ln" style="background:${az};height:3px"></i>Esperado sem calor</span><span><i style="background:${mkCor(az,.17)}"></i>${FAIXA}</span><span><i class="dt" style="background:${ink}"></i>Observado acima da faixa</span>`+
   (crit==="ic"?`<span><i style="background:${mkCor(la,.40)}"></i>≥ 3 dias com IC máximo ≥ 36 °C</span><span><i style="background:${mkCor(la,.16)}"></i>1 a 2 dias</span>`:"")+(crit==="nc"?`<span><i style="background:${mkCor(la,.40)}"></i>Semana com dia em NC 2 a NC 5 (estimado retrospectivamente)</span>`:"")+
   (AL?"":legendaBarras(B,cz,la,mkCor,false))+`<span><i style="background:${cz}"></i>${rotCov()}</span>`+(inc.some(Boolean)?`<span><i style="background:${cz};opacity:.3"></i>Sem registro no SIM (fora do ajuste)</span>`:"")+(nc.some(Boolean)?`<span><i style="background:repeating-linear-gradient(135deg,${cz} 0 1.3px,transparent 1.3px 4px)"></i>${rotNC()}</span>`:"")+(sc.some(Boolean)?`<span><i style="background:repeating-linear-gradient(90deg,${az} 0 1px,transparent 1px 4px);opacity:.7"></i>Sem dado de clima (exposição não observada)</span>`:"");
  // indicadores: sem COVID, sem semanas sem registro e sem semanas sem clima (semanas de registro não consolidado entram)
  const ok=idx.map((_,q)=>!(cov[q]||inc[q]||!sem.cl[idx[q]]||es[q]==null));
  const grp=f=>{let Oo=0,E=0,n=0,ab=0;ob.forEach((v,q)=>{if(ok[q]&&f(q)){Oo+=v;E+=es[q];n++;ab+=v>up[q]?1:0}});return {n,O:Oo,E,raz:E?Oo/E:NaN,ac:n?100*ab/n:NaN}};
  const H=grp(q=>calor[q]), N=grp(q=>!calor[q]);
  const tot=ob.reduce((x,y)=>x+(y||0),0);
  const critTxt=crit==="ic"?"semanas com pelo menos 3 dias com IC máximo ≥ 36 °C":"semanas com ao menos um dia em NC 2 a NC 5 (estimado retrospectivamente)";
  $("s-kpis").innerHTML=kpiHtml([
    [fn(tot),"óbitos no período exibido"+(nc.some(Boolean)?` (inclui ${fn(nc.filter(Boolean).length)} semana(s) com registro não consolidado${modo().nc?", fora do ajuste":""})`:""),TAG_PER],
    ...rrDoModelo(k,ex),
    [isFinite(H.raz)?fr(H.raz):"–","Razão observado/esperado sem calor (O/E): soma dos óbitos observados dividida pela soma dos valores previstos pelo modelo sem exposição ao calor, nas "+H.n+" "+critTxt+". Comparação descritiva.",TAG_PER,"desc"],
    [isFinite(N.raz)?fr(N.raz):"–","O/E nas "+N.n+" demais semanas do período exibido",TAG_PER,"desc"],
    [isFinite(H.ac)?fn(H.ac)+"%":"–","das semanas de calor com óbitos acima do limite superior da faixa aproximada de variação de 95%",TAG_PER,"desc"],
    [isFinite(N.ac)?fn(N.ac)+"%":"–","das demais semanas acima do limite superior da faixa (a cobertura por período e grupo está no Quadro 5, abaixo da figura)",TAG_PER,"desc"]
  ].concat(B.ncs&&B.bars?[[fn(B.nNC[2]+B.nNC[3]+B.nNC[4]+B.nNC[5]),`dias em NC 2 a NC 5, estimados retrospectivamente pelo painel (NC 4: ${fn(B.nNC[4])}; NC 5: ${fn(B.nNC[5])})`,TAG_PER]]:[]));
  $("i-serie").innerHTML=`<span class="t">Interpretação</span>`+(crit==="no"?`A linha azul indica o número de óbitos esperado sem calor segundo o modelo deste recorte (${compExp()}, com o efeito do calor retirado), e a faixa sombreada é a faixa aproximada de variação de 95% do número de óbitos de uma semana. Pontos escuros marcam as semanas em que o observado superou o limite superior. Para comparar semanas com e sem calor, selecione um critério de calor em Sombrear semanas com.`:
   (H.n&&N.n?`Nas ${H.n} ${critTxt}, foram observados ${fn(H.O)} óbitos, contra ${fn(H.E,0)} esperados sem calor (O/E = ${fr(H.raz)}, ou ${fp(pct(H.raz))} em relação ao esperado sem calor). Nas demais ${N.n} semanas, foram ${fn(N.O)} óbitos contra ${fn(N.E,0)} esperados (O/E = ${fr(N.raz)}). Os óbitos superaram o limite superior da faixa aproximada de variação de 95% em ${fn(H.ac)}% das semanas de calor e em ${fn(N.ac)}% das demais. Esses percentuais descrevem a frequência de semanas acima da faixa no período exibido. A faixa é uma aproximação sem validação como intervalo preditivo, e a cobertura nas demais semanas varia entre períodos (Quadro 5). A fração de óbitos atribuível ao calor é outra medida. ${H.raz>N.raz?"A O/E é maior nas semanas de calor.":"A O/E não é maior nas semanas de calor."} O esperado provém de um modelo ajustado apenas a este recorte, de modo que a O/E varia conforme o recorte. A comparação é descritiva e não inclui intervalo de confiança; a medida de associação é o RR acumulado do modelo, apresentado nos indicadores de RR acima da figura.`:`Há poucas semanas de calor no recorte selecionado para realizar a comparação.`));
  $("s-note").textContent=notaModelo(k,ex)+(modo().covid?" O período da COVID-19 (barra cinza na base) foi retirado do ajuste: nele, o esperado não é traçado e a semana fica fora dos indicadores. As semanas sem nenhum óbito registrado no SIM (faixa cinza clara) também ficam sem esperado.":" Os indicadores excluem o período da COVID-19 (barra cinza na base; o modelo tem um termo próprio para ele) e as semanas sem nenhum óbito registrado no SIM (faixa cinza clara), nas quais o esperado não é traçado.")+(modo().nc?" As semanas de meses com registro não consolidado (hachuradas) foram retiradas do ajuste e ficam sem esperado.":" As semanas de meses com registro não consolidado (hachuradas) entram no modelo e nos indicadores, e o registro nelas pode estar abaixo do real.")+notaClima()+notaAjuste(kd)+notaCausa()+" Semanas de calor: sombreadas em tom escuro. Faixa aproximada de variação de 95%: esperado semanal ± 1,96 × √(φ × soma das variâncias diárias do modelo), com dispersão semanal φ = "+fr(S.phi)+" (estimada nos resíduos semanais). Ela não é o intervalo de confiança do esperado nem um intervalo preditivo completo: deixa de fora a incerteza dos coeficientes e depende de uma aproximação normal (Quadro 5)."+(S.phi>3?" Atenção: φ elevado indica que o modelo não acompanha bem a tendência de longo prazo desta série (por exemplo, por mudança na forma de registrar o local do óbito), o que alarga a faixa.":"")+" A série começa em 2006 (SIM); há dados de clima a partir de abril de 2007, e as semanas sem clima não entram na comparação entre semanas de calor e as demais."+NOTA_BARRAS(B,AL);
  $("s-csv").onclick=()=>{let t=fichaCsv(fichaFig1(kd,ex))+"semana_inicio;ano_epidemiologico;semana_epidemiologica;observado;esperado_sem_calor;faixa_inferior_95;faixa_superior_95;dias_com_ic_maximo_ge_36;dias_nc2_a_nc5_estimados_retrospectivamente;registro_sim\n";const c1=v=>v==null?"":v.toFixed(1).replace(".",",");
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
  const B=barrasClima(idx, false), AL=alinhado(B);
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
    scales:{x:{grid:{display:false},afterFit:AL?eixoX:undefined,ticks:{color:tickc,autoSkip:false,maxRotation:0,callback:function(v){const d=idx[v]==null?"":dias[idx[v]];
        if(!d) return ""; if(d.slice(5)==="01-01") return d.slice(0,4); return (n<=1100&&d.slice(8)==="01")?MESES[+d.slice(5,7)-1]:"" }}},
      y:{beginAtZero:false,min:ymin,grace:"6%",grid:{color:gridc},ticks:{color:tickc},title:{display:true,text:"Óbitos por dia",color:tickc},afterFit:AL?larguraY:undefined},
      yt:AL?{display:false,min:0,max:1}:{display:!!B.bars,position:"right",min:0,max:B.tmax*1.7,grid:{display:false},ticks:{color:tickc,stepSize:10,callback:v=>v<=B.tmax?v:""},title:{display:!!B.bars,text:B.bars?BARRA_NOME[B.bv]+" (°C)":"",color:tickc}}},
    plugins:{legend:{display:false},covid:{cov,inc,nc,sc},barras:B.bars&&!AL?{vals:B.bars,nc:B.modoNC?B.ncs:null,lim:B.lim,cor0:mkCor(cz,.30),cor1:mkCor(la,.62),corL:la,linhas:B.linhas}:null,
      traco:{ob,es,acima:ac,abaixo:ab,lw,al:curto?.85:.6},
      tooltip:{filter:i=>["Observado","Esperado"].includes(i.dataset.label),
        callbacks:{title:it=>{const d=dias[idx[it[0].dataIndex]]; return `${SEMANA[new Date(d+"T12:00:00").getDay()]}, ${dBR(d)}`},
          label:c=>c.dataset.label==="Esperado"?`Esperado sem calor: ${fn(c.parsed.y,1)}`:`Observado: ${fn(c.parsed.y)}`,
          afterBody:it=>{const i=it[0].dataIndex, j=idx[i], v=ob[i], e=es[i], L=[];
            if(v!=null&&e!=null){ const dif=v-e; L.push(`${dif>=0?"Acima":"Abaixo"} do esperado em ${fn(Math.abs(dif),1)} óbitos (O/E = ${fr(v/e)})`); if(v>up[i]) L.push("Acima do limite superior da faixa aproximada de variação de 95%"); else if(v<lo[i]) L.push("Abaixo do limite inferior da faixa aproximada de variação de 95%") }
            else if(inc[i]) L.push("Sem registro de óbitos no SIM (fora do ajuste, sem esperado)");
            if(cov[i]) L.push(linhaCov());
            if(nc[i]) L.push(linhaNC("dia"));
            L.push(cl.ok[j]?`Horas com IC ≥ 36 °C: ${cl.h36[j]==null?"–":fn(cl.h36[j])} · dia com ≥ 4 h de IC ≥ 36 °C: ${EV[j]?"sim":"não"} · dia com exposição em t a t−3: ${XW[j]?"sim":"não"}`:"Sem dado de clima neste dia: exposição não observada (fora do ajuste principal)");
            const h=cd.hi_max[j], hm=cd.hi_med.o[j], tm=cd.t_med.o[j]; if(h!=null) L.push(`IC máximo: ${fn(h,1)} °C · IC médio: ${hm==null?"–":fn(hm,1)} °C · temperatura média do ar: ${tm==null?"–":fn(tm,1)} °C`);
            if(cd.nc[j]!=null) L.push(`NC estimado retrospectivamente pelo painel: NC ${cd.nc[j]}`); return L}}}}},
    plugins:[covPlugin,barPlugin,pontoPlugin]});
  if(AL) painelClima(B,idx.map(j=>dias[j]),chS.options.scales.x.ticks.callback,{titulo:q=>{const d=dias[idx[q]]; return `${SEMANA[new Date(d+"T12:00:00").getDay()]}, ${dBR(d)}`},rotulo:"Valor do dia",extra:q=>cd.nc[idx[q]]!=null&&B.modoNC?`NC estimado retrospectivamente pelo painel: NC ${cd.nc[idx[q]]}`:null});
  $("s-leg").innerHTML=`<span><i class="dt" style="background:${ac}"></i>Observado acima do esperado</span><span><i class="dt" style="background:${ab}"></i>Observado abaixo do esperado</span><span><i class="ln" style="background:${ink};height:3px"></i>Esperado sem calor</span><span><i class="ln" style="background:${cz}"></i>Linha do observado</span>`+
   `<span><i class="dt" style="background:transparent;border:2px solid ${ink};width:9px;height:9px"></i>Dia com exposição em t a t−3 (dia com ≥ 4 h de IC ≥ 36 °C no próprio dia ou em um dos 3 dias anteriores)</span>`+
   (AL?"":legendaBarras(B,cz,la,mkCor,false))+`<span><i style="background:${cz}"></i>${rotCov()}</span>`+(inc.some(Boolean)?`<span><i style="background:${cz};opacity:.3"></i>Sem registro no SIM (fora do ajuste)</span>`:"")+(nc.some(Boolean)?`<span><i style="background:repeating-linear-gradient(135deg,${cz} 0 1.3px,transparent 1.3px 4px)"></i>${rotNC()}</span>`:"")+(sc.some(Boolean)?`<span><i style="background:repeating-linear-gradient(90deg,${css("--azul")} 0 1px,transparent 1px 4px);opacity:.7"></i>Sem dado de clima (exposição não observada)</span>`:"");
  // indicadores: dias com esperado, com clima e fora de COVID; dias de mês não consolidado entram
  const ok=ob.map((v,i)=>v!=null&&es[i]!=null&&!!cl.ok[idx[i]]&&!cov[i]);
  const grp=f=>{let Oo=0,Ee=0,nn=0,ac_=0,sup=0;ob.forEach((v,i)=>{if(ok[i]&&f(i)){Oo+=v;Ee+=es[i];nn++;if(v>es[i])ac_++;if(v>up[i])sup++}});return {n:nn,O:Oo,E:Ee,raz:Ee?Oo/Ee:NaN,ac:nn?100*ac_/nn:NaN,sup:nn?100*sup/nn:NaN}};
  const T=grp(()=>true), H=grp(i=>exp_[i]), N=grp(i=>!exp_[i]);
  $("s-kpis").innerHTML=kpiHtml([
    [fn(ob.reduce((x,v)=>x+(v||0),0)),"óbitos no período exibido"+(nc.some(Boolean)?` (inclui ${fn(nc.filter(Boolean).length)} dia(s) de mês com registro não consolidado${modo().nc?", fora do ajuste":""})`:""),TAG_PER],
    ...rrDoModelo(k,ex),
    [isFinite(H.raz)?fr(H.raz):"–","Razão observado/esperado sem calor (O/E): soma dos óbitos observados dividida pela soma dos valores previstos pelo modelo sem exposição ao calor, nos "+fn(H.n)+" dias com exposição em t a t−3 (dia com ≥ 4 h de IC ≥ 36 °C no próprio dia ou em um dos 3 dias anteriores) do período mostrado. Comparação descritiva.",TAG_PER,"desc"],
    [isFinite(N.raz)?fr(N.raz):"–","O/E nos "+fn(N.n)+" demais dias do período mostrado",TAG_PER,"desc"],
    [isFinite(T.ac)?fn(T.ac)+"%":"–","dos "+fn(T.n)+" dias ficaram acima do esperado; "+(isFinite(T.sup)?fn(T.sup,1)+"% acima do limite superior da faixa aproximada de variação de 95%":""),TAG_PER,"desc"]
  ]);
  $("i-serie").innerHTML=`<span class="t">Interpretação</span>`+(H.n&&N.n?`Cada ponto é um dia: <span style="color:${ac}">vermelho</span> quando o número de óbitos ficou acima do esperado e <span style="color:${ab}">azul</span> quando ficou abaixo; o traço vertical liga o ponto ao esperado do dia. O esperado é o número de óbitos previsto pelo modelo sem calor (${compExp()}), com o efeito do calor (do dia e dos 10 dias anteriores) estimado e depois retirado. Nos dias com exposição em t a t−3 (contorno escuro), o observado fica acima do esperado na medida do efeito estimado para este recorte: ${fn(H.O)} óbitos contra ${fn(H.E,0)} esperados no período mostrado (O/E = ${fr(H.raz)}, ou ${fp(pct(H.raz))} em relação ao esperado sem calor); nos demais ${fn(N.n)} dias, ${fn(N.O)} contra ${fn(N.E,0)} (O/E = ${fr(N.raz)}). Como o modelo usa defasagens de 0 a ${M.lag} dias e o contorno marca apenas a janela de t a t−3, parte do efeito também aparece nos demais dias, e a O/E destes pode ficar um pouco acima de 1. A janela de 0 a ${M.lag} dias é uma decisão do modelo e não vem da janela de até três dias descrita no protocolo municipal. A contagem de um dia isolado varia ao acaso; a interpretação apoia-se na diferença sistemática entre grupos de dias. A janela de t a t−3 inclui o próprio dia e os três anteriores, de modo que um dia com ≥ 4 h de IC ≥ 36 °C aparece ligado a até quatro pontos com contorno escuro.`:`Há poucos dias com exposição em t a t−3 no período mostrado para realizar a comparação.`);
  $("s-note").textContent="Escala diária desde 2006 (há dados de clima a partir de abril de 2007; antes disso, o calor é tratado como ausente). O eixo vertical não parte de zero, para tornar visíveis as diferenças. "+notaModelo(k,ex)+" Faixa aproximada de variação de 95% de um dia: esperado ± 1,96 × raiz da variância do modelo (a posição do observado em relação a ela é indicada ao passar o cursor; a faixa deixa de fora a incerteza dos coeficientes e não foi avaliada quanto à cobertura). "+(modo().covid?"O período da COVID-19 (barra cinza na base) foi retirado do ajuste e fica sem esperado; os dias sem nenhum óbito registrado no SIM (faixa cinza clara) também ficam sem esperado.":"Os indicadores excluem o período da COVID-19 (barra cinza na base) e os dias sem nenhum óbito registrado no SIM (faixa cinza clara), nos quais o esperado não é traçado.")+(modo().nc?" Dias de meses com registro não consolidado (hachurados) foram retirados do ajuste e ficam sem esperado.":" Dias de meses com registro não consolidado (hachurados) entram no modelo e nos indicadores.")+notaClima()+notaAjuste(kd)+notaCausa()+NOTA_BARRAS(B,AL)+
    (n>2200?" Período longo: reduzir o período exibido (ano inicial e ano final) melhora a visualização dos pontos.":"");
  $("s-csv").onclick=()=>{let t=fichaCsv(fichaFig1(kd,ex))+"dia;observado;esperado_sem_calor;faixa_inferior_95;faixa_superior_95;horas_ic_ge_36;dia_com_4h_ic_ge_36;dia_com_exposicao_t_a_t3;ic_maximo_c;ic_medio_c;temperatura_media_ar_c;nc_estimado_retrospectivamente;registro_sim\n";const c1=v=>v==null?"":v.toFixed(1).replace(".",",");
    idx.forEach((j,i)=>{t+=[dias[j],ob[i]??"",c1(es[i]),c1(lo[i]),c1(up[i]),cl.h36[j]??"",EV[j],XW[j],cd.hi_max[j]??"",cd.hi_med.o[j]??"",cd.t_med.o[j]??"",cd.nc[j]??"",inc[i]?"sem_registro":nc[i]?"nao_consolidado":""].join(";")+"\n"});
    baixar(`serie_diaria_${ex}_${key.replace(/[^a-z0-9]+/gi,"_")}${sufixoArq()}.csv`,"﻿"+t)};
}

/* Interface das outras abas (assets/aba_*.js): cada uma se registra em window.PainelAbas e recebe este objeto. */
const P = {$, css, fn, fr, fp, dBR, fillSel, nm, mkCor, M, D, SH, EXP, KEXP, ix, modo, cod:codOpc, eleg, enviar, FAIXA, ouvir:OUV, abas:window.__abas,
  kd:(c,o,k)=>c+"~"+o+"~"+k, cv:(kd,ex)=>(D.cv&&D.cv[ex]&&D.cv[ex][kd])||null, cb:(kd,ex)=>(D.cb&&D.cb[ex]&&D.cb[ex][kd])||null, mapa:kd=>(D.mp&&D.mp[kd])||{}, cid:kd=>(D.cd&&D.cd[kd])||{}, dg:kd=>(D.dg&&D.dg[kd])||{}, pop:()=>POP,
  rrKpi:(kd,ex)=>rrDoModelo(ix.get(kd),ex), notaModelo:(kd,ex,m)=>notaModelo(ix.get(kd),ex,m), modeloTxt:(kd,ex)=>modeloTxt(ix.get(kd),ex),
  texto:{rotCov, rotNC, linhaCov, linhaNC, compExp, notaClima, notaCausa, causaPor:c=>CAUSA_POR[c], causaRot:c=>CAUSA_ROT[c], ficha:fichaEm, recorte:recorteTxt, filtrado:recorteFiltrado, grupos:GRUPOS_TXT}};
if(SH) (window.PainelAbas||[]).forEach(f=>f(P));
if(SH){ registrarShiny();
  const go=()=>{ racaSync(); window.__desenhar() };
  (window.Shiny.shinyapp && window.Shiny.shinyapp.isConnected && window.Shiny.shinyapp.isConnected()) ? go() : window.jQuery(document).one("shiny:connected",go) }
else { racaSync(); window.__desenhar() }
}
})();

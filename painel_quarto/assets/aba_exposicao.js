/* Aba "Exposição-resposta e defasagem" (app Shiny): curvas do modelo de cada recorte.
   Usa o objeto P que figura1.js entrega às abas (window.PainelAbas): filtros de causa e de retirada, pedidos ao servidor e textos comuns. */
(window.PainelAbas = window.PainelAbas || []).push(function(P){
"use strict";
const {$, css, fn, fr, fillSel, nm, mkCor, M, EXP, KEXP} = P;
if(!$("tab-exp")) return;
const RACAS = [{v:"Todas",t:"Todas"},{v:"Branca",t:"Branca (referência)"},{v:"Preta",t:"Preta"},{v:"Parda",t:"Parda"},{v:"PPI",t:"Pretos, pardos e indígenas (PPI)"}];
fillSel($("x-local"), M.locais.map(l=>({v:l,t:nm(l)})), "Todos os locais");
fillSel($("x-faixa"), M.faixas, "Todas as idades");
fillSel($("x-raca"), RACAS, "Todas");
fillSel($("x-exp"), KEXP.map(k=>({v:k,t:EXP[k].nome})), KEXP[0]);
if($("x-r-covid-t") && M.covid) $("x-r-covid-t").textContent = `Período COVID (${P.dBR(M.covid[0])} a ${P.dBR(M.covid[1])})`;

let c1 = null, c2 = null;
const chave = () => $("x-local").value+"|"+$("x-faixa").value+($("x-raca").value!=="Todas"?"|"+$("x-raca").value:"");
function estado(){ const m=P.modo("x"), cod=P.cod("x"), k=chave(), ex=$("x-exp").value; return {m, cod, k, ex, causa:m.causa, kd:P.kd(m.causa,cod,k)} }
const calc = on => { $("x-kpis").classList.toggle("calc",on); document.querySelectorAll("#tab-exp .chartbox").forEach(e=>e.classList.toggle("calc",on)) };
function limpar(){
  ["x-kpis","x-leg","x-leg2","x-interp","x-sub"].forEach(i=>$(i).innerHTML="");
  if(c1){ c1.destroy(); c1=null } if(c2){ c2.destroy(); c2=null }
  $("x-note").textContent = ""; $("x-note2").textContent = "";
}
const kpiHtml = lista => lista.map(([v,l])=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
const picoLag = l => l.rr.reduce((b,v,i)=>v>l.rr[b]?i:b, 0);

function desenharCurvas(){
  if($("tab-exp").classList.contains("hide")) return;
  const r = $("x-raca").value !== "Todas"; if(r) $("x-faixa").value = "Todas as idades"; $("x-faixa").disabled = r;
  $("x-faixa").title = r ? "As séries por raça/cor são calculadas para todas as idades; volte a Todas em raça/cor para escolher uma faixa etária." : "";
  const e = estado(), E = EXP[e.ex], u = E.unidade;
  const rotulo = `local do óbito: ${nm($("x-local").value).toLowerCase()}; faixa etária: ${$("x-faixa").value==="Todas as idades"?"todas as idades":$("x-faixa").value+" anos"}${r?"; raça/cor: "+(({PPI:"pretos, pardos e indígenas"})[$("x-raca").value]||$("x-raca").value.toLowerCase()):""}`;
  if(!P.eleg(e.causa,e.cod).has(e.k)){
    limpar(); calc(false);
    $("x-note").textContent = `Menos de ${M.min_obitos} óbitos ${e.cod!=="000"?"no ajuste ":""}nesta combinação de filtros: modelo não estimado.`;
    return;
  }
  const cv = P.cv(e.kd,e.ex);
  if(!cv){
    calc(true);
    $("x-note").textContent = "Calculando o modelo deste recorte (de 3 a 15 segundos na primeira vez; depois o resultado fica guardado no servidor)…";
    P.enviar(e.k,e.ex,e.causa,e.cod);
    return;
  }
  calc(false);
  $("x-sub").textContent = `Óbitos ${P.texto.causaPor(e.causa)}; ${rotulo}. As curvas vêm do mesmo modelo que gera o esperado sem calor da Figura 1 para este recorte.`;
  const az=css("--azul"), la=css("--laranja"), cz=css("--cinza"), ink=css("--ink"), tickc=css("--mut"), gridc=css("--grid"), card=css("--card");
  const nx = cv.x.length, xmax = cv.x[nx-1], L = cv.lag, cor = [az, la];
  const pts = a => cv.x.map((x,i)=>({x, y:a[i]}));

  // Figura 2: RR acumulado em 0 a 10 dias em função da exposição mantida nos 11 dias
  if(c1) c1.destroy();
  c1 = new Chart($("x-chart"),{type:"line",data:{datasets:[
    {label:"_lo",data:pts(cv.lo),borderWidth:0,pointRadius:0,order:5},
    {label:"IC 95%",data:pts(cv.hi),borderWidth:0,pointRadius:0,fill:"-1",backgroundColor:mkCor(az,.17),order:5},
    {label:"RR acumulado",data:pts(cv.rr),borderColor:az,borderWidth:2,pointRadius:0,pointHoverRadius:0,order:2},
    {label:"RR = 1",data:[{x:0,y:1},{x:xmax,y:1}],borderColor:mkCor(cz,.9),borderDash:[5,4],borderWidth:1,pointRadius:0,order:4},
    {label:"Níveis de referência",data:L.map(l=>({x:l.ref,y:l.ac[l.ac.length-1]})),showLine:false,pointRadius:6,pointBackgroundColor:cor,pointBorderColor:card,pointBorderWidth:2,order:1}
  ]},options:{responsive:true,maintainAspectRatio:false,animation:false,parsing:false,interaction:{mode:"nearest",axis:"x",intersect:false},
    scales:{x:{type:"linear",min:0,max:xmax,grid:{display:false},ticks:{color:tickc},title:{display:true,text:`${E.nome}, mantida em todos os ${M.lag+1} dias (${u})`,color:tickc}},
            y:{grid:{color:gridc},ticks:{color:tickc,callback:v=>fr(v)},title:{display:true,text:`RR acumulado em 0 a ${M.lag} dias`,color:tickc}}},
    plugins:{legend:{display:false},tooltip:{filter:i=>i.dataset.label==="RR acumulado",
      callbacks:{title:it=>`${fn(it[0].parsed.x,1)} ${u} por dia`, label:c=>{ const i=c.dataIndex; return `RR ${fr(cv.rr[i])} (IC 95%: ${fr(cv.lo[i])} a ${fr(cv.hi[i])})` }}}}}});
  $("x-leg").innerHTML = `<span><i class="ln" style="background:${az};height:3px"></i>RR acumulado</span><span><i style="background:${mkCor(az,.17)}"></i>IC 95%</span>`+
    L.map((l,j)=>`<span><i class="dt" style="background:${cor[j]}"></i>${fn(l.ref)} ${u} por dia</span>`).join("");

  // Figura 3: RR por defasagem, ou acumulado até cada defasagem, nos dois níveis de referência
  const tipo = $("x-lag").value, campo = tipo==="ac" ? ["ac","aclo","achi"] : ["rr","lo","hi"], lags = [...Array(M.lag+1).keys()];
  const ds = [];
  L.forEach((l,j)=>{
    ds.push({label:"_lo"+j,data:l[campo[1]],borderWidth:0,pointRadius:0,order:5});
    ds.push({label:"IC"+j,data:l[campo[2]],borderWidth:0,pointRadius:0,fill:"-1",backgroundColor:mkCor(cor[j],.15),order:5});
    ds.push({label:`${fn(l.ref)} ${u} por dia`,data:l[campo[0]],borderColor:cor[j],borderWidth:2,pointRadius:3,pointBackgroundColor:cor[j],pointBorderColor:card,pointBorderWidth:1,order:2});
  });
  ds.push({label:"RR = 1",data:lags.map(()=>1),borderColor:mkCor(cz,.9),borderDash:[5,4],borderWidth:1,pointRadius:0,order:4});
  if(c2) c2.destroy();
  c2 = new Chart($("x-chart2"),{type:"line",data:{labels:lags,datasets:ds},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:"index",intersect:false},
    scales:{x:{grid:{display:false},ticks:{color:tickc},title:{display:true,text:tipo==="ac"?"Defasagem final do acúmulo (dias após a exposição)":"Defasagem (dias após a exposição)",color:tickc}},
            y:{grid:{color:gridc},ticks:{color:tickc,callback:v=>fr(v)},title:{display:true,text:tipo==="ac"?"RR acumulado até a defasagem":"RR em cada defasagem",color:tickc}}},
    plugins:{legend:{display:false},tooltip:{filter:i=>/por dia$/.test(i.dataset.label),
      callbacks:{title:it=>`Defasagem de ${it[0].label} dia(s)`, label:c=>{ const l=L[Math.floor(c.datasetIndex/3)], i=c.dataIndex; return `${c.dataset.label}: RR ${fr(l[campo[0]][i])} (IC 95%: ${fr(l[campo[1]][i])} a ${fr(l[campo[2]][i])})` }}}}}});
  $("x-leg2").innerHTML = L.map((l,j)=>`<span><i class="ln" style="background:${cor[j]};height:3px"></i>${fn(l.ref)} ${u} por dia</span><span><i style="background:${mkCor(cor[j],.15)}"></i>IC 95%</span>`).join("");

  // quadros e textos
  const pico = L.map(picoLag), fim = l => l.ac[l.ac.length-1];
  $("x-kpis").innerHTML = kpiHtml([...P.rrKpi(e.kd,e.ex),
    ...L.map((l,j)=>[`${pico[j]} dia(s)`, `defasagem de maior RR com ${fn(l.ref)} ${u} por dia (RR ${fr(l.rr[pico[j]])})`]),
    [P.modeloTxt(e.kd,e.ex).replace(/ \(.*$/,""), "família do modelo (os parâmetros estão na nota abaixo das figuras)"]]);
  const curvaTxt = e.ex==="horas"
    ? "Com 1 grau de liberdade na exposição (spline natural), o logaritmo do RR cresce em linha reta com a exposição por construção, de modo que a curva não detecta limiar."
    : "O HAAT usa spline penalizado com 15 graus de liberdade, o que permite curvatura, mas as extremidades têm poucos dias e intervalos largos.";
  $("x-note").textContent = `RR acumulado em 0 a ${M.lag} dias para uma exposição constante, mantida em todos os ${M.lag+1} dias, em relação a nenhuma exposição. A faixa é o intervalo de confiança de 95% a partir dos coeficientes da cross-basis e da sua matriz de covariância. A grade vai até ${fn(xmax)} ${u} por dia, o percentil 99 dos dias com exposição; acima disso há poucos dias. ${curvaTxt}`;
  $("x-note2").textContent = `${tipo==="ac"?"RR acumulado da defasagem 0 até cada defasagem":"RR da exposição ocorrida l dias antes do óbito, para cada defasagem l"}, com a exposição de referência mantida nos ${M.lag+1} dias. A resposta à defasagem é um spline natural com 3 graus de liberdade. `+
    P.notaModelo(e.kd,e.ex,e.m)+P.texto.notaClima(e.m)+P.texto.notaCausa(e.m);
  const fmtRR = (x,lo,hi) => `${fr(x)} (IC 95%: ${fr(lo)} a ${fr(hi)})`;
  const partes = L.map((l,j)=>{ const i=l.ac.length-1, sig = l.aclo[i]>1 ? "o intervalo fica acima de 1" : l.achi[i]<1 ? "o intervalo fica abaixo de 1" : "o intervalo inclui 1";
    return `com ${fn(l.ref)} ${u} por dia, o RR acumulado em 0 a ${M.lag} dias é ${fmtRR(l.ac[i],l.aclo[i],l.achi[i])}, isto é, ${P.fp((l.ac[i]-1)*100)} no risco diário de óbito (${sig}); o maior RR por defasagem ocorre em ${pico[j]} dia(s), com ${fr(l.rr[pico[j]])}` });
  const tardio = L.some(l=>l.hi.some(v=>v<1));
  $("x-interp").innerHTML = `<span class="t">Interpretação</span>Neste recorte, ${partes.join("; ")}. `+
    `O RR acumulado soma o efeito das exposições do dia e dos ${M.lag} dias anteriores e, por isso, resume o risco de viver o período inteiro nesse nível de calor. `+
    (tardio?`Há defasagens em que o intervalo de confiança fica inteiro abaixo de 1. Isso pode refletir antecipação de óbitos de pessoas frágeis ou variação aleatória, e o modelo não separa as duas explicações. `:"")+
    `As curvas descrevem associação em dados agregados, sem controle de fatores individuais.`;
}

// ---------------------------------------------------------------- Figura 4: horas por dia x limiar do índice de calor
// Cada célula é um modelo próprio (R/modelo_joao.R, ajustar_mapa_limiar). O navegador pede uma coluna (limiar K) por vez, no máximo MAX_VOO ao mesmo
// tempo, e redesenha a tabela a cada coluna recebida. Primeiro o limiar usual de 36 °C, depois os demais.
const LIM = [36,32,33,34,35,37,38,39,40,41,42,43,44], LIM_ORD = [...LIM].sort((a,b)=>a-b), MAX_VOO = 2, ESPERA_MAX = 180000;
const voo = new Map(), falhou = new Map();                       // id da coluna -> instante do pedido | id da coluna -> mensagem de erro
const idM = (kd,K) => kd+"|"+K, eMapa = ex => /^mapa\d+$/.test(ex);
function bombear(e){
  const agora = Date.now(); voo.forEach((t,id)=>{ if(agora-t>ESPERA_MAX) voo.delete(id) });
  const prontos = P.mapa(e.kd);
  for(const K of LIM){
    if(voo.size>=MAX_VOO) break;
    const id = idM(e.kd,K);
    if(prontos[K] || voo.has(id) || falhou.has(id)) continue;
    voo.set(id,agora); P.enviar(e.k,"mapa"+K,e.causa,e.cod);
  }
}
const pctRR = r => (r-1)*100;
function mapa(){
  if($("tab-exp").classList.contains("hide")) return;
  const e = estado(), tab = $("x-hm"), prog = $("x-hm-prog"), nota = $("x-hm-note"), it = $("x-hm-interp");
  if(!P.eleg(e.causa,e.cod).has(e.k)){
    tab.innerHTML = ""; prog.textContent = ""; it.innerHTML = "";
    nota.textContent = `Menos de ${M.min_obitos} óbitos ${e.cod!=="000"?"no ajuste ":""}nesta combinação de filtros: modelo não estimado.`;
    return;
  }
  const curvasProntas = !!P.cv(e.kd,e.ex);
  if(curvasProntas) bombear(e);                                    // o mapa só começa depois das Figuras 2 e 3 do mesmo recorte, para que o servidor as atenda primeiro
  const col = P.mapa(e.kd), feitas = LIM_ORD.filter(K=>col[K]).length, erros = LIM_ORD.filter(K=>falhou.has(idM(e.kd,K)));
  const so = $("x-hm-sig").checked;
  prog.innerHTML = erros.length && [...falhou.values()].includes("dados_mudaram")
    ? 'Os dados foram atualizados no servidor. <a href="">Recarregue a página</a> para ver a versão nova.'
    : !curvasProntas && feitas<LIM.length
      ? "O mapa começa a ser calculado depois das Figuras 2 e 3 deste recorte."
    : feitas<LIM.length
      ? `Calculando as colunas do mapa: ${feitas} de ${LIM.length}${erros.length?" ("+erros.length+" sem estimativa por erro do servidor)":""}. Na primeira vez cada coluna leva cerca de 15 segundos; depois o resultado fica guardado no servidor.`
      : "";
  const H = (LIM_ORD.map(K=>col[K]).find(Boolean)||{h:[1,2,3,4,6,8,10,12]}).h;
  let s = "<tr><th>H \\ K (°C)</th>"+LIM_ORD.map(K=>`<th>${K}</th>`).join("")+"</tr>";
  H.forEach((h,i)=>{
    s += `<tr><td class="rl" style="cursor:default">≥ ${h} h</td>`;
    LIM_ORD.forEach(K=>{
      const c = col[K];
      if(!c){ const f = falhou.has(idM(e.kd,K)); s += `<td style="color:var(--mut)" title="${f?"não foi possível estimar esta coluna":"calculando"}">${f?"×":"…"}</td>`; return }
      const rr=c.rr[i], lo=c.lo[i], hi=c.hi[i], nd=c.nd[i];
      if(rr==null){ s += `<td style="color:var(--mut)" title="${nd<15?"menos de 15 dias expostos no ajuste":"célula não estimada (poucos dias sem exposição ou falha do ajuste)"}">–</td>`; return }
      const sig = lo>1 || hi<1, v = pctRR(rr), al = Math.min(Math.abs(v)/25,1)*.75;
      const cor = (so&&!sig) ? "transparent" : (v>=0 ? `rgba(181,84,28,${al})` : `rgba(22,65,145,${al})`);
      s += `<td style="background:${cor};${sig?"font-weight:700":"color:var(--mut)"}" title="Índice de calor ≥ ${K} °C por ≥ ${h} h/dia\nRR ${fr(rr)} (IC 95%: ${fr(lo)} a ${fr(hi)})\n${fn(nd)} dias expostos">${fr(rr)}</td>`;
    });
    s += "</tr>";
  });
  tab.innerHTML = s;
  nota.textContent = `Linhas: número mínimo de horas no dia com índice de calor ≥ K (H). Colunas: limiar K (°C). Cada célula é um modelo próprio, com o mesmo GAM do modelo de referência `+
    `(binomial negativa, spline do tempo, ciclo anual e termo do período COVID, defasagem de 0 a ${M.lag} dias pela cross-basis do dlnm), em que a exposição é o dia ter pelo menos H horas com índice de calor ≥ K. `+
    `O RR é o acumulado em 0 a ${M.lag} dias para a condição mantida em todos os ${M.lag+1} dias, em relação a nenhum dia com a condição, com IC 95% a partir da matriz de covariância dos coeficientes. `+
    `Células com menos de 15 dias expostos, ou com menos de 30 dias sem exposição, no ajuste não são estimadas (–). Em negrito, RR com IC 95% que não inclui 1. `+
    P.texto.notaClima(e.m)+P.texto.notaCausa(e.m);
  if(feitas<LIM.length){ it.innerHTML = `<span class="t">Interpretação</span>O texto fica disponível quando as ${LIM.length} colunas estiverem calculadas.`; return }
  const cel = [];
  LIM_ORD.forEach(K=>{ const c=col[K]; c.h.forEach((h,i)=>{ if(c.rr[i]!=null) cel.push({K,h,rr:c.rr[i],lo:c.lo[i],hi:c.hi[i],nd:c.nd[i]}) }) });
  if(!cel.length){ it.innerHTML = `<span class="t">Interpretação</span>Nenhuma combinação tem dias expostos suficientes neste recorte.`; return }
  const sg = cel.filter(c=>c.lo>1), dn = cel.filter(c=>c.hi<1), mx = cel.reduce((a,b)=>b.rr>a.rr?b:a);
  const base = cel.find(c=>c.K===36&&c.h===1), a = cel.find(c=>c.K===32&&c.h===1), b = cel.find(c=>c.K===40&&c.h===1);
  const ic = c => `${fr(c.rr)} (IC 95%: ${fr(c.lo)} a ${fr(c.hi)}; ${fn(c.nd)} dias expostos)`;
  it.innerHTML = `<span class="t">Interpretação</span>Das <b>${cel.length}</b> combinações estimadas, <b>${sg.length}</b> têm RR acima de 1 com IC 95% que não inclui 1 e <b>${dn.length}</b> têm RR abaixo de 1 com IC 95% que não inclui 1. `+
    (base?`Com o limiar usual de 36 °C e pelo menos 1 hora no dia, RR = <b>${ic(base)}</b>. `:"")+
    `O maior valor da tabela é RR = <b>${ic(mx)}</b>, com índice de calor ≥ ${mx.K} °C por ≥ ${mx.h} h. O máximo de muitas células tende a superestimar o efeito, e as células com poucos dias expostos têm intervalos largos. `+
    (a&&b?`Ao subir o limiar de 32 para 40 °C (≥ 1 h), o RR passa de ${fr(a.rr)} para ${fr(b.rr)}${b.rr>a.rr?", no sentido de risco maior com calor mais intenso; esse gradiente favorece a associação, e os dados agregados não permitem inferir causalidade. ":", sem gradiente crescente. "}`:"")+
    `As células são aninhadas, pois um dia com mais horas também entra nas definições com menos horas, e não passaram por correção para comparações múltiplas. O padrão geral da tabela é mais informativo do que uma célula isolada. `+
    `O RR de cada célula descreve a associação em dados agregados, sem controle de fatores individuais.`;
}

function desenhar(){ desenharCurvas(); mapa() }                    // as Figuras 2 e 3 são pedidas primeiro: o servidor as atende antes das colunas do mapa

P.ouvir.seg.push((kd,ex)=>{
  if(eMapa(ex)){ voo.delete(idM(kd,+ex.slice(4))); mapa(); return }
  const e=estado(); if(kd===e.kd && ex===e.ex){ desenharCurvas(); mapa() }
});
P.ouvir.erro.push(msg=>{
  if(eMapa(msg.ex)){
    if(msg.pop!==P.pop()) return;
    const id = idM(P.kd(msg.causa,msg.opc,msg.key), +msg.ex.slice(4));
    voo.delete(id); falhou.set(id, msg.codigo==="dados_mudaram" ? "dados_mudaram" : String(msg.mensagem||"erro"));
    mapa(); return;
  }
  if($("tab-exp").classList.contains("hide")) return;
  const e=estado(); if(msg.pop!==P.pop() || msg.key!==e.k || msg.ex!==e.ex || msg.causa!==e.causa || msg.opc!==e.cod) return;
  calc(false);
  $("x-note").innerHTML = msg.codigo==="dados_mudaram"
    ? 'Os dados foram atualizados no servidor. <a href="">Recarregue a página</a> para ver a versão nova.'
    : "Não foi possível ajustar o modelo deste recorte: "+String(msg.mensagem||"erro desconhecido").replace(/[<>&]/g,"");
});
P.ouvir.base.push(()=>{ voo.clear(); falhou.clear(); desenhar() });
["x-local","x-faixa","x-raca","x-exp","x-lag","x-causa","x-r-covid","x-r-nc","x-r-clima","x-hm-sig"].forEach(i=>{ const el=$(i); if(el) el.onchange=desenhar });
P.abas.exp = desenhar;
});

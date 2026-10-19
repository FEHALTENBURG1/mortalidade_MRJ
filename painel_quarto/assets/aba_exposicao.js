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

function desenhar(){
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

P.ouvir.seg.push((kd,ex)=>{ const e=estado(); if(kd===e.kd && ex===e.ex) desenhar() });
P.ouvir.erro.push(msg=>{
  if($("tab-exp").classList.contains("hide")) return;
  const e=estado(); if(msg.pop!==P.pop() || msg.key!==e.k || msg.ex!==e.ex || msg.causa!==e.causa || msg.opc!==e.cod) return;
  calc(false);
  $("x-note").innerHTML = msg.codigo==="dados_mudaram"
    ? 'Os dados foram atualizados no servidor. <a href="">Recarregue a página</a> para ver a versão nova.'
    : "Não foi possível ajustar o modelo deste recorte: "+String(msg.mensagem||"erro desconhecido").replace(/[<>&]/g,"");
});
P.ouvir.base.push(desenhar);
["x-local","x-faixa","x-raca","x-exp","x-lag","x-causa","x-r-covid","x-r-nc","x-r-clima"].forEach(i=>{ const el=$(i); if(el) el.onchange=desenhar });
P.abas.exp = desenhar;
});

/* Aba "Causas específicas (CID-10)" (app Shiny): RR em dias de calor para cada causa básica de 3 caracteres do recorte, com correção de Benjamini e Hochberg.
   Cada causa é um modelo próprio (o modelo de referência, R/servico.R: ajustar_pedido_cid). O navegador pede primeiro a lista de causas do recorte ("cidlista")
   e depois uma causa por vez ("cid_<CID>_<medida>"), no máximo MAX_VOO ao mesmo tempo; a figura se completa causa a causa. A série semanal de uma causa
   ("cidsem_<CID>_<medida>") só é pedida quando o usuário a escolhe. */
(window.PainelAbas = window.PainelAbas || []).push(function(P){
"use strict";
const {$, css, fn, fr, fp, dBR, fillSel, nm, mkCor, M, D, EXP, KEXP, FAIXA} = P;
if(!$("tab-cid")) return;
const RACAS = [{v:"Todas",t:"Todas"},{v:"Branca",t:"Branca (referência)"},{v:"Preta",t:"Preta"},{v:"Parda",t:"Parda"},{v:"PPI",t:"Pretos, pardos e indígenas (PPI)"}];
const CAPS = [["A","A-B Algumas doenças infecciosas e parasitárias"],["C","C-D48 Neoplasias"],["D","D50-D89 Sangue e imunitárias"],["E","E Endócrinas, nutricionais e metabólicas"],
  ["F","F Transtornos mentais e comportamentais"],["G","G Sistema nervoso"],["H","H Olho, ouvido"],["I","I Aparelho circulatório"],["J","J Aparelho respiratório"],
  ["K","K Aparelho digestivo"],["L","L Pele"],["M","M Osteomuscular"],["N","N Geniturinário"],["O","O Gravidez, parto e puerpério"],["P","P Afecções perinatais"],
  ["Q","Q Malformações congênitas"],["R","R Sintomas e causas mal definidas"],["X","V-Y Causas externas"]];
const capOf = c => { const l=c[0]; if(l==="B") return "A"; if(l==="D") return +c.slice(1)<50 ? "C" : "D"; if("VWXY".includes(l)) return "X"; return l };
// Causas selecionadas do referencial teórico (Morais et al.): os 15 grupos de causas de 00_aux_functions.R do repositório do artigo, escritos aqui como faixas
// de códigos de 3 caracteres [letra, primeiro número, último número]. A lista fica fixa e não depende dos resultados do painel.
const GRUPOS_REF = [
  ["Influenza e pneumonia", [["J",9,9],["J",12,18]]],
  ["Doenças respiratórias crônicas inferiores", [["J",40,47]]],
  ["Outras doenças respiratórias", [["J",0,6],["J",20,39],["J",60,70],["J",80,86],["J",90,99],["R",9,9],["U",4,4]]],
  ["Doenças hipertensivas", [["I",10,15]]],
  ["Doenças isquêmicas do coração", [["I",20,25]]],
  ["Insuficiência cardíaca", [["I",50,50]]],
  ["Doenças cerebrovasculares", [["I",60,69]]],
  ["Outras doenças do aparelho circulatório", [["I",0,9],["I",26,49],["I",51,52],["I",70,99]]],
  ["Neoplasias malignas", [["C",0,97]]],
  ["Alzheimer e demência", [["G",30,31],["F",1,1],["F",3,3]]],
  ["Diabetes", [["E",10,14]]],
  ["Insuficiência renal", [["N",17,19]]],
  ["Sepse", [["A",40,41]]],
  ["Infecção do trato urinário", [["N",39,39]]],
  ["Causas mal definidas", [["R",0,99]]]
];
const grupoRef = c => { const n = +c.slice(1,3); const g = GRUPOS_REF.find(([,fx])=>fx.some(([l,a,b])=>c[0]===l && n>=a && n<=b)); return g ? g[0] : null };
const aPriori = c => grupoRef(c) !== null;
const minus1 = t => t[0].toLowerCase()+t.slice(1);                // só a primeira letra: o °C da unidade não pode virar °c
const NOME = c => ((M.cid_nomes||{})[c]) || "";
const MAX_VOO = 2, ESPERA_MAX = 240000;

fillSel($("k-local"), M.locais.map(l=>({v:l,t:nm(l)})), "Todos os locais");
fillSel($("k-faixa"), M.faixas, "Todas as idades");
fillSel($("k-raca"), RACAS, "Todas");
fillSel($("k-exp"), KEXP.map(k=>({v:k,t:EXP[k].nome})), KEXP[0]);
fillSel($("k-cap"), [{v:"all",t:"Todos os capítulos"}, ...CAPS.map(([v,t])=>({v,t}))], "all");
if($("k-r-covid-t") && M.covid) $("k-r-covid-t").textContent = `Período COVID (${dBR(M.covid[0])} a ${dBR(M.covid[1])})`;
function niveis(){
  const E = EXP[$("k-exp").value], atual = $("k-nivel").value;
  fillSel($("k-nivel"), E.ref.map((r,i)=>({v:String(i),t:`${fn(r)} ${E.unidade} por dia`})), atual && +atual < E.ref.length ? atual : "0");
}
niveis();

let grafico = null, sel = null, timer = null;
const voo = new Map(), falhou = new Map();                       // id (kd|pedido) -> instante do pedido | id -> mensagem de erro
const idK = (kd,ex) => kd+"|"+ex, eCid = ex => /^cid/.test(ex);
const exCid = (c,medida) => `cid_${c}_${medida}`, exSem = (c,medida) => `cidsem_${c}_${medida}`;
const chave = () => $("k-local").value+"|"+$("k-faixa").value+($("k-raca").value!=="Todas"?"|"+$("k-raca").value:"");
function estado(){ const m=P.modo("k"), cod=P.cod("k"), k=chave(); return {m, cod, k, causa:m.causa, kd:P.kd(m.causa,cod,k), medida:$("k-exp").value, nivel:+$("k-nivel").value} }
const agendar = () => { clearTimeout(timer); timer = setTimeout(desenhar, 120) };
const fmtP = q => q==null ? "…" : q<0.001 ? "<0,001" : q.toFixed(3).replace(".",",");
const bh = p => { const n=p.length, o=p.map((v,i)=>[v,i]).sort((a,b)=>a[0]-b[0]), q=Array(n); let m=1; for(let r=n-1;r>=0;r--){ m=Math.min(m,o[r][0]*n/(r+1)); q[o[r][1]]=Math.min(m,1) } return q };

// manda o pedido se ainda não foi feito e há vaga (forcar = ignora o limite, para o que o usuário acabou de escolher)
function enviarUm(e, ex, forcar){
  const id = idK(e.kd,ex);
  if(P.cid(e.kd)[ex] || voo.has(id) || falhou.has(id)) return true;
  if(!forcar && voo.size>=MAX_VOO) return false;
  voo.set(id,Date.now()); P.enviar(e.k,ex,e.causa,e.cod); return true;
}
function bombear(e, exs){
  const agora = Date.now(); voo.forEach((t,id)=>{ if(agora-t>ESPERA_MAX) voo.delete(id) });
  for(const ex of exs) if(!enviarUm(e,ex,false)) break;
}

function limpar(){
  ["k-fig","k-interp","k-sub","k-interp2","k-leg"].forEach(i=>$(i).innerHTML="");
  $("k-prog").textContent = ""; $("k-note").textContent = ""; $("k-note2").textContent = "";
  if(grafico){ grafico.destroy(); grafico = null }
}

function desenhar(){
  if($("tab-cid").classList.contains("hide")) return;
  const r = $("k-raca").value !== "Todas"; if(r) $("k-faixa").value = "Todas as idades"; $("k-faixa").disabled = r;
  $("k-faixa").title = r ? "As séries por raça/cor são calculadas para todas as idades; volte a Todas em raça/cor para escolher uma faixa etária." : "";
  const e = estado(), E = EXP[e.medida], got = P.cid(e.kd);
  const rotulo = `local do óbito: ${nm($("k-local").value).toLowerCase()}; faixa etária: ${$("k-faixa").value==="Todas as idades"?"todas as idades":$("k-faixa").value+" anos"}${r?"; raça/cor: "+(({PPI:"pretos, pardos e indígenas"})[$("k-raca").value]||$("k-raca").value.toLowerCase()):""}`;
  if(!P.eleg(e.causa,e.cod).has(e.k)){
    limpar(); $("k-note").textContent = `Menos de ${M.min_obitos} óbitos ${e.cod!=="000"?"no ajuste ":""}nesta combinação de filtros: modelo não estimado.`;
    return;
  }
  $("k-sub").textContent = `Óbitos ${P.texto.causaPor(e.causa)}; ${rotulo}. Cada causa básica com pelo menos ${fn(M.cid_min)} óbitos nos dias do ajuste é avaliada em um modelo próprio.`;
  const lista = got.cidlista;
  if(!lista){
    const f = falhou.get(idK(e.kd,"cidlista"));
    $("k-fig").innerHTML = ""; $("k-interp").innerHTML = ""; $("k-note").textContent = "";
    $("k-prog").textContent = f ? "Não foi possível obter as causas deste recorte: "+String(f).replace(/[<>&]/g,"") : "Obtendo a lista de causas deste recorte…";
    if(!f) enviarUm(e,"cidlista",true);
    return;
  }
  const conj = $("k-conj").value, cap = $("k-cap").value;
  const fam = lista.cid.filter(c=>(conj==="todas"||aPriori(c)) && (cap==="all"||capOf(c)===cap));
  $("k-prog").textContent = "";
  if(!fam.length){
    $("k-fig").innerHTML = ""; $("k-interp").innerHTML = "";
    $("k-note").textContent = `Nenhuma causa tem pelo menos ${fn(M.cid_min)} óbitos nos dias do ajuste com esta combinação de recorte, conjunto e capítulo.`;
    return;
  }
  bombear(e, fam.map(c=>exCid(c,e.medida)));
  const res = [], erros = [];
  fam.forEach((c,i)=>{ const x = got[exCid(c,e.medida)]; if(x) res.push({c, n:x.n, rr:x.rr[e.nivel], lo:x.lo[e.nivel], hi:x.hi[e.nivel], p:x.p[e.nivel]}); else if(falhou.has(idK(e.kd,exCid(c,e.medida)))) erros.push(c) });
  const completo = res.length + erros.length === fam.length;
  if(completo && res.length){ const q = bh(res.map(x=>x.p)); res.forEach((x,i)=>x.q = q[i]) }
  const dados = res.length;
  const sg = completo ? res.filter(x=>x.q<0.05) : [];
  const alvo = completo ? ($("k-todos").checked ? res : sg) : res;
  const nivelTxt = `${fn(E.ref[e.nivel])} ${E.unidade} por dia`;
  $("k-prog").textContent = completo
    ? (erros.length ? `${erros.length} causa(s) sem estimativa por erro do servidor: ${erros.join(", ")}.` : "")
    : `Avaliando as causas: ${res.length+erros.length} de ${fam.length}. Na primeira vez cada causa leva de 3 a 10 segundos; depois o resultado fica guardado no servidor. A correção para comparações múltiplas e o filtro de significância aparecem quando todas estiverem calculadas.`;
  $("k-h2").textContent = `Causas básicas (CID-10, 3 caracteres) com RR diferente de 1 com ${nivelTxt}`;
  floresta(e, alvo, completo, fam.length);

  // nota e interpretação
  const nomeMedida = minus1(E.nome);
  $("k-note").textContent = `RR acumulado em 0 a ${M.lag} dias com a exposição (${nomeMedida}) mantida em ${nivelTxt} em todos os ${M.lag+1} dias, em relação a nenhuma exposição, estimado em um modelo próprio de cada causa `+
    `(binomial negativa, spline do tempo, ciclo anual e termo do período COVID, defasagem pela cross-basis do dlnm). O IC 95% e o valor de p vêm da matriz de covariância dos coeficientes. `+
    `O valor q é o de Benjamini e Hochberg para a taxa de falsas descobertas, calculado entre as ${fam.length} causas do conjunto e do capítulo escolhidos; q < 0,05 define as causas destacadas. `+
    `Causas com menos de ${fn(M.cid_min)} óbitos nos dias do ajuste não são avaliadas. Ordenação por RR.`+P.texto.notaClima(e.m)+P.texto.notaCausa(e.m);
  const ic = x => `${fr(x.rr)}; IC 95%: ${fr(x.lo)} a ${fr(x.hi)}`;
  if(!completo){ $("k-interp").innerHTML = `<span class="t">Interpretação</span>O texto fica disponível quando as ${fam.length} causas estiverem calculadas.`; }
  else if(!dados){ $("k-interp").innerHTML = `<span class="t">Interpretação</span>Nenhuma causa pôde ser estimada neste recorte.`; }
  else {
    const up = sg.filter(x=>x.rr>1).sort((a,b)=>b.rr-a.rr), dw = sg.filter(x=>x.rr<1).sort((a,b)=>a.rr-b.rr);
    const item = x => `<b>${x.c}</b> ${NOME(x.c)} (RR ${ic(x)})`;
    $("k-interp").innerHTML = `<span class="t">Interpretação</span>Com ${nivelTxt}, <b>${up.length}</b> das ${res.length} causas avaliadas têm RR acima de 1 e <b>${dw.length}</b> têm RR abaixo de 1 depois da correção de Benjamini e Hochberg (q < 0,05). `+
      (up.length ? `As de maior RR são ${up.slice(0,4).map(item).join("; ")}. ` : "")+
      (dw.length ? `RR abaixo de 1 (por exemplo ${dw.slice(0,2).map(x=>x.c).join(", ")}) pode refletir antecipação de óbitos, mudanças de classificação ou variação aleatória, e o modelo não separa essas explicações. ` : "")+
      `As demais ${res.length-sg.length} causas não diferem de 1 após a correção${$("k-todos").checked ? " e aparecem em cinza" : " e ficam fora da figura"}. `+
            `Os RR descrevem associação em dados agregados, sem controle de fatores individuais, e cada causa tem poucos óbitos por dia, de modo que os intervalos são largos nas causas menos frequentes.`;
  }
  // série semanal da causa escolhida
  if(sel && !fam.includes(sel)) sel = null;
  serie(e, completo ? padrao(sg) : null);
}
// causa mostrada na Figura 5b quando o usuário ainda não escolheu: a de maior RR acima de 1 entre as destacadas, ou a de menor q
const padrao = sg => { const a = sg.filter(x=>x.rr>1).sort((x,y)=>y.rr-x.rr)[0] || [...sg].sort((x,y)=>x.q-y.q)[0]; return a ? a.c : null };

// ---------------------------------------------------------------- Figura 5: floresta
function floresta(e, R, completo, total){
  const rows = [...R].sort((a,b)=>b.rr-a.rr);
  const W=1040, L=420, Rm=250, rh=26, H=40+Math.max(rows.length,1)*rh+30;
  const vals = rows.flatMap(r=>[r.lo,r.hi]);
  const mn = Math.min(0.9,...vals)-.01, mx = Math.max(1.1,...vals)+.01, X = v=>L+(v-mn)/(mx-mn)*(W-L-Rm);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="RR por causa básica">`;
  const passo = (mx-mn)>1 ? .25 : (mx-mn)>.5 ? .1 : .05;
  for(let v=Math.ceil(mn/passo)*passo; v<=mx; v+=passo) s += `<line x1="${X(v)}" x2="${X(v)}" y1="26" y2="${H-26}" stroke="${css("--grid")}"/><text class="m" x="${X(v)}" y="${H-10}" text-anchor="middle">${fr(v)}</text>`;
  s += `<line x1="${X(1)}" x2="${X(1)}" y1="26" y2="${H-26}" stroke="${css("--mut")}"/>`;
  s += `<text class="m" x="8" y="16" style="font-weight:700">Causa (CID-10)</text><text class="m" x="${W-Rm+12}" y="16" style="font-weight:700">RR (IC 95%)</text><text class="m" x="${W-62}" y="16" text-anchor="end" style="font-weight:700">q</text><text class="m" x="${W-8}" y="16" text-anchor="end" style="font-weight:700">Óbitos</text>`;
  if(!rows.length) s += `<text class="m" x="${L}" y="60">${completo ? "Nenhuma causa difere do esperado com esta combinação." : "Aguardando as primeiras causas…"}</text>`;
  rows.forEach((r,i)=>{
    const y = 40+i*rh+rh/2, sig = completo && r.q<0.05, c = !sig ? css("--cinza") : r.rr>1 ? css("--laranja") : css("--azul"), nome = NOME(r.c).slice(0,62);
    if(i%2===0) s += `<rect x="0" y="${y-rh/2}" width="${W}" height="${rh}" fill="${css("--faixa")}"/>`;
    if(r.c===sel) s += `<rect x="1" y="${y-rh/2+1}" width="${W-2}" height="${rh-2}" fill="none" stroke="${css("--azul")}" stroke-width="1.5" rx="3"/>`;
    s += `<text x="8" y="${y+4}"><tspan style="font-weight:650">${r.c}</tspan> <tspan class="m">${nome}</tspan></text>`;
    s += `<g data-c="${r.c}" style="cursor:pointer"><title>${r.c} ${NOME(r.c)}\n${grupoRef(r.c)?"Grupo do referencial: "+grupoRef(r.c)+"\n":""}RR ${fr(r.rr)} (IC 95%: ${fr(r.lo)} a ${fr(r.hi)})\n${completo?"q = "+fmtP(r.q)+" · ":""}p = ${fmtP(r.p)}\n${fn(r.n)} óbitos nos dias do ajuste · clique para ver a série semanal</title>`+
         `<rect x="${X(mn)}" y="${y-rh/2}" width="${W-L-Rm}" height="${rh}" fill="transparent"/><line x1="${X(r.lo)}" x2="${X(r.hi)}" y1="${y}" y2="${y}" stroke="${c}" stroke-width="2"/>`+
         `<circle cx="${X(r.rr)}" cy="${y}" r="4.5" fill="${c}" stroke="${css("--card")}" stroke-width="1.5"/></g>`;
    s += `<text x="${W-Rm+12}" y="${y+4}" style="${sig?"font-weight:650":""}">${fr(r.rr)} (${fr(r.lo)} a ${fr(r.hi)})</text><text class="m" x="${W-62}" y="${y+4}" text-anchor="end">${completo?fmtP(r.q):"…"}</text><text class="m" x="${W-8}" y="${y+4}" text-anchor="end">${fn(r.n)}</text>`;
  });
  $("k-fig").innerHTML = s+"</svg>";
  $("k-fig").querySelectorAll("g[data-c]").forEach(g=>{ g.onclick = () => { sel = g.dataset.c; desenhar() } });
}

// ---------------------------------------------------------------- Figura 5b: série semanal da causa escolhida
const planoCov = {id:"covcid", beforeDatasetsDraw(c,_a,o){
  if(!o) return; const {ctx,chartArea:a,scales:{x}} = c; const w = x.getPixelForValue(1)-x.getPixelForValue(0);
  const runs = (arr,f)=>{ let i=0; while(i<arr.length){ if(arr[i]){ let j=i; while(j+1<arr.length&&arr[j+1]) j++; f(x.getPixelForValue(i)-w/2,x.getPixelForValue(j)+w/2); i=j+1 } else i++ } };
  ctx.save();
  if(o.inc){ ctx.fillStyle = css("--cinza"); ctx.globalAlpha = .16; runs(o.inc,(l,r)=>ctx.fillRect(l,a.top,r-l,a.bottom-a.top)) }
  if(o.cov){ ctx.fillStyle = css("--cinza"); ctx.globalAlpha = .55; runs(o.cov,(l,r)=>ctx.fillRect(l,a.bottom-5,r-l,5)) }
  ctx.restore() }};
function serie(e, padrao){
  if(!sel && padrao) sel = padrao;
  const c = sel;
  if(!c){
    if(grafico){ grafico.destroy(); grafico = null }
    $("k-leg").innerHTML = ""; $("k-note2").textContent = ""; $("k-interp2").innerHTML = "";
    $("k-selnote").textContent = "Clique em uma causa da Figura 5 para ver a série semanal dela.";
    return;
  }
  const ex = exSem(c,e.medida), p = P.cid(e.kd)[ex], f = falhou.get(idK(e.kd,ex));
  $("k-h2b").textContent = `Óbitos semanais por causa: ${c} ${NOME(c)}`;
  if(!p){
    $("k-selnote").textContent = f ? "Não foi possível ajustar a série desta causa: "+String(f).replace(/[<>&]/g,"") : `Calculando a série semanal de ${c}…`;
    if(!f) enviarUm(e,ex,true);
    return;
  }
  $("k-selnote").textContent = `Causa escolhida: ${c} ${NOME(c)}.`;
  const sm = D.sem, n = sm.ano.length, idx = [...Array(n).keys()];
  const es = p.S.e, lo = p.S.l, up = p.S.u, ob = p.So.map((v,i)=>sm.inc[i]?null:v);
  const acima = ob.map((v,i)=>!sm.cov[i] && v!=null && up[i]!=null && v>up[i] ? v : null);
  const az = css("--azul"), cz = css("--cinza"), ink = css("--ink"), tickc = css("--mut"), gridc = css("--grid"), card = css("--card");
  if(grafico) grafico.destroy();
  grafico = new Chart($("k-chart"),{type:"line",data:{labels:idx.map(i=>`SE ${sm.se[i]}/${sm.ano[i]}`),datasets:[
    {label:"lo",data:lo,borderWidth:0,pointRadius:0,order:6},
    {label:FAIXA,data:up,borderWidth:0,pointRadius:0,fill:"-1",backgroundColor:mkCor(az,.17),order:6},
    {label:"Observado",data:ob,borderColor:cz,borderWidth:1.1,pointRadius:0,pointHoverRadius:4,order:3},
    {label:"Esperado sem calor",data:es,borderColor:az,borderWidth:2,pointRadius:0,order:2},
    {label:"Acima da faixa",data:acima,showLine:false,pointRadius:3,pointBackgroundColor:ink,pointBorderColor:card,pointBorderWidth:1,order:1}
  ]},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:"index",intersect:false},
    scales:{x:{grid:{display:false},ticks:{color:tickc,autoSkip:false,maxRotation:0,callback:function(v){ return sm.se[v]===1 ? sm.ano[v] : "" }}},
            y:{beginAtZero:true,grid:{color:gridc},ticks:{color:tickc},title:{display:true,text:"Óbitos por semana",color:tickc}}},
    plugins:{legend:{display:false},covcid:{cov:sm.cov,inc:sm.inc},tooltip:{filter:i=>["Observado","Esperado sem calor",FAIXA].includes(i.dataset.label),
      callbacks:{label:q=>q.dataset.label===FAIXA ? `${FAIXA}: ${lo[q.dataIndex]==null?"–":fn(lo[q.dataIndex])+" a "+fn(up[q.dataIndex])}` : `${q.dataset.label}: ${q.parsed.y==null?"–":fn(q.parsed.y,q.dataset.label==="Observado"?0:1)}`,
        afterBody:it=>{ const i=it[0].dataIndex, L=[`Início da semana: ${dBR(sm.ini[i])}`]; if(ob[i]!=null && es[i]!=null) L.push(`Observado ÷ esperado sem calor: ${fr(ob[i]/es[i])}`); if(sm.cov[i]) L.push("Semana do período COVID-19"); return L }}}}},
    plugins:[planoCov]});
  $("k-leg").innerHTML = `<span><i class="ln" style="background:${cz}"></i>Observado</span><span><i class="ln" style="background:${az};height:3px"></i>Esperado sem calor</span><span><i style="background:${mkCor(az,.17)}"></i>${FAIXA}</span><span><i class="dt" style="background:${ink}"></i>Acima da faixa</span>`;
  $("k-note2").textContent = `Mesmo modelo da Figura 1, ajustado a esta causa (${minus1(EXP[e.medida].nome)}). O esperado semanal é a soma dos esperados diários sem calor, e a faixa aproximada de variação de 95% usa a variância do modelo corrigida pela dispersão semanal (φ = ${fr(p.S.phi)}) e deixa de fora a incerteza dos coeficientes. `+
    `Sombreado cinza: semanas com dias sem registro no SIM. Barra cinza na base: semanas do período COVID-19.`+P.texto.notaClima(e.m)+P.texto.notaCausa(e.m);
  let so = 0, se = 0, nAcima = 0, nSem = 0;
  idx.forEach(i=>{ if(ob[i]!=null && es[i]!=null && !sm.cov[i]){ so += ob[i]; se += es[i]; nSem++; if(acima[i]!=null) nAcima++ } });
  $("k-interp2").innerHTML = nSem ? `<span class="t">Interpretação</span>Nas ${fn(nSem)} semanas com esperado estimado e fora do período COVID-19, o observado ficou acima do limite superior da faixa aproximada de variação de 95% em torno do esperado sem calor em <b>${fn(nAcima)}</b> (${fn(100*nAcima/nSem,1)}%). `+
    `O total observado é ${fr(so/se)} vezes o esperado sem calor, o que resume o excesso atribuído ao calor pelo modelo nesta causa. Semanas acima da faixa têm explicações possíveis além do calor (epidemias, mudanças de registro), e a figura mostra a coincidência com o calor apenas por associação.` : "";
}

P.ouvir.seg.push((kd,ex)=>{ if(!eCid(ex)) return; voo.delete(idK(kd,ex)); agendar() });
P.ouvir.erro.push(msg=>{
  if(!eCid(msg.ex) || msg.pop!==P.pop()) return;
  const id = idK(P.kd(msg.causa,msg.opc,msg.key), msg.ex);
  voo.delete(id); falhou.set(id, msg.codigo==="dados_mudaram" ? "os dados foram atualizados no servidor; recarregue a página" : String(msg.mensagem||"erro"));
  agendar();
});
P.ouvir.base.push(()=>{ voo.clear(); falhou.clear(); sel = null; desenhar() });
["k-local","k-faixa","k-raca","k-nivel","k-conj","k-cap","k-todos","k-causa","k-r-covid","k-r-nc","k-r-clima"].forEach(i=>{ const el=$(i); if(el) el.onchange = desenhar });
$("k-exp").onchange = () => { niveis(); desenhar() };
P.abas.cid = desenhar;
});

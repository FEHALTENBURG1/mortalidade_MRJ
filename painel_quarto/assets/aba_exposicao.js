/* Aba "Exposição-resposta e defasagem" (app Shiny): curvas do modelo de cada recorte.
   Usa o objeto P que figura1.js entrega às abas (window.PainelAbas): filtros de causa e de retirada, pedidos ao servidor e textos comuns.
   Um recorte (slot "x") ou dois (slots "x" e "y", que diferem só no local do óbito): cada elemento da aba tem uma cópia com prefixo y- (ver clonar()). */
(window.PainelAbas = window.PainelAbas || []).push(function(P){
"use strict";
const {$, css, fn, fr, fillSel, nm, mkCor, M, EXP, KEXP} = P;
if(!$("tab-exp")) return;
const RACAS = [{v:"Todas",t:"Todas"},{v:"Branca",t:"Branca (referência)"},{v:"Preta",t:"Preta"},{v:"Parda",t:"Parda"},{v:"PPI",t:"Pretos, pardos e indígenas (PPI)"}];
const SEM = "__sem__";
fillSel($("x-local"), M.locais.map(l=>({v:l,t:nm(l)})), "Todos os locais");
fillSel($("x-local2"), [{v:SEM,t:"Sem comparação"}, ...M.locais.map(l=>({v:l,t:nm(l)}))], SEM);
fillSel($("x-faixa"), M.faixas, "Todas as idades");
fillSel($("x-raca"), RACAS, "Todas");
fillSel($("x-exp"), KEXP.map(k=>({v:k,t:EXP[k].nome})), KEXP[0]);
if($("x-r-covid-t") && M.covid) $("x-r-covid-t").textContent = `Período COVID (${P.dBR(M.covid[0])} a ${P.dBR(M.covid[1])})`;

// Segundo recorte: cópia de cada elemento da aba marcado com a classe x, com ids y-... (o checkbox do mapa é um só e fica no recorte x)
[...$("x-cmp").children].filter(el=>el.classList.contains("x")).forEach(el=>{
  const c = el.cloneNode(true);
  c.querySelectorAll("[data-nao-clonar]").forEach(n=>n.remove());
  [c, ...c.querySelectorAll("[id]")].forEach(n=>{ if(n.id) n.id = n.id.replace(/^x-/,"y-") });
  c.classList.replace("x","y"); el.after(c);
});

const c1 = {x:null, y:null};
const SLOTS = ["x","y"];
const local = p => p==="y" ? $("x-local2").value : $("x-local").value;
const chave = p => local(p)+"|"+$("x-faixa").value+($("x-raca").value!=="Todas"?"|"+$("x-raca").value:"");
function estado(p){ const m=P.modo("x"), cod=P.cod("x"), k=chave(p), ex=$("x-exp").value; return {p, m, cod, k, ex, causa:m.causa, kd:P.kd(m.causa,cod,k)} }
const dois = () => $("x-local2").value !== SEM && $("x-local2").value !== $("x-local").value;
const ativos = () => dois() ? SLOTS : ["x"];
const calc = (p,on) => { $(p+"-kpis").classList.toggle("calc",on); document.querySelectorAll(`#tab-exp .card.${p} .chartbox, #tab-exp .card.${p} .forestbox`).forEach(e=>e.classList.toggle("calc",on)) };
function limpar(p){
  [p+"-kpis",p+"-leg",p+"-leg2",p+"-forest",p+"-interp"].forEach(i=>$(i).innerHTML="");
  if(c1[p]){ c1[p].destroy(); c1[p]=null }
  $(p+"-note").textContent = ""; $(p+"-note2").textContent = "";
}
const kpiHtml = lista => lista.map(([v,l])=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
const ic = (rr,lo,hi,d=2) => `${fn(rr,d)} (IC 95%: ${fn(lo,d)} a ${fn(hi,d)})`;

// ---------------------------------------------------------------- eixos e gráfico de floresta (Figura 3)
// Eixo com poucos marcos de valor redondo que cobre [mn, mx].
function eixo(mn, mx){
  const alvo = Math.max(mx-mn,1e-3)/4, pot = Math.pow(10,Math.floor(Math.log10(alvo))), f = alvo/pot, passo = Math.max((f<1.5?1:f<3.5?2:f<7.5?5:10)*pot, 0.01);   // RR com no máximo 2 casas: marcos de 0,01 em diante
  const a = Math.floor(mn/passo+1e-9)*passo; let b = Math.ceil(mx/passo-1e-9)*passo; if(b<=a+passo/2) b = a+passo;
  const marcos = [];
  for(let t=a; t<=b+passo/2; t+=passo) marcos.push(+t.toFixed(6));
  return {mn:a, mx:b, marcos, dec: 2};
}
const lagsAcum = () => [1,3,7,M.lag].filter((v,i,a)=>v<=M.lag && a.indexOf(v)===i);
const rotLag = l => l===0 ? "Lag 0 (mesmo dia)" : `Lag ${l}`;
const rotAcum = l => `Lag 0 a ${l}`;
// Linhas de cada bloco, uma por defasagem (bloco A) ou por acúmulo (bloco B); cada linha traz um intervalo por nível de referência.
const linhasA = L => [...Array(M.lag+1).keys()].map(l=>({rot:rotLag(l), neg:false, v:L.map(x=>({rr:x.rr[l],lo:x.lo[l],hi:x.hi[l]}))}));
const linhasB = L => lagsAcum().map(l=>({rot:rotAcum(l), neg:true, tt:`Acumulado, lag 0 a ${l}`, v:L.map(x=>({rr:x.ac[l],lo:x.aclo[l],hi:x.achi[l]}))}));
function dominioForesta(slots){
  const v = f => slots.flatMap(s=>f(s.cv.lag).flatMap(r=>r.v.flatMap(z=>[z.lo,z.hi])));
  const A = v(linhasA), B = v(linhasB);
  return {A:eixo(Math.min(1,...A),Math.max(1,...A)), B:eixo(Math.min(1,...B),Math.max(1,...B))};
}
function floresta(s, dom, C){
  const L = s.cv.lag, u = s.E.unidade, W=480, XL=100, X0=108, X1=340, XV=350, rh=28, cores=[C.az,C.la];
  let y0 = 8, g = "";
  const bloco = (titulo, linhas, ax) => {
    const X = v => X0 + (Math.min(Math.max(v,ax.mn),ax.mx)-ax.mn)/(ax.mx-ax.mn)*(X1-X0), n = linhas.length, yb = y0+22+n*rh;
    g += `<text x="${XL-92}" y="${y0+10}" style="font-weight:650">${titulo}</text>`;
    ax.marcos.forEach(t=>{ g += `<line x1="${X(t)}" x2="${X(t)}" y1="${y0+20}" y2="${yb}" stroke="${C.grid}"/><text class="m" x="${X(t)}" y="${yb+14}" text-anchor="middle">${fn(t,ax.dec)}</text>` });
    g += `<line x1="${X(1)}" x2="${X(1)}" y1="${y0+20}" y2="${yb}" stroke="${C.mut}"/>`;
    linhas.forEach((r,i)=>{
      const y = y0+22+i*rh+rh/2, dy = L.length>1 ? [-6.5,6.5] : [0];
      const dica = r.v.map((z,j)=>`${r.tt||r.rot}, ${fn(L[j].ref)} ${u} por dia: RR ${ic(z.rr,z.lo,z.hi)}`).join("\n");
      g += `<g><title>${dica}</title><text x="${XL}" y="${y+4}" text-anchor="end" style="${r.neg?"font-weight:650":""}">${r.rot}</text>`;
      r.v.forEach((z,j)=>{
        const sig = z.lo>1 || z.hi<1, yy = y+dy[j], rd = r.neg?4.6:3.6;
        g += `<line x1="${X(z.lo)}" x2="${X(z.hi)}" y1="${yy}" y2="${yy}" stroke="${cores[j]}" stroke-width="2"/>`+
             `<circle cx="${X(z.rr)}" cy="${yy}" r="${rd}" fill="${sig?cores[j]:C.card}" stroke="${cores[j]}" stroke-width="1.6"/>`+
             `<circle cx="${XV+3}" cy="${y+dy[j]-0.5}" r="2.6" fill="${cores[j]}"/>`+
             `<text x="${XV+10}" y="${y+dy[j]+3}" style="font-size:10.5px;${sig?"font-weight:650":""}">${fn(z.rr,2)} (${fn(z.lo,2)} a ${fn(z.hi,2)})</text>`;
      });
      g += `</g>`;
    });
    y0 = yb+14+16;
  };
  bloco("RR em cada defasagem", linhasA(L), dom.A);
  bloco("RR acumulado de 0 até a defasagem", linhasB(L), dom.B);
  return `<svg viewBox="0 0 ${W} ${y0}" width="100%" role="img" aria-label="RR por defasagem e RR acumulado, nos dois níveis de exposição de referência">${g}</svg>`;
}

// ---------------------------------------------------------------- Figuras 2 e 3 e quadros
function desenharCurvas(){
  if($("tab-exp").classList.contains("hide")) return;
  const r = $("x-raca").value !== "Todas"; if(r) $("x-faixa").value = "Todas as idades"; $("x-faixa").disabled = r;
  $("x-faixa").title = r ? "As séries por raça/cor são calculadas para todas as idades; volte a Todas em raça/cor para escolher uma faixa etária." : "";
  if($("x-local2").value===$("x-local").value) $("x-local2").value = SEM;      // comparar um local com ele mesmo não faz sentido
  const comp = dois();
  $("x-cmp").classList.toggle("dois", comp);
  const S = ativos().map(p=>{ const e = estado(p); return {p, e, E:EXP[e.ex]} });
  S.forEach(s=>{
    const e = s.e;
    if(!P.eleg(e.causa,e.cod).has(e.k)){ s.fase = "pouco"; return }
    s.cv = P.cv(e.kd,e.ex);
    s.fase = s.cv ? "ok" : "calc";
    if(!s.cv) P.enviar(e.k,e.ex,e.causa,e.cod);
  });
  S.forEach(s=>{
    const p = s.p;
    if(s.fase==="pouco"){ limpar(p); calc(p,false); $(p+"-sub").textContent = ""; $(p+"-note").textContent = `Menos de ${M.min_obitos} óbitos ${s.e.cod!=="000"?"no ajuste ":""}${comp?`no local “${nm(local(p))}”`:"nesta combinação de filtros"}: modelo não estimado.` }
    else if(s.fase==="calc"){ calc(p,true); $(p+"-note").textContent = "Calculando o modelo deste recorte (de 3 a 15 segundos na primeira vez; depois o resultado fica guardado no servidor)…" }
    else calc(p,false);
  });
  const prontos = S.filter(s=>s.fase==="ok");
  const C = {az:css("--azul"), la:css("--laranja"), cz:css("--cinza"), ink:css("--ink"), mut:css("--mut"), grid:css("--grid"), card:css("--card")};
  // mesma escala nos dois recortes, para que a comparação seja visual
  const dom = prontos.length ? {
    xmax: Math.max(...prontos.map(s=>s.cv.x[s.cv.x.length-1])),
    ymin: Math.floor(Math.min(1,...prontos.map(s=>Math.min(...s.cv.lo)))*100)/100, ymax: Math.ceil(Math.max(...prontos.map(s=>Math.max(...s.cv.hi)))*100)/100,
    f3: dominioForesta(prontos)} : null;
  prontos.forEach(s=>desenharSlot(s, dom, comp, C));
  comparacao(S);
}

function desenharSlot(s, dom, comp, C){
  const p = s.p, e = s.e, E = s.E, u = E.unidade, cv = s.cv, L = cv.lag, cor = [C.az, C.la], xmax = dom.xmax;
  const rotulo = `local do óbito: ${nm(local(p)).toLowerCase()}; faixa etária: ${$("x-faixa").value==="Todas as idades"?"todas as idades":$("x-faixa").value+" anos"}${$("x-raca").value!=="Todas"?"; raça/cor: "+(({PPI:"pretos, pardos e indígenas"})[$("x-raca").value]||$("x-raca").value.toLowerCase()):""}`;
  const suf = comp ? ` (local do óbito: ${nm(local(p))})` : "";
  $(p+"-sub").textContent = `Óbitos ${P.texto.causaPor(e.causa)}; ${rotulo}. As curvas vêm do mesmo modelo que gera o esperado sem calor da Figura 1 para este recorte.`;
  $(p+"-h2").textContent = "Resposta à exposição ao calor"+suf;
  $(p+"-h3").textContent = "RR por defasagem e RR acumulado"+suf;
  $(p+"-hm-h2").textContent = "RR de óbito segundo as horas do dia com índice de calor ≥ K °C"+suf;
  const pts = a => cv.x.map((x,i)=>({x, y:a[i]}));
  const eixoY = comp ? {min:dom.ymin, max:dom.ymax} : {};

  // Figura 2: RR acumulado em 0 a 10 dias em função da exposição mantida nos 11 dias
  if(c1[p]) c1[p].destroy();
  c1[p] = new Chart($(p+"-chart"),{type:"line",data:{datasets:[
    {label:"_lo",data:pts(cv.lo),borderWidth:0,pointRadius:0,order:5},
    {label:"IC 95%",data:pts(cv.hi),borderWidth:0,pointRadius:0,fill:"-1",backgroundColor:mkCor(C.az,.17),order:5},
    {label:"RR acumulado",data:pts(cv.rr),borderColor:C.az,borderWidth:2,pointRadius:0,pointHoverRadius:0,order:2},
    {label:"RR = 1",data:[{x:0,y:1},{x:xmax,y:1}],borderColor:mkCor(C.cz,.9),borderDash:[5,4],borderWidth:1,pointRadius:0,order:4},
    {label:"Níveis de referência",data:L.map(l=>({x:l.ref,y:l.ac[l.ac.length-1]})),showLine:false,pointRadius:6,pointBackgroundColor:cor,pointBorderColor:C.card,pointBorderWidth:2,order:1}
  ]},options:{responsive:true,maintainAspectRatio:false,animation:false,parsing:false,interaction:{mode:"nearest",axis:"x",intersect:false},
    scales:{x:{type:"linear",min:0,max:xmax,grid:{display:false},ticks:{color:C.mut},title:{display:true,text:`${E.nome}, mantida em todos os ${M.lag+1} dias (${u})`,color:C.mut}},
            y:{...eixoY,grid:{color:C.grid},ticks:{color:C.mut,callback:v=>fr(v)},title:{display:true,text:`RR acumulado em 0 a ${M.lag} dias`,color:C.mut}}},
    plugins:{legend:{display:false},tooltip:{filter:i=>i.dataset.label==="RR acumulado",
      callbacks:{title:it=>`${fn(it[0].parsed.x,1)} ${u} por dia`, label:c=>{ const i=c.dataIndex; return `RR ${fr(cv.rr[i])} (IC 95%: ${fr(cv.lo[i])} a ${fr(cv.hi[i])})` }}}}}});
  $(p+"-leg").innerHTML = `<span><i class="ln" style="background:${C.az};height:3px"></i>RR acumulado</span><span><i style="background:${mkCor(C.az,.17)}"></i>IC 95%</span>`+
    L.map((l,j)=>`<span><i class="dt" style="background:${cor[j]}"></i>${fn(l.ref)} ${u} por dia</span>`).join("");

  // Figura 3: floresta com o RR de cada defasagem e com o RR acumulado, nos dois níveis de referência
  $(p+"-forest").innerHTML = floresta(s, dom.f3, C);
  $(p+"-leg2").innerHTML = L.map((l,j)=>`<span><i class="dt" style="background:${cor[j]}"></i>${fn(l.ref)} ${u} por dia</span>`).join("")+
    `<span><i class="dt" style="background:${C.card};border:2px solid ${C.mut};width:9px;height:9px;box-sizing:border-box"></i>Marcador vazado: IC 95% inclui 1</span>`;

  // quadros: RR no mesmo dia e RR acumulado em 0 a 3 e em 0 a M.lag dias, para cada nível de referência
  const i3 = Math.min(3, M.lag), rrM = P.rrKpi(e.kd,e.ex);
  $(p+"-kpis").innerHTML = kpiHtml(L.flatMap((l,j)=>{
    const ref = `exposição de ${fn(l.ref)} ${u} por dia`;
    return [[ic(l.rr[0],l.lo[0],l.hi[0]), `RR no mesmo dia (lag 0), para ${ref}`],
            [ic(l.ac[i3],l.aclo[i3],l.achi[i3]), `RR acumulado nas defasagens de 0 a ${i3} dias, para ${ref} em todos esses dias`],
            [rrM[j][0], `RR acumulado nas defasagens de 0 a ${M.lag} dias, para ${ref} em todos os ${M.lag+1} dias`]];
  }));
  const curvaTxt = e.ex==="horas"
    ? "Com 1 grau de liberdade na exposição (spline natural), o logaritmo do RR cresce em linha reta com a exposição por construção, de modo que a curva não detecta limiar."
    : "O HAAT usa spline penalizado com 15 graus de liberdade, o que permite curvatura, mas as extremidades têm poucos dias e intervalos largos.";
  $(p+"-note").textContent = `RR acumulado em 0 a ${M.lag} dias para uma exposição constante, mantida em todos os ${M.lag+1} dias, em relação a nenhuma exposição. A faixa é o intervalo de confiança de 95% a partir dos coeficientes da cross-basis e da sua matriz de covariância. A grade vai até ${fn(xmax)} ${u} por dia, o percentil 99 dos dias com exposição; acima disso há poucos dias. ${curvaTxt}`;
  $(p+"-note2").textContent = `Parte superior: RR da exposição ocorrida l dias antes do óbito, para cada defasagem l de 0 a ${M.lag}. Parte inferior: RR acumulado das defasagens de 0 até l, que é o produto dos RR por defasagem de 0 a l e corresponde a manter a exposição em todos esses dias. `+
    `Os dois níveis de exposição de referência são mantidos nos ${M.lag+1} dias. As duas partes têm escalas horizontais diferentes, e as barras são intervalos de confiança de 95% a partir da matriz de covariância dos coeficientes. Marcador cheio: intervalo que não inclui 1 (valores em negrito). A resposta à defasagem é um spline natural com 3 graus de liberdade. `+
    P.notaModelo(e.kd,e.ex,e.m)+P.texto.notaClima(e.m)+P.texto.notaCausa(e.m);

  // interpretação
  const ate = l => { let k=-1; while(k+1<l.lo.length && l.lo[k+1]>1) k++; return k };            // último lag da sequência inicial com IC acima de 1
  const partes = L.map(l=>{
    const k = ate(l), a = M.lag, sig = l.aclo[a]>1 ? "o intervalo fica acima de 1" : l.achi[a]<1 ? "o intervalo fica abaixo de 1" : "o intervalo inclui 1";
    const seq = k<0 ? "sem defasagem inicial com intervalo acima de 1" : k>=a ? "com intervalo acima de 1 em todas as defasagens" : `com intervalo acima de 1 até o lag ${k}`;
    return `com ${fn(l.ref)} ${u} por dia, o RR no mesmo dia (lag 0) é ${ic(l.rr[0],l.lo[0],l.hi[0])}, ${seq}; o RR acumulado em 0 a ${i3} dias é ${ic(l.ac[i3],l.aclo[i3],l.achi[i3])} e em 0 a ${a} dias é ${ic(l.ac[a],l.aclo[a],l.achi[a])}, isto é, ${P.fp((l.ac[a]-1)*100)} no risco diário de óbito (${sig})` });
  const tardio = L.some(l=>l.hi.some(v=>v<1));
  $(p+"-interp").innerHTML = `<span class="t">Interpretação</span>Neste recorte, ${partes.join(". Já ")}. `+
    (tardio?`Há defasagens em que o intervalo de confiança fica inteiro abaixo de 1. Isso pode refletir antecipação de óbitos de pessoas frágeis ou variação aleatória, e o modelo não separa as duas explicações. `:"")+
    `As estimativas descrevem associação em dados agregados, sem controle de fatores individuais.`;
}

// Texto que põe lado a lado o RR acumulado dos dois locais (só com dois recortes prontos)
function comparacao(S){
  const el = $("x-comp-txt");
  if(S.length<2 || S.some(s=>s.fase!=="ok")){ el.innerHTML = ""; return }
  const [a,b] = S, u = a.E.unidade, i = M.lag;
  const frases = a.cv.lag.map((la,j)=>{
    const lb = b.cv.lag[j], sobrepoe = !(la.aclo[i]>lb.achi[i] || lb.aclo[i]>la.achi[i]);
    return `Com ${fn(la.ref)} ${u} por dia, o RR acumulado em 0 a ${i} dias é ${ic(la.ac[i],la.aclo[i],la.achi[i])} no local “${nm(local("x"))}” e ${ic(lb.ac[i],lb.aclo[i],lb.achi[i])} no local “${nm(local("y"))}”, e os intervalos ${sobrepoe?"se sobrepõem":"não se sobrepõem"}`;
  });
  const aninhado = [local("x"),local("y")].includes("Todos os locais");
  el.innerHTML = `<span class="t">Comparação entre os locais do óbito</span>${frases.join(". ")}. `+
    `A sobreposição dos intervalos é uma comparação informal e não substitui um teste da diferença entre os recortes. `+
    (aninhado?`Como “Todos os locais” inclui os óbitos do outro recorte, as duas estimativas não são independentes. `:"")+
    `Os dois recortes usam a mesma escala vertical na Figura 2 e a mesma escala horizontal na Figura 3.`;
}

// ---------------------------------------------------------------- Figura 4: horas por dia x limiar do índice de calor
// Cada célula é um modelo próprio (R/modelo_joao.R, ajustar_mapa_limiar). O navegador pede uma coluna (limiar K) por vez, no máximo MAX_VOO ao mesmo
// tempo, e redesenha a tabela a cada coluna recebida. Primeiro o limiar usual de 36 °C, depois os demais. Com dois recortes, o primeiro é calculado antes.
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
function mapaSlot(p){
  const e = estado(p), tab = $(p+"-hm"), prog = $(p+"-hm-prog"), nota = $(p+"-hm-note"), it = $(p+"-hm-interp");
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
  const icc = c => `${fr(c.rr)} (IC 95%: ${fr(c.lo)} a ${fr(c.hi)}; ${fn(c.nd)} dias expostos)`;
  it.innerHTML = `<span class="t">Interpretação</span>Das <b>${cel.length}</b> combinações estimadas, <b>${sg.length}</b> têm RR acima de 1 com IC 95% que não inclui 1 e <b>${dn.length}</b> têm RR abaixo de 1 com IC 95% que não inclui 1. `+
    (base?`Com o limiar usual de 36 °C e pelo menos 1 hora no dia, RR = <b>${icc(base)}</b>. `:"")+
    `O maior valor da tabela é RR = <b>${icc(mx)}</b>, com índice de calor ≥ ${mx.K} °C por ≥ ${mx.h} h. O máximo de muitas células tende a superestimar o efeito, e as células com poucos dias expostos têm intervalos largos. `+
    (a&&b?`Ao subir o limiar de 32 para 40 °C (≥ 1 h), o RR passa de ${fr(a.rr)} para ${fr(b.rr)}${b.rr>a.rr?", no sentido de risco maior com calor mais intenso; esse gradiente favorece a associação, e os dados agregados não permitem inferir causalidade. ":", sem gradiente crescente. "}`:"")+
    `As células são aninhadas, pois um dia com mais horas também entra nas definições com menos horas, e não passaram por correção para comparações múltiplas. O padrão geral da tabela é mais informativo do que uma célula isolada. `+
    `O RR de cada célula descreve a associação em dados agregados, sem controle de fatores individuais.`;
}
function mapa(){
  if($("tab-exp").classList.contains("hide")) return;
  ativos().forEach(mapaSlot);
}

function desenhar(){ desenharCurvas(); mapa() }                    // as Figuras 2 e 3 são pedidas primeiro: o servidor as atende antes das colunas do mapa

P.ouvir.seg.push((kd,ex)=>{
  if(eMapa(ex)){ voo.delete(idM(kd,+ex.slice(4))); mapa(); return }
  if(ativos().some(p=>{ const e=estado(p); return kd===e.kd && ex===e.ex })){ desenharCurvas(); mapa() }
});
P.ouvir.erro.push(msg=>{
  if(eMapa(msg.ex)){
    if(msg.pop!==P.pop()) return;
    const id = idM(P.kd(msg.causa,msg.opc,msg.key), +msg.ex.slice(4));
    voo.delete(id); falhou.set(id, msg.codigo==="dados_mudaram" ? "dados_mudaram" : String(msg.mensagem||"erro"));
    mapa(); return;
  }
  if($("tab-exp").classList.contains("hide")) return;
  ativos().forEach(p=>{
    const e = estado(p); if(msg.pop!==P.pop() || msg.key!==e.k || msg.ex!==e.ex || msg.causa!==e.causa || msg.opc!==e.cod) return;
    calc(p,false);
    $(p+"-note").innerHTML = msg.codigo==="dados_mudaram"
      ? 'Os dados foram atualizados no servidor. <a href="">Recarregue a página</a> para ver a versão nova.'
      : "Não foi possível ajustar o modelo deste recorte: "+String(msg.mensagem||"erro desconhecido").replace(/[<>&]/g,"");
  });
});
P.ouvir.base.push(()=>{ voo.clear(); falhou.clear(); desenhar() });
["x-local","x-local2","x-faixa","x-raca","x-exp","x-causa","x-r-covid","x-r-nc","x-r-clima","x-hm-sig"].forEach(i=>{ const el=$(i); if(el) el.onchange=desenhar });
P.abas.exp = desenhar;
});

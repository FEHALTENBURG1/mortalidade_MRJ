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

const c1 = {x:null, y:null}, c2 = {x:null, y:null};                // Figura 2 e gráfico de suporte (dias por hora)
const flexVoo = new Map(), flexFalhou = new Map();                    // kd -> instante do pedido | kd -> mensagem de erro (comparação com a curva flexível)
const flexDe = s => s.e.ex==="horas" ? (P.dg(s.e.kd)["flex_horas"]||null) : null;
// Suporte dos contrastes acumulados (pedido "sup_<medida>"): vale para qualquer recorte, então o navegador pede sempre com o recorte de todos os óbitos
const KEY_SUP = "Todos os locais|Todas as idades";
const supVoo = new Map(), supFalhou = new Map();
const supDe = s => P.dg(P.kd(s.e.causa,s.e.cod,KEY_SUP))["sup_"+s.e.ex] || null;
function pedirSup(e){
  const kd = P.kd(e.causa,e.cod,KEY_SUP), id = kd+"|"+e.ex, agora = Date.now(); supVoo.forEach((t,i)=>{ if(agora-t>180000) supVoo.delete(i) });
  if(supVoo.has(id) || supFalhou.has(id)) return;
  supVoo.set(id,agora); P.enviar(KEY_SUP,"sup_"+e.ex,e.causa,e.cod);
}
function pedirFlex(e){
  const agora = Date.now(); flexVoo.forEach((t,id)=>{ if(agora-t>180000) flexVoo.delete(id) });
  if(flexVoo.has(e.kd) || flexFalhou.has(e.kd)) return;
  flexVoo.set(e.kd,agora); P.enviar(e.k,"flex_horas",e.causa,e.cod);
}
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
  if(c2[p]){ c2[p].destroy(); c2[p]=null }
  ["-sq","-sq-dur","-sq-an","-sq-interp"].forEach(i=>$(p+i).innerHTML=""); ["-sq-note","-sq-note2","-sq-prog"].forEach(i=>$(p+i).textContent="");
  $(p+"-fx").innerHTML = ""; $(p+"-fx-interp").innerHTML = ""; $(p+"-fx-note").textContent = ""; $(p+"-fx-prog").textContent = ""; $(p+"-supnote").textContent = ""; $(p+"-supbox").style.display = "none";
  $(p+"-note").textContent = ""; $(p+"-note2").textContent = "";
}
const kpiHtml = lista => lista.map(([v,l])=>`<div class="kpi mod"><div class="tg"><span class="tp">RR do modelo</span></div><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");   // todos os cartões desta aba são RR estimados pelo modelo
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
    if(s.fase==="pouco"){ limpar(p); calc(p,false); P.texto.ficha(p+"-sub", null); $(p+"-note").textContent = `Menos de ${M.min_obitos} óbitos ${s.e.cod!=="000"?"no ajuste ":""}${comp?`no local “${nm(local(p))}”`:"nesta combinação de filtros"}: modelo não estimado.` }
    else if(s.fase==="calc"){ calc(p,true); $(p+"-note").textContent = "Calculando o modelo deste recorte (de 3 a 15 segundos na primeira vez; depois o resultado fica guardado no servidor)…" }
    else calc(p,false);
  });
  const prontos = S.filter(s=>s.fase==="ok");
  const C = {az:css("--azul"), la:css("--laranja"), cz:css("--cinza"), ink:css("--ink"), mut:css("--mut"), grid:css("--grid"), card:css("--card")};
  // mesma escala nos dois recortes, para que a comparação seja visual
  const dom = prontos.length ? {
    xmax: Math.max(...prontos.map(s=>s.cv.x[s.cv.x.length-1])),
    ymin: Math.floor(Math.min(1,...prontos.map(s=>Math.min(...s.cv.lo, ...(flexDe(s)?flexDe(s).flex.cv.lo:[]))))*100)/100,
    ymax: Math.ceil(Math.max(...prontos.map(s=>Math.max(...s.cv.hi, ...(flexDe(s)?flexDe(s).flex.cv.hi:[]))))*100)/100,
    f3: dominioForesta(prontos)} : null;
  prontos.forEach(s=>desenharSlot(s, dom, comp, C));
  comparacao(S);
}

// ---------------------------------------------------------------- suporte de dados e comparação com a curva flexível
// Dias no ajuste por hora de exposição (mesma escala horizontal da Figura 2): mostra onde há dados para estimar a curva. Só para as horas por dia.
function apoio(p, fx, xmax, C, eixoX, cv, E){
  const box = $(p+"-supbox"), nota = $(p+"-supnote");
  if(c2[p]){ c2[p].destroy(); c2[p]=null }
  if(E.fun!=="ns"){ box.style.display = "none"; nota.textContent = ""; return }
  if(!fx){
    box.style.display = "none";
    nota.textContent = flexFalhou.has(P.kd(P.modo("x").causa,P.cod("x"),chave(p))) ? "Não foi possível calcular a comparação com a curva flexível: "+String(flexFalhou.get(P.kd(P.modo("x").causa,P.cod("x"),chave(p)))).replace(/[<>&]/g,"")
      : "Calculando a curva flexível e o suporte de dados (cerca de 10 segundos na primeira vez; depois o resultado fica guardado no servidor)…";
    return;
  }
  box.style.display = "";
  const h = fx.sup.h, n = fx.sup.n, pts = h.map((x,i)=>({x, y:n[i]})).filter(q=>q.x>=1 && q.x<=xmax);
  c2[p] = new Chart($(p+"-sup"),{type:"bar",data:{datasets:[{label:"Dias no ajuste",data:pts,backgroundColor:mkCor(C.cz,.75),borderWidth:0,barPercentage:.9,categoryPercentage:1}]},
    options:{responsive:true,maintainAspectRatio:false,animation:false,parsing:false,
      scales:{x:{...eixoX,title:{display:true,text:"Horas por dia com IC ≥ 36 °C (barras: dias no ajuste)",color:C.mut}},
              y:{beginAtZero:true,grid:{color:C.grid},ticks:{color:C.mut,maxTicksLimit:4,callback:v=>fn(v)},title:{display:true,text:"Dias",color:C.mut},afterFit:sc=>{ sc.width = 64 }}},
      plugins:{legend:{display:false},tooltip:{callbacks:{title:it=>`${fn(it[0].parsed.x)} h por dia`,label:c=>`${fn(c.parsed.y)} dias no ajuste`}}}}});
  const tot = n.reduce((a,b)=>a+b,0), exp1 = tot-n[0], ge = k => h.reduce((a,x,i)=>a+(x>=k?n[i]:0),0);
  nota.textContent = `Barras: dias no ajuste (${fn(fx.nd)} dias) por número de horas com IC ≥ 36 °C; o dia sem nenhuma hora (${fn(n[0])} dias) não aparece. `+
    `São ${fn(exp1)} dias com pelo menos 1 h, ${fn(ge(8))} com pelo menos 8 h e ${fn(ge(10))} com pelo menos 10 h. O eixo termina em ${fn(xmax)} h, o percentil 99 dos dias com exposição, e há ${fn(ge(xmax+1))} dias acima desse valor. `+
    `A curva e as barras valem para todo o período do ajuste, e não para o recorte escolhido: o suporte de dias é o mesmo em qualquer recorte, e só o número de óbitos muda.`;
}

const icr = (v,d=2) => `${fn(v[0],d)} (IC 95%: ${fn(v[1],d)} a ${fn(v[2],d)})`;
const icc = v => `${fn(v[0],2)} (${fn(v[1],2)} a ${fn(v[2],2)})`;            // célula de tabela: o cabeçalho já diz IC 95%
function flexQuadro(s, fx){
  const p = s.p, e = s.e, E = s.E, u = E.unidade, tab = $(p+"-fx"), nota = $(p+"-fx-note"), it = $(p+"-fx-interp"), prog = $(p+"-fx-prog");
  if(E.fun!=="ns"){
    // HAAT: a curva já é flexível (spline penalizado); mostra a dimensão da base e os graus de liberdade efetivos
    const cb = (P.cb && P.cb(e.kd,e.ex)) || null;
    $(p+"-fx-h").textContent = "Flexibilidade da curva do HAAT";
    prog.textContent = "";
    if(!cb){ tab.innerHTML = ""; nota.textContent = ""; it.innerHTML = ""; return }
    tab.innerHTML = `<thead><tr><th>Especificação</th><th class="n">gl na exposição</th><th class="n">gl na defasagem</th><th class="n">Dimensão da base cruzada (k')</th><th class="n">gl efetivos da base cruzada</th></tr></thead><tbody>`+
      `<tr><td>Spline penalizado (modelo de referência)</td><td class="n">${E.df}</td><td class="n">3</td><td class="n">${fn(cb.k)}</td><td class="n">${fn(cb.edf,1)}</td></tr></tbody>`;
    nota.textContent = `O HAAT é estimado por um spline penalizado com ${E.df} graus de liberdade na exposição, combinado com 3 graus de liberdade na defasagem, o que dá uma base cruzada de k' = ${fn(cb.k)} colunas. A penalização encolhe os coeficientes: os graus de liberdade efetivos (${fn(cb.edf,1)}) medem a flexibilidade que os dados sustentaram, e não o número de colunas. `+
      `Nesta medida a curva é estimada e não imposta, mas as extremidades têm poucos dias de exposição alta e intervalos largos.`;
    it.innerHTML = `<span class="t">Interpretação</span>A curva do HAAT usa ${fn(cb.edf,1)} dos ${fn(cb.k)} graus de liberdade possíveis, de modo que a penalização mantém a curva mais suave do que a base permitiria. Leia as extremidades da Figura 2 com cautela, porque há poucos dias com HAAT alto.`;
    return;
  }
  $(p+"-fx-h").textContent = "Reta imposta e curva flexível (horas por dia)";
  if(!fx){ tab.innerHTML = ""; it.innerHTML = ""; nota.textContent = ""; prog.textContent = flexFalhou.has(e.kd) ? "" : "Calculando a comparação com a curva flexível…"; return }
  prog.textContent = "";
  const a = fx.lin, b = fx.flex, c = fx.comp, rf = fx.ref;
  const gl = (o,gx) => `${gx} (${o.k})`;
  tab.innerHTML = `<thead><tr><th>Especificação</th><th class="n">gl na exposição (colunas da base cruzada)</th><th class="n">RR com ${fn(rf[0])} h por dia (IC 95%)</th><th class="n">RR com ${fn(rf[1])} h por dia (IC 95%)</th>`+
    `<th class="n">RR de ${fn(rf[1])} h contra ${fn(rf[0])} h (IC 95%)</th><th class="n">log RR(${fn(rf[1])} h) ÷ log RR(${fn(rf[0])} h)</th><th class="n">AIC</th></tr></thead><tbody>`+
    `<tr><td>Reta imposta (modelo de referência)</td><td class="n">${gl(a,1)}</td><td class="n">${icc([a.rr[0],a.lo[0],a.hi[0]])}</td><td class="n">${icc([a.rr[1],a.lo[1],a.hi[1]])}</td><td class="n">${icc(a.r84)}</td><td class="n">${fn(2,2)} (imposta)</td><td class="n">${fn(a.aic,1)}</td></tr>`+
    `<tr><td>Curva flexível (spline natural, nós em ${fx.nos.join(" e ")} h)</td><td class="n">${gl(b,3)}</td><td class="n">${icc([b.rr[0],b.lo[0],b.hi[0]])}</td><td class="n">${icc([b.rr[1],b.lo[1],b.hi[1]])}</td><td class="n">${icc(b.r84)}</td><td class="n">${fn(c.razao,2)}</td><td class="n">${fn(b.aic,1)}</td></tr></tbody>`;
  const pt = c.p==null ? null : (c.p<0.001 ? "p < 0,001" : "p = "+fn(c.p,3));
  nota.textContent = `Reta imposta: com 1 grau de liberdade na exposição, o log-RR é proporcional às horas, de modo que RR(${fn(rf[1])} h) = RR(${fn(rf[0])} h)² e o RR de ${fn(rf[1])} h contra ${fn(rf[0])} h é igual ao RR de ${fn(rf[0])} h contra nenhuma exposição. Os dois RR do modelo de referência formam um só achado, e não duas estimativas independentes. `+
    `Curva flexível: spline natural com 3 graus de liberdade na exposição, com nós interiores em ${fx.nos.join(" e ")} h, definidos antes da análise e sem otimização, e os mesmos termos de tempo, de dia do ano, de COVID-19, a mesma defasagem e as mesmas retiradas do ajuste. `+
    (pt?`Comparação aproximada (razão de desvios do anova.gam do mgcv, com a reta contida na curva flexível): diferença de desvio ${fn(c.desvio,1)} com ${fn(c.gl,1)} gl, ${pt}; AIC da curva flexível menos AIC da reta = ${fn(c.d_aic,1).replace("-","−")}. `:`AIC da curva flexível menos AIC da reta = ${fn(c.d_aic,1).replace("-","−")}. `)+
    `Os resíduos do modelo têm autocorrelação (aba Diagnósticos e sensibilidades), por isso o valor de p é só indicativo. Os dois ajustes usam ${fn(fx.nd)} dias e ${fn(fx.no)} óbitos.`;
  // interpretação
  const dentro = (r,v) => v>=r[1] && v<=r[2], j = [0,1];
  const dir = j.map(i=>`${fn(rf[i])} h: ${fr(b.rr[i])} na curva flexível contra ${fr(a.rr[i])} na reta`).join("; ");
  const fora = j.filter(i=>!dentro([b.rr[i],b.lo[i],b.hi[i]], a.rr[i])).map(i=>fn(rf[i])+" h");
  const ult = b.cv.x.length-1, xm = b.cv.x[ult], ge10 = fx.sup.h.reduce((q,h,i)=>q+(h>=10?fx.sup.n[i]:0),0), exp1 = fx.sup.n.reduce((q,v)=>q+v,0)-fx.sup.n[0];
  const prefere = c.p!=null && c.p<0.05 && c.d_aic<0;
  it.innerHTML = `<span class="t">Interpretação</span>Os RR acumulados estimados são: ${dir}. `+
    (fora.length?`O RR da reta fica fora do IC 95% da curva flexível em ${fora.join(" e ")}. `:`O RR da reta fica dentro do IC 95% da curva flexível nos dois níveis. `)+
    `A razão log RR(${fn(rf[1])} h) ÷ log RR(${fn(rf[0])} h) é ${fn(c.razao,2)} na curva flexível, contra 2,00 imposto pela reta. `+
    (prefere?`O teste aproximado e o AIC preferem a curva flexível, o que indica que a reta é uma simplificação e que o RR de ${fn(rf[1])} h obtido da reta não deve ser lido como uma estimativa independente do de ${fn(rf[0])} h. `
            :`Neste recorte, a curva flexível não melhora o ajuste de modo claro (teste aproximado e AIC), e a reta é uma aproximação razoável dentro do que os dados mostram. `)+
    `Nas extremidades o suporte é pequeno: só ${fn(ge10)} dos ${fn(exp1)} dias com pelo menos 1 h chegam a 10 h ou mais. Em ${fn(xm)} h (limite da figura), o RR é ${fr(b.cv.rr[ult])} (IC 95%: ${fr(b.cv.lo[ult])} a ${fr(b.cv.hi[ult])}) na curva flexível e ${fr(a.cv.rr[ult])} (IC 95%: ${fr(a.cv.lo[ult])} a ${fr(a.cv.hi[ult])}) na reta. `+
    `O IC da curva flexível alarga ao se afastar da região com mais dias, e o IC estreito da reta nessa região vem da forma imposta, e não de mais dados.`;
}

// ---------------------------------------------------------------- suporte dos contrastes acumulados (Quadro 4)
// Quantas vezes a série tem a exposição de referência em todos os d dias seguidos até o dia do óbito: sem isso, o RR de 8 h (ou do HAAT alto) por 11 dias
// seria extrapolação do modelo. Cada linha traz o RR acumulado do mesmo contraste, tirado do ajuste do recorte (lag 0 a d-1).
const DUR_SQ = [1,2,4,8,11];
const leituraSq = n => n>=30 ? "frequente" : n>=5 ? "poucos eventos" : "extrapolação";
function sqQuadro(s, sp){
  const p = s.p, e = s.e, E = s.E, u = E.unidade, L = s.cv.lag, prog = $(p+"-sq-prog");
  ["-sq","-sq-dur","-sq-an","-sq-interp"].forEach(i=>$(p+i).innerHTML=""); ["-sq-note","-sq-note2"].forEach(i=>$(p+i).textContent="");
  if(!sp){
    const f = supFalhou.get(P.kd(e.causa,e.cod,KEY_SUP)+"|"+e.ex);
    prog.textContent = f ? "Não foi possível calcular o suporte dos contrastes: "+String(f).replace(/[<>&]/g,"") : "Calculando o suporte dos contrastes (poucos segundos)…";
    return;
  }
  prog.textContent = "";
  const nv = sp.niveis, ref = sp.ref, d11 = sp.dur.indexOf(M.lag+1);
  let h = `<thead><tr><th>Exposição de referência</th><th class="n">Dias seguidos com exposição até o dia do óbito</th><th class="n">Contraste (defasagens)</th><th class="n">RR acumulado (IC 95%)</th><th class="n">Janelas no ajuste</th><th class="n">Eventos independentes</th><th>Leitura</th></tr></thead><tbody>`;
  nv.forEach((q,j)=>sp.dur.forEach((d,i)=>{
    const l = L[j], a = d-1, ex = q.eventos[i]<5, rot = i===0 ? `${fn(ref[j])} ${u} por dia ou mais` : "";
    h += `<tr class="${ex?"ext":""}"><td>${rot}</td><td class="n">${fn(d)}${d===M.lag+1?" (cenário dos cartões de RR)":""}</td><td class="n">0 a ${fn(a)}</td><td class="n">${a<l.ac.length?`${fn(l.ac[a],2)} (${fn(l.aclo[a],2)} a ${fn(l.achi[a],2)})`:"–"}</td><td class="n">${fn(q.janelas[i])}</td><td class="n">${fn(q.eventos[i])}</td><td>${leituraSq(q.eventos[i])}</td></tr>`;
  }));
  $(p+"-sq").innerHTML = h+"</tbody>";
  $(p+"-sq-note").textContent = `Dia com exposição: dia em que a própria exposição, e não a janela de t a t−3 da Figura 1, atinge pelo menos o nível de referência (${ref.map(r=>fn(r)+" "+u).join(" ou ")}; dia sem dado de clima conta como sem exposição). Janela: dia do óbito no ajuste (${fn(sp.nd)} dias) em que os d dias terminados nele são todos dias com exposição; a janela de ${M.lag+1} dias é o cenário do cartão de RR. `+
    `Evento independente: conjunto de dias com exposição separado de outros por pelo menos ${M.lag} dias sem exposição, de modo que as janelas de defasagem de eventos diferentes não se tocam; o quadro conta os eventos que têm pelo menos uma janela de d dias. `+
    `O RR de cada linha é o acumulado nas defasagens de 0 a d-1 do recorte escolhido (exposição mantida nos d últimos dias e ausente antes), e o suporte (janelas e eventos) vale para qualquer recorte porque só depende da exposição e dos dias do ajuste. `+
    `Leitura: menos de 5 eventos independentes = extrapolação; 5 a 29 = poucos eventos; 30 ou mais = frequente. Esses limiares são uma convenção do painel para leitura rápida, e não um critério estatístico.`;
  // duração observada e distribuição por ano
  let hd = `<thead><tr><th>Exposição de referência</th>${sp.niveis[0].duracao.classe.map(c=>`<th class="n">${c}</th>`).join("")}<th class="n">Sequências</th></tr></thead><tbody>`;
  nv.forEach((q,j)=>{ const t = q.duracao.n.reduce((a,b)=>a+b,0); hd += `<tr><td>${fn(ref[j])} ${u} por dia ou mais</td>${q.duracao.n.map(v=>`<td class="n">${fn(v)}</td>`).join("")}<td class="n">${fn(t)}</td></tr>` });
  $(p+"-sq-dur").innerHTML = hd+"</tbody>";
  const anos = nv[0].anual.ano; let ha = `<thead><tr><th rowspan="2">Ano</th>${nv.map((q,j)=>`<th class="n gr2" colspan="3">${fn(ref[j])} ${u} por dia ou mais</th>`).join("")}</tr><tr>${nv.map(()=>`<th class="n gr2">Dias com exposição</th><th class="n">Sequências de 4 dias ou mais</th><th class="n">Janelas de ${M.lag+1} dias</th>`).join("")}</tr></thead><tbody>`;
  anos.forEach((a,i)=>{ ha += `<tr><td>${a}</td>${nv.map(q=>`<td class="n gr2">${fn(q.anual.dias[i])}</td><td class="n">${fn(q.anual.seq4[i])}</td><td class="n">${fn(q.anual.jan11[i])}</td>`).join("")}</tr>` });
  const som = v => v.reduce((a,b)=>a+b,0);
  ha += `<tr class="ext"><td>Total</td>${nv.map(q=>`<td class="n gr2">${fn(som(q.anual.dias))}</td><td class="n">${fn(som(q.anual.seq4))}</td><td class="n">${fn(som(q.anual.jan11))}</td>`).join("")}</tr>`;
  $(p+"-sq-an").innerHTML = ha+"</tbody>";
  $(p+"-sq-note2").textContent = `Sequência: dias com exposição seguidos, contada se tem pelo menos um dia no ajuste. Na tabela por ano, a sequência de 4 dias ou mais entra no ano em que completa o quarto dia com exposição dentro do ajuste, e a janela de ${M.lag+1} dias no ano do dia do óbito. Os anos são os do ajuste: 2007 começa com o clima disponível em abril e o último ano está incompleto.`;
  // interpretação
  const f = j => { const q = nv[j]; return `a exposição de ${fn(ref[j])} ${u} por dia em todos os ${M.lag+1} dias ocorre em ${fn(q.janelas[d11])} ${q.janelas[d11]===1?"janela":"janelas"} (${fn(q.eventos[d11])} ${q.eventos[d11]===1?"evento independente":"eventos independentes"})` };
  const maior = j => { const q = nv[j]; let k = -1; sp.dur.forEach((d,i)=>{ if(q.eventos[i]>=5) k = i }); return k<0 ? null : sp.dur[k] };
  const rara = nv.map((q,j)=>j).filter(j=>nv[j].eventos[d11]<5);
  const frases = nv.map((q,j)=>{ const m = maior(j); return `${f(j)}${m!=null&&m<M.lag+1?`; o maior contraste com pelo menos 5 eventos independentes é o de ${fn(m)} ${m===1?"dia":"dias"} seguidos`:""}` });
  $(p+"-sq-interp").innerHTML = `<span class="t">Interpretação</span>`+
    `No ajuste de ${fn(sp.nd)} dias, ${frases.join(". Já ")}. `+
    (rara.length ? `O RR acumulado de 0 a ${M.lag} dias para ${rara.map(j=>fn(ref[j])+" "+u+" por dia").join(" e para ")} descreve uma sequência que quase não ocorre na série: ele vem do modelo${e.ex==="horas"?" (reta imposta de 1 grau de liberdade)":""} aplicado a uma combinação de exposições que os dados mal cobrem, e deve ser lido como extrapolação. `+
                    `Há ${rara.map(j=>fn(nv[j].janelas_media)+" janelas de "+(M.lag+1)+" dias em que a média diária é de pelo menos "+fn(ref[j])+" "+u+" (com dias acima e abaixo)").join(" e ")}, o que dá algum suporte à dose total de exposição, mas não ao padrão constante que o cartão descreve. Os contrastes de menor duração, com mais eventos, são os que os dados sustentam melhor. `
                  : `Os cenários dos cartões de RR têm eventos suficientes para que a estimativa descreva exposições que de fato ocorreram, embora em poucos episódios independentes. `)+
    `Os eventos independentes são o número que mais se aproxima do tamanho efetivo da amostra de exposições: várias janelas seguidas dentro do mesmo evento não trazem informação independente.`;
}

function desenharSlot(s, dom, comp, C){
  const p = s.p, e = s.e, E = s.E, u = E.unidade, cv = s.cv, L = cv.lag, cor = [C.az, C.la], xmax = dom.xmax;
  const suf = comp ? ` (local do óbito: ${nm(local(p))})` : "";
  P.texto.ficha(p+"-sub", {recorte:P.texto.recorte(local(p),$("x-faixa").value,$("x-raca").value), kd:e.kd, ex:e.ex, m:e.m, filtrado:comp||P.texto.filtrado(local(p),$("x-faixa").value,$("x-raca").value), linhas:[["Origem das curvas","mesmo modelo que gera o esperado sem calor da Figura 1 para este recorte"]]});
  $(p+"-h2").textContent = "Resposta à exposição ao calor"+suf;
  $(p+"-h3").textContent = "RR por defasagem e RR acumulado"+suf;
  $(p+"-hm-h2").textContent = "RR da contagem diária de óbitos segundo as horas do dia com IC ≥ K °C"+suf;
  const pts = a => cv.x.map((x,i)=>({x, y:a[i]}));
  const eixoY = comp ? {min:dom.ymin, max:dom.ymax} : {};

  // Figura 2: RR acumulado em 0 a 10 dias em função da exposição mantida nos 11 dias. Para as horas por dia, a linha azul é a reta imposta pelo modelo
  // de referência (1 gl) e a curva tracejada é a alternativa flexível pré-definida (pedido "flex_horas"), com o suporte de dados logo abaixo.
  const fx = flexDe(s), horas = e.ex==="horas";
  if(horas && !fx) pedirFlex(e);
  if(c1[p]) c1[p].destroy();
  const ptsF = a => fx.flex.cv.x.map((x,i)=>({x, y:a[i]}));
  const rotP = horas ? "Reta imposta (log-RR linear, 1 gl)" : "Curva estimada (spline penalizado)";
  const off = horas ? 0.5 : 0;
  const eixoX = {type:"linear",min:-off,max:xmax+off,grid:{display:false},ticks:{color:C.mut,callback:v=>fn(v)},
    afterBuildTicks: horas ? sc=>{ sc.ticks = Array.from({length:Math.floor(xmax)+1},(_,i)=>({value:i})) } : undefined};     // horas inteiras de 0 a xmax; o meio ponto de folga nas bordas só dá espaço às barras
  c1[p] = new Chart($(p+"-chart"),{type:"line",data:{datasets:[
    {label:"_lo",data:pts(cv.lo),borderWidth:0,pointRadius:0,order:5},
    {label:"IC 95%",data:pts(cv.hi),borderWidth:0,pointRadius:0,fill:"-1",backgroundColor:mkCor(C.az,.17),order:5},
    ...(fx?[{label:"_lof",data:ptsF(fx.flex.cv.lo),borderWidth:0,pointRadius:0,order:6},
            {label:"IC 95% da curva flexível",data:ptsF(fx.flex.cv.hi),borderWidth:0,pointRadius:0,fill:"-1",backgroundColor:mkCor(C.ink,.10),order:6}]:[]),
    {label:rotP,tip:"ref",data:pts(cv.rr),borderColor:C.az,borderWidth:2,pointRadius:0,pointHoverRadius:0,order:2},
    ...(fx?[{label:"Curva flexível",tip:"flex",data:ptsF(fx.flex.cv.rr),borderColor:C.ink,borderDash:[7,4],borderWidth:2,pointRadius:0,pointHoverRadius:0,order:3}]:[]),
    {label:"RR = 1",data:[{x:-off,y:1},{x:xmax+off,y:1}],borderColor:mkCor(C.cz,.9),borderDash:[5,4],borderWidth:1,pointRadius:0,order:4},
    {label:"Níveis de referência",data:L.map(l=>({x:l.ref,y:l.ac[l.ac.length-1]})),showLine:false,pointRadius:6,pointBackgroundColor:cor,pointBorderColor:C.card,pointBorderWidth:2,order:1}
  ]},options:{responsive:true,maintainAspectRatio:false,animation:false,parsing:false,interaction:{mode:"nearest",axis:"x",intersect:false},
    scales:{x:{...eixoX,title:{display:true,text:`${E.nome}, mantida em todos os ${M.lag+1} dias (${u})`,color:C.mut}},
            y:{...eixoY,grid:{color:C.grid},ticks:{color:C.mut,callback:v=>fr(v)},title:{display:true,text:`RR acumulado em 0 a ${M.lag} dias`,color:C.mut},afterFit:sc=>{ sc.width = 64 }}},
    plugins:{legend:{display:false},tooltip:{filter:i=>!!i.dataset.tip,
      callbacks:{title:it=>`${fn(it[0].parsed.x,1)} ${u} por dia`, label:c=>{ const i=c.dataIndex, f=c.dataset.tip==="flex"?fx.flex.cv:cv; return `${c.dataset.tip==="flex"?"Curva flexível":rotP}: RR ${fr(f.rr[i])} (IC 95%: ${fr(f.lo[i])} a ${fr(f.hi[i])})` }}}}}});
  const traco = cl => `<i style="background:repeating-linear-gradient(90deg,${cl} 0 6px,transparent 6px 10px);height:3px;vertical-align:3px"></i>`;
  $(p+"-leg").innerHTML = `<span><i class="ln" style="background:${C.az};height:3px"></i>${rotP}</span><span><i style="background:${mkCor(C.az,.17)}"></i>IC 95%${horas?" da reta":""}</span>`+
    (fx?`<span>${traco(C.ink)}Curva flexível pré-definida (spline natural, 3 gl, nós em ${fx.nos.join(" e ")} h)</span><span><i style="background:${mkCor(C.ink,.10)}"></i>IC 95% da curva flexível</span>`:"")+
    L.map((l,j)=>`<span><i class="dt" style="background:${cor[j]}"></i>${fn(l.ref)} ${u} por dia (nível de referência na ${horas?"reta":"curva"})</span>`).join("");
  apoio(p, fx, xmax, C, eixoX, cv, E);

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
            [rrM[j][0], `RR acumulado nas defasagens de 0 a ${M.lag} dias, para ${ref} em todos os ${M.lag+1} dias`+(e.ex==="horas"&&j===1?". Na reta imposta (1 grau de liberdade), é o RR de 4 h elevado ao quadrado, e não uma estimativa independente":"")]];
  }));
  const curvaTxt = e.ex==="horas"
    ? "A linha azul é uma reta imposta: com 1 grau de liberdade na exposição (spline natural), o logaritmo do RR cresce em linha reta com as horas por construção, de modo que ela não detecta limiar nem curvatura. A curva tracejada, de 3 graus de liberdade, é a alternativa flexível pré-definida (Quadro 3)."
    : "A curva do HAAT é estimada por spline penalizado com 15 graus de liberdade na exposição, o que permite curvatura (Quadro 3 traz os graus de liberdade efetivos), mas as extremidades têm poucos dias e intervalos largos.";
  $(p+"-note").textContent = `RR acumulado em 0 a ${M.lag} dias para uma exposição constante, mantida em todos os ${M.lag+1} dias, em relação a nenhuma exposição. A faixa é o intervalo de confiança de 95% a partir dos coeficientes da cross-basis e da sua matriz de covariância. A grade vai até ${fn(xmax)} ${u} por dia, o percentil 99 dos dias com exposição; acima disso há poucos dias. ${curvaTxt}`;
  $(p+"-note2").textContent = `Parte superior: RR da exposição ocorrida l dias antes do óbito, para cada defasagem l de 0 a ${M.lag}. Parte inferior: RR acumulado das defasagens de 0 até l, que é o produto dos RR por defasagem de 0 a l e corresponde a manter a exposição em todos esses dias. `+
    `Os dois níveis de exposição de referência são mantidos nos ${M.lag+1} dias. As duas partes têm escalas horizontais diferentes, e as barras são intervalos de confiança de 95% a partir da matriz de covariância dos coeficientes. Marcador cheio: intervalo que não inclui 1 (valores em negrito). A resposta à defasagem é um spline natural com 3 graus de liberdade. `+
    P.notaModelo(e.kd,e.ex,e.m)+P.texto.notaClima(e.m)+P.texto.notaCausa(e.m);

  // interpretação
  const ate = l => { let k=-1; while(k+1<l.lo.length && l.lo[k+1]>1) k++; return k };            // último lag da sequência inicial com IC acima de 1
  const partes = L.map(l=>{
    const k = ate(l), a = M.lag, sig = l.aclo[a]>1 ? "o intervalo fica acima de 1" : l.achi[a]<1 ? "o intervalo fica abaixo de 1" : "o intervalo inclui 1";
    const seq = k<0 ? "sem defasagem inicial com intervalo acima de 1" : k>=a ? "com intervalo acima de 1 em todas as defasagens" : `com intervalo acima de 1 até o lag ${k}`;
    return `com ${fn(l.ref)} ${u} por dia, o RR no mesmo dia (lag 0) é ${ic(l.rr[0],l.lo[0],l.hi[0])}, ${seq}; o RR acumulado em 0 a ${i3} dias é ${ic(l.ac[i3],l.aclo[i3],l.achi[i3])} e em 0 a ${a} dias é ${ic(l.ac[a],l.aclo[a],l.achi[a])}, isto é, ${P.fp((l.ac[a]-1)*100)} na contagem diária de óbitos (${sig})` });
  const tardio = L.some(l=>l.hi.some(v=>v<1));
  $(p+"-interp").innerHTML = `<span class="t">Interpretação</span>Neste recorte, ${partes.join(". Já ")}. `+
    (tardio?`Há defasagens em que o intervalo de confiança fica inteiro abaixo de 1. Isso pode refletir antecipação de óbitos de pessoas frágeis ou variação aleatória, e o modelo não separa as duas explicações. `:"")+
    `As estimativas descrevem associação em dados agregados, sem controle de fatores individuais.`;
  const sp = supDe(s); if(!sp) pedirSup(e);
  flexQuadro(s, fx); sqQuadro(s, sp);
}

// Texto que põe lado a lado o RR acumulado dos dois locais (só com dois recortes prontos)
function comparacao(S){
  const el = $("x-comp-txt");
  if(S.length<2 || S.some(s=>s.fase!=="ok")){ el.innerHTML = ""; return }
  const [a,b] = S, u = a.E.unidade, i = M.lag;
  const frases = a.cv.lag.map((la,j)=>{
    const lb = b.cv.lag[j];
    return `Com ${fn(la.ref)} ${u} por dia, o RR acumulado em 0 a ${i} dias é ${ic(la.ac[i],la.aclo[i],la.achi[i])} no local “${nm(local("x"))}” e ${ic(lb.ac[i],lb.aclo[i],lb.achi[i])} no local “${nm(local("y"))}”`;
  });
  const aninhado = [local("x"),local("y")].includes("Todos os locais");
  el.innerHTML = `<span class="t">Comparação entre os locais do óbito</span>${frases.join(". ")}. `+
    `${P.texto.grupos} `+
    (aninhado?`Como “Todos os locais” inclui os óbitos do outro recorte, as duas estimativas não são independentes. `:"")+
    `Os dois recortes usam a mesma escala vertical na Figura 2 e a mesma escala horizontal na Figura 3.`;
}

// ---------------------------------------------------------------- Figura 4: horas por dia x limiar do IC
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
  const so = $("x-hm-sig").checked, mostraN = !$("x-hm-n") || $("x-hm-n").checked;
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
      const rr=c.rr[i], lo=c.lo[i], hi=c.hi[i], nd=c.nd[i], ev=c.ev?c.ev[i]:null;
      const sub = mostraN ? `<span class="sub">${fn(nd)} d · ${ev==null?"–":fn(ev)} ev.</span>` : "";
      const suporte = `${fn(nd)} dias com exposição em ${ev==null?"número não disponível de":fn(ev)} evento(s) independente(s)`;
      const refc = K===36 && h===4 ? "outline:2px solid var(--azul);outline-offset:-2px;" : "";                 // dia com ≥ 4 h de IC ≥ 36 °C: combinação de referência do painel
      if(rr==null){ s += `<td style="${refc}color:var(--mut)" title="${nd<15?"menos de 15 dias com exposição no ajuste":"célula não estimada (poucos dias sem exposição ou falha do ajuste)"}\n${suporte}">–${sub}</td>`; return }
      const sig = lo>1 || hi<1, v = pctRR(rr), al = Math.min(Math.abs(v)/25,1)*.75;
      const cor = (so&&!sig) ? "transparent" : (v>=0 ? `rgba(181,84,28,${al})` : `rgba(22,65,145,${al})`);
      s += `<td style="${refc}background:${cor};${sig?"font-weight:700":"color:var(--mut)"}" title="IC ≥ ${K} °C por ≥ ${h} h/dia\nRR ${fr(rr)} (IC 95%: ${fr(lo)} a ${fr(hi)})\n${suporte}">${fr(rr)}${sub}</td>`;
    });
    s += "</tr>";
  });
  tab.innerHTML = s;
  nota.textContent = `Linhas: número mínimo de horas no dia com IC ≥ K (H). Colunas: limiar K (°C). Cada célula é um modelo próprio, com o mesmo GAM do modelo de referência `+
    `(binomial negativa, spline do tempo, ciclo anual e termo do período COVID, defasagem de 0 a ${M.lag} dias pela cross-basis do dlnm), em que a exposição é o dia ter pelo menos H horas com IC ≥ K. `+
    `O RR é o acumulado em 0 a ${M.lag} dias para a condição mantida em todos os ${M.lag+1} dias, em relação a nenhum dia com a condição, com IC 95% a partir da matriz de covariância dos coeficientes. `+
    `Células com menos de 15 dias com exposição, ou com menos de 30 dias sem exposição, no ajuste não são estimadas (–). Em negrito, RR com IC 95% que não inclui 1. `+
    `Em cada célula, d é o número de dias com exposição no ajuste e ev. é o número de eventos independentes, isto é, de conjuntos de dias com exposição separados por mais de ${M.lag} dias sem exposição (as janelas de defasagem de eventos diferentes não se tocam). Contorno azul: dia com ≥ 4 h de IC ≥ 36 °C, combinação de referência do painel, próxima do critério do NC 2 do protocolo (que usa “acima de” 36 °C). `+
    P.texto.notaClima(e.m)+P.texto.notaCausa(e.m);
  if(feitas<LIM.length){ it.innerHTML = `<span class="t">Interpretação</span>O texto fica disponível quando as ${LIM.length} colunas estiverem calculadas.`; return }
  const cel = [];
  LIM_ORD.forEach(K=>{ const c=col[K]; c.h.forEach((h,i)=>{ if(c.rr[i]!=null) cel.push({K,h,rr:c.rr[i],lo:c.lo[i],hi:c.hi[i],nd:c.nd[i]}) }) });
  if(!cel.length){ it.innerHTML = `<span class="t">Interpretação</span>Nenhuma combinação tem dias com exposição suficientes neste recorte.`; return }
  const sg = cel.filter(c=>c.lo>1), dn = cel.filter(c=>c.hi<1), mx = cel.reduce((a,b)=>b.rr>a.rr?b:a), mi = cel.reduce((a,b)=>b.rr<a.rr?b:a);
  const ordem = cel.map(c=>c.rr).sort((x,y)=>x-y), med = ordem.length%2 ? ordem[(ordem.length-1)/2] : (ordem[ordem.length/2-1]+ordem[ordem.length/2])/2;
  const ref = cel.find(c=>c.K===36&&c.h===4), a = cel.find(c=>c.K===32&&c.h===1), b = cel.find(c=>c.K===40&&c.h===1);
  const evt = c => c.ev==null ? "" : ` em ${fn(c.ev)} evento(s) independente(s)`;
  const icc = c => `${fr(c.rr)} (IC 95%: ${fr(c.lo)} a ${fr(c.hi)}; ${fn(c.nd)} dias com exposição${evt(c)})`;
  it.innerHTML = `<span class="t">Interpretação</span>Das ${cel.length} combinações estimadas, ${sg.length} têm RR acima de 1 com IC 95% que não inclui 1 e ${dn.length} têm RR abaixo de 1 com IC 95% que não inclui 1. `+
    (ref?`Para o dia com ≥ 4 h de IC ≥ 36 °C (combinação de referência do painel), RR = <b>${icc(ref)}</b>. `:"")+
    `Os RR das células estimadas vão de ${fr(mi.rr)} a ${fr(mx.rr)}, com mediana de ${fr(med)}. O maior valor (IC ≥ ${mx.K} °C por ≥ ${mx.h} h, ${fn(mx.nd)} dias com exposição${evt(mx)}) é o máximo entre ${cel.length} modelos correlacionados e tende a superestimar o efeito, de modo que não indica o melhor limiar. Células com poucos dias com exposição ou poucos eventos têm intervalos largos. `+
    (a&&b?`Ao subir o limiar de 32 para 40 °C (≥ 1 h), o RR passa de ${fr(a.rr)} para ${fr(b.rr)}${b.rr>a.rr?", no sentido de RR maior com calor mais intenso; esse gradiente favorece a associação, e os dados agregados não permitem inferir causalidade. ":", sem gradiente crescente. "}`:"")+
    `As células são aninhadas, pois um dia com mais horas também entra nas definições com menos horas, e não passaram por correção para comparações múltiplas. O padrão geral da tabela é mais informativo do que uma célula isolada. `+
    `O RR de cada célula descreve a associação em dados agregados, sem controle de fatores individuais.`;
}
function mapa(){
  if($("tab-exp").classList.contains("hide")) return;
  ativos().forEach(mapaSlot);
}

function desenhar(){ desenharCurvas(); mapa() }                    // as Figuras 2 e 3 são pedidas primeiro: o servidor as atende antes das colunas do mapa

P.ouvir.seg.push((kd,ex)=>{
  if(/^sup_/.test(ex)){ supVoo.delete(kd+"|"+ex.slice(4)); if($("tab-exp").classList.contains("hide")) return; desenharCurvas(); return }
  if(ex==="flex_horas"){ flexVoo.delete(kd); if($("tab-exp").classList.contains("hide")) return; if(ativos().some(p=>estado(p).kd===kd)) desenharCurvas(); return }
  if(eMapa(ex)){ voo.delete(idM(kd,+ex.slice(4))); mapa(); return }
  if(ativos().some(p=>{ const e=estado(p); return kd===e.kd && ex===e.ex })){ desenharCurvas(); mapa() }
});
P.ouvir.erro.push(msg=>{
  if(/^sup_/.test(msg.ex)){
    if(msg.pop!==P.pop()) return;
    const id = P.kd(msg.causa,msg.opc,msg.key)+"|"+msg.ex.slice(4); supVoo.delete(id);
    supFalhou.set(id, msg.codigo==="dados_mudaram" ? "os dados foram atualizados no servidor; recarregue a página" : String(msg.mensagem||"erro"));
    if(!$("tab-exp").classList.contains("hide")) desenharCurvas();
    return;
  }
  if(msg.ex==="flex_horas"){
    if(msg.pop!==P.pop()) return;
    const kd = P.kd(msg.causa,msg.opc,msg.key); flexVoo.delete(kd);
    flexFalhou.set(kd, msg.codigo==="dados_mudaram" ? "os dados foram atualizados no servidor; recarregue a página" : String(msg.mensagem||"erro"));
    if(!$("tab-exp").classList.contains("hide")) desenharCurvas();
    return;
  }
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
P.ouvir.base.push(()=>{ voo.clear(); falhou.clear(); flexVoo.clear(); flexFalhou.clear(); supVoo.clear(); supFalhou.clear(); desenhar() });
["x-local","x-local2","x-faixa","x-raca","x-exp","x-causa","x-r-covid","x-r-nc","x-r-clima","x-hm-sig","x-hm-n"].forEach(i=>{ const el=$(i); if(el) el.onchange=desenhar });
P.abas.exp = desenhar;
});

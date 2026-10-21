/* Aba "Causas específicas (CID-10)" (app Shiny): RR da contagem diária de óbitos com exposição ao calor para cada causa básica de 3 caracteres do recorte, com correção de Benjamini e Hochberg
   dentro de duas famílias fixas (principal: grupos do referencial; exploratória: demais causas). Todas as estimativas ficam visíveis por padrão; os filtros de
   capítulo e de significância só escolhem as linhas mostradas e não mudam o q.
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
// Famílias de testes do valor q. A principal é fixa: as causas avaliadas que pertencem aos grupos acima. A exploratória reúne as demais causas avaliadas.
const FAMILIAS = [{id:"p", rot:"Família principal", sub:"grupos do referencial (Morais et al.)", f:aPriori}, {id:"e", rot:"Família exploratória", sub:"demais causas avaliadas", f:c=>!aPriori(c)}];
const minus1 = t => /^[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]/.test(t) ? t[0].toLowerCase()+t.slice(1) : t;                // só a primeira letra, e não nas siglas (HAAT, UPA): o °C da unidade não pode virar °c
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
  ["k-fig","k-interp","k-interp2","k-leg"].forEach(i=>$(i).innerHTML=""); P.texto.ficha("k-sub", null);
  $("k-prog").textContent = ""; $("k-note").textContent = ""; $("k-note2").textContent = "";
  if(grafico){ grafico.destroy(); grafico = null }
}

function desenhar(){
  if($("tab-cid").classList.contains("hide")) return;
  const r = $("k-raca").value !== "Todas"; if(r) $("k-faixa").value = "Todas as idades"; $("k-faixa").disabled = r;
  $("k-faixa").title = r ? "As séries por raça/cor são calculadas para todas as idades; volte a Todas em raça/cor para escolher uma faixa etária." : "";
  const e = estado(), E = EXP[e.medida], got = P.cid(e.kd);
  if(!P.eleg(e.causa,e.cod).has(e.k)){
    limpar(); $("k-note").textContent = `Menos de ${M.min_obitos} óbitos ${e.cod!=="000"?"no ajuste ":""}nesta combinação de filtros: modelo não estimado.`;
    return;
  }
  P.texto.ficha("k-sub", {recorte:P.texto.recorte($("k-local").value,$("k-faixa").value,$("k-raca").value), kd:e.kd, ex:e.medida, m:e.m, filtrado:P.texto.filtrado($("k-local").value,$("k-faixa").value,$("k-raca").value),
    modelo:`GAM com defasagens distribuídas (DLNM), ajustado por REML a cada causa básica de 3 caracteres com pelo menos ${fn(M.cid_min)} óbitos nos dias do ajuste; família binomial negativa, com quase-Poisson quando a binomial negativa não converge`,
    linhas:[["Nível de exposição",`${fn(E.ref[e.nivel])} ${E.unidade} por dia, mantido em todos os ${M.lag+1} dias (RR acumulado em 0 a ${M.lag} dias)`],
            ["Família de testes",`valor q de Benjamini e Hochberg dentro de duas famílias fixas, a principal (causas avaliadas dos ${GRUPOS_REF.length} grupos do referencial) e a exploratória (demais causas), sem correção conjunta entre elas; os filtros de exibição não alteram o q`]]});
  const lista = got.cidlista;
  if(!lista){
    const f = falhou.get(idK(e.kd,"cidlista"));
    $("k-fig").innerHTML = ""; $("k-interp").innerHTML = ""; $("k-note").textContent = "";
    $("k-prog").textContent = f ? "Não foi possível obter as causas deste recorte: "+String(f).replace(/[<>&]/g,"") : "Obtendo a lista de causas deste recorte…";
    if(!f) enviarUm(e,"cidlista",true);
    return;
  }
  const conj = $("k-conj").value, cap = $("k-cap").value, soSig = $("k-sig").checked;
  // Famílias do valor q: a principal é fixa (as causas avaliadas que pertencem aos 15 grupos do referencial); a exploratória reúne as demais causas avaliadas.
  // Capítulo e significância só escolhem as linhas mostradas e não entram nesta divisão. A escolha "só a família principal" deixa de calcular a exploratória e não muda o q da principal.
  const fams = FAMILIAS.filter(F=>F.id==="p" || conj==="todas").map(F=>({...F, cids:lista.cid.filter(F.f)})).filter(F=>F.cids.length);
  const pedir = fams.flatMap(F=>F.cids);                           // a família principal é pedida primeiro
  $("k-prog").textContent = "";
  if(!pedir.length){
    $("k-fig").innerHTML = ""; $("k-interp").innerHTML = ""; $("k-filtro").textContent = ""; $("k-leg5").innerHTML = "";
    $("k-note").textContent = `Nenhuma causa tem pelo menos ${fn(M.cid_min)} óbitos nos dias do ajuste com esta combinação de recorte e família.`;
    return;
  }
  bombear(e, pedir.map(c=>exCid(c,e.medida)));
  const erros = [];
  fams.forEach(F=>{
    F.res = []; F.erros = [];
    F.cids.forEach(c=>{ const x = got[exCid(c,e.medida)];
      if(x) F.res.push({c, f:F.id, n:x.n, rr:x.rr[e.nivel], lo:x.lo[e.nivel], hi:x.hi[e.nivel], p:x.p[e.nivel]});
      else if(falhou.has(idK(e.kd,exCid(c,e.medida)))) F.erros.push(c) });
    F.completa = F.res.length + F.erros.length === F.cids.length;
    if(F.completa && F.res.length){ const q = bh(F.res.map(x=>x.p)); F.res.forEach((x,i)=>x.q = q[i]) }       // q dentro da família, com todas as causas dela
    F.vis = F.res.filter(x=>(cap==="all" || capOf(x.c)===cap) && (!soSig || !F.completa || x.q<0.05));            // só a exibição
    erros.push(...F.erros);
  });
  const feitas = fams.reduce((a,F)=>a+F.res.length+F.erros.length,0), completo = feitas === pedir.length;
  const dados = fams.reduce((a,F)=>a+F.res.length,0);
  const sg = fams.flatMap(F=>F.completa ? F.res.filter(x=>x.q<0.05) : []);
  const nivelTxt = `${fn(E.ref[e.nivel])} ${E.unidade} por dia`;
  $("k-prog").textContent = completo
    ? (erros.length ? `${erros.length} causa(s) sem estimativa por erro do servidor: ${erros.join(", ")}.` : "")
    : `Avaliando as causas: ${feitas} de ${pedir.length}. Na primeira vez cada causa leva de 3 a 10 segundos; depois o resultado fica guardado no servidor. O valor q de cada família aparece quando todas as causas dela estiverem calculadas.`;
  $("k-h2").textContent = `Causas básicas (CID-10, 3 caracteres): RR da contagem diária de óbitos com ${nivelTxt}`;
  const mostradas = fams.reduce((a,F)=>a+F.vis.length,0);
  const filtros = [cap!=="all" ? "capítulo "+(CAPS.find(([v])=>v===cap)||["",cap])[1] : null, soSig ? "só q < 0,05" : null].filter(Boolean);
  $("k-filtro").textContent = `Mostrando ${fn(mostradas)} de ${fn(pedir.length)} causas avaliadas${filtros.length ? " (filtros de exibição: "+filtros.join("; ")+")" : ", sem filtro de exibição"}${completo ? "" : " (as causas ainda em cálculo entram quando chegam)"}. `+
    `O valor q de cada causa é calculado dentro da sua família e não muda com esses filtros: ${fams.map(F=>`${F.rot.toLowerCase()}, ${fn(F.cids.length)} causa(s)`).join("; ")}.`;
  floresta(e, fams);

  // nota e interpretação
  const nomeMedida = minus1(E.nome);
  $("k-note").textContent = `RR acumulado em 0 a ${M.lag} dias com a exposição (${nomeMedida}) mantida em ${nivelTxt} em todos os ${M.lag+1} dias, em relação a nenhuma exposição, estimado em um modelo próprio de cada causa `+
    `(binomial negativa, spline do tempo, ciclo anual e termo do período COVID, defasagem pela cross-basis do dlnm). O IC 95% e o valor de p vêm da matriz de covariância dos coeficientes. `+
    `O valor q é o de Benjamini e Hochberg para a taxa de falsas descobertas e é calculado dentro de cada família de testes. A família principal reúne as causas avaliadas que pertencem aos ${GRUPOS_REF.length} grupos do referencial (lista fixa, definida antes dos resultados); `+
    `a família exploratória reúne as demais causas avaliadas e serve para levantar hipóteses. Não há correção conjunta entre as duas famílias. O q não depende do capítulo nem da significância escolhidos para exibir a lista; `+
    `muda com o recorte (local, faixa etária, raça/cor), a medida e o nível de exposição, as retiradas do ajuste e a população, que definem as causas com pelo menos ${fn(M.cid_min)} óbitos nos dias do ajuste e os valores de p. Ordenação por RR dentro de cada família.`+P.texto.notaClima(e.m)+P.texto.notaCausa(e.m);
  const ic = x => `${fr(x.rr)}; IC 95%: ${fr(x.lo)} a ${fr(x.hi)}`;
  if(!completo){ $("k-interp").innerHTML = `<span class="t">Interpretação</span>O texto fica disponível quando as ${pedir.length} causas estiverem calculadas.`; }
  else if(!dados){ $("k-interp").innerHTML = `<span class="t">Interpretação</span>Nenhuma causa pôde ser estimada neste recorte.`; }
  else {
    const item = x => `<b>${x.c}</b> ${NOME(x.c)} (RR ${ic(x)})`;
    const porFam = fams.filter(F=>F.res.length).map(F=>{
      const s = F.res.filter(x=>x.q<0.05), up = s.filter(x=>x.rr>1).sort((a,b)=>b.rr-a.rr), dw = s.filter(x=>x.rr<1).sort((a,b)=>a.rr-b.rr);
      return `Na ${F.rot.toLowerCase()} (${fn(F.res.length)} causas avaliadas), <b>${up.length}</b> têm RR acima de 1 e <b>${dw.length}</b> têm RR abaixo de 1 com q < 0,05 dentro da família`+
        (up.length ? `; as de maior RR são ${up.slice(0,4).map(item).join("; ")}` : "")+
        (F.id==="e" ? " (resultado exploratório, para levantar hipóteses)" : "")+". ";
    });
    const abaixo = sg.filter(x=>x.rr<1).sort((a,b)=>a.rr-b.rr);
    $("k-interp").innerHTML = `<span class="t">Interpretação</span>Com ${nivelTxt}: `+porFam.join("")+
      (abaixo.length ? `RR abaixo de 1 (por exemplo ${abaixo.slice(0,2).map(x=>x.c).join(", ")}) pode refletir antecipação de óbitos, mudanças de classificação ou variação aleatória, e o modelo não separa essas explicações. ` : "")+
      `As causas sem q < 0,05 não diferem de 1 após a correção dentro da família e aparecem em cinza. `+
      `Os RR descrevem associação em dados agregados, sem controle de fatores individuais, e cada causa tem poucos óbitos por dia, de modo que os intervalos são largos nas causas menos frequentes.`;
  }
  // série semanal da causa escolhida
  if(sel && !pedir.includes(sel)) sel = null;
  serie(e, completo ? padrao(sg) : null);
}
// causa mostrada na Figura 5b quando o usuário ainda não escolheu: a de maior RR acima de 1 entre as destacadas, ou a de menor q
const padrao = sg => { const a = sg.filter(x=>x.rr>1).sort((x,y)=>y.rr-x.rr)[0] || [...sg].sort((x,y)=>x.q-y.q)[0]; return a ? a.c : null };

// ---------------------------------------------------------------- Figura 5: floresta, um bloco por família
function floresta(e, fams){
  const blocos = fams.map(F=>({F, rows:[...F.vis].sort((a,b)=>b.rr-a.rr)}));
  const itens = []; blocos.forEach(b=>{ itens.push({t:"cab", b}); if(b.rows.length) b.rows.forEach(r=>itens.push({t:"lin", r, b})); else itens.push({t:"vazio", b}) });
  const nLin = blocos.reduce((a,b)=>a+b.rows.length,0), rh = nLin>70 ? 22 : 26;
  const W=1040, L=420, Rm=250, H=40+itens.length*rh+30;
  const vals = blocos.flatMap(b=>b.rows.flatMap(r=>[r.lo,r.hi]));
  const mn = Math.min(0.9,...vals)-.01, mx = Math.max(1.1,...vals)+.01, X = v=>L+(v-mn)/(mx-mn)*(W-L-Rm);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="RR por causa básica, por família de testes">`;
  const passo = (mx-mn)>1 ? .25 : (mx-mn)>.5 ? .1 : .05;
  for(let v=Math.ceil(mn/passo)*passo; v<=mx; v+=passo) s += `<line x1="${X(v)}" x2="${X(v)}" y1="26" y2="${H-26}" stroke="${css("--grid")}"/><text class="m" x="${X(v)}" y="${H-10}" text-anchor="middle">${fr(v)}</text>`;
  s += `<line x1="${X(1)}" x2="${X(1)}" y1="26" y2="${H-26}" stroke="${css("--mut")}"/>`;
  s += `<text class="m" x="8" y="16" style="font-weight:700">Causa (CID-10)</text><text class="m" x="${W-Rm+12}" y="16" style="font-weight:700">RR (IC 95%)</text><text class="m" x="${W-62}" y="16" text-anchor="end" style="font-weight:700">q (na família)</text><text class="m" x="${W-8}" y="16" text-anchor="end" style="font-weight:700">Óbitos</text>`;
  let zebra = 0;
  itens.forEach((it,i)=>{
    const y = 40+i*rh+rh/2, F = it.b.F;
    if(it.t==="cab"){
      const m = it.b.rows.length, tot = F.res.length;
      s += `<rect x="0" y="${y-rh/2}" width="${W}" height="${rh}" fill="${css("--grid")}" opacity=".55"/>`+
        `<text x="8" y="${y+4}"><tspan style="font-weight:700">${F.rot}</tspan> <tspan class="m">${F.sub} · ${fn(m)} de ${fn(F.cids.length)} causas${F.res.length<F.cids.length?" (calculando)":""} · ${F.completa ? "q de Benjamini e Hochberg dentro da família" : "q aparece quando todas as causas da família estiverem calculadas"}</tspan></text>`;
      return;
    }
    if(it.t==="vazio"){
      s += `<text class="m" x="${L}" y="${y+4}">${F.completa ? "Nenhuma causa da família atende aos filtros de exibição." : "Aguardando as primeiras causas…"}</text>`;
      return;
    }
    const r = it.r, sig = F.completa && r.q<0.05, c = !sig ? css("--cinza") : r.rr>1 ? css("--laranja") : css("--azul"), nome = NOME(r.c).slice(0,62), vaz = F.id==="e";
    if(zebra++%2===0) s += `<rect x="0" y="${y-rh/2}" width="${W}" height="${rh}" fill="${css("--faixa")}"/>`;
    if(r.c===sel) s += `<rect x="1" y="${y-rh/2+1}" width="${W-2}" height="${rh-2}" fill="none" stroke="${css("--azul")}" stroke-width="1.5" rx="3"/>`;
    s += `<text x="8" y="${y+4}"><tspan style="font-weight:650">${r.c}</tspan> <tspan class="m">${nome}</tspan></text>`;
    s += `<g data-c="${r.c}" data-f="${F.id}" style="cursor:pointer"><title>${r.c} ${NOME(r.c)}\n${F.id==="p" ? "Família principal"+(grupoRef(r.c)?" (grupo do referencial: "+grupoRef(r.c)+")":"") : "Família exploratória"}\nRR ${fr(r.rr)} (IC 95%: ${fr(r.lo)} a ${fr(r.hi)})\n${F.completa?"q = "+fmtP(r.q)+" (dentro da família) · ":""}p = ${fmtP(r.p)}\n${fn(r.n)} óbitos nos dias do ajuste · clique para ver a série semanal</title>`+
         `<rect x="${X(mn)}" y="${y-rh/2}" width="${W-L-Rm}" height="${rh}" fill="transparent"/><line x1="${X(r.lo)}" x2="${X(r.hi)}" y1="${y}" y2="${y}" stroke="${c}" stroke-width="2"/>`+
         `<circle cx="${X(r.rr)}" cy="${y}" r="4.5" fill="${vaz ? css("--card") : c}" stroke="${vaz ? c : css("--card")}" stroke-width="${vaz ? 2 : 1.5}"/></g>`;
    s += `<text x="${W-Rm+12}" y="${y+4}" style="${sig?"font-weight:650":""}">${fr(r.rr)} (${fr(r.lo)} a ${fr(r.hi)})</text><text class="m" x="${W-62}" y="${y+4}" text-anchor="end">${F.completa?fmtP(r.q):"…"}</text><text class="m" x="${W-8}" y="${y+4}" text-anchor="end">${fn(r.n)}</text>`;
  });
  $("k-fig").innerHTML = s+"</svg>";
  const lar = css("--laranja"), azl = css("--azul"), cin = css("--cinza"), ink = css("--ink");
  $("k-leg5").innerHTML = `<span><i class="dt" style="background:${lar}"></i>RR acima de 1 com q < 0,05</span><span><i class="dt" style="background:${azl}"></i>RR abaixo de 1 com q < 0,05</span><span><i class="dt" style="background:${cin}"></i>q ≥ 0,05</span>`+
    `<span><i class="dt" style="background:${ink}"></i>Família principal (marcador cheio)</span><span><i class="dt" style="background:transparent;border:2px solid ${ink};width:9px;height:9px"></i>Família exploratória (marcador vazado)</span>`;
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
        afterBody:it=>{ const i=it[0].dataIndex, L=[`Início da semana: ${dBR(sm.ini[i])}`]; if(ob[i]!=null && es[i]!=null) L.push(`Razão observado/esperado sem calor (O/E): ${fr(ob[i]/es[i])}`); if(sm.cov[i]) L.push("Semana do período COVID-19"); return L }}}}},
    plugins:[planoCov]});
  $("k-leg").innerHTML = `<span><i class="ln" style="background:${cz}"></i>Observado</span><span><i class="ln" style="background:${az};height:3px"></i>Esperado sem calor</span><span><i style="background:${mkCor(az,.17)}"></i>${FAIXA}</span><span><i class="dt" style="background:${ink}"></i>Acima da faixa</span>`;
  $("k-note2").textContent = `Mesmo modelo da Figura 1, ajustado a esta causa (${minus1(EXP[e.medida].nome)}). O esperado semanal é a soma dos esperados diários sem calor, e a faixa aproximada de variação de 95% usa a variância do modelo corrigida pela dispersão semanal (φ = ${fr(p.S.phi)}) e deixa de fora a incerteza dos coeficientes. `+
    `Sombreado cinza: semanas com dias sem registro no SIM. Barra cinza na base: semanas do período COVID-19.`+P.texto.notaClima(e.m)+P.texto.notaCausa(e.m);
  // razão observado/esperado sem calor (O/E), descritiva: semanas de calor (pelo menos 3 dias com IC máximo ≥ 36 °C, como na Figura 1) e demais semanas
  const g = f => { let O = 0, Ee = 0, n = 0, ac = 0; idx.forEach(i=>{ if(ob[i]!=null && es[i]!=null && !sm.cov[i] && sm.cl[i] && f(i)){ O += ob[i]; Ee += es[i]; n++; if(acima[i]!=null) ac++ } }); return {O, E:Ee, n, ac, raz:Ee ? O/Ee : NaN} };
  const H = g(i=>sm.nb[i]>=3), Nn = g(i=>sm.nb[i]<3), T = g(()=>true);
  $("k-interp2").innerHTML = T.n ? `<span class="t">Interpretação</span>Medida descritiva, que não é o RR do modelo: nas ${fn(H.n)} semanas de calor (pelo menos 3 dias com IC máximo ≥ 36 °C), foram observados ${fn(H.O)} óbitos contra ${fn(H.E,0)} esperados sem calor pelo modelo, razão observado/esperado sem calor (O/E) = <b>${isFinite(H.raz)?fr(H.raz):"–"}</b>; `+
    `nas demais ${fn(Nn.n)} semanas, ${fn(Nn.O)} contra ${fn(Nn.E,0)}, O/E = <b>${isFinite(Nn.raz)?fr(Nn.raz):"–"}</b>. Em ${fn(T.ac)} das ${fn(T.n)} semanas (${fn(100*T.ac/T.n,1)}%), o observado ficou acima do limite superior da faixa aproximada de variação de 95% em torno do esperado sem calor. `+
    `A O/E compara somas de óbitos e não tem intervalo de confiança; semanas acima da faixa têm explicações possíveis além do calor (epidemias, mudanças de registro), e a figura mostra a coincidência com o calor apenas por associação.` : "";
}

P.ouvir.seg.push((kd,ex)=>{ if(!eCid(ex)) return; voo.delete(idK(kd,ex)); agendar() });
P.ouvir.erro.push(msg=>{
  if(!eCid(msg.ex) || msg.pop!==P.pop()) return;
  const id = idK(P.kd(msg.causa,msg.opc,msg.key), msg.ex);
  voo.delete(id); falhou.set(id, msg.codigo==="dados_mudaram" ? "os dados foram atualizados no servidor; recarregue a página" : String(msg.mensagem||"erro"));
  agendar();
});
P.ouvir.base.push(()=>{ voo.clear(); falhou.clear(); sel = null; desenhar() });
["k-local","k-faixa","k-raca","k-nivel","k-conj","k-cap","k-sig","k-causa","k-r-covid","k-r-nc","k-r-clima"].forEach(i=>{ const el=$(i); if(el) el.onchange = desenhar });
$("k-exp").onchange = () => { niveis(); desenhar() };
P.abas.cid = desenhar;
});

/* Aba "Diagnósticos e sensibilidades" (app Shiny): como o modelo principal de um recorte se comporta e quanto o RR muda quando uma escolha do modelo muda.
   O navegador pede ao servidor o ajuste principal com todos os diagnósticos ("diag_<medida>") e, depois, uma análise de sensibilidade por vez
   ("sens_<análise>_<medida>"), no máximo MAX_VOO ao mesmo tempo; o quadro se completa linha a linha. Cada análise refaz o ajuste do mesmo recorte com uma só
   mudança (R/modelo_joao.R: SENS) e traz o resumo do diagnóstico residual. */
(window.PainelAbas = window.PainelAbas || []).push(function(P){
"use strict";
const {$, css, fn, fr, dBR, fillSel, nm, mkCor, M, EXP, KEXP} = P;
if(!$("tab-dia")) return;
const RACAS = [{v:"Todas",t:"Todas"},{v:"Branca",t:"Branca (referência)"},{v:"Preta",t:"Preta"},{v:"Parda",t:"Parda"},{v:"PPI",t:"Pretos, pardos e indígenas (PPI)"}];
const MAX_VOO = 2, ESPERA_MAX = 240000, REL = 0.20;                // REL: variação relativa do log-RR a partir da qual a mudança é tratada como relevante
const SENS = () => M.sens || [];

fillSel($("d-local"), M.locais.map(l=>({v:l,t:nm(l)})), "Todos os locais");
fillSel($("d-faixa"), M.faixas, "Todas as idades");
fillSel($("d-raca"), RACAS, "Todas");
fillSel($("d-exp"), KEXP.map(k=>({v:k,t:EXP[k].nome})), KEXP[0]);
if($("d-r-covid-t") && M.covid) $("d-r-covid-t").textContent = `Período COVID (${dBR(M.covid[0])} a ${dBR(M.covid[1])})`;

let grafico = null, timer = null;
const voo = new Map(), falhou = new Map();
const idK = (kd,ex) => kd+"|"+ex, eDg = ex => /^(diag|sens)_/.test(ex);
const chave = () => $("d-local").value+"|"+$("d-faixa").value+($("d-raca").value!=="Todas"?"|"+$("d-raca").value:"");
function estado(){ const m=P.modo("d"), cod=P.cod("d"), k=chave(); return {m, cod, k, causa:m.causa, kd:P.kd(m.causa,cod,k), medida:$("d-exp").value} }
const agendar = () => { clearTimeout(timer); timer = setTimeout(desenhar, 120) };
const fmtP = p => p==null ? "–" : p<0.001 ? "< 0,001" : p.toFixed(3).replace(".",",");
const pTxt = p => p!=null && p<0.001 ? "p < 0,001" : "p = "+fmtP(p);
const num = (v,d=2) => v==null ? "–" : fn(v,d);
const rrTxt = (rr,lo,hi) => `${fr(rr)} (${fr(lo)} a ${fr(hi)})`;
const exs = e => ["diag_"+e.medida, ...SENS().map(s=>`sens_${s.id}_${e.medida}`)];

function enviarUm(e, ex, forcar){
  const id = idK(e.kd,ex);
  if(P.dg(e.kd)[ex] || voo.has(id) || falhou.has(id)) return true;
  if(!forcar && voo.size>=MAX_VOO) return false;
  voo.set(id,Date.now()); P.enviar(e.k,ex,e.causa,e.cod); return true;
}
function bombear(e){
  const agora = Date.now(); voo.forEach((t,id)=>{ if(agora-t>ESPERA_MAX) voo.delete(id) });
  for(const ex of exs(e)) if(!enviarUm(e,ex,false)) break;
}

function limpar(){
  ["d-kpis","d-suave","d-sens","d-interp","d-sinterp"].forEach(i=>$(i).innerHTML=""); P.texto.ficha("d-sub", null);
  ["d-prog","d-note","d-note2","d-sprog","d-snote"].forEach(i=>$(i).textContent="");
  if(grafico){ grafico.destroy(); grafico = null }
}

// Variação relativa do log-RR da análise em relação ao ajuste principal, em cada nível de referência (NA se o log-RR principal é quase zero).
const variacao = (a,b) => [0,1].map(i=>{ const lb=Math.log(b.rr[i]); return Math.abs(lb)<0.01 ? null : (Math.log(a.rr[i])-lb)/lb });
const relevante = v => v.some(x=>x!=null && Math.abs(x)>=REL);
const fv = x => x==null ? "–" : (x>=0?"+":"−")+Math.abs(100*x).toFixed(0)+"%";

function kpis(p, E){
  const d = p.diag, c = d.conv, th = p.f==="nb" ? `binomial negativa (θ = ${fn(p.d,0)})` : `quase-Poisson (φ = ${fn(p.d,2)})`;
  const k = (v,l) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`;
  return [
    k(th.charAt(0).toUpperCase()+th.slice(1), `família do ajuste${p.f==="qp"?" (a binomial negativa não convergiu)":""}; ${fn(p.nd)} dias e ${fn(p.no)} óbitos no ajuste`),
    k(`${num(d.chi2_gl,2)}`, "χ² de Pearson ÷ graus de liberdade residuais (dispersão residual)"),
    k(`ρ(1) = ${num(d.rho1,2)}`, `autocorrelação dos resíduos no lag 1; ${fn(d.n_acf)} de ${fn(d.acf.length)} defasagens fora do limite aproximado de ±${num(d.lim,3)}`),
    k(pTxt(d.lb.p), `Ljung-Box com ${d.lb.gl} defasagens (Q = ${fn(d.lb.q,0)}; sem desconto dos graus de liberdade do modelo)`),
    k(`${num(d.cb.edf,1)} de ${fn(d.cb.k)}`, `graus de liberdade efetivos da base cruzada (${E.fun==="ns"?"resposta linear: não há penalização":"spline penalizado"}); ${num(d.gl_total,1)} no modelo inteiro`),
    k(c.ok ? "Convergiu" : "Não convergiu", `REML: ${c.msg||"sem mensagem"}${c.iter!=null?`, ${c.iter} iterações`:""}${c.grad!=null?`, gradiente máximo ${num(c.grad,4)}`:""}`)
  ].join("");
}

function suaves(p, E){
  const d = p.diag, S = d.suaves || [];
  const linhaCb = `<tr><td>Base cruzada (calor × defasagem)</td><td class="n">${fn(d.cb.k)}</td><td class="n">${num(d.cb.edf,1)}</td><td class="n">–</td><td class="n">–</td><td>${E.fun==="ns"?"Resposta linear imposta (1 gl na exposição)":"Spline penalizado com "+E.df+" gl na exposição (k' = "+E.df+" × 3 gl da defasagem); os gl efetivos medem a flexibilidade que a penalização deixou"}</td></tr>`;
  const leit = s => { const pouca = s.kindex<1 && s.p<0.05, perto = s.edf>0.9*s.k; return pouca ? "k-index < 1 com p baixo: a base pode ser pequena" : perto ? "gl efetivos perto do limite da base (k')" : "sem sinal de base pequena" };
  $("d-suave").innerHTML = `<thead><tr><th>Termo</th><th class="n">k' (dimensão da base)</th><th class="n">gl efetivos</th><th class="n">k-index</th><th class="n">p do k-index</th><th>Leitura</th></tr></thead><tbody>${linhaCb}`+
    S.map(s=>`<tr><td>${s.termo}</td><td class="n">${num(s.k,0)}</td><td class="n">${num(s.edf,1)}</td><td class="n">${num(s.kindex,2)}</td><td class="n">${fmtP(s.p)}</td><td>${leit(s)}</td></tr>`).join("")+`</tbody>`;
}

function acf(p){
  const d = p.diag, az = css("--azul"), cz = css("--cinza"), tickc = css("--mut"), gridc = css("--grid");
  const lags = d.acf.map((_,i)=>i+1);
  if(grafico) grafico.destroy();
  grafico = new Chart($("d-acf"),{type:"bar",data:{labels:lags,datasets:[
    {type:"bar",label:"ACF dos resíduos",data:d.acf,backgroundColor:d.acf.map(v=>Math.abs(v)>d.lim?az:mkCor(cz,.7)),borderWidth:0,order:2},
    {type:"line",label:"Limite superior",data:lags.map(()=>d.lim),borderColor:css("--ink"),borderDash:[5,4],borderWidth:1,pointRadius:0,order:1},
    {type:"line",label:"Limite inferior",data:lags.map(()=>-d.lim),borderColor:css("--ink"),borderDash:[5,4],borderWidth:1,pointRadius:0,order:1}
  ]},options:{responsive:true,maintainAspectRatio:false,animation:false,
    scales:{x:{grid:{display:false},ticks:{color:tickc},title:{display:true,text:"Defasagem (dias)",color:tickc}},
            y:{grid:{color:gridc},ticks:{color:tickc},title:{display:true,text:"Autocorrelação",color:tickc}}},
    plugins:{legend:{display:false},tooltip:{filter:i=>i.dataset.label==="ACF dos resíduos",callbacks:{title:i=>`Defasagem de ${i[0].label} dia(s)`,label:q=>`Autocorrelação: ${fn(q.parsed.y,3)}${Math.abs(q.parsed.y)>d.lim?" (fora do limite)":""}`}}}}});
}

function interpDiag(p, E){
  const d = p.diag, forte = d.lb.p<0.05 && d.n_acf>=0.5*d.acf.length;
  const cc = d.covid_cc, marcados = (d.suaves||[]).filter(s=>s.kindex<1 && s.p<0.05);
  return `<span class="t">Interpretação</span>`+
    (forte ? `Os resíduos do modelo principal ainda têm dependência no tempo: a autocorrelação no lag 1 é ${num(d.rho1,2)} e decai devagar (${num(d.rho7,2)} no lag 7), com ${fn(d.n_acf)} das ${fn(d.acf.length)} defasagens fora do limite aproximado de ±${num(d.lim,3)} e Ljung-Box com ${pTxt(d.lb.p)}. Há variação de curto e médio prazo na mortalidade (epidemias, ondas de frio, mudanças de registro) que o spline do tempo e o ciclo anual não descrevem. Os intervalos de confiança de 95% dos RR são calculados como se os resíduos fossem independentes e, por isso, <b>podem ser estreitos demais</b>; a faixa semanal usa a dispersão φ, que não corrige o IC do RR. Os RR devem ser lidos como estimativas com precisão provavelmente menor que a informada.`
          : `Os resíduos do modelo principal mostram pouca autocorrelação (lag 1 = ${num(d.rho1,2)}; ${fn(d.n_acf)} de ${fn(d.acf.length)} defasagens fora do limite; Ljung-Box com ${pTxt(d.lb.p)}). Isso não prova que os IC estejam bem calibrados, mas não indica dependência residual evidente.`)+
    ` A dispersão residual (χ² ÷ gl = ${num(d.chi2_gl,2)}) fica perto de 1 por construção na binomial negativa, porque θ é estimado nos mesmos dados, e por isso informa pouco sobre a dependência.`+
    (marcados.length ? ` O k-index ficou abaixo de 1 com p baixo em ${marcados.map(s=>s.termo).join(" e ")}, o que sugere base pequena para o padrão dos dados; a análise com o dobro de nós no spline do tempo, no Quadro 2, mostra se isso muda o RR.` : ``)+
    (cc ? ` <b>Spline cíclico da pandemia:</b> o termo s(COVID) usa um spline cíclico sobre o índice de dias do período (0 fora dele). Pela construção do spline cíclico, o valor no último dia do período é forçado a coincidir com o do índice 0: o termo vale ${num(cc.fora,3)} fora do período, ${num(cc.primeiro,3)} no primeiro dia e ${num(cc.ultimo,3)} no último, com pico de ${num(cc.pico,3)} (escala do log). As análises de sensibilidade com o termo não cíclico, sem o termo e com o período retirado mostram quanto o RR depende dessa escolha.` : ``);
}

function tabelaSens(e, got, E){
  const base = got["diag_"+e.medida];
  const rotulo = (nome,ex) => { const p=got[ex], f=falhou.get(idK(e.kd,ex)); return {p, f} };
  const cab = `<thead><tr><th>Análise</th><th class="n">Dias no ajuste</th><th class="n">Óbitos no ajuste</th><th class="n">Dias com ≥ 4 h de IC ≥ 36 °C (eventos)</th><th class="n">RR com ${fn(E.ref[0])} ${E.unidade} por dia (IC 95%)</th><th class="n">RR com ${fn(E.ref[1])} ${E.unidade} por dia (IC 95%)</th><th class="n">ρ(1) dos resíduos</th><th class="n">Ljung-Box (p)</th><th class="n">χ² ÷ gl</th></tr></thead>`;
  const linha = (rot, p, mudou, f) => {
    if(!p) return `<tr><td>${rot}</td><td colspan="8">${f ? "não foi possível ajustar: "+String(f).replace(/[<>&]/g,"") : "calculando o modelo…"}</td></tr>`;
    const v = base && p!==base ? variacao(p,base) : null, marca = v && relevante(v);
    const cel = i => `${rrTxt(p.rr[i],p.lo[i],p.hi[i])}${v?`<br><span class="dl">variação do log-RR: ${fv(v[i])}</span>`:""}`;
    return `<tr${marca?' class="rel"':""}><td>${rot}${marca?' <span title="Variação de 20% ou mais no log-RR em relação ao ajuste principal">●</span>':""}</td><td class="n">${fn(p.nd)}</td><td class="n">${fn(p.no)}</td><td class="n">${fn(p.dias_calor)} (${fn(p.eventos)})</td><td class="n">${cel(0)}</td><td class="n">${cel(1)}</td><td class="n">${num(p.res.rho1,2)}</td><td class="n">${fmtP(p.res.lb_p)}</td><td class="n">${num(p.res.chi2_gl,2)}</td></tr>`;
  };
  let h = linha("Ajuste principal", base, false, falhou.get(idK(e.kd,"diag_"+e.medida)));
  let grupo = null;
  SENS().forEach(s=>{
    const ex = `sens_${s.id}_${e.medida}`, p = got[ex], f = falhou.get(idK(e.kd,ex));
    if(s.grupo!==grupo){ grupo = s.grupo; h += `<tr class="gr"><td colspan="9">${grupo}</td></tr>` }
    h += linha(p ? p.rot : s.rot, p, false, f);
  });
  $("d-sens").innerHTML = cab+"<tbody>"+h+"</tbody>";
}

function interpSens(e, got, E){
  const base = got["diag_"+e.medida]; if(!base) return "";
  const ok = SENS().map(s=>got[`sens_${s.id}_${e.medida}`]).filter(Boolean);
  if(!ok.length) return "";
  const pt = i => ok.map(p=>p.rr[i]), mn = i => Math.min(...pt(i)), mx = i => Math.max(...pt(i));
  const rel = ok.filter(p=>relevante(variacao(p,base)));
  const compl = ok.length===SENS().length;
  const txt = i => `${fr(mn(i))} a ${fr(mx(i))} (ajuste principal: ${fr(base.rr[i])})`;
  const k_d = got[`sens_k_dobro_${e.medida}`], dow = got[`sens_dow_${e.medida}`];
  return `<span class="t">Interpretação</span>`+
    `Com ${fn(E.ref[0])} ${E.unidade} por dia, o RR acumulado das ${fn(ok.length)} análises ${compl?"":"já concluídas "}vai de ${txt(0)}; com ${fn(E.ref[1])} ${E.unidade} por dia, de ${txt(1)}. `+
    (rel.length ? `Mudam o log-RR em ${REL*100}% ou mais em algum nível de referência: ${rel.map(p=>p.rot.toLowerCase()).join("; ")}. Nessas análises a amostra, a especificação do termo temporal ou o tratamento de dias sem clima altera o que o modelo atribui ao calor, e a estimativa principal depende dessa escolha; compare os dias e os eventos de calor de cada linha com os do ajuste principal. `
              : `Nenhuma análise muda o log-RR em ${REL*100}% ou mais, e as estimativas ficam próximas da principal. `)+
    (k_d ? `Com o dobro de nós no spline do tempo, a autocorrelação no lag 1 passa de ${num(base.diag.rho1,2)} para ${num(k_d.res.rho1,2)}${k_d.res.rho1>0.8*base.diag.rho1?", uma redução pequena: o excesso de dependência não vem só da dimensão do spline":""}. `:"")+
    (dow ? `O termo de dia da semana ${Math.abs(variacao(dow,base)[0]||0)<0.05?"quase não altera":"altera"} o log-RR (${fv(variacao(dow,base)[0])} com ${fn(E.ref[0])} ${E.unidade} por dia). `:"")+
    `O critério é a mudança do valor estimado, e não se o intervalo de confiança cruza o 1.${compl?"":" O quadro se completa à medida que o servidor termina cada modelo."}`;
}

function desenhar(){
  if($("tab-dia").classList.contains("hide")) return;
  const r = $("d-raca").value !== "Todas"; if(r) $("d-faixa").value = "Todas as idades"; $("d-faixa").disabled = r;
  $("d-faixa").title = r ? "As séries por raça/cor são calculadas para todas as idades; volte a Todas em raça/cor para escolher uma faixa etária." : "";
  const e = estado(), E = EXP[e.medida], got = P.dg(e.kd);
  if(!P.eleg(e.causa,e.cod).has(e.k)){
    limpar(); $("d-note").textContent = `Menos de ${M.min_obitos} óbitos ${e.cod!=="000"?"no ajuste ":""}nesta combinação de filtros: modelo não estimado.`;
    return;
  }
  P.texto.ficha("d-sub", {recorte:P.texto.recorte($("d-local").value,$("d-faixa").value,$("d-raca").value), kd:e.kd, ex:e.medida, m:e.m, filtrado:P.texto.filtrado($("d-local").value,$("d-faixa").value,$("d-raca").value),
    linhas:[["Análises","cada linha do Quadro 2 é um ajuste do mesmo recorte, com a mesma causa e as mesmas retiradas do ajuste, mudando uma só escolha"]]});
  bombear(e);
  const base = got["diag_"+e.medida], fb = falhou.get(idK(e.kd,"diag_"+e.medida));
  if(!base){
    ["d-kpis","d-suave","d-interp"].forEach(i=>$(i).innerHTML=""); $("d-note").textContent = ""; $("d-note2").textContent = "";
    if(grafico){ grafico.destroy(); grafico = null }
    $("d-prog").textContent = fb ? "Não foi possível ajustar o modelo principal deste recorte: "+String(fb).replace(/[<>&]/g,"") : "Calculando o modelo principal e os diagnósticos…";
  } else {
    $("d-prog").textContent = "";
    $("d-kpis").innerHTML = kpis(base,E); suaves(base,E); acf(base);
    $("d-note2").textContent = `Barras azuis: defasagens fora do limite aproximado de 95% (±1,96 ÷ raiz de n, com n = ${fn(base.diag.n)} dias no ajuste), que vale para resíduos independentes. A ACF ignora os dias fora do ajuste.`;
    $("d-note").textContent = `k-index e valor de p do mgcv::k.check (200 permutações, semente fixa): um k-index abaixo de 1 com p baixo sugere que a base do spline é pequena para o padrão dos dados. Dimensão da base k' do modelo de referência: spline do tempo com ${fn(M.k_tempo)} nós (cresce com o número de anos da série), ciclo anual com 6 e termo da COVID-19 com 8 (k' desconta a restrição de identificabilidade).`;
    $("d-interp").innerHTML = interpDiag(base,E);
  }
  const feitos = exs(e).filter(x=>got[x]).length;
  $("d-sprog").textContent = feitos<exs(e).length && !fb ? `${fn(feitos)} de ${fn(exs(e).length)} modelos concluídos. Cada linha leva de 2 a 10 segundos na primeira vez.` : "";
  tabelaSens(e,got,E);
  $("d-sinterp").innerHTML = interpSens(e,got,E);
  $("d-snote").textContent = `Dias com ≥ 4 h de IC ≥ 36 °C: dias no ajuste que atendem a esse critério; evento: sequência de dias seguidos que o atendem. A variação do log-RR é (log RR da análise − log RR principal) ÷ log RR principal, em cada nível de referência; ● marca variações de ${REL*100}% ou mais. A coluna de resíduos resume o diagnóstico de cada ajuste (mesmo cálculo do Quadro 1). O termo de dia da semana não faz parte do modelo de referência. Defasagem máxima de 7 e 14 dias refaz a base cruzada e a retirada dos dias sem clima com essa janela.`;
}
const minus1 = t => /^[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]/.test(t) ? t[0].toLowerCase()+t.slice(1) : t;                // só a primeira letra, e não nas siglas (HAAT, UPA): o °C da unidade não pode virar °c

P.ouvir.seg.push((kd,ex)=>{ if(!eDg(ex)) return; voo.delete(idK(kd,ex)); agendar() });
P.ouvir.erro.push(msg=>{
  if(!eDg(msg.ex) || msg.pop!==P.pop()) return;
  const id = idK(P.kd(msg.causa,msg.opc,msg.key), msg.ex);
  voo.delete(id); falhou.set(id, msg.codigo==="dados_mudaram" ? "os dados foram atualizados no servidor; recarregue a página" : String(msg.mensagem||"erro"));
  agendar();
});
P.ouvir.base.push(()=>{ voo.clear(); falhou.clear(); desenhar() });
["d-local","d-faixa","d-raca","d-exp","d-causa","d-r-covid","d-r-nc","d-r-clima"].forEach(i=>{ const el=$(i); if(el) el.onchange = desenhar });
P.abas.dia = desenhar;
});

"""Teste da página no navegador (Playwright). Uso: python3 testes/teste_pagina.py painel_figura1.html [pasta_de_capturas]
Percorre todos os recortes (local x faixa etária e local x raça/cor), as duas escalas e as duas medidas de calor; confere que nada quebra,
que o gráfico desenha e que o recorte muda os indicadores (a falha que motivou esta versão: razão igual a 1,00 para qualquer recorte)."""
import sys, os, re, itertools
from playwright.sync_api import sync_playwright

html = os.path.abspath(sys.argv[1]); shots = sys.argv[2] if len(sys.argv) > 2 else None
if shots: os.makedirs(shots, exist_ok=True)
erros, falhas = [], []
def falha(msg): falhas.append(msg); print("FALHA:", msg, flush=True)

with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1320, "height": 1100})
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    pg.goto("file://" + html)
    pg.wait_for_function("document.querySelectorAll('#s-kpis .kpi').length>0", timeout=90000)
    sel = lambda i, v: pg.select_option("#" + i, v)
    kpis = lambda: pg.eval_on_selector_all("#s-kpis .kpi", "els=>els.map(e=>e.querySelector('.v').innerText+' | '+e.querySelector('.l').innerText)")
    pixels = lambda: pg.evaluate("""()=>{const c=document.getElementById('s-chart'),g=c.getContext('2d'),d=g.getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<d.length;i+=4) if(d[i]>0) n++;return n}""")
    opcoes = lambda i: pg.eval_on_selector_all(f"#{i} option", "os=>os.map(o=>o.value)")
    def razao(txt):                                         # valor do cartão da razão O/E nos KPIs: "1,05 | Razão observado/esperado sem calor (O/E): ..."
        for t in txt:
            m = re.match(r"([\d,]+) \| Razão observado/esperado sem calor \(O/E\).* nas \d+ semanas", t)
            if m: return float(m.group(1).replace(",", "."))
    def rr(txt):
        if len(txt) < 2: return None                         # recorte sem série (menos de 300 óbitos)
        m = re.match(r"([\d,]+) \(IC 95%: ([\d,]+) a ([\d,]+)\)", txt[1]); return tuple(float(x.replace(",", ".")) for x in m.groups())

    locais, faixas, exps = opcoes("s-local"), opcoes("s-faixa"), opcoes("s-exp")
    print("locais", len(locais), "| faixas", faixas, "| medidas", exps, flush=True)
    assert faixas[1:] == ["0-4", "5-9", "10-19", "20-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+"], "faixas da UNICEF"
    n = 0
    for esc in ["sem", "dia"]:
        sel("s-esc", esc)
        for ex in exps:
            sel("s-exp", ex)
            for L in locais:
                sel("s-local", L)
                for raca in ["Todas", "Branca", "Preta", "Parda", "PPI"]:
                    sel("s-raca", raca)
                    for fx in (faixas if raca == "Todas" else ["Todas as idades"]):
                        if raca == "Todas": sel("s-faixa", fx)
                        k = kpis(); n += 1
                        nota = pg.inner_text("#s-note")
                        if nota.startswith("Menos de"): continue
                        if not k or any(("NaN" in t or "undefined" in t) for t in k): falha(f"{esc}/{ex}/{L}/{raca}/{fx}: KPI inválido {k}")
                        elif pixels() < 2000: falha(f"{esc}/{ex}/{L}/{raca}/{fx}: gráfico em branco")
    print(n, "combinações percorridas", flush=True)

    # rótulos sem acento quebrado
    for i in ["s-local", "s-faixa", "s-raca", "s-exp"]:
        for t in pg.eval_on_selector_all(f"#{i} option", "os=>os.map(o=>o.textContent)"):
            if re.search(r"<[0-9a-fU+]{2,}>", t): falha(f"rótulo com codificação quebrada em #{i}: {t}")
    print("locais:", pg.eval_on_selector_all("#s-local option", "os=>os.map(o=>o.textContent)"), flush=True)

    # o recorte tem de mudar o resultado (semanal, medida 'horas', série inteira)
    sel("s-esc", "sem"); sel("s-exp", exps[0]); sel("s-local", "Todos os locais"); sel("s-crit", "ic"); sel("s-ini", pg.eval_on_selector("#s-ini", "e=>e.options[0].value")); sel("s-fim", pg.eval_on_selector("#s-fim", "e=>e.options[e.options.length-1].value"))
    res = {}
    for raca in ["Todas", "Branca", "Preta", "Parda", "PPI"]:
        sel("s-raca", raca); k = kpis(); res[raca] = (razao(k), rr(k))
    print("razão nas semanas de calor e RR (4 h) por raça/cor:", res)
    if any(abs(v[0] - 1) < 0.0049 for v in res.values()): falha(f"razão colada em 1,00: {[v[0] for v in res.values()]}")
    if len(set(res.values())) < 3: falha("raça/cor: resultados iguais para recortes diferentes")
    sel("s-raca", "Todas")
    def coleta(seletor, valores):
        out = {}
        for v in valores:
            sel(seletor, v); k = kpis()
            if len(k) >= 2: out[v] = (razao(k), rr(k))          # recorte sem série (menos de 300 óbitos) não tem KPIs
        return out
    por_local = coleta("s-local", locais); sel("s-local", "Todos os locais")
    print("por local:", por_local)
    if len(set(por_local.values())) < 6: falha("locais diferentes com o mesmo resultado")
    if len({v[0] for v in por_local.values()}) < 4: falha("razão observado/esperado sem calor (O/E) quase igual entre locais")
    por_faixa = coleta("s-faixa", faixas)
    print("por faixa:", por_faixa)
    if len(set(por_faixa.values())) < 7: falha("faixas diferentes com o mesmo resultado")
    # a medida HAAT também varia entre recortes
    sel("s-exp", exps[1]); sel("s-faixa", "Todas as idades")
    rh = coleta("s-local", locais[:4]); print("HAAT por local:", rh)
    if len(set(rh.values())) < 3: falha("HAAT: RR iguais entre locais")
    sel("s-exp", exps[0]); sel("s-local", "Todos os locais")

    # capturas
    sel("s-local", "Domicílio"); sel("s-faixa", "80+")
    if shots: pg.screenshot(path=os.path.join(shots, "semanal_domicilio_80.png"), full_page=True)
    sel("s-local", "Todos os locais"); sel("s-faixa", "Todas as idades"); sel("s-raca", "Preta")
    if shots: pg.screenshot(path=os.path.join(shots, "semanal_preta.png"), full_page=True)
    sel("s-raca", "Todas"); sel("s-esc", "dia")
    if shots: pg.screenshot(path=os.path.join(shots, "diaria_todos.png"), full_page=True)
    sel("s-exp", exps[1])
    if shots: pg.screenshot(path=os.path.join(shots, "diaria_haat.png"), full_page=True)
    # CSV
    with pg.expect_download() as d: pg.click("#s-csv")
    txt = open(d.value.path(), encoding="utf-8-sig").read().splitlines(); print("CSV diário:", len(txt), "linhas;", txt[0][:90])
    if len(txt) < 300: falha("CSV diário curto")
    cab = [l for l in txt if not l.startswith("# ") and l.strip()][0]
    if not txt[0].startswith("# Dados:") or not any(l.startswith("# Período do ajuste:") for l in txt) or not any(l.startswith("# Ressalvas:") for l in txt): falha("CSV diário sem a ficha do resultado")
    if not cab.startswith("dia;observado;esperado_sem_calor;faixa_inferior_95;faixa_superior_95;horas_ic_ge_36;dia_com_4h_ic_ge_36;dia_com_exposicao_t_a_t3"): falha("CSV diário: cabeçalho fora do vocabulário do painel: " + cab[:80])
    # ficha do resultado na página estática (item 10 da revisão): período do ajuste vem do payload, retiradas do ajuste principal, família do modelo e ressalvas
    sel("s-esc", "sem")
    F = pg.evaluate("()=>Object.fromEntries([...document.querySelectorAll('#s-ficha dl>div')].map(d=>[d.querySelector('dt').textContent,d.querySelector('dd').textContent]))")
    if not re.fullmatch(r"\d\d/\d\d/\d{4} a \d\d/\d\d/\d{4} \([\d.]+ dias e [\d.]+ óbitos\)", F.get("Período do ajuste", "")): falha(f"ficha: período do ajuste ausente ou mal formado: {F.get('Período do ajuste')}")
    if "meses de registro não consolidado" not in F.get("Retiradas", "").split("Mantidos")[0] or "dias sem dado de clima" not in F.get("Retiradas", "").split("Mantidos")[0]: falha(f"ficha: retiradas do ajuste principal: {F.get('Retiradas')}")
    if not re.search(r"família (binomial negativa|quase-Poisson)", F.get("Modelo", "")) or "estudo ecológico" not in F.get("Ressalvas", "") or "Dados" not in F: falha(f"ficha: modelo, ressalvas ou dados ausentes: {list(F)}")
    if "Índice de Calor (IC)" not in pg.inner_text("#sub") or "não são alertas operacionais" not in pg.inner_text("#sub"): falha("cabeçalho sem o Índice de Calor (IC) por extenso e o aviso sobre alertas")
    # métodos
    pg.click("button[data-tab=sobre]")
    mt = pg.inner_text("#tab-sobre")
    for trecho in ["binomial negativa", "0-4, 5-9, 10-19", "registro não consolidado"]:
        if trecho not in mt: falha(f"Métodos sem '{trecho}'")
    if not re.search(r"\d{1,3}(\.\d{3})+ óbitos por causas naturais entre", mt): falha("Métodos sem o total de óbitos por causas naturais")      # o valor muda a cada versão dos dados
    if shots: pg.screenshot(path=os.path.join(shots, "metodos.png"), full_page=True)
    b.close()

if erros: falhas.append("erros no console: " + "; ".join(sorted(set(erros))[:5])); print(falhas[-1])
print("FALHAS:", "nenhuma" if not falhas else len(falhas))
sys.exit(1 if falhas else 0)

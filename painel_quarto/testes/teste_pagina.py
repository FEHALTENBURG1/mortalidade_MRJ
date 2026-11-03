"""Teste da página no navegador (Playwright). Uso: python3 testes/teste_pagina.py painel_figura1.html [pasta_de_capturas]
Percorre todos os recortes (local x faixa etária e local x raça/cor), as duas escalas e as duas medidas de calor; confere que nada quebra,
que o gráfico desenha e que o recorte muda os indicadores (a falha que motivou esta versão: razão igual a 1,00 para qualquer recorte).
O intervalo de confiança não vem escrito nos indicadores: fica em data-ic e aparece ao passar o cursor. Por padrão o que não tem poder estatístico (IC 95% que inclui 1)
fica oculto; o teste marca a caixa da barra lateral para percorrer tudo e confere o comportamento padrão no fim. Na página estática (sem servidor) o período
de análise e o comparativo não existem, porque dependem de reajustar o modelo."""
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
    kpis = lambda: pg.eval_on_selector_all("#s-kpis .kpi", "els=>els.map(e=>e.innerText.replace(/\\n/g,' | ') + (e.dataset.ic ? ' [' + e.dataset.ic + ']' : ''))")      # o IC 95% vem de data-ic
    pixels = lambda: pg.evaluate("""()=>{const c=document.getElementById('s-chart'),g=c.getContext('2d'),d=g.getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<d.length;i+=4) if(d[i]>0) n++;return n}""")
    opcoes = lambda i: pg.eval_on_selector_all(f"#{i} option", "os=>os.map(o=>o.value)")
    def razao(txt):                                         # primeiro número depois de "observado ÷ esperado" nos KPIs: "1,05 | observado ÷ esperado ..."
        for t in txt:
            m = re.match(r"([\d,]+) \| observado ÷ esperado sem calor nas \d+ semanas de calor", t)
            if m: return float(m.group(1).replace(",", "."))
    def rr(txt):
        if len(txt) < 2: return None                         # recorte sem série (menos de 300 óbitos)
        m = re.match(r"([\d,]+) \| RR acumulado.*\[IC 95%: ([\d,]+) a ([\d,]+)\]", txt[1]); return tuple(float(x.replace(",", ".")) for x in m.groups())

    if pg.is_checked("#s-nsig"): falha("a caixa 'mostrar também o que não tem poder estatístico' devia começar desmarcada")
    pg.check("#s-nsig")                                       # percorre tudo com todos os indicadores visíveis; o padrão (ocultar) é conferido no fim
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
    if len({v[0] for v in por_local.values()}) < 4: falha("razão observado ÷ esperado quase igual entre locais")
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
    # intervalo de confiança só em dica e poder estatístico por padrão
    sel("s-esc", "sem"); sel("s-exp", exps[0]); sel("s-local", "Todos os locais"); sel("s-faixa", "Todas as idades"); sel("s-raca", "Todas")
    sem_dicas = pg.evaluate("()=>{const c=document.body.cloneNode(true); c.querySelectorAll('title,script,style').forEach(n=>n.remove()); return c.textContent}")
    if re.search(r"IC 95%:? ?-?[\d.,]+ a |\(IC 95%:? ?\d", sem_dicas): falha("o IC 95% aparece escrito na página (deveria estar só em dica)")
    for i in ("lat-per", "lat-cmp"):
        if pg.is_visible("#" + i): falha(f"#{i} (período e comparativo) não deveria aparecer na página estática")
    n_todos = len(pg.query_selector_all("#s-kpis .kpi")); pg.uncheck("#s-nsig")
    ics = pg.eval_on_selector_all("#s-kpis .kpi[data-ic]", "els=>els.map(e=>e.dataset.ic)")
    for ic in ics:
        lo, hi = (float(x.replace(".", "").replace(",", ".")) for x in re.match(r"IC 95%: (-?[\d.]*,\d+) a (-?[\d.]*,\d+)", ic).groups())
        if not (lo >= 1.0 or hi <= 1.0): falha(f"padrão: indicador com IC 95% que inclui 1 ficou visível: {ic}")
    if len(pg.query_selector_all("#s-kpis .kpi")) > n_todos: falha("desmarcar a caixa não pode aumentar o número de indicadores")
    if ics:
        pg.hover("#s-kpis .kpi[data-ic]")
        if "IC 95%" not in pg.evaluate("()=>getComputedStyle(document.querySelector('#s-kpis .kpi[data-ic]'),'::after').content"): falha("o IC 95% não aparece como dica ao passar o cursor")
    pg.check("#s-nsig")
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

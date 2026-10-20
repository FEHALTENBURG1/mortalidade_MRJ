"""Teste do app Shiny no navegador (Playwright).

Uso, a partir da pasta do projeto:
  PAINEL_CACHE=/caminho/do/cache python3 testes/teste_app.py [--url http://127.0.0.1:PORTA] [--capturas pasta]
Sem --url, sobe o app com Rscript numa porta livre (precisa de R com shiny, future, promises, commonmark, mgcv, dlnm) e derruba no fim.
O cache precisa existir (shiny/atualizar_cache.R ou testes/montar_cache_local.R) com as populações res e todos.

Confere: a página abre sem erro, a causa do óbito e as três retiradas do ajuste (COVID, meses não consolidados, dias sem clima) geram modelos próprios, a figura é pedida ao servidor e desenhada, trocar local, faixa, raça/cor e medida de calor gera novos pedidos com
resultados diferentes, o recorte já visto não volta ao servidor, a troca de população recarrega os dados e o texto de métodos, recortes com menos de
300 óbitos não geram pedido, pedidos inválidos e de versão antiga de dados mostram mensagem, o CSV baixa e a aba de métodos mostra a versão dos dados."""
import os, re, subprocess, sys, time, socket, signal, urllib.request
from playwright.sync_api import sync_playwright

args = sys.argv[1:]
opcao = lambda n, p=None: args[args.index("--" + n) + 1] if ("--" + n) in args else p
raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
capturas = opcao("capturas")
if capturas: os.makedirs(capturas, exist_ok=True)
falhas = []
def checar(nome, cond, detalhe=""):
    print(("ok     " if cond else "FALHOU ") + nome + ((" | " + str(detalhe)) if (detalhe and not cond) else ""), flush=True)
    if not cond: falhas.append(nome)

proc = None
url = opcao("url")
if not url:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); porta = s.getsockname()[1]; s.close()
    env = dict(os.environ, no_proxy="127.0.0.1,localhost", NO_PROXY="127.0.0.1,localhost", OMP_NUM_THREADS="1")
    proc = subprocess.Popen(["Rscript", "-e", f'shiny::runApp("shiny", port={porta}, host="127.0.0.1", launch.browser=FALSE)'], cwd=raiz, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, preexec_fn=os.setsid)
    url = f"http://127.0.0.1:{porta}"
    for _ in range(120):
        try:
            urllib.request.urlopen(url, timeout=2); break
        except Exception: time.sleep(1)
    else:
        os.killpg(proc.pid, signal.SIGTERM); sys.exit("o app não subiu em 2 minutos")

try:
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1320, "height": 1100}, accept_downloads=True); pg = ctx.new_page()
        erros = []
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
        pg.goto(url)
        sel = lambda i, v: pg.select_option("#" + i, v)
        nota = lambda: pg.inner_text("#s-note")
        kpis = lambda: pg.eval_on_selector_all("#s-kpis .kpi", "els=>els.map(e=>e.innerText.replace(/\\n/g,' | '))")
        pixels = lambda: pg.evaluate("""()=>{const c=document.getElementById('s-chart'),g=c.getContext('2d'),d=g.getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<d.length;i+=4) if(d[i]>0) n++;return n}""")
        pronto = lambda t=120000: pg.wait_for_function("document.querySelectorAll('#s-kpis .kpi').length>0 && !document.getElementById('s-kpis').classList.contains('calc')", timeout=t)
        def esperar_nota(texto, t=60000): pg.wait_for_function("t=>document.getElementById('s-note').innerText.includes(t)", arg=texto, timeout=t)
        def medir(f):
            t0 = time.time(); f(); return time.time() - t0

        # 1. abertura: a página não traz nenhum recorte; o primeiro é pedido ao servidor
        t_1 = medir(pronto)
        checar("abre e desenha o recorte inicial (Todos os locais, Todas as idades)", len(kpis()) > 0 and pixels() > 2000, kpis())
        print(f"       primeiro desenho em {t_1:.1f} s", flush=True)
        opcoes = lambda i: pg.eval_on_selector_all(f"#{i} option", "os=>os.map(o=>o.value)")
        checar("seletor de população com res e todos", opcoes("s-pop") == ["res", "todos"], opcoes("s-pop") if pg.query_selector("#s-pop") else "sem #s-pop")
        checar("sem erros no console após abrir", not erros, erros)
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_01_inicial.png"))
        k_ini = kpis()

        # 2. mudar o recorte pede um modelo novo e muda o resultado
        sel("s-local", "Domicílio"); sel("s-faixa", "60-69")
        pg.wait_for_function("document.getElementById('s-kpis').classList.contains('calc') || document.getElementById('s-note').innerText.includes('Calculando')", timeout=5000)
        checar("durante o cálculo a nota avisa e a figura fica esmaecida", "Calculando" in nota() or "calc" in (pg.get_attribute("#s-kpis", "class") or ""))
        pronto(); k_dom = kpis()
        checar("Domicílio, 60-69 anos: desenha e difere do recorte inicial", len(k_dom) > 0 and k_dom != k_ini and pixels() > 2000, (k_ini, k_dom))
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_02_domicilio_60_69.png"))

        # 3. voltar a um recorte já visto sai da memória do navegador, sem novo cálculo (instantâneo)
        sel("s-local", "Todos os locais"); sel("s-faixa", "Todas as idades")
        t_volta = medir(pronto)
        checar("recorte já visto volta na hora", t_volta < 1.5 and kpis() == k_ini, f"{t_volta:.2f} s")

        # 4. outra medida de calor (HAAT) para o mesmo recorte é um modelo diferente
        sel("s-exp", "haat"); pronto(); k_haat = kpis()
        checar("medida HAAT: desenha e muda o resultado", len(k_haat) > 0 and k_haat != k_ini, (k_ini, k_haat))
        sel("s-exp", "horas"); pronto()

        # 5. raça/cor: trava a faixa etária e pede o recorte Local|Todas as idades|Raça
        sel("s-raca", "Parda"); pronto(); k_parda = kpis()
        checar("raça/cor Parda: faixa etária travada e resultado próprio", pg.is_disabled("#s-faixa") and k_parda != k_ini, k_parda)
        sel("s-raca", "Todas"); pronto()

        # 5b. causa do óbito e retiradas do ajuste (cada combinação é um modelo próprio, pedido ao servidor)
        texto = lambda i: pg.inner_text("#" + i)
        checar("controles novos: causa com 4 opções e três caixas de retirada",
               opcoes("s-causa") == ["naturais", "todas_sem_covid", "todas", "externas"] and all(pg.query_selector(f"#s-r-{c}") for c in ("covid", "nc", "clima")))
        checar("a caixa de COVID mostra as datas do período", re.search(r"\d\d/\d\d/\d{4} a \d\d/\d\d/\d{4}", texto("s-r-covid-t")) is not None, texto("s-r-covid-t"))
        checar("padrão: nenhuma caixa marcada e causas naturais", not any(pg.is_checked(f"#s-r-{c}") for c in ("covid", "nc", "clima")) and pg.input_value("#s-causa") == "naturais")
        sel("s-causa", "externas"); pronto(); k_ext = kpis()
        checar("causas externas: desenha, muda os resultados e o título", len(k_ext) > 0 and k_ext != k_ini and pixels() > 2000 and "causas externas" in texto("sub") and "causas externas" in texto("s-h2"), (k_ini, k_ext))
        sel("s-causa", "todas"); pronto(); k_todas_c = kpis()
        checar("todas as causas, com COVID: resultado próprio e título", k_todas_c != k_ini and k_todas_c != k_ext and "com COVID-19" in texto("sub"), k_todas_c)
        checar("nota de raça/cor acompanha a causa", "todas as causas, com COVID-19" in texto("s-raca-nota"), texto("s-raca-nota"))
        sel("s-causa", "todas_sem_covid"); pronto(); k_sc = kpis()
        checar("todas as causas, exceto COVID: resultado próprio", k_sc != k_todas_c and k_sc != k_ini and "exceto COVID-19" in texto("sub"), k_sc)
        sel("s-causa", "naturais")
        t_nat = medir(pronto)
        checar("voltar a causas naturais sai da memória do navegador e reproduz o resultado inicial", t_nat < 1.5 and kpis() == k_ini and "causas naturais" in texto("sub"), f"{t_nat:.2f} s")
        pg.check("#s-r-covid"); pronto(); k_sem_cov = kpis()
        checar("retirar o período COVID: refaz o modelo, muda os resultados e a legenda", k_sem_cov != k_ini and "COVID-19 (fora do ajuste)" in texto("s-leg") and "retirado do ajuste" in nota(), (k_ini, k_sem_cov, texto("s-leg")))
        checar("retirar o período COVID: a nota do modelo informa que não há termo para ele", "não tem termo para ele" in nota(), nota())
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_02b_sem_covid.png"))
        pg.check("#s-r-nc"); pronto(); k_sem_cov_nc = kpis()
        checar("retirar também os meses não consolidados: novo modelo e legenda", k_sem_cov_nc != k_sem_cov and "Registro não consolidado (fora do ajuste)" in texto("s-leg"), texto("s-leg"))
        pg.uncheck("#s-r-covid"); pg.uncheck("#s-r-nc"); pg.check("#s-r-clima"); pronto(); k_clima = kpis()
        checar("retirar dias sem clima (e os 10 seguintes): novo modelo e nota", len(k_clima) > 0 and "sem dados de clima e os 10 dias seguintes" in nota() and pixels() > 2000, nota()[-300:])
        pg.uncheck("#s-r-clima")
        t_pad = medir(pronto)
        checar("desmarcar tudo volta ao resultado inicial, na hora", t_pad < 1.5 and kpis() == k_ini and "COVID-19 (termo próprio no modelo)" in texto("s-leg"), f"{t_pad:.2f} s")
        sel("s-causa", "externas"); pg.check("#s-r-covid"); pg.check("#s-r-nc"); pronto()
        checar("causas externas com COVID e meses não consolidados retirados desenha", pixels() > 2000 and len(kpis()) > 0)
        sel("s-local", "Ignorado"); sel("s-faixa", "30-39")
        esperar_nota("Menos de 300 óbitos", 5000)
        checar("depois das retiradas, recorte com poucos óbitos no ajuste informa o limite sem pedir ao servidor", "no ajuste" in nota(), nota())
        sel("s-local", "Todos os locais"); sel("s-faixa", "Todas as idades")
        pg.uncheck("#s-r-covid"); pg.uncheck("#s-r-nc"); sel("s-causa", "naturais"); pronto()
        checar("estado restaurado para o padrão", kpis() == k_ini)

        # 5c. aba de exposição-resposta e defasagem (filtros próprios, mesmos modelos)
        xk = lambda: pg.eval_on_selector_all("#x-kpis .kpi", "els=>els.map(e=>e.innerText.replace(/\\n/g,' | '))")
        xpix = lambda i: pg.evaluate("""(id)=>{const c=document.getElementById(id),g=c.getContext('2d'),d=g.getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<d.length;i+=4) if(d[i]>0) n++;return n}""", i)
        xpronto = lambda t=120000: pg.wait_for_function("document.querySelectorAll('#x-kpis .kpi').length>0 && !document.getElementById('x-kpis').classList.contains('calc')", timeout=t)
        pg.click("nav button[data-tab=exp]")
        pg.wait_for_function("!document.getElementById('tab-exp').classList.contains('hide') && document.getElementById('tab-serie').classList.contains('hide')", timeout=5000)
        xpronto(); xk_ini = xk()
        n_circ = lambda p: pg.evaluate(f"()=>document.querySelectorAll('#{p}-forest svg circle').length")
        checar("aba de exposição-resposta abre e desenha as duas figuras (curva e floresta de defasagens)", len(xk_ini) == 6 and xpix("x-chart") > 1500 and n_circ("x") == 60, (xk_ini, n_circ("x")))
        rot_f = pg.evaluate("()=>[...document.querySelectorAll('#x-forest svg g > text:first-of-type')].map(t=>t.textContent)")
        checar("Figura 3: 11 defasagens (lag 0 a 10) e 4 acúmulos (0 a 1, 0 a 3, 0 a 7, 0 a 10)", rot_f == ["Lag 0 (mesmo dia)"] + [f"Lag {i}" for i in range(1, 11)] + ["Lag 0 a 1", "Lag 0 a 3", "Lag 0 a 7", "Lag 0 a 10"], rot_f)
        checar("quadros: RR no lag 0 e acumulados em 0 a 3 e 0 a 10 dias, para os dois níveis de referência",
               all(k.split(" | ")[1].startswith(pre) for k, pre in zip(xk_ini, ["RR no mesmo dia (lag 0), para exposição", "RR acumulado nas defasagens de 0 a 3 dias", "RR acumulado nas defasagens de 0 a 10 dias"] * 2)), xk_ini)
        leg_ini = pg.inner_text("#x-leg2")
        checar("a aba tem filtros próprios: população só uma vez e causa e retiradas por aba",
               len(pg.query_selector_all("#s-pop")) == 1 and opcoes("x-causa") == ["naturais", "todas_sem_covid", "todas", "externas"] and all(pg.query_selector(f"#x-r-{c}") for c in ("covid", "nc", "clima")))
        checar("o RR acumulado em 0 a 10 dias da aba é o mesmo da Figura 1 para o mesmo recorte", [xk_ini[2].split(" | ")[0], xk_ini[5].split(" | ")[0]] == [k.split(" | ")[0] for k in k_ini[1:3]], (xk_ini, k_ini[1:3]))
        checar("a interpretação cita o RR no lag 0 e os RR acumulados", "RR no mesmo dia (lag 0)" in pg.inner_text("#x-interp") and "RR acumulado em 0 a 3 dias" in pg.inner_text("#x-interp") and "em 0 a 10 dias" in pg.inner_text("#x-interp"), pg.inner_text("#x-interp"))
        checar("a aba não usa travessão no texto das figuras 2 e 3", not re.search("[—–]", pg.inner_text("#x-interp") + pg.inner_text("#x-note2") + pg.inner_text("#x-kpis") + pg.inner_text("#x-forest")))
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_02c_exposicao.png"), full_page=True)
        sel("x-exp", "haat"); xpronto(); xk_haat = xk()
        checar("medida HAAT na aba: nova curva e novos quadros", xk_haat != xk_ini and xpix("x-chart") > 1500, xk_haat)
        checar("medida HAAT na aba: a floresta é redesenhada com os níveis do HAAT", pg.inner_text("#x-leg2") != leg_ini and n_circ("x") == 60, (leg_ini, pg.inner_text("#x-leg2")))
        sel("x-exp", "horas"); xpronto()
        sel("x-causa", "externas"); xpronto(); xk_ext = xk()
        checar("causas externas na aba: novo modelo", xk_ext != xk_ini and "causas externas" in pg.inner_text("#x-sub"), xk_ext)
        pg.check("#x-r-covid"); xpronto()
        checar("retirar o período COVID na aba: a nota informa que o modelo não tem termo para ele", "não tem termo para ele" in pg.inner_text("#x-note2"), pg.inner_text("#x-note2")[:300])
        pg.uncheck("#x-r-covid"); sel("x-causa", "naturais"); xpronto()
        checar("filtros da aba não mudam os da Figura 1", pg.input_value("#s-causa") == "naturais" and not pg.is_checked("#s-r-covid"))
        sel("x-raca", "Parda"); xpronto()
        checar("raça/cor Parda na aba: faixa etária travada e resultado próprio", pg.is_disabled("#x-faixa") and xk() != xk_ini)
        sel("x-raca", "Todas"); sel("x-local", "Ignorado"); sel("x-faixa", "30-39")
        pg.wait_for_function("document.getElementById('x-note').innerText.includes('Menos de 300 óbitos')", timeout=5000)
        checar("aba: recorte com poucos óbitos informa o limite sem pedir ao servidor", "modelo não estimado" in pg.inner_text("#x-note"))
        sel("x-local", "Todos os locais"); sel("x-faixa", "Todas as idades"); xpronto()
        checar("voltar ao recorte inicial na aba reproduz os quadros", xk() == xk_ini)
        # 5d. Figura 4: mapa de horas por dia x limiar (um modelo por célula, uma coluna por pedido)
        hm_cols = lambda: pg.evaluate("()=>[...document.querySelectorAll('#x-hm tr:first-child th')].slice(1).map(t=>t.innerText)")
        hm_pend = lambda: pg.evaluate("()=>[...document.querySelectorAll('#x-hm td:not(.rl)')].filter(t=>t.innerText==='…').length")
        hm_pronto = lambda t=600000: pg.wait_for_function("document.querySelectorAll('#x-hm td:not(.rl)').length===104 && ![...document.querySelectorAll('#x-hm td:not(.rl)')].some(t=>t.innerText==='…') && document.getElementById('x-hm-interp').innerText.includes('combinações estimadas')", timeout=t)
        checar("Figura 4: cabeçalho com os limiares de 32 a 44 °C e 8 linhas de horas", hm_cols() == [str(k) for k in range(32, 45)] and pg.evaluate("()=>document.querySelectorAll('#x-hm td.rl').length") == 8, hm_cols())
        pg.wait_for_function("[...document.querySelectorAll('#x-hm td:not(.rl)')].some(t=>/^[0-9],[0-9]{2}$/.test(t.innerText))", timeout=120000)
        checar("Figura 4: a primeira coluna recebida é a de 36 °C e a tabela mostra progresso", "Calculando as colunas do mapa" in pg.inner_text("#x-hm-prog") or hm_pend() == 0, pg.inner_text("#x-hm-prog"))
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_02d_mapa_parcial.png"), full_page=True)
        hm_pronto()
        celulas = pg.evaluate("()=>[...document.querySelectorAll('#x-hm td:not(.rl)')].map(t=>({t:t.innerText,title:t.title,bold:t.style.fontWeight}))")
        rrs = [c for c in celulas if re.match(r"^\d,\d{2}$", c["t"])]
        checar("Figura 4: 104 células, a maioria estimada, o resto com traço", len(celulas) == 104 and len(rrs) > 60 and all(c["t"] in ("–",) or re.match(r"^\d,\d{2}$", c["t"]) for c in celulas), (len(celulas), len(rrs)))
        checar("Figura 4: o texto da célula traz limiar, horas, RR com IC 95% e dias expostos", all(("Índice de calor ≥" in c["title"] and "IC 95%" in c["title"] and "dias expostos" in c["title"]) for c in rrs))
        checar("Figura 4: o RR de 36 °C com 1 h bate com o da interpretação", re.search(r"36 °C e pelo menos 1 hora no dia, RR = (\d,\d{2})", pg.inner_text("#x-hm-interp")) and re.search(r"36 °C e pelo menos 1 hora no dia, RR = (\d,\d{2})", pg.inner_text("#x-hm-interp")).group(1) == pg.inner_text("#x-hm tr:nth-child(2) td:nth-child(6)"), pg.inner_text("#x-hm-interp")[:300])
        checar("Figura 4: a interpretação e a nota não usam travessão", "—" not in pg.inner_text("#x-hm-interp") + pg.inner_text("#x-hm-note") and "–" not in pg.inner_text("#x-hm-interp"))
        sem_ic = pg.evaluate("()=>[...document.querySelectorAll('#x-hm td:not(.rl)')].filter(t=>/^[0-9],/.test(t.innerText) && t.style.fontWeight!=='700').length")
        pg.check("#x-hm-sig")
        transp = pg.evaluate("()=>[...document.querySelectorAll('#x-hm td:not(.rl)')].filter(t=>/^[0-9],/.test(t.innerText) && t.style.fontWeight!=='700' && (t.style.backgroundColor==='transparent'||t.style.backgroundColor==='rgba(0, 0, 0, 0)')).length")
        checar("Figura 4: 'destacar só IC que não inclui 1' apaga a cor das células não significativas", transp == sem_ic, (transp, sem_ic))
        pg.uncheck("#x-hm-sig")
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_02d_mapa.png"), full_page=True)
        # trocar o recorte pede novas colunas; voltar usa o que já chegou
        sel("x-causa", "externas"); hm_pronto()
        checar("Figura 4: outra causa do óbito gera outro mapa", [c["t"] for c in pg.evaluate("()=>[...document.querySelectorAll('#x-hm td:not(.rl)')].map(t=>({t:t.innerText}))")] != [c["t"] for c in celulas])
        sel("x-causa", "naturais")
        pg.wait_for_function("document.getElementById('x-hm-interp').innerText.includes('combinações estimadas')", timeout=5000)
        checar("Figura 4: voltar ao recorte anterior redesenha na hora, sem novo cálculo", [c["t"] for c in pg.evaluate("()=>[...document.querySelectorAll('#x-hm td:not(.rl)')].map(t=>({t:t.innerText}))")] == [c["t"] for c in celulas])
        sel("x-local", "Ignorado"); sel("x-faixa", "30-39")
        pg.wait_for_function("document.getElementById('x-hm-note').innerText.includes('Menos de 300 óbitos')", timeout=5000)
        checar("Figura 4: recorte com poucos óbitos informa o limite e esvazia a tabela", pg.evaluate("()=>document.getElementById('x-hm').innerHTML==='' ") )
        sel("x-local", "Todos os locais"); sel("x-faixa", "Todas as idades"); xpronto()

        # 5e. comparação de dois locais do óbito, lado a lado
        yk = lambda: pg.eval_on_selector_all("#y-kpis .kpi", "els=>els.map(e=>e.innerText.replace(/\\n/g,' | '))")
        eixo_y = lambda c: pg.evaluate("(id)=>{const s=Chart.getChart(id).scales.y;return [s.min,s.max]}", c)
        visivel = lambda i: pg.evaluate("(i)=>document.getElementById(i).offsetWidth>0", i)
        checar("sem comparação: só o recorte x aparece", not visivel("y-kpis") and not visivel("y-forest") and not visivel("x-comp-txt") and not pg.evaluate("()=>document.getElementById('x-cmp').classList.contains('dois')"))
        sel("x-local2", "Hospital")
        pg.wait_for_function("document.querySelectorAll('#y-kpis .kpi').length>0 && !document.getElementById('y-kpis').classList.contains('calc') && document.querySelectorAll('#y-forest svg circle').length>0", timeout=120000)
        xpronto()
        checar("comparação: o segundo recorte aparece ao lado, com quadros, curva e floresta próprios", visivel("y-kpis") and visivel("y-forest") and len(yk()) == 6 and xpix("y-chart") > 1500 and n_circ("y") == 60 and yk() != xk(), (yk(), xk()))
        checar("comparação: os títulos nomeiam o local do óbito de cada coluna", "Todos os locais" in pg.inner_text("#x-h2") and "Hospital" in pg.inner_text("#y-h2"), (pg.inner_text("#x-h2"), pg.inner_text("#y-h2")))
        checar("comparação: a Figura 2 tem a mesma escala vertical nos dois recortes", eixo_y("x-chart") == eixo_y("y-chart"), (eixo_y("x-chart"), eixo_y("y-chart")))
        caixas = pg.evaluate("()=>['x-chart','y-chart'].map(i=>{const r=document.getElementById(i).getBoundingClientRect();return [Math.round(r.left),Math.round(r.top),Math.round(r.width)]})")
        checar("comparação: as duas figuras ficam lado a lado, na mesma altura e com a mesma largura", caixas[0][1] == caixas[1][1] and caixas[0][0] < caixas[1][0] and abs(caixas[0][2] - caixas[1][2]) <= 2, caixas)
        t_comp = pg.inner_text("#x-comp-txt")
        checar("comparação: o texto traz o RR acumulado dos dois locais e a ressalva sobre o teste", "COMPARAÇÃO ENTRE OS LOCAIS DO ÓBITO" in t_comp and "“Todos os locais”" in t_comp and "“Hospital”" in t_comp and "não substitui um teste" in t_comp and "não são independentes" in t_comp and not re.search("[—–]", t_comp), t_comp)
        checar("comparação: a Figura 4 do segundo recorte começa a ser pedida", pg.evaluate("()=>document.getElementById('y-hm').innerHTML.length")>0 and len(pg.query_selector_all("#y-hm-card #y-hm-sig")) == 0 and len(pg.query_selector_all("#x-hm-sig")) == 1)
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_02e_comparacao.png"), full_page=True)
        sel("x-causa", "externas"); xpronto()
        pg.wait_for_function("document.querySelectorAll('#y-kpis .kpi').length>0 && !document.getElementById('y-kpis').classList.contains('calc')", timeout=120000)
        checar("comparação: a causa do óbito vale para os dois recortes", "externas" in pg.inner_text("#x-sub") and "externas" in pg.inner_text("#y-sub"))
        sel("x-causa", "naturais"); xpronto()
        sel("x-local", "Hospital")
        pg.wait_for_function("document.getElementById('x-local2').value==='__sem__'", timeout=5000)
        checar("comparar um local com ele mesmo desfaz a comparação", not pg.evaluate("()=>document.getElementById('x-cmp').classList.contains('dois')") and not visivel("y-kpis"))
        sel("x-local", "Todos os locais"); xpronto()
        sel("x-local2", "Ignorado")
        pg.wait_for_function("document.getElementById('y-note').innerText.includes('Menos de 300 óbitos')", timeout=5000)
        checar("comparação: um recorte com poucos óbitos informa o limite só na sua coluna", "modelo não estimado" in pg.inner_text("#y-note") and len(xk()) == 6 and xpix("x-chart") > 1500)
        sel("x-local2", "__sem__"); xpronto()
        checar("sem comparação de novo: a aba volta ao recorte único", not visivel("y-kpis") and xk() == xk_ini)

        # 5f. aba de causas específicas (CID-10): um modelo por causa, valor q de Benjamini e Hochberg na família escolhida
        # (precisa de um cache com a causa básica de cada óbito; com cache antigo o servidor avisa e esta parte é pulada)
        kcod = lambda: pg.evaluate("()=>[...document.querySelectorAll('#k-fig g[data-c]')].map(g=>g.dataset.c)")
        ktit = lambda: pg.evaluate("()=>[...document.querySelectorAll('#k-fig g[data-c] title')].map(t=>t.textContent)")
        kpronto = lambda t=420000: pg.wait_for_function("document.getElementById('k-prog').innerText==='' && /causas avaliadas|Nenhuma causa|Menos de/.test(document.getElementById('k-interp').innerText + document.getElementById('k-note').innerText)", timeout=t)
        num_br = lambda t: 0.0005 if t.startswith("<") else float(t.replace(",", "."))
        pg.click("nav button[data-tab=cid]")
        pg.wait_for_function("!document.getElementById('tab-cid').classList.contains('hide')", timeout=5000)
        checar("aba CID: filtros de recorte, medida, nível, conjunto e capítulo, e filtros de causa e retiradas próprios",
               opcoes("k-exp") == ["horas", "haat"] and opcoes("k-conj") == ["todas", "apriori"] and len(opcoes("k-cap")) == 19 and len(opcoes("k-nivel")) == 2
               and opcoes("k-causa") == ["naturais", "todas_sem_covid", "todas", "externas"] and all(pg.query_selector(f"#k-r-{c}") for c in ("covid", "nc", "clima")))
        pg.wait_for_function("document.getElementById('k-prog').innerText!=='' || document.querySelectorAll('#k-fig g[data-c]').length>0 || document.getElementById('k-note').innerText!==''", timeout=120000)
        pg.wait_for_function("!document.getElementById('k-prog').innerText.startsWith('Obtendo')", timeout=120000)
        if "não traz a causa básica" in pg.inner_text("#k-prog") or "Não foi possível obter" in pg.inner_text("#k-prog"):
            print("PULADO: o cache deste teste não traz a causa básica de cada óbito (refaça com atualizar_cache.R --forcar ou montar_cache_local.R): ", pg.inner_text("#k-prog")[:160], flush=True)
        else:
            sel("k-conj", "apriori"); sel("k-cap", "I"); kpronto()
            cods = kcod()
            checar("aba CID: causas selecionadas do referencial no capítulo IX (aparelho circulatório): só causas I, com figura e interpretação", len(cods) > 0 and all(c.startswith("I") for c in cods) and "causas avaliadas" in pg.inner_text("#k-interp"), (cods, pg.inner_text("#k-interp")[:200]))
            qs = [num_br(re.search(r"q = (<?[0-9,]+)", t).group(1)) for t in ktit()]
            checar("aba CID: com o filtro padrão só aparecem causas com q < 0,05", all(q < 0.05 for q in qs), qs)
            pg.check("#k-todos"); n_todas = len(kcod())
            tit = ktit(); ps = [num_br(re.search(r"p = (<?[0-9,]+)", t).group(1)) for t in tit]; qs2 = [num_br(re.search(r"q = (<?[0-9,]+)", t).group(1)) for t in tit]
            checar("aba CID: incluir as causas sem diferença traz todas as causas da família", n_todas >= len(cods) and sum(1 for q in qs2 if q < 0.05) == len(cods), (n_todas, len(cods)))
            ordem = sorted(range(len(ps)), key=lambda i: (ps[i], qs2[i]))             # p e q vêm arredondados em 3 casas: empates em p ordenam por q
            checar("aba CID: o valor q nunca fica abaixo do p e não decresce com o p (Benjamini e Hochberg)", all(q2 >= p - 0.0006 for p, q2 in zip(ps, qs2)) and all(qs2[ordem[i]] <= qs2[ordem[i + 1]] + 0.0011 for i in range(len(ordem) - 1)), list(zip(ps, qs2))[:8])
            checar("aba CID: nota e interpretação sem travessão", not re.search("[—–]", pg.inner_text("#k-note") + pg.inner_text("#k-interp")))
            pg.uncheck("#k-todos")
            pg.wait_for_function("document.getElementById('k-h2b').innerText.length>20 && document.getElementById('k-chart')", timeout=120000)
            pg.wait_for_function("document.getElementById('k-selnote').innerText.startsWith('Causa escolhida')", timeout=120000)
            checar("aba CID: a Figura 5b abre com uma causa já escolhida e desenha a série semanal", xpix("k-chart") > 1500 and "Óbitos semanais por causa: " in pg.inner_text("#k-h2b"), pg.inner_text("#k-h2b"))
            if capturas: pg.screenshot(path=os.path.join(capturas, "app_02f_cid.png"), full_page=True)
            outra = [c for c in kcod() if c not in pg.inner_text("#k-h2b")]
            if outra:
                pg.click(f"#k-fig g[data-c={outra[0]}]")
                pg.wait_for_function("c=>document.getElementById('k-h2b').innerText.includes(c) && document.getElementById('k-selnote').innerText.startsWith('Causa escolhida')", arg=outra[0], timeout=120000)
                checar("aba CID: clicar em uma causa troca a série semanal", outra[0] in pg.inner_text("#k-selnote") and xpix("k-chart") > 1500, pg.inner_text("#k-selnote"))
            sel("k-exp", "haat")
            checar("aba CID: a medida HAAT refaz os níveis e pede as causas de novo", opcoes("k-nivel") == ["0", "1"] and ("Avaliando" in pg.inner_text("#k-prog") or len(kcod()) > 0))
            kpronto()
            checar("aba CID: com o HAAT o resultado é outro", ktit() != tit, (len(ktit()), len(tit)))
            sel("k-exp", "horas"); sel("k-nivel", "1"); kpronto()
            checar("aba CID: o segundo nível de exposição dá outro resultado", ktit() != tit)
            sel("k-nivel", "0"); sel("k-conj", "todas"); sel("k-cap", "all"); sel("k-causa", "externas"); kpronto()
            ext = kcod()
            checar("aba CID: causas externas na aba só listam causas dos capítulos V a Y", len(ext) > 0 and all(c[0] in "VWXY" for c in ext) and "causas externas" in pg.inner_text("#k-sub"), ext)
            sel("k-causa", "naturais"); sel("k-local", "Todos os locais"); sel("k-faixa", "5-9"); kpronto(120000)
            checar("aba CID: recorte com menos de 1.500 óbitos por causa informa o limite", "Nenhuma causa tem pelo menos 1.500 óbitos" in pg.inner_text("#k-note") and len(kcod()) == 0, pg.inner_text("#k-note")[:200])
            sel("k-local", "Ignorado"); sel("k-faixa", "30-39")
            pg.wait_for_function("document.getElementById('k-note').innerText.includes('Menos de 300 óbitos')", timeout=5000)
            checar("aba CID: recorte com menos de 300 óbitos informa o limite sem pedir ao servidor", "modelo não estimado" in pg.inner_text("#k-note"))
            sel("k-local", "Todos os locais"); sel("k-faixa", "Todas as idades")
            checar("aba CID: os filtros da aba não mudam os da Figura 1", pg.input_value("#s-causa") == "naturais" and pg.input_value("#x-causa") == "naturais")

        pg.click("nav button[data-tab=serie]"); pronto()
        checar("voltar para a Figura 1 mantém a figura", kpis() == k_ini and pixels() > 2000)

        # 6. escala diária e CSV
        sel("s-esc", "dia"); pronto()
        checar("escala diária desenha", pixels() > 2000)
        sel("s-esc", "sem"); sel("s-ini", pg.eval_on_selector("#s-ini", "e=>e.options[0].value")); pronto()       # a escala diária encurta o período: volta ao início da série
        with pg.expect_download(timeout=15000) as d:
            pg.click("#s-csv")
        caminho = d.value.path(); txt = open(caminho, encoding="utf-8-sig").read()
        checar("o nome do CSV identifica a causa", "_naturais.csv" in d.value.suggested_filename, d.value.suggested_filename)
        checar("CSV baixa com cabeçalho e linhas", txt.count("\n") > 100, txt[:200])

        # 7. recorte com menos de 300 óbitos: mensagem, sem pedido ao servidor
        sel("s-local", "Ignorado"); sel("s-faixa", "30-39")
        esperar_nota("Menos de 300 óbitos", 5000)
        checar("recorte sem óbitos suficientes informa o limite", "Menos de 300 óbitos" in nota(), nota())
        sel("s-local", "Todos os locais"); sel("s-faixa", "Todas as idades"); pronto()

        # 8. pedidos malformados não derrubam o app
        pg.evaluate("""()=>Shiny.setInputValue('pedido',{key:'Local inexistente|Todas as idades',ex:'horas',pop:'res',chave:'x',n:99},{priority:'event'})""")
        pg.evaluate("""()=>Shiny.setInputValue('pedido',{key:1,ex:null},{priority:'event'})""")
        pg.evaluate("""()=>Shiny.setInputValue('pedido','lixo',{priority:'event'})""")
        for causa, opc in (("xx", "000"), ("naturais", "2"), ("naturais", "1000"), ("todas", "abc")):
            pg.evaluate("""([c,o])=>Shiny.setInputValue('pedido',{key:'Todos os locais|Todas as idades',ex:'horas',pop:'res',chave:'x',causa:c,opc:o,n:200},{priority:'event'})""", [causa, opc])
        time.sleep(1.5)
        sel("s-local", "UPA / pronto atendimento"); pronto()
        checar("app segue respondendo depois de pedidos malformados", len(kpis()) > 0 and not erros, erros)
        sel("s-local", "Todos os locais"); pronto()

        # 9. troca de população: dados e métodos novos
        sel("s-pop", "todos"); pronto(); k_todos = kpis()
        checar("população 'todos': desenha e difere de 'res'", len(k_todos) > 0 and k_todos != k_ini, (k_ini, k_todos))
        pg.click("nav button[data-tab=sobre]")
        pg.wait_for_function("document.getElementById('tab-sobre').innerText.includes('todos os óbitos ocorridos no Rio, residentes ou não')", timeout=15000)
        sobre = pg.inner_text("#tab-sobre")
        checar("métodos mudam com a população", "residentes ou não" in sobre)
        checar("métodos explicam a causa do óbito e as retiradas do ajuste", "Causa do óbito" in sobre and "Retirar períodos do ajuste" in sobre and "Curvas de exposição-resposta e de defasagem" in sobre and "sem taxas por população" in sobre, sobre[:300])
        checar("métodos mostram a versão dos dados", "Versão dos dados" in sobre and "UTC" in sobre, sobre[-400:])
        checar("métodos sem marcação crua", "##" not in sobre and "**" not in sobre and "```" not in sobre)
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_03_metodos.png"), full_page=True)
        pg.click("nav button[data-tab=serie]"); pronto()
        sel("s-pop", "res"); pronto()
        checar("volta para 'res' e reproduz o primeiro resultado", kpis() == k_ini, kpis())

        # 10. segunda sessão (outra pessoa): os recortes já calculados vêm do disco, sem refazer o modelo
        pg2 = ctx.new_page(); pg2.goto(url)
        k2 = lambda: pg2.eval_on_selector_all("#s-kpis .kpi", "els=>els.map(e=>e.innerText.replace(/\\n/g,' | '))")
        pronto2 = lambda t=60000: pg2.wait_for_function("document.querySelectorAll('#s-kpis .kpi').length>0 && !document.getElementById('s-kpis').classList.contains('calc')", timeout=t)
        t_2 = medir(pronto2)
        checar("outra sessão abre o recorte inicial a partir do disco", t_2 < 8 and k2() == k_ini, f"{t_2:.1f} s")
        pg2.select_option("#s-local", "Domicílio"); pg2.select_option("#s-faixa", "60-69")
        t_3 = medir(pronto2)
        checar("outra sessão: Domicílio 60-69 vem do disco e dá o mesmo resultado", t_3 < 8 and k2() == k_dom, f"{t_3:.1f} s")
        pg2.close()

        # 11. dados atualizados no servidor enquanto a página estava aberta: mensagem pedindo para recarregar; depois de recarregar, funciona
        cache = os.environ.get("PAINEL_CACHE")
        if cache and os.path.exists(os.path.join(cache, "meta_res.json")):
            import json, shutil
            mp = os.path.join(cache, "meta_res.json"); m = json.load(open(mp)); velha = m["chave"]; nova = "teste" + velha[5:]
            rds_v = os.path.join(cache, f"contexto_res_{velha}.rds"); rds_n = os.path.join(cache, f"contexto_res_{nova}.rds")
            shutil.copy(rds_v, rds_n); m2 = dict(m, chave=nova); json.dump(m2, open(mp, "w"))
            try:
                sel("s-local", "Hospital"); sel("s-faixa", "70-79")
                esperar_nota("Recarregue a página", 30000)
                checar("versão de dados nova no servidor: a página avisa para recarregar", "Recarregue a página" in nota(), nota())
                pg.reload(); pronto(120000)
                checar("depois de recarregar, a versão nova responde", len(kpis()) > 0 and pixels() > 2000)
            finally:
                json.dump(m, open(mp, "w")); os.remove(rds_n)
        else:
            print("PULADO: defina PAINEL_CACHE para testar a troca de versão dos dados.")
        checar("sem erros no console ao longo do teste", not erros, erros)
        b.close()
finally:
    if proc:
        os.killpg(proc.pid, signal.SIGTERM)

print("\nFALHAS:", "nenhuma" if not falhas else falhas)
sys.exit(1 if falhas else 0)

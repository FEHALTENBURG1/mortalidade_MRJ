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
        checar("aba de exposição-resposta abre e desenha as duas figuras", len(xk_ini) == 5 and xpix("x-chart") > 1500 and xpix("x-chart2") > 1500, xk_ini)
        checar("a aba tem filtros próprios: população só uma vez e causa e retiradas por aba",
               len(pg.query_selector_all("#s-pop")) == 1 and opcoes("x-causa") == ["naturais", "todas_sem_covid", "todas", "externas"] and all(pg.query_selector(f"#x-r-{c}") for c in ("covid", "nc", "clima")))
        checar("o quadro de RR da aba é o mesmo da Figura 1 para o mesmo recorte", xk_ini[:2] == k_ini[1:3], (xk_ini[:2], k_ini[1:3]))
        checar("a interpretação cita os níveis de referência e a defasagem", "RR acumulado em 0 a 10 dias" in pg.inner_text("#x-interp") and "dia(s)" in pg.inner_text("#x-interp"), pg.inner_text("#x-interp"))
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_02c_exposicao.png"), full_page=True)
        sel("x-exp", "haat"); xpronto(); xk_haat = xk()
        checar("medida HAAT na aba: nova curva e novos quadros", xk_haat != xk_ini and xpix("x-chart") > 1500, xk_haat)
        sel("x-lag", "ac"); 
        checar("defasagem acumulada: redesenha a Figura 3", "acumulado" in pg.inner_text("#x-note2") and xpix("x-chart2") > 1500, pg.inner_text("#x-note2")[:200])
        sel("x-lag", "rr"); sel("x-exp", "horas"); xpronto()
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

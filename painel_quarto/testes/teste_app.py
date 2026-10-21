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
        kpis = lambda: pg.eval_on_selector_all("#s-kpis .kpi", "els=>els.map(e=>[e.querySelector('.v').innerText, e.querySelector('.l').innerText].join(' | '))")
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
        # ficha do resultado: {rótulo: texto} lido do DOM (os dois pontos dos rótulos vêm do CSS e não estão no texto)
        fch = lambda i: pg.evaluate("i=>Object.fromEntries([...document.querySelectorAll('#'+i+' dl>div')].map(d=>[d.querySelector('dt').textContent, d.querySelector('dd').textContent]))", i)
        PER_AJ = r"\d\d/\d\d/\d{4} a \d\d/\d\d/\d{4} \([\d.]+ dias e [\d.]+ óbitos\)"
        def ficha_ok(F, obrigatorios):
            falta = [r for r in obrigatorios if r not in F or not F[r].strip()]
            return not falta and ("Período do ajuste" not in F or re.fullmatch(PER_AJ, F["Período do ajuste"])), (falta, F.get("Período do ajuste"))
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
        checar("padrão (ajuste principal): meses não consolidados e dias sem clima retirados, período da COVID-19 mantido, causas naturais",
               not pg.is_checked("#s-r-covid") and pg.is_checked("#s-r-nc") and pg.is_checked("#s-r-clima") and pg.input_value("#s-causa") == "naturais")
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
        pg.uncheck("#s-r-covid"); pg.uncheck("#s-r-nc"); pronto(); k_com_nc = kpis()
        checar("manter os meses não consolidados (sensibilidade): novo modelo e legenda 'no ajuste'", k_com_nc != k_ini and "Registro não consolidado (no ajuste)" in texto("s-leg"), (k_ini, k_com_nc, texto("s-leg")))
        pg.uncheck("#s-r-clima"); pronto(); k_ant = kpis()
        checar("manter os dias sem clima como dias sem calor (especificação anterior): novo modelo e nota de atenção", k_ant != k_com_nc and k_ant != k_ini and "Atenção: os dias sem dados de clima foram mantidos no ajuste" in nota(), nota()[-400:])
        pg.check("#s-r-nc"); pg.check("#s-r-clima")
        t_pad = medir(pronto)
        checar("voltar ao ajuste principal sai da memória do navegador, na hora", t_pad < 1.5 and kpis() == k_ini and "COVID-19 (termo próprio no modelo)" in texto("s-leg") and "foram retirados do ajuste" in nota(), f"{t_pad:.2f} s")
        checar("nota do ajuste informa a amostra (dias, óbitos, período) e os dias fora do ajuste por motivo", "Amostra do ajuste:" in nota() and "Fora do ajuste:" in nota() and "sem dado de clima ou nos 10 dias seguintes" in nota(), nota()[-500:])
        # tabela fixa de sensibilidade: principal x meses não consolidados mantidos
        pg.wait_for_function("document.querySelectorAll('#s-sens tbody tr').length===2 && !document.getElementById('s-sens').innerText.includes('calculando')", timeout=120000)
        linhas_s = pg.eval_on_selector_all("#s-sens tbody tr", "trs=>trs.map(tr=>[...tr.children].map(td=>td.innerText))")
        checar("tabela de sensibilidade: duas análises, período estimado, dias, óbitos e RR (IC 95%) nos dois níveis de referência",
               len(linhas_s) == 2 and linhas_s[0][0].startswith("Principal") and linhas_s[1][0].startswith("Sensibilidade") and all(len(l) == 6 and re.search(r"\d\d/\d\d/\d{4} a \d\d/\d\d/\d{4}", l[1]) and re.search(r"\d,\d{2} \(\d,\d{2} a \d,\d{2}\)", l[4]) and re.search(r"\d,\d{2} \(\d,\d{2} a \d,\d{2}\)", l[5]) for l in linhas_s), linhas_s)
        rr_kpi = lambda t: re.sub(r"IC 95%: ", "", t.split(" | ")[0])
        checar("tabela de sensibilidade: a linha principal reproduz os quadros da Figura 1 nos dois níveis de referência", rr_kpi(k_ini[1]) == linhas_s[0][4] and rr_kpi(k_ini[2]) == linhas_s[0][5], (linhas_s[0], k_ini[1:3]))
        checar("o título informa o período estimado", re.search(r"\d\d/\d\d/\d{4} a \d\d/\d\d/\d{4}", texto("s-h2")) is not None, texto("s-h2"))
        # 5b2. Quadro 5: cobertura da faixa semanal por período e grupo (dentro da amostra, conferida contra o JSON de referência; fora da amostra, sob demanda)
        visivel = lambda i: pg.evaluate("(i)=>document.getElementById(i).offsetWidth>0", i)
        pg.wait_for_function("!document.getElementById('s-cobw').classList.contains('hide') && document.querySelectorAll('#s-cob tbody tr').length>0", timeout=60000)
        def linhas5():
            out = []; per = None
            for r in pg.eval_on_selector_all("#s-cob tbody tr", "trs=>trs.map(tr=>[...tr.children].map(td=>td.innerText))"):
                if len(r) == 10: per = r[0].replace(" †", ""); g = r[1]; v = r[2:]
                else: g = r[0]; v = r[1:]
                out.append((per, g, v))
            return out
        pct5 = lambda t: None if t in ("–", "") else float(t.replace("%", "").replace(",", "."))
        L5 = linhas5()
        checar("Quadro 5: períodos em linhas, dois grupos (calor e demais) por período e o total", [g for _, g, _ in L5][-2:] == ["Semanas de calor", "Demais semanas"] and L5[-1][0] == "Todos os períodos" and all(len(v) == 8 for _, _, v in L5) and len({p for p, _, _ in L5}) >= 5, [(p, g) for p, g, _ in L5])
        checar("Quadro 5: fora da amostra ainda não calculado (colunas com –) e botão visível", all(v[4:] == ["0", "–", "–", "–"] or v[4:] == ["–", "–", "–", "–"] for _, _, v in L5) and visivel("s-cob-btn") and "ainda não calculado" in texto("s-cob-st"), (L5[-1], texto("s-cob-st")))
        checar("Quadro 5: dentro, acima e abaixo somam 100% em cada linha com semanas", all(abs(sum(pct5(x) for x in v[1:4]) - 100) < 0.25 for _, _, v in L5 if v[0] not in ("0", "–")), L5[-2:])
        base_ref = os.environ.get("PAINEL_TESTE_BASE")
        if base_ref and os.path.exists(base_ref):
            import json
            ref = json.load(open(base_ref, encoding="utf-8")); chv = "Todos os locais|Todas as idades"; Sx = ref["S"]["horas"][chv]; Ox = ref["So"][chv]; sm = ref["sem"]
            PER = {"2006 a 2010": (2006, 2010), "2011 a 2014": (2011, 2014), "2015 a 2019": (2015, 2019), "2020 a 2022": (2020, 2022), "2023 em diante": (2023, 9999), "Todos os períodos": (0, 9999)}
            def cont5(calor_g, de, ate):                      # contagem independente, semana a semana, a partir do JSON de referência (laço explícito)
                n = d = a = b_ = 0
                for i in range(len(sm["ini"])):
                    if not (de <= sm["ano"][i] <= ate) or (sm["nb"][i] >= 3) != calor_g: continue
                    o, e, l, u = Ox[i], Sx["e"][i], Sx["l"][i], Sx["u"][i]
                    if o is None or e is None or l is None or u is None or sm["cov"][i] or sm["inc"][i] or not sm["cl"][i]: continue
                    n += 1
                    if o > u: a += 1
                    elif o < l: b_ += 1
                    else: d += 1
                return n, d, a, b_
            dif = []
            for per_, g, v in L5:
                n, d, a, b_ = cont5(g == "Semanas de calor", *PER[per_])
                esp = [str(n)] + ([f"{100*d/n:.1f}", f"{100*a/n:.1f}", f"{100*b_/n:.1f}"] if n else ["–"] * 3)
                got = [v[0].replace(".", "")] + [("–" if x == "–" else f"{pct5(x):.1f}") for x in v[1:4]]
                if [x for x in got] != esp and not (n and all(abs(float(x) - float(y)) < 0.051 for x, y in zip(got[1:], esp[1:])) and got[0] == esp[0]): dif.append((per_, g, got, esp))
            checar("Quadro 5: a cobertura dentro da amostra bate com a contagem independente semana a semana (todos os períodos e grupos)", not dif and len(L5) >= 11, dif[:3])
        else:
            print("PULADO: Quadro 5 contra o JSON de referência (defina PAINEL_TESTE_BASE).")
        texto5 = texto("s-cobw")
        checar("Quadro 5: o rótulo da faixa corresponde ao cálculo e não se afirma 2,5% de excedências", "faixa aproximada de variação de 95%" in texto5.lower() and "Faixa aproximada de variação de 95%" in texto("s-leg") and "Faixa de 95%" not in texto("s-leg") and "2,5%" not in (texto5 + texto("i-serie") + texto("s-kpis") + nota()) and "bem calibrado" not in (texto("i-serie") + texto("s-kpis")), texto("s-leg")[:200])
        checar("Quadro 5: distingue intervalo de confiança do esperado, intervalo preditivo e faixa aproximada, e diz que não é validação independente", all(t in texto("s-cob-n2") for t in ("intervalo de confiança do esperado", "intervalo preditivo", "faixa mostrada na Figura 1")) and "não é uma validação independente" in texto("s-cob-n"), texto("s-cob-n2")[:300])
        checar("Quadro 5: sem travessão", not re.search("[—–]", texto("s-cob-n") + texto("s-cob-n2") + texto("s-cob-i") + texto("s-cob-st") + texto("s-cob-t")))
        sel("s-crit", "no"); pg.wait_for_function("document.querySelectorAll('#s-cob tbody tr').length===6", timeout=20000)
        checar("Quadro 5: sem critério de calor há um só grupo, Todas as semanas", {g for _, g, _ in linhas5()} == {"Todas as semanas"} and len(linhas5()) == 6, linhas5()[-1])
        sel("s-crit", "ic")
        sel("s-esc", "dia"); pg.wait_for_function("document.getElementById('s-cobw').classList.contains('hide')", timeout=20000)
        checar("Quadro 5 some na escala diária e a faixa diária tem o mesmo nome e não afirma 2,5%", "2,5%" not in (texto("s-kpis") + nota()) and "Faixa aproximada de variação de 95% de um dia" in nota())
        sel("s-esc", "sem"); pg.select_option("#s-ini", index=0); pg.wait_for_function("!document.getElementById('s-cobw').classList.contains('hide')", timeout=20000)       # a escala diária reduz o período exibido aos 3 últimos anos
        pg.click("#s-cob-btn")
        pg.wait_for_function("document.getElementById('s-cob-st').innerText.includes('Calculando') || document.getElementById('s-cob-st').innerText.includes('Fora da amostra calculado')", timeout=15000)
        pg.wait_for_function("document.getElementById('s-cob-st').innerText.includes('Fora da amostra calculado') || document.getElementById('s-cob-st').innerText.includes('Não foi possível')", timeout=420000)
        L5o = linhas5()
        checar("Quadro 5 fora da amostra: calculado sem erro e o botão some", "Fora da amostra calculado" in texto("s-cob-st") and not visivel("s-cob-btn"), texto("s-cob-st"))
        checar("Quadro 5 fora da amostra: mesmas semanas do ajuste completo em cada linha, e dentro, acima e abaixo somam 100%",
               all(v[4] == v[0] for _, _, v in L5o) and all(abs(sum(pct5(x) for x in v[5:8]) - 100) < 0.25 for _, _, v in L5o if v[4] not in ("0", "–")), L5o[-2:])
        checar("Quadro 5 fora da amostra: os valores diferem do ajuste completo", [v[5:8] for _, _, v in L5o] != [v[1:4] for _, _, v in L5o], L5o[-2:])
        pers = [r[0].replace(" †", "") for r in pg.eval_on_selector_all("#s-cob tbody tr", "trs=>trs.map(tr=>[...tr.children].map(td=>td.innerText))") if len(r) == 10]
        marcados = [r[0] for r in pg.eval_on_selector_all("#s-cob tbody tr", "trs=>trs.map(tr=>[...tr.children].map(td=>td.innerText))") if len(r) == 10 and "†" in r[0]]
        checar("Quadro 5 fora da amostra: só o primeiro e o último período são marcados como extrapolação (†)", pers[-1] == "Todos os períodos" and marcados == [pers[0] + " †", pers[-2] + " †"], (pers, marcados))
        ti = texto("s-cob-i").lower()
        checar("Quadro 5 fora da amostra: a interpretação separa interpolação de extrapolação e cita a incerteza dos coeficientes", "interpolação" in ti and "extrapolação" in ti and "alargaria a faixa" in texto("s-cob-n2") and "fora da amostra" in ti, texto("s-cob-i")[:400])
        checar("Quadro 5 fora da amostra: sem travessão e sem 2,5%", not re.search("[—–]", texto("s-cobw")) and "2,5%" not in texto("s-cobw"))
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_02b2_cobertura.png"), full_page=True)
        sel("s-local", "Domicílio"); pronto()
        checar("Quadro 5: outro recorte volta a pedir o fora da amostra (botão visível, colunas vazias)", visivel("s-cob-btn") and all(v[4:] in (["–"] * 4, ["0", "–", "–", "–"]) for _, _, v in linhas5()))
        sel("s-local", "Todos os locais"); pronto()
        checar("Quadro 5: voltar ao recorte já calculado mostra o fora da amostra sem novo pedido", not visivel("s-cob-btn") and linhas5() == L5o)
        # 5b3. Período exibido: a seleção de anos altera só o que é mostrado; os RR vêm do modelo ajustado com a série completa
        etiq = lambda: pg.eval_on_selector_all("#s-kpis .kpi", "els=>els.map(e=>[e.querySelector('.tg')?[...e.querySelector('.tg').childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join(''):'', e.querySelector('.v').textContent])")
        et0 = etiq(); L5_0 = linhas5(); h2_0 = texto("s-h2")
        checar("Período exibido: os controles de anos e a nota usam o nome novo", "período exibido: ano inicial" in texto("tab-serie").lower() and "período exibido: ano final" in texto("tab-serie").lower() and "ano inicial" not in texto("tab-serie").lower().replace("período exibido: ano inicial", "") and texto("s-per-nota").startswith("Período exibido: ") and "(série completa)" in texto("s-per-nota"), texto("s-per-nota")[:200])
        checar("Período exibido: os dois cartões de RR dizem 'Modelo ajustado com a série completa' e os demais 'Período exibido'", len(et0) >= 6 and [e for e, _ in et0].count("Modelo ajustado com a série completa") == 2 and all(e in ("Modelo ajustado com a série completa", "Período exibido") for e, _ in et0), et0)
        ano_ini2 = pg.eval_on_selector_all("#s-ini option", "os=>os.map(o=>o.value)")[-4]
        t_per = medir(lambda: (sel("s-ini", ano_ini2), pronto()))
        et1 = etiq(); fim_a = pg.eval_on_selector_all("#s-fim option", "os=>os.map(o=>o.value)")[-1]
        obito = lambda e: int(e[0][1].replace(".", ""))
        checar("Período exibido: reduzir os anos muda óbitos e razões O/E, mantém os dois RR e não pede novo cálculo", t_per < 1.5 and obito(et1) < obito(et0) and [v for e, v in et1 if e.startswith("Modelo")] == [v for e, v in et0 if e.startswith("Modelo")] and [v for e, v in et1] != [v for e, v in et0], (et0, et1, t_per))
        checar("Período exibido: título e nota informam o período mostrado e dizem que o modelo usa a série completa", f"período exibido: {ano_ini2} a {fim_a}" in texto("s-h2") and f"Período exibido: {ano_ini2} a {fim_a}." in texto("s-per-nota") and "O modelo foi ajustado com a série completa" in texto("s-per-nota") and "(série completa)" not in texto("s-per-nota"), (texto("s-h2")[-120:], texto("s-per-nota")[:200]))
        checar("Período exibido: a cobertura do Quadro 5 não depende da seleção de anos", linhas5() == L5_0)
        checar("Período exibido: sem travessão na nota", not re.search("[—–]", texto("s-per-nota")))
        sel("s-esc", "dia"); pronto(); et_d = etiq()
        checar("Período exibido na escala diária: mesmas etiquetas nos cartões", [e for e, _ in et_d].count("Modelo ajustado com a série completa") == 2 and [e for e, _ in et_d].count("Período exibido") == len(et_d) - 2, et_d)
        sel("s-esc", "sem"); pg.select_option("#s-ini", index=0); pronto()
        checar("Período exibido: voltar à série completa restaura os cartões", etiq() == et0 and h2_0 == texto("s-h2"))
        sel("s-causa", "externas"); pg.check("#s-r-covid"); pronto()
        checar("causas externas com o período da COVID-19 também retirado desenha", pixels() > 2000 and len(kpis()) > 0)
        sel("s-local", "Ignorado"); sel("s-faixa", "30-39")
        esperar_nota("Menos de 300 óbitos", 5000)
        checar("depois das retiradas, recorte com poucos óbitos no ajuste informa o limite sem pedir ao servidor", "no ajuste" in nota(), nota())
        sel("s-local", "Todos os locais"); sel("s-faixa", "Todas as idades")
        pg.uncheck("#s-r-covid"); sel("s-causa", "naturais"); pronto()
        checar("estado restaurado para o padrão", kpis() == k_ini)


        # 5b4. RR do modelo x razão O/E descritiva (cartões diferenciados) e gráficos alinhados de clima e óbitos
        tipos = lambda: pg.eval_on_selector_all("#s-kpis .kpi", "els=>els.map(e=>({cls:e.className.split(' '),chip:(e.querySelector('.tp')||{}).textContent||'',l:e.querySelector('.l').innerText}))")
        T0 = tipos(); mod0 = [t for t in T0 if "mod" in t["cls"]]; desc0 = [t for t in T0 if "desc" in t["cls"]]
        tem_rr = lambda t: re.search(r"\bRR\b", t) is not None
        checar("Figura 1: os cartões de RR são 'mod' com o selo 'RR do modelo'; os de O/E e de frequência acima da faixa são 'desc' com o selo 'Descritivo, não é RR'",
               len(mod0) == 2 and all(t["chip"] == "RR do modelo" and tem_rr(t["l"]) for t in mod0) and len(desc0) == 4 and all(t["chip"] == "Descritivo, não é RR" and not tem_rr(t["l"]) for t in desc0), T0)
        checar("Figura 1: nenhum cartão de O/E é chamado de RR, e nenhum cartão de RR traz O/E", all(not ("O/E" in t["l"] or "observado/esperado" in t["l"]) or ("desc" in t["cls"] and not tem_rr(t["l"])) for t in T0) and all("O/E" not in t["l"] for t in mod0), T0)
        checar("Figura 1: a razão de semanas de calor se chama 'razão observado/esperado sem calor (O/E)'", any("Razão observado/esperado sem calor (O/E)" in t["l"] for t in desc0), [t["l"] for t in desc0])
        sel("s-esc", "dia"); pronto(); Td = tipos()
        checar("Figura 1 diária: dois cartões de RR do modelo e três descritivos, nenhum O/E chamado de RR", len([t for t in Td if "mod" in t["cls"]]) == 2 and len([t for t in Td if "desc" in t["cls"]]) == 3 and all(not tem_rr(t["l"]) for t in Td if "desc" in t["cls"]), Td)
        sel("s-esc", "sem"); pg.select_option("#s-ini", index=0); pronto()
        # gráficos alinhados (padrão) x sobrepostos
        geo = lambda: pg.evaluate("""()=>{const a=Chart.getChart('s-chart'),c=Chart.getChart('s-chart2');return a&&c?{a:[a.chartArea.left,a.chartArea.right],c:[c.chartArea.left,c.chartArea.right],n1:a.data.labels.length,n2:c.data.labels.length,l1:a.data.labels[0],l2:c.data.labels[c.data.labels.length-1],ya:a.options.scales.y.title.text,bar1:!!(a.options.plugins.barras),yt1:a.options.scales.yt.display,ytc:c.options.scales.yt.title.text,vals:JSON.stringify(c.options.plugins.barras.vals)}:null}""")
        g = geo()
        checar("Gráficos alinhados (padrão): painel de clima abaixo do de óbitos, com a mesma área de plotagem horizontal e o mesmo eixo do tempo",
               g and visivel("s-box2") and visivel("s-leg2") and abs(g["a"][0] - g["c"][0]) < 1 and abs(g["a"][1] - g["c"][1]) < 1 and g["n1"] == g["n2"] and g["l1"] and not g["bar1"] and g["yt1"] is False and pg.input_value("#s-disp") == "alinhado", g)
        checar("Gráficos alinhados: a legenda do clima fica no painel de clima, e a de óbitos não repete as colunas; a nota descreve o painel", "painel de clima" in texto("s-leg2").lower() and "eixo da direita" not in texto("s-leg") and "coluna diária" not in texto("s-leg") and "Painel de clima, alinhado ao gráfico de óbitos" in nota(), (texto("s-leg2")[:200], nota()[-300:]))
        checar("Gráficos alinhados: os eixos têm título curto e o painel de clima mostra as cores dos níveis de calor (NC)", "IC médio (°C)" == g["ytc"] and "NC" in texto("s-leg2") and pixels() > 2000 and pg.evaluate("""()=>{const c=document.getElementById('s-chart2'),g=c.getContext('2d'),d=g.getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<d.length;i+=4) if(d[i]>0) n++;return n}""") > 2000, g)
        vals_al = g["vals"]
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_01b_alinhado.png"), full_page=True)
        sel("s-disp", "sobreposto")
        gs = pg.evaluate("""()=>{const a=Chart.getChart('s-chart');return {bar1:!!(a.options.plugins.barras),yt1:a.options.scales.yt.display,vals:a.options.plugins.barras?JSON.stringify(a.options.plugins.barras.vals):null,c2:!!Chart.getChart('s-chart2')}}""")
        checar("Gráficos sobrepostos: o painel de clima some, as colunas voltam ao fundo com segundo eixo e os mesmos valores diários",
               not visivel("s-box2") and not visivel("s-leg2") and gs["bar1"] and gs["yt1"] is True and not gs["c2"] and gs["vals"] == vals_al and "eixo da direita" in texto("s-leg") and "Colunas ao fundo" in nota(), (gs, texto("s-leg")[:200]))
        sel("s-bar", "no")
        checar("Sem colunas de clima, só há o gráfico de óbitos, em qualquer disposição", not visivel("s-box2") and pg.evaluate("()=>!Chart.getChart('s-chart2')"))
        sel("s-disp", "alinhado")
        checar("Sem colunas de clima e disposição alinhada: continua só o gráfico de óbitos", not visivel("s-box2") and not visivel("s-leg2"))
        sel("s-bar", "hi_med")
        sel("s-esc", "dia"); pronto(); gd = geo()
        checar("Gráficos alinhados na escala diária: mesma área de plotagem e mesmo número de dias nos dois painéis", gd and abs(gd["a"][0] - gd["c"][0]) < 1 and abs(gd["a"][1] - gd["c"][1]) < 1 and gd["n1"] == gd["n2"] and visivel("s-box2"), gd)
        sel("s-esc", "sem"); pg.select_option("#s-ini", index=0); pronto()
        checar("Gráficos alinhados: voltar à escala semanal restaura o painel de clima", visivel("s-box2") and geo() is not None and pg.input_value("#s-disp") == "alinhado")
        checar("Gráficos e cartões: sem travessão nas legendas do painel de clima", not re.search("[—–]", texto("s-leg2")))

        # 5c. aba de exposição-resposta e defasagem (filtros próprios, mesmos modelos)
        xk = lambda: pg.eval_on_selector_all("#x-kpis .kpi", "els=>els.map(e=>[e.querySelector('.v').innerText, e.querySelector('.l').innerText].join(' | '))")
        xpix = lambda i: pg.evaluate("""(id)=>{const c=document.getElementById(id),g=c.getContext('2d'),d=g.getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<d.length;i+=4) if(d[i]>0) n++;return n}""", i)
        visivel = lambda i: pg.evaluate("(i)=>document.getElementById(i).offsetWidth>0", i)
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
        _txt_rr = pg.inner_text("#x-kpis") + " " + pg.inner_text("#x-interp") + " " + " ".join(pg.eval_on_selector_all("#x-forest svg text", "els=>els.map(e=>e.textContent)")) + " " + " ".join(pg.eval_on_selector_all("#x-forest svg title", "els=>els.map(e=>e.textContent)"))
        checar("RR com no máximo duas casas decimais nos quadros, na floresta (rótulos e dicas) e na interpretação", not re.search(r"\d,\d{3}", _txt_rr), re.findall(r".{12}\d,\d{3}.{6}", _txt_rr)[:5])
        # forma da curva: a reta imposta (1 gl) e a curva flexível pré-definida (pedido flex_horas), com o suporte de dias por hora
        fpronto = lambda t=300000: pg.wait_for_function("document.querySelectorAll('#x-fx tbody tr').length===2", timeout=t)
        fpronto(); fx_ini = pg.inner_text("#x-fx")
        linhas_fx = pg.eval_on_selector_all("#x-fx tbody tr", "trs=>trs.map(tr=>[...tr.children].map(td=>td.innerText))")
        checar("Quadro 3: reta imposta e curva flexível com RR de 4 e 8 h, RR de 8 h contra 4 h, razão dos log RR e AIC",
               len(linhas_fx) == 2 and linhas_fx[0][0].startswith("Reta imposta") and linhas_fx[1][0].startswith("Curva flexível") and linhas_fx[0][1] == "1 (3)" and linhas_fx[1][1] == "3 (9)"
               and linhas_fx[0][5].startswith("2,00") and "imposta" in linhas_fx[0][5] and all(re.fullmatch(r"\d,\d\d \(\d,\d\d a \d,\d\d\)", linhas_fx[i][j]) for i in (0, 1) for j in (2, 3, 4)), linhas_fx)
        checar("Quadro 3: o RR da reta é o da Figura 1 (4 h e 8 h do mesmo modelo de referência)",
               linhas_fx[0][2].split(" ")[0] == xk_ini[2].split(" | ")[0].split(" ")[0] and linhas_fx[0][3].split(" ")[0] == xk_ini[5].split(" | ")[0].split(" ")[0], (linhas_fx[0], xk_ini[2], xk_ini[5]))
        checar("Quadro 3: nota diz que RR(8 h) = RR(4 h)² e que não são dois achados; interpretação compara reta e curva flexível",
               "RR(8 h) = RR(4 h)²" in pg.inner_text("#x-fx-note") and "um só achado" in pg.inner_text("#x-fx-note") and "curva flexível" in pg.inner_text("#x-fx-interp") and "Nas extremidades o suporte é pequeno" in pg.inner_text("#x-fx-interp"), pg.inner_text("#x-fx-interp")[:300])
        checar("Figura 2: legenda distingue a reta imposta da curva flexível e há barras de suporte de dias por hora",
               "Reta imposta" in pg.inner_text("#x-leg") and "Curva flexível" in pg.inner_text("#x-leg") and xpix("x-sup") > 300 and "dias no ajuste" in pg.inner_text("#x-supnote") and visivel("x-sup"))
        checar("Figura 2: a nota explica que a linha azul é uma reta imposta", "reta imposta" in pg.inner_text("#x-note"))
        checar("os cartões de RR de 8 h dizem que, na reta, o RR é o de 4 h ao quadrado", "elevado ao quadrado" in xk_ini[5] and "elevado ao quadrado" in k_ini[2], (xk_ini[5], k_ini[2]))
        checar("Quadro 3: RR com no máximo duas casas e sem travessão", not re.search(r"\d,\d{3}", pg.inner_text("#x-fx") + pg.inner_text("#x-fx-interp")) and not re.search("[—–]", pg.inner_text("#x-fx") + pg.inner_text("#x-fx-note") + pg.inner_text("#x-fx-interp") + pg.inner_text("#x-supnote")))
        # Quadro 4: suporte dos contrastes acumulados (janelas e eventos independentes por duração, duração observada e distribuição por ano)
        num = lambda t: int(t.replace(".", ""))
        def quadro4(unid):
            pg.wait_for_function("document.querySelectorAll('#x-sq tbody tr').length===10", timeout=120000)
            L4 = pg.eval_on_selector_all("#x-sq tbody tr", "trs=>trs.map(tr=>[...tr.children].map(td=>td.innerText))")
            leit = lambda ev: "frequente" if ev >= 30 else "poucos eventos" if ev >= 5 else "extrapolação"
            return L4, all(r[6] == leit(num(r[5])) for r in L4) and all(num(r[5]) <= num(r[4]) for r in L4) and all(num(L4[k][4]) >= num(L4[k + 1][4]) for k in (0, 1, 2, 3, 5, 6, 7, 8)) and L4[0][0].endswith(f"{unid} por dia ou mais") and L4[5][0].endswith(f"{unid} por dia ou mais")
        L4, ok4 = quadro4("h")
        checar("Quadro 4: 5 durações para cada nível de referência, com janelas e eventos que não crescem com a duração e leitura pela regra de eventos", len(L4) == 10 and ok4 and [r[1] for r in L4[:5]] == ["1", "2", "4", "8", "11 (cenário dos cartões de RR)"], L4)
        checar("Quadro 4: o RR da linha de 11 dias é o RR acumulado dos cartões (mesmo modelo)", L4[4][3].split(" ")[0] == xk_ini[2].split(" | ")[0].split(" ")[0] and L4[9][3].split(" ")[0] == xk_ini[5].split(" | ")[0].split(" ")[0], (L4[4], L4[9], xk_ini[2], xk_ini[5]))
        dur4 = pg.eval_on_selector_all("#x-sq-dur tbody tr", "trs=>trs.map(tr=>[...tr.children].map(td=>td.innerText))")
        an4 = pg.eval_on_selector_all("#x-sq-an tbody tr", "trs=>trs.map(tr=>[...tr.children].map(td=>td.innerText))")
        checar("Quadro 4: a duração observada soma as sequências e a tabela por ano fecha com o total e com a linha de 11 dias do quadro",
               len(dur4) == 2 and all(sum(num(v) for v in r[1:6]) == num(r[6]) for r in dur4) and an4[-1][0] == "Total" and len(an4) >= 15
               and all(sum(num(r[c]) for r in an4[:-1]) == num(an4[-1][c]) for c in range(1, 7)) and num(an4[-1][3]) == num(L4[4][4]) and num(an4[-1][6]) == num(L4[9][4]) and num(an4[-1][1]) == num(L4[0][4]), (dur4, an4[-1]))
        checar("Quadro 4: nota define dia exposto, janela e evento independente, e diz que os limiares da leitura são uma convenção; a interpretação aponta o que é extrapolação",
               all(t in pg.inner_text("#x-sq-note").lower() for t in ("dia com exposição", "janela", "evento independente", "convenção do painel")) and "interpretação" in pg.inner_text("#x-sq-interp").lower() and ("extrapolação" in pg.inner_text("#x-sq-interp").lower() or all(num(r[5]) >= 5 for r in (L4[4], L4[9]))), (pg.inner_text("#x-sq-note")[:400], pg.inner_text("#x-sq-interp")[:300]))
        checar("Quadro 4: sem travessão nas notas e na interpretação", not re.search("[—–]", pg.inner_text("#x-sq-note") + pg.inner_text("#x-sq-interp") + pg.inner_text("#x-sq-note2")))
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_02c_exposicao.png"), full_page=True)
        sel("x-exp", "haat"); xpronto(); xk_haat = xk()
        L4h, ok4h = quadro4("°C·h")
        checar("HAAT: o Quadro 4 é refeito com os níveis do HAAT e mantém as regras de leitura", ok4h and L4h != L4 and num(L4h[9][4]) <= num(L4h[4][4]) + 1000, L4h)
        pg.wait_for_function("document.querySelectorAll('#x-fx tbody tr').length===1", timeout=5000)
        checar("HAAT: o Quadro 3 informa a dimensão da base (k' = 45) e os gl efetivos; sem barras de suporte nem curva flexível",
               "45" in pg.inner_text("#x-fx") and re.search(r"\d+,\d", pg.inner_text("#x-fx tbody")) and "Spline penalizado" in pg.inner_text("#x-fx") and not visivel("x-supbox") and "Curva flexível" not in pg.inner_text("#x-leg") and "estimada e não imposta" in pg.inner_text("#x-fx-note"), pg.inner_text("#x-fx"))
        checar("medida HAAT na aba: nova curva e novos quadros", xk_haat != xk_ini and xpix("x-chart") > 1500, xk_haat)
        checar("medida HAAT na aba: a floresta é redesenhada com os níveis do HAAT", pg.inner_text("#x-leg2") != leg_ini and n_circ("x") == 60, (leg_ini, pg.inner_text("#x-leg2")))
        sel("x-exp", "horas"); xpronto(); fpronto()
        checar("voltar às horas: o Quadro 3 reaparece sem novo cálculo", pg.inner_text("#x-fx") == fx_ini)
        sel("x-causa", "externas"); xpronto(); xk_ext = xk(); fpronto()
        checar("causas externas: a comparação de reta e curva flexível é refeita para a causa", pg.inner_text("#x-fx") != fx_ini)
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
        # 5c2. ficha da aba de exposição-resposta (item 10 da revisão)
        fx_ = fch("x-sub")
        ok_, det_ = ficha_ok(fx_, ["Dados", "População", "Recorte", "Causa do óbito", "Período do ajuste", "Exposição e defasagem", "Retiradas", "Modelo", "Origem das curvas", "Ressalvas"])
        checar("aba Exposição-resposta: a ficha traz dados, população, recorte, causa, período do ajuste, exposição, defasagem, retiradas, modelo e ressalvas", ok_, (det_, list(fx_)))
        checar("aba Exposição-resposta: a ficha descreve o Índice de Calor (IC), a defasagem de 0 a 10 dias e a família do modelo",
               "Índice de Calor (IC)" in fx_.get("Exposição e defasagem", "") and "defasagem de 0 a 10 dias" in fx_.get("Exposição e defasagem", "") and re.search(r"família (binomial negativa|quase-Poisson)", fx_.get("Modelo", "")), fx_)
        # 5d. Figura 4: mapa de horas por dia x limiar (um modelo por célula, uma coluna por pedido)
        hm_cols = lambda: pg.evaluate("()=>[...document.querySelectorAll('#x-hm tr:first-child th')].slice(1).map(t=>t.innerText)")
        hm_pend = lambda: pg.evaluate("()=>[...document.querySelectorAll('#x-hm td:not(.rl)')].filter(t=>t.innerText==='…').length")
        hm_pronto = lambda t=600000: pg.wait_for_function("document.querySelectorAll('#x-hm td:not(.rl)').length===104 && ![...document.querySelectorAll('#x-hm td:not(.rl)')].some(t=>t.innerText==='…') && document.getElementById('x-hm-interp').innerText.includes('combinações estimadas')", timeout=t)
        checar("Figura 4: cabeçalho com os limiares de 32 a 44 °C e 8 linhas de horas", hm_cols() == [str(k) for k in range(32, 45)] and pg.evaluate("()=>document.querySelectorAll('#x-hm td.rl').length") == 8, hm_cols())
        pg.wait_for_function("[...document.querySelectorAll('#x-hm td:not(.rl)')].some(t=>/^[0-9],[0-9]{2}$/.test(t.childNodes[0].textContent))", timeout=120000)
        checar("Figura 4: a primeira coluna recebida é a de 36 °C e a tabela mostra progresso", "Calculando as colunas do mapa" in pg.inner_text("#x-hm-prog") or hm_pend() == 0, pg.inner_text("#x-hm-prog"))
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_02d_mapa_parcial.png"), full_page=True)
        hm_pronto()
        celulas = pg.evaluate("()=>[...document.querySelectorAll('#x-hm td:not(.rl)')].map(t=>({t:t.childNodes[0].textContent,title:t.title,bold:t.style.fontWeight,sub:(t.querySelector('.sub')||{}).innerText||null,outline:t.style.outline}))")
        rrs = [c for c in celulas if re.match(r"^\d,\d{2}$", c["t"])]
        checar("Figura 4: 104 células, a maioria estimada, o resto com traço", len(celulas) == 104 and len(rrs) > 60 and all(c["t"] in ("–",) or re.match(r"^\d,\d{2}$", c["t"]) for c in celulas), (len(celulas), len(rrs)))
        checar("Figura 4: o texto da célula traz limiar, horas, RR com IC 95% e dias com exposição", all(("IC ≥" in c["title"] and "IC 95%" in c["title"] and "dias com exposição" in c["title"]) for c in rrs))
        cel_ref = pg.evaluate("()=>document.querySelector('#x-hm tr:nth-child(5) td:nth-child(6)').childNodes[0].textContent")
        m_ref = re.search(r"Para o dia com ≥ 4 h de IC ≥ 36 °C \(combinação de referência do painel\), RR = (\d,\d{2})", pg.inner_text("#x-hm-interp"))
        checar("Figura 4: o RR da célula de referência (36 °C, 4 h) bate com o da interpretação", m_ref and m_ref.group(1) == cel_ref, pg.inner_text("#x-hm-interp")[:300])
        # dias expostos e eventos independentes em cada célula; a célula (36 °C, 4 h) é a linha de 1 dia do Quadro 4 (outro caminho de cálculo, no servidor)
        subs = [c["sub"] for c in celulas]
        checar("Figura 4: cada célula mostra os dias com exposição (d) e os eventos independentes (ev.), no texto e na dica", all(s_ and re.match(r"^[\d.]+ d · [\d.]+ ev\.$", s_) for s_ in subs) and all(re.search(r"[\d.]+ dias com exposição em [\d.]+ evento\(s\) independente\(s\)", c["title"]) for c in celulas), subs[:4])
        def _dev(c):
            m_ = re.search(r"([\d.]+) dias com exposição em ([\d.]+) evento", c["title"]); return int(m_.group(1).replace(".", "")), int(m_.group(2).replace(".", ""))
        def _sub(c):
            m_ = re.match(r"^([\d.]+) d · ([\d.]+) ev\.$", c["sub"]); return int(m_.group(1).replace(".", "")), int(m_.group(2).replace(".", ""))
        checar("Figura 4: o texto da célula e a dica dizem o mesmo número de dias e de eventos, e os eventos nunca superam os dias", all(_sub(c) == _dev(c) and _dev(c)[1] <= _dev(c)[0] for c in celulas))
        L4_ref = L4[0]                                                                         # 4 h por dia ou mais, duração de 1 dia: dias expostos (col. 4) e eventos independentes (col. 5)
        d36, e36 = _dev(celulas[3 * 13 + 4])                                                   # linha H = 4 h (4ª linha), coluna K = 36 °C (5ª coluna)
        checar("Figura 4: a célula (36 °C, 4 h) tem os mesmos dias com exposição e eventos independentes da linha de 1 dia do Quadro 4", (d36, e36) == (num(L4_ref[4]), num(L4_ref[5])), ((d36, e36), L4_ref))
        checar("Figura 4: nas células aninhadas, os dias com exposição não crescem com as horas (cada coluna)", all(_dev(celulas[i * 13 + j])[0] >= _dev(celulas[(i + 1) * 13 + j])[0] for i in range(7) for j in range(13)))
        checar("Figura 4: só a célula de referência tem contorno; o máximo não é destacado", [i for i, c in enumerate(celulas) if "2px" in c["outline"]] == [3 * 13 + 4] and "O maior valor da tabela" not in pg.inner_text("#x-hm-interp") and "não indica o melhor limiar" in pg.inner_text("#x-hm-interp") and pg.eval_on_selector_all("#x-hm-interp b", "bs=>bs.length") == 1, pg.inner_text("#x-hm-interp")[:500])
        pg.uncheck("#x-hm-n")
        checar("Figura 4: desmarcar 'mostrar dias e eventos' tira a segunda linha das células e mantém a dica", pg.evaluate("()=>document.querySelectorAll('#x-hm td .sub').length")==0 and "dias com exposição" in pg.evaluate("()=>document.querySelector('#x-hm tr:nth-child(5) td:nth-child(6)').title"))
        pg.check("#x-hm-n")
        checar("Figura 4: marcar de novo devolve as 104 linhas de dias e eventos", pg.evaluate("()=>document.querySelectorAll('#x-hm td .sub').length")==104)
        checar("Figura 4: a interpretação e a nota não usam travessão", "—" not in pg.inner_text("#x-hm-interp") + pg.inner_text("#x-hm-note") and "–" not in pg.inner_text("#x-hm-interp"))
        sem_ic = pg.evaluate("()=>[...document.querySelectorAll('#x-hm td:not(.rl)')].filter(t=>/^[0-9],/.test(t.innerText) && t.style.fontWeight!=='700').length")
        pg.check("#x-hm-sig")
        transp = pg.evaluate("()=>[...document.querySelectorAll('#x-hm td:not(.rl)')].filter(t=>/^[0-9],/.test(t.innerText) && t.style.fontWeight!=='700' && (t.style.backgroundColor==='transparent'||t.style.backgroundColor==='rgba(0, 0, 0, 0)')).length")
        checar("Figura 4: 'destacar só IC que não inclui 1' apaga a cor das células não significativas", transp == sem_ic, (transp, sem_ic))
        pg.uncheck("#x-hm-sig")
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_02d_mapa.png"), full_page=True)
        # trocar o recorte pede novas colunas; voltar usa o que já chegou
        sel("x-causa", "externas"); hm_pronto()
        checar("Figura 4: outra causa do óbito gera outro mapa", [c["t"] for c in pg.evaluate("()=>[...document.querySelectorAll('#x-hm td:not(.rl)')].map(t=>({t:t.childNodes[0].textContent}))")] != [c["t"] for c in celulas])
        sel("x-causa", "naturais")
        pg.wait_for_function("document.getElementById('x-hm-interp').innerText.includes('combinações estimadas')", timeout=5000)
        checar("Figura 4: voltar ao recorte anterior redesenha na hora, sem novo cálculo", [c["t"] for c in pg.evaluate("()=>[...document.querySelectorAll('#x-hm td:not(.rl)')].map(t=>({t:t.childNodes[0].textContent}))")] == [c["t"] for c in celulas])
        sel("x-local", "Ignorado"); sel("x-faixa", "30-39")
        pg.wait_for_function("document.getElementById('x-hm-note').innerText.includes('Menos de 300 óbitos')", timeout=5000)
        checar("Figura 4: recorte com poucos óbitos informa o limite e esvazia a tabela", pg.evaluate("()=>document.getElementById('x-hm').innerHTML==='' ") )
        sel("x-local", "Todos os locais"); sel("x-faixa", "Todas as idades"); xpronto()

        # 5e. comparação de dois locais do óbito, lado a lado
        yk = lambda: pg.eval_on_selector_all("#y-kpis .kpi", "els=>els.map(e=>[e.querySelector('.v').innerText, e.querySelector('.l').innerText].join(' | '))")
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
        checar("comparação: o texto traz o RR acumulado dos dois locais e a ressalva sobre o teste", "COMPARAÇÃO ENTRE OS LOCAIS DO ÓBITO" in t_comp and "“Todos os locais”" in t_comp and "“Hospital”" in t_comp and "teste de interação" in t_comp and "não estabelecem, por si só" in t_comp and "não são independentes" in t_comp and "sobrepõ" not in t_comp and not re.search("[—–]", t_comp), t_comp)
        # 5e2. ficha dos dois recortes e comparação entre grupos sem inferência pela sobreposição dos intervalos
        fx_, fy_ = fch("x-sub"), fch("y-sub")
        checar("comparação: cada recorte tem a sua ficha, com o local do óbito e a ressalva sobre a comparação entre grupos",
               "local do óbito: todos os locais" in fx_.get("Recorte", "") and "local do óbito: hospital" in fy_.get("Recorte", "") and "teste de interação" in fx_.get("Comparação entre grupos", "") and "teste de interação" in fy_.get("Comparação entre grupos", ""), (fx_, fy_))
        ct_ = pg.inner_text("#x-comp-txt")
        checar("comparação: o texto traz a ressalva sobre o teste de interação, sem concluir pela sobreposição dos intervalos",
               "teste de interação" in ct_ and "sobrepõ" not in ct_ and "sobrepo" not in ct_, ct_[:500])
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

        # 5f. aba de causas específicas (CID-10): um modelo por causa; q de Benjamini e Hochberg dentro de duas famílias fixas (principal e exploratória);
        # capítulo e significância só filtram a exibição; todas as estimativas visíveis por padrão
        # (precisa de um cache com a causa básica de cada óbito; com cache antigo o servidor avisa e esta parte é pulada)
        kcod = lambda: pg.evaluate("()=>[...document.querySelectorAll('#k-fig g[data-c]')].map(g=>g.dataset.c)")
        ktit = lambda: pg.evaluate("()=>[...document.querySelectorAll('#k-fig g[data-c] title')].map(t=>t.textContent)")
        kpronto = lambda t=900000: pg.wait_for_function("document.getElementById('k-prog').innerText==='' && /causas avaliadas|Nenhuma causa|Menos de/.test(document.getElementById('k-interp').innerText + document.getElementById('k-note').innerText)", timeout=t)
        num_br = lambda t: 0.0005 if t.startswith("<") else float(t.replace(",", "."))
        # oráculo independente da família principal: os 15 grupos do estudo de referência, como listados no texto de Métodos (R/metodos.R)
        GRUPOS_REF_PY = [("J", 9, 9), ("J", 12, 18), ("J", 40, 47), ("J", 0, 6), ("J", 20, 39), ("J", 60, 70), ("J", 80, 99), ("R", 9, 9), ("U", 4, 4), ("I", 10, 15), ("I", 20, 25), ("I", 50, 50),
                         ("I", 60, 69), ("I", 0, 9), ("I", 26, 49), ("I", 51, 52), ("I", 70, 99), ("C", 0, 97), ("G", 30, 31), ("F", 1, 1), ("F", 3, 3), ("E", 10, 14), ("N", 17, 19), ("A", 40, 41),
                         ("N", 39, 39), ("R", 0, 99)]
        def principal_py(c): return any(c[0] == l and a <= int(c[1:3]) <= b for l, a, b in GRUPOS_REF_PY)
        def cap_py(c):
            l = c[0]
            if l == "B": return "A"
            if l == "D": return "C" if int(c[1:3]) < 50 else "D"
            if l in "VWXY": return "X"
            return l
        def krows():
            r = pg.evaluate("""()=>[...document.querySelectorAll('#k-fig g[data-c]')].map(g=>({c:g.dataset.c,f:g.dataset.f,t:g.querySelector('title').textContent,fill:g.querySelector('circle').getAttribute('fill'),sw:g.querySelector('circle').getAttribute('stroke-width')}))""")
            for x in r:
                x["q"] = num_br(re.search(r"q = (<?[0-9,]+)", x["t"]).group(1)) if "q = " in x["t"] else None
                x["p"] = num_br(re.search(r"p = (<?[0-9,]+)", x["t"]).group(1))
            return r
        def qmap(): return {x["c"]: x["q"] for x in krows()}
        filtro = lambda: pg.inner_text("#k-filtro")
        pg.click("nav button[data-tab=cid]")
        pg.wait_for_function("!document.getElementById('tab-cid').classList.contains('hide')", timeout=5000)
        checar("aba CID: filtros de recorte, medida, nível e famílias; capítulo e significância como filtros de exibição; filtros de causa e retiradas próprios",
               opcoes("k-exp") == ["horas", "haat"] and opcoes("k-conj") == ["todas", "principal"] and len(opcoes("k-cap")) == 19 and len(opcoes("k-nivel")) == 2
               and pg.query_selector("#k-sig") and not pg.query_selector("#k-todos") and not pg.is_checked("#k-sig") and pg.input_value("#k-cap") == "all" and pg.input_value("#k-conj") == "todas"
               and opcoes("k-causa") == ["naturais", "todas_sem_covid", "todas", "externas"] and all(pg.query_selector(f"#k-r-{c}") for c in ("covid", "nc", "clima")))
        pg.wait_for_function("document.getElementById('k-prog').innerText!=='' || document.querySelectorAll('#k-fig g[data-c]').length>0 || document.getElementById('k-note').innerText!==''", timeout=120000)
        pg.wait_for_function("!document.getElementById('k-prog').innerText.startsWith('Obtendo')", timeout=120000)
        if "não traz a causa básica" in pg.inner_text("#k-prog") or "Não foi possível obter" in pg.inner_text("#k-prog"):
            print("PULADO: o cache deste teste não traz a causa básica de cada óbito (refaça com atualizar_cache.R --forcar ou montar_cache_local.R): ", pg.inner_text("#k-prog")[:160], flush=True)
        else:
            # só a família principal: todas as estimativas aparecem, sem filtro, e todas pertencem aos 15 grupos
            sel("k-conj", "principal"); kpronto()
            rp = krows(); cp = [x["c"] for x in rp]
            checar("aba CID: só a família principal: todas as causas avaliadas aparecem por padrão (sem filtro de significância) e só há causas dos 15 grupos do referencial",
                   len(cp) > 10 and all(x["f"] == "p" for x in rp) and all(principal_py(c) for c in cp) and any(x["q"] >= 0.05 for x in rp), (len(cp), [c for c in cp if not principal_py(c)]))
            m = re.search(r"Mostrando ([\d.]+) de ([\d.]+) causas avaliadas, sem filtro de exibição", filtro())
            checar("aba CID: a linha 'Mostrando m de N causas' confere com a figura e informa que o q não muda com os filtros",
                   m and int(m.group(1).replace(".", "")) == len(cp) == int(m.group(2).replace(".", "")) and "não muda com esses filtros" in filtro() and "família principal" in filtro().lower(), filtro())
            q_prin = qmap()
            if capturas: pg.screenshot(path=os.path.join(capturas, "app_02f_cid_principal.png"), full_page=True)
            # as duas famílias: a lista completa, em dois blocos
            sel("k-conj", "todas"); kpronto()
            rt = krows(); ct = [x["c"] for x in rt]
            qt = {x["c"]: x["q"] for x in rt}
            checar("aba CID: duas famílias: a principal é o conjunto fixo dos 15 grupos (conferido por um oráculo independente) e a exploratória reúne o resto",
                   len(ct) > len(cp) and all((x["f"] == "p") == principal_py(x["c"]) for x in rt) and any(x["f"] == "e" for x in rt) and sorted(x["c"] for x in rt if x["f"] == "p") == sorted(cp), (len(ct), len(cp)))
            checar("aba CID: escolher só a família principal não muda o q dela", all(q_prin[c] == qt[c] for c in cp), [(c, q_prin[c], qt[c]) for c in cp if q_prin[c] != qt[c]][:5])
            fam_tx = pg.inner_text("#k-fig")
            checar("aba CID: a figura tem um bloco por família, com o número de causas e a explicação do q", "Família principal" in fam_tx and "Família exploratória" in fam_tx and "q de Benjamini e Hochberg dentro da família" in fam_tx, fam_tx[:300])
            checar("aba CID: marcador cheio na família principal e vazado na exploratória",
                   all(x["sw"] == ("1.5" if x["f"] == "p" else "2") for x in rt) and len({x["fill"] for x in rt if x["f"] == "e"}) == 1 and "vazado" in pg.inner_text("#k-leg5") and "cheio" in pg.inner_text("#k-leg5"), pg.inner_text("#k-leg5"))
            m2 = re.search(r"Mostrando ([\d.]+) de ([\d.]+) causas avaliadas, sem filtro", filtro())
            checar("aba CID: sem filtro, todas as causas avaliadas estão à vista e a linha de filtro conta as duas famílias", m2 and int(m2.group(1).replace(".", "")) == len(ct) == int(m2.group(2).replace(".", "")) and "família exploratória" in filtro().lower(), filtro())
            # q válido dentro de cada família: q >= p, não decresce com p e respeita o limite de Benjamini e Hochberg
            ok_bh = True; det = []
            for f in ("p", "e"):
                rr_f = [x for x in rt if x["f"] == f]; n = len(rr_f)
                o = sorted(rr_f, key=lambda x: (x["p"], x["q"]))
                if not all(x["q"] >= x["p"] - 0.0006 for x in rr_f): ok_bh = False; det.append((f, "q < p"))
                if not all(o[i]["q"] <= o[i + 1]["q"] + 0.0011 for i in range(n - 1)): ok_bh = False; det.append((f, "q decresce"))
                if not all(x["q"] <= min(1, (x["p"] + 0.0005) * n / (i + 1)) + 0.0011 for i, x in enumerate(o)): ok_bh = False; det.append((f, "q acima de p n / r"))
            checar("aba CID: dentro de cada família, q nunca fica abaixo do p, não decresce com o p e respeita o limite p n / r (Benjamini e Hochberg)", ok_bh, det)
            # filtro de capítulo: só a lista, sem mudar q nem a família
            sel("k-cap", "I")
            rI = krows(); cI = [x["c"] for x in rI]
            checar("aba CID: o filtro de capítulo mostra só as causas do capítulo, com o mesmo q e a mesma família de antes",
                   len(cI) > 0 and sorted(cI) == sorted(c for c in ct if cap_py(c) == "I") and all(qt[x["c"]] == x["q"] and ((x["f"] == "p") == principal_py(x["c"])) for x in rI), (cI, [c for c in ct if cap_py(c) == "I"]))
            mI = re.search(r"Mostrando ([\d.]+) de ([\d.]+) causas avaliadas \(filtros de exibição: capítulo ", filtro())
            checar("aba CID: com o filtro de capítulo a linha informa 'Mostrando m de N' e que o q não muda; as famílias continuam as mesmas",
                   mI and int(mI.group(1).replace(".", "")) == len(cI) and int(mI.group(2).replace(".", "")) == len(ct) and "não muda com esses filtros" in filtro(), filtro())
            # filtro de significância: só as linhas com q < 0,05
            pg.check("#k-sig")
            rS = krows()
            checar("aba CID: 'só causas com q < 0,05' mostra exatamente as causas com q < 0,05 do capítulo e não recalcula o q",
                   len(rS) > 0 and sorted(x["c"] for x in rS) == sorted(c for c in cI if qt[c] < 0.05) and all(qt[x["c"]] == x["q"] for x in rS), ([x["c"] for x in rS], [(c, qt[c]) for c in cI]))
            sel("k-cap", "all")
            rS2 = krows()
            checar("aba CID: sem filtro de capítulo, o filtro de significância deixa as causas com q < 0,05 das duas famílias, com o mesmo q",
                   sorted(x["c"] for x in rS2) == sorted(c for c in ct if qt[c] < 0.05) and all(qt[x["c"]] == x["q"] for x in rS2), len(rS2))
            pg.uncheck("#k-sig")
            checar("aba CID: sem filtros, a lista volta a ter todas as causas", len(krows()) == len(ct))
            tit = ktit()
            txt_cid = pg.inner_text("#k-note") + " " + pg.inner_text("#k-interp") + " " + pg.inner_text("#k-filtro") + " " + pg.inner_text("#k-leg5")
            checar("aba CID: nota e interpretação sem travessão e com as duas famílias, sem correção conjunta e com o q independente dos filtros",
                   not re.search("[—–]", txt_cid) and all(t in txt_cid.lower() for t in ("família principal", "família exploratória", "não há correção conjunta", "não depende do capítulo")) and "Na família principal" in pg.inner_text("#k-interp") and "Na família exploratória" in pg.inner_text("#k-interp"), txt_cid[:400])
            pg.wait_for_function("document.getElementById('k-h2b').innerText.length>20 && document.getElementById('k-chart')", timeout=120000)
            pg.wait_for_function("document.getElementById('k-selnote').innerText.startsWith('Causa escolhida')", timeout=120000)
            checar("aba CID: a Figura 5b abre com uma causa já escolhida e desenha a série semanal", xpix("k-chart") > 1500 and "Óbitos semanais por causa: " in pg.inner_text("#k-h2b"), pg.inner_text("#k-h2b"))
            i5b = pg.inner_text("#k-interp2")
            checar("aba CID: a Figura 5b chama a razão de observado/esperado sem calor (O/E), diz que não é o RR do modelo e traz as razões das semanas de calor e das demais",
                   "razão observado/esperado sem calor (O/E)" in i5b and "não é o RR do modelo" in i5b and len(re.findall(r"O/E\)? = \d,\d{2}", i5b)) == 2 and "excesso atribuído" not in i5b and not re.search(r"RR (=|de) \d,\d{2}", i5b), i5b[:400])
            if capturas: pg.screenshot(path=os.path.join(capturas, "app_02f_cid.png"), full_page=True)
            outra = [c for c in kcod() if c not in pg.inner_text("#k-h2b")]
            if outra:
                pg.click(f"#k-fig g[data-c={outra[0]}]")
                pg.wait_for_function("c=>document.getElementById('k-h2b').innerText.includes(c) && document.getElementById('k-selnote').innerText.startsWith('Causa escolhida')", arg=outra[0], timeout=120000)
                checar("aba CID: clicar em uma causa troca a série semanal", outra[0] in pg.inner_text("#k-selnote") and xpix("k-chart") > 1500, pg.inner_text("#k-selnote"))
            # outra medida e outro nível, em um recorte com poucas causas (as famílias continuam as mesmas e o q é refeito dentro delas)
            sel("k-faixa", "30-39"); kpronto()
            rs0 = krows(); t0 = ktit()
            checar("aba CID: recorte de 30 a 39 anos: poucas causas, cada uma na sua família, com q dentro da família", 0 < len(rs0) <= 5 and all(((x["f"] == "p") == principal_py(x["c"])) and x["q"] is not None for x in rs0), [(x["c"], x["f"], x["q"]) for x in rs0])
            sel("k-exp", "haat")
            checar("aba CID: a medida HAAT refaz os níveis e pede as causas de novo", opcoes("k-nivel") == ["0", "1"])
            kpronto()
            checar("aba CID: com o HAAT o resultado é outro", ktit() != t0, (len(ktit()), len(t0)))
            sel("k-exp", "horas"); sel("k-nivel", "1"); kpronto()
            checar("aba CID: o segundo nível de exposição dá outro resultado", ktit() != t0)
            sel("k-nivel", "0"); sel("k-faixa", "Todas as idades"); sel("k-causa", "externas"); kpronto()
            ext = kcod()
            checar("aba CID: causas externas na aba só listam causas dos capítulos V a Y, todas na família exploratória", len(ext) > 0 and all(c[0] in "VWXY" for c in ext) and all(x["f"] == "e" for x in krows()) and "causas externas" in pg.inner_text("#k-sub"), ext)
            sel("k-causa", "naturais"); sel("k-local", "Todos os locais"); sel("k-faixa", "5-9"); kpronto(120000)
            checar("aba CID: recorte com menos de 1.500 óbitos por causa informa o limite", "Nenhuma causa tem pelo menos 1.500 óbitos" in pg.inner_text("#k-note") and len(kcod()) == 0, pg.inner_text("#k-note")[:200])
            sel("k-local", "Ignorado"); sel("k-faixa", "30-39")
            pg.wait_for_function("document.getElementById('k-note').innerText.includes('Menos de 300 óbitos')", timeout=5000)
            checar("aba CID: recorte com menos de 300 óbitos informa o limite sem pedir ao servidor", "modelo não estimado" in pg.inner_text("#k-note"))
            sel("k-local", "Todos os locais"); sel("k-faixa", "Todas as idades")
            checar("aba CID: os filtros da aba não mudam os da Figura 1", pg.input_value("#s-causa") == "naturais" and pg.input_value("#x-causa") == "naturais")
            # 5f2. ficha da aba de causas específicas (item 10 da revisão)
            kpronto()
            fk_ = fch("k-sub")
            ok_, det_ = ficha_ok(fk_, ["Dados", "Recorte", "Período do ajuste", "Exposição e defasagem", "Nível de exposição", "Modelo", "Família de testes", "Ressalvas"])
            checar("aba Causas específicas: a ficha traz dados, recorte, período do ajuste, nível de exposição, modelo por causa, famílias de testes e ressalvas", ok_, (det_, list(fk_)))
            checar("aba Causas específicas: a ficha descreve o q de Benjamini e Hochberg por família e a quase-Poisson como alternativa", "Benjamini e Hochberg" in fk_.get("Família de testes", "") and "quase-Poisson" in fk_.get("Modelo", ""), fk_)

        # 5g. aba de diagnósticos e sensibilidades: diagnósticos do modelo principal (Quadro 1) e 12 análises que mudam uma escolha por vez (Quadro 2)
        dk = lambda: pg.eval_on_selector_all("#d-kpis .kpi", "els=>els.map(e=>e.innerText.replace(/\\n/g,' | '))")
        dlinhas = lambda: pg.eval_on_selector_all("#d-sens tbody tr:not(.gr)", "trs=>trs.map(tr=>tr.innerText)")
        dpronto = lambda t=420000: pg.wait_for_function("document.querySelectorAll('#d-sens tbody tr:not(.gr)').length===13 && !document.getElementById('d-sens').innerText.includes('calculando') && !document.getElementById('d-sens').innerText.includes('não foi possível')", timeout=t)
        pg.click("nav button[data-tab=dia]")
        pg.wait_for_function("!document.getElementById('tab-dia').classList.contains('hide')", timeout=5000)
        checar("aba Diagnósticos: filtros de recorte, medida, causa e retiradas próprios",
               opcoes("d-exp") == ["horas", "haat"] and opcoes("d-causa") == ["naturais", "todas_sem_covid", "todas", "externas"]
               and all(pg.query_selector(f"#d-r-{c}") for c in ("covid", "nc", "clima")) and "local do óbito" in pg.inner_text("#tab-dia").lower())
        pg.wait_for_function("document.querySelectorAll('#d-kpis .kpi').length>0", timeout=120000)
        checar("aba Diagnósticos: cartões do modelo principal (família, dispersão, autocorrelação, Ljung-Box, gl efetivos, convergência)",
               len(dk()) == 6 and any("ρ(1)" in t for t in dk()) and any("Ljung-Box" in t for t in dk()) and any("graus de liberdade efetivos" in t for t in dk()) and any("REML" in t for t in dk()), dk())
        checar("aba Diagnósticos: figura da autocorrelação desenhada", xpix("d-acf") > 1500)
        suaves = pg.eval_on_selector_all("#d-suave tbody tr", "trs=>trs.map(tr=>tr.children[0].innerText)")
        checar("aba Diagnósticos: tabela de termos traz a base cruzada e os termos suaves do modelo", len(suaves) >= 4 and suaves[0].startswith("Base cruzada") and any("time_id" in t for t in suaves) and any("dia_ano" in t for t in suaves), suaves)
        checar("aba Diagnósticos: interpretação do Quadro 1 cita a dependência dos resíduos e o spline cíclico da pandemia",
               "dependência" in pg.inner_text("#d-interp") and "cíclico" in pg.inner_text("#d-interp") and "estreitos demais" in pg.inner_text("#d-interp"), pg.inner_text("#d-interp")[:300])
        dpronto()
        L = dlinhas()
        checar("aba Diagnósticos: Quadro 2 tem o ajuste principal e as 12 análises", len(L) == 13 and L[0].startswith("Ajuste principal"), len(L))
        fd_ = fch("d-sub")
        ok_, det_ = ficha_ok(fd_, ["Dados", "Recorte", "Período do ajuste", "Exposição e defasagem", "Retiradas", "Análises", "Ressalvas"])
        checar("aba Diagnósticos: a ficha traz dados, recorte, período do ajuste, exposição, retiradas, análises e ressalvas", ok_, (det_, list(fd_)))
        for r in ("Dia da semana", "metade dos nós", "dobro dos nós", "Defasagem máxima de 7", "Defasagem máxima de 14", "retirado do ajuste", "sem termo próprio", "não cíclico", "óbitos diários de COVID-19",
                  "Meses de registro não consolidado mantidos", "Dias sem dado de clima contados como dias sem calor", "Especificação anterior do painel"):
            checar(f"aba Diagnósticos: linha '{r}'", any(r in t for t in L[1:]))
        checar("aba Diagnósticos: cada linha traz RR e IC nos dois níveis, dias com ≥ 4 h de IC ≥ 36 °C, eventos e diagnóstico residual", all(len(re.findall(r"[0-9],[0-9]{2} \([0-9],[0-9]{2} a [0-9],[0-9]{2}\)", t)) == 2 and re.search(r"[0-9.]+ \([0-9.]+\)", t) for t in L), L[:2])
        checar("aba Diagnósticos: o COVID retirado do ajuste tem menos dias que o principal", int(L[[i for i, t in enumerate(L) if "retirado do ajuste" in t][0]].split("\t")[1].replace(".", "")) < int(L[0].split("\t")[1].replace(".", "")), L[0])
        checar("aba Diagnósticos: a interpretação do Quadro 2 compara valores estimados e não o IC", "RR acumulado das 12 análises" in pg.inner_text("#d-sinterp") and "não" in pg.inner_text("#d-sinterp"))
        checar("aba Diagnósticos: textos sem travessão", not re.search("[—–]", pg.inner_text("#d-interp") + pg.inner_text("#d-sinterp") + pg.inner_text("#d-snote") + pg.inner_text("#d-note")))
        # a regra do marcador: ● só onde o log-RR varia 20% ou mais em relação ao principal (o texto de cada linha traz a variação em % nos dois níveis)
        vari = lambda t: [int(x.replace("−", "-").replace("+", "")) for x in re.findall(r"variação do log-RR: ([+−-]?[0-9]+)%", t)]
        checar("aba Diagnósticos: o marcador ● aparece só nas linhas com variação de 20% ou mais", all(("●" in t) == any(abs(v) >= 20 for v in vari(t)) for t in L[1:]), [(t[:40], vari(t), "●" in t) for t in L[1:]])
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_02g_diagnosticos.png"), full_page=True)
        d_ini = pg.inner_text("#d-sens")
        sel("d-exp", "haat")
        dpronto()
        checar("aba Diagnósticos: a medida HAAT refaz o quadro com a base cruzada de spline penalizado e outros níveis de referência",
               pg.inner_text("#d-sens") != d_ini and "Spline penalizado" in pg.inner_text("#d-suave") and "°c·h" in pg.inner_text("#d-sens").lower(), pg.inner_text("#d-suave")[:300])
        sel("d-exp", "horas"); dpronto()
        sel("d-causa", "externas"); dpronto()
        checar("aba Diagnósticos: trocar a causa refaz o quadro", pg.inner_text("#d-sens") != d_ini and "externas" in pg.inner_text("#d-sub"), pg.inner_text("#d-sub")[:200])
        sel("d-causa", "naturais")
        sel("d-local", "Ignorado"); sel("d-faixa", "30-39")
        pg.wait_for_function("document.getElementById('d-note').innerText.includes('Menos de 300 óbitos')", timeout=5000)
        checar("aba Diagnósticos: recorte com menos de 300 óbitos informa o limite e não mostra quadros", "modelo não estimado" in pg.inner_text("#d-note") and pg.inner_text("#d-kpis") == "" and dlinhas() == [])
        sel("d-local", "Todos os locais"); sel("d-faixa", "Todas as idades"); dpronto()
        checar("aba Diagnósticos: os filtros da aba não mudam os da Figura 1", pg.input_value("#s-causa") == "naturais" and pg.input_value("#x-causa") == "naturais" and pg.input_value("#s-local") == "Todos os locais")

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
        lin_ = txt.split("\n"); com_ = [l for l in lin_ if l.startswith("# ")]; cab_ = [l for l in lin_ if not l.startswith("# ") and l.strip()][0]
        checar("CSV semanal: as linhas iniciais com # trazem dados, período do ajuste, exposição, retiradas, modelo e ressalvas",
               com_ and com_[0].startswith("# Dados:") and all(any(l.startswith("# " + r + ":") for l in com_) for r in ("População", "Recorte", "Período do ajuste", "Exposição e defasagem", "Retiradas", "Modelo", "Ressalvas", "Período exibido")), com_[:12])
        checar("CSV semanal: cabeçalho com os nomes do vocabulário do painel",
               cab_ == "semana_inicio;ano_epidemiologico;semana_epidemiologica;observado;esperado_sem_calor;faixa_inferior_95;faixa_superior_95;dias_com_ic_maximo_ge_36;dias_nc2_a_nc5_estimados_retrospectivamente;registro_sim", cab_)
        checar("CSV semanal: sem travessão nas linhas de ficha", not re.search("[—–]", "\n".join(com_)))
        sel("s-esc", "dia"); pronto()
        with pg.expect_download(timeout=15000) as d2:
            pg.click("#s-csv")
        txt2 = open(d2.value.path(), encoding="utf-8-sig").read(); lin2 = txt2.split("\n"); cab2 = [l for l in lin2 if not l.startswith("# ") and l.strip()][0]
        checar("CSV diário: ficha com a linha do dia com exposição em t a t−3 e cabeçalho do vocabulário",
               any(l.startswith("# Dia com exposição em t a t−3:") for l in lin2) and cab2.startswith("dia;observado;esperado_sem_calor;faixa_inferior_95;faixa_superior_95;horas_ic_ge_36;dia_com_4h_ic_ge_36;dia_com_exposicao_t_a_t3;ic_maximo_c;ic_medio_c;temperatura_media_ar_c;nc_estimado_retrospectivamente"), (cab2, lin2[:12]))
        sel("s-esc", "sem"); sel("s-ini", pg.eval_on_selector("#s-ini", "e=>e.options[0].value")); pronto()

        # 6b. ficha do resultado e vocabulário do painel (item 10 da revisão)
        sub_ = pg.inner_text("#sub")
        checar("cabeçalho: estudo ecológico de série temporal com componente analítico, Índice de Calor (IC) por extenso e aviso de que não há alerta operacional",
               "Estudo ecológico de série temporal" in sub_ and "componente analítico" in sub_ and "Índice de Calor (IC)" in sub_ and "não são alertas operacionais" in sub_, sub_)
        F1 = fch("s-ficha")
        ok_, det_ = ficha_ok(F1, ["Dados", "População", "Recorte", "Causa do óbito", "Período do ajuste", "Exposição e defasagem", "Retiradas", "Modelo", "Período exibido", "Semana de calor", "Ressalvas"])
        checar("Figura 1: a ficha traz dados, população, recorte, causa, período do ajuste, exposição, defasagem, retiradas, modelo, período exibido, semana de calor e ressalvas", ok_, (det_, list(F1)))
        checar("Figura 1: a ficha informa as datas de atualização do SIM e do clima e a data de geração dos dados", "SIM atualizado em" in F1.get("Dados", "") and "clima atualizado em" in F1.get("Dados", "") and "dados gerados em" in F1.get("Dados", ""), F1.get("Dados"))
        checar("Figura 1: ficha com a família do modelo, a defasagem de 0 a 10 dias e a população analisada",
               re.search(r"família (binomial negativa \(θ = [\d,]+\)|quase-Poisson \(dispersão φ = [\d,]+)", F1.get("Modelo", "")) and "defasagem de 0 a 10 dias" in F1.get("Exposição e defasagem", "") and "residentes" in F1.get("População", ""), F1)
        checar("Figura 1: a ficha descreve as retiradas do ajuste principal (dias sem registro, meses não consolidados, dias sem clima)",
               "retirados do ajuste: dias sem registro no SIM; meses de registro não consolidado; dias sem dado de clima" in F1.get("Retiradas", "") and "período da COVID-19 (com o termo s(COVID))" in F1.get("Retiradas", ""), F1.get("Retiradas"))
        checar("Figura 1: sem comparação entre grupos quando o recorte é o geral", "Comparação entre grupos" not in F1, list(F1))
        sel("s-local", "Hospital"); pronto(); F2 = fch("s-ficha")
        checar("Figura 1: trocar o local do óbito muda o recorte e o período do ajuste da ficha e traz a ressalva sobre a comparação entre grupos",
               "local do óbito: hospital" in F2.get("Recorte", "") and F2.get("Período do ajuste") != F1.get("Período do ajuste") and "teste de interação" in F2.get("Comparação entre grupos", "") and "não é a residência" in F2.get("Ressalvas", ""), (F1.get("Recorte"), F2))
        sel("s-causa", "externas"); pronto(); F3 = fch("s-ficha")
        checar("Figura 1: trocar a causa muda a ficha", "V01 a Y98" in F3.get("Causa do óbito", "") and F3.get("Período do ajuste") != F2.get("Período do ajuste"), F3.get("Causa do óbito"))
        sel("s-causa", "naturais"); sel("s-local", "Todos os locais")
        pg.check("#s-r-covid"); pronto(); F4 = fch("s-ficha")
        checar("Figura 1: retirar a COVID-19 muda as retiradas e o período do ajuste da ficha", "período da COVID-19 (o modelo não tem o termo s(COVID))" in F4.get("Retiradas", "") and F4.get("Período do ajuste") != F1.get("Período do ajuste"), (F4.get("Retiradas"), F4.get("Período do ajuste"), F1.get("Período do ajuste")))
        pg.uncheck("#s-r-covid"); pronto()
        checar("Figura 1: voltar ao ajuste principal reproduz a ficha inicial", fch("s-ficha") == F1)
        sel("s-ini", "2018"); pronto(); F5 = fch("s-ficha")
        checar("Figura 1: o período exibido muda a ficha e o período do ajuste continua o da série completa", F5.get("Período exibido") != F1.get("Período exibido") and F5.get("Período do ajuste") == F1.get("Período do ajuste") and "altera só o que é mostrado" in F5.get("Período exibido", ""), (F5.get("Período exibido"), F5.get("Período do ajuste")))
        sel("s-ini", pg.eval_on_selector("#s-ini", "e=>e.options[0].value")); pronto()
        # textos prontos: cartões do RR do modelo, legenda dos níveis de calor
        kt_ = pg.inner_text("#s-kpis")
        checar("cartões: o RR do modelo traz a frase pronta (exposição mantida por 11 dias, comparada com ausência da exposição, período do ajuste)",
               re.search(r"RR acumulado em 0 a 10 dias: exposição de [\d,]+ h diárias com IC ≥ 36 °C mantida por 11 dias, em comparação com ausência dessa exposição no mesmo intervalo\. Estimativa do modelo ajustado para o período \d\d/\d\d/\d{4} a \d\d/\d\d/\d{4}\.", kt_), kt_[:700])
        checar("cartões: a razão observado/esperado é descritiva, separada do RR, e traz a sigla O/E", "Razão observado/esperado sem calor (O/E)" in kt_ and "Comparação descritiva" in kt_ and "descritivo, não é rr" in kt_.lower(), kt_[:900])
        nt_ = nota()
        checar("legenda dos níveis de calor: NC estimado retrospectivamente, sem previsão, pode diferir do COR, 'acima de' x '≥', Alerta Rio/INMET x REDMET e aviso de que não é alerta operacional",
               all(c in nt_ for c in ["estimados retrospectivamente", "não incorpora previsão", "Centro de Operações e Resiliência do Rio (COR)", "“acima de”", "Alerta Rio, do INMET e da REDMET", "não são alertas operacionais", "Quadro 1"]), nt_[:900])
        # vocabulário: nenhuma aba traz os termos antigos
        PROIB = [r"[Íí]ndice de calor", r"\bNC\d", r"dias? expostos?", r"dias? de calor", r"observado ÷", r"risco diário", r"excesso de óbitos", r"faixa de confiança", r"nível de alerta", r"sensação térmica", r"painel em Python", r"ainda utilizam o modelo anterior", r"IC de 95%"]
        def varrer(nome, texto):
            achados = {q: re.findall(".{0,40}" + q + ".{0,40}", texto) for q in PROIB}
            achados = {q: v[:3] for q, v in achados.items() if v}
            checar(f"vocabulário: {nome} sem os termos antigos (índice de calor em minúsculas, NC sem espaço, dia exposto, dias de calor, ÷, risco diário, excesso de óbitos, faixa de confiança, nível de alerta, sensação térmica)", not achados, achados)
        todos_ = lambda i: pg.evaluate("i=>{const s=document.getElementById(i).cloneNode(true);s.querySelectorAll('script,style').forEach(e=>e.remove());return s.textContent}", i)
        txt_dash_ = " ".join(pg.inner_text(i) for i in ("#sub", "#s-ficha", "#s-note", "#s-per-nota", "#i-serie", "#s-kpis"))
        checar("vocabulário: cabeçalho, ficha, notas, interpretação e cartões da Figura 1 sem travessão", not re.search("[—–]", txt_dash_), re.findall(".{0,30}[—–].{0,30}", txt_dash_)[:3])
        varrer("Figura 1", todos_("tab-serie") + " " + pg.inner_text("#sub"))
        varrer("aba Exposição-resposta", todos_("tab-exp"))
        varrer("aba Causas específicas", todos_("tab-cid"))
        varrer("aba Diagnósticos", todos_("tab-dia"))

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
        checar("métodos: estudo ecológico de série temporal com componente analítico, glossário de termos, correspondência com o protocolo municipal e ficha de cada resultado",
               all(c in sobre for c in ["Estudo ecológico de série temporal", "componente analítico", "Termos usados no painel", "Correspondência com o protocolo municipal", "Ficha de cada resultado", "REDMET", "Quadro 1 da página 6", "Razão observado/esperado sem calor (O/E)", "NC estimado retrospectivamente"]), [c for c in ["Estudo ecológico de série temporal", "componente analítico", "Termos usados no painel", "Correspondência com o protocolo municipal", "Ficha de cada resultado", "REDMET", "Quadro 1 da página 6", "Razão observado/esperado sem calor (O/E)", "NC estimado retrospectivamente"] if c not in sobre])
        checar("métodos: sem o texto desatualizado sobre as demais abas e sem travessão", "ainda utilizam o modelo anterior" not in sobre and "painel em Python" not in sobre and not re.search("[—–]", sobre), re.findall(".{0,30}[—–].{0,30}", sobre)[:3])
        checar("métodos: limitações (agregado municipal, rede de estações, confundimento residual, natureza ecológica, janela de 0 a 10 dias como decisão de modelagem)",
               all(c in sobre for c in ["exposição é uma série municipal agregada", "rede de estações", "confundimento residual", "ecológico", "decisão de modelagem"]), [c for c in ["exposição é uma série municipal agregada", "rede de estações", "confundimento residual", "ecológico", "decisão de modelagem"] if c not in sobre])
        varrer("Métodos e fontes", todos_("tab-sobre"))
        checar("métodos explicam a causa do óbito e as retiradas do ajuste", "Causa do óbito" in sobre and "Retirar períodos do ajuste" in sobre and "Curvas de exposição-resposta e de defasagem" in sobre and "sem taxas por população" in sobre, sobre[:300])
        checar("métodos mostram a fonte e a data da extração dos dados", "Fonte e data da extração" in sobre and "UTC" in sobre, sobre[-400:])
        tab_rec = pg.evaluate("""()=>{const t=[...document.querySelectorAll('#tab-sobre table')].find(t=>t.innerText.includes('Total de óbitos elegíveis'));
          return t?[...t.querySelectorAll('tbody tr')].map(tr=>[...tr.children].map(td=>td.innerText)):null}""")
        num_pt = lambda x: int(x.replace(".", ""))
        checar("métodos: a tabela de reconciliação das causas soma o total de óbitos elegíveis", tab_rec is not None and len(tab_rec) == 8 and sum(num_pt(l[1]) for l in tab_rec[:-1]) == num_pt(tab_rec[-1][1]), tab_rec)
        checar("métodos: causas externas definidas por V01 a Y98 e COVID-19 por B34.2 e U07", "V01 a Y98" in sobre and "B34.2" in sobre and "U07" in sobre and "B34 e códigos U" not in sobre)
        checar("métodos: regras de mês não consolidado e amostra principal descritas", "três regras" in sobre and "A amostra principal do ajuste retira" in sobre and "Dia sem dado de clima" in sobre)
        checar("métodos sem marcação crua", "##" not in sobre and "**" not in sobre and "```" not in sobre)
        if capturas: pg.screenshot(path=os.path.join(capturas, "app_03_metodos.png"), full_page=True)
        pg.click("nav button[data-tab=serie]"); pronto()
        sel("s-pop", "res"); pronto()
        checar("volta para 'res' e reproduz o primeiro resultado", kpis() == k_ini, kpis())

        # 10. segunda sessão (outra pessoa): os recortes já calculados vêm do disco, sem refazer o modelo
        pg2 = ctx.new_page(); pg2.goto(url)
        k2 = lambda: pg2.eval_on_selector_all("#s-kpis .kpi", "els=>els.map(e=>[e.querySelector('.v').innerText, e.querySelector('.l').innerText].join(' | '))")
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

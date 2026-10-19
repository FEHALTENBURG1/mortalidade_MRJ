"""Teste do app Shiny no navegador (Playwright).

Uso, a partir da pasta do projeto:
  PAINEL_CACHE=/caminho/do/cache python3 testes/teste_app.py [--url http://127.0.0.1:PORTA] [--capturas pasta]
Sem --url, sobe o app com Rscript numa porta livre (precisa de R com shiny, future, promises, commonmark, mgcv, dlnm) e derruba no fim.
O cache precisa existir (shiny/atualizar_cache.R ou testes/montar_cache_local.R) com as populações res e todos.

Confere: a página abre sem erro, a figura é pedida ao servidor e desenhada, trocar local, faixa, raça/cor e medida de calor gera novos pedidos com
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

        # 6. escala diária e CSV
        sel("s-esc", "dia"); pronto()
        checar("escala diária desenha", pixels() > 2000)
        sel("s-esc", "sem"); sel("s-ini", pg.eval_on_selector("#s-ini", "e=>e.options[0].value")); pronto()       # a escala diária encurta o período: volta ao início da série
        with pg.expect_download(timeout=15000) as d:
            pg.click("#s-csv")
        caminho = d.value.path(); txt = open(caminho, encoding="utf-8-sig").read()
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

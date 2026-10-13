#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data lake do SIM (Mortalidade Geral) - Município do Rio de Janeiro (IBGE 330455)

Camadas
-------
bronze : CSV do OpenDATASUS de cada ano, Brasil inteiro, tudo como texto, em Parquet.
silver : recortes do MRJ, já tratados (datas, idade, labels, capítulo CID-10).
         - ocorrencia_mrj : óbitos ocorridos no município (CODMUNOCOR)
         - residencia_mrj : óbitos de residentes no município (CODMUNRES)
         - combinado_mrj  : união dos dois (residentes OU óbitos no território),
                            com a coluna categoria_territorial

Uso
---
    python sim_datalake.py direto --apagar-zip    # RECOMENDADO: só o MRJ, sem gravar o Brasil;
                                                  # gera ocorrência, residência e combinado
    # Fluxo com bronze (Brasil inteiro em Parquet), se um dia for preciso:
    python sim_datalake.py bronze                 # baixa e grava o Brasil inteiro
    python sim_datalake.py ocorrencia             # 1º recorte
    python sim_datalake.py residencia             # 2º recorte
    python sim_datalake.py combinado              # 3º recorte (união)
    python sim_datalake.py tudo                   # todas as etapas, na ordem acima
    python sim_datalake.py tudo --anos 2016 2017  # só alguns anos
    python sim_datalake.py bronze --forcar-download

Dependências: pandas, pyarrow, requests, numpy
"""
from __future__ import annotations

import argparse
import codecs
import datetime as dt
import logging
import re
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

log = logging.getLogger("sim")

# --------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------
COD_MRJ = "330455"  # Rio de Janeiro (IBGE, 6 dígitos, sem dígito verificador)
ANO_INI_PADRAO = 2006
ANO_FIM_PADRAO = 2026
URL_TPL = (
    "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SIM/csv/"
    "Mortalidade_Geral_{ano}_csv.zip"
)

# Campos de data no padrão ddmmaaaa (dicionário SIM, versão 06/2025)
COLS_DATA = [
    "DTOBITO", "DTNASC", "DTATESTADO", "DTINVESTIG", "DTCADASTRO", "DTRECEBIM",
    "DTRECORIGA", "DTCADINV", "DTCONINV", "DTCADINF", "DTCONCASO",
]

# --------------------------------------------------------------------------
# Labels (domínios do dicionário SIM, versão 06/2025)
# --------------------------------------------------------------------------
SIM_NAO_IGN = {"1": "Sim", "2": "Não", "9": "Ignorado"}
SIM_NAO_01 = {"1": "Sim", "0": "Não"}
SIM_NAO_12 = {"1": "Sim", "2": "Não"}
ANTES_DURANTE_DEPOIS = {"1": "Antes", "2": "Durante", "3": "Depois", "9": "Ignorado"}
ESC_NIVEL = {
    "0": "Sem escolaridade",
    "1": "Fundamental I (1ª a 4ª série)",
    "2": "Fundamental II (5ª a 8ª série)",
    "3": "Médio (antigo 2º grau)",
    "4": "Superior incompleto",
    "5": "Superior completo",
    "9": "Ignorado",
}
ESC_ANOS = {
    "1": "Nenhuma", "2": "1 a 3 anos", "3": "4 a 7 anos",
    "4": "8 a 11 anos", "5": "12 anos e mais", "9": "Ignorado",
}
ESC_AGR = {
    "00": "Sem escolaridade", "01": "Fundamental I incompleto",
    "02": "Fundamental I completo", "03": "Fundamental II incompleto",
    "04": "Fundamental II completo", "05": "Médio incompleto",
    "06": "Médio completo", "07": "Superior incompleto",
    "08": "Superior completo", "09": "Ignorado",
    "10": "Fundamental I incompleto ou inespecífico",
    "11": "Fundamental II incompleto ou inespecífico",
    "12": "Médio incompleto ou inespecífico",
}

LABELS: dict[str, dict[str, str]] = {
    "TIPOBITO": {"1": "Fetal", "2": "Não fetal"},
    "RACACOR": {"1": "Branca", "2": "Preta", "3": "Amarela", "4": "Parda", "5": "Indígena"},
    "ESTCIV": {
        "1": "Solteiro", "2": "Casado", "3": "Viúvo",
        "4": "Separado judicialmente/divorciado", "5": "União estável", "9": "Ignorado",
    },
    "ESC2010": ESC_NIVEL,
    "ESCMAE2010": ESC_NIVEL,
    "ESC": ESC_ANOS,
    "ESCMAE": ESC_ANOS,
    "ESCMAEAGR1": ESC_AGR,
    "ESCFALAGR1": ESC_AGR,
    "LOCOCOR": {
        "1": "Hospital", "2": "Outros estabelecimentos de saúde", "3": "Domicílio",
        "4": "Via pública", "5": "Outros", "6": "Aldeia indígena", "9": "Ignorado",
    },
    "GRAVIDEZ": {"1": "Única", "2": "Dupla", "3": "Tripla e mais", "9": "Ignorada"},
    "PARTO": {"1": "Vaginal", "2": "Cesáreo", "9": "Ignorado"},
    "OBITOPARTO": ANTES_DURANTE_DEPOIS,
    "MORTEPARTO": {"1": "Antes", "2": "Durante", "3": "Após", "9": "Ignorado"},
    "TPMORTEOCO": {
        "1": "Na gravidez", "2": "No parto", "3": "No abortamento",
        "4": "Até 42 dias após o término do parto",
        "5": "De 43 dias a 1 ano após o término da gestação",
        "8": "Não ocorreu nestes períodos", "9": "Ignorado",
    },
    "OBITOGRAV": SIM_NAO_IGN,
    "OBITOPUERP": {
        "1": "Sim, até 42 dias após o parto", "2": "Sim, de 43 dias a 1 ano",
        "3": "Não", "9": "Ignorado",
    },
    "ASSISTMED": SIM_NAO_IGN,
    "NECROPSIA": SIM_NAO_IGN,
    "EXAME": SIM_NAO_IGN,
    "CIRURGIA": SIM_NAO_IGN,
    "ACIDTRAB": SIM_NAO_IGN,
    "ATESTANTE": {"1": "Assistente", "2": "Substituto", "3": "IML", "4": "SVO", "5": "Outro"},
    "CIRCOBITO": {"1": "Acidente", "2": "Suicídio", "3": "Homicídio", "4": "Outros", "9": "Ignorado"},
    "FONTE": {"1": "Ocorrência policial", "2": "Hospital", "3": "Família", "4": "Outra", "9": "Ignorado"},
    "GESTACAO": {
        "1": "Menos de 22 semanas", "2": "22 a 27 semanas", "3": "28 a 31 semanas",
        "4": "32 a 36 semanas", "5": "37 a 41 semanas", "6": "42 semanas e mais",
        "9": "Ignorado",  # aparece nos dados (óbitos não fetais), mas não está no dicionário
    },
    "FONTEINV": {
        "1": "Comitê de Morte Materna e/ou Infantil", "2": "Visita domiciliar / entrevista família",
        "3": "Estabelecimento de saúde / prontuário", "4": "Relacionado com outros bancos de dados",
        "5": "SVO", "6": "IML", "7": "Outra fonte", "8": "Múltiplas fontes", "9": "Ignorado",
    },
    "STDOEPIDEM": SIM_NAO_01,
    "STDONOVA": SIM_NAO_01,
    "TPRESGINFO": {
        "01": "Não acrescentou nem corrigiu informação",
        "02": "Sim, permitiu o resgate de novas informações",
        "03": "Sim, permitiu a correção de alguma das causas informadas originalmente",
    },
    "TPNIVELINV": {"E": "Estadual", "R": "Regional", "M": "Municipal"},
    "ALTCAUSA": SIM_NAO_12,
    # Na API aparece "N" (e o dicionário diz 1/2); aceita as duas codificações
    "TPPOS": {"1": "Sim", "2": "Não", "S": "Sim", "N": "Não"},
}
# Colunas cujos códigos têm 2 dígitos no dicionário
COLS_2DIG = {"ESCMAEAGR1", "ESCFALAGR1", "TPRESGINFO"}

# SEXO aceita M/F/I e 1/2/0/9 conforme o ano
SEXO_MAP = {
    "M": "Masculino", "1": "Masculino",
    "F": "Feminino", "2": "Feminino",
    "I": "Ignorado", "0": "Ignorado", "9": "Ignorado",
}

# Unidade da idade (1º dígito de IDADE). O texto do dicionário PDF lista uma
# numeração diferente (1=minuto, 2=hora, sem dias); aqui vale o layout clássico
# do SIM: 0=minutos, 1=horas, 2=dias, 3=meses, 4=anos, 5=100 anos ou mais.
# Confira a distribuição de idade_unidade nos dados antes de confiar.
IDADE_UNID = {
    "0": "minutos", "1": "horas", "2": "dias",
    "3": "meses", "4": "anos", "5": "100 anos ou mais",
}

# Capítulos da CID-10 (tabela padrão da classificação; não vem no dicionário)
CAPITULOS_CID10 = [
    ("A00", "B99", "I", "Algumas doenças infecciosas e parasitárias"),
    ("C00", "D48", "II", "Neoplasias (tumores)"),
    ("D50", "D89", "III", "Doenças do sangue e dos órgãos hematopoéticos e alguns transtornos imunitários"),
    ("E00", "E90", "IV", "Doenças endócrinas, nutricionais e metabólicas"),
    ("F00", "F99", "V", "Transtornos mentais e comportamentais"),
    ("G00", "G99", "VI", "Doenças do sistema nervoso"),
    ("H00", "H59", "VII", "Doenças do olho e anexos"),
    ("H60", "H95", "VIII", "Doenças do ouvido e da apófise mastóide"),
    ("I00", "I99", "IX", "Doenças do aparelho circulatório"),
    ("J00", "J99", "X", "Doenças do aparelho respiratório"),
    ("K00", "K93", "XI", "Doenças do aparelho digestivo"),
    ("L00", "L99", "XII", "Doenças da pele e do tecido subcutâneo"),
    ("M00", "M99", "XIII", "Doenças do sistema osteomuscular e do tecido conjuntivo"),
    ("N00", "N99", "XIV", "Doenças do aparelho geniturinário"),
    ("O00", "O99", "XV", "Gravidez, parto e puerpério"),
    ("P00", "P96", "XVI", "Algumas afecções originadas no período perinatal"),
    ("Q00", "Q99", "XVII", "Malformações congênitas, deformidades e anomalias cromossômicas"),
    ("R00", "R99", "XVIII", "Sintomas, sinais e achados anormais de exames clínicos e de laboratório"),
    ("S00", "T98", "XIX", "Lesões, envenenamento e algumas outras consequências de causas externas"),
    ("V01", "Y98", "XX", "Causas externas de morbidade e de mortalidade"),
    ("Z00", "Z99", "XXI", "Fatores que influenciam o estado de saúde e o contato com os serviços de saúde"),
    ("U00", "U99", "XXII", "Códigos para propósitos especiais"),
]

# Alguns arquivos do OpenDATASUS vêm SEM linha de cabeçalho (2022 e 2023 em 2026-10).
# O layout deles foi conferido contra o de anos vizinhos: 2022 = layout de 2021
# (87 colunas) e 2023 = layout de 2025 (86 colunas, "contador" na frente).
_CAB_2021 = (
    "ORIGEM;TIPOBITO;DTOBITO;HORAOBITO;NATURAL;CODMUNNATU;DTNASC;IDADE;SEXO;RACACOR;"
    "ESTCIV;ESC;ESC2010;SERIESCFAL;OCUP;CODMUNRES;LOCOCOR;CODESTAB;ESTABDESCR;CODMUNOCOR;"
    "IDADEMAE;ESCMAE;ESCMAE2010;SERIESCMAE;OCUPMAE;QTDFILVIVO;QTDFILMORT;GRAVIDEZ;"
    "SEMAGESTAC;GESTACAO;PARTO;OBITOPARTO;PESO;TPMORTEOCO;OBITOGRAV;OBITOPUERP;ASSISTMED;"
    "EXAME;CIRURGIA;NECROPSIA;LINHAA;LINHAB;LINHAC;LINHAD;LINHAII;CAUSABAS;CB_PRE;"
    "COMUNSVOIM;DTATESTADO;CIRCOBITO;ACIDTRAB;FONTE;NUMEROLOTE;TPPOS;DTINVESTIG;CAUSABAS_O;"
    "DTCADASTRO;ATESTANTE;STCODIFICA;CODIFICADO;VERSAOSIST;VERSAOSCB;FONTEINV;DTRECEBIM;"
    "ATESTADO;DTRECORIGA;CAUSAMAT;ESCMAEAGR1;ESCFALAGR1;STDOEPIDEM;STDONOVA;DIFDATA;"
    "NUDIASOBCO;NUDIASOBIN;DTCADINV;TPOBITOCOR;DTCONINV;FONTES;TPRESGINFO;TPNIVELINV;"
    "NUDIASINF;DTCADINF;MORTEPARTO;DTCONCASO;FONTESINF;ALTCAUSA;CONTADOR"
).split(";")
_CAB_2025 = (
    "CONTADOR;ORIGEM;TIPOBITO;DTOBITO;HORAOBITO;NATURAL;CODMUNNATU;DTNASC;IDADE;SEXO;"
    "RACACOR;ESTCIV;ESC;ESC2010;SERIESCFAL;OCUP;CODMUNRES;LOCOCOR;CODESTAB;CODMUNOCOR;"
    "IDADEMAE;ESCMAE;ESCMAE2010;SERIESCMAE;OCUPMAE;QTDFILVIVO;QTDFILMORT;GRAVIDEZ;"
    "SEMAGESTAC;GESTACAO;PARTO;OBITOPARTO;PESO;TPMORTEOCO;OBITOGRAV;OBITOPUERP;ASSISTMED;"
    "EXAME;CIRURGIA;NECROPSIA;LINHAA;LINHAB;LINHAC;LINHAD;LINHAII;CAUSABAS;CB_PRE;"
    "COMUNSVOIM;DTATESTADO;CIRCOBITO;ACIDTRAB;FONTE;NUMEROLOTE;DTINVESTIG;DTCADASTRO;"
    "ATESTANTE;STCODIFICA;CODIFICADO;VERSAOSIST;VERSAOSCB;FONTEINV;DTRECEBIM;ATESTADO;"
    "DTRECORIGA;OPOR_DO;CAUSAMAT;ESCMAEAGR1;ESCFALAGR1;STDOEPIDEM;STDONOVA;DIFDATA;"
    "NUDIASOBCO;DTCADINV;TPOBITOCOR;DTCONINV;FONTES;TPRESGINFO;TPNIVELINV;DTCADINF;"
    "MORTEPARTO;DTCONCASO;ALTCAUSA;CAUSABAS_O;TPPOS;TP_ALTERA;CB_ALT"
).split(";")
assert len(_CAB_2021) == 87 and len(_CAB_2025) == 86
CABECALHOS_SEM_HEADER = {2022: _CAB_2021, 2023: _CAB_2025}

CAT_RES_OCOR = "Residente e óbito no MRJ"
CAT_RES_FORA = "Residente no MRJ, óbito fora do MRJ"
CAT_NRES_OCOR = "Não residente, óbito no MRJ"


# --------------------------------------------------------------------------
# Download e leitura
# --------------------------------------------------------------------------
def baixar_zip(ano: int, raiz: Path, forcar: bool = False) -> Path:
    """Baixa o zip do ano. O ano corrente é sempre baixado de novo (dado preliminar)."""
    destino = raiz / "raw_zip" / f"Mortalidade_Geral_{ano}_csv.zip"
    destino.parent.mkdir(parents=True, exist_ok=True)
    ano_corrente = ano >= dt.date.today().year
    if destino.exists() and destino.stat().st_size > 0 and not (forcar or ano_corrente):
        log.info("%s: zip já existe, reaproveitando", ano)
        return destino

    url = URL_TPL.format(ano=ano)
    tmp = destino.with_suffix(".zip.part")
    ultimo_erro: Exception | None = None
    for tentativa in range(1, 4):
        try:
            log.info("%s: baixando (tentativa %d) %s", ano, tentativa, url)
            with requests.get(url, stream=True, timeout=(15, 180)) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for bloco in r.iter_content(chunk_size=1 << 20):
                        f.write(bloco)
            tmp.replace(destino)
            return destino
        except requests.HTTPError as e:
            ultimo_erro = e
            if e.response is not None and e.response.status_code == 404:
                raise  # arquivo não existe; não adianta repetir
            time.sleep(5 * tentativa)
        except requests.RequestException as e:
            ultimo_erro = e
            time.sleep(5 * tentativa)
    raise RuntimeError(f"Falha ao baixar {url}: {ultimo_erro}")


def _detectar_encoding(amostra: bytes) -> str:
    if amostra.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    dec = codecs.getincrementaldecoder("utf-8")()
    try:
        dec.decode(amostra, final=False)  # tolera caractere cortado no fim da amostra
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def _detectar_encoding_arquivo(z: zipfile.ZipFile, nome: str) -> str:
    """Varre o CSV inteiro (em blocos) para decidir o encoding.

    Olhar só o começo não basta: há anos (2013-2015) em que os primeiros bytes são
    ASCII/UTF-8 válidos e o primeiro byte latin-1 aparece lá no meio do arquivo.
    Se qualquer trecho não for UTF-8 válido, usa latin-1 (que nunca falha).
    """
    with z.open(nome) as f:
        ini = f.read(4)
    if ini.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    dec = codecs.getincrementaldecoder("utf-8")()
    with z.open(nome) as f:
        while True:
            bloco = f.read(1 << 22)
            if not bloco:
                break
            try:
                dec.decode(bloco, final=False)
            except UnicodeDecodeError:
                return "latin-1"
    return "utf-8"


def _detectar_sep(amostra: bytes, encoding: str) -> str:
    primeira = amostra.decode(encoding, errors="replace").splitlines()[0]
    return max([";", ",", "\t", "|"], key=primeira.count)


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().strip('"').upper() for c in df.columns]
    return df


def _ano_do_arquivo(caminho_zip: Path) -> int | None:
    m = re.search(r"(\d{4})", caminho_zip.name)
    return int(m.group(1)) if m else None


def _abrir_csv_zip(z: zipfile.ZipFile, caminho_zip: Path) -> tuple[str, str, str, dict]:
    """Descobre nome do CSV, encoding, separador e se há cabeçalho.

    O 4º item são argumentos extras do pd.read_csv: vazio quando o arquivo tem
    cabeçalho; header=None + names=... quando não tem (2022 e 2023).
    """
    csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
    if not csvs:
        raise ValueError(f"Nenhum CSV dentro de {caminho_zip.name}")
    nome = csvs[0]
    with z.open(nome) as f:
        amostra = f.read(1 << 16)
    enc = _detectar_encoding_arquivo(z, nome)
    sep = _detectar_sep(amostra, enc)
    primeira = amostra.decode(enc, errors="replace").splitlines()[0]
    campos = [c.strip().strip('"').upper() for c in primeira.split(sep)]
    extra: dict = {}
    if not {"DTOBITO", "CODMUNRES", "CAUSABAS"} & set(campos):
        ano = _ano_do_arquivo(caminho_zip)
        cab = CABECALHOS_SEM_HEADER.get(ano)
        if cab is None or len(cab) != len(campos):
            raise ValueError(
                f"{caminho_zip.name}: CSV sem cabeçalho ({len(campos)} colunas) e sem "
                f"layout conhecido para o ano {ano}. Primeira linha: {primeira[:120]!r}"
            )
        extra = {"header": None, "names": cab}
        log.warning("  %s: sem cabeçalho; usando o layout registrado para %s", nome, ano)
    log.info("  %s | encoding=%s | sep=%r", nome, enc, sep)
    return nome, enc, sep, extra


def _validar_layout(df: pd.DataFrame, origem: str) -> None:
    """Falha cedo se as colunas não batem com o conteúdo (evita filtro silenciosamente vazio)."""
    amostra = df.head(5000)
    regras = {"DTOBITO": r"^(?:\d{7,8}|\d{2}-\d{2}-\d{4})$", "CODMUNRES": r"^\d{6,7}$"}
    for col, padrao in regras.items():
        if col not in amostra.columns:
            raise ValueError(f"{origem}: coluna {col} ausente")
        s = amostra[col].dropna().astype(str).str.strip()
        taxa = s.str.match(padrao).mean() if len(s) else 0.0
        if taxa < 0.95:
            raise ValueError(
                f"{origem}: {col} fora do padrão esperado em {1 - taxa:.0%} da amostra; "
                "o layout das colunas provavelmente mudou"
            )


def ler_csv_zip(caminho_zip: Path) -> pd.DataFrame:
    """Lê o CSV de dentro do zip, tudo como texto, vazio vira nulo (Brasil inteiro)."""
    with zipfile.ZipFile(caminho_zip) as z:
        nome, enc, sep, extra = _abrir_csv_zip(z, caminho_zip)
        with z.open(nome) as f:
            df = pd.read_csv(
                f, sep=sep, encoding=enc, dtype=str,
                na_values=[""], keep_default_na=False, low_memory=False, **extra,
            )
    df = _norm_cols(df)
    _validar_layout(df, caminho_zip.name)
    return df


def ler_csv_zip_mrj(caminho_zip: Path, linhas_por_bloco: int = 200_000) -> tuple[pd.DataFrame, int]:
    """Lê o CSV em blocos e guarda só os óbitos do MRJ (residência OU ocorrência).

    Evita carregar o Brasil inteiro na memória. Devolve (df_mrj_marcado, n_linhas_brasil).
    """
    partes: list[pd.DataFrame] = []
    n_total = 0
    with zipfile.ZipFile(caminho_zip) as z:
        nome, enc, sep, extra = _abrir_csv_zip(z, caminho_zip)
        with z.open(nome) as f:
            leitor = pd.read_csv(
                f, sep=sep, encoding=enc, dtype=str, na_values=[""],
                keep_default_na=False, chunksize=linhas_por_bloco, **extra,
            )
            for bloco in leitor:
                bloco = _norm_cols(bloco)
                if n_total == 0:
                    _validar_layout(bloco, caminho_zip.name)
                n_total += len(bloco)
                bloco = marcar_territorio(bloco)
                partes.append(bloco[bloco["residente_mrj"] | bloco["ocorrencia_mrj"]])
    if not partes:
        raise ValueError(f"CSV vazio em {caminho_zip.name}")
    df = pd.concat(partes, ignore_index=True)
    return df, n_total


def gravar_particao(df: pd.DataFrame, base: Path, ano: int) -> Path:
    """Grava base/ano_arquivo=AAAA/part-0.parquet (a partição fica só no caminho)."""
    pasta = base / f"ano_arquivo={ano}"
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / "part-0.parquet"
    df.drop(columns=["ano_arquivo"], errors="ignore").to_parquet(arq, index=False)
    return arq


# --------------------------------------------------------------------------
# Tratamento
# --------------------------------------------------------------------------
def _cod6(df: pd.DataFrame, col: str) -> pd.Series:
    """Primeiros 6 caracteres do código de município (aceita 6 ou 7 dígitos)."""
    if col not in df.columns:
        return pd.Series(pd.NA, index=df.index, dtype="string")
    return df[col].astype("string").str.strip().str[:6]


def marcar_territorio(df: pd.DataFrame) -> pd.DataFrame:
    """Cria os códigos de 6 dígitos e as flags de residência/ocorrência no MRJ."""
    df = df.copy()
    df["cod_mun_res6"] = _cod6(df, "CODMUNRES")
    df["cod_mun_ocor6"] = _cod6(df, "CODMUNOCOR")
    df["residente_mrj"] = (df["cod_mun_res6"] == COD_MRJ).fillna(False).to_numpy(dtype=bool)
    df["ocorrencia_mrj"] = (df["cod_mun_ocor6"] == COD_MRJ).fillna(False).to_numpy(dtype=bool)
    df["categoria_territorial"] = np.select(
        [
            df["residente_mrj"] & df["ocorrencia_mrj"],
            df["residente_mrj"] & ~df["ocorrencia_mrj"],
            ~df["residente_mrj"] & df["ocorrencia_mrj"],
        ],
        [CAT_RES_OCOR, CAT_RES_FORA, CAT_NRES_OCOR],
        default="Fora do MRJ",
    )
    return df


def decodificar_idade(idade: pd.Series) -> pd.DataFrame:
    """IDADE (3 caracteres: unidade + quantidade) -> idade_anos (float)."""
    s = idade.astype("string").str.strip().fillna("")
    vazio = (s == "").to_numpy()
    s = s.str.zfill(3)
    unid = s.str[0].to_numpy(dtype=object)
    qtd = pd.to_numeric(s.str[1:], errors="coerce").to_numpy(dtype="float64")
    anos = np.select(
        [unid == "0", unid == "1", unid == "2", unid == "3", unid == "4", unid == "5"],
        [
            qtd / (365.25 * 24 * 60), qtd / (365.25 * 24), qtd / 365.25,
            qtd / 12, qtd, 100 + qtd,
        ],
        default=np.nan,
    )
    anos[vazio] = np.nan
    unid_desc = pd.Series(unid, index=idade.index).map(IDADE_UNID)
    unid_desc = unid_desc.mask(vazio, None)
    return pd.DataFrame(
        {
            "idade_unidade": pd.Series(unid, index=idade.index).mask(vazio, None),
            "idade_unidade_desc": unid_desc,
            "idade_valor": np.where(vazio, np.nan, qtd),
            "idade_anos": anos,
        },
        index=idade.index,
    )


def converter_datas(df: pd.DataFrame) -> pd.DataFrame:
    """Aceita ddmmaaaa (com ou sem zero à esquerda) e dd-mm-aaaa (2022 e 2023).

    31-12-1969 é o "zero" do Unix gravado no lugar de data vazia nesses arquivos;
    vira nulo.
    """
    zero_unix = pd.Timestamp("1969-12-31")
    for col in COLS_DATA:
        if col in df.columns:
            s = df[col].astype("string").str.strip()
            com_traco = s.str.contains("-", regex=False).fillna(False).to_numpy(dtype=bool)
            sem = pd.to_datetime(
                s.mask(com_traco).str.zfill(8), format="%d%m%Y", errors="coerce"
            )
            com = pd.to_datetime(s.where(com_traco), format="%d-%m-%Y", errors="coerce")
            datas = sem.fillna(com)
            df[col] = datas.mask(datas == zero_unix)
    return df


def aplicar_labels(df: pd.DataFrame) -> pd.DataFrame:
    for var, mapa in LABELS.items():
        if var not in df.columns:
            continue
        s = df[var].astype("string").str.strip()
        if var in COLS_2DIG:
            s = s.str.zfill(2)
        desc = s.map(mapa)
        fora = s.notna().to_numpy() & desc.isna().to_numpy()
        df[var + "_DESC"] = desc.mask(fora, "Fora do domínio")
    if "SEXO" in df.columns:
        s = df["SEXO"].astype("string").str.strip().str.upper()
        desc = s.map(SEXO_MAP)
        fora = s.notna().to_numpy() & desc.isna().to_numpy()
        df["sexo_desc"] = desc.mask(fora, "Fora do domínio")
    return df


def cid_capitulo(df: pd.DataFrame, col: str = "CAUSABAS") -> pd.DataFrame:
    if col not in df.columns:
        return df
    c3 = df[col].astype("string").str.strip().str.upper().str[:3]
    cap = pd.Series(pd.NA, index=df.index, dtype="string")
    nome = pd.Series(pd.NA, index=df.index, dtype="string")
    for lo, hi, rom, desc in CAPITULOS_CID10:
        m = ((c3 >= lo) & (c3 <= hi)).to_numpy(dtype=bool, na_value=False)
        cap = cap.mask(m, rom)
        nome = nome.mask(m, desc)
    df["cid_capitulo"] = cap
    df["cid_capitulo_desc"] = nome
    return df


def tratar(df: pd.DataFrame) -> pd.DataFrame:
    """Tratamento da camada silver (aplicado só ao recorte do MRJ)."""
    df = df.copy()
    if "IDADE" in df.columns:
        df = pd.concat([df, decodificar_idade(df["IDADE"])], axis=1)
    df = converter_datas(df)
    if "DTOBITO" in df.columns:
        df["ano_obito"] = df["DTOBITO"].dt.year.astype("Int64")
        df["mes_obito"] = df["DTOBITO"].dt.month.astype("Int64")
    df = aplicar_labels(df)
    df = cid_capitulo(df)
    return df


# --------------------------------------------------------------------------
# Etapas
# --------------------------------------------------------------------------
def etapa_bronze(anos, raiz: Path, forcar: bool, apagar_zip: bool) -> list[int]:
    base = raiz / "bronze" / "sim"
    falhas: list[int] = []
    for ano in anos:
        try:
            zip_path = baixar_zip(ano, raiz, forcar)
            df = ler_csv_zip(zip_path)
        except Exception as e:  # noqa: BLE001
            log.error("%s: falhou (%s)", ano, e)
            falhas.append(ano)
            continue
        df["arquivo_origem"] = zip_path.name
        df["ingestao_em"] = dt.datetime.now().isoformat(timespec="seconds")
        gravar_particao(df, base, ano)
        log.info("%s: bronze gravada (%d linhas, %d colunas)", ano, len(df), df.shape[1])
        if apagar_zip:
            zip_path.unlink(missing_ok=True)
    return falhas


FILTROS = {
    "ocorrencia": lambda d: d["ocorrencia_mrj"],
    "residencia": lambda d: d["residente_mrj"],
    "combinado": lambda d: d["ocorrencia_mrj"] | d["residente_mrj"],
}


def _gravar_recorte(nome: str, ano: int, df_marcado: pd.DataFrame, n_brasil: int, raiz: Path) -> dict:
    """Aplica o filtro `nome`, trata, grava a partição do ano e devolve a linha de resumo."""
    saida = raiz / "silver" / "sim" / f"{nome}_mrj"
    recorte = df_marcado[FILTROS[nome](df_marcado)]
    n_rec = len(recorte)
    recorte = tratar(recorte)
    recorte.insert(0, "ano_arquivo", ano)
    gravar_particao(recorte, saida, ano)
    linha = {"ano_arquivo": ano, "n_brasil": n_brasil, "n_recorte": n_rec}
    for cat, n in recorte["categoria_territorial"].value_counts().items():
        linha[cat] = int(n)
    log.info("%s: %s -> %d de %d óbitos", ano, nome, n_rec, n_brasil)
    return linha


def _salvar_resumo(linhas: list[dict], nome: str, raiz: Path) -> pd.DataFrame:
    """Grava qa/resumo_<nome>.csv mantendo os anos já resumidos em execuções anteriores."""
    novo = pd.DataFrame(linhas)
    qa = raiz / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    arq = qa / f"resumo_{nome}.csv"
    if arq.exists() and not novo.empty:
        antigo = pd.read_csv(arq)
        antigo = antigo[~antigo["ano_arquivo"].isin(novo["ano_arquivo"])]
        novo = pd.concat([antigo, novo], ignore_index=True)
    novo = novo.sort_values("ano_arquivo").fillna(0).reset_index(drop=True) if not novo.empty else novo
    novo.to_csv(arq, index=False)
    return novo


def etapa_silver(nome: str, anos, raiz: Path) -> pd.DataFrame:
    """Gera um recorte a partir da bronze (Brasil inteiro) já gravada."""
    bronze = raiz / "bronze" / "sim"
    linhas = []
    for ano in anos:
        arq = bronze / f"ano_arquivo={ano}" / "part-0.parquet"
        if not arq.exists():
            log.warning("%s: bronze não encontrada, pulando (%s)", ano, arq)
            continue
        df = marcar_territorio(pd.read_parquet(arq))
        linhas.append(_gravar_recorte(nome, ano, df, len(df), raiz))
    return _salvar_resumo(linhas, nome, raiz)


def etapa_direto(anos, raiz: Path, forcar: bool, apagar_zip: bool, linhas_por_bloco: int) -> list[int]:
    """Zip -> silver do MRJ, sem gravar a bronze do Brasil.

    Gera os três recortes (ocorrência, residência, combinado) de cada ano.
    """
    resumos: dict[str, list[dict]] = {n: [] for n in FILTROS}
    falhas: list[int] = []
    for ano in anos:
        try:
            zip_path = baixar_zip(ano, raiz, forcar)
            df, n_brasil = ler_csv_zip_mrj(zip_path, linhas_por_bloco)
        except Exception as e:  # noqa: BLE001
            log.error("%s: falhou (%s)", ano, e)
            falhas.append(ano)
            continue
        for nome in FILTROS:  # ocorrência, residência, combinado
            resumos[nome].append(_gravar_recorte(nome, ano, df, n_brasil, raiz))
        if apagar_zip:
            zip_path.unlink(missing_ok=True)
    for nome, linhas in resumos.items():
        _salvar_resumo(linhas, nome, raiz)
        if linhas:
            print(f"\nResumo {nome} (anos desta execução):\n{pd.DataFrame(linhas).fillna(0).to_string(index=False)}\n")
    return falhas


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Data lake SIM - município do Rio de Janeiro")
    p.add_argument(
        "etapa",
        choices=["direto", "bronze", "ocorrencia", "residencia", "combinado", "tudo"],
        help="direto = zip -> silver do MRJ sem gravar o Brasil; "
             "bronze/ocorrencia/residencia/combinado/tudo = fluxo com bronze",
    )
    p.add_argument("--linhas-por-bloco", type=int, default=200_000,
                   help="linhas por bloco de leitura no modo direto (controla a memória)")
    p.add_argument("--anos", type=int, nargs="+", help="lista de anos (ex.: 2016 2017)")
    p.add_argument("--ano-ini", type=int, default=ANO_INI_PADRAO)
    p.add_argument("--ano-fim", type=int, default=ANO_FIM_PADRAO)
    p.add_argument("--raiz", default="datalake", help="pasta raiz do data lake")
    p.add_argument("--forcar-download", action="store_true")
    p.add_argument("--apagar-zip", action="store_true", help="apaga o zip depois da bronze")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raiz = Path(a.raiz)
    anos = a.anos or list(range(a.ano_ini, a.ano_fim + 1))

    etapas = ["bronze", "ocorrencia", "residencia", "combinado"] if a.etapa == "tudo" else [a.etapa]
    for etapa in etapas:
        if etapa == "direto":
            falhas = etapa_direto(anos, raiz, a.forcar_download, a.apagar_zip, a.linhas_por_bloco)
            if falhas:
                log.error("Anos com falha: %s", falhas)
                return 1
        elif etapa == "bronze":
            falhas = etapa_bronze(anos, raiz, a.forcar_download, a.apagar_zip)
            if falhas:
                log.warning("Anos com falha na bronze: %s", falhas)
        else:
            res = etapa_silver(etapa, anos, raiz)
            if not res.empty:
                print(f"\nResumo {etapa}:\n{res.to_string(index=False)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

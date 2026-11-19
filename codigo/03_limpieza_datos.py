# Nombres y apellidos: YULIANA ORIHUELA LAZO
# Código de matrícula: 2024200514G
# Tema: Valor en riesgo (VaR) de un portafolio de acciones peruanas -N° 70
# Fecha de extracción:  2026-11-19 
#
# =============================================================================
# 03_limpieza_datos.py  -  LIMPIEZA, UNIÓN Y VARIABLES DERIVADAS
#
# Qué hace este script (es el ÚNICO lugar donde se tipifica y depura; los crudos no se tocan):
#   1. Lee los crudos de Yahoo (un CSV por ticker) y de la BVL (tabla cruda unificada).
#   2. Normaliza nombres y tipos: ticker sin ".LM", fecha AAAA-MM-DD (sin zona horaria),
#      números como números, dividendos de Yahoo (texto con moneda) a número.
#   3. Une ambas fuentes por (ticker, fecha) con una unión EXTERNA (outer): no se pierde ninguna
#      fecha de ninguna fuente; la columna fuente_presente dice de dónde viene cada fila.
#      Se valida que la llave sea única en cada fuente y en el resultado (sin duplicados).
#   4. Marca los días sin negociación (no se borra ninguna fila) y calcula los retornos.
#   5. Guarda datos_procesados_<matrícula>.csv, su hash SHA-256 y un resumen de calidad por emisor.
#
# Decisiones declaradas (deben ir en el artículo):
#   * Retorno: TIPO_RETORNO ("log" o "simple"). Con Yahoo se usa el cierre AJUSTADO (incluye
#     dividendos); con la BVL se usa el cierre sin ajustar, por lo que el retorno BVL puede
#     mostrar saltos en fechas ex-dividendo. Sirve como contraste de robustez, no como serie principal.
#   * Los retornos se calculan entre observaciones consecutivas CON precio válido de cada fuente.
#   * Cierre BVL <= 0 sin negociación = "sin precio" (NaN). Cierre BVL <= 0 CON negociación: se reconstruye con el
#     "cierre anterior corregido" de la sesión siguiente (columna cierre_bvl_reconstruido = True); no se arrastra ningún precio.
#   * Yahoo: Close/Adj Close <= 0 también pasa a NaN. Los días con volumen 0 se marcan, no se eliminan.
#
# Ubicación esperada: <proyecto>/codigo/03_limpieza_datos.py
# Orden de ejecución: 01_extraccion_api -> 02_scraping_web -> 03_limpieza_datos -> 04_analisis
# Instalación: pip install pandas numpy
# =============================================================================

import datetime as dt
import hashlib
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ============================ PARÁMETROS CONGELADOS ==========================
CODIGO = "2024200514G"
TIPO_RETORNO = "log"          # "log" (logarítmico) o "simple"; declarar la elección en el artículo
OBS_MINIMAS_TEMARIO = 20000
COLUMNAS_MIN_PROCESADO = 6    # consigna: >= 6 columnas, >= 4 sustantivas, >= 1 por fuente

# ============================= RUTAS RELATIVAS ===============================
try:
    RAIZ = Path(__file__).resolve().parent.parent   # script dentro de /codigo
except NameError:                                    # Colab / Jupyter: no existe __file__
    RAIZ = Path.cwd()
DIR_CRUDOS = RAIZ / "datos_crudos"
DIR_PROC = RAIZ / "datos_procesados"
DIR_PROC.mkdir(parents=True, exist_ok=True)
LOG_PATH = RAIZ / "log_ejecucion.txt"
RUTA_BVL = DIR_CRUDOS / f"bvl_cotizaciones_crudo_{CODIGO}.csv"
RUTA_SALIDA = DIR_PROC / f"datos_procesados_{CODIGO}.csv"
RUTA_HASH = DIR_PROC / f"hash_sha256_{CODIGO}.txt"
RUTA_RESUMEN = DIR_PROC / f"resumen_calidad_{CODIGO}.csv"


# ================================ UTILIDADES =================================
def log(msg: str) -> None:
    linea = f"[{dt.datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(linea)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


def sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def a_numero(serie: pd.Series, nombre: str) -> pd.Series:
    """Convierte a número y avisa cuántos valores NO vacíos no se pudieron convertir."""
    original = serie.replace({"": np.nan, "nan": np.nan, "None": np.nan})
    convertida = pd.to_numeric(original, errors="coerce")
    perdidos = int((convertida.isna() & original.notna()).sum())
    if perdidos:
        log(f"AVISO: {nombre}: {perdidos} valores no numéricos pasaron a vacío")
    return convertida


def exigir_columnas(df: pd.DataFrame, columnas: list, origen: str) -> None:
    faltan = [c for c in columnas if c not in df.columns]
    if faltan:
        raise KeyError(f"{origen}: faltan columnas {faltan}. Columnas halladas: {list(df.columns)}")


def retorno(precio: pd.Series, ticker: pd.Series) -> pd.Series:
    """Retorno entre observaciones consecutivas con precio válido, por ticker (ordenado por fecha)."""
    valido = precio.notna()
    sub_precio = precio[valido]
    previo = sub_precio.groupby(ticker[valido]).shift(1)
    if TIPO_RETORNO == "log":
        r = np.log(sub_precio / previo)
    else:
        r = sub_precio / previo - 1
    return r.reindex(precio.index)


# ============================== LECTURA: YAHOO ===============================
def leer_yahoo() -> pd.DataFrame:
    archivos = sorted(DIR_CRUDOS.glob(f"api_yahoo_*_{CODIGO}.csv"))
    if not archivos:
        raise FileNotFoundError(f"No hay crudos de Yahoo en {DIR_CRUDOS} (api_yahoo_*_{CODIGO}.csv). Corre antes 01_extraccion_api.py")
    partes = []
    for ruta in archivos:
        ticker = ruta.name[len("api_yahoo_"):-len(f"_{CODIGO}.csv")].replace(".LM", "")
        df = pd.read_csv(ruta, dtype=str)
        exigir_columnas(df, ["Date", "Close", "Adj Close", "Volume", "Dividends"], ruta.name)
        p = pd.DataFrame({
            "ticker": ticker,
            "fecha": df["Date"].str[:10],   # AAAA-MM-DD: se descarta la hora y la zona horaria (-05:00)
            "cierre_yahoo": a_numero(df["Close"], f"{ticker} Close"),
            "cierre_ajustado_yahoo": a_numero(df["Adj Close"], f"{ticker} Adj Close"),
            "volumen_yahoo": a_numero(df["Volume"], f"{ticker} Volume"),
            # Dividends llega como texto ('0', o número con moneda): se extrae solo el número
            "dividendo_yahoo": a_numero(df["Dividends"].str.extract(r"^\s*([0-9]*\.?[0-9]+)")[0], f"{ticker} Dividends"),
        })
        for c in ("cierre_yahoo", "cierre_ajustado_yahoo"):
            p.loc[p[c] <= 0, c] = np.nan
        partes.append(p)
    y = pd.concat(partes, ignore_index=True)
    dup = int(y.duplicated(["ticker", "fecha"]).sum())
    if dup:
        raise ValueError(f"Yahoo: {dup} filas con (ticker, fecha) duplicada")
    log(f"Yahoo leído: {len(archivos)} archivos | filas={len(y):,} | tickers={sorted(y['ticker'].unique())}")
    return y


# =============================== LECTURA: BVL ================================
def leer_bvl() -> pd.DataFrame:
    if not RUTA_BVL.exists():
        raise FileNotFoundError(f"No existe {RUTA_BVL}. Corre antes 02_scraping_web.py")
    df = pd.read_csv(RUTA_BVL, dtype=str)
    exigir_columnas(df, ["nemonico", "date", "close", "quantityNegotiated", "solAmountNegotiated", "yesterdayClose"], RUTA_BVL.name)
    cierre = a_numero(df["close"], "BVL close")
    cierre_ant = a_numero(df["yesterdayClose"], "BVL yesterdayClose")   # "cierre anterior corregido" de la BVL
    b = pd.DataFrame({
        "ticker": df["nemonico"].str.strip(),
        "fecha": df["date"].str[:10],
        "cierre_bvl": cierre.where(cierre > 0),     # cierre <= 0 = sin precio
        "cantidad_bvl": a_numero(df["quantityNegotiated"], "BVL quantityNegotiated"),
        "monto_efectivo_bvl": a_numero(df["solAmountNegotiated"], "BVL solAmountNegotiated"),
        "cierre_anterior_bvl": cierre_ant.where(cierre_ant > 0),
    })
    n_cierre_cero = int((cierre <= 0).sum())
    # La BVL no publica cierre en algunos días CON negociación (cierre = 0). Ese cierre se recupera del
    # "cierre anterior corregido" de la sesión siguiente (verificado: precio promedio / ese valor ~ 1,0).
    b = b.sort_values(["ticker", "fecha"]).reset_index(drop=True)
    sgte = b.groupby("ticker")["cierre_anterior_bvl"].shift(-1)
    recon = b["cierre_bvl"].isna() & (b["cantidad_bvl"].fillna(0) > 0) & (sgte > 0)
    b["cierre_bvl"] = b["cierre_bvl"].where(~recon, sgte)
    b["cierre_bvl_reconstruido"] = recon
    dup = int(b.duplicated(["ticker", "fecha"]).sum())
    if dup:
        raise ValueError(f"BVL: {dup} filas con (ticker, fecha) duplicada")
    log(f"BVL leído: filas={len(b):,} | tickers={sorted(b['ticker'].unique())} | cierre<=0: {n_cierre_cero} | reconstruidos desde el cierre anterior corregido del día siguiente: {int(recon.sum())} | sin precio: {int(b['cierre_bvl'].isna().sum())}")
    return b


# ================================== PRINCIPAL ================================
def main() -> int:
    log("=== INICIO 03_limpieza_datos ===")
    log(f"Entorno: Python {platform.python_version()} | pandas {pd.__version__} | numpy {np.__version__} | retorno={TIPO_RETORNO}")
    y, b = leer_yahoo(), leer_bvl()

    # ---- Unión externa por (ticker, fecha), validando que sea uno a uno ----
    df = y.merge(b, on=["ticker", "fecha"], how="outer", validate="one_to_one", indicator=True)
    df["fuente_presente"] = df["_merge"].map({"both": "ambas", "left_only": "solo_yahoo", "right_only": "solo_bvl"})
    df = df.drop(columns="_merge").sort_values(["ticker", "fecha"]).reset_index(drop=True)
    if df.duplicated(["ticker", "fecha"]).any():
        raise ValueError("La unión generó duplicados de (ticker, fecha)")
    log("Unión externa: " + " | ".join(f"{k}={v:,}" for k, v in df["fuente_presente"].value_counts().items()))

    # ---- Banderas de días sin negociación (no se elimina ninguna fila) ----
    df["sin_volumen_yahoo"] = (df["volumen_yahoo"] == 0).where(df["volumen_yahoo"].notna())
    df["sin_negociacion_bvl"] = (df["cantidad_bvl"].fillna(0) == 0).where(df["fuente_presente"].isin(["ambas", "solo_bvl"]))

    # ---- Retornos y diferencia de cierres ----
    df["ret_yahoo"] = retorno(df["cierre_ajustado_yahoo"], df["ticker"])
    df["ret_bvl"] = retorno(df["cierre_bvl"], df["ticker"])
    df["dif_cierre"] = df["cierre_yahoo"] - df["cierre_bvl"]   # Yahoo menos BVL, en soles
    # Retorno BVL contra el "cierre anterior corregido" que publica la propia BVL (una sesión)
    if TIPO_RETORNO == "log":
        df["ret_bvl_corr"] = np.log(df["cierre_bvl"] / df["cierre_anterior_bvl"])
    else:
        df["ret_bvl_corr"] = df["cierre_bvl"] / df["cierre_anterior_bvl"] - 1
    # Chequeo: ¿el cierre anterior corregido se aparta (>0,5 %) del último cierre BVL válido?
    previo_valido = df.groupby("ticker")["cierre_bvl"].transform(lambda x: x.ffill().shift(1))
    flag_dif = ((df["cierre_anterior_bvl"] / previo_valido - 1).abs() > 0.005)

    columnas = ["ticker", "fecha", "cierre_yahoo", "cierre_ajustado_yahoo", "volumen_yahoo", "dividendo_yahoo",
                "cierre_bvl", "cantidad_bvl", "monto_efectivo_bvl", "ret_yahoo", "ret_bvl",
                "sin_volumen_yahoo", "sin_negociacion_bvl", "dif_cierre", "fuente_presente",
                "cierre_anterior_bvl", "ret_bvl_corr", "cierre_bvl_reconstruido"]
    df = df[columnas]

    # ---- Resumen de calidad por emisor (insumo para el artículo) ----
    filas = []
    for t, g in df.groupby("ticker"):
        gy, gb, ga = g[g["fuente_presente"] != "solo_bvl"], g[g["fuente_presente"] != "solo_yahoo"], g[g["fuente_presente"] == "ambas"]
        ry, rb, rc = g["ret_yahoo"].dropna(), g["ret_bvl"].dropna(), g["ret_bvl_corr"].dropna()
        fd = flag_dif.loc[g.index]
        filas.append({
            "ticker": t, "n_total": len(g),
            "n_ambas": int((g["fuente_presente"] == "ambas").sum()),
            "n_solo_yahoo": int((g["fuente_presente"] == "solo_yahoo").sum()),
            "n_solo_bvl": int((g["fuente_presente"] == "solo_bvl").sum()),
            "pct_sin_volumen_yahoo": round(100 * (gy["volumen_yahoo"] == 0).mean(), 2) if len(gy) else np.nan,
            "pct_sin_negociacion_bvl": round(100 * (gb["cantidad_bvl"].fillna(0) == 0).mean(), 2) if len(gb) else np.nan,
            "n_yahoo_vol0_bvl_con_negoc": int(((ga["volumen_yahoo"] == 0) & (ga["cantidad_bvl"] > 0)).sum()),
            "n_yahoo_con_vol_bvl_sin_negoc": int(((ga["volumen_yahoo"] > 0) & (ga["cantidad_bvl"].fillna(0) == 0)).sum()),
            "pct_ret_cero_yahoo": round(100 * (ry == 0).mean(), 2) if len(ry) else np.nan,
            "pct_ret_cero_bvl": round(100 * (rb == 0).mean(), 2) if len(rb) else np.nan,
            "pct_ret_cero_bvl_corr": round(100 * (rc == 0).mean(), 2) if len(rc) else np.nan,
            "n_cierres_bvl_reconstruidos": int((g["cierre_bvl_reconstruido"] == True).sum()),
            "n_cierre_ant_distinto_0_5pct": int(fd.sum()),
            "n_de_esos_con_dividendo_yahoo": int((fd & (g["dividendo_yahoo"] > 0)).sum()),
        })
    resumen = pd.DataFrame(filas)
    resumen.to_csv(RUTA_RESUMEN, index=False, encoding="utf-8", lineterminator="\n")

    # ---- Guardado y hash (lineterminator fijo para que el hash no dependa del sistema operativo) ----
    df.to_csv(RUTA_SALIDA, index=False, encoding="utf-8", lineterminator="\n")
    h = sha256_archivo(RUTA_SALIDA)
    RUTA_HASH.write_text(f"{h}  {RUTA_SALIDA.name}\n", encoding="utf-8")

    log(f"Procesado: {RUTA_SALIDA.name} | filas={len(df):,} | columnas={len(df.columns)} | sha256={h}")
    log(f"Resumen de calidad: {RUTA_RESUMEN.name}")
    if len(df.columns) < COLUMNAS_MIN_PROCESADO:
        log("AVISO: menos columnas que el mínimo de la consigna")
    if len(df) < OBS_MINIMAS_TEMARIO:
        log(f"AVISO: {len(df):,} filas; el mínimo del temario es {OBS_MINIMAS_TEMARIO:,}")
    log("=== FIN 03_limpieza_datos ===")
    return 0


if __name__ == "__main__":
    codigo_salida = main()
    if "ipykernel" not in sys.modules:   # en Colab/Jupyter sys.exit() muestra un aviso inofensivo
        sys.exit(codigo_salida)

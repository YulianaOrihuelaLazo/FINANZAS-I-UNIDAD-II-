# Nombres y apellidos: ORIHUELA LAZO YULIANA
# Código de matrícula: 2024200514G
# Tema: Valor en riesgo (VaR) de un portafolio de acciones peruanas - N°70
# Fecha de extracción: 2026-11-14 

# =============================================================================
# 01_extraccion_api.py  -  VÍA 1: API (Yahoo Finance)
#
# Qué hace este script:
#   * Consume la API de Yahoo Finance (vía la librería yfinance) para las 8 acciones
#     de la cartera, con frecuencia diaria entre FECHA_INICIO y FECHA_CORTE.
#   * Guarda los datos CRUDOS tal como salen de la fuente (sin editar) en /datos_crudos.
#   * Registra en log_ejecucion.txt la fecha y hora de cada extracción, el número de
#     filas, el código de respuesta HTTP y el hash SHA-256 de cada archivo crudo.
#
# Endpoint declarado: yfinance consulta
#   https://query1.finance.yahoo.com/v8/finance/chart/{ticker}
#   con parámetros: period1/period2 (rango), interval=1d, events=div|splits.
#   Yahoo Finance no requiere clave de API, por eso no hay .env.example con claves.
#
# Ubicación esperada: <proyecto>/codigo/01_extraccion_api.py
# Orden de ejecución: 01_extraccion_api -> 02_scraping_web -> 03_limpieza_datos -> 04_analisis
# Instalación: pip install yfinance pandas requests
# =============================================================================

import datetime as dt
import hashlib
import platform
import sys
import time
from pathlib import Path

import pandas as pd
import requests

# ============================ PARÁMETROS CONGELADOS ==========================
# Constantes (no se usan fechas dinámicas tipo "hoy"): garantizan reproducibilidad.
CODIGO = "2024200514G"
FECHA_INICIO = "2015-01-01"
FECHA_CORTE = "2025-12-31"   # inclusive; yfinance excluye la fecha final, se ajusta abajo

# Cartera de 8 acciones (sufijo .LM = Bolsa de Valores de Lima en Yahoo Finance)
TICKERS = {
    "VOLCABC1.LM": ("Volcan Compañía Minera (clase B)", "Minería"),
    "FERREYC1.LM": ("Ferreycorp", "Industria/Servicios"),
    "ALICORC1.LM": ("Alicorp", "Consumo"),
    "CPACASC1.LM": ("Cementos Pacasmayo", "Construcción"),
    "UNACEMC1.LM": ("UNACEM", "Construcción"),
    "MINSURI1.LM": ("Minsur", "Minería"),
    "LUSURC1.LM": ("Luz del Sur", "Energía"),
    "BACKUSI1.LM": ("Unión de Cervecerías Backus", "Consumo"),
}

ENDPOINT_YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart"
INTERVALO = "1d"
PAUSA_SEGUNDOS = 1.0     # pausa mínima entre solicitudes (buena práctica, numeral 2.4.8)
REINTENTOS = 3           # reintentos ante fallas temporales de red
OBS_MINIMAS_TEMARIO = 20000
# Identificación del cliente para el sondeo HTTP (incluye "Mozilla" porque Yahoo
# rechaza agentes de usuario sin ese prefijo).
USER_AGENT = "Mozilla/5.0 (compatible; FinanzasI-UNCP-2026II; Orihuela Lazo Yuliana; 2024200514G; uso academico)"

# ============================= RUTAS RELATIVAS ===============================
# Rutas relativas a la carpeta del proyecto (nunca rutas absolutas tipo C:\Users\...).
try:
    RAIZ = Path(__file__).resolve().parent.parent   # script dentro de /scripts
except NameError:                                    # Colab / Jupyter: no existe __file__
    RAIZ = Path.cwd()
DIR_CRUDOS = RAIZ / "datos_crudos"
DIR_CRUDOS.mkdir(parents=True, exist_ok=True)
LOG_PATH = RAIZ / "log_ejecucion.txt"


# ================================ UTILIDADES =================================
def log(msg: str) -> None:
    """Escribe en pantalla y en log_ejecucion.txt con fecha y hora."""
    linea = f"[{dt.datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(linea)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


def sha256_archivo(ruta: Path) -> str:
    """Hash SHA-256 del archivo (evidencia de integridad del dato crudo)."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def sondeo_http(ticker: str) -> str:
    """
    yfinance no expone el código HTTP. Para dejar evidencia, se consulta una vez el MISMO
    endpoint con un rango corto (5 días) y se registra el código de respuesta.
    """
    try:
        r = requests.get(
            f"{ENDPOINT_YAHOO}/{ticker}",
            params={"range": "5d", "interval": INTERVALO},
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        return str(r.status_code)
    except Exception as e:  # sin conexión, DNS, etc.
        return f"ERROR({type(e).__name__})"


def validar_descarga(df: pd.DataFrame, ticker: str) -> None:
    """Una descarga vacía o incompleta se trata como ERROR (yfinance no lanza excepción)."""
    if df is None or df.empty:
        raise ValueError(f"descarga vacía para {ticker} (símbolo inexistente o sin datos)")
    faltan = {"Close", "Volume"} - set(df.columns)
    if faltan:
        raise ValueError(f"faltan columnas {faltan} en {ticker}")


# ============================== EXTRACCIÓN ===================================
def extraer_ticker(ticker: str) -> dict:
    """Descarga un ticker, guarda el crudo y devuelve un diccionario de metadatos."""
    import yfinance as yf  # import local: facilita registrar la versión en el log

    # yfinance excluye la fecha final: se suma un día para incluir FECHA_CORTE
    fin_exclusivo = (pd.Timestamp(FECHA_CORTE) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    ultimo_error = None
    for intento in range(1, REINTENTOS + 1):
        try:
            tk = yf.Ticker(ticker)
            # auto_adjust=False -> se obtienen Close (sin ajustar) y Adj Close (ajustado)
            df = tk.history(
                start=FECHA_INICIO, end=fin_exclusivo, interval=INTERVALO,
                auto_adjust=False, actions=True,
            )
            validar_descarga(df, ticker)

            # Dato crudo TAL COMO SALE de la fuente (sin ninguna edición)
            ruta = DIR_CRUDOS / f"api_yahoo_{ticker}_{CODIGO}.csv"
            df.to_csv(ruta, encoding="utf-8")

            # Metadatos de la fuente (moneda de cotización, bolsa, zona horaria)
            try:
                meta = tk.history_metadata or {}
            except Exception:
                meta = {}

            http = sondeo_http(ticker)
            idx = pd.to_datetime(df.index)
            return {
                "ticker": ticker,
                "emisora": TICKERS[ticker][0],
                "sector": TICKERS[ticker][1],
                "moneda": meta.get("currency", "NA"),
                "bolsa": meta.get("exchangeName", "NA"),
                "zona_horaria": meta.get("exchangeTimezoneName", "NA"),
                "filas": int(len(df)),
                "primera_fecha": str(idx.min().date()),
                "ultima_fecha": str(idx.max().date()),
                "http_sondeo": http,
                "sha256_crudo": sha256_archivo(ruta),
                "archivo": ruta.name,
                "estado": "OK",
                "error": "",
            }
        except Exception as e:
            ultimo_error = f"{type(e).__name__}: {e}"
            log(f"  {ticker}: intento {intento}/{REINTENTOS} falló -> {ultimo_error}")
            time.sleep(PAUSA_SEGUNDOS * intento)  # espera creciente

    return {
        "ticker": ticker, "emisora": TICKERS[ticker][0], "sector": TICKERS[ticker][1],
        "filas": 0, "http_sondeo": "NA", "estado": "ERROR", "error": ultimo_error or "desconocido",
    }


def main() -> int:
    log("=== INICIO 01_extraccion_api ===")
    try:
        import yfinance
        v_yf = yfinance.__version__
    except Exception:
        v_yf = "NO INSTALADO"
    log(f"Entorno: Python {platform.python_version()} | yfinance {v_yf} | "
        f"pandas {pd.__version__} | requests {requests.__version__}")
    log(f"Parámetros: FECHA_INICIO={FECHA_INICIO} FECHA_CORTE={FECHA_CORTE} "
        f"intervalo={INTERVALO} endpoint={ENDPOINT_YAHOO}")

    resultados = []
    for t in TICKERS:
        res = extraer_ticker(t)
        resultados.append(res)
        if res["estado"] == "OK":
            log(f"{t} | filas={res['filas']} | {res['primera_fecha']} a {res['ultima_fecha']} | "
                f"moneda={res['moneda']} | HTTP(sondeo)={res['http_sondeo']} | "
                f"sha256={res['sha256_crudo'][:16]}... | OK")
        else:
            log(f"{t} | ERROR | {res['error']}")
        time.sleep(PAUSA_SEGUNDOS)

    # Tabla de metadatos de la extracción (no es dato crudo; es evidencia de la corrida)
    meta = pd.DataFrame(resultados)
    ruta_meta = DIR_CRUDOS / f"metadatos_extraccion_yahoo_{CODIGO}.csv"
    meta.to_csv(ruta_meta, index=False, encoding="utf-8-sig")

    ok = meta[meta["estado"] == "OK"]
    errores = meta[meta["estado"] == "ERROR"]
    total = int(ok["filas"].sum())
    log(f"RESUMEN: {len(ok)} OK, {len(errores)} con ERROR | filas totales={total:,}")
    if total < OBS_MINIMAS_TEMARIO:
        log(f"ATENCIÓN: {total:,} filas < mínimo del temario ({OBS_MINIMAS_TEMARIO:,}).")
    monedas = sorted(set(ok["moneda"].astype(str))) if len(ok) else []
    log(f"Monedas de cotización detectadas: {monedas} (si hay más de una, convertir en 03)")

    log("=== FIN 01_extraccion_api ===")
    return 1 if len(errores) else 0   # código de salida distinto de 0 si algo falló


if __name__ == "__main__":
    sys.exit(main())

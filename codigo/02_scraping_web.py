# Nombres y apellidos: ORIHUELA LAZO YULIANA
# Código de matrícula: 2024200514G
# Tema: Valor en riesgo (VaR) de un portafolio de acciones peruanas -N° 70
# Fecha de extracción: 2026-11-19 
#
# =============================================================================
# 02_scraping_web.py  -  VÍA 2: BVL (Bolsa de Valores de Lima), cotizaciones diarias
#
# Qué hace este script:
#   * Consulta, con requests, el servicio de datos que la propia página de la BVL usa
#     en la pestaña "Histórico de cotizaciones" de cada emisor:
#         GET https://dataondemand.bvl.com.pe/v1/issuers/stock
#             ?name={NEMONICO}&startDate=AAAA-MM-DD&endDate=AAAA-MM-DD
#     Responde JSON (lista de sesiones diarias). Campos observados en la prueba manual de
#     la página: nemonico, date, open, close, high, low, average, quantityNegotiated,
#     solAmountNegotiated, dollarAmountNegotiated, yesterday, yesterdayClose, currencySymbol.
#   * Pide un año calendario por solicitud (la prueba manual se hizo con rangos de un año).
#   * Guarda la respuesta ORIGINAL (bytes tal como llegaron) en /datos_crudos y, aparte,
#     una tabla cruda unificada sin limpiar (todo como texto, sin convertir tipos).
#   * Registra en log_ejecucion.txt fecha y hora, URL, código HTTP, filas y hash SHA-256.
#
# Ética y legalidad (numeral 2.4.8 de la consigna):
#   * Solo información pública que cualquier visitante ve en la web de la BVL.
#   * Pausa de PAUSA_SEGUNDOS (>= 1 s) entre solicitudes y User-Agent identificable.
#   * No se extraen datos personales. No se evade ningún bloqueo: si el servidor responde
#     403/429 o similar, el script se DETIENE y se documenta en incidencias_fuente.md.
#   * Términos de uso: los T&C de la BVL (www.bvl.com.pe/regulacion/terminos-y-condiciones)
#     prohíben redistribuir la información de cotización. Los datos se usan solo con fines
#     académicos y la fuente fue aceptada por el docente de la asignatura.
#   * La BVL no publica un robots.txt real (la ruta devuelve el HTML del sitio); el script
#     lo consulta y deja constancia en el log.
#
# Ubicación esperada: <proyecto>/codigo/02_scraping_web.py
# Orden de ejecución: 01_extraccion_api -> 02_scraping_web -> 03_limpieza_datos -> 04_analisis
# Instalación: pip install requests pandas
# Variable de entorno opcional: CONTACTO_SCRAPING (correo de contacto que va en el User-Agent)
# =============================================================================

import datetime as dt
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

import pandas as pd
import requests

# ============================ PARÁMETROS CONGELADOS ==========================
CODIGO = "2024200514G"
FECHA_INICIO = "2015-01-01"
FECHA_CORTE = "2025-12-31"   # inclusive (si el servicio la excluye, se verá en el log)
ANIO_INICIO = int(FECHA_INICIO[:4])
ANIO_FIN = int(FECHA_CORTE[:4])

PAUSA_SEGUNDOS = 1.0         # pausa mínima entre solicitudes (numeral 2.4.8)
REINTENTOS = 3               # reintentos solo ante fallas de red o 5xx (no ante 403/429)
TIMEOUT = 30
OBS_MINIMAS_TEMARIO = 20000

ENDPOINT_BVL = "https://dataondemand.bvl.com.pe/v1/issuers/stock"
URLS_ROBOTS = ["https://www.bvl.com.pe/robots.txt", "https://dataondemand.bvl.com.pe/robots.txt"]

CONTACTO = os.environ.get("CONTACTO_SCRAPING", "e_2024200514G@uncp.edu.pe")   # correo institucional (se puede sobrescribir con la variable de entorno)
USER_AGENT = (f"FinanzasI-UNCP-2026II; Orihuela Lazo Yuliana; {CODIGO}; "
              f"uso academico; contacto: {CONTACTO}")

# Nemónicos BVL = ticker de Yahoo sin el sufijo ".LM" (misma cartera que 01_extraccion_api.py)
NEMONICOS = [
    "VOLCABC1", "FERREYC1", "ALICORC1", "CPACASC1",
    "UNACEMC1", "MINSURI1", "LUSURC1", "BACKUSI1",
]

# ============================= RUTAS RELATIVAS ===============================
try:
    RAIZ = Path(__file__).resolve().parent.parent   # script dentro de /codigo
except NameError:                                    # Colab / Jupyter: no existe __file__
    RAIZ = Path.cwd()
DIR_CRUDOS = RAIZ / "datos_crudos"
DIR_CRUDOS.mkdir(parents=True, exist_ok=True)
DIR_JSON_BVL = DIR_CRUDOS / "bvl_json_por_anio"   # respuestas originales (1 por emisor y año)
DIR_JSON_BVL.mkdir(parents=True, exist_ok=True)
LOG_PATH = RAIZ / "log_ejecucion.txt"


# ================================ UTILIDADES =================================
def log(msg: str) -> None:
    """Escribe en pantalla y en log_ejecucion.txt con fecha y hora."""
    linea = f"[{dt.datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(linea)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


def sha256_bytes(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


class FuenteBloqueada(Exception):
    """El servidor rechazó la solicitud (403/429...). No se evade: se detiene y se documenta."""


def consultar_robots(sesion: requests.Session) -> None:
    """Consulta robots.txt y deja constancia. Si devuelve HTML, no es un robots.txt real."""
    for url in URLS_ROBOTS:
        try:
            r = sesion.get(url, timeout=TIMEOUT)
            tipo = r.headers.get("Content-Type", "NA")
            es_html = "html" in tipo.lower() or r.text.lstrip().lower().startswith("<!doctype")
            log(f"robots.txt | {url} | HTTP={r.status_code} | content-type={tipo} | "
                f"{'devuelve HTML (no hay robots.txt real)' if es_html else 'texto plano: REVISAR a mano'}")
            if not es_html and r.status_code == 200:
                log("robots.txt contenido (primeras líneas): " + " / ".join(r.text.splitlines()[:8]))
        except requests.RequestException as e:
            log(f"robots.txt | {url} | error de red: {type(e).__name__}")
        time.sleep(PAUSA_SEGUNDOS)


def pedir_anio(sesion: requests.Session, nemonico: str, anio: int):
    """
    Una solicitud (nemónico, año). Devuelve (bytes_originales, http, lista_de_registros).
    Se limita el rango a [FECHA_INICIO, FECHA_CORTE].
    """
    ini = max(f"{anio}-01-01", FECHA_INICIO)
    fin = min(f"{anio}-12-31", FECHA_CORTE)
    params = {"name": nemonico, "startDate": ini, "endDate": fin}
    ultimo_error = ""
    for intento in range(1, REINTENTOS + 1):
        try:
            r = sesion.get(ENDPOINT_BVL, params=params, timeout=TIMEOUT)
            if r.status_code in (401, 403, 429):
                raise FuenteBloqueada(f"HTTP {r.status_code} en {r.url}")
            if r.status_code >= 500:
                ultimo_error = f"HTTP {r.status_code}"
                time.sleep(PAUSA_SEGUNDOS * intento)
                continue
            if r.status_code != 200:
                return r.content, r.status_code, None, r.url
            registros = json.loads(r.content)
            if not isinstance(registros, list):
                return r.content, r.status_code, None, r.url
            return r.content, r.status_code, registros, r.url
        except FuenteBloqueada:
            raise
        except (requests.RequestException, json.JSONDecodeError) as e:
            ultimo_error = f"{type(e).__name__}"
            time.sleep(PAUSA_SEGUNDOS * intento)
    return b"", 0, None, f"{ENDPOINT_BVL}?name={nemonico}&startDate={ini}&endDate={fin} ({ultimo_error})"


# ================================== PRINCIPAL ================================
def main() -> int:
    log("=== INICIO 02_scraping_web ===")
    log(f"Entorno: Python {platform.python_version()} | pandas {pd.__version__} | requests {requests.__version__}")
    log(f"Parámetros: FECHA_INICIO={FECHA_INICIO} FECHA_CORTE={FECHA_CORTE} endpoint={ENDPOINT_BVL} "
        f"pausa={PAUSA_SEGUNDOS}s")

    sesion = requests.Session()
    sesion.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    log(f"User-Agent: {USER_AGENT}")
    consultar_robots(sesion)

    metadatos, todas_las_filas, errores = [], [], 0
    try:
        for nem in NEMONICOS:
            filas_nem = 0
            for anio in range(ANIO_INICIO, ANIO_FIN + 1):
                contenido, http, registros, url = pedir_anio(sesion, nem, anio)
                time.sleep(PAUSA_SEGUNDOS)
                if registros is None:
                    errores += 1
                    log(f"{nem} | {anio} | HTTP={http} | ERROR | {url}")
                    metadatos.append({"nemonico": nem, "anio": anio, "http": http, "filas": 0,
                                      "estado": "ERROR", "url": url, "sha256_crudo": "", "archivo": ""})
                    continue
                # Respuesta original, byte a byte, sin editar
                ruta = DIR_JSON_BVL / f"bvl_{nem}_{anio}_{CODIGO}.json"
                with open(ruta, "wb") as f:
                    f.write(contenido)
                n = len(registros)
                filas_nem += n
                todas_las_filas.extend(registros)
                fechas = [x.get("date") for x in registros if isinstance(x, dict)]
                rango = f"{min(fechas)} a {max(fechas)}" if fechas else "sin filas"
                estado = "OK" if n > 0 else "VACIO"
                log(f"{nem} | {anio} | filas={n} | {rango} | HTTP={http} | sha256={sha256_bytes(contenido)[:16]}... | {estado}")
                metadatos.append({"nemonico": nem, "anio": anio, "http": http, "filas": n, "estado": estado,
                                  "url": url, "sha256_crudo": sha256_archivo(ruta), "archivo": f"bvl_json_por_anio/{ruta.name}"})
            log(f"{nem} | TOTAL filas={filas_nem}")
    except FuenteBloqueada as e:
        errores += 1
        log(f"FUENTE BLOQUEADA: {e}. No se evade. Documentar en incidencias_fuente.md "
            f"(URL, fecha y hora, código HTTP, captura) y pedir sustitución al docente por ADESA.")

    # Tabla cruda unificada (sin limpiar: todo como texto; la tipificación se hace en 03)
    if todas_las_filas:
        df = pd.DataFrame(todas_las_filas).astype(str)
        ruta_tabla = DIR_CRUDOS / f"bvl_cotizaciones_crudo_{CODIGO}.csv"
        df.to_csv(ruta_tabla, index=False, encoding="utf-8")
        log(f"Tabla cruda unificada: {ruta_tabla.name} | filas={len(df)} | sha256={sha256_archivo(ruta_tabla)[:16]}...")
    pd.DataFrame(metadatos).to_csv(DIR_CRUDOS / f"metadatos_extraccion_bvl_{CODIGO}.csv", index=False, encoding="utf-8")

    total = len(todas_las_filas)
    log(f"RESUMEN: filas totales BVL={total:,} | solicitudes con ERROR={errores}")
    if total and total < OBS_MINIMAS_TEMARIO:
        log(f"AVISO: la BVL aporta {total:,} filas; el mínimo del temario es {OBS_MINIMAS_TEMARIO:,} (se cuenta sobre la base unida).")
    log("=== FIN 02_scraping_web ===")
    return 1 if errores else 0


if __name__ == "__main__":
    codigo_salida = main()
    if "ipykernel" not in sys.modules:   # en Colab/Jupyter sys.exit() muestra un aviso inofensivo
        sys.exit(codigo_salida)

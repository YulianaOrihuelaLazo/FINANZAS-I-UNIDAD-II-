# Nombres y apellidos: YULIANA ORIHUELA LAZO
# Código de matrícula: 2024200514G
# Tema: Valor en riesgo (VaR) de un portafolio de acciones peruanas - N°70
# Fecha de extracción: 2026-11-19 
#
# =============================================================================
# 04_analisis.py  -  VaR PARAMÉTRICO, HISTÓRICO Y MONTE CARLO + BACKTESTING
#
# Qué hace este script (parte SOLO de datos_procesados; todas las tablas y figuras del artículo
# salen de aquí y se guardan en /salidas):
#   1. Arma la matriz de retornos diarios de las 8 acciones (cartera con pesos iguales 1/8).
#        * Serie PRINCIPAL  = BVL (retorno contra el "cierre anterior corregido" de la BVL),
#                             en el calendario de días en que la BVL operó.
#        * Serie CONTRASTE  = Yahoo (cierre ajustado), solo en las fechas que tienen ambas fuentes.
#   2. Para cada día t estima el VaR con una ventana móvil de VENTANA días que termina en t-1
#      (nunca usa información de t: sin sesgo de anticipación):
#        * Paramétrico: normal, con media y covarianza de la ventana.      VaR = -(mu_p + z * sigma_p)
#        * Histórico:   cuantil empírico de los retornos de la cartera en la ventana.
#        * Monte Carlo: simula N_SIM retornos normales multivariados (media y covarianza de la ventana).
#      A 95 % y 99 %, horizonte de 1 día.
#   3. Backtesting: una EXCEPCIÓN ocurre cuando la pérdida del día t supera el VaR estimado para t.
#      Se aplican Kupiec (frecuencia), Christoffersen (independencia y cobertura condicional) y la
#      zona de Basilea (semáforo) sobre los últimos 250 días al 99 %.
#   4. Tablas y figuras: descriptivos, correlaciones, concordancia Yahoo-BVL, liquidez (monto efectivo
#      BVL), VaR promedio y backtesting.
#
# Decisiones declaradas (deben ir en el artículo):
#   * Pesos iguales (1/8) y constantes; valor de la cartera V0 = 1 000 000 soles (solo para expresar el VaR en S/).
#   * Los retornos diarios por acción se pasan a SIMPLES para agregarlos en la cartera.
#   * Días sin negociación en la BVL: retorno 0 (el precio no se movió; el cierre anterior corregido
#     de la sesión siguiente ya recoge el último precio).
#   * Monte Carlo con distribución normal: converge al VaR paramétrico cuando N_SIM crece; sus
#     diferencias con el paramétrico son solo ruido de simulación. Semilla fija SEMILLA = 514
#     (cuatro últimos dígitos de la matrícula).
#
# Ubicación esperada: <proyecto>/codigo/04_analisis.py
# Orden de ejecución: 01_extraccion_api -> 02_scraping_web -> 03_limpieza_datos -> 04_analisis
# Instalación: pip install pandas numpy scipy matplotlib
# =============================================================================

import datetime as dt
import platform
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")                      # figuras a archivo, sin ventana
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import __version__ as scipy_version
from scipy.special import xlog1py, xlogy
from scipy.stats import chi2, kurtosis, norm, skew

# ============================ PARÁMETROS CONGELADOS ==========================
CODIGO = "2024200514G"
SEMILLA = 514                # cuatro últimos dígitos de la matrícula (0514)
VENTANA = 250                # días de la ventana móvil (aprox. un año bursátil)
N_SIM = 10000                # simulaciones Monte Carlo por día
NIVELES = (0.95, 0.99)       # niveles de confianza
V0 = 1_000_000               # valor de la cartera en soles (solo para expresar el VaR en S/)
TIPO_RETORNO = "log"         # DEBE coincidir con el de 03_limpieza_datos.py
DIAS_ANIO = 252              # para anualizar la volatilidad
TOLERANCIA_CIERRE = 0.005    # soles: diferencia mínima para decir que dos cierres "difieren"
METODOS = ("param", "hist", "mc")
NOMBRE_METODO = {"param": "Paramétrico", "hist": "Histórico", "mc": "Monte Carlo"}

# ============================= RUTAS RELATIVAS ===============================
try:
    RAIZ = Path(__file__).resolve().parent.parent   # script dentro de /codigo
except NameError:                                    # Colab / Jupyter: no existe __file__
    RAIZ = Path.cwd()
DIR_PROC = RAIZ / "datos_procesados"
DIR_SAL = RAIZ / "salidas"
DIR_SAL.mkdir(parents=True, exist_ok=True)
LOG_PATH = RAIZ / "log_ejecucion.txt"
RUTA_PROC = DIR_PROC / f"datos_procesados_{CODIGO}.csv"


# ================================ UTILIDADES =================================
def log(msg: str) -> None:
    linea = f"[{dt.datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(linea)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


def guardar_tabla(df: pd.DataFrame, nombre: str, indice: bool = False) -> None:
    ruta = DIR_SAL / nombre
    df.round(6).to_csv(ruta, index=indice, encoding="utf-8", lineterminator="\n")
    log(f"Tabla guardada: {nombre} ({len(df)} filas)")


def guardar_figura(fig, nombre: str) -> None:
    fig.tight_layout()
    fig.savefig(DIR_SAL / nombre, dpi=150)
    plt.close(fig)
    log(f"Figura guardada: {nombre}")


def a_simple(r: pd.DataFrame) -> pd.DataFrame:
    """Pasa retornos logarítmicos a simples (para poder agregarlos en la cartera)."""
    return np.expm1(r) if TIPO_RETORNO == "log" else r


# ====================== RETORNOS: SERIE PRINCIPAL Y CONTRASTE =================
def retornos_bvl(df: pd.DataFrame) -> pd.DataFrame:
    """Serie PRINCIPAL: calendario de días en que la BVL tuvo sesión; retorno contra cierre anterior corregido."""
    g = df[df["fuente_presente"].isin(["ambas", "solo_bvl"])].copy()
    r = g["ret_bvl_corr"]
    # si falta el cierre anterior corregido pero hubo cierre: retorno cierre contra cierre
    r = r.where(~(r.isna() & g["cierre_bvl"].notna()), g["ret_bvl"])
    # día sin negociación: el precio no se movió -> retorno 0
    sin_neg = g["cantidad_bvl"].fillna(0).eq(0)
    r = r.where(~(r.isna() & sin_neg), 0.0)
    ancho = g.assign(r=r).pivot(index="fecha", columns="ticker", values="r").sort_index()
    n0 = len(ancho)
    ancho = ancho.dropna()
    log(f"Serie BVL (principal): fechas={n0:,} | fechas completas para las 8 acciones={len(ancho):,} | descartadas={n0 - len(ancho)}")
    return a_simple(ancho)


def retornos_yahoo(df: pd.DataFrame, fechas_bvl: pd.Index) -> pd.DataFrame:
    """Serie CONTRASTE: cierre ajustado de Yahoo, solo fechas con ambas fuentes."""
    g = df[df["fuente_presente"] == "ambas"]
    ancho = g.pivot(index="fecha", columns="ticker", values="ret_yahoo").sort_index()
    n0 = len(ancho)
    ancho = ancho.dropna()
    log(f"Serie Yahoo (contraste): fechas con ambas fuentes={n0:,} | completas para las 8 acciones={len(ancho):,}")
    return a_simple(ancho)


# ============================ VaR: TRES MÉTODOS ==============================
def calcular_var(R: pd.DataFrame, w: np.ndarray):
    """Devuelve el retorno diario de la cartera y los VaR (positivos, como fracción del valor) por método y nivel."""
    X = R.to_numpy()
    T = len(X)
    rp = X @ w                                           # retorno de la cartera, día a día
    rng = np.random.default_rng(SEMILLA)                 # semilla fijada UNA sola vez por serie
    out = {f"{m}_{int(round(a * 100))}": np.full(T, np.nan) for m in METODOS for a in NIVELES}
    for t in range(VENTANA, T):
        ventana = X[t - VENTANA:t]                       # días t-VENTANA ... t-1 (sin mirar el día t)
        mu = ventana.mean(axis=0)
        cov = np.cov(ventana, rowvar=False)
        mu_p, sd_p = float(w @ mu), float(np.sqrt(w @ cov @ w))
        rp_v = rp[t - VENTANA:t]
        sims = rng.multivariate_normal(mu, cov, size=N_SIM) @ w
        for a in NIVELES:
            k = int(round(a * 100))
            out[f"param_{k}"][t] = -(mu_p + norm.ppf(1 - a) * sd_p)
            out[f"hist_{k}"][t] = -np.quantile(rp_v, 1 - a)
            out[f"mc_{k}"][t] = -np.quantile(sims, 1 - a)
    return rp, out


# ============================== BACKTESTING ==================================
def kupiec(x: int, T: int, p: float):
    """Prueba de proporción de fallas de Kupiec (LR ~ chi2 con 1 gl)."""
    if T == 0:
        return np.nan, np.nan
    ph = x / T
    ll0 = (T - x) * np.log(1 - p) + xlogy(x, p)
    ll1 = xlog1py(T - x, -ph) + xlogy(x, ph)
    lr = max(-2 * (ll0 - ll1), 0.0)
    return lr, 1 - chi2.cdf(lr, 1)


def christoffersen(exc: np.ndarray):
    """Independencia de Christoffersen (LR_ind, p) a partir de las transiciones entre excepciones."""
    e = exc.astype(int)
    a, b = e[:-1], e[1:]
    n00, n01 = int(((a == 0) & (b == 0)).sum()), int(((a == 0) & (b == 1)).sum())
    n10, n11 = int(((a == 1) & (b == 0)).sum()), int(((a == 1) & (b == 1)).sum())
    pi01 = n01 / (n00 + n01) if (n00 + n01) else 0.0
    pi11 = n11 / (n10 + n11) if (n10 + n11) else 0.0
    pi = (n01 + n11) / max(n00 + n01 + n10 + n11, 1)
    ll_ind = xlogy(n00 + n10, 1 - pi) + xlogy(n01 + n11, pi)
    ll_mar = xlogy(n00, 1 - pi01) + xlogy(n01, pi01) + xlogy(n10, 1 - pi11) + xlogy(n11, pi11)
    lr = max(-2 * (ll_ind - ll_mar), 0.0)
    return lr, 1 - chi2.cdf(lr, 1)


def semaforo(n_exc_250: int) -> str:
    """Zona de Basilea para VaR al 99 % con 250 observaciones."""
    return "verde" if n_exc_250 <= 4 else ("amarilla" if n_exc_250 <= 9 else "roja")


def backtesting(serie: str, fechas: pd.Index, rp: np.ndarray, var: dict):
    filas, diario = [], {"fecha": fechas, "retorno_cartera": rp}
    perdida = -rp
    for m in METODOS:
        for a in NIVELES:
            k = int(round(a * 100))
            v = var[f"{m}_{k}"]
            ok = ~np.isnan(v)
            exc = np.zeros(len(v), dtype=bool)
            exc[ok] = perdida[ok] > v[ok]
            T, x = int(ok.sum()), int(exc[ok].sum())
            lr_uc, p_uc = kupiec(x, T, 1 - a)
            lr_ind, p_ind = christoffersen(exc[ok])
            lr_cc = lr_uc + lr_ind
            ult = exc[ok][-250:]
            filas.append({
                "serie": serie, "metodo": NOMBRE_METODO[m], "nivel": f"{k} %", "dias_evaluados": T,
                "excepciones": x, "tasa_observada_pct": 100 * x / T, "tasa_esperada_pct": 100 * (1 - a),
                "kupiec_LR": lr_uc, "kupiec_p": p_uc, "christoffersen_ind_LR": lr_ind, "christoffersen_ind_p": p_ind,
                "cobertura_cond_LR": lr_cc, "cobertura_cond_p": 1 - chi2.cdf(lr_cc, 2),
                "excepciones_ultimos_250": int(ult.sum()), "zona_basilea_99": semaforo(int(ult.sum())) if k == 99 else "NA",
            })
            diario[f"var_{m}_{k}"] = v
            diario[f"exc_{m}_{k}"] = exc
    return pd.DataFrame(filas), pd.DataFrame(diario)


# =========================== TABLAS DESCRIPTIVAS =============================
def tabla_descriptivos(R: pd.DataFrame, w: np.ndarray) -> pd.DataFrame:
    R = R.assign(CARTERA=R.to_numpy() @ w)
    filas = []
    for c in R.columns:
        x = R[c]
        filas.append({"serie": c, "n": len(x), "media_diaria_pct": 100 * x.mean(), "desv_diaria_pct": 100 * x.std(),
                      "vol_anual_pct": 100 * x.std() * np.sqrt(DIAS_ANIO), "minimo_pct": 100 * x.min(),
                      "maximo_pct": 100 * x.max(), "asimetria": skew(x), "curtosis_exceso": kurtosis(x),
                      "pct_retorno_cero": 100 * (x == 0).mean()})
    return pd.DataFrame(filas)


def tabla_concordancia(df: pd.DataFrame) -> pd.DataFrame:
    g = df[df["fuente_presente"] == "ambas"]
    filas = []
    for t, x in g.groupby("ticker"):
        dif = x["dif_cierre"].abs()
        c = x.dropna(subset=["ret_yahoo", "ret_bvl_corr"])
        filas.append({
            "ticker": t, "n_fechas_ambas": len(x), "dif_cierre_abs_media_S": dif.mean(), "dif_cierre_abs_max_S": dif.max(),
            "pct_dias_cierres_difieren": 100 * (dif > TOLERANCIA_CIERRE).mean(),
            "correlacion_retornos": c["ret_yahoo"].corr(c["ret_bvl_corr"]),
            "vol_anual_yahoo_pct": 100 * c["ret_yahoo"].std() * np.sqrt(DIAS_ANIO),
            "vol_anual_bvl_pct": 100 * c["ret_bvl_corr"].std() * np.sqrt(DIAS_ANIO),
            "pct_ret_cero_yahoo": 100 * (c["ret_yahoo"] == 0).mean(),
            "pct_ret_cero_bvl": 100 * (c["ret_bvl_corr"] == 0).mean(),
        })
    return pd.DataFrame(filas)


def tabla_liquidez(df: pd.DataFrame) -> pd.DataFrame:
    g = df[df["fuente_presente"].isin(["ambas", "solo_bvl"])]
    filas = []
    for t, x in g.groupby("ticker"):
        neg = x[x["cantidad_bvl"].fillna(0) > 0]
        filas.append({"ticker": t, "dias_bvl": len(x), "pct_dias_sin_negociacion": 100 * (1 - len(neg) / len(x)),
                      "monto_mediano_S": neg["monto_efectivo_bvl"].median(), "monto_medio_S": neg["monto_efectivo_bvl"].mean(),
                      "monto_total_millones_S": neg["monto_efectivo_bvl"].sum() / 1e6})
    return pd.DataFrame(filas)


def tabla_var_promedio(resultados: dict) -> pd.DataFrame:
    filas = []
    for serie, (rp, var) in resultados.items():
        for m in METODOS:
            for a in NIVELES:
                k = int(round(a * 100))
                v = var[f"{m}_{k}"]
                v = v[~np.isnan(v)]
                filas.append({"serie": serie, "metodo": NOMBRE_METODO[m], "nivel": f"{k} %", "VaR_medio_pct": 100 * v.mean(),
                              "VaR_medio_S": V0 * v.mean(), "VaR_maximo_pct": 100 * v.max()})
    return pd.DataFrame(filas)


# ================================== FIGURAS ==================================
def figuras(R: pd.DataFrame, diario_p: pd.DataFrame, bt: pd.DataFrame, conc: pd.DataFrame, liq: pd.DataFrame) -> None:
    # 1) VaR al 99 % frente a la pérdida diaria (serie principal)
    f = pd.to_datetime(diario_p["fecha"])
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(f, -diario_p["retorno_cartera"] * 100, color="0.65", lw=0.6, label="Pérdida diaria de la cartera")
    for m in METODOS:
        ax.plot(f, diario_p[f"var_{m}_99"] * 100, lw=1.0, label=f"VaR 99 % {NOMBRE_METODO[m]}")
    e = diario_p["exc_hist_99"].astype(bool)
    ax.scatter(f[e], -diario_p.loc[e, "retorno_cartera"] * 100, s=14, color="black", zorder=5, label="Excepciones (histórico)")
    ax.set_xlabel("Fecha"); ax.set_ylabel("% del valor de la cartera"); ax.legend(fontsize=7, ncol=3)
    guardar_figura(fig, "fig_01_var99_vs_perdidas.png")

    # 2) Tasa de excepciones observada frente a la esperada
    fig, axs = plt.subplots(1, 2, figsize=(10, 4))
    for ax, nivel in zip(axs, ("95 %", "99 %")):
        s = bt[bt["nivel"] == nivel]
        etiquetas = [f"{r.serie}\n{r.metodo}" for r in s.itertuples()]
        ax.bar(range(len(s)), s["tasa_observada_pct"])
        ax.axhline(s["tasa_esperada_pct"].iloc[0], color="black", ls="--", label="Tasa esperada")
        ax.set_xticks(range(len(s))); ax.set_xticklabels(etiquetas, fontsize=6)
        ax.set_title(f"Nivel {nivel}"); ax.set_ylabel("% de días con excepción"); ax.legend(fontsize=7)
    guardar_figura(fig, "fig_02_excepciones_por_metodo.png")

    # 3) Correlaciones de la serie principal
    C = R.corr()
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    im = ax.imshow(C.to_numpy(), vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(C))); ax.set_xticklabels(C.columns, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(C))); ax.set_yticklabels(C.index, fontsize=8)
    for i in range(len(C)):
        for j in range(len(C)):
            ax.text(j, i, f"{C.iat[i, j]:.2f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax, shrink=0.8)
    guardar_figura(fig, "fig_03_correlaciones.png")

    # 4) Liquidez: monto efectivo mediano negociado (BVL)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(liq["ticker"], liq["monto_mediano_S"] / 1e3)
    ax.set_xlabel("Monto efectivo mediano diario (miles de S/), días con negociación"); ax.invert_yaxis()
    guardar_figura(fig, "fig_04_liquidez_monto_efectivo.png")

    # 5) Calidad: retornos en cero Yahoo frente a BVL
    fig, ax = plt.subplots(figsize=(8, 4))
    x = np.arange(len(conc))
    ax.bar(x - 0.2, conc["pct_ret_cero_yahoo"], 0.4, label="Yahoo")
    ax.bar(x + 0.2, conc["pct_ret_cero_bvl"], 0.4, label="BVL (corregido)")
    ax.set_xticks(x); ax.set_xticklabels(conc["ticker"], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("% de días con retorno cero"); ax.legend()
    guardar_figura(fig, "fig_05_retornos_cero_yahoo_vs_bvl.png")


# ================================== PRINCIPAL ================================
def main() -> int:
    log("=== INICIO 04_analisis ===")
    log(f"Entorno: Python {platform.python_version()} | pandas {pd.__version__} | numpy {np.__version__} | scipy {scipy_version} | matplotlib {matplotlib.__version__}")
    log(f"Parámetros: SEMILLA={SEMILLA} VENTANA={VENTANA} N_SIM={N_SIM} NIVELES={NIVELES} V0={V0:,} retorno={TIPO_RETORNO}")
    if not RUTA_PROC.exists():
        raise FileNotFoundError(f"No existe {RUTA_PROC}. Corre antes 03_limpieza_datos.py")
    df = pd.read_csv(RUTA_PROC)
    log(f"Datos procesados leídos: filas={len(df):,} | columnas={len(df.columns)}")

    R_bvl = retornos_bvl(df)
    R_yah = retornos_yahoo(df, R_bvl.index)
    n = R_bvl.shape[1]
    w = np.full(n, 1.0 / n)                       # pesos iguales
    log(f"Cartera: {list(R_bvl.columns)} | pesos iguales 1/{n}")

    resultados, bts, diarios = {}, [], {}
    for nombre, R in (("BVL (principal)", R_bvl), ("Yahoo (contraste)", R_yah)):
        rp, var = calcular_var(R, w)
        resultados[nombre] = (rp, var)
        bt, diario = backtesting(nombre, R.index, rp, var)
        bts.append(bt)
        diarios[nombre] = diario
        guardar_tabla(diario, f"var_diario_{nombre.split()[0].lower()}_{CODIGO}.csv")
    bt = pd.concat(bts, ignore_index=True)

    guardar_tabla(tabla_descriptivos(R_bvl, w), "tabla_01_descriptivos.csv")
    guardar_tabla(R_bvl.corr().reset_index().rename(columns={"index": "ticker"}), "tabla_02_correlaciones.csv")
    conc = tabla_concordancia(df)
    guardar_tabla(conc, "tabla_03_concordancia_yahoo_bvl.csv")
    liq = tabla_liquidez(df)
    guardar_tabla(liq, "tabla_04_liquidez_bvl.csv")
    guardar_tabla(tabla_var_promedio(resultados), "tabla_05_var_promedio.csv")
    guardar_tabla(bt, "tabla_06_backtesting.csv")
    figuras(R_bvl, diarios["BVL (principal)"], bt, conc, liq)

    for r in bt.itertuples():
        log(f"Backtesting | {r.serie} | {r.metodo} {r.nivel} | días={r.dias_evaluados} | excepciones={r.excepciones} "
            f"({r.tasa_observada_pct:.2f} % vs {r.tasa_esperada_pct:.1f} %) | Kupiec p={r.kupiec_p:.3f}")
    log("=== FIN 04_analisis ===")
    return 0


if __name__ == "__main__":
    codigo_salida = main()
    if "ipykernel" not in sys.modules:   # en Colab/Jupyter sys.exit() muestra un aviso inofensivo
        sys.exit(codigo_salida)

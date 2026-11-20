
# VaR de un portafolio de acciones peruanas (Unidad II, Finanzas I)

**Nombres y apellidos:** Yuliana Orihuela Lazo
**Código de matrícula:** 2024200514G
**Curso:** Finanzas I (055D), Universidad Nacional del Centro del Perú (UNCP), 2026-II
**Tema del temario:** Valor en riesgo (VaR) de un portafolio de acciones peruanas - N°70
**Repositorio:** (https://github.com/YulianaOrihuelaLazo/FINANZAS-I-UNIDAD-II-)

## Qué hace este proyecto

Construye una base de datos propia de 8 acciones peruanas (diaria, 2015-2025) a partir de dos fuentes, estima el VaR paramétrico, histórico y por simulación Monte Carlo a 95 % y 99 %, y evalúa su desempeño con backtesting (Kupiec, Christoffersen y zona de Basilea). Todo el flujo se ejecuta con cuatro scripts, y las tablas y figuras salen únicamente de `04_analisis.py`.

## Fuentes de datos y endpoints

| Fuente | Vía | Endpoint | Fecha de extracción |
|---|---|---|---|
| Yahoo Finance | API (librería `yfinance`) | `https://query1.finance.yahoo.com/v8/finance/chart/{ticker}` | 2026-11-14 |
| Bolsa de Valores de Lima (BVL) | Descarga programática (JSON por emisor y año) | `https://dataondemand.bvl.com.pe/v1/issuers/stock?name={NEMONICO}&startDate=AAAA-MM-DD&endDate=AAAA-MM-DD` | 2026-11-19 |

- **Ventana de extracción:** `FECHA_INICIO = 2015-01-01`, `FECHA_CORTE = 2025-12-31` (inclusive), declaradas en `01_extraccion_api.py` y `02_scraping_web.py`.
- **Cartera (8 emisores, nemónico BVL; en Yahoo se agrega `.LM`):** VOLCABC1, FERREYC1, ALICORC1, CPACASC1, UNACEMC1, MINSURI1, LUSURC1, BACKUSI1. Todos cotizan en soles.
- **Scraping ético:** solo información pública, sin datos personales, pausa de 1 segundo entre solicitudes, User-Agent identificable con contacto, sin eludir bloqueos. Detalle en `incidencias_fuente.md`.
- **Claves:** no se requiere ninguna clave de API. Ver `.env.example`.

## Orden de ejecución

```
python codigo/01_extraccion_api.py      # API de Yahoo Finance -> datos_crudos/
python codigo/02_scraping_web.py        # BVL (descarga programática) -> datos_crudos/
python codigo/03_limpieza_datos.py      # limpieza, unión y retornos -> datos_procesados/
python codigo/04_analisis.py            # VaR, backtesting, tablas y figuras -> salidas/
```

Cada script registra su ejecución (fecha, hora, parámetros, versiones, códigos HTTP y hashes) en `log_ejecucion.txt`.

## Entorno

- **Python:** 3.13.18 (Google Colab)
- **Librerías:** yfinance 0.2.66, requests 2.32.4, pandas 2.2.3, numpy 2.4.6, scipy 1.16.3, matplotlib 3.10.0
- **Instalación:** `pip install -r requirements.txt`
- **Semilla de la simulación Monte Carlo:** 514 (cuatro últimos dígitos de la matrícula), `N_SIM = 10000`.

## Estructura del repositorio

| Carpeta o archivo | Contenido |
|---|---|
| `codigo/` | Los cuatro scripts (`01_extraccion_api.py`, `02_scraping_web.py`, `03_limpieza_datos.py`, `04_analisis.py`) |
| `datos_crudos/` | Datos tal como salen de cada fuente, sin editar (CSV de Yahoo por emisor, JSON de la BVL por emisor y año, tabla cruda unificada de la BVL y metadatos de extracción) |
| `datos_procesados/` | `datos_procesados_2024200514G.csv`, `hash_sha256_2024200514G.txt` y `resumen_calidad_2024200514G.csv` |
| `salidas/` | Tablas (`tabla_01` a `tabla_06`), VaR diario y figuras (`fig_01` a `fig_05`) generadas por `04_analisis.py` |
| `log_ejecucion.txt` | Registro de todas las ejecuciones |
| `diccionario_variables.md` | Definición de cada variable, unidad, fuente y equivalencia nemónico BVL ↔ ticker Yahoo |
| `incidencias_fuente.md` | Acceso a la BVL, robots.txt, términos de uso y diferencias entre fuentes |
| `requirements.txt`, `.env.example` | Dependencias y variable de entorno opcional |

## Archivo procesado y verificación de integridad

- **Archivo:** `datos_procesados/datos_procesados_2024200514G.csv` (22,685 filas, 18 columnas; llave `ticker` + `fecha`).
- **Hash SHA-256:** `3848825afadacfe629227c7ae9aa1a34359a5ce3eeb6f6de117ad17d1edae2da`
- **Cómo verificarlo:**

```
sha256sum datos_procesados/datos_procesados_2024200514G.csv
```

## Decisiones metodológicas principales

- **Cartera:** pesos iguales (1/8), valor de referencia de 1 000 000 de soles solo para expresar el VaR en soles.
- **Serie principal:** BVL (retorno contra el "cierre anterior corregido" de la propia BVL). Yahoo (cierre ajustado) se usa como contraste, en las fechas que tienen ambas fuentes.
- **VaR:** horizonte de 1 día, ventana móvil de 250 días que termina en el día anterior, niveles de 95 % y 99 %.
- **Días sin negociación en la BVL:** retorno 0. Cierres de la BVL en 0 con negociación: se reconstruyen con el cierre anterior corregido de la sesión siguiente y quedan marcados en `cierre_bvl_reconstruido`.
- **Limitaciones declaradas:** Yahoo y la BVL difieren en el calendario (feriados de Perú y de EE. UU.); algunos emisores tienen muchos días sin negociación; el cierre anterior corregido de la BVL se aparta del último cierre en un grupo de días que no se explica solo por dividendos.

## Cómo citar las fuentes

- Yahoo Finance. (2026). *Cotizaciones históricas diarias, acciones listadas en la BVL (.LM)* [Base de datos]. Consultado el 14 de noviembre de 2026. https://query1.finance.yahoo.com/v8/finance/chart/
- Bolsa de Valores de Lima. (2026). *Cotizaciones históricas por emisor* [Base de datos]. Consultado el 19 de noviembre de 2026. https://dataondemand.bvl.com.pe/v1/issuers/stock

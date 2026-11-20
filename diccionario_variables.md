# Diccionario de variables

**Autora:** Yuliana Orihuela Lazo · **Matrícula:** 2024200514G · **Curso:** Finanzas I (055D), UNCP, 2026-II
**Tema 70 (Unidad II):** Valor en riesgo (VaR) de un portafolio de acciones peruanas
**Archivo descrito:** `datos_procesados/datos_procesados_2024200514G.csv` (generado por `codigo/03_limpieza_datos.py`)
**Frecuencia:** diaria · **Cobertura:** 2015-01-01 a 2025-12-31 · **Llave:** `ticker` + `fecha` (única, sin duplicados)
**Moneda:** soles (S/) en todas las variables de precio y monto.

## Fuentes

| Fuente | Vía | Endpoint | Fecha de extracción | Crudos |
|---|---|---|---|---|
| Yahoo Finance | API (librería `yfinance`) | `https://query1.finance.yahoo.com/v8/finance/chart/{ticker}` (`interval=1d`, eventos de dividendos y splits) | 2026-11-14 | `datos_crudos/api_yahoo_{ticker}_2024200514G.csv` |
| Bolsa de Valores de Lima (BVL) | Descarga programática (`requests`, JSON por emisor y año) | `https://dataondemand.bvl.com.pe/v1/issuers/stock?name={NEMONICO}&startDate=AAAA-MM-DD&endDate=AAAA-MM-DD` | 2026-11-19 (misma salida que el 2026-11-14) | `datos_crudos/bvl_json_por_anio/` (JSON originales) y `datos_crudos/bvl_cotizaciones_crudo_2024200514G.csv` (tabla cruda unificada) |

Los crudos se conservan sin editar. El tratamiento (tipos, nombres, unión, retornos) ocurre solo en `03_limpieza_datos.py`.

## Cartera: equivalencia nemónico BVL ↔ ticker Yahoo

En `datos_procesados` la columna `ticker` usa el nemónico de la BVL (sin sufijo). Yahoo Finance lo identifica agregando `.LM`.

| `ticker` (nemónico BVL) | Ticker Yahoo | Emisor | Sector |
|---|---|---|---|
| VOLCABC1 | VOLCABC1.LM | Volcan Compañía Minera (clase B) | Minería |
| FERREYC1 | FERREYC1.LM | Ferreycorp | Industria/Servicios |
| ALICORC1 | ALICORC1.LM | Alicorp | Consumo |
| CPACASC1 | CPACASC1.LM | Cementos Pacasmayo | Construcción |
| UNACEMC1 | UNACEMC1.LM | UNACEM | Construcción |
| MINSURI1 | MINSURI1.LM | Minsur | Minería |
| LUSURC1 | LUSURC1.LM | Luz del Sur | Energía |
| BACKUSI1 | BACKUSI1.LM | Unión de Cervecerías Backus | Consumo |

## Variables del archivo procesado (18 columnas)

| N.º | Variable | Definición | Unidad / tipo | Origen |
|---|---|---|---|---|
| 1 | `ticker` | Nemónico BVL del emisor, sin `.LM`. Parte de la llave. | texto | Ambas |
| 2 | `fecha` | Fecha de cotización, formato AAAA-MM-DD (sin hora ni zona horaria). Parte de la llave. | fecha | Ambas |
| 3 | `cierre_yahoo` | Precio de cierre sin ajustar (`Close`). Valores ≤ 0 pasan a vacío. | S/ | Yahoo, API |
| 4 | `cierre_ajustado_yahoo` | Precio de cierre ajustado por dividendos y splits (`Adj Close`). Valores ≤ 0 pasan a vacío. | S/ | Yahoo, API |
| 5 | `volumen_yahoo` | Volumen negociado en el día (`Volume`). | acciones | Yahoo, API |
| 6 | `dividendo_yahoo` | Dividendo por acción de la fecha ex-dividendo (`Dividends`); Yahoo lo entrega como texto con moneda y el 03 extrae solo el número. | S/ por acción | Yahoo, API |
| 7 | `cierre_bvl` | Precio de cierre de la BVL (`close`). Si es ≤ 0 sin negociación queda vacío; si es ≤ 0 con negociación se reconstruye (ver `cierre_bvl_reconstruido`). | S/ | BVL |
| 8 | `cantidad_bvl` | Cantidad de acciones negociadas (`quantityNegotiated`). | acciones | BVL |
| 9 | `monto_efectivo_bvl` | Monto efectivo negociado (`solAmountNegotiated`). | S/ | BVL |
| 10 | `ret_yahoo` | Retorno logarítmico diario con `cierre_ajustado_yahoo`, entre observaciones consecutivas con precio válido. Derivada. | log (adimensional) | Derivada de Yahoo |
| 11 | `ret_bvl` | Retorno logarítmico con `cierre_bvl` (sin ajustar), entre cierres válidos consecutivos. Derivada. | log (adimensional) | Derivada de BVL |
| 12 | `sin_volumen_yahoo` | Verdadero si `volumen_yahoo` es 0; vacío si no hay dato de Yahoo ese día. | booleano | Derivada de Yahoo |
| 13 | `sin_negociacion_bvl` | Verdadero si `cantidad_bvl` es 0 o falta; vacío si no hay fila de la BVL ese día. | booleano | Derivada de BVL |
| 14 | `dif_cierre` | `cierre_yahoo` menos `cierre_bvl`. Derivada. | S/ | Derivada de ambas |
| 15 | `fuente_presente` | Procedencia de la fila tras la unión externa: `ambas`, `solo_yahoo` o `solo_bvl`. | texto | Derivada |
| 16 | `cierre_anterior_bvl` | "Cierre anterior corregido" que publica la BVL (`yesterdayClose`). Valores ≤ 0 pasan a vacío. | S/ | BVL |
| 17 | `ret_bvl_corr` | Retorno logarítmico `log(cierre_bvl / cierre_anterior_bvl)`: contra el cierre anterior corregido de la propia BVL. Serie principal del análisis. Derivada. | log (adimensional) | Derivada de BVL |
| 18 | `cierre_bvl_reconstruido` | Verdadero si `cierre_bvl` venía en 0 pese a haber negociación y se recuperó del `cierre_anterior_bvl` de la sesión siguiente. | booleano | Derivada de BVL |

## Notas de tratamiento (declaradas en el artículo)

- **Unión externa por `ticker` + `fecha`:** no se pierde ninguna fecha de ninguna fuente. Yahoo y la BVL no coinciden en feriados (hay fechas de una sola fuente), por eso existe `fuente_presente`.
- **Días sin negociación:** no se elimina ninguna fila; se marcan con `sin_volumen_yahoo` y `sin_negociacion_bvl`.
- **Cierres de la BVL en 0 con negociación:** se reconstruyen solo con el cierre anterior corregido de la sesión siguiente, y se marcan con `cierre_bvl_reconstruido`. No se arrastra ningún precio.
- **Retornos:** logarítmicos; en `04_analisis.py` se pasan a simples para agregarlos en la cartera (pesos iguales 1/8).
- **Cierre ajustado y BVL:** Yahoo ajusta por dividendos; la BVL se usa sin ajustar, por lo que `ret_bvl` puede mostrar saltos en fechas ex-dividendo.
- **Alcance de este diccionario:** describe las columnas del archivo procesado. Los archivos crudos conservan todas las columnas originales de cada fuente.

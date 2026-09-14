#!/usr/bin/env python3
"""
Actualiza cotizaciones.csv con los precios de la BMV desde Yahoo Finance.

Corre dentro de GitHub Actions: al no haber navegador no existe el problema de
CORS y tampoco hace falta ninguna llave de API.

Tres protecciones que importan:
  1. Reintenta cada lote antes de darlo por perdido.
  2. Conserva los precios anteriores de las emisoras que Yahoo no devolvió, en
     lugar de borrarlas del archivo.
  3. Se niega a escribir si la cobertura queda por debajo del mínimo, para que
     una respuesta incompleta no arruine un archivo que estaba bien.

Salida: cotizaciones.csv con el formato que lee el SSOT de North Star Strategies.
"""
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ARCHIVO = "cotizaciones.csv"
COBERTURA_MINIMA = 0.60          # no se publica por debajo del 60% de las emisoras
INTENTOS = 3
CABECERAS = {"User-Agent": "Mozilla/5.0 (compatible; NorthStarSSOT/1.0)"}
SPARK = "https://query1.finance.yahoo.com/v7/finance/spark?symbols={}&range=1d&interval=1d"

# ticker en el SSOT -> símbolo en Yahoo Finance
SIMBOLOS = {
    "AC": "AC.MX", "AMXB": "AMXB.MX", "ASURB": "ASURB.MX", "BBAJIOO": "BBAJIOO.MX",
    "BIMBOA": "BIMBOA.MX", "CEMEXCPO": "CEMEXCPO.MX", "CHDRAUIB": "CHDRAUIB.MX",
    "FEMSAUBD": "FEMSAUBD.MX", "GAPB": "GAPB.MX", "GCARSOA1": "GCARSOA1.MX",
    "GENTERA": "GENTERA.MX", "GFNORTEO": "GFNORTEO.MX", "GMEXICOB": "GMEXICOB.MX",
    "GRUMAB": "GRUMAB.MX", "KIMBERA": "KIMBERA.MX", "KOFUBL": "KOFUBL.MX",
    "MEGACPO": "MEGACPO.MX", "OMAB": "OMAB.MX", "PINFRA": "PINFRA.MX", "Q": "Q.MX",
    "RA": "RA.MX", "SIGMAFA": "SIGMAFA.MX", "TLEVISACPO": "TLEVISACPO.MX",
    "VESTA": "VESTA.MX", "WALMEX": "WALMEX.MX",
    "LIVEPOLC1": "LIVEPOLC-1.MX", "ALSEA": "ALSEA.MX", "LACOMERUBC": "LACOMERUBC.MX",
    "CUERVO": "CUERVO.MX", "GFINBURO": "GFINBURO.MX", "BOLSAA": "BOLSAA.MX",
    "LABB": "LABB.MX", "VOLARA": "VOLARA.MX", "ORBIA": "ORBIA.MX", "ALPEKA": "ALPEKA.MX",
    "GCC": "GCC.MX", "PEOLES": "PE&OLES.MX", "MEXTRAC": "MEXTRAC09.MX",
}


def aviso(texto):
    print(texto, file=sys.stderr)


def lotes(items, n=18):
    """Yahoo rechaza con 400 cuando se le piden más de veinte símbolos."""
    for i in range(0, len(items), n):
        yield items[i:i + n]


def consultar(simbolos_yahoo):
    url = SPARK.format(urllib.parse.quote(",".join(simbolos_yahoo), safe=""))
    ultimo_error = None
    for intento in range(1, INTENTOS + 1):
        try:
            req = urllib.request.Request(url, headers=CABECERAS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)["spark"]["result"]
        except Exception as e:                      # red, 429, 5xx, JSON incompleto
            ultimo_error = e
            if intento < INTENTOS:
                espera = intento * 4
                aviso(f"intento {intento} falló ({e}); reintentando en {espera}s")
                time.sleep(espera)
    raise RuntimeError(f"agotados {INTENTOS} intentos: {ultimo_error}")


def leer_previo():
    """Lo que ya estaba publicado, para no perder emisoras si Yahoo falla."""
    if not os.path.exists(ARCHIVO):
        return {}
    try:
        with open(ARCHIVO, newline="", encoding="utf-8") as f:
            return {
                fila["simbolo"]: fila
                for fila in csv.DictReader(f)
                if fila.get("simbolo")
            }
    except Exception as e:
        aviso(f"no se pudo leer el archivo previo ({e}); se parte de cero")
        return {}


def main():
    inverso = {v: k for k, v in SIMBOLOS.items()}
    previo = leer_previo()
    frescos, fallidos = {}, []

    for lote in lotes(list(SIMBOLOS.values())):
        try:
            resultados = consultar(lote)
        except Exception as e:
            fallidos.append(f"{', '.join(lote)} -> {e}")
            continue
        for r in resultados:
            meta = (r.get("response") or [{}])[0].get("meta", {})
            ticker = inverso.get(meta.get("symbol"))
            precio = meta.get("regularMarketPrice")
            if not ticker or not precio:
                continue
            anterior = meta.get("previousClose") or meta.get("chartPreviousClose")
            if not anterior and ticker in previo:
                anterior = previo[ticker].get("precio")     # el cierre de la corrida pasada
            ts = meta.get("regularMarketTime")
            frescos[ticker] = {
                "simbolo": ticker,
                "precio": f"{float(precio):.4f}",
                "anterior": f"{float(anterior):.4f}" if anterior else "",
                "fecha_hora": datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else "",
            }

    cobertura = len(frescos) / len(SIMBOLOS)
    if cobertura < COBERTURA_MINIMA:
        aviso(f"Cobertura insuficiente: {len(frescos)} de {len(SIMBOLOS)} "
              f"({cobertura:.0%}, mínimo {COBERTURA_MINIMA:.0%}). No se sobrescribe nada.")
        for f in fallidos:
            aviso(f)
        return 1

    # Las emisoras que no respondieron conservan su última cotización conocida.
    salida = dict(previo)
    salida.update(frescos)
    conservadas = [t for t in salida if t not in frescos]

    with open(ARCHIVO, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["simbolo", "precio", "anterior", "fecha_hora"],
                           lineterminator="\n")
        w.writeheader()
        for ticker in sorted(salida):
            fila = salida[ticker]
            w.writerow({k: fila.get(k, "") for k in w.fieldnames})

    cdmx = datetime.now(timezone(timedelta(hours=-6)))
    print(f"{len(frescos)} de {len(SIMBOLOS)} precios frescos "
          f"({cobertura:.0%}) · {cdmx:%d/%m/%Y %H:%M} hora de Ciudad de México")
    if conservadas:
        print(f"Sin respuesta, se conservó su último precio: {', '.join(sorted(conservadas))}")
    for f in fallidos:
        aviso("lote fallido: " + f)
    return 0


if __name__ == "__main__":
    sys.exit(main())

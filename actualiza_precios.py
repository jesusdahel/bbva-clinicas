#!/usr/bin/env python3
"""
Actualiza cotizaciones.csv con los precios de la BMV desde Yahoo Finance.
Se ejecuta en GitHub Actions: no hay navegador, así que no hay problema de CORS
y tampoco hace falta ninguna llave de API.

Salida: cotizaciones.csv con el formato que lee el SSOT de North Star Strategies.
"""
import json, urllib.request, urllib.parse, csv, sys
from datetime import datetime, timezone, timedelta

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
SPARK = "https://query1.finance.yahoo.com/v7/finance/spark?symbols={}&range=1d&interval=1d"
CABECERAS = {"User-Agent": "Mozilla/5.0 (compatible; NorthStarSSOT/1.0)"}


def lotes(items, n=18):
    """Yahoo rechaza más de ~20 símbolos por llamada."""
    for i in range(0, len(items), n):
        yield items[i:i + n]


def consultar(simbolos_yahoo):
    url = SPARK.format(urllib.parse.quote(",".join(simbolos_yahoo), safe=""))
    req = urllib.request.Request(url, headers=CABECERAS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["spark"]["result"]


def main():
    inverso = {v: k for k, v in SIMBOLOS.items()}
    filas, faltantes = [], []
    for lote in lotes(list(SIMBOLOS.values())):
        try:
            for r in consultar(lote):
                meta = (r.get("response") or [{}])[0].get("meta", {})
                ticker = inverso.get(meta.get("symbol"))
                precio = meta.get("regularMarketPrice")
                anterior = meta.get("previousClose") or meta.get("chartPreviousClose")
                if ticker and precio:
                    ts = meta.get("regularMarketTime")
                    marca = datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else ""
                    filas.append([ticker, round(float(precio), 4),
                                  round(float(anterior), 4) if anterior else "", marca])
        except Exception as e:
            faltantes.append(f"{lote}: {e}")

    if not filas:
        print("No se recibió ningún precio. No se sobrescribe el archivo.", file=sys.stderr)
        for f in faltantes:
            print(f, file=sys.stderr)
        return 1

    filas.sort(key=lambda x: x[0])
    with open("cotizaciones.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["simbolo", "precio", "anterior", "fecha_hora"])
        w.writerows(filas)

    cdmx = datetime.now(timezone(timedelta(hours=-6)))
    print(f"{len(filas)} de {len(SIMBOLOS)} precios escritos · {cdmx:%d/%m/%Y %H:%M} hora de Ciudad de México")
    for f in faltantes:
        print("aviso:", f, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""CLI: python -m ratium revisar archivo.zip --rfc XAXX010101000 [--lista-69b ruta.csv] [--salida carpeta]
         python -m ratium actualizar-69b [--destino ruta.csv]"""
import argparse
import csv
import collections
import pathlib
import urllib.request

from . import validaciones, zip_sat

URL_69B = 'http://omawww.sat.gob.mx/cifras_sat/Documents/Listado_Completo_69-B.csv'
LISTA_DEFAULT = pathlib.Path(__file__).resolve().parent.parent / 'datos' / 'lista_69b.csv'

COLUMNAS_CFDI = ['uuid', 'tipo', 'fecha', 'serie', 'folio', 'emisor_rfc', 'emisor_nombre', 'receptor_rfc', 'receptor_nombre',
                 'uso_cfdi', 'forma_pago', 'metodo_pago', 'moneda', 'tipo_cambio', 'subtotal', 'descuento', 'traslados',
                 'retenciones', 'total', 'version']


def revisar(args):
    cfdis, metadata, errores = zip_sat.leer_zip(args.zip)
    lista = zip_sat.leer_69b(args.lista_69b) if pathlib.Path(args.lista_69b).exists() else {}
    if not lista:
        print('⚠️  Sin lista 69-B: corre "python -m ratium actualizar-69b" para revisar EFOS')
    alertas = validaciones.revisar(cfdis, args.rfc, metadata, lista)

    salida = pathlib.Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    with open(salida / 'cfdis.csv', 'w', newline='', encoding='utf-8-sig') as f:  # utf-8-sig: Excel abre bien los acentos
        w = csv.DictWriter(f, COLUMNAS_CFDI, extrasaction='ignore')
        w.writeheader()
        w.writerows(sorted(cfdis.values(), key=lambda c: c['fecha'] or ''))
    with open(salida / 'alertas.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, ['nivel', 'regla', 'uuid', 'fecha', 'emisor_rfc', 'emisor_nombre', 'receptor_rfc', 'total', 'mensaje'])
        w.writeheader()
        w.writerows(alertas)

    print(f'{len(cfdis)} CFDI leídos, {len(metadata)} renglones de metadata, {len(errores)} archivos con error')
    for nombre, error in errores:
        print(f'  ✗ {nombre}: {error}')
    for (nivel, regla), n in sorted(collections.Counter((a['nivel'], a['regla']) for a in alertas).items()):
        print(f'  {nivel} {regla}: {n}')
    print(f'Reportes en {salida}/cfdis.csv y {salida}/alertas.csv')


def actualizar_69b(args):
    destino = pathlib.Path(args.destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix('.tmp')
    urllib.request.urlretrieve(URL_69B, tmp)
    n = len(zip_sat.leer_69b(tmp))  # valida antes de reemplazar la lista buena
    tmp.replace(destino)
    print(f'Lista 69-B actualizada: {n} RFC en {destino}')


def main():
    p = argparse.ArgumentParser(prog='ratium')
    sub = p.add_subparsers(required=True)
    r = sub.add_parser('revisar', help='Revisa un ZIP del SAT')
    r.add_argument('zip')
    r.add_argument('--rfc', required=True, help='RFC del cliente del contador')
    r.add_argument('--lista-69b', default=str(LISTA_DEFAULT))
    r.add_argument('--salida', default='reporte')
    r.set_defaults(func=revisar)
    a = sub.add_parser('actualizar-69b', help='Descarga la lista 69-B vigente del SAT')
    a.add_argument('--destino', default=str(LISTA_DEFAULT))
    a.set_defaults(func=actualizar_69b)
    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()

"""CLI: python -m ratium revisar emitidos.zip recibidos.zip [metadata.txt...] --rfc XAXX010101000 [--lista-69b ruta.csv] [--salida carpeta]
         python -m ratium conciliar estado_cuenta.pdf emitidos.zip recibidos.zip [metadata.txt...] --rfc XAXX010101000 [--salida carpeta]
         python -m ratium actualizar-69b [--destino ruta.csv]
         python -m ratium corpus [CLAVES...]"""
import argparse
import csv
import collections
from decimal import Decimal
import pathlib
import urllib.request

from . import banco, conciliacion, corpus, validaciones, zip_sat

URL_69B = 'http://omawww.sat.gob.mx/cifras_sat/Documents/Listado_Completo_69-B.csv'
LISTA_DEFAULT = pathlib.Path(__file__).resolve().parent.parent / 'datos' / 'lista_69b.csv'

COLUMNAS_CFDI = ['uuid', 'tipo', 'fecha', 'serie', 'folio', 'emisor_rfc', 'emisor_nombre', 'receptor_rfc', 'receptor_nombre',
                 'uso_cfdi', 'forma_pago', 'metodo_pago', 'moneda', 'tipo_cambio', 'subtotal', 'descuento', 'traslados',
                 'retenciones', 'total', 'version']


def leer_archivos(rutas):
    """Varios ZIP del SAT (emitidos, recibidos) y TXT de metadata sueltos → (cfdis, metadata, errores)."""
    cfdis, metadata, errores = {}, {}, []
    for ruta in rutas:
        if ruta.lower().endswith(('.txt', '.csv')):
            metadata.update(zip_sat.leer_metadata(zip_sat._texto(pathlib.Path(ruta).read_bytes())))
            continue
        c, m, e = zip_sat.leer_zip(ruta)
        for uuid, cfdi in c.items():
            cfdis.setdefault(uuid, cfdi)
        metadata.update(m)
        errores += e
    return cfdis, metadata, errores


def revisar(args):
    cfdis, metadata, errores = leer_archivos(args.archivos)
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


def conciliar(args):
    movimientos, resumen = banco.leer_bbva(banco.texto_pdf(args.estado_cuenta))
    cfdis, metadata, errores = leer_archivos(args.archivos)
    vigentes = [c for u, c in cfdis.items() if metadata.get(u, {}).get('estatus') != '0']
    filas, pendientes = conciliacion.conciliar(movimientos, vigentes, args.rfc)

    salida = pathlib.Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    with open(salida / 'conciliacion.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, ['fecha', 'codigo', 'descripcion', 'cargo', 'abono', 'estado', 'regla', 'diferencia', 'contraparte', 'uuids'])
        w.writeheader()
        w.writerows(filas)
    with open(salida / 'cfdi_sin_banco.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, ['lado', 'fecha', 'importe', 'rfc', 'nombre', 'tipo', 'uuid'])
        w.writeheader()
        for e in sorted(pendientes, key=lambda e: (e['lado'], e['fecha'])):
            c = e['cfdi']
            w.writerow({'lado': e['lado'], 'fecha': e['fecha'][:10], 'importe': e['importe'], 'rfc': e['rfc'], 'tipo': c['tipo'], 'uuid': c['uuid'],
                        'nombre': c['emisor_nombre'] if e['lado'] == 'cargo' else c['receptor_nombre']})

    print(f"{len(movimientos)} movimientos (cuadran con el banco: {resumen['n_cargos']} cargos ${resumen['total_cargos']:,}, "
          f"{resumen['n_abonos']} abonos ${resumen['total_abonos']:,}); {len(vigentes)} CFDI vigentes, {len(errores)} archivos con error")
    for lado in ('cargo', 'abono'):
        mias = [f for f in filas if f[lado]]
        print(f'  {lado}s:')
        for estado in ('conciliado', 'revisar', 'sin_cfdi'):
            grupo = [f for f in mias if f['estado'] == estado]
            print(f"    {estado:<11}{len(grupo):>4}  ${sum((f[lado] for f in grupo), Decimal('0')):>16,}")
    print(f'  CFDI que deberían estar en el banco y no aparecen: {len(pendientes)}')
    print(f'Reportes en {salida}/conciliacion.csv y {salida}/cfdi_sin_banco.csv')


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
    r.add_argument('archivos', nargs='+', help='ZIP del SAT y TXT de metadata')
    r.add_argument('--rfc', required=True, help='RFC del cliente del contador')
    r.add_argument('--lista-69b', default=str(LISTA_DEFAULT))
    r.add_argument('--salida', default='reporte')
    r.set_defaults(func=revisar)
    k = sub.add_parser('conciliar', help='Cruza el estado de cuenta (PDF BBVA) con los CFDI')
    k.add_argument('estado_cuenta')
    k.add_argument('archivos', nargs='+', help='ZIP del SAT y TXT de metadata')
    k.add_argument('--rfc', required=True, help='RFC del cliente del contador')
    k.add_argument('--salida', default='reporte')
    k.set_defaults(func=conciliar)
    a = sub.add_parser('actualizar-69b', help='Descarga la lista 69-B vigente del SAT')
    a.add_argument('--destino', default=str(LISTA_DEFAULT))
    a.set_defaults(func=actualizar_69b)
    c = sub.add_parser('corpus', help='Baja y parte leyes, reglamentos, RMF y criterios fiscales')
    c.add_argument('claves', nargs='*', help='solo estas (ej. LISR RMF)')
    c.set_defaults(func=lambda a: corpus.construir(a.claves))
    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()

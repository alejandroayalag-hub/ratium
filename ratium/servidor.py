"""App web de RATIUM: python -m ratium web [--host 0.0.0.0] [--puerto 3016]

Solo stdlib. No guarda nada en disco: los archivos se procesan en memoria y el resultado
regresa al navegador (los CSV se arman ahí). Fuera de localhost exige RATIUM_CLAVE (HTTP Basic).
"""
import base64
import email.parser
import email.policy
import hmac
import io
import json
import mimetypes
import os
import pathlib
import tempfile
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import banco, conciliacion, validaciones, zip_sat

WEB = pathlib.Path(__file__).resolve().parent / 'web'
LISTA_69B = pathlib.Path(__file__).resolve().parent.parent / 'datos' / 'lista_69b.csv'
MAX_SUBIDA = 500 * 1024 * 1024
COLUMNAS_CFDI = ['uuid', 'tipo', 'fecha', 'serie', 'folio', 'emisor_rfc', 'emisor_nombre', 'receptor_rfc', 'receptor_nombre',
                 'uso_cfdi', 'forma_pago', 'metodo_pago', 'moneda', 'subtotal', 'traslados', 'retenciones', 'total']


def procesar(rfc, archivos):
    """archivos: [(nombre, bytes)]. Regresa el dict que consume la página."""
    rfc = rfc.strip().upper()
    pdfs = [(n, d) for n, d in archivos if n.lower().endswith('.pdf')]
    sat = [(n, io.BytesIO(d)) for n, d in archivos if not n.lower().endswith('.pdf')]
    if not sat:
        raise ValueError('Sube al menos un ZIP del SAT')
    cfdis, metadata, errores = zip_sat.leer_varios(sat)
    lista = zip_sat.leer_69b(LISTA_69B) if LISTA_69B.exists() else {}
    alertas = validaciones.revisar(cfdis, rfc, metadata, lista)
    salida = {
        'rfc': rfc,
        'cfdis': [{k: c.get(k) for k in COLUMNAS_CFDI} for c in sorted(cfdis.values(), key=lambda c: c['fecha'] or '')],
        'alertas': alertas, 'errores': errores, 'n_metadata': len(metadata), 'lista_69b': bool(lista), 'bancos': [],
    }
    vigentes = [c for u, c in cfdis.items() if metadata.get(u, {}).get('estatus') != '0']
    for nombre, datos in pdfs:
        with tempfile.NamedTemporaryFile(suffix='.pdf') as tmp:  # pdftotext necesita archivo; se borra al salir
            tmp.write(datos)
            tmp.flush()
            movimientos, resumen = banco.leer_bbva(banco.texto_pdf(tmp.name))
        filas, pendientes = conciliacion.conciliar(movimientos, vigentes, rfc)
        salida['bancos'].append({'archivo': nombre, 'resumen': resumen, 'filas': filas,
                                 'sin_factura': conciliacion.pagos_sin_factura(filas, pendientes, vigentes, rfc), 'pendientes': [
            {'lado': e['lado'], 'fecha': e['fecha'][:10], 'importe': e['importe'], 'rfc': e['rfc'], 'tipo': e['cfdi']['tipo'],
             'uuid': e['cfdi']['uuid'], 'nombre': e['cfdi']['emisor_nombre' if e['lado'] == 'cargo' else 'receptor_nombre']}
            for e in sorted(pendientes, key=lambda e: (e['lado'], e['fecha']))]})
    return salida


def _json(obj):
    return json.dumps(obj, ensure_ascii=False, default=lambda o: str(o) if isinstance(o, Decimal) else repr(o)).encode()


class Manejador(BaseHTTPRequestHandler):
    server_version = 'RATIUM'

    def _autorizado(self):
        clave = os.environ.get('RATIUM_CLAVE')
        if not clave:
            return True
        enviado = self.headers.get('Authorization', '')
        esperado = 'Basic ' + base64.b64encode(f'ratium:{clave}'.encode()).decode()
        if hmac.compare_digest(enviado, esperado):
            return True
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="RATIUM"')
        self.end_headers()
        return False

    def _enviar(self, codigo, cuerpo, tipo):
        self.send_response(codigo)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(cuerpo)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        if not self._autorizado():
            return
        ruta = (WEB / (self.path.split('?')[0].lstrip('/') or 'index.html')).resolve()
        if WEB not in ruta.parents or not ruta.is_file():  # nada fuera de web/
            return self._enviar(404, b'No existe', 'text/plain; charset=utf-8')
        tipo = mimetypes.guess_type(ruta.name)[0] or 'application/octet-stream'
        self._enviar(200, ruta.read_bytes(), tipo + ('; charset=utf-8' if tipo.startswith('text/') else ''))

    def do_POST(self):
        if not self._autorizado():
            return
        if self.path != '/api/revision':
            return self._enviar(404, b'{}', 'application/json')
        largo = int(self.headers.get('Content-Length') or 0)
        if largo > MAX_SUBIDA:
            return self._enviar(413, _json({'error': 'Los archivos pasan de 500 MB'}), 'application/json')
        cuerpo = self.rfile.read(largo)
        msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
            b'Content-Type: ' + self.headers.get('Content-Type', '').encode() + b'\r\n\r\n' + cuerpo)
        rfc, archivos = '', []
        for parte in msg.iter_parts() if msg.is_multipart() else []:
            campo = parte.get_param('name', header='content-disposition')
            if campo == 'rfc':
                rfc = parte.get_payload(decode=True).decode()
            elif campo == 'archivos' and parte.get_filename():
                archivos.append((parte.get_filename(), parte.get_payload(decode=True)))
        try:
            if len(rfc.strip()) not in (12, 13):
                raise ValueError('RFC inválido: debe tener 12 (moral) o 13 (física) caracteres')
            self._enviar(200, _json(procesar(rfc, archivos)), 'application/json')
        except Exception as e:  # el contador ve el motivo; el detalle técnico se queda en la terminal
            self.log_error('revisión falló: %r', e)
            self._enviar(400, _json({'error': str(e) or e.__class__.__name__}), 'application/json')


def servir(host='127.0.0.1', puerto=3016):
    if host not in ('127.0.0.1', 'localhost') and not os.environ.get('RATIUM_CLAVE'):
        raise SystemExit('Para abrir RATIUM a la red define RATIUM_CLAVE (usuario "ratium")')
    print(f'RATIUM en http://{host}:{puerto}')
    ThreadingHTTPServer((host, puerto), Manejador).serve_forever()

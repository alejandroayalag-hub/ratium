"""Lectura de CFDI 3.3 y 4.0 (Anexo 20 del SAT) a un dict plano.

Solo stdlib. El dinero va siempre en Decimal: nunca float.
"""
from decimal import Decimal
import xml.etree.ElementTree as ET

NS_CFDI = {'3.3': 'http://www.sat.gob.mx/cfd/3', '4.0': 'http://www.sat.gob.mx/cfd/4'}
NS_TFD = 'http://www.sat.gob.mx/TimbreFiscalDigital'
NS_PAGOS = ('http://www.sat.gob.mx/Pagos20', 'http://www.sat.gob.mx/Pagos')  # 2.0 (CFDI 4.0), 1.0 (CFDI 3.3)
NS_IMPLOCAL = 'http://www.sat.gob.mx/implocal'
NS_NOMINA = 'http://www.sat.gob.mx/nomina12'

TIPOS = {'I': 'ingreso', 'E': 'egreso', 'P': 'pago', 'N': 'nomina', 'T': 'traslado'}


class CfdiInvalido(ValueError):
    pass


def _d(valor):
    return Decimal(valor) if valor not in (None, '') else Decimal('0')


def leer(xml_bytes):
    # ponytail: expat de Python >= 3.12 trae protección contra "billion laughs" y etree no resuelve entidades externas
    try:
        raiz = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise CfdiInvalido(f'XML mal formado: {e}') from None

    version = raiz.get('Version') or raiz.get('version')
    ns = NS_CFDI.get(version)
    if ns is None or raiz.tag != f'{{{ns}}}Comprobante':
        raise CfdiInvalido(f'No es un CFDI 3.3/4.0 (raíz {raiz.tag}, versión {version})')

    def hijo(nodo, nombre):
        return nodo.find(f'{{{ns}}}{nombre}')

    emisor = hijo(raiz, 'Emisor')
    receptor = hijo(raiz, 'Receptor')
    timbre = raiz.find(f'.//{{{NS_TFD}}}TimbreFiscalDigital')
    if emisor is None or receptor is None or timbre is None:
        raise CfdiInvalido('Falta Emisor, Receptor o TimbreFiscalDigital')

    conceptos = []
    for c in raiz.iterfind(f'{{{ns}}}Conceptos/{{{ns}}}Concepto'):
        conceptos.append({
            'clave_prod_serv': c.get('ClaveProdServ'),
            'descripcion': c.get('Descripcion'),
            'cantidad': _d(c.get('Cantidad')),
            'valor_unitario': _d(c.get('ValorUnitario')),
            'importe': _d(c.get('Importe')),
            'descuento': _d(c.get('Descuento')),
            'traslados': sum((_d(t.get('Importe')) for t in c.iterfind(f'{{{ns}}}Impuestos/{{{ns}}}Traslados/{{{ns}}}Traslado')), Decimal('0')),
            'retenciones': sum((_d(r.get('Importe')) for r in c.iterfind(f'{{{ns}}}Impuestos/{{{ns}}}Retenciones/{{{ns}}}Retencion')), Decimal('0')),
        })

    # Totales de impuestos: los del nodo global; si no viene (p.ej. tasa exenta), se suman los de conceptos
    imp = hijo(raiz, 'Impuestos')
    if imp is not None and (imp.get('TotalImpuestosTrasladados') or imp.get('TotalImpuestosRetenidos')):
        traslados = _d(imp.get('TotalImpuestosTrasladados'))
        retenciones = _d(imp.get('TotalImpuestosRetenidos'))
    else:
        traslados = sum((c['traslados'] for c in conceptos), Decimal('0'))
        retenciones = sum((c['retenciones'] for c in conceptos), Decimal('0'))

    implocal = raiz.find(f'.//{{{NS_IMPLOCAL}}}ImpuestosLocales')
    pagos = []
    for ns_p in NS_PAGOS:
        for p in raiz.iterfind(f'.//{{{ns_p}}}Pago'):
            for doc in p.iterfind(f'{{{ns_p}}}DoctoRelacionado'):
                pagos.append({
                    'uuid': (doc.get('IdDocumento') or '').upper(),
                    'fecha_pago': p.get('FechaPago'),
                    'forma_pago': p.get('FormaDePagoP'),
                    'parcialidad': doc.get('NumParcialidad'),
                    'saldo_anterior': _d(doc.get('ImpSaldoAnt')),
                    'pagado': _d(doc.get('ImpPagado')),
                    'saldo_insoluto': _d(doc.get('ImpSaldoInsoluto')),
                })

    return {
        'uuid': timbre.get('UUID', '').upper(),
        'version': version,
        'tipo': TIPOS.get(raiz.get('TipoDeComprobante'), raiz.get('TipoDeComprobante')),
        'serie': raiz.get('Serie', ''),
        'folio': raiz.get('Folio', ''),
        'fecha': raiz.get('Fecha'),
        'fecha_timbrado': timbre.get('FechaTimbrado'),
        'forma_pago': raiz.get('FormaPago', ''),
        'metodo_pago': raiz.get('MetodoPago', ''),
        'moneda': raiz.get('Moneda', 'MXN'),
        'tipo_cambio': _d(raiz.get('TipoCambio') or '1'),
        'subtotal': _d(raiz.get('SubTotal')),
        'descuento': _d(raiz.get('Descuento')),
        'total': _d(raiz.get('Total')),
        'traslados': traslados,
        'retenciones': retenciones,
        'traslados_locales': _d(implocal.get('TotaldeTraslados')) if implocal is not None else Decimal('0'),
        'retenciones_locales': _d(implocal.get('TotaldeRetenciones')) if implocal is not None else Decimal('0'),
        'emisor_rfc': emisor.get('Rfc', '').upper(),
        'emisor_nombre': emisor.get('Nombre', ''),
        'emisor_regimen': emisor.get('RegimenFiscal', ''),
        'receptor_rfc': receptor.get('Rfc', '').upper(),
        'receptor_nombre': receptor.get('Nombre', ''),
        'uso_cfdi': receptor.get('UsoCFDI', ''),
        'conceptos': conceptos,
        'relacionados': [r.get('UUID', '').upper() for r in raiz.iterfind(f'{{{ns}}}CfdiRelacionados/{{{ns}}}CfdiRelacionado')],
        'pagos': pagos,
        'es_nomina': raiz.find(f'.//{{{NS_NOMINA}}}Nomina') is not None,
    }

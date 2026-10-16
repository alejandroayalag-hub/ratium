"""Conciliación bancaria: movimientos del estado de cuenta ↔ CFDI del mes.

Determinista, sin IA. Orden de reglas (de más a menos segura):
  1. 'rfc'     el banco trae el RFC (pagos BNET "RFC:XXX") y uno o varios CFDI de ese RFC suman el importe exacto
  2. 'nombre'  el beneficiario/ordenante del SPEI coincide con el nombre del CFDI y suman el importe exacto
  1b.'rfc ±$1' mismo RFC, un solo CFDI con diferencia de centavos → revisar
  1c.'rfc (varias transferencias)' un complemento de pago que suma varias transferencias del mismo RFC
  3. 'monto'   un solo CFDI pendiente con ese importe exacto a ±5 días → hay que revisarlo
Lo que no concilia se etiqueta por código de movimiento (comisiones, ventas TPV, efectivo…).
"""
from datetime import date
from decimal import Decimal
import itertools
import re
import unicodedata

# Formas de pago que no pasan por el banco: efectivo, dación, condonación, compensación, por definir
FORMAS_SIN_BANCO = {'01', '12', '15', '17', '99'}
RE_RFC = re.compile(r'RFC:\s*([A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3})')
MAX_COMBINACION = 4  # ponytail: hasta 4 facturas por pago; subir si Diana ve pagos que liquidan más
MAX_CANDIDATOS = 25  # por RFC/nombre se prueban solo los 25 de fecha más cercana (25C4 ≈ 12k combinaciones)
DIAS_MONTO = 5
TOLERANCIA = Decimal('1.00')
DIAS_VARIOS = 10  # transferencias que un mismo complemento de pago puede agrupar

CATEGORIAS = {
    'V42': 'Venta con terminal (débito)', 'V45': 'Venta con terminal (crédito)', 'K54': 'Venta con terminal (AMEX)',
    'V43': 'Comisión terminal', 'V46': 'Comisión terminal', 'K64': 'Comisión terminal',
    'V44': 'IVA comisión terminal', 'V47': 'IVA comisión terminal', 'K65': 'IVA comisión terminal',
    'S39': 'Comisión banca internet', 'S40': 'IVA comisión banca internet',
    'AA7': 'Depósito en efectivo (practicaja)', 'C02': 'Depósito en efectivo',
    'X01': 'Pago IMSS/Infonavit', 'Y45': 'Compensación del banco', 'T22': 'SPEI devuelto',
}
STOP = {'PAGO', 'CUENTA', 'TERCERO', 'SPEI', 'ENVIADO', 'RECIBIDO', 'REF', 'RFC', 'IVA', 'BNET', 'TRANSF', 'FACTURA', 'SA', 'DE', 'CV', 'S', 'A', 'C', 'V', 'RL', 'SAB', 'SAPI', 'SC', 'LA', 'EL', 'LOS', 'LAS', 'Y', 'DEL'}


def _palabras(texto):
    t = unicodedata.normalize('NFKD', texto.upper().replace("'", '')).encode('ascii', 'ignore').decode()  # HUGO'S = HUGOS
    return {p for p in re.findall(r'[A-Z0-9]+', t) if p not in STOP and len(p) > 1}


def _dias(a, b):
    return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)


def esperados(cfdis, rfc):
    """CFDI que deberían verse en el banco → lista de {lado, rfc, nombre, fecha, importe, cfdi}.
    lado 'cargo' = le pagamos a un proveedor (recibidos); 'abono' = nos pagó un cliente (emitidos)."""
    salida = []
    for c in cfdis:
        if c['emisor_rfc'] == rfc:
            lado, contra_rfc, contra_nombre = 'abono', c['receptor_rfc'], c['receptor_nombre']
        elif c['receptor_rfc'] == rfc:
            lado, contra_rfc, contra_nombre = 'cargo', c['emisor_rfc'], c['emisor_nombre']
        else:
            continue
        base = {'lado': lado, 'rfc': contra_rfc, 'palabras': _palabras(contra_nombre), 'cfdi': c}
        if c['tipo'] == 'pago':
            # cada nodo Pago es una transferencia distinta (puede haber varios con fechas distintas en un CFDI)
            por_pago = {}
            for p in c['pagos']:
                if p['forma_pago'] not in FORMAS_SIN_BANCO:
                    clave = (p['fecha_pago'] or c['fecha'], p['forma_pago'])
                    por_pago[clave] = por_pago.get(clave, Decimal('0')) + p['pagado']
            salida += [{**base, 'fecha': f, 'importe': imp} for (f, _), imp in por_pago.items()]
        elif c['tipo'] == 'egreso' and c['metodo_pago'] == 'PUE':
            # nota de crédito: resta de lo que se paga, aunque su forma sea compensación (17) o por definir (99)
            salida.append({**base, 'fecha': c['fecha'], 'importe': -c['total'] * c['tipo_cambio']})
        elif c['tipo'] == 'ingreso' and c['metodo_pago'] == 'PUE' and c['forma_pago'] not in FORMAS_SIN_BANCO:
            salida.append({**base, 'fecha': c['fecha'], 'importe': c['total'] * c['tipo_cambio']})
        # PPD se concilia por su complemento de pago; nómina va por dispersión
    return salida


def _combinacion(candidatos, importe, fecha):
    """Primera combinación (de menos a más CFDI) que suma exacto el importe."""
    candidatos = sorted(candidatos, key=lambda e: _dias(e['fecha'], fecha))[:MAX_CANDIDATOS]
    for n in range(1, MAX_COMBINACION + 1):
        for combo in itertools.combinations(candidatos, n):
            if sum(e['importe'] for e in combo) == importe:
                return list(combo)
    return None


def conciliar(movimientos, cfdis, rfc):
    """Regresa (filas por movimiento, CFDI esperados que no aparecieron en el banco)."""
    pendientes = esperados(cfdis, rfc)
    # el nombre del propio cliente sale en muchas referencias ("Transf a SUPER PACK"): no cuenta para el parecido
    propias = set().union(*(_palabras(c['emisor_nombre']) for c in cfdis if c['emisor_rfc'] == rfc),
                          *(_palabras(c['receptor_nombre']) for c in cfdis if c['receptor_rfc'] == rfc))
    filas = []
    for m in movimientos:
        lado = _lado(m)
        importe = m['cargo'] or m['abono']
        mios = [e for e in pendientes if e['lado'] == lado]
        encontrados, regla = None, ''

        r = RE_RFC.search(m['descripcion'])
        if r:
            del_rfc = [e for e in mios if e['rfc'] == r.group(1)]
            encontrados, regla = _combinacion(del_rfc, importe, m['fecha']), 'rfc'
            if not encontrados:  # mismo RFC, diferencia de centavos (error de captura del proveedor o del banco)
                cerca = [e for e in del_rfc if abs(e['importe'] - importe) <= TOLERANCIA]
                encontrados, regla = (cerca if len(cerca) == 1 else None), f'rfc ±${TOLERANCIA}'
        if not encontrados:
            # nombre: el beneficiario/ordenante viene en el detalle (SPEI) o en la descripción (pago referenciado);
            # piden 2 palabras en común, o la única si el nombre del CFDI es de una palabra (BOFRYMEX)
            nombre = _palabras(m['descripcion']) - propias
            parecidos = [e for e in mios if e['palabras'] and len(nombre & e['palabras']) >= min(2, len(e['palabras']))]
            encontrados, regla = (_combinacion(parecidos, importe, m['fecha']) if parecidos else None), 'nombre'
        if not encontrados:
            mismos = [e for e in mios if e['importe'] == importe and _dias(e['fecha'], m['fecha']) <= DIAS_MONTO]
            encontrados, regla = (mismos if len(mismos) == 1 else None), 'monto'

        if encontrados:
            for e in encontrados:
                pendientes.remove(e)
            estado = 'conciliado' if regla in ('rfc', 'nombre') else 'revisar'
        else:
            estado, regla = 'sin_cfdi', CATEGORIAS.get(m['codigo'], '')
        filas.append(_fila(m, estado, regla, encontrados or []))

    # 2a pasada: un solo CFDI de pago que cubre varias transferencias del mismo RFC
    for e in list(pendientes):
        sueltos = [i for i, f in enumerate(filas) if f['estado'] == 'sin_cfdi' and _lado(f) == e['lado']
                   and (r := RE_RFC.search(f['descripcion'])) and r.group(1) == e['rfc'] and _dias(f['fecha'], e['fecha']) <= DIAS_VARIOS]
        for n in range(2, MAX_COMBINACION + 1):
            combo = next((c for c in itertools.combinations(sueltos, n)
                          if sum(filas[i]['cargo'] or filas[i]['abono'] for i in c) == e['importe']), None)
            if combo:
                for i in combo:
                    filas[i] = _fila(filas[i], 'conciliado', 'rfc (varias transferencias)', [e], diferencia='')
                pendientes.remove(e)
                break
    return filas, [e for e in pendientes if e['importe'] > 0]  # una nota de crédito sola no se espera en el banco


def _lado(m):
    return 'cargo' if m['cargo'] else 'abono'


def _fila(m, estado, regla, encontrados, diferencia=None):
    importe = m['cargo'] or m['abono']
    nombre = 'emisor_nombre' if _lado(m) == 'cargo' else 'receptor_nombre'
    return {**m, 'estado': estado, 'regla': regla,
            'diferencia': diferencia if diferencia is not None else (importe - sum(e['importe'] for e in encontrados) if encontrados else ''),
            'uuids': ' '.join(e['cfdi']['uuid'] for e in encontrados),
            'contraparte': ', '.join(sorted({f"{e['rfc']} {e['cfdi'][nombre]}" for e in encontrados}))}

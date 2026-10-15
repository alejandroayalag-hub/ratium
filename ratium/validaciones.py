"""Reglas de revisión. Cada regla es determinista (sin IA) y regresa alertas.

Supuestos pendientes de confirmar con Diana: ver docs/preguntas-diana.md (#7 IVA PPD, #15 EFOS, #16 deducibilidad).
"""
from decimal import Decimal

GRAVE, REVISAR = '🔴', '🟡'
TOLERANCIA = Decimal('0.01')  # redondeo permitido entre suma de impuestos y total
LIMITE_EFECTIVO = Decimal('2000')  # LISR art. 27 fr. III


def _alerta(nivel, regla, c, mensaje):
    return {'nivel': nivel, 'regla': regla, 'uuid': c['uuid'], 'fecha': c['fecha'],
            'emisor_rfc': c['emisor_rfc'], 'emisor_nombre': c['emisor_nombre'],
            'receptor_rfc': c['receptor_rfc'], 'total': c['total'], 'mensaje': mensaje}


def revisar(cfdis, rfc_cliente, metadata=None, lista_69b=None):
    rfc_cliente = rfc_cliente.upper()
    metadata = metadata or {}
    lista_69b = lista_69b or {}
    alertas = []

    pagado = {}  # uuid de factura PPD -> suma de ImpPagado en los complementos cargados
    for c in cfdis.values():
        if metadata.get(c['uuid'], {}).get('estatus') == '0':
            continue  # un complemento de pago cancelado no paga nada
        for p in c['pagos']:
            pagado[p['uuid']] = pagado.get(p['uuid'], Decimal('0')) + p['pagado']

    for c in cfdis.values():
        recibido = c['receptor_rfc'] == rfc_cliente
        emitido = c['emisor_rfc'] == rfc_cliente

        if not (recibido or emitido):
            alertas.append(_alerta(GRAVE, 'no_es_del_cliente', c, f'Ni emisor ni receptor es {rfc_cliente}'))
            continue

        meta = metadata.get(c['uuid'])
        if meta and meta.get('estatus') == '0':
            alertas.append(_alerta(GRAVE, 'cancelado', c, f"CFDI cancelado ante el SAT ({meta.get('fechacancelacion') or 'sin fecha'})"))
            continue

        if recibido:
            # ponytail: con varios oficios gana el más grave; criterio por confirmar con Diana (pregunta #19)
            situaciones = lista_69b.get(c['emisor_rfc'], [])
            otras = f" (aparece {len(situaciones)} veces: {', '.join(situaciones)})" if len(situaciones) > 1 else ''
            if 'Definitivo' in situaciones:
                alertas.append(_alerta(GRAVE, 'efos_69b', c, f'Emisor en lista 69-B DEFINITIVA (operaciones inexistentes): no deducible{otras}'))
            elif 'Presunto' in situaciones:
                alertas.append(_alerta(REVISAR, 'efos_69b', c, f'Emisor en lista 69-B como PRESUNTO: documentar materialidad{otras}'))

        if c['tipo'] in ('ingreso', 'egreso'):
            calculado = (c['subtotal'] - c['descuento'] + c['traslados'] - c['retenciones']
                         + c['traslados_locales'] - c['retenciones_locales'])
            if abs(calculado - c['total']) > TOLERANCIA:
                alertas.append(_alerta(REVISAR, 'totales_no_cuadran', c,
                                       f"Subtotal - descuento + impuestos = {calculado}, pero el total dice {c['total']}"))

        if c['tipo'] == 'ingreso' and c['metodo_pago'] == 'PPD':
            pago = pagado.get(c['uuid'], Decimal('0'))
            if pago == 0:
                alertas.append(_alerta(REVISAR, 'ppd_sin_complemento', c, 'Factura PPD sin complemento de pago en los XML cargados'))
            elif c['total'] - pago > TOLERANCIA:
                alertas.append(_alerta(REVISAR, 'ppd_saldo_pendiente', c, f"Pagado {pago} de {c['total']}: saldo {c['total'] - pago}"))

        if recibido and c['tipo'] == 'ingreso':
            if c['forma_pago'] == '01' and c['total'] > LIMITE_EFECTIVO:
                alertas.append(_alerta(REVISAR, 'efectivo_mayor_2000', c, 'Pagado en efectivo por más de $2,000: no deducible (LISR 27-III)'))
            if c['uso_cfdi'] in ('S01', 'P01'):
                alertas.append(_alerta(REVISAR, 'uso_cfdi', c, f"Uso CFDI {c['uso_cfdi']}: sin efectos fiscales / por definir"))

    # UUID en la metadata sin su XML: el contador no descargó algún comprobante vigente
    for uuid, meta in metadata.items():
        if uuid not in cfdis and meta.get('estatus') == '1':
            alertas.append({'nivel': REVISAR, 'regla': 'falta_xml', 'uuid': uuid, 'fecha': meta.get('fechaemision', ''),
                            'emisor_rfc': meta.get('rfcemisor', ''), 'emisor_nombre': meta.get('nombreemisor', ''),
                            'receptor_rfc': meta.get('rfcreceptor', ''), 'total': meta.get('monto', ''),
                            'mensaje': 'Vigente en la metadata del SAT pero no viene su XML'})

    alertas.sort(key=lambda a: (a['nivel'] != GRAVE, a['regla'], a['fecha'] or ''))
    return alertas

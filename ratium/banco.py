"""Estado de cuenta bancario (PDF) → movimientos.

Por ahora solo BBVA (Maestra Pyme). Usa `pdftotext -layout` (poppler-utils) porque stdlib no lee PDF.
Cargo vs abono se decide por la columna en que cae el importe, y al final se cuadra contra los
totales que imprime el propio banco: si no cuadra, se truena en vez de entregar una conciliación mala.
"""
from decimal import Decimal
import re
import subprocess

MESES = {m: i for i, m in enumerate('ENE FEB MAR ABR MAY JUN JUL AGO SEP OCT NOV DIC'.split(), 1)}
RE_MOV = re.compile(r'^\s*(\d{2})/([A-Z]{3})\s+\d{2}/[A-Z]{3}\s+([A-Z0-9]{3})\s+(.*)$')
RE_IMPORTE = re.compile(r'\d{1,3}(?:,\d{3})*\.\d{2}')
RE_PERIODO = re.compile(r'DEL (\d{2})/(\d{2})/(\d{4}) AL')


class EstadoCuentaInvalido(ValueError):
    pass


def _dec(texto):
    return Decimal(texto.replace(',', ''))


def texto_pdf(ruta):
    return subprocess.run(['pdftotext', '-layout', str(ruta), '-'], capture_output=True, text=True, check=True).stdout


def leer_bbva(texto):
    """Regresa (movimientos, resumen). Cada movimiento: fecha, codigo, descripcion, cargo, abono (Decimal)."""
    m = RE_PERIODO.search(texto)
    if not m or 'BBVA' not in texto:
        raise EstadoCuentaInvalido('No parece un estado de cuenta BBVA')
    anio = int(m.group(3))

    movs, col_cargos, col_abonos, actual = [], None, None, None
    for linea in texto.splitlines():
        if 'Total de Movimientos' in linea:
            break
        if '\f' in linea or linea.startswith('BBVA MEXICO, S.A.'):  # salto de página o pie: no es detalle
            actual = None
            continue
        if 'CARGOS' in linea and 'ABONOS' in linea:  # encabezado de cada página: aquí se miden las columnas
            col_cargos = linea.index('CARGOS') + len('CARGOS')
            col_abonos = linea.index('ABONOS') + len('ABONOS')
            actual = movs[-1] if movs else None  # lo que sigue al encabezado es detalle del último movimiento
            continue
        if col_cargos is None:
            continue
        mm = RE_MOV.match(linea)
        if mm:
            dia, mes, codigo, _ = mm.groups()
            importes = list(RE_IMPORTE.finditer(linea))
            if not importes:
                raise EstadoCuentaInvalido(f'Movimiento sin importe: {linea.strip()}')
            imp = importes[0]
            es_cargo = abs(imp.end() - col_cargos) < abs(imp.end() - col_abonos)
            actual = {
                'fecha': f'{anio}-{MESES[mes]:02d}-{int(dia):02d}',
                'codigo': codigo,
                'descripcion': linea[mm.start(4):imp.start()].strip(),
                'cargo': _dec(imp.group()) if es_cargo else Decimal('0'),
                'abono': Decimal('0') if es_cargo else _dec(imp.group()),
            }
            movs.append(actual)
        elif not linea.strip():
            actual = None  # una línea en blanco cierra el detalle del movimiento
        elif actual is not None:  # detalle: referencia, RFC, beneficiario
            actual['descripcion'] += ' | ' + linea.strip()

    resumen = {}
    for clave, patron in [('total_cargos', r'TOTAL IMPORTE CARGOS\s+([\d,]+\.\d{2})'),
                          ('total_abonos', r'TOTAL IMPORTE ABONOS\s+([\d,]+\.\d{2})'),
                          ('n_cargos', r'TOTAL MOVIMIENTOS CARGOS\s+(\d+)'),
                          ('n_abonos', r'TOTAL MOVIMIENTOS ABONOS\s+(\d+)'),
                          ('saldo_inicial', r'Saldo de Operación Inicial\s+([\d,]+\.\d{2})'),
                          ('saldo_final', r'Saldo Final \(\+\)\s+([\d,]+\.\d{2})')]:
        r = re.search(patron, texto)
        if not r:
            raise EstadoCuentaInvalido(f'No encontré {clave} en el resumen del banco')
        resumen[clave] = _dec(r.group(1)) if '.' in r.group(1) else int(r.group(1))

    cargos = [x['cargo'] for x in movs if x['cargo']]
    abonos = [x['abono'] for x in movs if x['abono']]
    leido = (len(cargos), sum(cargos), len(abonos), sum(abonos))
    esperado = (resumen['n_cargos'], resumen['total_cargos'], resumen['n_abonos'], resumen['total_abonos'])
    if leido != esperado:
        raise EstadoCuentaInvalido(f'No cuadra con el banco: leído {leido}, banco {esperado}')
    return movs, resumen

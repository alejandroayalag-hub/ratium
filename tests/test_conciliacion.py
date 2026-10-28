"""python -m unittest tests.test_conciliacion   (desde ~/ratium)"""
import unittest
from decimal import Decimal as D

from ratium import banco, conciliacion

CLIENTE = 'AAA010101AAA'
H = '  OPER LIQ      COD. DESCRIPCIÓN                  REFERENCIA                                     CARGOS        ABONOS       OPERACIÓN LIQUIDACIÓN'


def estado(movs, n_c, t_c, n_a, t_a):
    return '\n'.join([
        'BBVA', 'Periodo DEL 01/09/2026 AL 30/09/2026', 'Saldo de Operación Inicial 1,000.00', 'Saldo Final (+) 1,000.00', H, *movs,
        'Total de Movimientos',
        f'    TOTAL IMPORTE CARGOS   {t_c}    TOTAL MOVIMIENTOS CARGOS   {n_c}',
        f'    TOTAL IMPORTE ABONOS   {t_a}    TOTAL MOVIMIENTOS ABONOS   {n_a}'])


def mov(dia, cod, desc, importe, abono=False):
    linea = f'{dia}/SEP   {dia}/SEP {cod} {desc}'
    fin = H.index('ABONOS') + 6 if abono else H.index('CARGOS') + 6
    return linea.ljust(fin - len(importe)) + importe


def cfdi(uuid, emisor, receptor, tipo='ingreso', total='0', metodo='PUE', forma='03', fecha='2026-09-02', pagos=(), nombre='PROVEEDOR'):
    return {'uuid': uuid, 'tipo': tipo, 'emisor_rfc': emisor, 'receptor_rfc': receptor, 'emisor_nombre': nombre,
            'receptor_nombre': 'CLIENTE PROPIO' if receptor == CLIENTE else nombre, 'total': D(total), 'tipo_cambio': D('1'),
            'metodo_pago': metodo, 'forma_pago': forma, 'fecha': fecha + 'T10:00:00', 'pagos': list(pagos)}


def pago(fecha, pagado, forma='03'):
    return {'fecha_pago': fecha + 'T12:00:00', 'forma_pago': forma, 'pagado': D(pagado)}


class TestBBVA(unittest.TestCase):
    def test_cargo_abono_por_columna_y_detalle(self):
        texto = estado([mov('01', 'N06', 'PAGO CUENTA DE TERCERO', '1,160.00'),
                        '                RFC:BBB020202BBB IVA:.05 Ref. 1',
                        mov('02', 'T20', 'SPEI RECIBIDOBANAMEX', '500.00', abono=True),
                        '\fEstado de Cuenta', H, '                JUAN PEREZ'],  # detalle tras salto de página
                       1, '1,160.00', 1, '500.00')
        movs, resumen = banco.leer_bbva(texto)
        self.assertEqual([(m['cargo'], m['abono']) for m in movs], [(D('1160.00'), D('0')), (D('0'), D('500.00'))])
        self.assertIn('RFC:BBB020202BBB', movs[0]['descripcion'])
        self.assertTrue(movs[1]['descripcion'].endswith('JUAN PEREZ'))
        self.assertEqual(movs[1]['fecha'], '2026-09-02')

    def test_si_no_cuadra_con_el_banco_truena(self):
        texto = estado([mov('01', 'N06', 'PAGO', '1,160.00')], 1, '1,160.01', 0, '0.00')
        with self.assertRaises(banco.EstadoCuentaInvalido):
            banco.leer_bbva(texto)


class TestConciliar(unittest.TestCase):
    def m(self, fecha, desc, cargo='0', abono='0', codigo='N06'):
        return {'fecha': fecha, 'codigo': codigo, 'descripcion': desc, 'cargo': D(cargo), 'abono': D(abono)}

    def test_rfc_con_nota_de_credito_por_compensacion(self):
        cfdis = [cfdi('F1', 'BBB020202BBB', CLIENTE, total='4978'), cfdi('F2', 'BBB020202BBB', CLIENTE, total='8744'),
                 cfdi('NC', 'BBB020202BBB', CLIENTE, tipo='egreso', total='640', forma='17')]
        filas, pend = conciliacion.conciliar([self.m('2026-09-01', 'PAGO | RFC:BBB020202BBB IVA:.05', cargo='13082')], cfdis, CLIENTE)
        self.assertEqual((filas[0]['estado'], filas[0]['regla']), ('conciliado', 'rfc'))
        self.assertEqual(set(filas[0]['uuids'].split()), {'F1', 'F2', 'NC'})
        self.assertEqual(pend, [])

    def test_complemento_de_pago_con_dos_pagos_y_tolerancia(self):
        cfdis = [cfdi('P1', 'BBB020202BBB', CLIENTE, tipo='pago', pagos=[pago('2026-09-03', '100.00'), pago('2026-09-10', '33805.10')])]
        movs = [self.m('2026-09-03', 'RFC:BBB020202BBB', cargo='100.00'), self.m('2026-09-10', 'RFC:BBB020202BBB', cargo='33805.01')]
        filas, _ = conciliacion.conciliar(movs, cfdis, CLIENTE)
        self.assertEqual([(f['estado'], f['regla']) for f in filas], [('conciliado', 'rfc'), ('revisar', 'rfc ±$1.00')])
        self.assertEqual(filas[1]['diferencia'], D('-0.09'))

    def test_un_complemento_cubre_varias_transferencias(self):
        cfdis = [cfdi('P1', 'BBB020202BBB', CLIENTE, tipo='pago', pagos=[pago('2026-09-23', '48624.60')])]
        movs = [self.m('2026-09-23', 'RFC:BBB020202BBB', cargo='28270.00'), self.m('2026-09-24', 'RFC:BBB020202BBB', cargo='20354.60')]
        filas, pend = conciliacion.conciliar(movs, cfdis, CLIENTE)
        self.assertEqual({f['regla'] for f in filas}, {'rfc (varias transferencias)'})
        self.assertEqual(pend, [])

    def test_nombre_ignora_el_del_cliente_y_efectivo_no_se_espera(self):
        cfdis = [cfdi('A', 'CCC030303CCC', CLIENTE, total='500', nombre="DISTRIBUIDORA HUGO'S SA DE CV"),
                 cfdi('B', 'DDD040404DDD', CLIENTE, total='500', nombre='CLIENTE PROPIO OTRO'),
                 cfdi('E', 'EEE050505EEE', CLIENTE, total='999', forma='01')]
        movs = [self.m('2026-09-02', 'SPEI ENVIADO | CLIENTE PROPIO | DISTRIBUIDORA HUGOS SA DE CV', cargo='500', codigo='T17')]
        filas, pend = conciliacion.conciliar(movs, cfdis, CLIENTE)
        self.assertEqual((filas[0]['regla'], filas[0]['uuids']), ('nombre', 'A'))
        self.assertEqual([e['cfdi']['uuid'] for e in pend], ['B'])  # el de efectivo (E) no se espera en el banco

    def test_nombre_con_diferencia_de_centavos(self):
        cfdis = [cfdi('P1', 'ADU800131T10', CLIENTE, tipo='pago', nombre='ABARROTERA DEL DUERO', pagos=[pago('2026-09-18', '124439.00')])]
        movs = [self.m('2026-09-17', 'ABARROTERA DEL DUERO | CIE:1475797', cargo='124440.00', codigo='P14')]
        filas, pend = conciliacion.conciliar(movs, cfdis, CLIENTE)
        self.assertEqual((filas[0]['estado'], filas[0]['regla'], filas[0]['uuids']), ('revisar', 'nombre ±$1.00', 'P1'))
        self.assertEqual(pend, [])

    def test_pagos_sin_factura_por_proveedor(self):
        cfdis = [cfdi('P1', 'BBB020202BBB', CLIENTE, tipo='pago', nombre='JABON LA CORONA', pagos=[pago('2026-08-30', '50.00')]),
                 cfdi('F1', 'CCC030303CCC', CLIENTE, total='10', nombre='PAPELERIA CISNE', metodo='PPD')]
        movs = [self.m('2026-09-05', 'PAGO | RFC:BBB020202BBB IVA:.05', cargo='700'), self.m('2026-09-06', 'PAGO | RFC:BBB020202BBB', cargo='300'),
                self.m('2026-09-07', 'SPEI ENVIADO BAJIO | 0300926 Ref. 1 | 0003 | PAPELERIA CISNE SA', cargo='99', codigo='T17'),
                self.m('2026-09-08', 'SPEI ENVIADO NUBANK | 0210926PAGO SERVICIOS Ref. 2', cargo='70', codigo='T17'),
                self.m('2026-09-09', 'SAT | REF:04266 CIE:0844985', cargo='12', codigo='P14')]
        filas, pend = conciliacion.conciliar(movs, cfdis, CLIENTE)
        self.assertEqual(filas[-1]['regla'], 'Pago de impuestos SAT')
        panam = self.m('2026-09-02', 'SPEI RECIBIDOSANTANDER | Ref. 1 | 0001 | SERVICIO PAN AMERICANO DE PROTECCION SAD', abono='352500', codigo='T20')
        self.assertEqual(conciliacion.conciliar([panam], [], CLIENTE)[0][0]['regla'], 'Efectivo recolectado (Panamericano)')
        g = conciliacion.pagos_sin_factura(filas, pend, cfdis, CLIENTE)
        self.assertEqual([(x['nombre'], x['pagos'], x['total']) for x in g],
                         [('JABON LA CORONA', 2, D('1000')), ('PAPELERIA CISNE SA', 1, D('99')), ('SPEI ENVIADO NUBANK', 1, D('70'))])
        self.assertEqual([x['accion'].split(':')[0] for x in g],
                         ['Hay 1 CFDI suyo(s) sin cruzar por $50.00', 'Hay facturas suyas en el mes pero ninguna cuadra', 'Ningún CFDI suyo en el mes'])

    def test_sin_cfdi_se_categoriza_por_codigo(self):
        filas, _ = conciliacion.conciliar([self.m('2026-09-01', 'APLI TASA DE DES CREDITO', cargo='264.36', codigo='V46')], [], CLIENTE)
        self.assertEqual((filas[0]['estado'], filas[0]['regla']), ('sin_cfdi', 'Comisión terminal'))


if __name__ == '__main__':
    unittest.main()

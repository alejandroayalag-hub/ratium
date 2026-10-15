"""python -m unittest -v   (desde ~/ratium)"""
import io
import tempfile
import unittest
import zipfile
from decimal import Decimal

from ratium import cfdi, validaciones, zip_sat

CLIENTE = 'AAA010101AAA'
PROV = 'BBB020202BBB'


def factura(uuid, emisor=PROV, receptor=CLIENTE, subtotal='1000.00', iva='160.00', total='1160.00',
            metodo='PUE', forma='03', uso='G03', version='4.0', tipo='I', extra_comp=''):
    ns = 'http://www.sat.gob.mx/cfd/4' if version == '4.0' else 'http://www.sat.gob.mx/cfd/3'
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="{ns}" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
  Version="{version}" Fecha="2026-09-15T10:00:00" SubTotal="{subtotal}" Total="{total}" Moneda="MXN"
  TipoDeComprobante="{tipo}" MetodoPago="{metodo}" FormaPago="{forma}" Serie="A" Folio="1">
  <cfdi:Emisor Rfc="{emisor}" Nombre="Emisor Ñandú SA" RegimenFiscal="601"/>
  <cfdi:Receptor Rfc="{receptor}" Nombre="Receptor" UsoCFDI="{uso}"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="43211500" Cantidad="1" Descripcion="Laptop" ValorUnitario="{subtotal}" Importe="{subtotal}">
      <cfdi:Impuestos><cfdi:Traslados><cfdi:Traslado Base="{subtotal}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{iva}"/></cfdi:Traslados></cfdi:Impuestos>
    </cfdi:Concepto>
  </cfdi:Conceptos>
  <cfdi:Impuestos TotalImpuestosTrasladados="{iva}"/>
  <cfdi:Complemento><tfd:TimbreFiscalDigital Version="1.1" UUID="{uuid}" FechaTimbrado="2026-09-15T10:01:00"/>{extra_comp}</cfdi:Complemento>
</cfdi:Comprobante>'''.encode()


def pago(uuid, uuid_factura, monto):
    comp = f'''<pago20:Pagos xmlns:pago20="http://www.sat.gob.mx/Pagos20" Version="2.0">
      <pago20:Pago FechaPago="2026-09-30T12:00:00" FormaDePagoP="03" MonedaP="MXN" Monto="{monto}">
        <pago20:DoctoRelacionado IdDocumento="{uuid_factura}" NumParcialidad="1" ImpSaldoAnt="1160.00" ImpPagado="{monto}" ImpSaldoInsoluto="0"/>
      </pago20:Pago></pago20:Pagos>'''
    return factura(uuid, subtotal='0', iva='0', total='0', tipo='P', metodo='', forma='', uso='CP01', extra_comp=comp)


def zip_con(archivos):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for nombre, datos in archivos.items():
            z.writestr(nombre, datos)
    buf.seek(0)
    return buf


def reglas(alertas):
    return sorted(a['regla'] for a in alertas)


class TestCfdi(unittest.TestCase):
    def test_lee_40(self):
        c = cfdi.leer(factura('aaaa-1'))
        self.assertEqual(c['uuid'], 'AAAA-1')
        self.assertEqual(c['tipo'], 'ingreso')
        self.assertEqual(c['total'], Decimal('1160.00'))
        self.assertEqual(c['traslados'], Decimal('160.00'))
        self.assertEqual(c['conceptos'][0]['clave_prod_serv'], '43211500')
        self.assertEqual(c['emisor_nombre'], 'Emisor Ñandú SA')

    def test_lee_33(self):
        self.assertEqual(cfdi.leer(factura('B-1', version='3.3'))['version'], '3.3')

    def test_lee_pago(self):
        c = cfdi.leer(pago('P-1', 'F-1', '1160.00'))
        self.assertEqual(c['tipo'], 'pago')
        self.assertEqual(c['pagos'][0]['uuid'], 'F-1')
        self.assertEqual(c['pagos'][0]['pagado'], Decimal('1160.00'))

    def test_rechaza_basura(self):
        with self.assertRaises(cfdi.CfdiInvalido):
            cfdi.leer(b'<html/>')
        with self.assertRaises(cfdi.CfdiInvalido):
            cfdi.leer(b'no es xml')


class TestValidaciones(unittest.TestCase):
    def revisar(self, *xmls, metadata=None, lista=None):
        cfdis = {c['uuid']: c for c in map(cfdi.leer, xmls)}
        return validaciones.revisar(cfdis, CLIENTE, metadata, lista)

    def test_factura_limpia_sin_alertas(self):
        self.assertEqual(self.revisar(factura('F-1')), [])

    def test_no_es_del_cliente(self):
        self.assertEqual(reglas(self.revisar(factura('F-1', receptor='ZZZ999999ZZZ'))), ['no_es_del_cliente'])

    def test_cancelado(self):
        self.assertEqual(reglas(self.revisar(factura('F-1'), metadata={'F-1': {'estatus': '0'}})), ['cancelado'])

    def test_efos(self):
        self.assertEqual(self.revisar(factura('F-1'), lista={PROV: ['Definitivo']})[0]['nivel'], validaciones.GRAVE)
        self.assertEqual(self.revisar(factura('F-1'), lista={PROV: ['Presunto']})[0]['nivel'], validaciones.REVISAR)
        self.assertEqual(self.revisar(factura('F-1'), lista={PROV: ['Desvirtuado']}), [])
        # varios oficios: gana el más grave
        a = self.revisar(factura('F-1'), lista={PROV: ['Definitivo', 'Sentencia Favorable']})
        self.assertEqual(a[0]['nivel'], validaciones.GRAVE)
        self.assertIn('aparece 2 veces', a[0]['mensaje'])

    def test_efos_solo_en_recibidas(self):
        # el cliente emite a un EFOS: no es su gasto, no se marca
        self.assertEqual(self.revisar(factura('F-1', emisor=CLIENTE, receptor=PROV), lista={CLIENTE: ['Definitivo']}), [])

    def test_totales_no_cuadran(self):
        self.assertEqual(reglas(self.revisar(factura('F-1', total='1200.00'))), ['totales_no_cuadran'])
        self.assertEqual(self.revisar(factura('F-1', total='1160.01')), [])  # dentro de tolerancia

    def test_ppd(self):
        self.assertEqual(reglas(self.revisar(factura('F-1', metodo='PPD'))), ['ppd_sin_complemento'])
        self.assertEqual(self.revisar(factura('F-1', metodo='PPD'), pago('P-1', 'F-1', '1160.00')), [])
        self.assertEqual(reglas(self.revisar(factura('F-1', metodo='PPD'), pago('P-1', 'F-1', '500.00'))), ['ppd_saldo_pendiente'])

    def test_pago_cancelado_no_cuenta(self):
        alertas = self.revisar(factura('F-1', metodo='PPD'), pago('P-1', 'F-1', '1160.00'), metadata={'P-1': {'estatus': '0'}})
        self.assertEqual(reglas(alertas), ['cancelado', 'ppd_sin_complemento'])

    def test_no_deducibles(self):
        self.assertEqual(reglas(self.revisar(factura('F-1', forma='01', subtotal='5000', iva='800', total='5800'))), ['efectivo_mayor_2000'])
        self.assertEqual(self.revisar(factura('F-1', forma='01')), [])  # $1,160 en efectivo: permitido
        self.assertEqual(reglas(self.revisar(factura('F-1', uso='S01'))), ['uso_cfdi'])

    def test_efectivo_solo_recibidas(self):
        self.assertEqual(self.revisar(factura('F-1', emisor=CLIENTE, receptor=PROV, forma='01', subtotal='5000', iva='800', total='5800')), [])

    def test_falta_xml(self):
        meta = {'X-9': {'estatus': '1', 'rfcemisor': PROV, 'monto': '50'}}
        self.assertEqual(reglas(self.revisar(factura('F-1'), metadata=meta)), ['falta_xml'])


class TestZip(unittest.TestCase):
    def test_zip_con_metadata_y_anidado(self):
        meta = 'Uuid~RfcEmisor~NombreEmisor~RfcReceptor~NombreReceptor~RfcPac~FechaEmision~FechaCertificacionSat~Monto~EfectoComprobante~Estatus~FechaCancelacion\n' \
               'f-1~BBB020202BBB~X~AAA010101AAA~Y~PAC~2026-09-15~2026-09-15~1160~I~0~2026-09-20\n'
        interno = zip_con({'dentro.xml': factura('F-2')}).getvalue()
        z = zip_con({'a.xml': factura('F-1'), 'rota.xml': b'<x', 'meta.txt': meta.encode(), 'sub.zip': interno})
        cfdis, metadata, errores = zip_sat.leer_zip(z)
        self.assertEqual(sorted(cfdis), ['F-1', 'F-2'])
        self.assertEqual(metadata['F-1']['estatus'], '0')
        self.assertEqual([n for n, _ in errores], ['rota.xml'])

    def test_lista_69b(self):
        contenido = '"Información actualizada al 31 de diciembre",,,\nListado completo,,,\n' \
                    'No,RFC,Nombre del Contribuyente,Situación del contribuyente\n' \
                    '1,BBB020202BBB,ÑANDÚ SA,Definitivo\n2,CCC030303CCC,OTRO,Desvirtuado\n3,BBB020202BBB,ÑANDÚ SA,Sentencia Favorable\n'
        with tempfile.NamedTemporaryFile('w', encoding='latin-1', suffix='.csv', delete=False) as f:
            f.write(contenido)
        self.assertEqual(zip_sat.leer_69b(f.name), {'BBB020202BBB': ['Definitivo', 'Sentencia Favorable'], 'CCC030303CCC': ['Desvirtuado']})


if __name__ == '__main__':
    unittest.main()

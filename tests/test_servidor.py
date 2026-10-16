"""python -m unittest tests.test_servidor   (desde ~/ratium)"""
import io
import json
import unittest
import zipfile

from ratium import servidor
from tests.test_ratium import CLIENTE, factura


class TestProcesar(unittest.TestCase):
    def test_zip_a_json(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('a.xml', factura('11111111-1111-1111-1111-111111111111', forma='01', total='2320.00', subtotal='2000.00', iva='320.00'))
        r = servidor.procesar(CLIENTE.lower(), [('recibidos.zip', buf.getvalue())])
        datos = json.loads(servidor._json(r))  # Decimal → texto, sin perder centavos
        self.assertEqual(datos['rfc'], CLIENTE)
        self.assertEqual(datos['cfdis'][0]['total'], '2320.00')
        self.assertIn('efectivo_mayor_2000', {a['regla'] for a in datos['alertas']})
        self.assertEqual(datos['bancos'], [])

    def test_sin_zip_es_error(self):
        with self.assertRaises(ValueError):
            servidor.procesar(CLIENTE, [('estado.pdf', b'%PDF')])


if __name__ == '__main__':
    unittest.main()

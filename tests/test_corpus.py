"""Separadores del corpus fiscal con textos mínimos que imitan los PDF oficiales."""
import unittest

from ratium import corpus

RMF = """Capítulo 2.1. Disposiciones generales
Cobro de créditos fiscales
2.1.1.

Para los efectos del artículo 4o. del CFF, conforme a la regla
2.1.2.
se envía el documento.
CFF 4o., 17-D
Comprobantes emitidos por residentes en el extranjero sin establecimiento
permanente en México
2.1.2.

Los contribuyentes podrán deducir.
NOTA: Este documento constituye una compilación de las resoluciones publicadas
CFF 29, 29-A
Supuestos de reducción de multas conforme al artículo 74 del
CFF
2.1.3.

Texto final.
Transitorios
Primero. Entra en vigor.
"""

ANEXO = """Contenido
A. Vigentes
1/CFF/N
2/CFF/N
B. Derogados:
2/CFF/N
A.
Vigentes
1/CFF/N

Crédito fiscal. Es firme cuando transcurren los términos.
2/CFF/N

Texto derogado que no debe entrar.
B.
Criterios normativos derogados.
2/CFF/N

Texto derogado que no debe entrar.
"""

LEY = """LEY DEL IMPUESTO DE PRUEBA
Artículo 1. Primer artículo.
Artículo 2o.- Segundo, que cita: Artículo 1. texto citado.
LEY DEL IMPUESTO DE PRUEBA
Artículo 17 Bis.- Tercero.
TRANSITORIOS
Artículo 1. No entra.
"""


class TestCorpus(unittest.TestCase):
    def test_rmf(self):
        reglas = corpus.partir_rmf(RMF)
        self.assertEqual([r[0] for r in reglas], ['2.1.1.', '2.1.2.', '2.1.3.'])  # la referencia partida no es regla
        self.assertEqual(reglas[0][1], 'Cobro de créditos fiscales')
        self.assertEqual(reglas[1][1], 'Comprobantes emitidos por residentes en el extranjero sin establecimiento permanente en México')
        self.assertEqual(reglas[2][1], 'Supuestos de reducción de multas conforme al artículo 74 del CFF')
        self.assertNotIn('NOTA', reglas[1][2])  # pie de página de la compilación
        self.assertNotIn('Supuestos', reglas[1][2])  # el título de la siguiente no es cuerpo
        self.assertEqual(reglas[2][2], 'Texto final.')  # la última termina en Transitorios

    def test_criterios_sin_derogados(self):
        crit = corpus.partir_criterios(ANEXO)
        self.assertEqual([c[0] for c in crit], ['1/CFF/N'])
        self.assertIn('Crédito fiscal', crit[0][2])

    def test_ley(self):
        arts = corpus.partir_ley(LEY, 'Ley del Impuesto de Prueba')
        self.assertEqual([a[0] for a in arts], ['1', '2o', '17 Bis'])
        self.assertNotIn('LEY DEL IMPUESTO', arts[1][1])  # encabezado de página quitado


if __name__ == '__main__':
    unittest.main()

"""Lectura del ZIP que baja el contador del portal del SAT (XML + metadata opcional) y de la lista 69-B."""
import csv
import io
import zipfile

from . import cfdi

MAX_ARCHIVO = 20 * 1024 * 1024      # un XML real pesa KB; esto frena zip bombs
MAX_TOTAL = 2 * 1024 * 1024 * 1024  # 2 GB descomprimido por ZIP


def _texto(datos):
    try:
        return datos.decode('utf-8-sig')
    except UnicodeDecodeError:
        return datos.decode('latin-1')


def leer_metadata(texto):
    """Metadata del SAT: separada por '~', columnas Uuid, RfcEmisor, ..., Estatus (1 vigente, 0 cancelado)."""
    lineas = [l for l in texto.splitlines() if l.strip()]
    if not lineas:
        return {}
    encabezado = [c.strip().lower() for c in lineas[0].split('~')]
    if 'uuid' not in encabezado:
        return {}
    filas = {}
    for linea in lineas[1:]:
        fila = dict(zip(encabezado, (c.strip() for c in linea.split('~'))))
        if fila.get('uuid'):
            filas[fila['uuid'].upper()] = fila
    return filas


def leer_zip(ruta_o_archivo):
    """Regresa (cfdis, metadata, errores). Los ZIP anidados (el SAT a veces entrega ZIP de ZIPs) se abren también."""
    cfdis, metadata, errores = {}, {}, []
    total = 0

    def procesar(zf, prefijo=''):
        nonlocal total
        for info in zf.infolist():
            if info.is_dir():
                continue
            nombre = prefijo + info.filename
            with zf.open(info) as f:
                datos = f.read(MAX_ARCHIVO + 1)
            if len(datos) > MAX_ARCHIVO:
                errores.append((nombre, 'Archivo demasiado grande, se omitió'))
                continue
            total += len(datos)
            if total > MAX_TOTAL:
                raise ValueError('El ZIP descomprimido excede 2 GB')
            bajo = nombre.lower()
            if bajo.endswith('.zip'):
                procesar(zipfile.ZipFile(io.BytesIO(datos)), nombre + '/')
            elif bajo.endswith('.xml'):
                try:
                    c = cfdi.leer(datos)
                except cfdi.CfdiInvalido as e:
                    errores.append((nombre, str(e)))
                    continue
                cfdis.setdefault(c['uuid'], c)  # duplicados: se queda el primero
            elif bajo.endswith(('.txt', '.csv')):
                metadata.update(leer_metadata(_texto(datos)))

    with zipfile.ZipFile(ruta_o_archivo) as zf:
        procesar(zf)
    return cfdis, metadata, errores


def leer_69b(ruta):
    """CSV oficial del SAT (latin-1, con renglones de preámbulo). Regresa {rfc: [situaciones]}.

    Un RFC puede venir en varios renglones (varios oficios), p.ej. Definitivo + Sentencia Favorable."""
    with open(ruta, encoding='latin-1', newline='') as f:
        lector = csv.reader(f)
        for fila in lector:
            if 'RFC' in fila:
                i_rfc = fila.index('RFC')
                i_sit = next(i for i, c in enumerate(fila) if c.startswith('Situaci'))
                break
        else:
            raise ValueError('No se encontró el encabezado RFC en la lista 69-B')
        lista = {}
        for fila in lector:
            if len(fila) > i_sit and fila[i_rfc].strip():
                lista.setdefault(fila[i_rfc].strip().upper(), []).append(fila[i_sit].strip())
        return lista

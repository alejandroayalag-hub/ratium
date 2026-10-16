"""Corpus fiscal para el RAG: baja leyes, reglamentos, RMF y criterios del SAT y los parte en un .md por documento,
con un encabezado "## <DOC> — <unidad>" por artículo/regla/criterio y la VIGENCIA en cada fragmento,
para que la IA cite la unidad exacta y no conteste con una versión derogada.

Uso: python -m ratium corpus            (todo)
     python -m ratium corpus LISR RMF   (solo esos)
Requiere pdftotext (poppler-utils).
"""
import datetime
import json
import pathlib
import re
import subprocess
import time
import urllib.request

DIR = pathlib.Path(__file__).resolve().parent.parent / 'datos' / 'corpus'
DIP = 'https://www.diputados.gob.mx/LeyesBiblio/'
SAT = 'https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/documentos2026/rmf/'

# ponytail: lista fija; cada año (o cada modificación de la RMF) se actualizan aquí las URL del SAT
FUENTES = [
    # (clave, nombre, url, tipo)
    ('CFF', 'Código Fiscal de la Federación', DIP + 'pdf/CFF.pdf', 'ley'),
    ('LISR', 'Ley del Impuesto sobre la Renta', DIP + 'pdf/LISR.pdf', 'ley'),
    ('LIVA', 'Ley del Impuesto al Valor Agregado', DIP + 'pdf/LIVA.pdf', 'ley'),
    ('LIEPS', 'Ley del Impuesto Especial sobre Producción y Servicios', DIP + 'pdf/LIEPS.pdf', 'ley'),
    ('LIF_2026', 'Ley de Ingresos de la Federación para el Ejercicio Fiscal de 2026', DIP + 'pdf/LIF_2026.pdf', 'ley'),
    ('LSS', 'Ley del Seguro Social', DIP + 'pdf/LSS.pdf', 'ley'),
    ('LIFNVT', 'Ley del Instituto del Fondo Nacional de la Vivienda para los Trabajadores', DIP + 'pdf/LIFNVT.pdf', 'ley'),
    ('LFT', 'Ley Federal del Trabajo', DIP + 'pdf/LFT.pdf', 'ley'),
    ('LFDC', 'Ley Federal de los Derechos del Contribuyente', DIP + 'pdf/LFDC.pdf', 'ley'),
    ('RCFF', 'Reglamento del Código Fiscal de la Federación', DIP + 'regley/Reg_CFF.pdf', 'ley'),
    ('RLISR', 'Reglamento de la Ley del Impuesto sobre la Renta', DIP + 'regley/Reg_LISR_060516.pdf', 'ley'),
    ('RLIVA', 'Reglamento de la Ley del Impuesto al Valor Agregado', DIP + 'regley/Reg_LIVA_250914.pdf', 'ley'),
    ('RLIEPS', 'Reglamento de la Ley del Impuesto Especial sobre Producción y Servicios', DIP + 'regley/Reg_LIEPS.pdf', 'ley'),
    ('RMF', 'Resolución Miscelánea Fiscal para 2026 (compilada con la 1a. RM, DOF 09-07-2026)',
     SAT + 'compiladas/Compilado_Primera_Modificacion_a_la-Resolucion_Miscelanea_Fiscal_para_2026.pdf', 'rmf'),
    ('ANEXO7', 'Anexo 7 RMF 2026 — Criterios normativos del SAT', SAT + 'anexos/Anexo_7_RMF2026-09012026.pdf', 'criterios'),
    ('ANEXO3', 'Anexo 3 RMF 2026 — Criterios no vinculativos (prácticas fiscales indebidas)', SAT + 'anexos/Anexo_3_RMF2026-09012026.pdf', 'criterios'),
]

# "Artículo 165.-", "Artículo 2o.", "Artículo 17 Bis.-", "Artículo 153-F Bis.", "Artículo 210-bis.-" al inicio de línea
RE_ART = re.compile(r'^\s*(?:Art[íi]culo|ART[ÍI]CULO)\s+(\d+[o°ºª]?(?:\s*-\s*[A-ZÑ]{1,2}(?![a-zñ]))?'
                    r'(?:[\s.\-]*(?:[Bb]is|[Tt]er|[Qq]u[áa]ter|[Qq]uinquies|[Ss]exies|[Ss]epties|[Oo]cties)\b\s*\d*)?)\s*[.\-–]')
RE_REGLA = re.compile(r'^(\d+\.\d+(?:\.\d+){0,3}\.)$')
RE_CRITERIO = re.compile(r'^(\d+/[A-Z]+(?:/[A-Z]+)?/(?:N|NV|PI))\b\s*(.*)$')  # N normativo, PI práctica indebida, NV no vinculativo
RE_REFORMA = re.compile(r'[ÚU]ltima [Rr]eforma(?: publicada)? DOF\s*(\d{2}[-/]\d{2}[-/]\d{4})')
RE_NUEVA = re.compile(r'Nuev[oa] (?:Ley|Código|Reglamento) DOF\s*(\d{2}[-/]\d{2}[-/]\d{4})')
RUIDO = re.compile(r'^.*(CÁMARA DE DIPUTADOS DEL H\. CONGRESO DE LA UNIÓN|Secretaría General|Secretaría de Servicios Parlamentarios'
                   r'|Última Reforma DOF|Nueva Ley publicada|Nuevo Código publicado|Nuevo Reglamento publicado).*$'
                   # pie de página de las compilaciones del SAT (3 renglones en cada hoja)
                   r'|^NOTA: Este documento constituye una compilación.*$|^de dar a conocer el texto actualizado de la Resolución Miscelánea.*$'
                   r'|^del Contribuyente\. Para sustentar legalmente actos o resoluciones.*$'
                   r'|^\s*(P[áa]gina\s+)?\d+\s+(de|/)\s+\d+\s*$', re.I | re.M)


def texto_pdf(pdf):
    return subprocess.run(['pdftotext', '-enc', 'UTF-8', str(pdf), '-'], check=True, capture_output=True).stdout.decode().replace('\f', '\n')


def partir_ley(texto, nombre):
    """[(num, cuerpo)] por artículo; ignora transitorios y números repetidos (citas textuales dentro de otro artículo)."""
    encabezado = ' '.join(nombre.upper().split()).rstrip('.')
    lineas = [l for l in RUIDO.sub('', texto).split('\n') if ' '.join(l.upper().split()).rstrip('.') != encabezado]
    arts, vistos, actual = [], set(), None
    for l in lineas:
        if re.match(r'^\s*(ART[ÍI]CULOS?\s+)?TRANSITORIOS?:?\s*$', l, re.I):
            break
        m = RE_ART.match(l)
        num = m and ' '.join(m.group(1).split())
        if m and num not in vistos:
            vistos.add(num)
            actual = [num, [l.strip()]]
            arts.append(actual)
        elif actual:
            actual[1].append(l.strip())
    return [(n, ' '.join(' '.join(c).split())) for n, c in arts]


def partir_rmf(texto):
    """[(regla, título, cuerpo)]. La regla real es el número solo en su renglón seguido de un renglón vacío;
    el título son los 1-2 renglones anteriores. Se descartan referencias partidas ("...conforme a la regla\n2.1.18.")."""
    L = [l.rstrip() for l in RUIDO.sub('', texto).split('\n')]
    # fin de cada regla: renglón de fundamentos ("CFF 29, LISR 27, RMF 2.7.1.21.") o encabezado de título/capítulo/sección
    leyes = r'(CFF|RCFF|LISR|RLISR|LIVA|RLIVA|LIEPS|RLIEPS|LFD|LIF|LSS|LFT|LCF|RMF|RGCE|LFDC|LIGIE|LA|LISH|LGOAAC|LFPCA|LIC|LMV|LGSM)'
    corte = re.compile(rf'^(Título|Capítulo|Sección)\s+\d|^{leyes}\s+\S|,\s*{leyes}\s+\d|\bDOF (el )?\d')
    inicios, vistos = [], set()
    for i, l in enumerate(L):
        m = RE_REGLA.match(l.strip())
        if not m or i + 1 >= len(L) or L[i + 1].strip():
            continue
        previo = next((L[j].strip() for j in range(i - 1, -1, -1) if L[j].strip()), '')
        if m.group(1) in vistos or re.search(r'(reglas?|,|\by|\bo|\bla|\bel)$', previo, re.I):
            continue
        vistos.add(m.group(1))
        titulo, j = [], i - 1
        while j >= 0 and len(titulo) < 2:
            t = L[j].strip()
            if t and corte.search(t):
                break
            if t:
                titulo.insert(0, t)
            elif titulo:
                break
            j -= 1
        inicios.append((i, m.group(1), ' '.join(titulo), j + 1))
    reglas = []
    for k, (i, num, titulo, _) in enumerate(inicios):
        if k + 1 < len(inicios):
            fin = inicios[k + 1][3]  # donde empieza el título de la siguiente
        else:  # la última corre hasta los transitorios o la nota final de la compilación
            fin = next((x for x in range(i, len(L)) if L[x].strip() == 'Transitorios' or L[x].startswith('NOTA: Este documento')), len(L))
        reglas.append((num, titulo, ' '.join(' '.join(L[i + 1:fin]).split())))
    return reglas


def partir_criterios(texto):
    """[(clave, título, cuerpo)] para '1/CFF/N', '1/CFF/PI'. Si la clave aparece en el índice y en el cuerpo, se queda la más larga.
    Excluye los DEROGADOS: el índice los lista bajo "B. Derogados" y su texto va al final, tras el segundo "Derogados"."""
    L = [l.strip() for l in RUIDO.sub('', texto).split('\n')]
    marcas = [i for i, l in enumerate(L) if re.search(r'\bDerogados\b', l)]
    derogados = set()
    if marcas:
        fin_indice = next((i for i in range(marcas[0], len(L)) if L[i] in ('A.', 'Vigentes')), len(L))
        derogados = {m.group(1) for l in L[marcas[0]:fin_indice] if (m := RE_CRITERIO.match(l))}
        if len(marcas) > 1:
            L = L[:marcas[1]]  # el texto de los derogados no entra al corpus
    inicios = [(i, *RE_CRITERIO.match(l).groups()) for i, l in enumerate(L) if RE_CRITERIO.match(l)]
    mejores = {}
    for k, (i, clave, resto) in enumerate(inicios):
        fin = inicios[k + 1][0] if k + 1 < len(inicios) else len(L)
        cuerpo = ' '.join(' '.join([resto] + L[i + 1:fin]).split())
        if len(cuerpo) > len(mejores.get(clave, '')):
            mejores[clave] = cuerpo
    return [(c, '', b) for c, b in mejores.items() if c not in derogados]


def a_markdown(clave, nombre, url, tipo, texto):
    if tipo == 'ley':
        m, nueva = RE_REFORMA.search(texto), RE_NUEVA.search(texto)
        if m:
            vigencia = f"última reforma DOF {m.group(1).replace('/', '-')}"
        elif nueva:
            vigencia = f"publicada DOF {nueva.group(1).replace('/', '-')}, sin reformas"
        else:
            vigencia = 'texto vigente según Diputados (sin fecha detectada)'
        unidades = [(f'Artículo {n}', '', c) for n, c in partir_ley(texto, nombre)]
    elif tipo == 'rmf':
        vigencia = 'RMF 2026 vigente desde 01-01-2026, compilada con 1a. RM DOF 09-07-2026'
        unidades = [(f'Regla {n}', t, c) for n, t, c in partir_rmf(texto)]
    else:
        vigencia = 'Anexo de la RMF 2026 (DOF 09-01-2026)'
        unidades = [(f'Criterio {c}', t, b) for c, t, b in partir_criterios(texto)]
    out = [f'# {nombre}\n\nClave: {clave} · Vigencia: {vigencia} · Fuente: {url}\n']
    for unidad, titulo, cuerpo in unidades:
        t = f' {titulo}' if titulo else ''
        out.append(f'## {clave} — {unidad}{t}\n\n{clave}, {unidad.lower()}{t} ({vigencia}): {cuerpo}\n')
    return '\n'.join(out), len(unidades), vigencia


def construir(claves=()):
    (DIR / 'pdf').mkdir(parents=True, exist_ok=True)
    (DIR / 'md').mkdir(parents=True, exist_ok=True)
    indice_path = DIR / 'indice.json'
    indice = json.loads(indice_path.read_text()) if indice_path.exists() else {}
    for clave, nombre, url, tipo in FUENTES:
        if claves and clave not in claves:
            continue
        pdf = DIR / 'pdf' / f'{clave}.pdf'
        try:
            if not pdf.exists():
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (RATIUM; corpus fiscal)'})
                with urllib.request.urlopen(req, timeout=180) as r:
                    datos = r.read()
                if not datos.startswith(b'%PDF'):
                    raise ValueError('la descarga no es un PDF')
                pdf.write_bytes(datos)
                time.sleep(1)  # ponytail: 1 descarga/seg a sitios de gobierno sin API
            md, n, vigencia = a_markdown(clave, nombre, url, tipo, texto_pdf(pdf))
            (DIR / 'md' / f'{clave}.md').write_text(md)
            indice[clave] = {'nombre': nombre, 'url': url, 'tipo': tipo, 'vigencia': vigencia, 'unidades': n,
                             'descargado': datetime.date.fromtimestamp(pdf.stat().st_mtime).isoformat()}
            print(f'✓ {clave}: {n} unidades · {vigencia}')
        except Exception as e:  # una fuente caída no detiene las demás
            print(f'✗ {clave}: {e}')
    indice_path.write_text(json.dumps(indice, ensure_ascii=False, indent=1))

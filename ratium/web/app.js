'use strict';
// RATIUM — página única. Los datos vienen de XML de terceros: todo se pinta con textContent, nunca innerHTML.

const $ = (s) => document.querySelector(s);
const PAGINA = 200; // renglones visibles antes de "mostrar más"

const REGLAS = {
  cancelado: 'Cancelado', efos_69b: 'Lista 69-B', no_es_del_cliente: 'No es del cliente', totales_no_cuadran: 'Totales no cuadran',
  ppd_sin_complemento: 'PPD sin complemento', ppd_saldo_pendiente: 'PPD con saldo', efectivo_mayor_2000: 'Efectivo > $2,000',
  uso_cfdi: 'Uso CFDI S01', falta_xml: 'Falta XML',
};
const ESTADOS = {
  conciliado: ['Conciliado', 'ok', 'i-check'], revisar: ['Revisar', 'revisar', 'i-eye'], sin_cfdi: ['Sin CFDI', 'neutro', 'i-minus'],
};
const NIVELES = { '🔴': ['Grave', 'grave', 'i-alert'], '🟡': ['Revisar', 'revisar', 'i-eye'] };
const RE_RFC = /^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/;
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const pesos = new Intl.NumberFormat('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const entero = new Intl.NumberFormat('es-MX');

// ── utilidades ──
function h(tag, attrs, ...hijos) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const x of hijos.flat()) if (x != null && x !== false) el.append(x instanceof Node ? x : String(x));
  return el;
}
function ico(id, cls = 'ico') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', cls);
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', '#' + id);
  svg.append(use);
  return svg;
}
const centavos = (v) => Math.round(parseFloat(v || 0) * 100);
const dinero = (v) => (v === '' || v == null || parseFloat(v) === 0 ? '' : pesos.format(parseFloat(v)));
const dineroC = (c) => pesos.format(c / 100);
function fecha(v) {
  if (!v) return '';
  const [a, m, d] = v.slice(0, 10).split('-');
  return `${d}/${m}/${a}`;
}
const peso = (b) => (b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB');
function insignia([texto, tono, icono]) {
  return h('span', { class: `nivel nivel--${tono}` }, ico(icono), texto);
}
function descargarCSV(nombre, columnas, filas) {
  const esc = (v) => {
    const s = v == null ? '' : String(v);
    return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const texto = '﻿' + [columnas.map((c) => c[1]), ...filas.map((f) => columnas.map((c) => esc(f[c[0]])))].map((r) => r.join(',')).join('\r\n');
  const a = h('a', { href: URL.createObjectURL(new Blob([texto], { type: 'text/csv;charset=utf-8' })), download: nombre });
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
}

// ── captura ──
let archivos = [];
const lista = $('#lista-archivos');

function tipoArchivo(nombre) {
  const n = nombre.toLowerCase();
  if (n.endsWith('.pdf')) return ['Estado de cuenta', 'chip chip--banco', 'i-bank'];
  if (n.endsWith('.zip')) return ['ZIP del SAT', 'chip chip--sat', 'i-zip'];
  if (n.endsWith('.txt') || n.endsWith('.csv')) return ['Metadata', 'chip', 'i-file'];
  return null;
}
function agregar(files) {
  const rechazados = [];
  for (const f of files) {
    if (!tipoArchivo(f.name)) { rechazados.push(f.name); continue; }
    if (!archivos.some((a) => a.name === f.name && a.size === f.size)) archivos.push(f);
  }
  mostrarError('#archivos-error', rechazados.length ? `No se reconoce: ${rechazados.join(', ')}. Solo ZIP, TXT y PDF.` : '');
  pintarArchivos();
}
function pintarArchivos() {
  lista.replaceChildren(...archivos.map((f, i) => {
    const [etq, cls, icono] = tipoArchivo(f.name);
    return h('li', {},
      ico(icono), h('span', { class: 'nombre', title: f.name }, f.name), h('span', { class: cls }, etq), h('span', { class: 'peso cifra' }, peso(f.size)),
      h('button', { type: 'button', 'aria-label': `Quitar ${f.name}`, onclick: () => { archivos.splice(i, 1); pintarArchivos(); } }, ico('i-x')));
  }));
}
function mostrarError(sel, msg) {
  const el = $(sel);
  el.textContent = msg;
  el.hidden = !msg;
}

const zona = $('#zona');
$('#archivos').addEventListener('change', (e) => { agregar(e.target.files); e.target.value = ''; });
['dragenter', 'dragover'].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.add('sobre'); }));
['dragleave', 'drop'].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.remove('sobre'); }));
zona.addEventListener('drop', (e) => agregar(e.dataTransfer.files));

const rfc = $('#rfc');
rfc.addEventListener('input', () => { rfc.value = rfc.value.toUpperCase().replace(/\s/g, ''); });
rfc.addEventListener('blur', () => validarRFC(false));
function validarRFC(enfocar) {
  const ok = RE_RFC.test(rfc.value);
  rfc.setAttribute('aria-invalid', String(!ok && rfc.value !== '' || (!ok && enfocar)));
  mostrarError('#rfc-error', ok || (rfc.value === '' && !enfocar) ? '' : 'Revisa el RFC: 3 o 4 letras, 6 dígitos de fecha y 3 de homoclave.');
  if (!ok && enfocar) rfc.focus();
  return ok;
}

$('#formulario').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!validarRFC(true)) return;
  if (!archivos.some((f) => /\.zip$/i.test(f.name))) {
    mostrarError('#archivos-error', 'Falta al menos un ZIP del SAT.');
    zona.focus();
    return;
  }
  const boton = $('#enviar');
  const estado = $('#estado-envio');
  boton.disabled = true;
  boton.replaceChildren(h('span', { class: 'giro', 'aria-hidden': 'true' }), 'Revisando…');
  estado.textContent = 'Leyendo XML y cruzando con el banco. Un mes típico tarda unos segundos.';
  const datos = new FormData();
  datos.append('rfc', rfc.value);
  archivos.forEach((f) => datos.append('archivos', f, f.name));
  try {
    const r = await fetch('/api/revision', { method: 'POST', body: datos });
    const json = await r.json().catch(() => ({ error: `El servidor respondió ${r.status}` }));
    if (!r.ok) throw new Error(json.error || `Error ${r.status}`);
    estado.textContent = '';
    mostrarResultados(json);
  } catch (err) {
    estado.textContent = '';
    mostrarError('#archivos-error', `No se pudo revisar: ${err.message}`);
  } finally {
    boton.disabled = false;
    boton.replaceChildren(h('span', { class: 'boton__texto' }, 'Revisar'));
  }
});

$('#nueva').addEventListener('click', () => {
  $('#vista-resultados').hidden = true;
  $('#vista-captura').hidden = false;
  window.scrollTo(0, 0);
  rfc.focus();
});

// ── resultados ──
function mostrarResultados(d) {
  const delCliente = d.cfdis.find((c) => c.emisor_rfc === d.rfc) || d.cfdis.find((c) => c.receptor_rfc === d.rfc);
  const nombre = delCliente ? (delCliente.emisor_rfc === d.rfc ? delCliente.emisor_nombre : delCliente.receptor_nombre) : '';
  $('#r-cliente').replaceChildren(nombre || d.rfc, nombre ? h('span', { class: 'cifra' }, d.rfc) : null);
  $('#r-periodo').textContent = periodo(d.cfdis);

  const graves = d.alertas.filter((a) => a.nivel === '🔴').length;
  const banco = d.bancos[0];
  let conc = null;
  if (banco) {
    const cargos = banco.filas.filter((f) => centavos(f.cargo));
    const ok = cargos.filter((f) => f.estado === 'conciliado').reduce((s, f) => s + centavos(f.cargo), 0);
    conc = Math.round((ok / Math.max(1, cargos.reduce((s, f) => s + centavos(f.cargo), 0))) * 100);
  }
  $('#r-cifras').replaceChildren(
    cifra('CFDI leídos', entero.format(d.cfdis.length), d.n_metadata ? `de ${entero.format(d.n_metadata)} en metadata` : ''),
    cifra('Alertas graves', entero.format(graves), '', graves ? 'grave' : ''),
    cifra('Por revisar', entero.format(d.alertas.length - graves)),
    cifra('Pagos conciliados', conc == null ? '—' : `${conc}%`, conc == null ? 'sin estado de cuenta' : 'del importe de cargos'));

  const avisos = [];
  if (d.errores.length) avisos.push(['grave', `${d.errores.length} archivo(s) no se pudieron leer: ${d.errores.slice(0, 3).map((e) => e[0]).join(', ')}`]);
  const faltan = d.alertas.filter((a) => a.regla === 'falta_xml').length;
  if (faltan) avisos.push(['', `Faltan ${entero.format(faltan)} XML que sí están en la metadata. El portal del SAT entrega máximo 500 por descarga: bájalos por rangos de días.`]);
  if (!d.lista_69b) avisos.push(['', 'No hay lista 69-B cargada: corre "python -m ratium actualizar-69b" para revisar EFOS.']);
  $('#r-avisos').replaceChildren(...avisos.map(([t, m]) => h('p', { class: `aviso ${t ? 'aviso--' + t : ''}` }, ico('i-alert'), h('span', {}, m))));

  $('#c-alertas').textContent = entero.format(d.alertas.length);
  $('#c-cfdis').textContent = entero.format(d.cfdis.length);
  $('#c-conciliacion').textContent = banco ? entero.format(banco.filas.length) : '—';
  $('#c-pendientes').textContent = banco ? entero.format(banco.pendientes.length) : '—';

  panelAlertas(d);
  panelConciliacion(d);
  panelPendientes(d);
  panelCfdis(d);
  elegirPestana($('#t-alertas'), false);

  $('#vista-captura').hidden = true;
  $('#vista-resultados').hidden = false;
  window.scrollTo(0, 0);
  $('#principal').focus({ preventScroll: true });
}
function cifra(titulo, valor, nota, cls) {
  return h('div', { class: cls || null }, h('dt', {}, cls === 'grave' ? ico('i-alert') : null, titulo), h('dd', {}, valor, nota ? h('small', {}, nota) : null));
}
function periodo(cfdis) {
  const meses = [...new Set(cfdis.map((c) => (c.fecha || '').slice(0, 7)).filter(Boolean))].sort();
  if (!meses.length) return 'Revisión';
  const nombre = (m) => `${MESES[+m.slice(5) - 1]} ${m.slice(0, 4)}`;
  // un mes "dominante" (los XML del mes) aunque haya alguno de días vecinos
  const cuenta = meses.map((m) => [m, cfdis.filter((c) => (c.fecha || '').startsWith(m)).length]).sort((a, b) => b[1] - a[1]);
  return cuenta[0][1] / cfdis.length > 0.9 ? nombre(cuenta[0][0]) : `${nombre(meses[0])} – ${nombre(meses.at(-1))}`;
}

// Tabla genérica con filtros por chip, búsqueda, CSV y totales con doble subrayado.
function tablaFiltrable(panel, cfg) {
  let filtro = 'todos';
  let texto = '';
  let limite = PAGINA;
  const cuerpo = h('div', {});
  const contar = (k) => (k === 'todos' ? cfg.filas.length : cfg.filas.filter((f) => cfg.grupo(f) === k).length);
  const chips = h('div', { class: 'filtros', role: 'group', 'aria-label': 'Filtrar' },
    [['todos', 'Todos'], ...cfg.grupos].filter(([k]) => contar(k)).map(([k, etq]) =>
      h('button', { type: 'button', 'aria-pressed': String(k === 'todos'), onclick: (e) => {
        filtro = k; limite = PAGINA;
        chips.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b === e.currentTarget)));
        pintar();
      } }, etq, h('span', { class: 'n' }, entero.format(contar(k))))));
  const buscar = h('input', { type: 'search', placeholder: cfg.buscarTexto || 'Buscar RFC, nombre, UUID…', 'aria-label': 'Buscar', oninput: (e) => { texto = e.target.value.toLowerCase(); limite = PAGINA; pintar(); } });
  const visibles = () => cfg.filas.filter((f) => (filtro === 'todos' || cfg.grupo(f) === filtro) && (!texto || cfg.texto(f).toLowerCase().includes(texto)));
  const csv = h('button', { type: 'button', class: 'boton boton--fantasma boton--chico', onclick: () => descargarCSV(cfg.csv, cfg.csvColumnas, visibles()) }, ico('i-download'), 'CSV');
  panel.append(h('div', { class: 'herramientas' }, chips, h('div', { class: 'buscar' }, ico('i-search'), buscar), csv), cuerpo);

  function pintar() {
    const filas = visibles();
    if (!filas.length) {
      cuerpo.replaceChildren(h('div', { class: 'hoja sin-datos' }, ico('i-check', 'ico'), h('p', {}, cfg.vacio || 'Nada que mostrar con este filtro.')));
      return;
    }
    const thead = h('thead', {}, h('tr', {}, cfg.columnas.map((c) => h('th', { class: c.num ? 'num' : null, scope: 'col' }, c.t))));
    const tbody = h('tbody', {}, filas.slice(0, limite).map((f) => h('tr', {}, cfg.columnas.map((c) => {
      const v = c.v(f);
      return h('td', { class: [c.num && 'num', c.cls, v === '' && 'vacio'].filter(Boolean).join(' ') || null }, v === '' ? '—' : v);
    }))));
    const tfoot = cfg.totales ? h('tfoot', {}, h('tr', {}, cfg.columnas.map((c, i) => {
      if (i === 0) return h('td', {}, `${entero.format(filas.length)} renglones`);
      if (!c.suma) return h('td', {});
      return h('td', { class: 'num' }, h('span', {}, dineroC(filas.reduce((s, f) => s + centavos(c.suma(f)), 0))));
    }))) : null;
    cuerpo.replaceChildren(h('div', { class: 'hoja' }, h('table', {}, thead, tbody, tfoot)),
      filas.length > limite ? h('button', { type: 'button', class: 'boton boton--fantasma boton--chico mas', onclick: () => { limite += PAGINA * 5; pintar(); } },
        `Mostrar ${entero.format(Math.min(filas.length - limite, PAGINA * 5))} más de ${entero.format(filas.length - limite)}`) : null);
  }
  pintar();
}

function contraparte(nombre, rfc) {
  return h('span', {}, nombre || rfc || '', nombre && rfc ? h('span', { class: 'sub cifra' }, rfc) : null);
}

function panelAlertas(d) {
  const panel = $('#p-alertas');
  panel.replaceChildren();
  const presentes = [...new Set(d.alertas.map((a) => a.regla))];
  tablaFiltrable(panel, {
    filas: d.alertas, grupo: (a) => a.regla, grupos: presentes.map((r) => [r, REGLAS[r] || r]),
    texto: (a) => [a.uuid, a.emisor_rfc, a.emisor_nombre, a.receptor_rfc, a.mensaje].join(' '),
    vacio: 'Sin alertas: los XML del mes pasaron todas las validaciones.',
    csv: `alertas_${d.rfc}.csv`,
    csvColumnas: [['nivel', 'Nivel'], ['regla', 'Regla'], ['fecha', 'Fecha'], ['emisor_rfc', 'RFC emisor'], ['emisor_nombre', 'Emisor'], ['receptor_rfc', 'RFC receptor'], ['total', 'Total'], ['uuid', 'UUID'], ['mensaje', 'Mensaje']],
    columnas: [
      { t: 'Nivel', v: (a) => insignia(NIVELES[a.nivel] || ['Info', 'neutro', 'i-eye']) },
      { t: 'Fecha', v: (a) => fecha(a.fecha), cls: 'fecha' },
      { t: 'Contraparte', v: (a) => (a.emisor_rfc === d.rfc ? contraparte('', a.receptor_rfc) : contraparte(a.emisor_nombre, a.emisor_rfc)) },
      { t: 'Detalle', v: (a) => h('span', {}, h('b', {}, REGLAS[a.regla] || a.regla), h('span', { class: 'sub' }, a.mensaje), h('span', { class: 'sub uuid' }, a.uuid)) },
      { t: 'Total', v: (a) => dinero(a.total), num: true },
    ],
  });
}

function panelConciliacion(d) {
  const panel = $('#p-conciliacion');
  panel.replaceChildren();
  if (!d.bancos.length) {
    panel.append(h('div', { class: 'hoja sin-datos' }, ico('i-bank', 'ico'), h('p', {}, 'Sube el estado de cuenta en PDF junto con los ZIP para conciliar los pagos del mes.')));
    return;
  }
  for (const b of d.bancos) {
    const r = b.resumen;
    panel.append(
      h('p', { class: 'cuadre' }, ico('i-check'), `${b.archivo} cuadra con el banco: ${r.n_cargos} cargos y ${r.n_abonos} abonos · saldo final $${dinero(r.saldo_final)}`),
      h('div', { class: 'balanza' }, balanza('Pagos (cargos)', b.filas, 'cargo'), balanza('Cobros (abonos)', b.filas, 'abono')));
    tablaFiltrable(panel, {
      filas: b.filas, grupo: (f) => f.estado, grupos: Object.entries(ESTADOS).map(([k, v]) => [k, v[0]]),
      texto: (f) => [f.descripcion, f.contraparte, f.uuids, f.regla].join(' '),
      csv: `conciliacion_${d.rfc}.csv`, totales: true,
      csvColumnas: [['fecha', 'Fecha'], ['codigo', 'Código'], ['descripcion', 'Descripción'], ['cargo', 'Cargo'], ['abono', 'Abono'], ['estado', 'Estado'], ['regla', 'Regla / categoría'], ['diferencia', 'Diferencia'], ['contraparte', 'Contraparte'], ['uuids', 'UUIDs']],
      columnas: [
        { t: 'Fecha', v: (f) => fecha(f.fecha), cls: 'fecha' },
        { t: 'Movimiento', v: (f) => { const [p, ...resto] = f.descripcion.split(' | '); return h('span', {}, p, resto.length ? h('span', { class: 'sub' }, resto.join(' · ')) : null); } },
        { t: 'Cargo', v: (f) => dinero(f.cargo), num: true, suma: (f) => f.cargo },
        { t: 'Abono', v: (f) => dinero(f.abono), num: true, suma: (f) => f.abono },
        { t: 'Estado', v: (f) => insignia(ESTADOS[f.estado]) },
        { t: 'Regla / CFDI', v: (f) => h('span', {}, f.regla || '—', f.contraparte ? h('span', { class: 'sub' }, f.contraparte) : null,
          f.diferencia && parseFloat(f.diferencia) !== 0 ? h('span', { class: 'sub' }, `Diferencia $${pesos.format(parseFloat(f.diferencia))}`) : null) },
      ],
    });
  }
}
function balanza(titulo, filas, lado) {
  const mias = filas.filter((f) => centavos(f[lado]));
  const total = mias.reduce((s, f) => s + centavos(f[lado]), 0) || 1;
  const por = Object.keys(ESTADOS).map((k) => { const g = mias.filter((f) => f.estado === k); return [k, g.length, g.reduce((s, f) => s + centavos(f[lado]), 0)]; });
  return h('article', {},
    h('h3', {}, titulo, h('span', { class: 'cifra' }, `$${dineroC(total)}`)),
    h('div', { class: 'barra-c', role: 'img', 'aria-label': por.map(([k, n, c]) => `${ESTADOS[k][0]}: ${n} movimientos, ${Math.round((c / total) * 100)}%`).join('; ') },
      por.filter(([, , c]) => c).map(([k, , c]) => h('span', { class: `seg-${k}`, style: `flex:${c}` }))),
    h('dl', { class: 'leyenda' }, por.map(([k, n, c]) => h('div', {},
      h('dt', {}, h('i', { class: `seg-${k}` }), ESTADOS[k][0]),
      h('dd', {}, `$${dineroC(c)}`, h('small', {}, ` · ${n}`))))));
}

function panelPendientes(d) {
  const panel = $('#p-pendientes');
  panel.replaceChildren();
  if (!d.bancos.length) return panel.append(h('div', { class: 'hoja sin-datos' }, ico('i-bank', 'ico'), h('p', {}, 'Requiere estado de cuenta.')));
  panel.append(h('p', { class: 'ayuda', style: 'margin:0 0 14px' }, 'CFDI que por su forma de pago debieron pasar por el banco y no aparecen en el estado de cuenta (pagos de otro mes, otra cuenta o en efectivo mal marcado).'));
  tablaFiltrable(panel, {
    filas: d.bancos[0].pendientes, grupo: (e) => e.lado, grupos: [['cargo', 'Pagos a proveedores'], ['abono', 'Cobros a clientes']],
    texto: (e) => [e.rfc, e.nombre, e.uuid].join(' '), csv: `cfdi_sin_banco_${d.rfc}.csv`, totales: true,
    vacio: 'Todos los CFDI esperados aparecieron en el banco.',
    csvColumnas: [['lado', 'Lado'], ['fecha', 'Fecha'], ['rfc', 'RFC'], ['nombre', 'Nombre'], ['tipo', 'Tipo'], ['importe', 'Importe'], ['uuid', 'UUID']],
    columnas: [
      { t: 'Fecha', v: (e) => fecha(e.fecha), cls: 'fecha' },
      { t: 'Contraparte', v: (e) => contraparte(e.nombre, e.rfc) },
      { t: 'Tipo', v: (e) => h('span', {}, e.tipo === 'pago' ? 'Complemento de pago' : 'Factura PUE', h('span', { class: 'sub uuid' }, e.uuid)) },
      { t: 'Importe', v: (e) => dinero(e.importe), num: true, suma: (e) => e.importe },
    ],
  });
}

function panelCfdis(d) {
  const panel = $('#p-cfdis');
  panel.replaceChildren();
  tablaFiltrable(panel, {
    filas: d.cfdis, grupo: (c) => (c.emisor_rfc === d.rfc ? 'emitidos' : 'recibidos'), grupos: [['emitidos', 'Emitidos'], ['recibidos', 'Recibidos']],
    texto: (c) => [c.uuid, c.emisor_rfc, c.emisor_nombre, c.receptor_rfc, c.receptor_nombre, c.serie, c.folio, c.tipo].join(' '),
    csv: `cfdis_${d.rfc}.csv`, totales: true,
    csvColumnas: Object.keys(d.cfdis[0] || {}).map((k) => [k, k]),
    columnas: [
      { t: 'Fecha', v: (c) => fecha(c.fecha), cls: 'fecha' },
      { t: 'Tipo', v: (c) => h('span', {}, c.tipo, h('span', { class: 'sub' }, [c.metodo_pago, c.forma_pago && `forma ${c.forma_pago}`].filter(Boolean).join(' · '))) },
      { t: 'Emisor', v: (c) => contraparte(c.emisor_nombre, c.emisor_rfc) },
      { t: 'Receptor', v: (c) => contraparte(c.receptor_nombre, c.receptor_rfc) },
      { t: 'Folio', v: (c) => h('span', {}, [c.serie, c.folio].filter(Boolean).join('-') || '—', h('span', { class: 'sub uuid' }, c.uuid)) },
      { t: 'Total', v: (c) => dinero(c.total), num: true, suma: (c) => c.total },
    ],
  });
}

// ── pestañas (flechas izquierda/derecha como pide ARIA) ──
const pestanas = [...document.querySelectorAll('[role=tab]')];
function elegirPestana(tab, enfocar = true) {
  pestanas.forEach((t) => {
    const sel = t === tab;
    t.setAttribute('aria-selected', String(sel));
    t.tabIndex = sel ? 0 : -1;
    document.getElementById(t.getAttribute('aria-controls')).hidden = !sel;
  });
  if (enfocar) tab.focus();
}
pestanas.forEach((t, i) => {
  t.addEventListener('click', () => elegirPestana(t));
  t.addEventListener('keydown', (e) => {
    const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (d) { e.preventDefault(); elegirPestana(pestanas[(i + d + pestanas.length) % pestanas.length]); }
  });
});

# Preguntas para Diana (piloto RATIUM)

## Flujo real de Diana (reunión 2026-10-27)
1. Abre CONTPAQi Contabilidad → **ADD** descarga del SAT los XML + metadata (sin portal ni ZIP).
2. **Contabilizador** (Contabilizar CFDI) genera las pólizas automáticamente en CONTPAQi.
3. **Cotejo con el estado de cuenta bancario**: revisar cuáles CFDI sí aparecen en el banco → con **F9** se hace la póliza (de pago/cobro).
4. **Lo que más tiempo le toma: la conciliación bancaria (paso 3).**

5. Respuestas (2026-10-27):
   - Cotejo: va cotejando conforme encuentra los movimientos/facturas (en los dos sentidos).
   - F9: selecciona el movimiento si está dentro del estado de cuenta. **Foto de la pantalla F9: mañana 2026-10-28.**
   - Lo que atora: montos que no cuadran por centavos y facturas que no aparecen.
   - **Prioridad: lo que salió del banco y no tiene factura.**
   - El cliente manda el estado de cuenta en PDF hacia el **día 5**; conciliar Super Pack le toma **5 días**.

Consecuencia: CONTPAQi ya resuelve la descarga y las pólizas de provisión. El valor de RATIUM está en la conciliación banco ↔ CFDI.

Se van agregando conforme surgen dudas técnicas. Marcar con ✅ y anotar la respuesta.

## Material que necesitamos
- [x] Versión de CONTPAQi Contabilidad → ✅ 19.2.0, licencia anual 4 usuarios, empresas ilimitadas, DPIVA + Contabilidad Electrónica (2026-10-16)
- [x] Catálogo de cuentas → ✅ Super Pack La Charanda (SPC150925J13): 1,094 cuentas, 8 dígitos, catálogo estándar CONTPAQi ligado a agrupador SAT, sin subcuentas por proveedor/cliente
- [x] ZIP del SAT → ✅ sep-2026, 2 ZIP + 2 metadata. ⚠️ Emitidas: ZIP trae 500 XML y metadata 679 → el portal corta en 500; faltan 178 emitidas (+19 recibidas). Hay que bajar por rangos de días
- [ ] Las pólizas que capturó ese mes para ese cliente (la "respuesta correcta")
- [ ] Si importa algún archivo a CONTPAQi hoy: un ejemplo

- [x] Extra: estado de cuenta BBVA sep-2026 (PDF 38 págs, 565 movimientos: SPEI, terminal punto de venta, comisiones) → base para conciliación bancaria

## CONTPAQi y su forma de trabajar
1. ¿Cómo contabiliza hoy los XML: captura manual, ADD (visor de XML de CONTPAQi) o importa un archivo? → captura de pantalla de **Contabilizar CFDI** (asiento + póliza diaria, concepto "VENTAS BANCARIAS"). Confirmar: ¿usa asientos contables predefinidos por tipo de CFDI?
2. ¿Hace una póliza por factura o agrupa (por día, por proveedor, por mes)?
3. ¿Qué tipos de póliza usa para cada caso (diario, ingresos, egresos)?
4. ¿Qué texto pone en el concepto de la póliza? (ej. "Fact A-123 Proveedor X")
5. ¿Usa segmentos de negocio o centros de costo?
6. ¿Lleva contabilidad electrónica con código agrupador del SAT ligado al catálogo?
7. IVA en facturas PPD: ¿lo registra como "IVA pendiente de acreditar/trasladar" y lo pasa a "efectivamente pagado" cuando llega el complemento de pago?

## Sus clientes
8. ¿Cuántos clientes lleva y de qué regímenes (RESICO, PF actividad empresarial, persona moral, arrendamiento…)?
9. ¿Cuántos XML por mes tiene un cliente típico? ¿Y el más grande?
10. ¿Algún cliente factura o recibe facturas en dólares u otra moneda?
11. ¿Contabiliza la nómina a partir de los XML de nómina timbrados?

## Descarga del SAT
12. ¿Descarga emitidas y recibidas en ZIP separados? → ✅ sí, cada uno con su metadata TXT
13. ¿Descarga también la metadata (TXT/CSV con estatus de cancelación)? → ✅ sí
20. ¿Sabe que el portal SAT limita a 500 XML por descarga? En sep-2026 faltaron 178 emitidas. ¿Las baja en varias tandas?
21. ¿Las facturas de mostrador / venta al público general se contabilizan una por una o en global?

## Reglas que aplica hoy
14. ¿Qué hace con un CFDI cancelado que ya había contabilizado?
15. ¿Revisa proveedores contra la lista 69-B (EFOS)? ¿Qué hace si sale uno?
16. Gastos no deducibles: ¿qué reglas revisa? (pago en efectivo > $2,000, uso CFDI S01, gastos sin relación con la actividad…)

19. Un RFC puede aparecer varias veces en la lista 69-B (ej. "Definitivo" y "Sentencia Favorable" por oficios distintos; hay 82 casos en la lista actual). Hoy RATIUM marca la situación más grave. ¿Es correcto o la sentencia favorable lo limpia?

## Valor del producto (para vender a otros contadores)
17. ¿Cuánto tiempo le toma hoy contabilizar un mes de un cliente típico?
18. ¿Qué parte del proceso le quita más tiempo o le da más errores?

## Conciliación bancaria (sep-2026 Super Pack)
22. Hay ~$5.5 M en pagos con RFC sin factura/complemento (ej. AAMM690929989, FJC780315E91). ¿Faltan en la descarga o el proveedor no ha timbrado el complemento?
23. Cobros en efectivo/terminal (~$5.3 M): ¿cómo los concilia, contra factura global o por día?
24. ¿Qué bancos usan sus clientes además de BBVA?

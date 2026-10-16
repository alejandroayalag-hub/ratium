# Armado e instalación del equipo de IA (llega 23-oct-2026)

## Antes de que llegue
- [ ] Descargar **Ubuntu Server 24.04 LTS** (ubuntu.com/download/server) y grabarlo en una USB de 8 GB o más (balenaEtcher o Rufus).
- [ ] Confirmar que tienes: cable **OCuLink**, **fuente de poder** para el dock y la **GPU**.
- [ ] Un cable de red al router (mejor que WiFi) y un monitor + teclado solo para la instalación.

## Armado
1. GPU en el dock, fuente conectada al dock, cable OCuLink del dock a la miniPC.
2. **Siempre: primero se enciende el dock, después la miniPC.** La GPU por OCuLink no se detecta si se conecta con la miniPC prendida.

## Preparar el NAS QNAP (en su página web, antes de correr el script)
La miniPC va en el **mismo router/switch que el NAS**.
1. **Panel de control → Carpetas compartidas → Crear:**
   - `escritos`: ahí van los escritos Word del despacho (Lexium los lee).
   - `respaldos`: ahí la miniPC deja una copia diaria de su respaldo (30 días).
2. **Panel de control → Usuarios → Crear:**
   - `lexium-ro`: permiso **solo lectura** en `escritos`, **sin acceso** a lo demás.
   - `ia-respaldo`: **lectura/escritura** solo en `respaldos`, sin acceso a lo demás.
3. **Panel de control → Red y servicios de archivo → Win/Mac/NFS:** SMB activado, versión mínima **SMB 3**.
4. Anotar la **IP del NAS** y, de preferencia, fijarla en el router (reserva DHCP) para que no cambie.

El script pide las dos contraseñas una sola vez y las guarda protegidas en la miniPC. Además revisa que `lexium-ro` de verdad no pueda escribir: la IA nunca debe poder modificar ni borrar los escritos.

## Instalar Ubuntu
1. Arrancar de la USB (F7/F11/Supr al prender, según la marca).
2. Opciones: idioma English o Español, disco completo, usuario **`alejandro`** (igual que la PC de Lexium), marcar **Install OpenSSH server**. No marcar paquetes extra.
3. Al terminar, quitar la USB y reiniciar.

## Correr el script
Desde esta computadora, ya con la miniPC en la misma red (Claude puede hacerlo si le das la IP local):

```
scp ~/ratium/instalacion/instalar.sh alejandro@IP_DE_LA_MINIPC:
ssh alejandro@IP_DE_LA_MINIPC
sudo bash instalar.sh      # instala el driver NVIDIA y pide reiniciar
sudo reboot
sudo NAS_IP=IP_DEL_NAS bash instalar.sh   # instala todo lo demás y monta el NAS (~20-30 min, baja ~10 GB de modelos)
sudo tailscale up          # autorizar con tu cuenta en el link que imprime
tailscale ip -4            # esta IP se la pasas a Claude
```

Si al reiniciar sale una pantalla azul **"Perform MOK management"**: Enroll MOK → Continue → Yes → la contraseña que te pidió el script.

## Qué deja instalado
| | |
|---|---|
| Ollama | qwen3:14b + bge-m3, solo accesible desde la propia miniPC |
| Open WebUI | `http://IP:3000`, la primera cuenta que se registra es la de admin |
| Tailscale | acceso remoto de soporte |
| Firewall | solo red local y Tailscale; nada expuesto a internet |
| SSH | por red solo con llave (en la consola física sigue la contraseña) |
| NAS | `escritos` en `/mnt/nas/escritos` (solo lectura) y `respaldos` en `/mnt/nas/respaldos`; si el NAS está apagado la miniPC arranca igual |
| Respaldos | diario 3:30 am: 14 días en la miniPC + 30 días en el NAS |
| Actualizaciones | parches de seguridad automáticos |

Al final el script mide la velocidad: con la GPU funcionando debe dar **más de 15 tokens/s**. Si da 2-5, la IA está corriendo en el procesador y la GPU no se detectó.

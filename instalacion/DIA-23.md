# Armado e instalación del equipo de IA (llega 23-oct-2026)

## Antes de que llegue
- [ ] Descargar **Ubuntu Server 24.04 LTS** (ubuntu.com/download/server) y grabarlo en una USB de 8 GB o más (balenaEtcher o Rufus).
- [ ] Confirmar que tienes: cable **OCuLink**, **fuente de poder** para el dock y la **GPU**.
- [ ] Un cable de red al router (mejor que WiFi) y un monitor + teclado solo para la instalación.

## Armado
1. GPU en el dock, fuente conectada al dock, cable OCuLink del dock a la miniPC.
2. **Siempre: primero se enciende el dock, después la miniPC.** La GPU por OCuLink no se detecta si se conecta con la miniPC prendida.

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
sudo bash instalar.sh      # instala todo lo demás (~20-30 min, baja ~10 GB de modelos)
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
| Respaldos | diario 3:30 am en `/srv/respaldos`, 14 días (mismo disco: falta copia externa) |
| Actualizaciones | parches de seguridad automáticos |

Al final el script mide la velocidad: con la GPU funcionando debe dar **más de 15 tokens/s**. Si da 2-5, la IA está corriendo en el procesador y la GPU no se detectó.

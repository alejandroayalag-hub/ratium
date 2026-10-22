#!/usr/bin/env bash
# Instala el equipo de IA local (miniPC + GPU NVIDIA por OCuLink) sobre Ubuntu Server 24.04 LTS.
# Sirve para RATIUM y Lexium: Ollama + Open WebUI + Tailscale + firewall + respaldos.
#
# Uso:  sudo bash instalar.sh
#       sudo NAS_IP=192.168.68.50 bash instalar.sh    (además monta el NAS QNAP del despacho; ver DIA-23.md)
#       sudo SIN_GPU=1 bash instalar.sh               (instala todo menos el driver, con la GPU aún sin conectar;
#                                                      al conectarla se vuelve a correr sin SIN_GPU)
# Correrlo DOS veces: la primera instala el driver NVIDIA y pide reiniciar; la segunda instala el resto.
# Es idempotente: si algo falla se corrige y se vuelve a correr.
set -euo pipefail

USUARIO_IA=ia                       # usuario de sistema que corre Open WebUI
DIR_IA=/srv/ia                      # home de $USUARIO_IA: datos de Open WebUI y de RATIUM
DIR_RESPALDOS=/srv/respaldos
OWUI_VERSION=0.11.4                 # la misma que Lexium: sus scripts de carga usan esta API
OWUI_PUERTO=3000
MODELOS=(qwen3:14b bge-m3)          # generador + embeddings (caben juntos en 16 GB de VRAM)
NAS_IP="${NAS_IP:-}"                # vacío = sin NAS
SIN_GPU="${SIN_GPU:-}"              # 1 = se salta GPU y driver (Ollama corre en CPU mientras)
NAS_ESCRITOS=escritos               # carpeta compartida con los escritos del despacho (Lexium la lee)
NAS_RESPALDOS=respaldos             # carpeta compartida donde se copia el respaldo diario
NAS_USUARIO_RO=lexium-ro            # usuario del QNAP con permiso SOLO LECTURA en $NAS_ESCRITOS
NAS_USUARIO_RESP=ia-respaldo        # usuario del QNAP con lectura/escritura SOLO en $NAS_RESPALDOS
LLAVE_SSH='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJmOE5ko1yKAIdqOHyETwWR0aAxzQ571g5fExh5uebRq alejandroayalag@gmail.com'           # llave pública de la máquina de desarrollo (acceso de soporte)

paso() { printf '\n\033[1;35m▶ %s\033[0m\n' "$*"; }
falla() { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || falla "Córrelo con sudo: sudo bash $0"
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" =~ ^(24|26)\.04$ ]] || falla "Probado solo en Ubuntu 24.04 y 26.04 (este es $PRETTY_NAME)"

paso "1/10 Revisando la GPU"
command -v lspci >/dev/null || apt-get install -y pciutils
if [[ -n "$SIN_GPU" ]]; then
  echo "SIN_GPU=1: se omiten GPU y driver"
else
  lspci | grep -qi nvidia || falla "No se ve ninguna GPU NVIDIA. La GPU por OCuLink NO se detecta en caliente:
  apaga la miniPC, enciende primero el dock de la GPU y después la miniPC.
  (Para instalar el resto sin GPU: sudo SIN_GPU=1 bash $0)"
  lspci | grep -i nvidia || true
fi

paso "2/10 Paquetes del sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y full-upgrade
apt-get install -y curl git poppler-utils python3 ufw unattended-upgrades openssh-server ubuntu-drivers-common
dpkg-reconfigure -f noninteractive unattended-upgrades   # parches de seguridad automáticos

paso "3/10 Driver NVIDIA"
if [[ -n "$SIN_GPU" ]]; then
  echo "SIN_GPU=1: driver pendiente"
elif ! nvidia-smi >/dev/null 2>&1; then
  ubuntu-drivers install
  printf '\n\033[1;33m⚠ Driver instalado. Reinicia (sudo reboot) y vuelve a correr: sudo bash %s\033[0m\n' "$0"
  printf '  Si al reiniciar aparece la pantalla azul "Perform MOK management": Enroll MOK → Continue → la contraseña que te pidió.\n'
  exit 0
else
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
fi

paso "4/10 Ollama"
if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/install.sh -o /tmp/ollama-install.sh
  sh /tmp/ollama-install.sh
fi
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/ia.conf <<'EOF'
[Service]
# solo local: Open WebUI es la única puerta de entrada (Ollama no tiene usuarios ni contraseña)
Environment=OLLAMA_HOST=127.0.0.1:11434
Environment=OLLAMA_KEEP_ALIVE=30m
# la carga masiva de documentos satura la cola de embeddings con el valor por defecto (512)
Environment=OLLAMA_MAX_QUEUE=4096
EOF
systemctl daemon-reload
systemctl enable --now ollama
systemctl restart ollama
for i in $(seq 1 30); do ollama list >/dev/null 2>&1 && break; sleep 2; done
for m in "${MODELOS[@]}"; do ollama pull "$m"; done

paso "5/10 Usuario de servicio y Open WebUI $OWUI_VERSION"
id "$USUARIO_IA" >/dev/null 2>&1 || useradd --system --create-home --home-dir "$DIR_IA" --shell /usr/sbin/nologin "$USUARIO_IA"
install -d -o "$USUARIO_IA" -g "$USUARIO_IA" -m 750 "$DIR_IA/webui-data" "$DIR_IA/datos"
como_ia() { sudo -u "$USUARIO_IA" -H env PATH="$DIR_IA/.local/bin:/usr/bin:/bin" bash -c "$1"; }
[[ -x "$DIR_IA/.local/bin/uv" ]] || como_ia 'curl -LsSf https://astral.sh/uv/install.sh | sh'
if ! como_ia "uv tool list 2>/dev/null | grep -q 'open-webui v$OWUI_VERSION'"; then
  como_ia "uv tool install --force --python 3.11 open-webui==$OWUI_VERSION"
fi

cat > /etc/systemd/system/ia-webui.service <<EOF
[Unit]
Description=Open WebUI (IA local RATIUM / Lexium)
After=network-online.target ollama.service
Wants=network-online.target

[Service]
User=$USUARIO_IA
Group=$USUARIO_IA
WorkingDirectory=$DIR_IA
Environment=DATA_DIR=$DIR_IA/webui-data
Environment=OLLAMA_BASE_URL=http://127.0.0.1:11434
Environment=RAG_EMBEDDING_ENGINE=ollama
Environment=RAG_EMBEDDING_MODEL=bge-m3
Environment=CHUNK_SIZE=3000
Environment=CHUNK_OVERLAP=200
Environment=RAG_TOP_K=8
Environment=ENABLE_OPENAI_API=False
Environment=ANONYMIZED_TELEMETRY=False
Environment=DO_NOT_TRACK=True
ExecStart=$DIR_IA/.local/bin/open-webui serve --host 0.0.0.0 --port $OWUI_PUERTO
Restart=always
# Open WebUI abre una colección por documento: con cientos de leyes truena con el límite de 1024
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now ia-webui
systemctl restart ia-webui

paso "6/10 Tailscale (acceso remoto de soporte)"
command -v tailscale >/dev/null || curl -fsSL https://tailscale.com/install.sh | sh
systemctl enable --now tailscaled

paso "7/10 SSH solo con llave"
ADMIN="${SUDO_USER:-}"
if [[ -n "$ADMIN" && "$LLAVE_SSH" == ssh-* ]]; then
  HOME_ADMIN=$(getent passwd "$ADMIN" | cut -d: -f6)
  install -d -o "$ADMIN" -g "$ADMIN" -m 700 "$HOME_ADMIN/.ssh"
  touch "$HOME_ADMIN/.ssh/authorized_keys"
  grep -qF "$LLAVE_SSH" "$HOME_ADMIN/.ssh/authorized_keys" || echo "$LLAVE_SSH" >> "$HOME_ADMIN/.ssh/authorized_keys"
  chown "$ADMIN:$ADMIN" "$HOME_ADMIN/.ssh/authorized_keys"; chmod 600 "$HOME_ADMIN/.ssh/authorized_keys"
  # la consola física sigue entrando con contraseña; por red, solo llave
  printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\n' > /etc/ssh/sshd_config.d/10-ia.conf
  sshd -t && systemctl reload ssh
else
  echo "Sin SUDO_USER o sin llave: SSH queda como estaba"
fi

paso "8/10 Firewall: solo red local y Tailscale"
ufw default deny incoming
ufw default allow outgoing
ufw allow in on tailscale0
for red in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16; do
  ufw allow from "$red" to any port 22 proto tcp
  ufw allow from "$red" to any port "$OWUI_PUERTO" proto tcp
done
ufw --force enable

paso "9/10 NAS del despacho"
if [[ -n "$NAS_IP" ]]; then
  apt-get install -y cifs-utils
  install -d -m 700 /etc/ia
  pedir_cred() {  # $1 archivo, $2 usuario del QNAP; la contraseña se pide una vez y queda en un archivo 600
    if [[ ! -s "$1" ]]; then
      read -rsp "Contraseña del usuario $2 en el NAS: " clave; echo
      printf 'username=%s\npassword=%s\n' "$2" "$clave" > "$1"; chmod 600 "$1"; unset clave
    fi
  }
  pedir_cred /etc/ia/nas-escritos.cred "$NAS_USUARIO_RO"
  pedir_cred /etc/ia/nas-respaldos.cred "$NAS_USUARIO_RESP"
  install -d "/mnt/nas/$NAS_ESCRITOS" "/mnt/nas/$NAS_RESPALDOS"
  UID_IA=$(id -u "$USUARIO_IA"); GID_IA=$(id -g "$USUARIO_IA")
  # nofail + automount: si el NAS está apagado la miniPC arranca igual y monta cuando el NAS vuelve
  OPC="vers=3.0,nofail,_netdev,x-systemd.automount,x-systemd.mount-timeout=15"
  sed -i '\#/mnt/nas/#d' /etc/fstab
  echo "//$NAS_IP/$NAS_ESCRITOS /mnt/nas/$NAS_ESCRITOS cifs ro,credentials=/etc/ia/nas-escritos.cred,uid=$UID_IA,gid=$GID_IA,file_mode=0440,dir_mode=0550,$OPC 0 0" >> /etc/fstab
  echo "//$NAS_IP/$NAS_RESPALDOS /mnt/nas/$NAS_RESPALDOS cifs rw,credentials=/etc/ia/nas-respaldos.cred,uid=0,gid=0,file_mode=0600,dir_mode=0700,$OPC 0 0" >> /etc/fstab
  systemctl daemon-reload
  systemctl restart remote-fs.target
  if ls "/mnt/nas/$NAS_ESCRITOS" >/dev/null 2>&1; then
    echo "✓ escritos montado: $(find "/mnt/nas/$NAS_ESCRITOS" -type f | wc -l) archivos"
    # ro en el montaje no basta: el usuario del QNAP tampoco debe poder escribir (defensa doble)
    if mount -o remount,rw "/mnt/nas/$NAS_ESCRITOS" 2>/dev/null && touch "/mnt/nas/$NAS_ESCRITOS/.prueba-ia" 2>/dev/null; then
      rm -f "/mnt/nas/$NAS_ESCRITOS/.prueba-ia"
      echo "⚠ El usuario $NAS_USUARIO_RO PUEDE escribir en $NAS_ESCRITOS: en el QNAP déjalo en solo lectura"
    fi
    mount -o remount,ro "/mnt/nas/$NAS_ESCRITOS" 2>/dev/null || true
  else
    echo "✗ No se pudo montar //$NAS_IP/$NAS_ESCRITOS: revisa usuario, contraseña y permisos en el QNAP"
  fi
  if touch "/mnt/nas/$NAS_RESPALDOS/.prueba-ia" 2>/dev/null; then
    rm -f "/mnt/nas/$NAS_RESPALDOS/.prueba-ia"; echo "✓ respaldos montado con escritura"
  else
    echo "✗ No se pudo escribir en //$NAS_IP/$NAS_RESPALDOS"
  fi
else
  echo "Sin NAS_IP: se omite (los respaldos quedan solo en este disco)"
fi

paso "10/10 Respaldo diario"
install -d -m 700 "$DIR_RESPALDOS"
cat > /usr/local/sbin/ia-respaldo <<EOF
#!/bin/sh
set -e
archivo="ia-\$(date +%F).tar.gz"
tar czf "$DIR_RESPALDOS/\$archivo" -C "$DIR_IA" webui-data datos
find "$DIR_RESPALDOS" -name 'ia-*.tar.gz' -mtime +14 -delete
# copia fuera de este disco: si el NAS está montado, ahí se guardan 30 días
if mountpoint -q "/mnt/nas/$NAS_RESPALDOS"; then
  cp "$DIR_RESPALDOS/\$archivo" "/mnt/nas/$NAS_RESPALDOS/"
  find "/mnt/nas/$NAS_RESPALDOS" -name 'ia-*.tar.gz' -mtime +30 -delete
fi
EOF
chmod 700 /usr/local/sbin/ia-respaldo
echo "30 3 * * * root /usr/local/sbin/ia-respaldo" > /etc/cron.d/ia-respaldo

paso "Verificación"
for i in $(seq 1 60); do curl -fs "http://127.0.0.1:$OWUI_PUERTO/health" >/dev/null && break; sleep 2; done
curl -fs "http://127.0.0.1:$OWUI_PUERTO/health" >/dev/null && echo "✓ Open WebUI responde" || echo "✗ Open WebUI no responde: journalctl -u ia-webui -n 50"
curl -fs http://127.0.0.1:11434/api/generate -d '{"model":"qwen3:14b","prompt":"Responde solo OK","stream":false,"think":false}' \
  | python3 -c 'import json,sys; r=json.load(sys.stdin); print("✓ qwen3:14b responde a %.1f tokens/s (con GPU debe ser > 15)" % (r["eval_count"]/r["eval_duration"]*1e9))' \
  || echo "✗ qwen3:14b no respondió: journalctl -u ollama -n 50"
ollama ps

IP_LAN=$(hostname -I | awk '{print $1}')
cat <<EOF

────────────────────────────────────────────────────────
Listo. Falta UN paso manual:
  1. sudo tailscale up        → abre el link que imprime y autoriza con tu cuenta
  2. Pásale a Claude la IP de Tailscale:  tailscale ip -4
  3. Abre http://$IP_LAN:$OWUI_PUERTO y crea la cuenta de administrador
     (la PRIMERA cuenta que se registra es la de admin)
────────────────────────────────────────────────────────
EOF

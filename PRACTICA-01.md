# Práctica 01 — Runbook completo

**Identificación de Riesgos de Confidencialidad**
ICSA-014 Manejo de Datos para la Ciberseguridad — FCC/BUAP

Guía operativa de principio a fin. Cada fase trae los comandos exactos y, donde
existe, la trampa que hace perder horas. Contrasta la numeración con tu
enunciado: aquí las fases van por orden lógico, no por número de paso.

- Paso 1 (preparar VirtualBox e ISOs) → [`vm/paso-01-preparacion.md`](vm/paso-01-preparacion.md)
- Reglas de detección → [`lab/reglas/lab-cia.rules`](lab/reglas/lab-cia.rules)

**Direcciones que usa todo este documento** — son las mismas con las que se
validaron las reglas, así que respétalas y todo encaja:

| Máquina | Adaptador 1 (NAT) | Adaptador 2 (LAB-CIA) |
|---|---|---|
| Debian 12 (defensa/IDS) | DHCP automático | **192.168.100.10/24** |
| Kali (atacante) | DHCP automático | **192.168.100.20/24** |

---

## Fase A — Crear las VMs

```bash
cd vm
./lab-cia-virtualbox.sh \
  --iso-debian ~/Descargas/debian-12.x.0-amd64-netinst.iso \
  --iso-kali   ~/Descargas/kali-linux-2026.N-installer-amd64.iso
```

Es el mismo comando del Paso 1 sin `--dry-run`. Crea `LAB-CIA-Debian` y
`LAB-CIA-Kali` con NAT en el adaptador 1 y la red interna `LAB-CIA` en el 2, en
modo promiscuo *permitir todo*.

Verifica antes de arrancar nada:

```bash
VBoxManage showvminfo LAB-CIA-Debian | grep -i "^NIC"
VBoxManage showvminfo LAB-CIA-Kali   | grep -i "^NIC"
```

Debes ver `NIC 2: ... Internal Network 'LAB-CIA' ... Promisc Policy: allow-all`.
Si el promiscuo no dice `allow-all`, **el IDS no verá un solo paquete** y no lo
descubrirás hasta la fase F.

---

## Fase B — Instalar Debian 12

```bash
VBoxManage startvm LAB-CIA-Debian
```

Recorre el instalador capturando cada pantalla.

> **Trampa.** El instalador detecta **dos** interfaces y pregunta cuál es la
> principal. Elige **la primera (`enp0s3`, el NAT)**. La segunda es el segmento
> aislado, no tiene DHCP ni salida a Internet, y si la eliges el instalador se
> quedará colgado buscando el mirror de Debian.

En la selección de software, marca **SSH server** y **utilidades estándar del
sistema**. El entorno de escritorio es opcional (el sensor funciona en consola).

---

## Fase C — Instalar Kali

```bash
VBoxManage startvm LAB-CIA-Kali
```

Misma trampa de la interfaz principal: **la primera, el NAT**.

Datos que exige el enunciado, tal cual:

| Campo | Valor |
|---|---|
| Nombre de la máquina | `LAB-CIA` |
| Dominio | `datoskali.org` |
| Nombre completo | `Atacante Kali` |
| Usuario | `atacante` |
| Contraseña | `12345` |
| Software | Xfce + `default -- recommended tools` |

> `12345` la fija el enunciado. Es aceptable **solo** porque es una VM de
> laboratorio en una red interna aislada. No la reutilices en nada más.

---

## Fase D — Configurar la red interna

**Esta fase no está en el guion de la mayoría de las guías y sin ella nada
funciona.** La red interna de VirtualBox **no tiene servidor DHCP**: el
adaptador 2 arranca sin dirección IPv4. Si haces `ip addr show enp0s8` recién
instalado, verás la interfaz sin IP, y eso no es un fallo tuyo.

Hay que poner IPs estáticas a mano en las dos máquinas.

### Debian (192.168.100.10)

Primero confirma el nombre real de la interfaz:

```bash
ip link show
```

Si el sistema usa NetworkManager (instalaste escritorio):

```bash
sudo nmcli con add type ethernet ifname enp0s8 con-name LAB-CIA \
     ip4 192.168.100.10/24
sudo nmcli con up LAB-CIA
```

Si es una instalación de consola con `ifupdown`:

```bash
sudo tee /etc/network/interfaces.d/lab-cia >/dev/null <<'EOF'
auto enp0s8
iface enp0s8 inet static
    address 192.168.100.10
    netmask 255.255.255.0
EOF
sudo ifup enp0s8
```

### Kali (192.168.100.20)

En Kali las interfaces suelen llamarse `eth0` (NAT) y `eth1` (interna);
confírmalo con `ip link show`.

```bash
sudo nmcli con add type ethernet ifname eth1 con-name LAB-CIA \
     ip4 192.168.100.20/24
sudo nmcli con up LAB-CIA
```

### Comprobaciones (las que pide el enunciado)

```bash
# Debian
ip link show                 # interfaces detectadas
ip addr show enp0s8          # IP del adaptador interno → 192.168.100.10
ping -c 4 google.com         # salida a Internet por el NAT
ping -c 4 192.168.100.20     # alcance a Kali por la red interna

# Kali
nmcli device status
ip a
ping -c 4 192.168.100.10     # alcance a Debian
```

Si los dos `ping` internos responden, el segmento LAB-CIA está vivo y puedes
seguir. Si no, revisa que ambas VMs tengan el adaptador 2 en la **misma** red
interna con el **mismo nombre exacto**, `LAB-CIA`.

---

## Fase E — Levantar servicios en Debian

Las reglas 1000006–1000009 detectan **fugas de confidencialidad por banner**:
el servicio anunciando su versión. Para que haya banner que detectar, tiene que
haber servicio escuchando.

```bash
sudo apt update
sudo apt install -y openssh-server apache2
sudo systemctl enable --now ssh apache2
```

Con eso cubres la regla del banner SSH (1000006) y la cabecera `Server:` de
Apache (1000009). Si quieres también las de FTP y MySQL:

```bash
sudo apt install -y vsftpd mariadb-server
```

> La regla 1000010 (sondeo a MySQL) dispara con el **SYN** al puerto 3306
> aunque no haya nada escuchando: esa funciona sin instalar nada.

---

## Fase F — Poner en marcha el sensor IDS

```bash
sudo apt install -y snort suricata
```

El paquete de Snort abre un diálogo preguntando por `HOME_NET`; pon lo que sea,
lo vamos a sobrescribir con nuestra propia configuración.

Detén los servicios automáticos, que arrancan en la interfaz equivocada:

```bash
sudo systemctl stop snort suricata
sudo systemctl disable snort suricata
```

Copia las reglas a la VM (por `scp`, carpeta compartida o `git clone`) y déjalas
en, por ejemplo, `~/lab-cia.rules`.

### La trampa importante: HOME_NET y EXTERNAL_NET

Kali y Debian están en la **misma** red interna. La configuración de fábrica de
Suricata trae:

```yaml
HOME_NET: "[192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12]"
EXTERNAL_NET: "!$HOME_NET"
```

Con eso, `192.168.100.20` (Kali) queda **dentro** de HOME_NET, `EXTERNAL_NET` lo
excluye, y las reglas escritas como `$EXTERNAL_NET any -> $HOME_NET any`
—es decir, todas las de escaneo— **no disparan jamás**. Cero alertas, sin ningún
mensaje de error que te oriente. Es el fallo que más tiempo hace perder.

La solución es acotar las variables al par de máquinas del laboratorio, que es
exactamente como se validaron las reglas:

**Suricata** (sin tocar el YAML, todo por línea de comandos):

```bash
sudo suricata -i enp0s8 -S ~/lab-cia.rules -l /var/log/suricata -k none \
  --set vars.address-groups.HOME_NET="[192.168.100.10/32]" \
  --set vars.address-groups.EXTERNAL_NET="[192.168.100.20/32]"
```

**Snort** (configuración mínima propia):

```bash
sudo tee /etc/snort/snort-lab.conf >/dev/null <<'EOF'
var HOME_NET 192.168.100.10/32
var EXTERNAL_NET 192.168.100.20/32
include /etc/snort/classification.config
include /etc/snort/reference.config
include /home/TU_USUARIO/lab-cia.rules
EOF

sudo snort -q -i enp0s8 -c /etc/snort/snort-lab.conf -A console -k none
```

`-k none` desactiva la validación de checksums. En interfaces virtuales el
*checksum offload* deja checksums inválidos en los paquetes y ambos motores los
descartan **en silencio**: otra vía rápida a cero alertas.

Deja el sensor corriendo en primer plano y pasa a Kali en otra ventana.

---

## Fase G — Reconocimiento desde Kali

Ejecuta desde Kali, con el sensor mirando:

```bash
# Descubrimiento de hosts        → regla 1000001
sudo nmap -sn --disable-arp-ping 192.168.100.0/24

# Escaneo SYN                    → regla 1000002
sudo nmap -sS -p 1-1000 192.168.100.10

# Banderas anómalas              → reglas 1000003, 1000004, 1000005
sudo nmap -sN -p 21,22,80,3306 192.168.100.10
sudo nmap -sF -p 21,22,80,3306 192.168.100.10
sudo nmap -sX -p 21,22,80,3306 192.168.100.10

# Versiones de servicio (banners) → reglas 1000006-1000009
sudo nmap -sV -p 21,22,80,3306 192.168.100.10
```

> **Trampa en el barrido de hosts.** `nmap -sn` contra una máquina de tu **misma
> subred** usa **ARP**, no ICMP, y la regla 1000001 busca ICMP `itype:8`: sin
> `--disable-arp-ping` el barrido no genera ni una alerta y parece que la regla
> está rota. El flag fuerza el ping ICMP.

Alternativa equivalente para ese mismo caso:

```bash
for i in $(seq 1 20); do ping -c1 -W1 192.168.100.$i >/dev/null 2>&1 & done
```

### Alertas esperadas en Debian

| SID | Alerta | Disparada por |
|---|---|---|
| 1000001 | Barrido ICMP | `nmap -sn --disable-arp-ping` |
| 1000002 | Escaneo SYN | `nmap -sS` |
| 1000003 | Escaneo NULL | `nmap -sN` |
| 1000004 | Escaneo FIN | `nmap -sF` |
| 1000005 | Escaneo XMAS | `nmap -sX` |
| 1000006 | Banner SSH | `nmap -sV` con `ssh` activo |
| 1000009 | Cabecera Server de Apache | `nmap -sV` con `apache2` activo |
| 1000010 | Sondeo a MySQL | cualquier SYN a 3306 |

Las 1000007 (banner MySQL) y 1000008 (banner FTP) solo aparecen si instalaste
`mariadb-server` y `vsftpd` en la fase E.

Registros donde quedan las alertas:

```bash
sudo tail -f /var/log/suricata/fast.log     # Suricata
# Snort las imprime en consola con -A console
```

---

## Fase H — Evidencia

Las capturas las haces tú, con tu escritorio y **fecha y hora visibles**. El
conjunto mínimo que cuenta la historia completa:

1. Verificación de las ISOs: `sha256sum -c` en `OK` y `gpg --verify` con
   `Good signature`.
2. Cada pantalla del instalador de Debian.
3. Cada pantalla del instalador de Kali, en especial las de `LAB-CIA`,
   `datoskali.org`, `Atacante Kali` / `atacante`, y la selección de software
   con Xfce y `default -- recommended tools`.
4. `VBoxManage showvminfo` mostrando `Internal Network 'LAB-CIA'` y
   `Promisc Policy: allow-all`.
5. Comprobaciones de red: `ip link show`, `ip addr show enp0s8`,
   `ping -c 4 google.com`, `nmcli device status`, `ip a`.
6. Los dos `ping` cruzados entre 192.168.100.10 y .20.
7. **Las dos ventanas a la vez**: Kali lanzando `nmap` y Debian mostrando las
   alertas apareciendo. Esta es la captura que demuestra la práctica entera.
8. `fast.log` con las alertas por SID.

---

## Si algo no dispara

| Síntoma | Causa más probable |
|---|---|
| Cero alertas de todo | `EXTERNAL_NET` incluye a Kali → acota las variables (fase F) |
| Cero alertas de todo | Adaptador 2 sin `allow-all` → revisa `showvminfo` |
| Cero alertas de todo | Checksums inválidos → falta `-k none` |
| Solo falla 1000001 | `nmap -sn` usó ARP → añade `--disable-arp-ping` |
| Solo fallan 1000006-1000009 | No hay servicios escuchando → fase E |
| Las VMs no se ven entre sí | Nombre de red interna distinto, o falta la IP estática → fase D |

---

## Nota sobre la validación de las reglas

`lab/lab-cia-sim.sh` reproduce este segmento con network namespaces y pasa
tráfico real de Nmap por Snort y Suricata. Es una ayuda de validación, no el
laboratorio: los namespaces corren Linux normal, no Kali ni Debian invitados, y
la validación se hizo con `HOME_NET`/`EXTERNAL_NET` acotados a las dos IPs — la
misma configuración que indica la fase F, y la razón por la que hay que
replicarla en las VMs.

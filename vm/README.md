# Laboratorio virtual — máquinas Kali y Debian

Dos herramientas con propósitos distintos. Elige según lo que necesites.

| Script | Para qué sirve | Hipervisor |
|---|---|---|
| `lab-cia-virtualbox.sh` | Práctica 01 de ICSA-014 (FCC/BUAP): crea las VMs con la red exacta y tú recorres el instalador capturando pantallas | VirtualBox |
| `provision-kali.sh` | Kali desatendido y reproducible, sin tocar el instalador | QEMU o libvirt/KVM |

> **¿Empezando la práctica?** El [Paso 1 — Preparar VirtualBox y las ISOs](paso-01-preparacion.md)
> cubre qué imágenes descargar (ojo: Kali **Installer**, no Live; y Debian 12 ya
> no está en `current/`) y cómo verificar su firma antes de crear nada.

---

## `lab-cia-virtualbox.sh` — la práctica

La práctica pide **evidencias en captura de pantalla de cada paso del
instalador**, así que automatizar la instalación completa sería contraproducente.
Este script hace la parte que sí conviene automatizar: crear las dos VMs con la
configuración de red correcta.

```bash
./lab-cia-virtualbox.sh \
  --iso-debian ~/Descargas/debian-12.x.0-amd64-netinst.iso \
  --iso-kali   ~/Descargas/kali-linux-2025.x-installer-amd64.iso
```

Usa `--dry-run` para ver los comandos sin ejecutar nada.

### La topología

```
        ┌──────────────────┐        ┌──────────────────┐
        │  LAB-CIA-Debian  │        │   LAB-CIA-Kali   │
        │    defensa/IDS   │        │     atacante     │
        └────┬────────┬────┘        └────┬────────┬────┘
   Adaptador1│        │Adaptador2   Ad.1 │        │ Ad.2
        NAT  │        │  intnet      NAT │        │ intnet
             ▼        ▼                  ▼        ▼
        (Internet)   ═══════ red interna "LAB-CIA" ═══════
                       modo promiscuo: permitir todo
```

- **Adaptador 1 → NAT**: salida a Internet (para `apt` y el `ping -c 4 google.com`
  del Paso 5c).
- **Adaptador 2 → Red interna `LAB-CIA`**: segmento aislado donde ocurre el
  ataque. No toca tu red real.
- **Modo promiscuo `permitir todo`** en el adaptador 2: sin esto, la interfaz
  descarta las tramas que no van dirigidas a su MAC y **Snort y Suricata no ven
  absolutamente nada**. Es el error más común de esta práctica.

### Datos que pide el enunciado (Paso 3, VM de Kali)

| Campo | Valor |
|---|---|
| Nombre de la máquina | `LAB-CIA` |
| Dominio | `datoskali.org` |
| Nombre completo | `Atacante Kali` |
| Usuario | `atacante` |
| Contraseña | `12345` |
| Software | Xfce + `default -- recommended tools` |

> La contraseña `12345` la fija el enunciado. Es aceptable **sólo** porque es una
> VM de laboratorio en una red interna aislada y sin exposición a Internet
> entrante. No la reutilices en nada más.

### Comprobaciones (Pasos 5 y 7)

```bash
# Debian
ip link show              # 5a — interfaces detectadas
ip addr show enp0s8       # 5b — IP del adaptador interno
ping -c 4 google.com      # 5c — salida a Internet por el NAT

# Kali
nmcli device status       # 7a
ip a                      # 7b
```

`enp0s3` suele ser el adaptador 1 (NAT) y `enp0s8` el adaptador 2 (red interna).
Confírmalo con `ip link show` antes de dar por hecho el nombre.

---

## `provision-kali.sh` — instalación desatendida

Instala Kali de cero sin interacción: descarga el netinst oficial, **verifica la
firma GPG del archivo de Kali y el SHA256 de la imagen**, y arranca el
instalador con un preseed inyectado en el initrd.

```bash
# QEMU (portable)
./provision-kali.sh --backend qemu --disk 60 --ram 4096

# libvirt/KVM
./provision-kali.sh --backend libvirt --name kali-lab
```

Opciones útiles: `--packages "kali-linux-headless"` para una VM sin escritorio,
`--apt-proxy` si tienes caché apt local, `--iso` para reutilizar una ISO ya
descargada. `--help` lista todo.

### Seguridad

- La contraseña **nunca** se pasa por línea de comandos ni se guarda en el repo:
  se pide por stdin o se toma de `KALI_PASSWORD`, y se hashea localmente con
  SHA-512 antes de escribirla en el preseed (permisos `600`).
- Si la firma GPG de `SHA256SUMS` o el hash de la ISO no cuadran, **aborta**. No
  hay opción de saltarse la verificación.
- La huella de la clave de Kali está fijada en el script; si la clave descargada
  no coincide, aborta.
- El login de `root` queda deshabilitado; la administración va por `sudo`.

### Requisitos

`curl gpg openssl awk` y, según backend, `qemu-system-x86_64 qemu-img xorriso
cpio gzip` o `virt-install virsh`. Necesitas virtualización por hardware (VT-x /
AMD-V) activada en la BIOS y acceso a `/dev/kvm`; sin ella funciona, pero
emulado y entre 10 y 20 veces más lento.

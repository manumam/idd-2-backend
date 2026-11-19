"""Genera el plan JMeter del polling del frontend a partir de config/escenario.json."""
import json
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

CARPETA = Path(__file__).parent
ESCENARIO = json.loads((CARPETA.parent / 'config' / 'escenario.json').read_text())
API = urlsplit(ESCENARIO['api_url'])

# setInterval del front: el próximo tick se agenda desde el montaje, no desde la respuesta;
# si una respuesta tarda más que el intervalo, ese tick se pierde (como el `if (loading)` del front).
ESPERAR_TICK = '''long intervalo = Long.parseLong(Parameters)
long ahora = System.currentTimeMillis()
long proximo = Long.parseLong(vars.get('proximo_tick')) + intervalo
while (proximo <= ahora) proximo += intervalo
vars.put('proximo_tick', Long.toString(proximo))
proximo - ahora'''
MONTAJE = "if (vars.get('proximo_tick') == null) vars.put('proximo_tick', Long.toString(System.currentTimeMillis()))"


def prop(name, value, kind='stringProp'):
    return f'<{kind} name="{name}">{escape(str(value))}</{kind}>'


def P(nombre, defecto):
    return f'${{__P({nombre},{defecto})}}'


def nodo(elemento, hijos=''):
    return elemento + '<hashTree>' + hijos + '</hashTree>'


def jsr(tipo, nombre, script, parametros=''):
    tag = 'JSR223' + tipo
    return nodo(f'<{tag} guiclass="TestBeanGUI" testclass="{tag}" testname="{nombre}" enabled="true">'
                + prop('scriptLanguage', 'groovy') + prop('cacheKey', 'true') + prop('parameters', parametros)
                + prop('filename', '') + prop('script', script) + f'</{tag}>')


def get(etiqueta, ruta):
    return nodo(f'<HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="{escape(etiqueta)}" enabled="true">'
                + prop('HTTPSampler.protocol', P('protocolo', API.scheme))
                + prop('HTTPSampler.domain', P('host', API.hostname))
                + prop('HTTPSampler.port', P('puerto', API.port))
                + prop('HTTPSampler.path', ruta) + prop('HTTPSampler.method', 'GET')
                + prop('HTTPSampler.use_keepalive', 'true', 'boolProp') + prop('HTTPSampler.follow_redirects', 'false', 'boolProp')
                + prop('HTTPSampler.connect_timeout', P('timeout', ESCENARIO['timeout_ms']))
                + prop('HTTPSampler.response_timeout', P('timeout', ESCENARIO['timeout_ms']))
                + '<elementProp name="HTTPsampler.Arguments" elementType="Arguments"><collectionProp name="Arguments.arguments"/></elementProp>'
                + '</HTTPSamplerProxy>')


def esperar(pagina):
    intervalo = P(f'intervalo_{pagina}', ESCENARIO['intervalos_ms'][pagina])
    return nodo('<TestAction guiclass="TestActionGui" testclass="TestAction" testname="Esperar próximo tick" enabled="true">'
                + prop('ActionProcessor.action', 1, 'intProp') + prop('ActionProcessor.target', 0, 'intProp')
                + prop('ActionProcessor.duration', 0) + '</TestAction>',
                jsr('Timer', f'setInterval {pagina}', ESPERAR_TICK, intervalo))


def bucle(nombre, vueltas, hijos):
    return nodo(f'<LoopController guiclass="LoopControlPanel" testclass="LoopController" testname="{nombre}" enabled="true">'
                + prop('LoopController.continue_forever', 'true', 'boolProp') + prop('LoopController.loops', vueltas)
                + '</LoopController>', hijos)


def una_vez(hijos):
    return nodo('<OnceOnlyController guiclass="OnceOnlyControllerGui" testclass="OnceOnlyController" testname="Al montar la página" enabled="true"/>', hijos)


def pagina(nombre, usuarios, pasos):
    return nodo(f'<ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="{nombre}" enabled="true">'
                + prop('ThreadGroup.on_sample_error', 'continue')
                + '<elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop">'
                + prop('LoopController.continue_forever', 'false', 'boolProp') + prop('LoopController.loops', -1, 'intProp') + '</elementProp>'
                + prop('ThreadGroup.num_threads', P(f'usuarios_{usuarios}', ESCENARIO['usuarios'][usuarios]))
                + prop('ThreadGroup.ramp_time', P('rampa', ESCENARIO['rampa_s']))
                + prop('ThreadGroup.scheduler', 'true', 'boolProp')
                + prop('ThreadGroup.duration', f"${{__intSum({P('rampa', ESCENARIO['rampa_s'])},{P('sostenimiento', ESCENARIO['sostenimiento_s'])})}}")
                + prop('ThreadGroup.delay', '')
                + '</ThreadGroup>',
                jsr('PreProcessor', 'Montaje', MONTAJE) + pasos)


partido = P('partido', ESCENARIO['partido'])
grupo = P('grupo', ESCENARIO['grupo'])
alineaciones_cada = ESCENARIO['intervalos_ms']['alineaciones'] // ESCENARIO['intervalos_ms']['partido']

# El detalle y la cronología se refrescan juntos cada 5 s; las alineaciones, en uno de cada tres ticks (15 s).
pagina_partido = pagina('Página de partido en vivo', 'partido',
                        get('GET /partidos/{codigo}/alineaciones', f'/partidos/{partido}/alineaciones')
                        + bucle('Ticks entre alineaciones', alineaciones_cada,
                                get('GET /partidos/{codigo}', f'/partidos/{partido}')
                                + get('GET /partidos/{codigo}/eventos', f'/partidos/{partido}/eventos?limit=200&skip=0')
                                + esperar('partido')))
pagina_fixture = pagina('Página de fixture', 'fixture', get('GET /fixture', '/fixture') + esperar('fixture'))
pagina_grupos = pagina('Página de grupos', 'grupos',
                       una_vez(get('GET /grupos', '/grupos'))
                       + get('GET /grupos/{id}/posiciones', f'/grupos/{grupo}/posiciones') + esperar('grupos'))
pagina_playoffs = pagina('Página de playoffs', 'playoffs', get('GET /playoffs', '/playoffs') + esperar('playoffs'))

cabeceras = nodo('<HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="Cabeceras del front" enabled="true">'
                 '<collectionProp name="HeaderManager.headers"><elementProp name="" elementType="Header">'
                 + prop('Header.name', 'Accept') + prop('Header.value', 'application/json')
                 + '</elementProp></collectionProp></HeaderManager>')

plan = ('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3"><hashTree>'
        + nodo('<TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Polling del front" enabled="true">'
               + prop('TestPlan.functional_mode', 'false', 'boolProp')
               + '<elementProp name="TestPlan.user_defined_variables" elementType="Arguments"><collectionProp name="Arguments.arguments"/></elementProp>'
               + '</TestPlan>',
               cabeceras + pagina_partido + pagina_fixture + pagina_grupos + pagina_playoffs)
        + '</hashTree></jmeterTestPlan>\n')
(CARPETA / 'polling_front.jmx').write_text(plan)

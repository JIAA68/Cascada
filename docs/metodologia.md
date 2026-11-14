# Cascada: metodología

Versión del demostrador, 8 de noviembre de 2026. Describe los métodos, supuestos y limitaciones de Cascada tal como están implementados en el demostrador. Las cifras proceden de los datos descargados en octubre de 2026.

## 1. Datos

### 1.1 Fuentes

| Fuente | Organismo | Licencia | Uso |
|---|---|---|---|
| Catálogo de Riesgos Potenciales: capas de peligrosidad (5 m) | Comunidad de Madrid (IDEM) | CC BY 4.0 | Amenazas |
| Centros educativos | Comunidad de Madrid (portal de datos abiertos) | CC BY | Activos |
| Centros, servicios y establecimientos sanitarios | Comunidad de Madrid (portal de datos abiertos) | CC BY | Activos |
| Registro de centros de atención social | Comunidad de Madrid (portal de datos abiertos) | CC BY | Activos y plazas |
| Municipios y distritos de Madrid (2020) | Comunidad de Madrid (portal de datos abiertos) | CC BY | Límites y municipio de la ignición |
| Censo 2021 en rejilla de 1 km | INE | Reutilización del INE | Población por celda |
| Mapa base, ortofoto PNOA y MDT | IGN | CC BY 4.0 | Fondo y relieve |
| Mapa de modelos de combustibles (LiDAR, 433.681 polígonos, modelos NFFL) | Comunidad de Madrid (IDEM, servicio WFS) | CC BY 4.0 | Modelo de incendio dentro de la Comunidad |
| Mapa europeo de combustibles (2017, vegetación de hacia 2000) | Copernicus EFFIS (JRC) | CC BY 4.0 | Modelo de incendio fuera de la Comunidad |
| Observación, predicción horaria y predicción diaria por municipio | AEMET OpenData | Reutilización de AEMET, con atribución | Viento; previsión de la prealerta |
| Avisos del Plan Meteoalerta (CAP, canal público) y delimitación de las zonas de aviso | AEMET | Reutilización de AEMET, con atribución | Prealerta: avisos oficiales y zonas |
| Avisos meteorológicos de España (respaldo) | Meteoalarm (EUMETNET) | Licencia equivalente a CC BY 4.0 | Prealerta, si AEMET no responde |
| Focos de calor VIIRS | NASA FIRMS | Datos abiertos de la NASA | Alertas automáticas; focos de 2025 para la validación |
| Áreas quemadas (perímetros) | Copernicus EFFIS (JRC) | CC BY 4.0 | Validación del modelo de incendio |
| Red de Calidad del Aire: datos meteorológicos horarios | Comunidad de Madrid (portal de datos abiertos) | CC BY | Viento medido para la validación |
| Base Topográfica Armonizada 2017 (1:10.000): red viaria y ferroviaria | Comunidad de Madrid (IDEM, servicio WFS) | CC BY 4.0 | Carreteras y vías de tren afectadas por el incendio |
| Horario de Cercanías (GTFS estático, 30 días) | Renfe (data.renfe.com) | CC BY 4.0 | Trenes programados que pasan por estaciones afectadas |
| Nomenclátor Geográfico Básico de España (servicio WFS INSPIRE de nombres geográficos): capitales de municipio, núcleos de población y entidades menores | IGN (CNIG) | CC BY 4.0 | Núcleos de población a los que llega el incendio |

### 1.2 Trazabilidad

Cada fichero descargado se registra con su URL, la fecha de descarga (UTC), su huella SHA-256 y su tamaño. Las fuentes de la cadena de datos se registran en `datos/registro.csv`, que se publica. Las descargas de uso (AEMET, FIRMS, relieve de cada simulación) se registran en un registro local.

### 1.3 Sistema de referencia

Capas y centros están en ETRS89 UTM 30N (EPSG:25830). Se verificó con 34 direcciones de centros geocodificadas por CartoCiudad (IGN): la mediana de la desviación es de 0,4 a 1,5 m, frente a unos 235 m si se interpretaran en ED50. Las 47 capas del catálogo comparten exactamente la misma rejilla de 5 m.

**Limitación:** en centros grandes (hospitales, campus) la coordenada puede estar hasta unos 230 m del portal, porque apunta al interior de la parcela. Con píxeles de 5 m, el riesgo "en el punto" del centro puede no recoger peligros de su borde.

### 1.4 Activos

Se filtran los tres conjuntos del portal según el diseño: **3.163 educativos, 105 sanitarios y 2.643 de atención social (5.911)**. De ellos, **5.632 tienen ubicación**:

- 177 centros sociales tienen algún dato marcado como `RESERVADO` por la propia Comunidad (sobre todo de menores y de mujeres): 175, la dirección, el municipio, las coordenadas y el teléfono; 2, solo el teléfono. No se ubican por ningún medio, aunque traigan coordenadas.
- 104 tienen las coordenadas vacías.

**Centros sensibles (decisiones del 13-11-2026):** los 177 en los que la propia Comunidad reserva algún dato, con 3.071 plazas autorizadas. Cascada no interviene en lo que decide la Comunidad: muestra los centros que ella publica y no ubica los que reserva. Como casi todos tienen también el municipio reservado, no pueden contarse por celda, municipio ni zona afectada: solo como total de la Comunidad. En los centros de colectivos protegidos (mujeres, menores, refugiados, personas sin hogar, reclusos, familias, inmigrantes), el rótulo del mapa se queda en el tipo de centro, sin el colectivo: un piso de seis plazas rotulado con su colectivo lo señalaría.

Ninguno de los tres conjuntos contiene NIF de personas físicas. Teléfonos, correos y webs no se publican.

## 2. Riesgo basal

### 2.1 Peligrosidad

Se usan las capas de **peligrosidad** del catálogo, no las de riesgo, porque estas ya incorporan una vulnerabilidad que incluye colegios, residencias y hospitales y producirían doble cómputo.

Codificación común: 0 sin peligro, 1 muy baja, 2 baja, 3 moderada, 4 alta, 5 muy alta, 255 fuera de la Comunidad. **Cada capa usa un tramo distinto de la escala**, según su metodología:

- Nube tóxica, sobrepresión y radiación térmica: 1 (zona de alerta) y 2 (zona de intervención o establecimiento).
- Rotura de presas: 1 (plana de inundación) y 2 (primeros 30 minutos).
- Transporte de energía, centrales y actividades extractivas: hasta 3.
- Incendios forestales, avenidas y derrumbes: escala completa.

**El nivel de peligrosidad no mide lo mismo en todas las capas:** en avenidas es el periodo de retorno (probabilidad); en las capas industriales, la intensidad del daño según la zona de planificación; en derrumbes, la frecuencia histórica de intervenciones por municipio o distrito.

Incendios forestales y avión asignan nivel 1 a todo el territorio como fondo.

**Vista combinada por grupo (decisión del 09-11-2026).** Al marcar un grupo entero (naturales o tecnológicos), el visor no superpone sus capas, porque con una sola paleta el color sería el de la capa dibujada encima y no se entendería nada: muestra una capa combinada con el **nivel máximo del grupo en cada píxel de 5 m**, sin contar el fondo de incendios y avión. Es una vista de conjunto para localizar dónde hay algún peligro del grupo y de qué nivel; no es un índice, porque el nivel de cada capa mide cosas distintas. Al alejarse se pinta el nivel más frecuente, como en las capas de superficie, de modo que los elementos finos (cauces, vías, edificios) solo se ven al acercarse.

### 2.2 Celda de 1 km

Se usa la rejilla europea de 1 km (INSPIRE/Eurostat, EPSG:3035), la misma en la que el INE publica la población del Censo 2021. Cada píxel de 5 m se asigna a la celda que contiene su centro. Para cada celda y capa:

- **Nivel máximo** de los píxeles de la celda.
- **Porcentaje de la celda** (dentro de la Comunidad) con peligro. En incendios forestales y avión no cuenta el nivel 1 de fondo.

Se presentan los dos datos porque el máximo solo sobrestima: en 1 km casi siempre hay una carretera o un edificio con algún nivel. Por ejemplo, derrumbes aparece en 6.084 celdas, pero en la mitad cubre solo el 1 % de la celda.

La población por celda (total, menores de 16 y mayores de 64) es la del Censo 2021. El INE la redondea a múltiplos de 5 por secreto estadístico. La suma sobre la Comunidad es de 6.756.230 habitantes.

### 2.3 Riesgo de un activo

Para cada capa, la peligrosidad en el punto del activo se cruza con su vulnerabilidad mediante **la matriz del propio catálogo** (memoria metodológica, apartado 3):

| Vulnerabilidad ↓ / Peligrosidad → | Muy baja | Baja | Moderada | Alta | Muy alta |
|---|---|---|---|---|---|
| Muy baja | Muy bajo | Muy bajo | Bajo | Bajo | Moderado |
| Baja | Muy bajo | Bajo | Moderado | Moderado | Moderado |
| Moderada | Bajo | Moderado | Moderado | Alto | Alto |
| Alta | Bajo | Moderado | Alto | Alto | Muy alto |
| Muy alta | Moderado | Alto | Alto | Muy alto | Muy alto |

La vulnerabilidad es la de Cascada, según la capacidad de autoprotección de los ocupantes y si hay gente durmiendo en el centro:

| Vulnerabilidad | Activos |
|---|---|
| Muy alta | Hospitales; centros sociales residenciales; educación especial, aulas hospitalarias y centros educativo-terapéuticos |
| Alta | Escuelas infantiles; centros de diálisis; residencias de mayores autónomos y pisos tutelados de adultos autónomos |
| Moderada | Primaria y secundaria; centros sociales de día |
| Baja | Hogares y clubes de mayores |

**Consecuencias de la matriz:**

- Las capas que nunca pasan de peligrosidad *baja* (nube tóxica, sobrepresión, presas) dan como máximo riesgo *alto*, incluso en un hospital.
- Una peligrosidad *muy baja* sobre un centro de vulnerabilidad *muy alta* da riesgo *moderado*.
- **El nivel 1 de fondo de incendios forestales y avión no da riesgo (decisión del 13-11-2026).** Cubre todo el territorio, así que no distingue un centro de otro; contarlo daría a todos los centros un riesgo mínimo de incendio y de avión. Se trata igual que en la celda y en el número de amenazas: la ficha del centro lo muestra como «(fondo)» con riesgo «sin riesgo». Con este criterio, 48 centros cuyo único riesgo era ese fondo quedan sin riesgo.

### 2.4 Lectura de los resultados

Cuatro capas dominan cualquier recuento por su extensión: subsidencias (71 % de los activos con nivel ≥ 2), incendios forestales, derrumbes y transporte de energía. Derrumbes es una media municipal asignada a cada edificio: no distingue dentro de un municipio. Subsidencias es un fenómeno lento que no amenaza a los ocupantes como una emergencia. Las capas que discriminan de verdad entre centros son las de menor extensión: nube tóxica, sobrepresión, presas y avenidas.

## 3. Gestión de crisis: incendio forestal

### 3.1 Velocidad de propagación (Rothermel)

Modelo de propagación de incendios de superficie de Rothermel (1972), con las correcciones de Albini (1976), en implementación propia de Cascada a partir de las publicaciones.

- **Combustibles:** los 13 modelos NFFL de Anderson (1982). Dentro de la Comunidad se usa su mapa de modelos de combustibles (decisión del 08-11-2026, construido el 10-11-2026): 433.681 polígonos elaborados a partir de LiDAR con el modelo NFFL de 0 a 9, que la cadena descarga del servicio WFS del geoportal IDEM, rasteriza a 25 m y lleva a la rejilla de 50 m por el modelo más frecuente. Fuera de la Comunidad, el mapa europeo de EFFIS (250 m, modelos 1 a 10).
- **Validación:** con humedad del 8 % en muertos, 100 % en vivos, viento a media llama de 5 mi/h y terreno llano, 11 de los 13 modelos quedan a menos del 10 % de las velocidades nominales de la tabla de Anderson (1982). El modelo 5 se desvía un −20 % y el 7 un +30 %; ambos tienen combustible vivo.
- **Humedad del combustible (decisión del 10-11-2026):** hora a hora. La del combustible muerto fino es la humedad de equilibrio que dan la temperatura y la humedad del aire de esa hora, con las ecuaciones de Simard (1968), las mismas del índice de Fosberg de la prealerta, y nunca por debajo del 2 %. La del muerto de 10 y 100 h, 1 y 2 puntos más. Con viento a mano, o si faltan datos, el muerto toma el valor fijo de "verano seco" (escenario de BehavePlus: 6, 7 y 8 % en muertos de 1, 10 y 100 h). La del **vivo** depende del mes de la ignición (decisión del 10-11-2026): 60 % de julio a septiembre, el escenario «muy seco» de BehavePlus, y 90 % el resto del año.
- **Viento:** del viento a 10 m de AEMET al viento a 6,1 m de Rothermel (factor 1/1,15) y de ahí al viento a media llama con un factor de ajuste por modelo (Albini y Baughman, 1979). **Pendiente de verificar** contra la publicación original.
- **Sin límite de viento (decisión del 10-11-2026):** no se aplica el límite de viento efectivo de Rothermel (U ≤ 0,9·I_R). Andrews, Cruz y Rothermel (2013, *International Journal of Wildland Fire* 22: 959-969) lo consideran demasiado restrictivo, y BehavePlus y FlamMap ya no lo aplican por defecto. Con él, el pasto apenas acelera con vientos fuertes: en Tres Cantos, el avance de los primeros 40 minutos se quedaba en 2,4 km.
- **Pendiente:** del MDT de 25 m del IGN, promediado a la rejilla de cálculo.
- **Viento y pendiente** se suman como vectores. La forma del frente es una elipse con la ignición en el foco y relación longitud/anchura de Anderson (1983), limitada a 8: 1,18 con 2 mi/h de viento efectivo, 1,59 con 5 y 2,78 con 10. **Corrección del 13-11-2026:** hasta entonces la fórmula recibía el viento en mi/h con los coeficientes para m/s, lo que daba elipses el doble o el triple de alargadas (3,19 con 5 mi/h) y fuegos demasiado estrechos.

### 3.2 Ruta del fuego (tiempo mínimo de recorrido)

Rejilla de 50 m en una ventana de 50 × 50 km centrada en la ignición (30 × 30 hasta el 13-11-2026). El tiempo de llegada a cada celda es el del camino más rápido desde la ignición (algoritmo de Dijkstra, como el método de tiempo mínimo de recorrido de FlamMap; Finney, 2002), con **32 vecinos**: los desplazamientos de hasta tres celdas. Con 16, la velocidad dependía del rumbo del viento respecto de la rejilla: con 13° de giro y 40 km/h, la cabeza avanzaba el 29 % de lo debido; con 32 vecinos, entre el 92 y el 100 % en cualquier rumbo hasta 60 km/h. Una arista que cruza una celda sin combustible no existe: una franja sin combustible, aunque sea de una celda, es barrera salvo el salto con viento fuerte. Horizonte de 24 horas.

El viento y la humedad pueden cambiar cada hora. Mientras no cambian se hace un solo cálculo. Al cambiar, el grafo se construye con las condiciones nuevas y lo quemado sigue ardiendo desde el instante del cambio: cada arista que el fuego había empezado a recorrer conserva la fracción recorrida, así que las condiciones nuevas solo actúan hacia delante. **Corrección del 13-11-2026:** hasta entonces cada hora se expandía desde la hora de llegada de cada celda quemada, de modo que el viento nuevo actuaba como si hubiera soplado desde el principio: en pasto llano, un viento de 60 km/h que entraba a la cuarta hora quemaba de golpe, en el minuto 180, las 2.900 ha que habría quemado en tres horas con ese viento. En cada tramo solo se construye el grafo del recuadro que el fuego puede alcanzar en él (la velocidad máxima por la duración, más el salto), lo que deja una simulación con viento horario en unos 10 segundos (implementación con `scipy.sparse.csgraph`).

**Salto de franjas sin combustible (decisión del 10-11-2026).** Con viento a 10 m de al menos 30 km/h, una celda que arde junto a una celda sin combustible puede encender celdas con combustible a menos de 300 m viento abajo, en un cono de ±45° alrededor de la dirección hacia la que sopla el viento, si entre ambas hay alguna celda sin combustible. El salto se recorre a la velocidad del fuego de la celda de origen en esa dirección. Representa las pavesas que hacen cruzar al fuego carreteras, avenidas y cortafuegos estrechos con viento fuerte; no representa los focos secundarios a kilómetros. Los parámetros se fijaron con el caso de Tres Cantos (apartado 3.11), donde un salto de 100 o 150 m no cruzaba la Gran Vía y uno de 300 m sí. El salto no conserva la fracción recorrida al cambiar de hora.

**Simulador visual del avance (decisión del 07-11-2026).** El motor guarda el mapa completo de tiempos de llegada (GeoTIFF de minutos) y lo entrega al visor como enteros de 16 bits. El visor pinta cualquier minuto sin recalcular: área quemada (llegada ≤ t), frente activo (quemado en los últimos 20 minutos), humo viento abajo (las zonas del apartado 3.7, calculadas por el servidor cada 5 minutos), y los activos, municipios e instalaciones Seveso se marcan en el minuto en que el fuego les llega. Reproductor con pausa, velocidad (1 a 60 minutos simulados por segundo), barra de tiempo arrastrable y saltos a los cortes de 1, 3, 6, 12 y 24 h.

### 3.3 Datos de viento

- **Primera hora:** observación de la estación de AEMET más cercana a la ignición con dato de viento, con su temperatura y humedad.
- **Horas siguientes:** predicción horaria del municipio de la ignición (8 rumbos y velocidad, temperatura y humedad). Si falta alguna hora, se mantiene la anterior.
- **Rachas (decisión del 10-11-2026):** en cada hora se usa el viento medio, salvo cuando AEMET prevé tormenta en su periodo, con una probabilidad de al menos el 40 % (el umbral de la prealerta), o cuando, en la primera hora, la racha observada alcanza el umbral amarillo de rachas de Meteoalerta de la zona (70 km/h en la metropolitana y el sur, 80 en la sierra). Entonces se usa la racha, con la dirección del viento medio (en la observación, la de la propia racha). Así se recogen los episodios convectivos sin inflar todas las horas.
- **Ventana de AEMET (10-11-2026):** AEMET da la última observación y la predicción horaria de unos tres días. Una ignición anterior a la observación en más de 3 horas, o posterior a la última hora prevista, no se simula con AEMET: se rechaza con un mensaje que lleva al viento a mano, en lugar de repetir el tiempo de ahora en otra fecha. Si la ignición es posterior a la observación, la primera hora también sale de la predicción.
- **Cuando no arde:** si el fuego no sale de la celda de ignición, el resultado lo explica: o el combustible muerto fino no baja en las 24 horas de su humedad de extinción (con las dos cifras), o no hay combustible continuo alrededor del punto.
- **Respaldo:** viento introducido a mano, constante o con un valor por hora (el modo hora a hora lo usa la validación del apartado 3.11).

### 3.4 Limitaciones del modelo de incendio

- **Combustibles:** dentro de la Comunidad, el mapa propio clasifica los pastos y buena parte de los cultivos como pasto fino (modelo 1), así que ya arden; lo que figura sin combustible (suelo urbano, agua, viales) actúa como barrera, salvo franjas de hasta 300 m con viento de 30 km/h o más. Fuera de la Comunidad, el mapa de EFFIS, de 250 m y con la vegetación de hacia el año 2000, trata los cultivos como barrera: allí los incendios agrícolas no se modelan.
- **No incluye** fuego de copas, focos secundarios lejanos ni extinción. Las pavesas solo se representan como salto de franjas sin combustible de hasta 300 m con viento fuerte (apartado 3.2).
- **Humedad del combustible:** la del muerto sigue a la del aire hora a hora, sin el retraso con que se secan y humedecen los combustibles gruesos; la del vivo es fija.
- **Ventana de 50 km:** el fuego no puede salir de ella. Si llega al borde, la respuesta da el minuto y el visor avisa de que desde entonces la superficie y los afectados se quedan cortos (decisión del 13-11-2026).
- **Viento homogéneo** en toda la ventana: no se ajusta al relieve.

### 3.5 Activos alcanzados

Un activo se considera **alcanzado cuando el fuego llega a menos de 250 m** de su ubicación: a alguna celda cuyo centro esté a 250 m o menos (un círculo; hasta el 13-11-2026 era un cuadrado de ±250 m, que llegaba a 350 m en diagonal y adelantaba la llegada). Casi todos los centros están en suelo urbano, sin combustible, y el fuego no entra en su celda: la amenaza les llega desde el borde.

**Avisos anticipados (decisión del 11-11-2026).** Los centros de vulnerabilidad alta y muy alta reciben un aviso en el mapa **3 horas antes** de que el fuego los alcance: un globo con su nombre y la cuenta atrás («llega en 2 h 35 min, hacia las 21:10») y una flecha por la **ruta del fuego**, desde el frente hasta el punto en que el fuego queda a menos de 250 m. Al llegar, el globo se pone rojo con la hora y se apaga a los 30 minutos simulados. **Desde el 12-11-2026, el mismo globo sirve para todos los avisos**: centros, carreteras y vías de tren (en el punto por el que llega el fuego), núcleos de población, instalaciones Seveso y la conducción, cada uno con su símbolo y su texto al ser alcanzado (probable corte, zonas activadas…). Se ven a la vez **los cinco más próximos, de cualquier tipo**, para no saturar el mapa; solo los centros llevan la flecha por la ruta del fuego. **En las 3 primeras horas (decisión del 13-11-2026), la antelación de avisos, isocronas y cascada es igual al tiempo que lleva el incendio** (en el minuto 10, lo que llega antes del minuto 20), para que la animación empiece con la ignición sola y se vea la secuencia de lo que va alcanzando el fuego. Es una decisión de presentación: la simulación es la misma.

La ruta se reconstruye hacia atrás sobre el mapa de tiempos de llegada. Empieza en la celda que arde antes a menos de 250 m del centro, la que fija su hora de llegada, y en cada paso toma la celda que arde antes entre las vecinas a dos celdas. Si ninguna arde antes, porque el fuego llegó saltando una franja sin combustible, busca a la distancia del salto. Así llega hasta la ignición, y se guarda un punto cada 100 m. Es una aproximación del camino de tiempo mínimo, no el camino exacto del cálculo: sirve para dibujar por dónde viene el fuego, que se curva con el viento, la pendiente y el combustible. En cada minuto, el visor dibuja solo el tramo que el fuego aún no ha recorrido.

**Isocronas (decisión del 11-11-2026).** Por delante del frente, el visor dibuja hasta dónde habrá llegado el fuego a cada hora en punto de las 3 siguientes. Son los contornos del mapa de tiempos de llegada a esas horas, simplificados a 50 m (una celda), sin manchas de menos de 1 ha ni huecos sin quemar de menos de 5 ha. Tienen la misma incertidumbre que la simulación de la que salen (apartado 3.12).

**Carreteras y vías de tren (decisión del 11-11-2026).** La red sale de la Base Topográfica Armonizada 2017 de la Comunidad: carreteras de calzada doble y única, con su código (A-6, M-607…), y vías de ferrocarril, metro y tranvía en uso, en superficie o elevadas. Los tramos soterrados no entran, porque el fuego no los alcanza, y tampoco las calles, caminos y sendas. Las pistas forestales tampoco (decisión del 12-11-2026): en el mapa despistaban más que ayudaban. Cada tramo se corta en trozos de unos 200 m, con un punto cada 25 m como máximo. Sin cortarlos, el fuego a 250 m de un extremo pintaría una carretera de varios kilómetros entera.

Un trozo queda **afectado por el fuego** desde el minuto en que el fuego llega a menos de 250 m de alguno de sus puntos, la misma distancia que para los centros: se marca en rojo como **probable corte**. Queda **bajo el humo** desde el primer paso de 5 minutos en que alguno de sus puntos entra en la zona de humo del apartado 3.7: se marca en gris como **visibilidad reducida**. El resumen da, para cada carretera, la primera hora de cada efecto y los kilómetros alcanzados por el fuego en 24 horas. Las pistas y cada clase de vía de tren se agrupan, porque no tienen código. No es una predicción de cortes de la DGT: indica dónde el fuego o el humo hacen probable que la vía deje de ser practicable.

**Núcleos de población (decisión del 12-11-2026).** Los nombres y la posición salen del Nomenclátor Geográfico Básico de España del IGN: las capitales de municipio, los núcleos de población y las entidades menores de la Comunidad (610 tras quitar la capital que aparece también como núcleo). El servicio no responde a tiempo con filtro por tipo, así que se descargan todos los lugares por recuadros de 0,2° y se filtran aquí. La forma del casco son las manchas urbanas del mapa base del IGN que ya prepara la cadena. Una población queda **alcanzada cuando el fuego llega a menos de 250 m de su casco**, la misma distancia que para los centros: de alguna celda de su mancha. Un núcleo pertenece a la mancha que lo contiene o que está a menos de 300 m; si varios comparten mancha (una urbanización pegada al pueblo), cada celda es del núcleo más cercano. Un núcleo sin mancha se toma como un punto. Limitación: las manchas son las del mapa base a escalas pequeñas, simplificadas a unos 30 m.

**Aviso en el mapa (decisión del 12-11-2026).** Las carreteras, las vías de tren y los núcleos de población a los que llegará el fuego reciben el mismo globo de aviso que los centros (apartado 3.5), en el punto por el que llega el fuego. Para cada carretera, ese punto es el primero de la carretera al que llega el fuego, no el primero que alcanza el humo.

**Trenes de Cercanías programados.** Con el horario de Renfe (GTFS estático del núcleo de Madrid, que cubre los 30 días siguientes), se buscan los trenes que pasan por una estación cuando ya está afectada por el fuego o el humo, dentro de las 24 horas simuladas. Se agrupan por línea y estación, en los dos sentidos, con la hora del primero, su destino y el número de trenes, y cuántos pasan ya con el fuego a menos de 250 m. Si la fecha simulada cae fuera del horario, se usan los trenes del mismo día de la semana dentro de él (decisión del 13-11-2026), y el visor lo dice. No se estima cuántas personas llevan (decisión del 30-10-2026). Complementa la foto de los trenes en tiempo real (apartado 7.8 de la memoria del demostrador), que dice qué trenes hay ahora en la zona, no cuáles pasarán.

### 3.6 Efecto cascada

En el visor, la franja activada de una conducción se dibuja como los 750 m alrededor de las celdas del núcleo que el fuego ha alcanzado hasta cada hora; los centros afectados se eligen, como se describe abajo, con la propia capa 6_12 del catálogo. La activación de cada instalación o conducción se anima (decisión del 11-11-2026): la ruta del fuego hasta ella en la hora previa, un pulso y las zonas que crecen desde ella, y flechas a los centros de vulnerabilidad alta y muy alta que quedan dentro. El visor marca las instalaciones y el punto de la conducción que el fuego alcanzará, con su hora, cuando aparece su flecha de aproximación.

**Línea de las conducciones (decisión del 11-11-2026).** El visor pinta siempre, en los tres modos, la línea de las conducciones. Como no hay trazado abierto con geometría, es el eje del núcleo de la capa 6_12, calculado por adelgazamiento (Zhang y Suen, 1984) sobre el núcleo a 25 m, con poda de ramitas de menos de 300 m y simplificación a 25 m. Es una aproximación: el núcleo es una banda de peligrosidad y la tubería va hacia su centro, no exactamente en él. En el entorno de Valdemorillo, el gasoducto de Enagás que registra OpenStreetMap pasa a menos de 1 km del eje calculado. El punto en que el fuego alcanza la conducción se coloca sobre esta línea.

No hay una fuente abierta con la ubicación de las instalaciones Seveso ni con el trazado de las conducciones (la BTA 1:10.000 de la Comunidad publica sus conducciones de hidrocarburos sin geometría). Se deducen del propio catálogo:

- **Instalaciones Seveso** (capas 6_3, 6_4 y 6_5): según la memoria, las zonas se trazan con los radios de intervención (nivel 2) y alerta (nivel 1) alrededor de cada instalación, y en los datos son círculos concéntricos. Se toma como instalación el **centro de cada zona de intervención** y se fusionan los centros de distintas capas a menos de 300 m: **44 instalaciones** a partir de 88 zonas. El radio de intervención es el equivalente de su zona de nivel 2. El de alerta, el de la zona de nivel 1 que la contiene si la instalación está sola en ella; cuando las zonas de alerta de varias instalaciones se tocan y forman una sola mancha (en el sur de la Comunidad, de unos 12 km de radio), se estima como el radio de intervención más la diferencia mediana entre alerta e intervención de las instalaciones aisladas de la misma capa (1.120 m en nube tóxica; decisión del 13-11-2026). Cuando el fuego llega a menos de 250 m del centro, se activan sus zonas de intervención y alerta como **amenaza derivada**, con los activos que contienen: «intervención» solo dentro de su propio radio de intervención, «alerta» hasta su radio de alerta y dentro de la zona del catálogo.
- **Conducciones** (capa 6_12): la capa es una franja trazada alrededor de gasoductos y oleoductos según su diámetro y presión. Se toma su **núcleo** (nivel 3, *moderado*) como trazado. Cuando el fuego entra en él, se activa la franja (nivel 2 o más) en 750 m alrededor del tramo alcanzado (la mayor distancia de efectos de la memoria: incendio de un charco de gasolinas, 738 m).

**Limitaciones:**

- El radio de alerta de las 7 instalaciones de nube tóxica cuya zona comparte mancha con otras es una estimación. Hasta el 13-11-2026 se les daba el radio de la mancha entera (12 km), que atribuía a una instalación los centros de las zonas de sus vecinas.
- El centro de la zona aproxima la instalación, que ocupa una parcela.
- Los gasoductos van enterrados: un incendio forestal rara vez los daña. El riesgo real está en las instalaciones de superficie (válvulas, estaciones de regulación), que el catálogo incluye en la franja pero no distingue.
- No se incluyen las vías de mercancías peligrosas ni las centrales eléctricas.

### 3.7 Ruta del humo

Modelo geométrico. Cada 5 minutos, el humo sale del área quemada hasta ese momento y se desplaza viento abajo con el viento de esa hora, abriéndose en un cono. La zona de humo es la envolvente convexa del área quemada y de esa misma área desplazada y ensanchada a cada lado. Es una sola geometría (decisión del 13-11-2026): la calcula el servidor, el visor la dibuja y con ella se marcan los centros, carreteras, vías y estaciones bajo el humo. Hasta entonces el visor dibujaba su propio cono minuto a minuto y el servidor marcaba con otro solo a las 1, 3, 6, 12 y 24 h, y no coincidían.

- Semiángulo del cono: 20°.
- Alcance: velocidad del viento × tiempo transcurrido desde la ignición, hasta 2 horas de permanencia, con un máximo de 25 km más allá del área quemada.
- Sin viento, el humo se queda en un radio de 500 m alrededor del fuego.

Parámetros provisionales. **No es un modelo de dispersión:** no tiene en cuenta la altura de la columna, la estabilidad atmosférica, el relieve ni las concentraciones. Señala qué activos pueden quedar a sotavento.

### 3.8 Municipios alcanzados

Los municipios de la Comunidad (límites de 2020) se rasterizan en la ventana de cálculo y para cada uno se toma el primer minuto en que el fuego entra en él. Sirven para las comunicaciones y para la lista del visor.

**Personas (decisión del 13-11-2026).** La crisis da dos cifras de personas, sin estimar alumnos ni pacientes, que los registros de centros educativos y sanitarios no publican:

- **Población de las celdas que toca el fuego:** la del Censo 2021 del INE en la rejilla de 1 km, con menores de 16 y mayores de 64, de cada celda a la que ha llegado el fuego. Cuenta la celda entera en cuanto arde una parte de ella, aunque el casco urbano no arda (el suelo urbano no es combustible): es una **cota alta** de la población de la zona afectada, no de la población en peligro. En el caso del vídeo (ignición junto a Torrejón de la Calzada el 15 de julio a las 15:00, viento del oeste a 20 km/h), 248.940 habitantes a las 24 h; ponderando cada celda por su fracción quemada serían 70.804.
- **Plazas de los centros sociales alcanzados:** las plazas autorizadas del registro de atención social, el único de los tres que las publica.

### 3.9 Comunicaciones ficticias (decisión del 07-11-2026)

A partir de la simulación, el visor genera para el instante mostrado un **mensaje para redes sociales** (texto geoposicionado con el municipio, la hora estimada, la superficie, los municipios afectados, la dirección del humo y los centros alcanzados) y un **falso ES-Alert** (el aviso a los móviles por celda que solo puede emitir la autoridad), con el área del aviso formada por los municipios en los que el fuego ha entrado o entra en la hora siguiente. El ES-Alert se emite al declarar la alerta y cada vez que esa área crece, y su texto es el de la última emisión (decisión del 13-11-2026). Se muestran en pantalla tal como saldrían; no se publica nada en ninguna red ni se envía ningún aviso real.

### 3.10 Alertas automáticas (NASA FIRMS)

Focos de calor de las últimas 24 horas de los tres satélites con sensor VIIRS (Suomi NPP, NOAA-20 y NOAA-21), filtrados con el límite de la Comunidad.

- Cada detección es un píxel de 375 m: indica que hay fuego en ese píxel, no su perímetro.
- Unas 6 pasadas al día entre los tres satélites. El humo denso y las nubes impiden la detección. Los datos casi en tiempo real llegan unas horas después de la pasada.
- **Fuentes fijas:** un foco con detecciones a menos de 500 m en 3 o más días de la última semana se marca como posible fuente fija (industria, vertedero). En octubre de 2026, las únicas detecciones en la Comunidad eran dos de estas fuentes, repetidas noche tras noche.

### 3.11 Validación con un caso real: Tres Cantos, 11 de agosto de 2025 (decisión del 10-11-2026)

**Por qué este caso.** Fue una sola ignición que corrió en pocas horas, compatible con el horizonte de 24 horas y la ventana de cálculo del modelo. Se descartó el incendio de la Sierra Oeste de julio de 2026, mucho mayor, porque fueron tres focos que se unieron y ardieron varios días con extinción, y no hay publicados el punto ni la hora de cada foco.

**Lo que se sabe de lo ocurrido.**

| Dato | Valor | Fuente |
|---|---|---|
| Inicio | 19:45 del 11-08-2025, en Nuevo Tres Cantos | Seguimiento del Ayuntamiento de Colmenar Viejo y prensa |
| Avance | Hacia el sureste; más de 6 km en unos 40 minutos | Ayuntamiento de Colmenar Viejo y prensa |
| Viento | Tormenta seca con rachas de más de 70 km/h | Declaraciones del consejero, recogidas por el Ayuntamiento de Colmenar Viejo |
| Superficie | Más de 1.500 ha a las 15:00 del 12-08; 2.037 ha al final | Ayuntamiento de Colmenar Viejo; Copernicus EFFIS (área quemada 278333) |
| Evolución | Perimetrado durante la noche del 11 al 12; controlado el 13 | Ayuntamiento de Colmenar Viejo |
| Focos de satélite | 18 detecciones VIIRS a las 03:49 (Suomi NPP) y a las 04:11 (NOAA-20) del 12-08 | NASA FIRMS, ficheros anuales de España de 2025 |

**Cómo se simula.**

- **Punto de ignición:** no hay coordenadas oficiales publicadas. Se usa un punto estimado por el proyecto, 40,6141 N y 3,6936 O, en los pastos de la periferia noreste de la tercera fase de Nuevo Tres Cantos, junto a la Gran Vía y antes del monte. Cae dentro del perímetro de EFFIS, a 29 m de su borde noroeste, sobre pasto con arbolado o matorral. El visor lo indica como punto estimado.
- **Viento:** el medio horario medido en la estación de Colmenar Viejo de la Red de Calidad del Aire de la Comunidad de Madrid, a unos 9 km, un valor distinto en cada hora. La red rotula los valores de h01 a h24 sin indicar el huso; **son horas UTC**, porque el máximo de radiación solar cae en h13 en junio y en diciembre, sin cambio de hora, y el mediodía solar de Madrid es hacia las 12:15 UTC. Cada valor se toma como el de la hora que termina en su marca, y a cada hora de simulación le corresponde la hora de la red que contiene su punto medio. En las dos primeras horas el viento medio fue del oeste y del oeste-noroeste, a 8-12 km/h, y después flojo del este.
- **Rachas y extinción:** el viento medio horario no recoge las rachas de la tormenta seca; se añade la racha registrada por AEMET en la primera hora (paso 3 de abajo). El modelo no tiene extinción.

**Métricas.** El mapa de tiempos de llegada se compara con el perímetro de EFFIS rasterizado en la misma rejilla de 50 m:

- superficie simulada a 1, 3, 6, 12 y 24 horas y a las 15:00 del día siguiente, frente a la real;
- coincidencia espacial con el **índice de Sørensen**, 2·|S∩R| / (|S| + |R|), de 0 a 1, en cada hora, con la mejor hora; y qué parte del perímetro real queda quemada y qué parte de lo simulado cae fuera de él;
- dirección del avance: rumbo desde la ignición al centro del área real y al centro del área simulada a 24 horas;
- avance: distancia máxima recorrida a los 40 minutos, frente a los 6 km reales;
- focos de satélite: cuántos caen, a su hora, a menos de 375 m (un píxel VIIRS) del área simulada como quemada.

**Ajuste de los parámetros (10-11-2026).** Este es el caso con el que se fijaron los parámetros del modelo, en cinco pasos, cada uno sobre el anterior. **La tabla se calculó con el modelo anterior a las correcciones del 13-11-2026** (forma de la elipse, cambio horario de las condiciones y 32 vecinos, apartados 3.1 y 3.2), así que sus cifras ya no son las del modelo; se conserva porque documenta cómo se eligieron los parámetros. El resultado con el modelo actual va después.

1. El mapa europeo de EFFIS, con el viento medio medido y la humedad fija de verano.
2. El mapa de combustibles de la Comunidad.
3. La racha máxima del día registrada por AEMET en Colmenar Viejo (19,7 m/s, 71 km/h) en la primera hora, con la dirección de su parte diario (noroeste), y la humedad del combustible de cada hora con la temperatura y la humedad del aire medidas.
4. La racha con la dirección medida a esa hora junto al incendio (oeste; decisión del 10-11-2026: la del parte diario es de otra estación y otra hora, y empuja el fuego hacia el casco urbano) y el salto de franjas sin combustible de hasta 300 m.
5. Como usa ahora el modelo: además, sin el límite de viento de Rothermel y con el combustible vivo al 60 % en agosto.

| Medida | Real | 1. EFFIS | 2. Mapa de la Comunidad | 3. Racha del NO y humedad | 4. Racha local y salto | 5. Sin límite de viento y vivo de verano |
|---|---|---|---|---|---|---|
| Superficie en la primera hora | | 0 ha | 4 ha | 4 ha | 106 ha | 302 ha |
| Avance en los primeros 40 minutos | Más de 6 km | 0,1 km | 0,2 km | 0,3 km | 2,4 km | 4,5 km |
| Tiempo hasta los 6 km | Unos 40 min | | | | | 76 min |
| Superficie a las 15:00 del 12-08 | Más de 1.500 ha | 205 ha | 753 ha | 759 ha | 3.426 ha | 6.870 ha |
| Mejor coincidencia con el perímetro (índice de Sørensen) | | 0,46, a las 23 h | 0,65, a las 21 h | 0,60, a las 21 h | 0,75, a las 16 h | 0,62, a las 16 h |
| Perímetro real alcanzado en esa hora | | 41 % | 80 % | 80 % | 75 % | 88 % |
| Simulado fuera del perímetro en esa hora | | 47 % | 45 % | 53 % | 25 % | 53 % |
| Focos de satélite de las 03:49 y las 04:11 dentro de lo simulado a su hora | 18 | 0 | 0 | 0 | 8 | 10 |
| Hasta las 8 h, con el real ya perimetrado: superficie, Sørensen y rumbo del avance | 2.035 ha al final; este-sureste (107°) | | | | 949 ha; 0,57; 104° | 1.653 ha; 0,59; 98° |

**Lectura.**

- **El combustible era el primer problema.** EFFIS, con 250 m y la vegetación de hacia el año 2000, trataba los pastos y cultivos de alrededor como barrera. El mapa de la Comunidad da pasto fino en el 53 % del perímetro, que es lo que ardió, y la coincidencia sube de 0,46 a 0,65.
- **El segundo, la dirección de la racha.** La racha del parte diario de AEMET (noroeste) empuja el fuego hacia el casco urbano de Tres Cantos, que no arde. Con la dirección medida junto al incendio a esa hora (oeste), el fuego corre hacia el este-sureste, como el real.
- **El tercero, la franja sin combustible.** Al este del punto de ignición hay unos 200 m sin combustible (la Gran Vía y su glorieta). Con el salto de hasta 300 m, el fuego la cruza como el real: 106 ha en la primera hora y 663 ha a las 6 horas con menos del 10 % fuera del perímetro real; a las 16 horas, 2.015 ha frente a las 2.035 reales y la mejor coincidencia, 0,75.
- **El cuarto, el límite de viento de Rothermel.** Con él, el pasto apenas aceleraba con la racha de 71 km/h y la carrera se quedaba en 2,4 km en 40 minutos. Sin él, como en BehavePlus y FlamMap actuales, y con el combustible vivo de agosto, el fuego simulado recorre 4,5 km en 40 minutos y llega a los 6 km a los 76 minutos (el real, en unos 40); quema 302 ha en la primera hora y 1.653 ha a las 8 horas, avanzando hacia los 98°.
- **Lo que no se reproduce: la extinción.** El fuego real quedó perimetrado esa noche; el simulado sigue creciendo después: a las 15:00 del día 12 multiplica por cuatro la superficie real y a las 24 horas por diez. Por eso la mejor coincidencia global baja de 0,75 a 0,62 al hacer el fuego más rápido: lo que gana en las primeras horas lo pierde después por desbordar. Para una herramienta de crisis cuentan las primeras horas, que deciden cuándo llega el fuego a cada centro; las de después dependen de la extinción, que el modelo no tiene.
- **La humedad del día** apenas cambia este caso: esa tarde, con 29 a 33 °C y entre el 19 y el 31 % de humedad del aire, el combustible fino sale en torno al 5,5 %, casi igual que el 6 % fijo.

**Resultado con el modelo actual (13-11-2026).** Con las correcciones, el fuego simulado quema 1.106 ha en la primera hora y llega a los 6 km a los 46 minutos (el real, en unos 40), avanzando hacia los 119° (el real, 107°). A las 8 horas, cuando el real ya estaba perimetrado, quema 3.364 ha, con una coincidencia de 0,54 y el 57 % de lo simulado fuera del perímetro; a las 15:00 del día 12, 6.030 ha frente a las más de 1.500 reales. 11 de los 18 focos de satélite caen dentro de lo simulado a su hora. Las primeras horas se parecen mucho más a lo ocurrido; lo que sigue desbordando es lo que la extinción paró.

La conclusión para el uso del modelo: **representa la propagación con el viento medio, no los episodios convectivos**, que son los que producen las carreras más peligrosas. En una crisis real, la simulación debe leerse junto con las rachas previstas y los avisos de AEMET, y una tormenta seca en la zona es motivo para considerar que el fuego puede ir mucho más rápido de lo simulado.

**Reproducir.** `python -m procesamiento.incendio.validacion --lon … --lat …` (o el paso 8 de la cadena, con el punto fijado en el módulo). El resultado se ve en el visor, modo de gestión de crisis, «Validación con un caso real»: la simulación se carga en el reproductor con el perímetro de EFFIS y los focos de satélite superpuestos (estos aparecen a su hora) y una tabla que compara lo simulado con lo ocurrido.

### 3.12 Validación con siete incendios (recalculada el 13-11-2026)

Un solo caso no basta: en Tres Cantos, girar el viento 15° o mover la ignición 100 m cambia el resultado tanto como cualquiera de los ajustes del apartado 3.11, y además es el caso con el que se fijaron los parámetros. Por eso el modelo se compara con siete incendios de la Comunidad que ardieron desde un solo punto en una tarde o una noche, con perímetro de Copernicus EFFIS y una hora y un lugar de inicio publicados. **n = 7**: es un contraste, no una estimación estadística del error.

**Cómo se simula cada caso.**

- **Viento y humedad:** de la estación de la Red de Calidad del Aire más cercana al punto de ignición con viento válido, hora a hora, con la misma regla en todos los casos. En Tres Cantos esa estación es San Sebastián de los Reyes, no la de Colmenar Viejo del apartado 3.11, y se mantiene la racha de 71 km/h en la primera hora.
- **Incertidumbre:** hasta 15 simulaciones por caso: cinco puntos de ignición (el estimado y cuatro a 200 m, al norte, este, sur y oeste) por tres direcciones del viento (la medida y girada 15° a cada lado). Los puntos que caen sin combustible se descartan.
- **Hora de comparación fijada de antemano** (decisión del 13-11-2026): la de contención publicada del caso (8 horas en Tres Cantos, Colmenar Viejo y Villa del Prado; 6 en El Molar) y, donde no se conoce, 8 horas. Antes se daba la mejor coincidencia de las 24 horas, elegida después de ver el resultado; eso borra el error de ritmo (un fuego lento acaba llenando el perímetro a las 18 horas y puntúa igual que uno rápido), así que ahora solo se da como referencia.
- **Modelo nulo:** un círculo centrado en la ignición con la misma superficie que la simulada a esa hora. Si el modelo no acierta más que el círculo, su forma y su dirección no aportan nada sobre «un fuego de ese tamaño alrededor del punto».
- **Métricas a esa hora:** coincidencia con el perímetro real (índice de Sørensen), la del círculo y la diferencia (la ganancia del modelo), la parte de lo simulado que cae fuera del perímetro real y la razón entre la superficie simulada y la real final. Se da la mediana de las simulaciones de cada caso y, entre paréntesis, el rango.
- **Ajuste y evaluación por separado:** Tres Cantos, con el que se fijaron los parámetros, se resume aparte de los otros seis, que son los de evaluación.

**Resultados con el modelo actual (13-11-2026).**

| Incendio | Superficie final (EFFIS) | Estación | Simulaciones | Hora | Coincidencia del modelo | Del círculo | Ganancia | Simulado fuera | Superficie simulada / real |
|---|---|---|---|---|---|---|---|---|---|
| Tres Cantos, 11-08-2025 (ajuste) | 2.035 ha | San Sebastián de los Reyes, 6,9 km | 9 | 8 h | 0,45 (0,25-0,55) | 0,52 | −0,05 | 53 % | 0,97 |
| Tres Cantos y Colmenar Viejo, 22-08-2024 | 534 ha | Colmenar Viejo, 7,6 km | 6 | 8 h | 0,42 (0,36-0,44) | 0,16 | +0,26 | 70 % | 2,3 |
| Loeches, 31-07-2024 | 756 ha | Rivas Vaciamadrid, 8,7 km | 15 | 8 h* | 0,32 (0,30-0,35) | 0,17 | +0,15 | 74 % | 1,6 |
| El Molar y Pedrezuela, 05-08-2024 | 206 ha | Guadalix de la Sierra, 10,9 km | 9 | 6 h | 0,44 (0,13-0,78) | 0,36 | +0,09 | 62 % | 1,3 |
| Aranjuez, 05-07-2022 | 264 ha | Aranjuez, 4,0 km | 9 | 8 h* | 0,47 (0,00-0,53) | 0,27 | +0,18 | 40 % | 0,6 |
| Aranjuez, 08-08-2025 | 263 ha | Aranjuez, 3,4 km | 12 | 8 h* | 0,31 (0,22-0,44) | 0,39 | −0,08 | 72 % | 1,2 |
| Villa del Prado, 29-06-2025 | 123 ha | Villa del Prado, 2,2 km | 15 | 8 h | 0,17 (0,14-0,18) | 0,15 | +0,01 | 91 % | 11,1 |
| **Mediana de los seis de evaluación** | | | | | **0,37** (0,17-0,47) | **0,22** | **+0,12** | **71 %** | **1,4** |

\* Sin hora de contención publicada: 8 horas, fijada de antemano.

Puntos de ignición: en Colmenar Viejo 2024, la glorieta de Casas Viejas; en El Molar, detrás del cementerio; en Aranjuez 2022, la cuneta de la A-4 en el km 49; en Aranjuez 2025, los altos de Sotomayor junto a la Casa de la Monta (una sola fuente). En Loeches y Villa del Prado la prensa no precisa el lugar y se toma el extremo del perímetro a barlovento, a 100 m de su borde.

**Lectura.**

- **El modelo aporta sobre el círculo en cuatro de los seis casos de evaluación** (ganancia de +0,09 a +0,26): acierta hacia dónde va el fuego. En Aranjuez 2025 lo hace peor que el círculo y en Villa del Prado, igual.
- **Sobrestima la superficie**: mediana de 1,4 veces la real a la hora de comparación, y 11 veces en Villa del Prado, que se controló pronto, con el 91 % de lo simulado fuera del perímetro. Es la extinción, que el modelo no tiene: cuanto antes se controló el incendio real, más desborda el simulado.
- **En Tres Cantos, el caso de ajuste, no supera al círculo** a las 8 horas: con la estación más cercana (San Sebastián de los Reyes, que marca viento del noreste tras la primera hora) el fuego se abre hacia el sur; con el viento de Colmenar Viejo (apartado 3.11) acierta la dirección. Lo que más pesa es el viento en el punto.
- **Para qué sirve, y para qué no.** Da la dirección y el orden de magnitud de las primeras horas, que es lo que decide qué centros se alcanzan primero; no da la superficie final, que depende de la extinción. La herramienta lo usa así: para ordenar por tiempo de llegada, no para predecir hectáreas.
- **Antes de las correcciones del 13-11-2026**, con la mejor hora de las 24, la mediana era 0,44; a la hora fijada y con el modelo corregido es 0,37. La comparación de configuraciones del 10-11-2026 (salto, límite de viento, cuatro estaciones) se hizo con el modelo anterior y no se ha repetido.

**Reproducir.** `python -m procesamiento.incendio.casos`, que escribe `datos/procesados/validacion/conjunto.json` con cada simulación y el resumen de ajuste y evaluación. Son 75 simulaciones y tardan unos 13 minutos.

## 4. Prealerta a 7 días

La prealerta responde a dónde está el riesgo focal en los próximos siete días: qué fenómenos meteorológicos adversos prevé AEMET para cada municipio, a qué activos afectan directamente y qué peligros del catálogo activan.

### 4.1 Fuentes

- **Previsión municipal diaria a 7 días** de AEMET OpenData, para los 179 municipios: temperaturas máxima y mínima, humedad relativa máxima y mínima, viento medio por periodos, racha máxima (cuando AEMET la da), probabilidad de precipitación, cota de nieve y estado del cielo. Se pide una vez al día y se guarda en caché; el servidor la actualiza en segundo plano y, si AEMET falla, reintenta cada 15 minutos. Si tres municipios seguidos no responden, la actualización se interrumpe y se sirve la última previsión disponible, con su fecha de elaboración.
- **Previsión horaria a 3 días**, solo para los municipios cuya diaria anuncia precipitación (probabilidad ≥ 30 %), tormenta o nieve en esos días: precipitación y nieve por hora, racha por hora y probabilidad de tormenta por tramos. De ella salen la lluvia máxima en 1 hora y en 12 horas deslizantes, la nieve acumulada en el día, la racha máxima y la probabilidad de tormenta.
- **Avisos oficiales del Plan Meteoalerta**, por el canal público de AEMET sin clave: el RSS de avisos enlaza un paquete con los ficheros CAP (Common Alerting Protocol) vigentes y previstos hasta pasado mañana. De cada aviso se toman la zona, el fenómeno, el nivel, el umbral, la probabilidad, la vigencia y el polígono. Si AEMET no responde, se usa el canal de Meteoalarm (red europea que redistribuye los avisos de AEMET), que no trae polígono.
- **Delimitación oficial de las zonas de aviso** (shapefile v6 de AEMET). La Comunidad de Madrid tiene tres: Sierra de Madrid (722801), Metropolitana y Henares (722802) y Sur, Vegas y Oeste (722803). Cada municipio se asigna a la zona con la que más superficie comparte: 75, 44 y 60 municipios.

### 4.2 Niveles y umbrales

Los niveles son los del Plan Meteoalerta: verde (sin aviso), amarillo, naranja y rojo. Cascada traduce la previsión de cada municipio y día a niveles con **los umbrales que el Plan Meteoalerta fija para su zona de aviso** (anexo de umbrales, versión de 31 de mayo de 2022):

| Zona | Tmáx (°C) | Tmín (°C) | Racha (km/h) | Lluvia 12 h (mm) | Lluvia 1 h (mm) | Nieve 24 h (cm) |
|---|---|---|---|---|---|---|
| Sierra de Madrid | 34 / 37 / 40 | −6 / −10 / −14 | 80 / 100 / 140 | 40 / 80 / 120 | 15 / 30 / 60 | 5 / 20 / 40 |
| Metropolitana y Henares; Sur, Vegas y Oeste | 36 / 39 / 42 | −4 / −8 / −12 | 70 / 90 / 130 | 40 / 80 / 120 | 15 / 30 / 60 | 2 / 5 / 20 |

(amarillo / naranja / rojo). La racha es la horaria si existe y, si no, la máxima diaria; lluvia y nieve solo se evalúan con la previsión horaria (la diaria no da cantidades). La tormenta se gradúa con la probabilidad horaria de AEMET (≥ 40 % amarillo, ≥ 70 % naranja; criterio propio) o, sin horaria, con el estado del cielo (tormenta prevista: amarillo). Niebla, polvo en suspensión y granizo solo entran por aviso oficial.

Donde hay aviso oficial de AEMET para la zona del municipio y el día, el nivel del aviso manda sobre el calculado y se etiqueta con su origen («aviso AEMET»); el resto se etiqueta como calculado por Cascada («previsión»). Los avisos oficiales solo llegan hasta pasado mañana: de ahí en adelante toda la prealerta es cálculo propio sobre la previsión.

### 4.3 Peligro meteorológico de incendio

AEMET publica su predicción de riesgo de incendio solo como imagen. Cascada calcula el **índice meteorológico de peligro de incendio de Fosberg (1978)**, que combina la humedad de equilibrio del combustible fino y el viento, con la temperatura máxima, la humedad relativa mínima y el viento máximo previstos para el día:

- Humedad de equilibrio *m* (%) por tramos de humedad relativa *h* (%) y temperatura *T* (°F): si *h* < 10, *m* = 0,03229 + 0,281073·*h* − 0,000578·*h*·*T*; si 10 ≤ *h* < 50, *m* = 2,22749 + 0,160107·*h* − 0,01478·*T*; si *h* ≥ 50, *m* = 21,0606 + 0,005565·*h*² − 0,00035·*h*·*T* − 0,483199·*h*.
- η = 1 − 2(*m*/30) + 1,5(*m*/30)² − 0,5(*m*/30)³.
- FFWI = η · √(1 + *U*²) / 0,3002, con *U* el viento en millas por hora.

Clases propias de Cascada: menos de 15 bajo, menos de 30 moderado, menos de 50 alto (amarillo), menos de 70 muy alto (naranja) y el resto extremo (rojo). Por ejemplo, 35 °C, 20 % de humedad y 30 km/h dan 47 (alto); 40 °C, 10 % y 50 km/h dan 89 (extremo); un día de invierno con 10 °C, 70 % y 10 km/h da 8 (bajo).

### 4.4 Efecto directo y activación de peligros

Dos lecturas, las del diseño funcional:

- **Efecto directo sobre las personas.** Las temperaturas máximas afectan a los centros residenciales y de día, las escuelas infantiles, la educación especial, los hospitales y los centros de diálisis; las temperaturas mínimas y las nevadas, a los residenciales y de día. Si hubiera centros sensibles ubicados, se contarían sin mostrarse en el frío y la nieve; con el criterio del 13-11-2026 no los hay. El nivel del activo es el del fenómeno en su municipio.
- **Activación de peligros basales.** Un fenómeno en amarillo o más activa una capa del catálogo en los activos del municipio con peligrosidad moderada o superior en esa capa; el riesgo que se muestra es el basal de la capa (matriz del catálogo). Tabla de activación: vientos o Fosberg → incendios forestales (3_1); lluvias o tormentas → avenidas y crecidas (2_1) y torrencialidad en cauces (2_2); nevadas → transporte por carretera (6_16); vientos → derrumbes y colapso de edificaciones (6_27).

Las 13 capas de peligrosidad meteorológica del catálogo (1_1 a 1_13) describen la propensión climática de cada punto (periodos de retorno, probabilidad anual de olas de calor…), no una previsión: se ofrecen como capas de contexto en el modo Prealerta, muestreadas en cada activo y teseladas hasta el zoom 11, porque son zonas suaves.

### 4.5 Limitaciones de la prealerta

- La previsión municipal de AEMET es un valor por municipio y día: dentro de Madrid capital o de los municipios serranos con mucho desnivel, la realidad varía.
- Las cantidades de lluvia y nieve solo existen en la previsión horaria, que llega a tres días; a partir del cuarto día solo se dispone de la probabilidad de precipitación, que no da nivel.
- El índice de Fosberg se calcula con valores diarios (máxima, humedad mínima, viento máximo), que no coinciden necesariamente en la misma hora; no incluye la sequedad acumulada del combustible (a diferencia del FWI canadiense) ni el estado real de la vegetación.
- Los umbrales de tormenta y las clases de Fosberg son criterios propios de Cascada, no de AEMET.
- La activación de peligros basales es un cruce cualitativo (fenómeno en el municipio × peligrosidad en el punto), sin modelo físico de cada peligro.

## 5. Privacidad

- No hay usuarios ni se recogen datos personales.
- Los datos personales de los conjuntos de centros (teléfonos, correos, webs) no se publican.
- Los centros de colectivos en situación de protección solo aparecen como recuento de centros y plazas, en el mapa, en las consultas y en las salidas de la crisis.
- Los 177 centros con algún dato reservado por la Comunidad no se ubican.
- La lista de instalaciones Seveso deducida del catálogo no se publica en el repositorio: se regenera en local a partir de las capas públicas (uso responsable).

## 6. Referencias

- AEMET (2022). *Plan Meteoalerta. Plan nacional de predicción y vigilancia de fenómenos meteorológicos adversos. Anexo 1: umbrales*. Versión de 31 de mayo de 2022.
- Albini, F. A. (1976). *Estimating wildfire behavior and effects*. USDA Forest Service, INT-GTR-30.
- Albini, F. A. y Baughman, R. G. (1979). *Estimating windspeeds for predicting wildland fire behavior*. USDA Forest Service, INT-RP-221.
- Anderson, H. E. (1982). *Aids to determining fuel models for estimating fire behavior*. USDA Forest Service, INT-GTR-122.
- Anderson, H. E. (1983). *Predicting wind-driven wild land fire size and shape*. USDA Forest Service, INT-RP-305.
- Comunidad de Madrid (2025). *Catálogo de Riesgos Potenciales de la Comunidad de Madrid. Memoria metodológica*. Noviembre de 2025.
- European Forest Fire Information System (2017). *European Fuel Map*, contrato JRC n.º 384347. Copernicus Emergency Management Service.
- Finney, M. A. (2002). Fire growth using minimum travel time methods. *Canadian Journal of Forest Research*, 32(8), 1420–1424.
- Fosberg, M. A. (1978). Weather in wildland fire management: the fire weather index. *Proceedings of the Conference on Sierra Nevada Meteorology*, American Meteorological Society, 1–4.
- Rothermel, R. C. (1972). *A mathematical model for predicting fire spread in wildland fuels*. USDA Forest Service, INT-RP-115.

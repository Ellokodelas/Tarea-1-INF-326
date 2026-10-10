# Discusión de la arquitectura

## Trade-offs

### Avisos pequeños y detalle por HTTP

El publicador envía el ID y las coordenadas. Con eso cada ciudad decide si necesita el resto de los datos. Por ejemplo, en el caso simulado de Valparaíso, Arica recibe el aviso pero no pide el detalle, mientras que Coquimbo y Concepción sí lo consultan.

Esto evita enviar información completa a ciudades lejanas. El costo es que las ciudades interesadas hacen una petición adicional y dependen de la API para obtener el detalle. Si casi todas consultaran por cada sismo, o si el detalle fuera muy pequeño, las peticiones HTTP podrían costar más que el ahorro. La ventaja depende de la ubicación de los sismos y del tamaño de los mensajes.

### Una cola por ciudad

Con una cola independiente, cada ciudad recibe todos los avisos y los procesa a su ritmo. Si Arica se desconecta por un momento, las otras ciudades pueden seguir funcionando y los avisos de Arica quedan en su cola. Una sola cola compartida repartiría los avisos entre ciudades, por lo que algunas no se enterarían del sismo.

A cambio, RabbitMQ guarda y entrega una copia por ciudad, y todas calculan la distancia aunque finalmente descarten el aviso. Para cinco ciudades, esta organización resulta fácil de seguir. Si se agregaran muchos suscriptores, tendría sentido evaluar una distribución por zonas. Eso reduciría las copias, pero complicaría el caso de ciudades cuyos radios se superponen.

### Manejo de mensajes y fallos

Las colas y los mensajes se conservan ante reinicios normales usando el volumen de RabbitMQ. El publicador espera la confirmación del broker y cada suscriptor confirma su copia después de procesarla. Esto requiere guardar datos y enviar confirmaciones, pero permite que una ciudad reciba avisos que llegaron mientras estaba desconectada.

Para mantener sencilla la implementación, una consulta HTTP fallida se registra y el aviso se descarta para esa ciudad. No hay recuperación automática: si la API vuelve a funcionar, se puede publicar nuevamente el evento. El costo es claro: una ciudad puede quedarse sin el detalle de un sismo por una falla temporal. En un servicio donde no se puedan perder avisos, habría que agregar una forma de conservarlos y reintentarlos. También pueden repetirse consultas si un mensaje se publica o se entrega otra vez.

El sistema tiene un solo RabbitMQ y una sola API. Esto facilita ejecutarlo en un computador, pero cada uno representa un punto de fallo. En el dominio de los sismos, recibir información demasiado tarde o perderla puede reducir su utilidad; el nivel de recuperación necesario dependería del uso del servicio.

### Datos en memoria y componentes separados

La API carga el catálogo desde un JSON. Esto permite probar siempre los mismos casos y evita instalar una base de datos. La limitación es que el catálogo queda fijo durante la ejecución. Para incorporar nuevos registros habría que cambiar esa parte del sistema. El aviso y su detalle también deben mantener el mismo ID y las mismas coordenadas.

Separar publicador, API y suscriptores permite cambiar una parte sin rehacer las demás. Los cinco suscriptores comparten código, así que una corrección al filtro se aplica a todas las ciudades. El costo es tener varios procesos y conexiones que configurar. Docker Compose reúne esa configuración y ordena el inicio de los servicios.

## Cómo aplicar Back of the Envelope

Para estimar la carga, primero se definiría qué sismos va a notificar el servicio. Publicar todos los registrados o sólo los que superen cierta magnitud produce cantidades distintas de avisos. La implementación actual publica todos los eventos de su catálogo y filtra únicamente por distancia.

Con un período representativo del catálogo histórico del CSN se podría contar cuántos eventos llegan por intervalo y revisar sus momentos de mayor actividad. También interesa contemplar las réplicas: ocurren en la misma zona general después de un sismo mayor y su frecuencia disminuye con el tiempo, según el [USGS](https://www.usgs.gov/faqs/foreshocks-aftershocks-whats-difference). Por eso se considerarían tanto períodos tranquilos como períodos con muchos avisos seguidos. La hora de publicación sería el dato más útil para medir la llegada al sistema; usar la hora de ocurrencia sería una aproximación si los informes se publican con retraso.

Luego se aplicarían las coordenadas históricas al mismo filtro de 500 km para saber qué ciudades pedirían detalle. Un evento cercano a Valparaíso y otro cercano a Arica no generan las mismas consultas. RabbitMQ entrega una copia a cada ciudad, pero la carga de la API depende de cuántas estén interesadas en cada evento.

Para estimar el tráfico se relacionaría la frecuencia de avisos con el tamaño del mensaje y la cantidad de copias. A eso se sumaría el tamaño de las respuestas HTTP por la cantidad de consultas, considerando también los encabezados de los protocolos. Para el almacenamiento, se usaría la llegada de mensajes durante el tiempo que se quiera soportar una ciudad desconectada. Un período con muchas réplicas sería especialmente relevante para ese cálculo.

Finalmente, se mediría cuánto demora la API en responder y cuánto tarda cada suscriptor en procesar un aviso. Al comparar la capacidad de atención con la llegada de mensajes, se podría evaluar si una sola API y un solo broker bastan o si las colas crecerían durante los períodos de mayor actividad. Esa estimación serviría para decidir si conviene aumentar recursos o agregar instancias, y después se contrastaría con pruebas de carga. Los pocos eventos de la demostración permiten comprobar el recorrido, pero no representan la frecuencia real de sismos.

## Referencias

- Presentaciones de clases de Arquitectura de Software (INF326).
- [CSN: informe del sismo usado en el catálogo](https://sismologia.cl/sismicidad/informes/2026/10/385245.html).
- [RabbitMQ: publish-subscribe](https://www.rabbitmq.com/tutorials/tutorial-three-python) y [confirmaciones de mensajes](https://www.rabbitmq.com/docs/confirms).
- [USGS: sismos precursores y réplicas](https://www.usgs.gov/faqs/foreshocks-aftershocks-whats-difference).

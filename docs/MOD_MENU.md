# Que hace libModMenu.so y por que no se carga tal cual

`libModMenu.so` es el mod nativo de Reawaken (3 MB). Lo carga el Java del apk al arrancar. Analizandolo:

- Instala hooks en tiempo de ejecucion con un motor de hooking propio (estilo Substrate/Dobby, hay cadenas
  `MSHookFunction` / `A64_HOOK`) y parchea memoria con `KittyMemory` ("PATCH FAILED ...").
- Su constructor (`lib_main`) solo registra la hora y lanza un hilo (`hack_thread`); ese hilo hace `dlopen("libuaf.so")`,
  `dlsym("Java_com_ubisoft_uaf_UAFJNILib_InitGlobal")` y engancha `InitGlobal`. Lo demas lo instala despues.
- Los parches de trucos tienen la forma `parche(base_de_libuaf + OFFSET, bytes_hex)` con una bandera on/off
  (ejemplo real: offset `0xc8c86c`, cadenas `001c005360150034` / `60aa193960150036`). Son interruptores del menu.
- Casi todas sus cadenas estan cifradas con XOR en tiempo de ejecucion (por eso no aparecen nombres de funciones del
  motor), asi que reconstruir todos los hooks leyendo ensamblador es muy costoso.
- Tambien incluye la capa de red propia de Reawaken (guardado en la nube, amigos, multijugador) y mensajes como
  "tracking event skipped: Ubisoft services not ready": el mod esta pensado para jugar **sin los servidores de Ubisoft**.

## Por que no se puede ejecutar dentro del cargador de la Switch

Necesita escribir sobre el codigo de `libuaf.so` ya cargado y ejecutable (hooks/trampolines) y localizar la libreria con
`dl_iterate_phdr`/`/proc/self/maps`. En Horizon el codigo ejecutable no es escribible: solo se puede parchear **antes** de
`so_finalize()`. Por eso este proyecto parchea por nombre desde `patches.txt` en ese momento (ver `source/patches.h`).

## Lo que se sabe del problema de "la ruedita"

- `libuaf.so` incluye el SDK **UbiServices** completo (`ubiservices::JobLogin`, "Session creation to UbiServices is in
  progress", `online::UbiServicesModule`...) y el cliente del servidor de juego (`online::GameServerModule`, lee su
  URL de un archivo de configuracion del obb con `readNodeJsConfigFromFile`).
- Los servidores de Ubisoft ya no existen: el login nunca termina y el motor se queda con el indicador de actividad
  de red girando. El motor exporta todos sus simbolos (114 409), asi que se puede intervenir por nombre.
- Las otras librerias del apk (`libnms`, `libEncryptorP`, `libapminsight*`) **no** influyen: `libuaf.so` no importa
  ningun simbolo de ellas y son de SDKs de anuncios/analiticas cargados por Java.

## Experimentos (de menos a mas invasivo), sin recompilar

Edita `config.txt` / `patches.txt` en la SD y manda el `data/log.txt` de cada prueba:

1. `connection_status = 0` (el motor cree que no hay red y no intenta el login).
2. `net_block = 1` (los hosts `*.ubi.com`, `*.ubisoft.com`... fallan al instante en vez de colgarse).
3. Lineas de `patches.txt` (hay ideas comentadas en la plantilla). `python3 tools/find_sym.py libuaf.so <texto>` lista
   los nombres mangled disponibles.

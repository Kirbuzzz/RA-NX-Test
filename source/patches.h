/* patches.h -- parches al codigo de libuaf.so por NOMBRE de funcion, editables desde la SD sin recompilar.
 *
 * Por que existe: el motor trae el SDK UbiServices y hace login contra servidores de Ubisoft que ya no existen;
 * en Android, el mod de Reawaken (libModMenu.so) lo evita enganchando funciones en tiempo de ejecucion. Aqui no se
 * puede escribir en codigo ya ejecutable, pero SI antes de so_finalize(): game_boot() llama a patches_apply() justo ahi.
 *
 * Archivo <base>/patches.txt (se crea una plantilla comentada la primera vez). Una orden por linea; '#' comenta:
 *
 *   ret <entero> <objetivo>    la funcion devuelve <entero> de inmediato (bool/int: w0 = valor)
 *   void <objetivo>            la funcion no hace nada (retorna enseguida)
 *
 * <objetivo> es el nombre EXACTO (mangled, p. ej. _ZN6online11LoginModule24isFirstPartyServerOnlineEv) o
 * "~texto" para parchear las funciones cuyo nombre contenga ese texto (maximo 16 coincidencias; si hay mas, se omite).
 */
#ifndef __PATCHES_H__
#define __PATCHES_H__

#include "so_util.h"

/* Debe llamarse con el modulo ya relocalizado y ANTES de so_finalize(). */
void patches_apply(so_module *mod);

#endif

/* patches.c -- ver patches.h */
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include "log.h"
#include "paths.h"
#include "patches.h"

#define MAX_MATCHES 16

static const char k_template[] =
  "# patches.txt -- parches a libuaf.so por nombre de funcion (se aplican al arrancar el motor).\n"
  "#\n"
  "#   ret <entero> <objetivo>   la funcion devuelve ese valor de inmediato\n"
  "#   void <objetivo>           la funcion no hace nada\n"
  "#\n"
  "# <objetivo>: nombre exacto (mangled) o ~texto para todas las funciones que lo contengan (max. 16).\n"
  "# El log (data/log.txt) dice que se aplico: busca las lineas que empiezan por 'patch:'.\n"
  "#\n"
  "# El motor trae el SDK UbiServices y hace login contra servidores de Ubisoft que ya no existen. Ideas para probar\n"
  "# (una cada vez; quita el # para activarla):\n"
  "#\n"
  "# ret 0 _ZN6online11LoginModule24isFirstPartyServerOnlineEv\n"
  "# ret 1 _ZN6online11LoginModule24isFirstPartyServerOnlineEv\n"
  "# void _ZN6online17UbiServicesModule20checkConnectionStateEv\n"
  "# void _ZN6online17UbiServicesModule4initEv\n"
  "# void _ZN6online19LoginModule_Android16updateConnectingEv\n"
  "# void _ZN6online21NetworkModule_Android6updateEv\n";

static void write_ret(uintptr_t addr, int val) {
  uint32_t *p = (uint32_t *)addr;
  if (val >= 0 && val <= 0xffff) {
    p[0] = 0x52800000u | ((uint32_t)val << 5);                       /* movz w0, #val */
    p[1] = 0xd65f03c0u;                                              /* ret */
  } else if (val < 0 && val >= -0x10000) {
    p[0] = 0x12800000u | (((uint32_t)(~val) & 0xffffu) << 5);        /* movn w0, #(~val) */
    p[1] = 0xd65f03c0u;
  } else {
    p[0] = 0x52800000u | (((uint32_t)val & 0xffffu) << 5);           /* movz w0, #lo */
    p[1] = 0x72a00000u | ((((uint32_t)val >> 16) & 0xffffu) << 5);   /* movk w0, #hi, lsl 16 */
    p[2] = 0xd65f03c0u;
  }
}

static void write_void(uintptr_t addr) {
  *(uint32_t *)addr = 0xd65f03c0u;                                   /* ret */
}

/* aplica `fn` a cada simbolo de funcion que coincide; devuelve cuantos */
static int for_matches(so_module *mod, const char *target, int value, int is_ret) {
  int n = 0;
  uintptr_t found[MAX_MATCHES];
  const char *names[MAX_MATCHES];

  if (target[0] == '~') {
    const char *sub = target + 1;
    int total = 0;
    for (int i = 0; i < mod->num_syms; i++) {
      const Elf64_Sym *s = &mod->syms[i];
      if (s->st_shndx == 0 || s->st_value == 0 || ELF64_ST_TYPE(s->st_info) != STT_FUNC)
        continue;
      const char *name = mod->dynstrtab + s->st_name;
      if (!strstr(name, sub))
        continue;
      if (total < MAX_MATCHES) {
        found[total] = (uintptr_t)mod->load_base + s->st_value;
        names[total] = name;
      }
      total++;
    }
    if (total > MAX_MATCHES) {
      LOG("patch: '%s' coincide con %d funciones (maximo %d): omitido, usa un texto mas especifico", target, total, MAX_MATCHES);
      return 0;
    }
    n = total;
  } else {
    const uintptr_t a = so_try_find_addr(mod, target);
    if (a) { found[0] = a; names[0] = target; n = 1; }
  }

  for (int i = 0; i < n; i++) {
    if (is_ret) write_ret(found[i], value); else write_void(found[i]);
    LOG("patch: %s %s", is_ret ? "ret" : "void", names[i]);
  }
  return n;
}

void patches_apply(so_module *mod) {
  const char *path = path_patches();
  FILE *f = fopen(path, "r");
  if (!f) {                                        /* primera vez: deja la plantilla para que sea facil encontrarla */
    f = fopen(path, "w");
    if (f) { fputs(k_template, f); fclose(f); }
    LOG("patches: no habia %s; plantilla creada (sin parches activos)", path);
    return;
  }

  char line[512];
  int lineno = 0, applied = 0, missing = 0;
  while (fgets(line, sizeof line, f)) {
    lineno++;
    char *p = line;
    while (isspace((unsigned char)*p)) p++;
    if (*p == '#' || *p == '\0')
      continue;
    char op[16] = { 0 }, target[400] = { 0 };
    int value = 0;
    if (sscanf(p, "ret %d %399s", &value, target) == 2) {
      strcpy(op, "ret");
    } else if (sscanf(p, "void %399s", target) == 1) {
      strcpy(op, "void");
    } else {
      LOG("patches: linea %d no valida: %s", lineno, p);
      continue;
    }
    const int n = for_matches(mod, target, value, !strcmp(op, "ret"));
    if (n) applied += n; else { missing++; LOG("patch: NO ENCONTRADO: %s (linea %d)", target, lineno); }
  }
  fclose(f);
  LOG("patches: %d funciones parcheadas, %d objetivos sin encontrar (%s)", applied, missing, path);
}

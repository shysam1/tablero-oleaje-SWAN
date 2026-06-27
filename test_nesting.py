"""Tests del motor de nesting (builder, validación y orden de corrida)."""
import swan_builder
import swan_runner


MALLA_G = {"xpc": 0, "ypc": 0, "xlenc": 48000, "ylenc": 59000, "mxc": 48, "myc": 59}
MALLA_N = {"xpc": 36480, "ypc": 32229, "xlenc": 9000, "ylenc": 10000,
           "mxc": 45, "myc": 50}
NIDO = {"sname": "nido1", "nestfile": "nest1", "xpn": 36480, "ypn": 32229,
        "xlenn": 9000, "ylenn": 10000, "mxn": 45, "myn": 50}
BORDES = [{"lado": "W", "hs": 8.16, "per": 13, "dir": 315, "dd": 17.7}]


def test_construir_swn_nido_emite_ngrid_nestout():
    txt = swan_builder.construir_swn("G", MALLA_G, {"archivo": "b.bot"}, BORDES,
                                     nido=NIDO)
    assert "NGRID 'nido1' 36480 32229 0. 9000 10000 45 50" in txt
    assert "NESTOUT 'nido1' 'nest1'" in txt
    assert "BOUN SIDE W" in txt          # el grande conserva sus bordes


def test_construir_swn_bou_nest_reemplaza_boun_side():
    txt = swan_builder.construir_swn("N", MALLA_N, {"archivo": "bn.bot"}, [],
                                     bou_nest="nest1")
    assert "BOU NEST 'nest1' CLOSED" in txt
    assert "BOUN SIDE" not in txt
    assert "BOU SHAPE" not in txt


def test_construir_swn_bou_nest_descarta_bordes_si_los_hay():
    txt = swan_builder.construir_swn("N", MALLA_N, {"archivo": "bn.bot"},
                                     BORDES, bou_nest="nest1")  # bordes no vacíos
    assert "BOU NEST 'nest1' CLOSED" in txt
    assert "BOUN SIDE" not in txt


def test_construir_swn_punto_espectral():
    txt = swan_builder.construir_swn(
        "N", MALLA_N, {"archivo": "bn.bot"}, [], bou_nest="nest1",
        punto_espectral={"x": 42423, "y": 37171, "archivo": "Espectro_Punto.txt"})
    assert "POINTS 'SpecOut' 42423 37171" in txt
    assert "SPEC 'SpecOut' SPEC2D ABS 'Espectro_Punto.txt'" in txt


def test_validar_caso_anidado_nido_fuera_es_error():
    g = {**MALLA_G, "zona_utm": "18S"}
    n = {"xpc": 40000, "ypc": 55000, "xlenc": 20000, "ylenc": 20000,
         "mxc": 100, "myc": 100, "zona_utm": "18S"}     # se sale por arriba
    errores, _ = swan_builder.validar_caso_anidado(g, n)
    assert any("contenido" in e.lower() for e in errores)


def test_validar_caso_anidado_zona_distinta_es_error():
    g = {**MALLA_G, "zona_utm": "18S"}
    n = {**MALLA_N, "zona_utm": "19S"}
    errores, _ = swan_builder.validar_caso_anidado(g, n)
    assert any("zona" in e.lower() for e in errores)


def test_validar_caso_anidado_ok_no_tiene_errores():
    g = {**MALLA_G, "zona_utm": "18S"}
    n = {**MALLA_N, "zona_utm": "18S"}
    errores, _ = swan_builder.validar_caso_anidado(g, n)
    assert errores == []


def test_validar_caso_anidado_celda_no_fina_avisa():
    g = {**MALLA_G, "zona_utm": "18S"}                  # ~1000 m
    n = {"xpc": 1000, "ypc": 1000, "xlenc": 9000, "ylenc": 10000,
         "mxc": 4, "myc": 5, "zona_utm": "18S"}         # ~2250 m, más gruesa
    _, avisos = swan_builder.validar_caso_anidado(g, n)
    assert any("fina" in a.lower() for a in avisos)


def test_validar_caso_sin_bordes_no_exige_borde():
    errores, _ = swan_builder.validar_caso(
        MALLA_N, {"archivo": "bn.bot"}, [], requiere_bordes=False)
    assert not any("borde" in e.lower() for e in errores)


def test_escribir_par_anidado_crea_dos_swn_enlazados(tmp_path):
    rg, rn = swan_builder.escribir_par_anidado(
        tmp_path, "Grande", "Nido", MALLA_G, {"archivo": "bg.bot"}, BORDES,
        MALLA_N, {"archivo": "bn.bot"})
    tg, tn = rg.read_text(), rn.read_text()
    assert "NGRID 'nido1' 36480 32229 0. 9000 10000 45 50" in tg
    assert "NESTOUT 'nido1' 'nest1'" in tg
    assert "BOU NEST 'nest1' CLOSED" in tn
    assert "CGRID 36480 32229" in tn
    assert "BOUN SIDE" not in tn


def test_escribir_par_anidado_punto_espectral_va_al_nido(tmp_path):
    pe = {"x": 42000, "y": 37000, "archivo": "Esp.txt"}
    rg, rn = swan_builder.escribir_par_anidado(
        tmp_path, "G", "N", MALLA_G, {"archivo": "g.bot"}, BORDES,
        MALLA_N, {"archivo": "n.bot"}, punto_espectral=pe)
    assert "POINTS 'SpecOut' 42000 37000" in rn.read_text()
    assert "POINTS" not in rg.read_text()

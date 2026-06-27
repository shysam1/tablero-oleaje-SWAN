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

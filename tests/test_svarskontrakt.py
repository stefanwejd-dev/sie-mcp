"""Tester för svarskontrakt.py — schemat AI:t fyller i när svaret innehåller
tabelldata (Område A, fas 2).

Kontraktets hela poäng är att layouten INTE ska bero på modellen: appen
renderar, modellen levererar bara data. Testerna vaktar därför två saker
lika hårt — att ett korrekt svar går igenom oförvanskat, och att ALLT annat
ger None så anroparen kan falla tillbaka till vanlig text utan att något
kraschar. Kontraktet ska aldrig kunna släcka chatten.

Ingen maskerings- eller avmaskeringslogik testas här: strukturerade svar
innehåller samma maskerade tokens ([BOLAG_1]) som resten av chatten, precis
som texten gör idag.
"""

from __future__ import annotations

import json

from svarskontrakt import (
    KONTRAKT_INSTRUKTION,
    DiagramBlock,
    KolumnDef,
    StruktureratSvar,
    TabellBlock,
    TextBlock,
    med_inledande_text,
    svarskontrakt_verktygsschema,
    text_sammanfattning,
    validera_svar,
    validera_svar_dict,
)

FAKTURATABELL = {
    "typ": "tabell",
    "rubrik": "Obetalda leverantörsfakturor",
    "kolumner": [
        {"nyckel": "leverantor", "rubrik": "Leverantör", "typ": "text"},
        {"nyckel": "forfaller", "rubrik": "Förfaller", "typ": "datum"},
        {"nyckel": "exkl_moms", "rubrik": "Exkl. moms", "typ": "belopp"},
        {"nyckel": "inkl_moms", "rubrik": "Inkl. moms", "typ": "belopp"},
    ],
    "rader": [
        {
            "leverantor": "[BOLAG_1]",
            "forfaller": "2026-08-15",
            "exkl_moms": 19600,
            "inkl_moms": 24500,
        },
        {
            "leverantor": "[BOLAG_2]",
            "forfaller": "2026-08-22",
            "exkl_moms": 8000,
            "inkl_moms": 10000,
        },
    ],
    "summa_rad": {"leverantor": "Summa", "exkl_moms": 27600, "inkl_moms": 34500},
}

GILTIGT_SVAR = {
    "block": [
        {"typ": "text", "innehall": "Två fakturor är obetalda."},
        FAKTURATABELL,
    ]
}


class TestValideringAvDict:
    def test_giltigt_svar_ger_strukturerat_svar(self):
        svar = validera_svar_dict(GILTIGT_SVAR)

        assert svar is not None
        assert len(svar.block) == 2
        assert isinstance(svar.block[0], TextBlock)
        assert isinstance(svar.block[1], TabellBlock)

    def test_blocktyperna_skiljs_at_pa_typ_faltet(self):
        svar = validera_svar_dict({
            "block": [
                {"typ": "text", "innehall": "Kommentar"},
                FAKTURATABELL,
                {
                    "typ": "diagram", "diagram_typ": "cirkel", "rubrik": "Fördelning",
                    "kategori_falt": "k", "varde_falt": "v",
                    "data": [{"k": "A", "v": 1}],
                },
            ]
        })

        assert svar is not None
        assert [type(b) for b in svar.block] == [TextBlock, TabellBlock, DiagramBlock]

    def test_tabelldata_bevaras_oforandrat(self):
        svar = validera_svar_dict(GILTIGT_SVAR)

        tabell = svar.block[1]
        assert [k.nyckel for k in tabell.kolumner] == [
            "leverantor", "forfaller", "exkl_moms", "inkl_moms",
        ]
        assert tabell.rader[0]["leverantor"] == "[BOLAG_1]"
        assert tabell.summa_rad["inkl_moms"] == 34500

    def test_maskerade_tokens_skrivs_inte_om(self):
        # Kontraktet ska aldrig röra maskeringen — den sker före AI-anropet
        # och svaret visas som det är, med tokens kvar.
        svar = validera_svar_dict(GILTIGT_SVAR)

        assert "[BOLAG_1]" in text_sammanfattning(svar)

    def test_okanda_radnycklar_avvisar_inte_svaret(self):
        # Tolerant: en extra nyckel i en rad är ett modellfel som inte ska
        # kosta användaren hela tabellen — den ignoreras vid rendering.
        data = json.loads(json.dumps(GILTIGT_SVAR))
        data["block"][1]["rader"][0]["okand_nyckel"] = "skräp"

        assert validera_svar_dict(data) is not None

    def test_kolumnstandardtyp_ar_text(self):
        svar = validera_svar_dict({
            "block": [{
                "typ": "tabell",
                "kolumner": [{"nyckel": "a", "rubrik": "A"}],
                "rader": [{"a": "x"}],
            }]
        })

        assert svar.block[0].kolumner[0].typ == "text"


class TestValideringFallerTillbaka:
    def test_icke_dict_ger_none(self):
        assert validera_svar_dict(["block"]) is None
        assert validera_svar_dict(None) is None
        assert validera_svar_dict("{}") is None

    def test_tomt_blocklista_ger_none(self):
        # Ett tomt svar ska bli vanlig text, inte en tom chattbubbla.
        assert validera_svar_dict({"block": []}) is None

    def test_saknad_blocknyckel_ger_none(self):
        assert validera_svar_dict({"blocks": []}) is None

    def test_tabell_utan_kolumner_ger_none(self):
        assert validera_svar_dict({
            "block": [{"typ": "tabell", "kolumner": [], "rader": []}]
        }) is None

    def test_tabell_utan_rader_nyckel_ger_none(self):
        assert validera_svar_dict({
            "block": [{
                "typ": "tabell",
                "kolumner": [{"nyckel": "a", "rubrik": "A"}],
            }]
        }) is None

    def test_tomt_textblock_ger_none(self):
        assert validera_svar_dict({"block": [{"typ": "text", "innehall": ""}]}) is None

    def test_okand_kolumntyp_ger_none(self):
        assert validera_svar_dict({
            "block": [{
                "typ": "tabell",
                "kolumner": [{"nyckel": "a", "rubrik": "A", "typ": "valuta"}],
                "rader": [],
            }]
        }) is None

    def test_okand_diagramtyp_ger_none(self):
        assert validera_svar_dict({
            "block": [{
                "typ": "diagram", "diagram_typ": "radar", "rubrik": "R",
                "kategori_falt": "k", "varde_falt": "v", "data": [],
            }]
        }) is None


class TestValideringAvRatext:
    def test_ren_json_i_texten(self):
        assert validera_svar(json.dumps(GILTIGT_SVAR)) is not None

    def test_json_med_omgivande_blanktecken(self):
        assert validera_svar("\n  " + json.dumps(GILTIGT_SVAR) + "  \n") is not None

    def test_json_i_kodstaket(self):
        rått = "```json\n" + json.dumps(GILTIGT_SVAR) + "\n```"

        assert validera_svar(rått) is not None

    def test_json_i_kodstaket_utan_sprakmarkering(self):
        rått = "```\n" + json.dumps(GILTIGT_SVAR) + "\n```"

        assert validera_svar(rått) is not None

    def test_vanlig_prosa_ger_none(self):
        # Det VANLIGA fallet: modellen svarar i löpande text, som förut.
        assert validera_svar("Bolaget har en stabil likviditet just nu.") is None

    def test_trasig_json_ger_none_utan_att_kasta(self):
        assert validera_svar('{"block": [{"typ": "text",') is None

    def test_giltig_json_med_fel_form_ger_none(self):
        assert validera_svar('{"svar": "hej"}') is None

    def test_tom_strang_ger_none(self):
        assert validera_svar("") is None


class TestTextSammanfattning:
    def test_innehaller_text_rubrik_och_rader(self):
        svar = validera_svar_dict(GILTIGT_SVAR)

        text = text_sammanfattning(svar)

        assert "Två fakturor är obetalda." in text
        assert "Obetalda leverantörsfakturor" in text
        assert "[BOLAG_2]" in text
        assert "34500" in text  # summaraden följer med

    def test_ar_aldrig_tom(self):
        # ChattMeddelande.text återsänds till agenten i varje varv; ett tomt
        # meddelande avvisas av API:t.
        svar = StruktureratSvar(block=[
            DiagramBlock(
                diagram_typ="stapel", rubrik="", kategori_falt="k",
                varde_falt="v", data=[],
            )
        ])

        assert text_sammanfattning(svar).strip() != ""

    def test_langa_tabeller_kapas(self):
        svar = StruktureratSvar(block=[TabellBlock(
            kolumner=[KolumnDef(nyckel="a", rubrik="A")],
            rader=[{"a": f"rad{i}"} for i in range(50)],
        )])

        text = text_sammanfattning(svar, max_rader=5)

        assert "rad4" in text
        assert "rad5" not in text
        assert "(50 rader totalt)" in text

    def test_pipe_i_cellvarde_spracker_inte_tabellen(self):
        svar = StruktureratSvar(block=[TabellBlock(
            kolumner=[KolumnDef(nyckel="a", rubrik="A")],
            rader=[{"a": "x | y"}],
        )])

        rad = [r for r in text_sammanfattning(svar).splitlines() if "x" in r][0]
        assert rad == r"| x \| y |"  # cellens pipe escapad, inte en ny kolumn

    def test_diagramblock_namns_men_ritas_inte_i_text(self):
        svar = StruktureratSvar(block=[DiagramBlock(
            diagram_typ="linje", rubrik="Kassaflöde", kategori_falt="k",
            varde_falt="v", data=[{"k": "v31", "v": 100}],
        )])

        assert text_sammanfattning(svar) == "[Diagram: Kassaflöde]"


class TestMedInledandeText:
    def test_kommentaren_laggs_forst_som_textblock(self):
        svar = validera_svar_dict({"block": [FAKTURATABELL]})

        med_inledande_text(svar, "Här är de obetalda fakturorna:")

        assert isinstance(svar.block[0], TextBlock)
        assert svar.block[0].innehall == "Här är de obetalda fakturorna:"
        assert isinstance(svar.block[1], TabellBlock)

    def test_tom_eller_blank_text_lamnar_svaret_orort(self):
        svar = validera_svar_dict({"block": [FAKTURATABELL]})

        med_inledande_text(svar, None)
        med_inledande_text(svar, "   \n ")

        assert len(svar.block) == 1

    def test_resultatet_gar_att_serialisera_till_session_state(self):
        # app.py sparar .model_dump() i session_state och validerar tillbaka
        # det vid rendering — den vändan måste överleva insättningen.
        svar = med_inledande_text(validera_svar_dict(GILTIGT_SVAR), "Kommentar")

        assert validera_svar_dict(svar.model_dump()) is not None


class TestVerktygsschema:
    def test_kraver_block(self):
        schema = svarskontrakt_verktygsschema()

        assert schema["required"] == ["block"]
        assert schema["properties"]["block"]["items"]["required"] == ["typ"]

    def test_ar_helt_inlinat(self):
        # $ref/$defs har ojämnt stöd i både Anthropics tool use och Ollamas
        # mindre modeller — därför handskrivet i stället för Pydantics
        # model_json_schema().
        rått = json.dumps(svarskontrakt_verktygsschema())

        assert "$ref" not in rått
        assert "$defs" not in rått

    def test_returnerar_kopia_som_inte_kan_mutera_modulen(self):
        schema = svarskontrakt_verktygsschema()
        schema["properties"]["block"]["type"] = "sabotage"

        assert svarskontrakt_verktygsschema()["properties"]["block"]["type"] == "array"

    def test_inga_falt_utanfor_modellerna(self):
        # Vaktar drift: schemat är handskrivet och kan annars tyst hamna ur
        # fas med Pydantic-modellerna det ska matcha.
        modellfalt = (
            set(TextBlock.model_fields)
            | set(TabellBlock.model_fields)
            | set(DiagramBlock.model_fields)
        )
        schemafalt = set(
            svarskontrakt_verktygsschema()["properties"]["block"]["items"]["properties"]
        )

        assert schemafalt <= modellfalt

    def test_alla_obligatoriska_modellfalt_finns_i_schemat(self):
        # Ett fält modellen MÅSTE fylla i, men aldrig får veta om, ger bara
        # tysta valideringsmisslyckanden i produktion.
        schemafalt = set(
            svarskontrakt_verktygsschema()["properties"]["block"]["items"]["properties"]
        )
        for modell in (TextBlock, TabellBlock, DiagramBlock):
            obligatoriska = {
                namn for namn, falt in modell.model_fields.items() if falt.is_required()
            }
            assert obligatoriska <= schemafalt, modell.__name__

    def test_kolumnschemat_matchar_kolumndef(self):
        kolumnfalt = set(
            svarskontrakt_verktygsschema()
            ["properties"]["block"]["items"]["properties"]["kolumner"]["items"]["properties"]
        )

        assert kolumnfalt <= set(KolumnDef.model_fields)


class TestKontraktinstruktion:
    def test_namnger_schemats_nycklar(self):
        # Instruktionen är enda schemabeskrivningen icke-agentläget har.
        for nyckel in ("block", "typ", "kolumner", "rader", "nyckel", "rubrik"):
            assert nyckel in KONTRAKT_INSTRUKTION

    def test_exemplet_i_instruktionen_ar_giltigt_enligt_kontraktet(self):
        # Ett exempel som inte validerar vore precis fel sorts felkälla.
        exempel = KONTRAKT_INSTRUKTION[KONTRAKT_INSTRUKTION.index('{"block"'):]

        assert validera_svar(exempel) is not None

    def test_sager_att_belopp_ska_vara_rena_tal(self):
        assert "24500.5" in KONTRAKT_INSTRUKTION

    def test_sager_att_lopande_text_forblir_text(self):
        assert "vanlig text" in KONTRAKT_INSTRUKTION

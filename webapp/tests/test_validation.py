"""Tests unitaires de la validation des fichiers (SB-80)."""
import json

import pytest

from app.services.validation import (
    PREVIEW_ROWS,
    ValidationError,
    decode,
    detect_format,
    extension_of,
    validate_csv,
    validate_json,
    validate_upload,
)

CSV_HEADER = "timestamp,sensor_id,sensor_type,zone,value,unit"
CSV_ROW = "2026-11-10T10:00:00Z,S-001,temperature,Hall,21.5,C"


def make_csv(n):
    return "\n".join([CSV_HEADER] + [CSV_ROW] * n)


def json_line(drop=(), **extra):
    obj = {
        "timestamp": "2026-11-10T10:00:00Z",
        "sensor_id": "S-001",
        "sensor_type": "temperature",
        "value": 21.5,
        **extra,
    }
    for key in drop:
        obj.pop(key)
    return json.dumps(obj)


# --- fonctions utilitaires ---
@pytest.mark.parametrize(
    "name,expected",
    [("a.csv", "csv"), ("A.JSON", "json"), ("notes.txt", "txt"),
     ("archive.tar.gz", "gz"), ("sans_extension", "")],
)
def test_extension_of(name, expected):
    assert extension_of(name) == expected


def test_decode_utf8_et_bom():
    assert decode("é".encode("utf-8")) == "é"
    assert decode(b"\xef\xbb\xbfabc") == "abc"


def test_decode_refuse_un_encodage_invalide():
    with pytest.raises(ValidationError, match="UTF-8"):
        decode(b"\xff\xfe\xfa")


def test_detect_format():
    assert detect_format("csv", "{pas du json}") == "csv"
    assert detect_format("json", "a,b,c") == "json"
    assert detect_format("txt", json_line()) == "json"
    assert detect_format("txt", "\n\n" + CSV_HEADER) == "csv"


# --- CSV ---
def test_csv_valide():
    r = validate_csv(make_csv(3))
    assert r.fmt == "csv"
    assert r.rows == 3
    assert len(r.preview) == 3
    assert r.columns == CSV_HEADER.split(",")


def test_csv_avec_colonnes_status_et_message():
    text = f"{CSV_HEADER},status,message\n{CSV_ROW},OK,Mesure normale"
    assert validate_csv(text).rows == 1


def test_csv_apercu_limite_a_10_lignes():
    r = validate_csv(make_csv(25))
    assert r.rows == 25
    assert len(r.preview) == PREVIEW_ROWS == 10


@pytest.mark.parametrize(
    "text,message",
    [
        ("", "vide"),
        (CSV_HEADER, "aucune ligne"),
        ("timestamp,sensor_id,value\n2026,S1,1", "En-tête CSV invalide"),
        ("sensor_id,timestamp,sensor_type,zone,value,unit\nS1,2026,t,Hall,1,C",
         "En-tête CSV invalide"),
    ],
)
def test_csv_invalide(text, message):
    with pytest.raises(ValidationError, match=message):
        validate_csv(text)


def test_csv_nombre_de_colonnes_incoherent():
    text = f"{CSV_HEADER}\n{CSV_ROW}\n2026-11-10T10:05:00Z,S-001,temperature"
    with pytest.raises(ValidationError, match="Ligne 3"):
        validate_csv(text)


def test_csv_ignore_les_lignes_vides():
    assert validate_csv(f"{CSV_HEADER}\n{CSV_ROW}\n\n{CSV_ROW}\n").rows == 2


# --- JSON (un objet par ligne) ---
def test_json_valide():
    r = validate_json("\n".join([json_line(), json_line(), ""]))
    assert r.fmt == "json"
    assert r.rows == 2
    assert len(r.preview) == 2
    assert r.columns == ["timestamp", "sensor_id", "sensor_type", "value"]


def test_json_accepte_arobase_timestamp():
    line = json_line(drop=["timestamp"], **{"@timestamp": "2026-11-10T10:00:00Z"})
    assert validate_json(line).rows == 1


def test_json_apercu_limite_a_10_lignes():
    r = validate_json("\n".join(json_line() for _ in range(25)))
    assert r.rows == 25
    assert len(r.preview) == 10


@pytest.mark.parametrize(
    "text,message",
    [
        ("", "aucune ligne"),
        ("[" + json_line() + "]", "tableau"),
        (json_line() + "\n{pas du json", "Ligne 2"),
        ("123", "objet JSON est attendu"),
        (json_line(drop=["value"]), "champs manquants.*value"),
        (json_line(drop=["timestamp"]), "champs manquants.*timestamp"),
    ],
)
def test_json_invalide(text, message):
    with pytest.raises(ValidationError, match=message):
        validate_json(text)


# --- validation complète d'un upload (RM01 à RM03) ---
def test_upload_extension_refusee():
    with pytest.raises(ValidationError) as exc:
        validate_upload("malware.exe", b"abc")
    assert exc.value.status == 415


def test_upload_fichier_vide():
    with pytest.raises(ValidationError, match="vide"):
        validate_upload("a.csv", b"  \n ")


def test_upload_encodage_invalide():
    with pytest.raises(ValidationError, match="UTF-8"):
        validate_upload("a.csv", b"\xff\xfe\xfa")


def test_upload_csv_en_majuscules_avec_bom():
    raw = b"\xef\xbb\xbf" + make_csv(2).encode()
    assert validate_upload("DATA.CSV", raw).rows == 2


def test_upload_txt_classe_selon_le_contenu():
    assert validate_upload("log.txt", json_line().encode()).fmt == "json"
    assert validate_upload("log.txt", make_csv(1).encode()).fmt == "csv"

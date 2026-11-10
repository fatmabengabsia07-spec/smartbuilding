"""Validation des fichiers de logs avant injection (format, structure, aperçu)."""
import csv
import io
import json
from dataclasses import dataclass

ALLOWED_EXTENSIONS = {"csv", "json", "txt"}
# Ordre imposé par le pipeline Logstash CSV (colonnes positionnelles)
CSV_COLUMNS = ["timestamp", "sensor_id", "sensor_type", "zone", "value", "unit", "status", "message"]
CSV_MIN_COLUMNS = 6
JSON_REQUIRED = ["sensor_id", "sensor_type", "value"]
PREVIEW_ROWS = 10


class ValidationError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


@dataclass
class ValidationResult:
    fmt: str          # "csv" ou "json" (format d'ingestion)
    rows: int         # nombre de lignes de données
    columns: list     # colonnes de l'aperçu
    preview: list     # 10 premières lignes


def extension_of(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def decode(raw):
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("Encodage invalide : le fichier doit être en UTF-8.")


def detect_format(extension, text):
    """CSV et JSON gardent leur format ; un TXT est classé selon son contenu."""
    if extension in ("csv", "json"):
        return extension
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return "json" if first.startswith("{") else "csv"


def validate_csv(text):
    reader = csv.reader(io.StringIO(text))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        raise ValidationError("Le fichier est vide.")
    except csv.Error as exc:
        raise ValidationError(f"CSV illisible : {exc}.")
    n = len(header)
    if n < CSV_MIN_COLUMNS or n > len(CSV_COLUMNS) or header != CSV_COLUMNS[:n]:
        raise ValidationError(
            "En-tête CSV invalide. Colonnes attendues, dans cet ordre : "
            "timestamp, sensor_id, sensor_type, zone, value, unit[, status, message]."
        )
    rows, preview = 0, []
    try:
        for line_no, row in enumerate(reader, start=2):
            if not row or all(not cell.strip() for cell in row):
                continue
            if len(row) != n:
                raise ValidationError(f"Ligne {line_no} : {len(row)} colonnes au lieu de {n}.")
            rows += 1
            if len(preview) < PREVIEW_ROWS:
                preview.append(row)
    except csv.Error as exc:
        raise ValidationError(f"CSV illisible : {exc}.")
    if rows == 0:
        raise ValidationError("Le fichier ne contient aucune ligne de données.")
    return ValidationResult("csv", rows, header, preview)


def validate_json(text):
    rows, objects, keys = 0, [], []
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        if rows == 0 and line.startswith("["):
            raise ValidationError(
                "Format JSON non supporté : un objet JSON par ligne est attendu (pas de tableau)."
            )
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Ligne {line_no} : JSON invalide ({exc.msg}).")
        if not isinstance(obj, dict):
            raise ValidationError(f"Ligne {line_no} : un objet JSON est attendu.")
        missing = [k for k in JSON_REQUIRED if k not in obj]
        if "timestamp" not in obj and "@timestamp" not in obj:
            missing.append("timestamp")
        if missing:
            raise ValidationError(f"Ligne {line_no} : champs manquants : {', '.join(missing)}.")
        rows += 1
        if len(objects) < PREVIEW_ROWS:
            objects.append(obj)
            keys.extend(k for k in obj if k not in keys)
    if rows == 0:
        raise ValidationError("Le fichier ne contient aucune ligne de données.")
    preview = [[obj.get(k, "") for k in keys] for obj in objects]
    return ValidationResult("json", rows, keys, preview)


def validate_upload(filename, raw):
    """Contrôle complet : extension, contenu non vide, encodage, structure."""
    extension = extension_of(filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationError("Extension non acceptée : seuls les fichiers CSV, JSON et TXT sont autorisés.", 415)
    if not raw.strip():
        raise ValidationError("Le fichier est vide.")
    text = decode(raw)
    fmt = detect_format(extension, text)
    return validate_csv(text) if fmt == "csv" else validate_json(text)

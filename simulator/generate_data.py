
import argparse
import json
import random
from collections import Counter
from datetime import timezone
from pathlib import Path

from faker import Faker


fake = Faker()

ZONES = [
    "Salle_A",
    "Salle_B",
    "Salle_C",
    "Bureau_1",
    "Bureau_2",
    "Hall",
    "Parking",
]

SENSORS = {
    "temperature": {
        "prefix": "TEMP",
        "min": 15,
        "max": 40,
        "unit": "C",
    },
    "humidity": {
        "prefix": "HUM",
        "min": 20,
        "max": 95,
        "unit": "%",
    },
    "luminosity": {
        "prefix": "LUX",
        "min": 50,
        "max": 1200,
        "unit": "lux",
    },
    "co2": {
        "prefix": "CO2",
        "min": 350,
        "max": 2000,
        "unit": "ppm",
    },
    "energy": {
        "prefix": "ENERGY",
        "min": 0.5,
        "max": 15,
        "unit": "kWh",
    },
    "occupancy": {
        "prefix": "OCC",
        "min": 0,
        "max": 30,
        "unit": "persons",
    },
}


def get_status(sensor_type, value):
    """Détermine le statut d'une mesure selon son type."""

    if sensor_type == "temperature":
        if value > 30 or value < 17:
            return "ERROR"
        elif value > 27 or value < 19:
            return "WARNING"

    elif sensor_type == "humidity":
        if value > 80 or value < 25:
            return "ERROR"
        elif value > 70 or value < 35:
            return "WARNING"

    elif sensor_type == "luminosity":
        if value < 100 or value > 1000:
            return "WARNING"

    elif sensor_type == "co2":
        if value > 1500:
            return "ERROR"
        elif value > 1000:
            return "WARNING"

    elif sensor_type == "energy":
        if value > 12:
            return "ERROR"
        elif value > 9:
            return "WARNING"

    elif sensor_type == "occupancy":
        if value > 25:
            return "ERROR"
        elif value > 20:
            return "WARNING"

    return "INFO"


def generate_event():
    """Génère un événement de capteur Smart Building."""

    sensor_type = random.choice(list(SENSORS.keys()))
    config = SENSORS[sensor_type]

    sensor_number = random.randint(1, 20)
    sensor_id = f"{config['prefix']}_{sensor_number:03d}"

    # Toutes les valeurs sont converties en float
    # pour garantir un type numérique homogène dans Elasticsearch.
    if sensor_type == "occupancy":
        value = float(
            random.randint(config["min"], config["max"])
        )
    elif sensor_type == "temperature":
        value = float(
            round(
                random.uniform(config["min"], config["max"]), 1
            )
        )
    else:
        value = float(
            round(
                random.uniform(config["min"], config["max"]), 2
            )
        )

    status = get_status(sensor_type, value)

    timestamp = fake.date_time_between(
        start_date="-7d",
        end_date="now",
        tzinfo=timezone.utc,
    )

    return {
        "event_id": fake.uuid4(),
        "@timestamp": timestamp.isoformat(),
        "sensor_id": sensor_id,
        "sensor_type": sensor_type,
        "zone": random.choice(ZONES),
        "value": value,
        "unit": config["unit"],
        "status": status,
        "message": (
            f"{sensor_type.capitalize()} measurement: "
            f"{value} {config['unit']}"
        ),
        "source": "smart_building_simulator",
    }


def generate_dataset(count, output):
    """Génère et enregistre les événements au format JSON Lines."""

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    events = [generate_event() for _ in range(count)]

    with output_path.open("w", encoding="utf-8") as file:
        for event in events:
            file.write(
                json.dumps(event, ensure_ascii=False) + "\n"
            )

    statuses = Counter(event["status"] for event in events)
    sensor_types = Counter(
        event["sensor_type"] for event in events
    )

    print("\n=== Smart Building Data Generator ===")
    print(f"Events generated : {count}")
    print(f"Output file      : {output_path.resolve()}")
    print(f"File size        : {output_path.stat().st_size} bytes")

    print("\nStatus distribution:")
    for status, total in statuses.items():
        print(f"  {status}: {total}")

    print("\nSensor distribution:")
    for sensor_type, total in sensor_types.items():
        print(f"  {sensor_type}: {total}")

    print("\nData generation completed successfully!")


def main():
    parser = argparse.ArgumentParser(
        description="Smart Building sensor data generator"
    )

    parser.add_argument(
        "--count",
        type=int,
        default=500,
        help="Number of events to generate (default: 500)",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="data/logs/json/smart_building_logs.json",
        help="Output JSON Lines file",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible data",
    )

    args = parser.parse_args()

    if args.count <= 0:
        parser.error("--count must be greater than 0")

    if args.seed is not None:
        random.seed(args.seed)
        Faker.seed(args.seed)

    generate_dataset(args.count, args.output)


if __name__ == "__main__":
    main()


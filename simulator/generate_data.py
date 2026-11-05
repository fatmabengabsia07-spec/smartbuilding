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
        "unit": "C",
        "min": 15,
        "max": 40,
    },
    "humidity": {
        "prefix": "HUM",
        "unit": "%",
        "min": 20,
        "max": 95,
    },
    "luminosity": {
        "prefix": "LUX",
        "unit": "lux",
        "min": 50,
        "max": 1200,
    },
    "co2": {
        "prefix": "CO2",
        "unit": "ppm",
        "min": 350,
        "max": 2000,
    },
    "energy": {
        "prefix": "ENERGY",
        "unit": "kWh",
        "min": 0.5,
        "max": 15,
    },
    "occupancy": {
        "prefix": "OCC",
        "unit": "persons",
        "min": 0,
        "max": 30,
    },
}


def get_status(sensor_type, value):
    if sensor_type == "temperature":
        if value > 30 or value < 15:
            return "ERROR"
        if value > 26 or value < 18:
            return "WARNING"

    elif sensor_type == "humidity":
        if value > 85:
            return "ERROR"
        if value > 70 or value < 25:
            return "WARNING"

    elif sensor_type == "luminosity":
        if value < 100:
            return "WARNING"

    elif sensor_type == "co2":
        if value > 1500:
            return "ERROR"
        if value > 1000:
            return "WARNING"

    elif sensor_type == "energy":
        if value > 12:
            return "ERROR"
        if value > 8:
            return "WARNING"

    elif sensor_type == "occupancy":
        if value > 25:
            return "ERROR"
        if value > 20:
            return "WARNING"

    return "INFO"


def generate_event():
    sensor_type = random.choice(list(SENSORS.keys()))
    config = SENSORS[sensor_type]

    sensor_number = random.randint(1, 20)
    sensor_id = f"{config['prefix']}_{sensor_number:03d}"

    if sensor_type == "occupancy":
        value = random.randint(
            config["min"], config["max"]
        )
    elif sensor_type == "temperature":
        value = round(
            random.uniform(config["min"], config["max"]), 1
        )
    else:
        value = round(
            random.uniform(config["min"], config["max"]), 2
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
        "message": f"{sensor_type.capitalize()} measurement: {value} {config['unit']}",
        "source": "smart_building_simulator",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Smart Building - Faker Data Generator"
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
        help="Output JSON file",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible data",
    )

    args = parser.parse_args()

    if args.count <= 0:
        parser.error("--count must be greater than zero")

    if args.seed is not None:
        random.seed(args.seed)
        Faker.seed(args.seed)

    project_root = Path(__file__).resolve().parent.parent
    output_path = project_root / args.output

    output_path.parent.mkdir(parents=True, exist_ok=True)

    events = [
        generate_event()
        for _ in range(args.count)
    ]

    with output_path.open("w", encoding="utf-8") as file:
        for event in events:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

    statuses = Counter(event["status"] for event in events)
    types = Counter(event["sensor_type"] for event in events)

    print("\n========== SMART BUILDING DATA GENERATOR ==========")
    print(f"Events generated : {len(events)}")
    print(f"Output file      : {output_path}")
    print(f"File size        : {output_path.stat().st_size} bytes")

    print("\nEvents by status:")
    for status, count in statuses.items():
        print(f"  {status}: {count}")

    print("\nEvents by sensor type:")
    for sensor_type, count in types.items():
        print(f"  {sensor_type}: {count}")

    print("\nGeneration completed successfully!")


if __name__ == "__main__":
    main()

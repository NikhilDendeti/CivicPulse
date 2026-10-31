import json

from django.core.management.base import BaseCommand, CommandError

from apps.authorities.models import Ward


class Command(BaseCommand):
    help = ("Load ward boundaries from a GeoJSON FeatureCollection of real ward polygons "
            "(e.g. GHMC wards from an open-data source whose licence you have checked).")

    def add_arguments(self, parser):
        parser.add_argument("geojson_path")
        parser.add_argument("--name-field", default="name", help="Feature property holding the ward name")
        parser.add_argument("--code-field", default="", help="Feature property holding the ward code/number")
        parser.add_argument("--source-url", required=True, help="Where this boundary data came from")
        parser.add_argument("--replace", action="store_true")

    def handle(self, *args, **o):
        with open(o["geojson_path"], encoding="utf-8") as fh:
            data = json.load(fh)
        feats = data.get("features")
        if not feats:
            raise CommandError("No features found in GeoJSON")
        if o["replace"]:
            Ward.objects.all().delete()
        n = 0
        for f in feats:
            props = f.get("properties") or {}
            name = props.get(o["name_field"])
            if not name:
                self.stderr.write(f"Skipping feature without '{o['name_field']}': {list(props)[:5]}")
                continue
            Ward.objects.create(name=str(name), code=str(props.get(o["code_field"], "")) if o["code_field"] else "",
                                geometry=f["geometry"], source_url=o["source_url"])
            n += 1
        self.stdout.write(self.style.SUCCESS(f"Loaded {n} wards"))

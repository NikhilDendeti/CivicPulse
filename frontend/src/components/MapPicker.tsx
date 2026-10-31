import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import { useEffect, useMemo, useRef } from "react";

export const HYDERABAD: [number, number] = [17.385, 78.4867];

const pin = L.divIcon({
  className: "pin",
  html: '<div class="pin-dot"></div>',
  iconSize: [28, 28],
  iconAnchor: [14, 28],
});

function Recenter({ pos }: { pos: [number, number] }) {
  const map = useMap();
  const first = useRef(true);
  useEffect(() => {
    map.setView(pos, first.current ? 17 : map.getZoom());
    first.current = false;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pos[0], pos[1]]);
  return null;
}

function ClickToPlace({ onChange }: { onChange: (p: [number, number]) => void }) {
  useMapEvents({ click: (e) => onChange([e.latlng.lat, e.latlng.lng]) });
  return null;
}

export default function MapPicker({ value, onChange }: { value: [number, number]; onChange: (p: [number, number]) => void }) {
  const handlers = useMemo(
    () => ({
      dragend(e: L.LeafletEvent) {
        const ll = (e.target as L.Marker).getLatLng();
        onChange([ll.lat, ll.lng]);
      },
    }),
    [onChange],
  );
  return (
    <MapContainer center={value} zoom={17} className="map" scrollWheelZoom={false}>
      <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} />
      <Recenter pos={value} />
      <ClickToPlace onChange={onChange} />
      <Marker position={value} draggable icon={pin} eventHandlers={handlers} />
    </MapContainer>
  );
}

/**
 * Google Maps JavaScript API の最小限の型定義。
 * `@types/google.maps` を追加せずに、この画面で使う範囲だけを宣言する。
 */

export type LatLngLiteral = { lat: number; lng: number };

export interface GMap {
  setCenter(position: LatLngLiteral): void;
  addListener(event: "click", handler: (event: { latLng?: GLatLng }) => void): void;
}

export interface GLatLng {
  lat(): number;
  lng(): number;
}

export interface GMarker {
  setPosition(position: LatLngLiteral): void;
  setMap(map: GMap | null): void;
  addListener(event: "click", handler: () => void): void;
}

export interface GeocoderResult {
  formatted_address: string;
}

export interface GMapsNamespace {
  Map: new (
    element: HTMLElement,
    options: {
      center: LatLngLiteral;
      zoom: number;
      disableDefaultUI?: boolean;
      zoomControl?: boolean;
       clickableIcons?: boolean;
    },
  ) => GMap;
  Marker: new (options: {
    position: LatLngLiteral;
    map: GMap;
    title?: string;
    icon?: unknown;
  }) => GMarker;
  Geocoder: new () => {
    geocode(
      request: { location: LatLngLiteral; language?: string },
      callback: (results: GeocoderResult[] | null, status: string) => void,
    ): void;
  };
}

declare global {
  interface Window {
    google?: { maps: GMapsNamespace };
    __spotcheckMapsLoader?: Promise<void>;
  }
}
